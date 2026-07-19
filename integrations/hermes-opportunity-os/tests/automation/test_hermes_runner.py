import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor

from opportunity_os.automation.hermes_runner import CADENCE_TIMEOUTS, CadenceRunner
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
        self.pid = os.getpid()
        self.returncode = returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
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
    factory = CapturingProcessFactory([0])
    first = make_runner(tmp_path, factory).run("weekly", "2026-W29")
    second = make_runner(tmp_path, factory).run("weekly", "2026-W29")

    assert first.status == "success"
    assert second.status == "skipped_duplicate"
    assert len(factory.calls) == 1
    assert first.idempotency_key == "weekly:2026-W29"


def test_runner_uses_fixed_quiet_non_yolo_hermes_argv_and_safe_prompt(tmp_path: Path) -> None:
    factory = CapturingProcessFactory()
    make_runner(tmp_path, factory).run("daily", "2026-07-19")

    argv, _ = factory.calls[0]
    assert Path(argv[0]).name == "hermes"
    assert argv[1:6] == ["-p", "opportunity-discovery", "chat", "-Q", "-q"]
    assert "--yolo" not in argv
    assert not any(term in argv for term in ("message", "cron", "gateway"))
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
    assert CADENCE_TIMEOUTS[cadence] == expected_timeout


def test_active_atomic_mkdir_lock_returns_locked_without_invoking_hermes(tmp_path: Path) -> None:
    home = tmp_path / "private"
    lock = home / "dashboard" / "locks" / "daily.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps({"pid": os.getpid(), "started_at": NOW.isoformat(), "run_id": "other"}), encoding="utf-8"
    )
    factory = CapturingProcessFactory()

    record = CadenceRunner(
        home,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
    ).run("daily", "2026-07-19")

    assert record.status == "locked"
    assert factory.calls == []


def test_stale_dead_owner_lock_is_reclaimed(tmp_path: Path) -> None:
    home = tmp_path / "private"
    lock = home / "dashboard" / "locks" / "daily.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps({"pid": 999_999_999, "started_at": "2026-07-19T08:00:00+00:00", "run_id": "dead"}),
        encoding="utf-8",
    )
    factory = CapturingProcessFactory()

    record = CadenceRunner(
        home,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
        stale_after_seconds=60,
    ).run(
        "daily", "2026-07-19"
    )

    assert record.status == "success"
    assert len(factory.calls) == 1


def test_heartbeat_is_atomic_0600_and_records_terminal_success(tmp_path: Path) -> None:
    home = tmp_path / "private"
    record = make_runner(tmp_path).run("daily", "2026-07-19")
    heartbeat = home / "dashboard" / "heartbeats" / "daily.json"
    payload = json.loads(heartbeat.read_text(encoding="utf-8"))

    assert heartbeat.stat().st_mode & 0o777 == 0o600
    assert payload["status"] == "success"
    assert payload["run_id"] == record.run_id
    assert list(heartbeat.parent.glob("*.tmp")) == []


def test_nonzero_and_timeout_are_persisted_as_terminal_failures(tmp_path: Path) -> None:
    home = tmp_path / "private"
    failed = CadenceRunner(
        home,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=CapturingProcessFactory([7]),
        now=lambda: NOW,
    )
    failure_record = failed.run("daily", "2026-07-19")

    assert failure_record.status == "failed"
    assert failure_record.error_class == "nonzero_exit"
    rendered = json.dumps(failure_record.to_dict())
    assert "private detail" not in rendered
    assert "secret" not in rendered


def test_unexpected_runner_exception_is_a_secret_free_terminal_failure(tmp_path: Path) -> None:
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
    heartbeat = json.loads((home / "dashboard" / "heartbeats" / "daily.json").read_text(encoding="utf-8"))

    assert record.status == "failed"
    assert record.error_class == "execution_error"
    assert heartbeat["status"] == "failed"
    assert "token" not in json.dumps(heartbeat).casefold()


