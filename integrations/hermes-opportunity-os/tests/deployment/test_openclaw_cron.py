import json
from pathlib import Path

import pytest

from opportunity_os.deployment.openclaw_cron import (
    CronManifest,
    OpenClawCronClient,
    reconcile,
)


MANIFEST = Path(__file__).parents[2] / "deployment/openclaw/cron-jobs.json"
OWNER_PLACEHOLDER = "__OPENCLAW_DINGTALK_OWNER__"


def configured_manifest(tmp_path: Path) -> Path:
    destination = tmp_path / "jobs.json"
    destination.write_text(MANIFEST.read_text(encoding="utf-8").replace(OWNER_PLACEHOLDER, "owner-safe-id"), encoding="utf-8")
    return destination


class RecordingRunner:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, argv, *, env, **kwargs):
        self.calls.append((list(argv), dict(env)))
        return type("Result", (), {"returncode": 0, "stdout": next(self.responses), "stderr": ""})()


def test_manifest_has_three_native_jobs_and_native_failure_alerts() -> None:
    manifest = CronManifest.load(MANIFEST)
    assert {job.name for job in manifest.jobs} == {
        "opportunity-os-daily",
        "opportunity-os-weekly",
        "opportunity-os-healthcheck",
    }
    assert all(job.failure_alert.enabled for job in manifest.jobs)
    assert all(job.failure_alert.exclude_skipped for job in manifest.jobs)
    assert all(job.timezone == "Asia/Shanghai" for job in manifest.jobs)
    assert all(job.failure_alert.channel == "dingtalk" for job in manifest.jobs)
    assert all(job.failure_alert.to == OWNER_PLACEHOLDER for job in manifest.jobs)
    assert all(job.delivery_to == OWNER_PLACEHOLDER for job in manifest.jobs)
    assert {job.delivery for job in manifest.jobs} == {"announce", "none"}
    assert all("If the exec exits non-zero" in job.message for job in manifest.jobs)
    assert all("fail the Cron task" in job.message for job in manifest.jobs)
    assert all("do not convert" in job.message for job in manifest.jobs)


