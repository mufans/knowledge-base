from pathlib import Path

import pytest

from opportunity_os.deployment.kb_sync import LIVE_SYNC_SCRIPT, KnowledgeSync


def test_uses_only_agents_declared_live_sync_script() -> None:
    sync = KnowledgeSync()
    assert sync.command("Opportunity OS weekly export") == [
        "/bin/bash",
        str(LIVE_SYNC_SCRIPT),
        "Opportunity OS weekly export",
    ]


def test_sync_defaults_to_dry_run_and_apply_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def runner(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    sync = KnowledgeSync(runner=runner, environ={"PATH": "/usr/bin", "SECRET": "x"})
    monkeypatch.setattr(sync, "_validate_script", lambda: None)
    assert sync.run("safe commit").applied is False
    assert calls == []
    assert sync.run("safe commit", apply=True).applied is True
    assert calls[0][0] == ["/bin/bash", str(LIVE_SYNC_SCRIPT), "safe commit"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["env"] == {"PATH": "/usr/bin"}


@pytest.mark.parametrize("message", ["", "x\nsecond", "x" * 201])
def test_sync_rejects_unsafe_commit_messages(message: str) -> None:
    with pytest.raises(ValueError):
        KnowledgeSync().command(message)


def test_repository_does_not_contain_a_second_sync_script() -> None:
    project = Path(__file__).parents[2]
    assert list(project.rglob("sync_kb.sh")) == []
