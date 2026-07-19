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
    adapter.status()
    adapter.runs("job-1")

    assert tasks[0].model_dump() == {
        "job_id": "job-1", "enabled": True, "cron": "0 8 * * *", "tz": "Asia/Shanghai",
        "updated_at_ms": 1, "provider_status": "unknown", "cost_status": "unknown",
    }
    assert runner.calls == [
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "list", "--all", "--json"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "status"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "runs", "--id", "job-1", "--limit", "50"), 10),
    ]


def test_adapter_rejects_cli_like_identifier() -> None:
    adapter = OpenClawTaskAdapter(Runner(CommandResult(0, "{}", "", False, 1)))
    with pytest.raises(ValueError):
        adapter.runs("--help")