def test_manifest_rejects_unknown_fields_and_shell_like_names(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "name": "bad;name",
                        "cron": "0 1 * * *",
                        "timezone": "Asia/Shanghai",
                        "message": "x",
                        "enabled": True,
                        "session": "isolated",
                        "timeout_seconds": 30,
                        "delivery": "none",
                        "failure_alert": {
                            "enabled": True,
                            "after": 1,
                            "cooldown": "1h",
                            "exclude_skipped": True,
                        },
                        "unexpected": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        CronManifest.load(path)


def test_reconcile_is_dry_run_by_default_and_never_uses_a_shell() -> None:
    runner = RecordingRunner([json.dumps({"jobs": []})])
    client = OpenClawCronClient(
        executable="/opt/homebrew/bin/openclaw",
        runner=runner,
        environ={"HOME": "/Users/example", "PATH": "/usr/bin", "SECRET": "no"},
    )

    result = reconcile(CronManifest.load(MANIFEST), client)

    assert result.applied is False
    assert [action.kind for action in result.actions] == ["add", "add", "add"]
    assert runner.calls == [
        (
            ["/opt/homebrew/bin/openclaw", "cron", "list", "--all", "--json"],
            {"HOME": "/Users/example", "PATH": "/usr/bin"},
        )
    ]


def test_apply_adds_jobs_then_configures_openclaw_native_failure_alerts(tmp_path: Path) -> None:
    runner = RecordingRunner(
        [
            json.dumps({"jobs": []}),
            json.dumps({"id": "job-daily"}),
            "{}",
            json.dumps({"id": "job-weekly"}),
            "{}",
            json.dumps({"id": "job-health"}),
            "{}",
        ]
    )
    client = OpenClawCronClient(
        executable="/opt/homebrew/bin/openclaw",
        runner=runner,
        environ={"HOME": "/Users/example", "PATH": "/usr/bin", "TOKEN": "not-forwarded"},
    )

    result = reconcile(CronManifest.load(configured_manifest(tmp_path)), client, apply=True)

    assert result.applied is True
    mutation_argv = [argv for argv, _ in runner.calls[1:]]
    assert len(mutation_argv) == 6
    assert all(argv[:3] in (["/opt/homebrew/bin/openclaw", "cron", "add"], ["/opt/homebrew/bin/openclaw", "cron", "edit"]) for argv in mutation_argv)
    for argv in mutation_argv[1::2]:
        assert "--failure-alert" in argv
        assert "--failure-alert-exclude-skipped" in argv
        assert "--failure-alert-cooldown" in argv
        assert "dingtalk" in argv
        assert "owner-safe-id" in argv
    assert all("not-forwarded" not in value for argv, env in runner.calls for value in [*argv, *env.values()])


def test_obsolete_managed_jobs_are_disabled_not_deleted(tmp_path: Path) -> None:
    current = {
        "jobs": [
            {
                "id": "old-id",
                "name": "opportunity-os-old",
                "enabled": True,
                "schedule": {"kind": "cron", "expr": "0 1 * * *", "tz": "Asia/Shanghai"},
                "payload": {"kind": "agentTurn", "message": "old"},
                "sessionTarget": "isolated",
            }
        ]
    }
    runner = RecordingRunner([json.dumps(current), json.dumps({"id": "one"}), "{}", json.dumps({"id": "two"}), "{}", json.dumps({"id": "three"}), "{}", "{}"])
    client = OpenClawCronClient(executable="/usr/local/bin/openclaw", runner=runner, environ={})

    reconcile(CronManifest.load(configured_manifest(tmp_path)), client, apply=True)

    assert ["/usr/local/bin/openclaw", "cron", "disable", "old-id"] in [call[0] for call in runner.calls]
    assert not any("rm" in call[0] for call in runner.calls)


def test_apply_refuses_unresolved_owner_placeholder() -> None:
    runner = RecordingRunner([json.dumps({"jobs": []})])
    client = OpenClawCronClient(executable="/usr/bin/openclaw", runner=runner, environ={})
    with pytest.raises(ValueError, match="placeholder"):
        reconcile(CronManifest.load(MANIFEST), client, apply=True)
    assert runner.calls == []


def test_status_run_and_runs_are_native_read_only_or_explicit_operations() -> None:
    runner = RecordingRunner(["{}", "{}", "{}"])
    client = OpenClawCronClient(executable="/usr/bin/openclaw", runner=runner, environ={})
    client.status()
    client.run("safe-id")
    client.runs("safe-id")
    assert [call[0] for call in runner.calls] == [
        ["/usr/bin/openclaw", "cron", "status", "--json"],
        ["/usr/bin/openclaw", "cron", "run", "safe-id"],
        ["/usr/bin/openclaw", "cron", "runs", "--id", "safe-id"],
    ]
    with pytest.raises(ValueError):
        client.run("../bad")


def test_reconcile_repairs_native_delivery_timeout_and_failure_alert_drift() -> None:
    desired = CronManifest.load(MANIFEST).jobs[0]
    current = {
        "jobs": [
            {
                "id": "daily-id",
                "name": desired.name,
                "description": desired.description,
                "enabled": True,
                "schedule": {"kind": "cron", "expr": desired.cron, "tz": desired.timezone},
                "payload": {"kind": "agentTurn", "message": desired.message, "timeoutSeconds": 99},
                "delivery": {"mode": "none"},
                "failureAlert": {"enabled": True, "after": 9, "cooldownMs": 1, "includeSkipped": True},
                "sessionTarget": desired.session,
            }
        ]
    }
    runner = RecordingRunner([json.dumps(current)])
    client = OpenClawCronClient(executable="/usr/bin/openclaw", runner=runner, environ={})
    result = reconcile(CronManifest((desired,)), client)
    assert result.actions == (type(result.actions[0])("edit", desired.name, "daily-id"),)


def test_reconcile_is_idempotent_against_openclaw_native_job_shape() -> None:
    desired = CronManifest.load(MANIFEST).jobs[0]
    current = {
        "jobs": [
            {
                "id": "daily-id",
                "agentId": "main",
                "name": desired.name,
                "description": desired.description,
                "enabled": desired.enabled,
                "wakeMode": "now",
                "schedule": {"kind": "cron", "expr": desired.cron, "tz": desired.timezone},
                "payload": {"kind": "agentTurn", "message": desired.message, "timeoutSeconds": desired.timeout_seconds, "toolsAllow": ["exec"]},
                "delivery": {"mode": desired.delivery, "channel": "dingtalk", "to": "__OPENCLAW_DINGTALK_OWNER__"},
                "failureAlert": {"after": 2, "cooldownMs": 3_600_000, "includeSkipped": False, "mode": "announce", "channel": "dingtalk", "to": "__OPENCLAW_DINGTALK_OWNER__"},
                "sessionTarget": desired.session,
            }
        ]
    }
    runner = RecordingRunner([json.dumps(current)])
    client = OpenClawCronClient(executable="/usr/bin/openclaw", runner=runner, environ={})
    assert reconcile(CronManifest((desired,)), client).actions == ()
