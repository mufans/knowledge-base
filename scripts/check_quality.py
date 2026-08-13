#!/usr/bin/env python3
"""Evidence-oriented Wiki quality and link gate.

Legacy self-evaluation tables are intentionally ignored. Compiler-authored
pages are held to page-type structure and claim-level citation coverage;
all Wiki pages are held to zero broken local links.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
PAGE_TYPES = {
    "concepts": ("原理", "适用条件", "限制", "实现机制"),
    "entities": ("真实能力", "架构", "成熟度", "适用场景"),
    "sources": ("来源结论", "方法", "数据", "局限"),
    "syntheses": ("多来源共同点", "冲突", "趋势判断", "行动建议"),
}
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
FACT_LINE = re.compile(r"^\s*-\s+\*\*Fact\*\*：", re.MULTILINE)
NUMERIC_OR_API = re.compile(
    r"(?:\b(?:v?\d+(?:\.\d+){0,3})\b|%|\b(?:ms|s|MB|GB|tokens?|QPS|FPS)\b|\bAPI\b)",
    re.IGNORECASE,
)
PURPOSE_TERMS = (
    "agent", "llm", "rag", "mcp", "android", "mobile", "swift", "harmony",
    "移动", "鸿蒙", "端侧", "vibe coding", "代码生成", "知识",
)


@dataclass(frozen=True, slots=True)
class Issue:
    severity: str
    path: str
    code: str
    detail: str


def markdown_without_code(text: str) -> str:
    lines: list[str] = []
    fenced = False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return "\n".join(lines)


def _local_links(path: Path, text: str) -> list[tuple[str, Path | None]]:
    result: list[tuple[str, Path | None]] = []
    for _, raw_target in LINK.findall(markdown_without_code(text)):
        target = unquote(raw_target.strip())
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto"} or target.startswith("#"):
            continue
        relative = target.split("#", 1)[0]
        if not relative:
            continue
        if relative.startswith(("/", "~")):
            result.append((raw_target, None))
            continue
        resolved = (path.parent / relative).resolve()
        result.append((raw_target, resolved))
    return result


def _index_targets(index: Path) -> set[str]:
    if not index.is_file():
        return set()
    return {
        target.split("#", 1)[0]
        for _, target in LINK.findall(index.read_text(encoding="utf-8", errors="replace"))
        if target.endswith(".md")
    }


def check_repository(root: Path = ROOT) -> dict[str, object]:
    wiki = root / "wiki"
    pages = sorted(
        path
        for path in wiki.rglob("*.md")
        if path.name != "index.md"
    )
    issues: list[Issue] = []
    fact_total = fact_cited = numeric_total = numeric_cited = 0
    compiler_pages = legacy_pages = 0
    headings: dict[str, str] = {}

    for path in pages:
        relative = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="replace")
        visible = markdown_without_code(text)
        compiler_page = "> compiler: schema v1" in text
        if compiler_page:
            compiler_pages += 1
        else:
            legacy_pages += 1
        category = path.parent.name

        title_match = re.search(r"^#\s+(.+)$", visible, re.MULTILINE)
        if not title_match:
            issues.append(Issue("error", relative, "missing_title", "缺少一级标题"))
        else:
            normalized = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", title_match.group(1).casefold())
            if normalized in headings:
                issues.append(
                    Issue("error", relative, "duplicate_title", f"与 {headings[normalized]} 标题重复")
                )
            else:
                headings[normalized] = relative

        if compiler_page:
            required = PAGE_TYPES.get(category, ())
            for section in required:
                match = re.search(
                    rf"^##\s+{re.escape(section)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
                    text,
                    re.MULTILINE | re.DOTALL,
                )
                if match is None or not match.group("body").strip():
                    issues.append(
                        Issue("error", relative, "required_section_missing", section)
                    )
            if not any(term in text.casefold() for term in PURPOSE_TERMS):
                issues.append(Issue("error", relative, "purpose_mismatch", "与 purpose.md 不匹配"))
            if "## 信息增量" not in text:
                issues.append(Issue("error", relative, "novelty_missing", "缺少信息增量"))
            if "## 证据化声明" not in text:
                issues.append(Issue("error", relative, "claims_missing", "缺少证据化声明"))

        for target, resolved in _local_links(path, text):
            if (
                resolved is None
                or not resolved.is_relative_to(root.resolve())
                or not resolved.exists()
                or resolved.is_dir()
            ):
                issues.append(Issue("error", relative, "broken_local_link", target))

        if "[[" in visible or "]]" in visible:
            issues.append(Issue("error", relative, "obsidian_link", "禁止 [[]] 链接"))

        if compiler_page:
            for line in visible.splitlines():
                if not line.lstrip().startswith("- **"):
                    continue
                if line.lstrip().startswith("- **Fact**："):
                    fact_total += 1
                    if re.search(r"\[[^\]]+\]\(https?://[^)]+\)", line):
                        fact_cited += 1
                    else:
                        issues.append(Issue("error", relative, "uncited_fact", line[:120]))
                if NUMERIC_OR_API.search(line):
                    numeric_total += 1
                    if re.search(r"\[[^\]]+\]\(https?://[^)]+\)", line):
                        numeric_cited += 1
                    else:
                        issues.append(Issue("error", relative, "uncited_numeric_claim", line[:120]))

    for category in PAGE_TYPES:
        directory = wiki / category
        actual = {
            path.name
            for path in directory.glob("*.md")
            if path.name != "index.md"
        }
        indexed = _index_targets(directory / "index.md")
        missing = sorted(actual - indexed)
        extra = sorted(indexed - actual)
        for name in missing:
            issues.append(
                Issue("error", str((directory / "index.md").relative_to(root)), "index_missing", name)
            )
        for name in extra:
            issues.append(
                Issue("error", str((directory / "index.md").relative_to(root)), "index_stale", name)
            )

    error_count = sum(issue.severity == "error" for issue in issues)
    fact_citation_coverage = fact_cited / fact_total if fact_total else None
    numeric_citation_coverage = numeric_cited / numeric_total if numeric_total else None
    return {
        "ok": error_count == 0,
        "page_count": len(pages),
        "compiler_pages": compiler_pages,
        "legacy_pages": legacy_pages,
        "errors": error_count,
        "warnings": sum(issue.severity == "warning" for issue in issues),
        "issues": [asdict(issue) for issue in issues],
        "metrics": {
            "fact_citation_coverage": fact_citation_coverage,
            "numeric_citation_coverage": numeric_citation_coverage,
            "fact_coverage_status": "needs_migration" if fact_total == 0 else "covered",
            "fact_claims": fact_total,
            "numeric_claims": numeric_total,
            "broken_links": sum(issue.code == "broken_local_link" for issue in issues),
            "duplicate_titles": sum(issue.code == "duplicate_title" for issue in issues),
            "synthesis_ratio": (
                sum(path.parent.name == "syntheses" for path in pages) / len(pages)
                if pages
                else 0
            ),
        },
        "issue_counts": dict(Counter(issue.code for issue in issues)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check_repository()
    if args.output:
        destination = args.output.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for issue in report["issues"]:
            print(
                f"{issue['severity'].upper()} {issue['path']} "
                f"[{issue['code']}] {issue['detail']}"
            )
        print(
            f"pages={report['page_count']} errors={report['errors']} "
            f"broken_links={report['metrics']['broken_links']} "
            f"synthesis={report['metrics']['synthesis_ratio']:.1%}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
