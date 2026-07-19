"""AGENTS-compliant public report export and private OpenClaw bridge."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

from opportunity_os.errors import BoundaryError, ValidationError
from opportunity_os.sanitizer import contains_secret


BRIDGE_NAMES = {
    "openclaw-handoff.json",
    "source-feedback.json",
    "experiment-evidence-request.json",
}
REQUIRED_SECTIONS = ("核心概念", "设计原理", "关键实现", "关联分析", "可执行建议")
SCORE_DIMENSIONS = ("技术深度", "实用价值", "时效性", "领域匹配", "综合")
SELF_DIMENSIONS = ("摘要质量", "技术深度", "相关性", "原创性", "格式规范")
SELF_WEIGHTS = {"摘要质量": 0.25, "技术深度": 0.25, "相关性": 0.20, "原创性": 0.15, "格式规范": 0.15}
TAG_PATTERN = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]*$")
CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")
PRIVATE_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|~/(?:\.hermes|\.config)|profile://|\\Users\\)", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")


class KnowledgeExporter:
    def __init__(
        self,
        knowledge_root: str | Path,
        *,
        private_home: str | Path,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.knowledge_root = Path(knowledge_root).expanduser().resolve()
        self.private_home = Path(private_home).expanduser().resolve()
        if self.private_home == self.knowledge_root or self.private_home.is_relative_to(self.knowledge_root):
            raise BoundaryError("private bridge 必须位于知识库之外")
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _safe_number(value: object, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{label} 必须为数字")
        number = float(value)
        if not math.isfinite(number) or not 0 <= number <= 10:
            raise ValidationError(f"{label} 必须位于 0 到 10")
        return number

    @staticmethod
    def _nested_items(value: object):
        if isinstance(value, Mapping):
            for key, item in value.items():
                yield key, item
                yield from KnowledgeExporter._nested_items(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from KnowledgeExporter._nested_items(item)
        else:
            yield None, value

    @classmethod
    def _contains_private_path(cls, value: object) -> bool:
        return any(isinstance(item, str) and PRIVATE_PATH_PATTERN.search(item) for _, item in cls._nested_items(value))

    @classmethod
    def _requests_broad_source_removal(cls, value: object) -> bool:
        for key, _ in cls._nested_items(value):
            if key is None:
                continue
            normalized = re.sub(r"[^a-z]", "", str(key).casefold())
            if "source" in normalized and any(action in normalized for action in ("remove", "delete", "drop")):
                return True
        return False

    @staticmethod
    def _validate_public_text(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("公开文本不能为空")
        text = value.strip()
        if contains_secret(text) or PRIVATE_PATH_PATTERN.search(text):
            raise ValidationError("公开文本包含秘密或私人路径")
        if "[[" in text or "]]" in text:
            raise ValidationError("禁止 Obsidian wikilink")
        without_links = MARKDOWN_LINK_PATTERN.sub("", text)
        if re.search(r"https?://", without_links):
            raise ValidationError("URL 必须使用 Markdown 链接")
        for _, target in MARKDOWN_LINK_PATTERN.findall(text):
            if target.startswith(("http://", "https://")):
                parsed = urlsplit(target)
                if parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValidationError("公开 URL 不得包含凭据、query 或 fragment")
            elif not target.endswith(".md") or target.startswith(("/", "~")):
                raise ValidationError("Wiki 链接必须是安全的 .md 相对链接")
        return text

    def render(self, report: Mapping[str, object]) -> str:
        if contains_secret(report) or self._contains_private_path(report):
            raise ValidationError("报告包含敏感字段、秘密或私人路径")
        title = self._validate_public_text(report.get("title"))
        if not CHINESE_PATTERN.search(title):
            raise ValidationError("标题必须包含中文")

        tags = report.get("tags")
        if not isinstance(tags, list) or not 2 <= len(tags) <= 5 or any(
            not isinstance(tag, str) or not TAG_PATTERN.fullmatch(tag) for tag in tags
        ):
            raise ValidationError("页面必须包含 2–5 个英文技术标签")

        source_links = report.get("source_links")
        if not isinstance(source_links, list) or not source_links:
            raise ValidationError("页面必须包含来源链接")
        rendered_sources = []
        for source in source_links:
            if not isinstance(source, Mapping):
                raise ValidationError("来源格式无效")
            name = self._validate_public_text(source.get("name"))
            url = source.get("url")
            if not isinstance(url, str):
                raise ValidationError("来源 URL 无效")
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError("来源 URL 仅允许 HTTP(S)")
            if parsed.username or parsed.password or parsed.query or parsed.fragment or contains_secret(url):
                raise ValidationError("来源 URL 包含私人信息")
            rendered_sources.append(f"[{name}]({url})")

        scores = report.get("score")
        if not isinstance(scores, Mapping) or set(scores) != set(SCORE_DIMENSIONS):
            raise ValidationError("score 维度不完整")
        score_values = {name: self._safe_number(scores[name], name) for name in SCORE_DIMENSIONS}

        sections = report.get("sections")
        if not isinstance(sections, Mapping) or set(sections) != set(REQUIRED_SECTIONS):
            raise ValidationError("页面章节不完整")
        rendered_sections = {name: self._validate_public_text(sections[name]) for name in REQUIRED_SECTIONS}
        if not all(CHINESE_PATTERN.search(value) for value in rendered_sections.values()):
            raise ValidationError("每个章节必须包含中文分析")

        self_evaluation = report.get("self_evaluation")
        if not isinstance(self_evaluation, Mapping) or set(self_evaluation) != set(SELF_DIMENSIONS):
            raise ValidationError("自评维度不完整")
        self_values = {name: self._safe_number(self_evaluation[name], name) for name in SELF_DIMENSIONS}
        weighted = sum(self_values[name] * SELF_WEIGHTS[name] for name in SELF_DIMENSIONS)
        if weighted < 7.0:
            raise ValidationError("自评加权总分低于 7.0")

        lines = [
            f"# {title}",
            "",
            f"> tags: {' '.join(tags)}",
            f"> source: {'、'.join(rendered_sources)}",
            (
                f"> score: 技术深度{score_values['技术深度']:g}/10 | "
                f"实用价值{score_values['实用价值']:g}/10 | 时效性{score_values['时效性']:g}/10 | "
                f"领域匹配{score_values['领域匹配']:g}/10 | 综合 {score_values['综合']:g}/10"
            ),
            "",
        ]
        for heading in REQUIRED_SECTIONS:
            lines.extend((f"## {heading}", "", rendered_sections[heading], ""))
        lines.extend((
            "## 自评",
            "",
            "| 维度 | 分数 | 权重 | 加权 |",
            "|------|------|------|------|",
        ))
        for name in SELF_DIMENSIONS:
            lines.append(
                f"| {name} | {self_values[name]:g} | {SELF_WEIGHTS[name]:.2f} | "
                f"{self_values[name] * SELF_WEIGHTS[name]:.2f} |"
            )
        lines.extend((
            f"| **加权总分** | | | **{weighted:.2f}** |",
            "",
            "> 评分标准：摘要质量（具体技术细节）| 技术深度（有实质性的设计/实现分析）| "
            "相关性（purpose匹配）| 原创性（独立见解）| 格式规范（标签/链接/评分）",
            "",
        ))
        rendered = "\n".join(lines)
        self._validate_public_text(rendered)
        return rendered

    @staticmethod
    def _atomic_text(path: Path, content: str, *, mode: int = 0o644) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
            os.chmod(path, mode)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _reject_symlink(path: Path) -> None:
        if path.is_symlink():
            raise BoundaryError(f"拒绝符号链接路径: {path.name}")

    def _validate_repository_contract(self) -> None:
        agents = self.knowledge_root / "AGENTS.md"
        purpose = self.knowledge_root / "purpose.md"
        raw = self.knowledge_root / "raw"
        for path in (agents, purpose, raw):
            self._reject_symlink(path)
        if not agents.is_file() or not purpose.is_file() or not raw.is_dir():
            raise ValidationError("知识库规则、purpose 或 raw 边界缺失")
        agents_text = agents.read_text(encoding="utf-8")
        required_agents = (
            "raw/",
            "wiki/syntheses",
            "log.md",
            "## 核心概念",
            "## 设计原理",
            "## 关键实现",
            "## 关联分析",
            "## 可执行建议",
            "## 自评",
        )
        if any(marker not in agents_text for marker in required_agents):
            raise ValidationError("AGENTS.md 不包含受支持的 Wiki 模板契约")
        purpose_text = purpose.read_text(encoding="utf-8")
        if "## 目标" not in purpose_text or "## 研究范围" not in purpose_text:
            raise ValidationError("purpose.md 缺少目标或研究范围")

    def _page_name(self, kind: str, period_key: str | None) -> str:
        if kind == "dashboard" and period_key is None:
            return "个人机会发现仪表盘.md"
        if kind == "freshness" and period_key is None:
            return "技术新鲜度观察.md"
        if kind == "weekly" and isinstance(period_key, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", period_key):
            try:
                datetime.strptime(period_key, "%Y-%m-%d")
            except ValueError as error:
                raise ValidationError("weekly period_key 不是有效日期") from error
            return f"个人机会发现周报-{period_key}.md"
        if kind == "experiment" and isinstance(period_key, str) and re.fullmatch(r"\d{4}-W\d{2}", period_key):
            week = int(period_key[-2:])
            if not 1 <= week <= 53:
                raise ValidationError("experiment period_key 周数无效")
            return f"方向实验复盘-{period_key}.md"
        raise ValidationError("报告类型或 period_key 不在固定允许列表中")

    def _acquire_export_lock(self) -> Path:
        locks = self.private_home / "locks"
        locks.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = locks / "kb-export.lock"
        deadline = time.monotonic() + 5
        while True:
            try:
                lock.mkdir(mode=0o700)
                return lock
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ValidationError("知识库导出锁超时")
                time.sleep(0.01)

    def export(self, kind: str, report: Mapping[str, object], *, period_key: str | None = None) -> Path:
        filename = self._page_name(kind, period_key)
        content = self.render(report)
        lock = self._acquire_export_lock()
        try:
            self._validate_repository_contract()
            syntheses = self.knowledge_root / "wiki" / "syntheses"
            self._reject_symlink(self.knowledge_root / "wiki")
            self._reject_symlink(syntheses)
            if not syntheses.is_dir() or not syntheses.resolve().is_relative_to(self.knowledge_root):
                raise BoundaryError("wiki/syntheses 边界无效")
            page = syntheses / filename
            index = syntheses / "index.md"
            log = self.knowledge_root / "log.md"
            for target in (page, index, log):
                self._reject_symlink(target)
            if not index.is_file() or not log.is_file():
                raise ValidationError("知识库 index.md 或 log.md 不存在")

            self._atomic_text(page, content)
            title = str(report["title"])
            entry = f"- [{title}]({filename})"
            index_text = index.read_text(encoding="utf-8")
            existing_targets = {target for _, target in MARKDOWN_LINK_PATTERN.findall(index_text)}
            if filename not in existing_targets:
                if index_text and not index_text.endswith("\n"):
                    index_text += "\n"
                index_text += f"{entry}\n"
                self._atomic_text(index, index_text)

            at = self.now().astimezone(timezone.utc).date().isoformat()
            log_line = f"{at} | export | {page.relative_to(self.knowledge_root)} | 写入脱敏公开报告并更新综合索引\n"
            descriptor = os.open(log, os.O_WRONLY | os.O_APPEND)
            try:
                os.write(descriptor, log_line.encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return page
        finally:
            try:
                lock.rmdir()
            except OSError:
                pass

    @staticmethod
    def _validate_bridge_name(name: str) -> None:
        if name not in BRIDGE_NAMES:
            raise ValidationError("bridge 文件名不在固定允许列表中")

    def write_bridge(
        self,
        name: str,
        payload: Mapping[str, object],
        *,
        broad_sources: Sequence[str],
        targeted_searches: Sequence[str],
    ) -> Path:
        self._validate_bridge_name(name)
        if contains_secret(payload) or contains_secret([list(broad_sources), list(targeted_searches)]):
            raise ValidationError("bridge 不得包含秘密")
        if self._requests_broad_source_removal(payload):
            raise ValidationError("bridge 不得移除广域来源")
        if not broad_sources or any(not isinstance(item, str) or not item.strip() for item in broad_sources):
            raise ValidationError("broad_sources 不能为空")
        if any(not isinstance(item, str) or not item.strip() for item in targeted_searches):
            raise ValidationError("targeted_searches 格式无效")
        if len(targeted_searches) > len(broad_sources) / 4:
            raise ValidationError("定向搜索占比不得超过 20%")

        bridge = self.private_home / "bridge"
        bridge.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._reject_symlink(bridge)
        path = bridge / name
        self._reject_symlink(path)
        created = self.now().astimezone(timezone.utc)
        document = {
            "schema_version": 1,
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(days=14)).isoformat(),
            "broad_sources": list(broad_sources),
            "targeted_searches": list(targeted_searches),
            "payload": dict(payload),
        }
        self._atomic_text(path, json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n", mode=0o600)
        return path

    def read_bridge(self, name: str) -> dict[str, object] | None:
        self._validate_bridge_name(name)
        path = self.private_home / "bridge" / name
        self._reject_symlink(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires = datetime.fromisoformat(str(payload["expires_at"]))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValidationError("bridge 文件损坏") from error
        if expires.tzinfo is None or self.now().astimezone(timezone.utc) >= expires.astimezone(timezone.utc):
            return None
        return payload
