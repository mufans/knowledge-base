#!/usr/bin/env python3
"""Generate read-only discovery metadata for the public Wiki home.

The generator never edits Wiki pages and never ranks by legacy self-scores.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
OUTPUT = ROOT / "docs" / "assets" / "dashboard-data.js"
CATEGORIES = ("concepts", "entities", "sources", "syntheses")
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
AGENT_TERMS = re.compile(r"(?i)\b(agent|llm|rag|mcp|tool.call|multi.agent)\b|智能体|代理")
MOBILE_TERMS = re.compile(r"(?i)\b(android|ios|swiftui|mobile|harmonyos)\b|移动端|端侧|鸿蒙")
OPPOSITION_TERMS = re.compile(r"限制|局限|反例|反方|反对证据|风险|冲突|trade.?off", re.I)
ACTION_TERMS = re.compile(r"行动建议|可执行建议|下一步实验|最小实验")


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    value = yaml.safe_load(text[4:end]) or {}
    return (value if isinstance(value, dict) else {}), text[end + 5 :]


def visible_text(body: str) -> str:
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    body = re.sub(r"<[^>]+>", "", body)
    return body


def title_for(path: Path, metadata: dict[str, object], body: str) -> str:
    if isinstance(metadata.get("title"), str) and metadata["title"].strip():
        return str(metadata["title"]).strip()
    heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return heading.group(1).strip() if heading else path.stem.replace("-", " ")


def tags_for(metadata: dict[str, object], body: str) -> list[str]:
    tags = metadata.get("tags")
    if isinstance(tags, list):
        return [str(item).lstrip("#") for item in tags if str(item).strip()][:8]
    line = re.search(r"^>\s*tags:\s*(.+)$", body, re.MULTILINE | re.IGNORECASE)
    return re.findall(r"#([A-Za-z][A-Za-z0-9_-]*)", line.group(1))[:8] if line else []


def description_for(metadata: dict[str, object], body: str, title: str) -> str:
    description = metadata.get("description")
    if isinstance(description, str) and 8 <= len(description.strip()) <= 180:
        return description.strip()
    cleaned = visible_text(body)
    for paragraph in re.split(r"\n\s*\n", cleaned):
        value = re.sub(r"^(?:#+|>|[-*])\s*", "", paragraph.strip())
        value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
        value = re.sub(r"\s+", " ", value)
        if 20 <= len(value) and not value.startswith(("tags:", "source:", "score:")):
            return value[:177] + ("…" if len(value) > 177 else "")
    return title


def published_date(path: Path, metadata: dict[str, object]) -> str:
    value = metadata.get("date")
    if value:
        return str(value)
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def local_related(path: Path, body: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for label, target in LINK.findall(visible_text(body)):
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("#"):
            continue
        relative = target.split("#", 1)[0]
        if not relative.endswith(".md"):
            continue
        resolved = (path.parent / relative).resolve()
        if not resolved.is_relative_to(WIKI.resolve()) or not resolved.is_file():
            continue
        wiki_relative = resolved.relative_to(ROOT).with_suffix("")
        item = {"title": label.strip(), "url": str(wiki_relative)}
        if item not in result:
            result.append(item)
        if len(result) == 4:
            break
    return result


def evidence_quality(body: str) -> tuple[str, int, bool]:
    external = {
        target for _, target in LINK.findall(visible_text(body))
        if urlsplit(target).scheme in {"http", "https"}
    }
    has_opposition = bool(OPPOSITION_TERMS.search(body))
    if len(external) >= 3 and has_opposition:
        return "high", len(external), has_opposition
    if external:
        return "medium", len(external), has_opposition
    return "low", 0, has_opposition


def article(path: Path, category: str) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata, body = split_frontmatter(text)
    title = title_for(path, metadata, body)
    quality, citations, has_opposition = evidence_quality(body)
    cross_topic = bool(AGENT_TERMS.search(body) and MOBILE_TERMS.search(body))
    actionable = bool(ACTION_TERMS.search(body))
    return {
        "title": title,
        "category": category,
        "tags": tags_for(metadata, body),
        "description": description_for(metadata, body, title),
        "date": published_date(path, metadata),
        "url": str(path.relative_to(ROOT).with_suffix("")),
        "evidence_quality": quality,
        "citation_count": citations,
        "has_opposing_evidence": has_opposition,
        "actionable": actionable,
        "agent_mobile": cross_topic,
        "related": local_related(path, body),
    }


def generate() -> dict[str, object]:
    articles = [
        article(path, category)
        for category in CATEGORIES
        for path in sorted((WIKI / category).glob("*.md"))
        if path.name != "index.md"
    ]
    articles.sort(
        key=lambda item: (
            item["date"],
            item["category"] == "syntheses",
            item["evidence_quality"] == "high",
            item["title"],
        ),
        reverse=True,
    )
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "today": today,
        "articles": articles,
        "counts": {
            category: sum(item["category"] == category for item in articles)
            for category in CATEGORIES
        },
    }


def main() -> int:
    payload = generate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "window.__knowledge_home = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(
        f"generated={len(payload['articles'])} "
        f"syntheses={payload['counts']['syntheses']} wiki_files_modified=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
