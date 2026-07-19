from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "opportunity_os"
SKILL = ROOT / "deployment" / "openclaw" / "skills" / "hermes-dashboard" / "SKILL.md"


def _python_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(SOURCE.rglob("*.py"))
    )


def test_native_products_own_transport_sessions_approvals_and_recovery() -> None:
    source = _python_source()
    for duplicate in (
        "DeliveryQueue",
        "RestartBudget",
        "ImCommandRouter",
        "ConfirmationStore",
        "ConversationService",
    ):
        assert duplicate not in source

    for removed in (
        SOURCE / "dashboard" / "conversations.py",
        SOURCE / "dashboard" / "approvals.py",
        SOURCE / "dashboard" / "audit.py",
        SOURCE / "dashboard" / "im.py",
        SOURCE / "dashboard" / "incidents.py",
        SOURCE / "automation" / "monitor.py",
    ):
        assert not removed.exists()


def test_openclaw_cron_adapter_is_strictly_read_only() -> None:
    source = (SOURCE / "dashboard" / "tasks.py").read_text(encoding="utf-8")
    for write_surface in (
        "edit_enabled",
        "edit_schedule",
        "run_now",
        "TaskMutationCoordinator",
        "WRITE_TIMEOUT_SECONDS",
    ):
        assert write_surface not in source
    for command in ('"edit"', '"run"', '"enable"', '"disable"'):
        assert command not in source


def test_healthcheck_has_no_transport_retry_or_restart_implementation() -> None:
    source = (SOURCE / "automation" / "healthcheck.py").read_text(encoding="utf-8")
    for forbidden in (
        "delivery",
        "outbox",
        "receipt",
        "retry",
        "restart",
        "cooldown",
        "threshold",
    ):
        assert forbidden not in source.casefold()


def test_openclaw_skill_delegates_native_controls() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    lowered = skill.casefold()
    assert "owner allowlist" in lowered
    assert "openclaw control ui" in lowered
    assert "hermes" in lowered and "dashboard" in lowered
    assert "native `/restart`" in lowered
    for forbidden in ("nonce", "confirmationstore", "imcommandrouter", "boot-hook"):
        assert forbidden not in lowered
