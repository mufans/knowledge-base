import inspect
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import opportunity_os.automation.hermes_runner as hermes_runner
from opportunity_os.automation.hermes_runner import CADENCES, CadenceRunner
from opportunity_os.errors import BoundaryError, ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def make_hermes_executable(tmp_path: Path, body: str = "#!/bin/sh\nexit 0\n") -> Path:
    executable = tmp_path / "bin" / "hermes"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(body, encoding="utf-8")
    executable.chmod(0o700)
    return executable


class ImmediateProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode


class CapturingProcessFactory:
    def __init__(self, returncodes: list[int] | None = None) -> None:
        self.returncodes = list(returncodes or [0])
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv: list[str], **kwargs) -> ImmediateProcess:
        self.calls.append((list(argv), dict(kwargs)))
        return ImmediateProcess(self.returncodes.pop(0))


def make_runner(tmp_path: Path, factory: CapturingProcessFactory | None = None) -> CadenceRunner:
    return CadenceRunner(
        tmp_path / "private",
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=factory or CapturingProcessFactory(),
        now=lambda: NOW,
    )


@pytest.mark.parametrize("cadence", sorted(CADENCES))
def test_exact_cadence_allowlist_accepts_only_documented_values(tmp_path: Path, cadence: str) -> None:
    assert make_runner(tmp_path).run(cadence, "2026-07-19").status == "success"


@pytest.mark.parametrize("cadence", ["hourly", "six_week", "quarterly ", "DAILY", "../../daily"])
def test_exact_cadence_allowlist_rejects_variants(tmp_path: Path, cadence: str) -> None:
    with pytest.raises(ValidationError):
        make_runner(tmp_path).run(cadence, "2026-07-19")


@pytest.mark.parametrize("period_key", ["", "../escape", "2026/07/19", ".hidden", "x" * 81])
def test_period_key_rejects_path_traversal_and_ambiguous_values(tmp_path: Path, period_key: str) -> None:
    with pytest.raises(ValidationError):
        make_runner(tmp_path).run("daily", period_key)


def test_successful_period_is_skipped_across_runner_instances(tmp_path: Path) -> None:
    factory = CapturingProcessFactory([0])
    first = make_runner(tmp_path, factory).run("weekly", "2026-W29")
    second = make_runner(tmp_path, factory).run("weekly", "2026-W29")

    assert first.status == "success"
    assert second.status == "skipped_duplicate"
    assert first.idempotency_key == "weekly:2026-W29"
    assert len(factory.calls) == 1


def test_failure_is_returned_but_not_marked_as_success_for_later_openclaw_run(tmp_path: Path) -> None:
    factory = CapturingProcessFactory([7, 0])
    runner = make_runner(tmp_path, factory)

    first = runner.run("daily", "2026-07-19")
    second = runner.run("daily", "2026-07-19")

    assert (first.status, first.error_class) == ("failed", "nonzero_exit")
    assert second.status == "success"
    assert len(factory.calls) == 2


