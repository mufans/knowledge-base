from pathlib import Path


SKILL = Path(__file__).parents[2] / "deployment/openclaw/skills/hermes-dashboard/SKILL.md"


def test_skill_is_thin_and_delegates_native_controls() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "native owner allowlist" in text
    assert "group access is disabled" in text
    assert "opportunity-os domain query" in text
    assert "opportunity-os domain propose" in text
    assert "OpenClaw native `/restart`" in text
    assert "OpenClaw Control UI" in text
    assert "Hermes native dashboard" in text
    assert "shell=False" in text
