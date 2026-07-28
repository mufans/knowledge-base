#!/usr/bin/env python3
"""Build a deterministic, score-blind 16-page calibration pack."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
OUTPUT = ROOT / "integrations" / "hermes-opportunity-os" / "calibration"
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
CATEGORIES = ("concepts", "entities", "sources", "syntheses")


def title(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def main() -> int:
    selected: list[Path] = []
    for category in CATEGORIES:
        pages = [path for path in (WIKI / category).glob("*.md") if path.name != "index.md"]
        pages.sort(key=lambda path: hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest())
        selected.extend(pages[:4] if len(pages) >= 4 else pages)
    # Syntheses currently has only three pages; fill the final slot from all remaining pages.
    if len(selected) < 16:
        remaining = [
            path for category in CATEGORIES
            for path in (WIKI / category).glob("*.md")
            if path.name != "index.md" and path not in selected
        ]
        remaining.sort(key=lambda path: hashlib.sha256(path.read_bytes()).hexdigest())
        selected.extend(remaining[: 16 - len(selected)])

    blind = {
        "schema_version": 1,
        "instructions": "独立阅读页面，不查看历史自评分或 calibration key；每项使用 1-5 分并写一句证据。",
        "criteria": [
            "信息增量是否明确",
            "重要事实是否可追溯",
            "Fact/Inference/Hypothesis 是否可区分",
            "是否包含限制、反例或反方证据",
            "是否带来可执行的学习、验证或项目行动",
            "页面结构是否符合内容类型且无模板填充",
        ],
        "samples": [],
    }
    key: dict[str, object] = {"schema_version": 1, "samples": []}
    for index, path in enumerate(selected, 1):
        text = path.read_text(encoding="utf-8", errors="replace")
        sample_id = f"blind-{index:02d}"
        relative = str(path.relative_to(ROOT))
        external = {
            target for _, target in LINK.findall(text)
            if urlsplit(target).scheme in {"http", "https"}
        }
        blind["samples"].append({
            "sample_id": sample_id,
            "title": title(text, path.stem),
            "path": relative,
            "reviewer_scores": {},
            "reviewer_evidence": "",
            "decision": "",
        })
        key["samples"].append({
            "sample_id": sample_id,
            "page_type": path.parent.name.removesuffix("s"),
            "citation_count": len(external),
            "has_opposing_evidence": bool(
                re.search(r"限制|局限|反例|反方|反对证据|风险|冲突|trade.?off", text, re.I)
            ),
            "legacy_self_score_ignored": True,
        })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "blind-review-sample.json").write_text(
        json.dumps(blind, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT / "blind-review-key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"samples={len(blind['samples'])} reviewer_decisions=0 key_separated=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
