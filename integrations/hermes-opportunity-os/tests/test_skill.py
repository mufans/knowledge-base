import re
from pathlib import Path


SKILL = Path(__file__).parents[1] / "skills" / "opportunity-discovery" / "SKILL.md"
REFERENCES = SKILL.parent / "references"
PROFILE_CONFIG = Path(__file__).parents[1] / "profile" / "config.yaml"


def test_skill_has_valid_compact_frontmatter_and_required_sections() -> None:
    text = SKILL.read_text(encoding="utf-8")
    description = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)

    assert text.startswith("---\n")
    assert "name: opportunity-discovery" in text
    assert description is not None and len(description.group(1).strip()) <= 60
    for section in ("## When to Use", "## Procedure", "## Safety Boundaries", "## Verification"):
        assert section in text


def test_skill_encodes_anti_cocoon_and_stability_contracts() -> None:
    text = SKILL.read_text(encoding="utf-8")

    for required in (
        "list_signals", "Fact", "Inference", "Hypothesis", "反对证据", "40/40/20",
        "意外发现", "known_latest", "recommended_stable", "1–2 周", "禁止对外",
    ):
        assert required in text


def test_evidence_contract_names_exact_source_tier_values() -> None:
    contracts = (REFERENCES / "data-contracts.md").read_text(encoding="utf-8")
    policy = (REFERENCES / "source-policy.md").read_text(encoding="utf-8")

    for value in ("official", "primary", "secondary", "community"):
        assert f"`{value}`" in contracts
    assert "Fact 只能使用 `official` 或 `primary`" in policy
    assert "不得使用 `A`、`B`、`C`" in policy
    assert "`kind` 只能是 `fact`、`inference`、`hypothesis`" in contracts
    assert "`stance` 只能是 `support` 或 `oppose`" in contracts


def test_profile_template_pins_current_hermes_config_schema() -> None:
    text = PROFILE_CONFIG.read_text(encoding="utf-8")

    assert text.startswith("_config_version: 33\n")


def test_profile_template_has_safe_unattended_learning_defaults() -> None:
    text = PROFILE_CONFIG.read_text(encoding="utf-8")

    for required in (
        "memory_enabled: true",
        "user_profile_enabled: true",
        "write_approval: true",
        "nudge_interval: 0",
        "guard_agent_created: true",
        "creation_nudge_interval: 0",
        'profile_build: "off"',
    ):
        assert required in text


def test_operating_rhythm_resists_cocoon_self_mutation_and_external_action() -> None:
    text = (REFERENCES / "operating-rhythm.md").read_text(encoding="utf-8")

    for required in (
        "广域输入", "不少于 80%", "定向补充", "不超过 20%", "反对证据", "意外发现",
        "不得修改 Memory 或 Skill", "改进建议草案", "不得执行任何外部行动",
    ):
        assert required in text
