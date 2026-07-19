import json

import pytest

from opportunity_os.dashboard.probes import CommandResult
from opportunity_os.dashboard.tasks import DEFAULT_OPENCLAW_EXECUTABLE, OpenClawTaskAdapter


class Runner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, argv, timeout):
        self.calls.append((argv, timeout))
        return self.result


def test_adapter_has_only_three_fixed_read_shapes() -> None:
    job = {"id": "job-1", "enabled": True, "updatedAtMs": 1, "schedule": {"expr": "0 8 * * *", "tz": "Asia/Shanghai"}, "payload": "private"}
    runner = Runner(CommandResult(0, json.dumps({"jobs": [job]}), "", False, 1))
    adapter = OpenClawTaskAdapter(runner)
    tasks = adapter.list()
    runner.result = CommandResult(0, json.dumps({"enabled": True, "jobs": 1, "nextWakeAtMs": 123}), "", False, 1)
    status = adapter.status()
    runner.result = CommandResult(0, json.dumps({"runs": []}), "", False, 1)
    adapter.runs("job-1")

    assert tasks[0].model_dump() == {
        "job_id": "job-1", "enabled": True, "cron": "0 8 * * *", "tz": "Asia/Shanghai",
        "updated_at_ms": 1, "provider_status": "unknown", "cost_status": "unknown",
    }
    assert runner.calls == [
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "list", "--all", "--json"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "status", "--json"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "runs", "--id", "job-1", "--limit", "50"), 10),
    ]
    assert status.ok is True
    assert status.scheduler_enabled is True
    assert status.job_count == 1
    assert status.next_wake_at_ms == 123


def test_disabled_scheduler_is_not_reported_ok() -> None:
    runner = Runner(CommandResult(
        0, json.dumps({"enabled": False, "jobs": 42, "nextWakeAtMs": None}), "", False, 1
    ))

    status = OpenClawTaskAdapter(runner).status()

    assert status.ok is False
    assert status.scheduler_enabled is False
    assert status.error_code == "scheduler_disabled"


def test_cron_without_explicit_timezone_is_a_valid_native_job() -> None:
    job = {
        "id": "job-local-zone", "enabled": True, "updatedAtMs": 1,
        "schedule": {"kind": "cron", "expr": "0 8 * * *"},
    }
    adapter = OpenClawTaskAdapter(Runner(CommandResult(
        0, json.dumps({"jobs": [job]}), "", False, 1
    )))

    summary = adapter.list()[0]

    assert summary.cron == "0 8 * * *"
    assert summary.tz is None


def test_adapter_rejects_cli_like_identifier() -> None:
    adapter = OpenClawTaskAdapter(Runner(CommandResult(0, "{}", "", False, 1)))
    with pytest.raises(ValueError):
        adapter.runs("--help")
