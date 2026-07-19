import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor

from opportunity_os.automation.hermes_runner import CadenceRunner
from opportunity_os.errors import ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakeCommandRunner:
    def __init__(self, *, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[tuple[list[str], int]] = []

    def __call__(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(argv), timeout))
        return subprocess.CompletedProcess(argv, self.returncode, stdout="ok", stderr=self.stderr)


def make_runner(tmp_path: Path, command: FakeCommandRunner | None = None) -> CadenceRunner:
    return CadenceRunner(tmp_path / "private", command_runner=command or FakeCommandRunner(), now=lambda: NOW)


@pytest.mark.parametrize("cadence", ["daily", "weekly", "biweekly", "six-week", "quarterly"])
def test_exact_cadence_allowlist_accepts_only_documented_values(tmp_path: Path, cadence: str) -> None:
    record = make_runner(tmp_path).run(cadence, "2026-07-19")
    assert record.status == "success"


@pytest.mark.parametrize("cadence", ["hourly", "six_week", "quarterly ", "DAILY", "../../daily"])
def test_exact_cadence_allowlist_rejects_variants(tmp_path: Path, cadence: str) -> None:
    with pytest.raises(ValidationError):
        make_runner(tmp_path).run(cadence, "2026-07-19")


@pytest.mark.parametrize("period_key", ["", "../escape", "2026/07/19", ".hidden", "x" * 81])
def test_period_key_rejects_path_traversal_and_ambiguous_values(tmp_path: Path, period_key: str) -> None:
    with pytest.raises(ValidationError):
        make_runner(tmp_path).run("daily", period_key)


def test_duplicate_period_is_skipped_across_runner_instances(tmp_path: Path) -> None:
    command = FakeCommandRunner()
    first = make_runner(tmp_path, command).run("weekly", "2026-W29")
    second = make_runner(tmp_path, command).run("weekly", "2026-W29")

    assert first.status == "success"
    assert second.status == "skipped_duplicate"
    assert len(command.calls) == 1
    assert first.idempotency_key == "weekly:2026-W29"


def test_runner_uses_fixed_quiet_non_yolo_hermes_argv_and_safe_prompt(tmp_path: Path) -> None:
    command = FakeCommandRunner()
    make_runner(tmp_path, command).run("daily", "2026-07-19")

    argv, timeout = command.calls[0]
    assert argv[:6] == ["hermes", "-p", "opportunity-discovery", "chat", "-Q", "-q"]
    assert "--yolo" not in argv
    assert not any(term in argv for term in ("message", "cron", "gateway"))
    assert timeout == 1500
    prompt = argv[-1]
    for required in ("广域输入", "反对证据", "意外发现", "不得执行任何外部行动", "改进建议草案"):
        assert required in prompt
    assert "不得修改 Memory 或 Skill" in prompt


@pytest.mark.parametrize(
    ("cadence", "expected_timeout"),
    [("daily", 1500), ("weekly", 3000), ("biweekly", 3000), ("six-week", 3600), ("quarterly", 3600)],
)
def test_every_cadence_has_an_explicit_bounded_timeout(
    tmp_path: Path, cadence: str, expected_timeout: int
) -> None:
    command = FakeCommandRunner()
    make_runner(tmp_path, command).run(cadence, "2026-07-19")
    assert command.calls[0][1] == expected_timeout


def test_active_atomic_mkdir_lock_returns_locked_without_invoking_hermes(tmp_path: Path) -> None:
    home = tmp_path / "private"
    lock = home / "dashboard" / "locks" / "daily.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps({"pid": os.getpid(), "started_at": NOW.isoformat(), "run_id": "other"}), encoding="utf-8"
    )
    command = FakeCommandRunner()

    record = CadenceRunner(home, command_runner=command, now=lambda: NOW).run("daily", "2026-07-19")

    assert record.status == "locked"
    assert command.calls == []


def test_stale_dead_owner_lock_is_reclaimed(tmp_path: Path) -> None:
    home = tmp_path / "private"
    lock = home / "dashboard" / "locks" / "daily.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps({"pid": 999_999_999, "started_at": "2026-07-19T08:00:00+00:00", "run_id": "dead"}),
        encoding="utf-8",
    )
    command = FakeCommandRunner()

    record = CadenceRunner(home, command_runner=command, now=lambda: NOW, stale_after_seconds=60).run(
        "daily", "2026-07-19"
    )

    assert record.status == "success"
    assert len(command.calls) == 1


def test_heartbeat_is_atomic_0600_and_records_terminal_success(tmp_path: Path) -> None:
    home = tmp_path / "private"
    record = CadenceRunner(home, command_runner=FakeCommandRunner(), now=lambda: NOW).run(
        "daily", "2026-07-19"
    )
    heartbeat = home / "dashboard" / "heartbeats" / "daily.json"
    payload = json.loads(heartbeat.read_text(encoding="utf-8"))

    assert heartbeat.stat().st_mode & 0o777 == 0o600
    assert payload["status"] == "success"
    assert payload["run_id"] == record.run_id
    assert list(heartbeat.parent.glob("*.tmp")) == []


def test_nonzero_and_timeout_are_persisted_as_terminal_failures(tmp_path: Path) -> None:
    home = tmp_path / "private"
    failed = CadenceRunner(home, command_runner=FakeCommandRunner(returncode=7, stderr="private detail"), now=lambda: NOW)
    failure_record = failed.run("daily", "2026-07-19")

    class TimeoutRunner(FakeCommandRunner):
        def __call__(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(argv, timeout, output="secret", stderr="private")

    timeout_record = CadenceRunner(home, command_runner=TimeoutRunner(), now=lambda: NOW).run(
        "weekly", "2026-W29"
    )

    assert failure_record.status == "failed"
    assert failure_record.error_class == "nonzero_exit"
    assert timeout_record.status == "timeout"
    assert timeout_record.error_class == "timeout"
    rendered = json.dumps([failure_record.to_dict(), timeout_record.to_dict()])
    assert "private detail" not in rendered
    assert "secret" not in rendered


def test_unexpected_runner_exception_is_a_secret_free_terminal_failure(tmp_path: Path) -> None:
    class BrokenRunner(FakeCommandRunner):
        def __call__(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            raise RuntimeError("provider token=abcdefghijklmnop")

    home = tmp_path / "private"
    record = CadenceRunner(home, command_runner=BrokenRunner(), now=lambda: NOW).run("daily", "2026-07-19")
    heartbeat = json.loads((home / "dashboard" / "heartbeats" / "daily.json").read_text(encoding="utf-8"))

    assert record.status == "failed"
    assert record.error_class == "execution_error"
    assert heartbeat["status"] == "failed"
    assert "token" not in json.dumps(heartbeat).casefold()


def test_same_period_concurrency_invokes_hermes_only_once(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    class BlockingRunner(FakeCommandRunner):
        def __call__(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            self.calls.append((list(argv), timeout))
            entered.set()
            assert release.wait(2)
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    command = BlockingRunner()
    first_runner = make_runner(tmp_path, command)
    second_runner = make_runner(tmp_path, command)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_runner.run, "weekly", "2026-W29")
        assert entered.wait(2)
        second = pool.submit(second_runner.run, "weekly", "2026-W29")
        second_record = second.result(timeout=2)
        release.set()
        first_record = first.result(timeout=2)

    assert {first_record.status, second_record.status} == {"success", "locked"}
    assert len(command.calls) == 1
