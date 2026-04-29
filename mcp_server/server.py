"""Knowledge Base MCP Server — provides search_kb, get_entity, list_recent tools."""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

KB_PATH = os.environ.get(
    "KNOWLEDGE_BASE_PATH",
    "/Users/liujun/Nutstore Files/我的坚果云/knowledge",
)
WIKI_DIR = Path(KB_PATH) / "wiki"
CATEGORIES = ["concepts", "entities", "sources", "syntheses"]

mcp = FastMCP("knowledge-base")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_md_files(category: str | None = None) -> list[Path]:
    """Return all .md files under wiki/ (excluding index.md)."""
    dirs = [WIKI_DIR / c for c in (["category"] if category else CATEGORIES) if (WIKI_DIR / (c or category)).is_dir()]
    if category:
        d = WIKI_DIR / category
        dirs = [d] if d.is_dir() else []
    files: list[Path] = []
    for d in dirs:
        for f in sorted(d.rglob("*.md")):
            if f.stem != "index":
                files.append(f)
    return files


def _parse_frontmatter(text: str) -> dict:
    """Extract metadata from the blockquote header of a wiki page."""
    meta: dict = {}
    # tags: #tag1 #tag2
    m = re.search(r">\s*tags:\s*(.+)", text)
    if m:
        meta["tags"] = re.findall(r"#(\S+)", m.group(1))
    # source: [...](url)
    m = re.search(r">\s*source:\s*\[(.+?)\]\((.+?)\)", text)
    if m:
        meta["source"] = m.group(1)
        meta["source_url"] = m.group(2)
    # score: 综合 X.X/10
    m = re.search(r"综合\s+([\d.]+)/10", text)
    if m:
        meta["score"] = float(m.group(1))
    return meta


def _parse_sections(text: str, max_chars: int = 500) -> list[dict]:
    """Split markdown into sections by ## headings, truncate content."""
    sections = []
    # Skip the first H1 title line(s)
    lines = text.split("\n")
    current_heading = "概述"
    current_lines: list[str] = []
    started = False
    for line in lines:
        if re.match(r"^# ", line) and not started:
            started = True
            continue
        hm = re.match(r"^## (.+)", line)
        if hm:
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append({"heading": current_heading, "content": content[:max_chars]})
            current_heading = hm.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"heading": current_heading, "content": content[:max_chars]})
    return sections


def _parse_related(text: str, current_file: Path) -> list[dict]:
    """Extract [name](path.md) links as related entries."""
    related = []
    seen = set()
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+\.md)\)", text):
        name, path = m.group(1), m.group(2)
        if path.startswith("http"):
            continue
        # Resolve relative path
        resolved = (current_file.parent / path).resolve()
        if resolved.stem == "index":
            continue
        if name not in seen:
            seen.add(name)
            # Compute relative wiki path
            try:
                rel = resolved.relative_to(WIKI_DIR)
            except ValueError:
                continue
            related.append({"name": name, "path": str(rel)})
    return related


def _get_summary(text: str) -> str:
    """Extract a brief summary: first non-empty, non-metadata paragraph."""
    lines = text.split("\n")
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">") or stripped.startswith("#") or stripped == "---":
            continue
        if stripped:
            paragraph.append(stripped)
        elif paragraph:
            break
    result = " ".join(paragraph)[:200]
    return result


def _file_mtime(path: Path) -> str:
    mt = path.stat().st_mtime
    return datetime.fromtimestamp(mt).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_kb(query: str, category: str | None = None, limit: int = 10) -> list[dict]:
    """Full-text search the knowledge base wiki using ripgrep.

    Args:
        query: Search keywords
        category: Optional filter — concepts, entities, sources, or syntheses
        limit: Max results (default 10)
    """
    if category:
        d = WIKI_DIR / category
        search_dirs = [d] if d.is_dir() else []
    else:
        search_dirs = [WIKI_DIR / c for c in CATEGORIES if (WIKI_DIR / c).is_dir()]

    if not search_dirs:
        return []

    # Build rg command
    cmd = [
        "rg", "--no-heading", "-n", "-l", "-i",
        "--glob", "!index.md",
        "-e", query,
    ] + [str(d) for d in search_dirs]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    matched_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
    results: list[dict] = []

    for fpath_str in matched_files[:limit]:
        fpath = Path(fpath_str)
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        meta = _parse_frontmatter(text)

        # Get highlights: lines containing the query
        highlights = []
        for line in text.split("\n"):
            if re.search(re.escape(query), line, re.IGNORECASE):
                stripped = line.strip()
                if stripped.startswith(">") or stripped.startswith("#"):
                    continue
                highlights.append(stripped[:200])
                if len(highlights) >= 3:
                    break

        # Determine category from path
        try:
            rel = fpath.relative_to(WIKI_DIR)
            cat = rel.parts[0] if rel.parts else ""
        except ValueError:
            cat = ""

        results.append({
            "title": fpath.stem,
            "path": str(rel),
            "category": cat,
            "score": meta.get("score"),
            "tags": meta.get("tags", []),
            "summary": _get_summary(text),
            "key_concepts": meta.get("tags", [])[:5],
            "highlights": highlights,
        })

    return results


@mcp.tool()
def get_entity(name: str) -> dict | None:
    """Get details of a single wiki page by name (filename without .md).

    Args:
        name: Page name, e.g. "OpenClaw" or "Self-RAG"
    """
    # Search all wiki subdirs
    for cat_dir in [WIKI_DIR / c for c in CATEGORIES]:
        if not cat_dir.is_dir():
            continue
        for fpath in cat_dir.rglob(f"{name}.md"):
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            meta = _parse_frontmatter(text)
            rel = fpath.relative_to(WIKI_DIR)
            return {
                "title": fpath.stem,
                "path": str(rel),
                "category": rel.parts[0] if rel.parts else "",
                "score": meta.get("score"),
                "tags": meta.get("tags", []),
                "source_url": meta.get("source_url"),
                "sections": _parse_sections(text),
                "related": _parse_related(text, fpath),
            }
    return None


@mcp.tool()
def list_recent(
    category: str | None = None,
    days: int = 7,
    min_score: float = 7.0,
) -> list[dict]:
    """List recently updated wiki pages.

    Args:
        category: Optional filter — concepts, entities, sources, or syntheses
        days: How many days back to look (default 7)
        min_score: Minimum composite score (default 7.0)
    """
    cutoff = datetime.now() - timedelta(days=days)
    results: list[dict] = []

    for fpath in _find_md_files(category):
        mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
        if mtime < cutoff:
            continue
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        meta = _parse_frontmatter(text)
        score = meta.get("score", 0)
        if score < min_score:
            continue

        try:
            rel = fpath.relative_to(WIKI_DIR)
            cat = rel.parts[0] if rel.parts else ""
        except ValueError:
            cat = ""

        results.append({
            "title": fpath.stem,
            "path": str(rel),
            "category": cat,
            "score": score,
            "tags": meta.get("tags", []),
            "summary": _get_summary(text),
            "updated": mtime.strftime("%Y-%m-%d"),
        })

    results.sort(key=lambda x: x["updated"], reverse=True)
    return results


if __name__ == "__main__":
    mcp.run(transport="stdio")