def test_same_period_concurrency_invokes_hermes_only_once(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    class BlockingProcess(ImmediateProcess):
        def wait(self, timeout: float | None = None) -> int:
            assert release.wait(2)
            return 0

    class BlockingFactory(CapturingProcessFactory):
        def __call__(self, argv: list[str], **kwargs) -> BlockingProcess:
            self.calls.append((list(argv), dict(kwargs)))
            entered.set()
            return BlockingProcess()

    factory = BlockingFactory()
    first_runner = make_runner(tmp_path, factory)
    second_runner = make_runner(tmp_path, factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_runner.run, "weekly", "2026-W29")
        assert entered.wait(2)
        second = pool.submit(second_runner.run, "weekly", "2026-W29")
        second_record = second.result(timeout=2)
        release.set()
        first_record = first.result(timeout=2)

    assert {first_record.status, second_record.status} == {"success", "locked"}
    assert len(factory.calls) == 1


def test_popen_contract_uses_real_absolute_hermes_minimal_env_cwd_and_exact_argv(tmp_path: Path) -> None:
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
    argv, options = factory.calls[0]
    assert argv[:6] == [str(executable.resolve()), "-p", "opportunity-discovery", "chat", "-Q", "-q"]
    assert argv[6:10] == ["--source", "tool", "--skills", "opportunity-discovery"]
    assert "--yolo" not in argv
    assert options["cwd"] == str(working_directory.resolve())
    assert options["env"] == {
        "HOME": str(Path.home()),
        "LANG": "C.UTF-8",
        "PATH": f"{executable.parent.resolve()}:/usr/bin:/bin",
    }
    assert options["start_new_session"] is True
    assert options["stdin"] is subprocess.DEVNULL
    assert options["stdout"] is subprocess.DEVNULL
    assert options["stderr"] is subprocess.DEVNULL


def test_default_argv_keeps_fixed_home_local_bin_entry_after_realpath_validation(
    tmp_path: Path, monkeypatch
) -> None:
    fake_home = tmp_path / "home"
    target = fake_home / "runtime" / "hermes"
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    target.chmod(0o700)
    entry = fake_home / ".local" / "bin" / "hermes"
    entry.parent.mkdir(parents=True)
    entry.symlink_to(target)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    factory = CapturingProcessFactory()
    runner = CadenceRunner(
        tmp_path / "private",
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
    )

    assert runner.run("daily", "2026-07-19").status == "success"
    argv, options = factory.calls[0]
    assert argv[0] == str(entry)
    assert options["env"]["PATH"].startswith(f"{entry.parent}:")


@pytest.mark.parametrize("path_kind", ["relative", "wrong_basename", "symlink"])
def test_hermes_executable_must_be_absolute_real_executable_named_hermes(tmp_path: Path, path_kind: str) -> None:
    real = make_hermes_executable(tmp_path)
    if path_kind == "relative":
        candidate = Path("bin/hermes")
    elif path_kind == "wrong_basename":
        candidate = real.with_name("not-hermes")
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o700)
    else:
        target = real.with_name("actual-binary")
        real.rename(target)
        real.symlink_to(target)
        candidate = real

    with pytest.raises(ValidationError):
        CadenceRunner(tmp_path / "private", hermes_path=candidate, working_directory=tmp_path)


def test_failed_and_timeout_periods_retry_until_success_with_monotonic_attempt(tmp_path: Path) -> None:
    executable = make_hermes_executable(tmp_path)
    factory = CapturingProcessFactory([7, 0])
    runner = CadenceRunner(
        tmp_path / "private",
        hermes_path=executable,
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
    )

    first = runner.run("daily", "2026-07-19")
    second = runner.run("daily", "2026-07-19")
    duplicate = runner.run("daily", "2026-07-19")

    assert (first.status, first.attempt) == ("failed", 1)
    assert (second.status, second.attempt) == ("success", 2)
    assert (duplicate.status, duplicate.attempt) == ("skipped_duplicate", 2)
    assert len(factory.calls) == 2
    persisted = json.loads((tmp_path / "private" / "dashboard" / "runs" / "daily" / "2026-07-19.json").read_text())
    assert (persisted["status"], persisted["attempt"]) == ("success", 2)


def test_persisted_timeout_is_retryable_and_does_not_block_next_attempt(tmp_path: Path) -> None:
    home = tmp_path / "private"
    record_path = home / "dashboard" / "runs" / "daily" / "2026-07-19.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps({"status": "timeout", "attempt": 3, "run_id": "old-timeout"}), encoding="utf-8"
    )
    factory = CapturingProcessFactory([0])
    runner = CadenceRunner(
        home,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
    )

    record = runner.run("daily", "2026-07-19")

    assert (record.status, record.attempt) == ("success", 4)
    assert len(factory.calls) == 1


def test_running_heartbeat_refreshes_periodically_and_stops_at_terminal(tmp_path: Path) -> None:
    executable = make_hermes_executable(tmp_path, "#!/bin/sh\nsleep 0.35\n")
    home = tmp_path / "private"
    runner = CadenceRunner(
        home,
        hermes_path=executable,
        working_directory=tmp_path,
        heartbeat_interval_seconds=0.05,
    )
    result = []
    thread = threading.Thread(target=lambda: result.append(runner.run("daily", "2026-07-19")))
    thread.start()
    heartbeat = home / "dashboard" / "heartbeats" / "daily.json"
    deadline = time.monotonic() + 2
    observed_updates = set()
    while thread.is_alive() and time.monotonic() < deadline:
        if heartbeat.exists():
            payload = json.loads(heartbeat.read_text(encoding="utf-8"))
            if payload["status"] == "running":
                observed_updates.add(payload["updated_at"])
        time.sleep(0.02)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert result[0].status == "success"
    assert len(observed_updates) >= 2
    terminal = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert terminal["status"] == "success"
    terminal_mtime = heartbeat.stat().st_mtime_ns
    time.sleep(0.1)
    assert heartbeat.stat().st_mtime_ns == terminal_mtime