def test_runner_invokes_fixed_profile_and_skill_once_without_scheduler_options(tmp_path: Path) -> None:
    executable = make_hermes_executable(tmp_path)
    working_directory = tmp_path / "work"
    working_directory.mkdir()
    factory = CapturingProcessFactory()
    runner = CadenceRunner(
        tmp_path / "private",
        hermes_path=executable,
        working_directory=working_directory,
        process_factory=factory,
        now=lambda: NOW,
    )

    assert runner.run("daily", "2026-07-19").status == "success"
    assert len(factory.calls) == 1
    argv, options = factory.calls[0]
    assert argv[:6] == [str(executable.resolve()), "-p", "opportunity-discovery", "chat", "-Q", "-q"]
    assert argv[6:10] == ["--source", "tool", "--skills", "opportunity-discovery"]
    assert "--yolo" not in argv
    assert not any(term in argv for term in ("message", "cron", "gateway"))
    assert options == {
        "cwd": str(working_directory.resolve()),
        "env": {
            "HOME": str(Path.home()),
            "LANG": "C.UTF-8",
            "PATH": f"{executable.parent.resolve()}:/usr/bin:/bin",
        },
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    prompt = argv[-1]
    for required in ("广域输入", "反对证据", "意外发现", "不得执行任何外部行动", "改进建议草案"):
        assert required in prompt
    assert "不得修改 Memory 或 Skill" in prompt


def test_unexpected_provider_error_is_persisted_without_secret_details(tmp_path: Path) -> None:
    class BrokenFactory(CapturingProcessFactory):
        def __call__(self, argv: list[str], **kwargs) -> ImmediateProcess:
            raise RuntimeError("provider token=abcdefghijklmnop")

    home = tmp_path / "private"
    record = CadenceRunner(
        home,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=BrokenFactory(),
        now=lambda: NOW,
    ).run("daily", "2026-07-19")

    assert (record.status, record.error_class) == ("failed", "execution_error")
    assert "token" not in json.dumps(record.to_dict()).casefold()
    record_path = home / "dashboard" / "runs" / "daily" / "2026-07-19.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert "token" not in json.dumps(payload).casefold()


def test_success_record_is_atomic_0600_and_secret_free(tmp_path: Path) -> None:
    home = tmp_path / "private"
    record = make_runner(tmp_path).run("daily", "2026-07-19")
    record_path = home / "dashboard" / "runs" / "daily" / "2026-07-19.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))

    assert record_path.stat().st_mode & 0o777 == 0o600
    assert payload["status"] == "success"
    assert payload["run_id"] == record.run_id
    assert "token" not in json.dumps(payload).casefold()
    assert list(record_path.parent.glob("*.tmp")) == []


def test_malformed_or_mismatched_success_record_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "private"
    record_path = home / "dashboard" / "runs" / "daily" / "2026-07-19.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps({"status": "success", "cadence": "weekly"}), encoding="utf-8")
    factory = CapturingProcessFactory()

    with pytest.raises(ValidationError):
        make_runner(tmp_path, factory).run("daily", "2026-07-19")
    assert factory.calls == []


@pytest.mark.parametrize("link_kind", ["home", "dashboard", "runs", "cadence", "record"])
def test_runtime_rejects_symlink_components_before_target_write(tmp_path: Path, link_kind: str) -> None:
    external = tmp_path / "knowledge" / "raw"
    external.mkdir(parents=True)
    sentinel = external / "sentinel.md"
    sentinel.write_text("unchanged", encoding="utf-8")
    before = (sentinel.read_bytes(), external.stat().st_mtime_ns)
    private = tmp_path / "private"
    if link_kind == "home":
        private.symlink_to(external, target_is_directory=True)
    else:
        private.mkdir()
        dashboard = private / "dashboard"
        if link_kind == "dashboard":
            dashboard.symlink_to(external, target_is_directory=True)
        else:
            dashboard.mkdir()
            runs = dashboard / "runs"
            if link_kind == "runs":
                runs.symlink_to(external, target_is_directory=True)
            else:
                runs.mkdir()
                cadence = runs / "daily"
                if link_kind == "cadence":
                    cadence.symlink_to(external, target_is_directory=True)
                else:
                    cadence.mkdir()
                    (cadence / "2026-07-19.json").symlink_to(sentinel)
    runner = CadenceRunner(
        private,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=CapturingProcessFactory(),
        now=lambda: NOW,
    )

    with pytest.raises(BoundaryError):
        runner.run("daily", "2026-07-19")
    assert before == (sentinel.read_bytes(), external.stat().st_mtime_ns)


def test_architecture_guard_has_no_second_scheduler_or_process_supervisor() -> None:
    source = inspect.getsource(hermes_runner)
    forbidden = (
        "exclusive_arbitration",
        "lock",
        "heartbeat",
        "os.killpg",
        "start_new_session",
        "TimeoutExpired",
        "timeout",
        "retry",
        "CADENCE_TIMEOUTS",
        "stale_after_seconds",
        "termination_grace_seconds",
    )

    assert {token for token in forbidden if token in source} == set()
