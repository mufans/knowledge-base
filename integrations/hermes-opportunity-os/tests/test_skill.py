import re
from pathlib import Path


SKILL = Path(__file__).parents[1] / "skills" / "opportunity-discovery" / "SKILL.md"


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