def test_timeout_terminates_entire_process_group_including_grandchild(tmp_path: Path, monkeypatch) -> None:
    executable = make_hermes_executable(
        tmp_path,
        "#!/bin/sh\ntrap 'exit 0' TERM\nsh -c 'trap \"\" TERM; sleep 30' &\necho $! > child.pid\nwait\n",
    )
    monkeypatch.setitem(
        __import__("opportunity_os.automation.hermes_runner", fromlist=["CADENCE_TIMEOUTS"]).CADENCE_TIMEOUTS,
        "daily",
        0.8,
    )
    runner = CadenceRunner(
        tmp_path / "private",
        hermes_path=executable,
        working_directory=tmp_path,
        heartbeat_interval_seconds=0.05,
        termination_grace_seconds=0.1,
    )

    record = runner.run("daily", "2026-07-19")
    child_pid = int((tmp_path / "child.pid").read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)

    assert record.status == "timeout"
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_heartbeat_supervision_failure_terminates_child_and_grandchild_before_unlock(
    tmp_path: Path, monkeypatch
) -> None:
    executable = make_hermes_executable(
        tmp_path,
        "#!/bin/sh\ntrap 'exit 0' TERM\nsh -c 'trap \"\" TERM; sleep 30' &\necho $! > child.pid\nwait\n",
    )
    runner = CadenceRunner(
        tmp_path / "private",
        hermes_path=executable,
        working_directory=tmp_path,
        heartbeat_interval_seconds=0.05,
        termination_grace_seconds=0.1,
    )
    original_heartbeat = runner._heartbeat
    calls = 0

    def failing_heartbeat(heartbeats_fd, record) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            deadline = time.monotonic() + 1
            while not (tmp_path / "child.pid").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert (tmp_path / "child.pid").is_file()
            raise OSError("simulated heartbeat failure")
        original_heartbeat(heartbeats_fd, record)

    monkeypatch.setattr(runner, "_heartbeat", failing_heartbeat)
    child_pid = None
    try:
        record = runner.run("daily", "2026-07-19")
        child_pid = int((tmp_path / "child.pid").read_text(encoding="utf-8"))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)

        assert record.status == "failed"
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        assert not (tmp_path / "private" / "dashboard" / "locks" / "daily.lock").exists()
    finally:
        if child_pid is not None:
            try:
                os.killpg(os.getpgid(child_pid), 9)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("link_kind", ["home", "dashboard", "locks", "runs", "heartbeats"])
def test_cadence_runtime_rejects_symlink_components_before_any_target_write(
    tmp_path: Path, link_kind: str
) -> None:
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
            (dashboard / link_kind).symlink_to(external, target_is_directory=True)
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


def test_cadence_arbitration_file_is_permanent_nofollow_and_0600(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    assert runner.run("daily", "2026-07-19").status == "success"
    arbitration = tmp_path / "private" / "dashboard" / "locks" / ".cadence-arbitration.lock"

    assert arbitration.is_file() and not arbitration.is_symlink()
    assert arbitration.stat().st_mode & 0o777 == 0o600


def test_two_cadence_contenders_cannot_steal_new_lock_after_stale_takeover(tmp_path: Path) -> None:
    home = tmp_path / "private"
    stale = home / "dashboard" / "locks" / "daily.lock"
    stale.mkdir(parents=True)
    (stale / "owner.json").write_text(
        json.dumps({"pid": 999_999_999, "started_at": "2020-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    entered = threading.Event()
    release = threading.Event()

    class BlockingProcess(ImmediateProcess):
        def wait(self, timeout: float | None = None) -> int:
            assert release.wait(2)
            return 0

    class BlockingFactory(CapturingProcessFactory):
        def __call__(self, argv: list[str], **kwargs) -> BlockingProcess:
            self.calls.append((list(argv), dict(kwargs)))
            entered.set()
            return BlockingProcess()

    factory = BlockingFactory()
    first = CadenceRunner(
        home,
        hermes_path=make_hermes_executable(tmp_path),
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
        stale_after_seconds=1,
    )
    second = CadenceRunner(
        home,
        hermes_path=tmp_path / "bin" / "hermes",
        working_directory=tmp_path,
        process_factory=factory,
        now=lambda: NOW,
        stale_after_seconds=1,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first.run, "daily", "2026-07-19")
        assert entered.wait(2)
        second_future = pool.submit(second.run, "daily", "2026-07-19")
        second_record = second_future.result(timeout=2)
        release.set()
        first_record = first_future.result(timeout=2)

    assert {first_record.status, second_record.status} == {"success", "locked"}
    assert len(factory.calls) == 1
