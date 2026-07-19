"""AGENTS-compliant public report export and private OpenClaw bridge."""

from __future__ import annotations

import json
import math
import os
import re
import socket
import stat
import tempfile
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

from opportunity_os.automation.secure_runtime import exclusive_arbitration
from opportunity_os.errors import BoundaryError, ValidationError
from opportunity_os.sanitizer import contains_secret


BRIDGE_NAMES = {
    "openclaw-handoff.json",
    "source-feedback.json",
    "experiment-evidence-request.json",
}
BRIDGE_PAYLOAD_SCHEMAS: dict[str, tuple[str, frozenset[str], str | None, str | None]] = {
    "openclaw-handoff.json": (
        "add_handoff_refs",
        frozenset({"operation", "entity_ids"}),
        "entity_ids",
        "entity",
    ),
    "source-feedback.json": (
        "add_targeted_searches",
        frozenset({"operation"}),
        None,
        None,
    ),
    "experiment-evidence-request.json": (
        "add_evidence_queries",
        frozenset({"operation", "experiment_ids"}),
        "experiment_ids",
        "experiment",
    ),
}
REQUIRED_SECTIONS = ("核心概念", "设计原理", "关键实现", "关联分析", "可执行建议")
SCORE_DIMENSIONS = ("技术深度", "实用价值", "时效性", "领域匹配", "综合")
SELF_DIMENSIONS = ("摘要质量", "技术深度", "相关性", "原创性", "格式规范")
SELF_WEIGHTS = {"摘要质量": 0.25, "技术深度": 0.25, "相关性": 0.20, "原创性": 0.15, "格式规范": 0.15}
TAG_PATTERN = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]*$")
CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")
PRIVATE_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|~/(?:\.hermes|\.config)|profile://|\\Users\\)", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class KnowledgeExporter:
    def __init__(
        self,
        knowledge_root: str | Path,
        *,
        private_home: str | Path,
        now: Callable[[], datetime] | None = None,
        lock_stale_after_seconds: float = 3900,
        lock_wait_seconds: float = 5,
    ) -> None:
        self.knowledge_root = Path(knowledge_root).expanduser().resolve()
        private_path = Path(private_home).expanduser()
        if not private_path.is_absolute():
            raise BoundaryError("private bridge 必须使用绝对路径")
        if ".." in private_path.parts:
            raise BoundaryError("private bridge 路径不得包含父目录跳转")
        self.private_home = private_path
        self._reject_symlink_components(self.private_home)
        resolved_private = self.private_home.resolve(strict=False)
        if resolved_private == self.knowledge_root or resolved_private.is_relative_to(self.knowledge_root):
            raise BoundaryError("private bridge 必须位于知识库之外")
        if lock_stale_after_seconds <= 0 or lock_wait_seconds <= 0:
            raise ValidationError("export lock timeout 必须大于零")
        self.lock_stale_after_seconds = lock_stale_after_seconds
        self.lock_wait_seconds = lock_wait_seconds
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _reject_symlink_components(path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise BoundaryError(f"拒绝私人目录符号链接: {current.name}")

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
        return any(
            (isinstance(key, str) and PRIVATE_PATH_PATTERN.search(key))
            or (isinstance(item, str) and PRIVATE_PATH_PATTERN.search(item))
            for key, item in cls._nested_items(value)
        )

    @classmethod
    def _validate_json_domain(cls, value: object, *, depth: int = 0) -> None:
        if depth > 16:
            raise ValidationError("bridge JSON 嵌套过深")
        if value is None or isinstance(value, (bool, str)):
            if isinstance(value, str) and len(value) > 16_384:
                raise ValidationError("bridge 字符串过长")
            return
        if isinstance(value, int) and not isinstance(value, bool):
            if abs(value) > 1_000_000_000_000_000:
                raise ValidationError("bridge 整数超出允许范围")
            return
        if isinstance(value, float):
            if not math.isfinite(value) or abs(value) > 1_000_000_000_000:
                raise ValidationError("bridge 浮点数必须有限且有界")
            return
        if isinstance(value, Mapping):
            if len(value) > 256:
                raise ValidationError("bridge 对象字段过多")
            for key, item in value.items():
                if not isinstance(key, str) or not key or len(key) > 128:
                    raise ValidationError("bridge 对象 key 必须是有界非空字符串")
                cls._validate_json_domain(item, depth=depth + 1)
            return
        if isinstance(value, list):
            if len(value) > 1024:
                raise ValidationError("bridge 列表过长")
            for item in value:
                cls._validate_json_domain(item, depth=depth + 1)
            return
        raise ValidationError("bridge 仅允许 JSON domain 值")

    @classmethod
    def _normalize_source_collection(
        cls, value: object, *, label: str
    ) -> tuple[list[str], set[str]]:
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"{label} 必须是受支持的非字符串数组")
        items = list(value)
        cls._validate_json_domain(items)
        cleaned: list[str] = []
        normalized: set[str] = set()
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise ValidationError(f"{label} 只能包含非空字符串")
            stripped = item.strip()
            key = unicodedata.normalize("NFKC", stripped).casefold()
            if key in normalized:
                raise ValidationError(f"{label} 不得包含规范化重复项")
            normalized.add(key)
            cleaned.append(stripped)
        return cleaned, normalized

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
        self._validate_json_domain(report)
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
        if score_values["综合"] < 7.0:
            raise ValidationError("页面综合评分低于 7.0")

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

    def _open_private_home(self) -> int:
        current_fd = os.open(self.private_home.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in self.private_home.parts[1:]:
                try:
                    next_fd = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=current_fd,
                    )
                except FileNotFoundError:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    try:
                        next_fd = os.open(
                            part,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current_fd,
                        )
                    except OSError as error:
                        raise BoundaryError("无法安全创建 private home") from error
                except OSError as error:
                    raise BoundaryError("private home 路径包含不安全组件") from error
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except Exception:
            os.close(current_fd)
            raise

    def _open_private_subdir(self, name: str) -> int:
        home_fd = self._open_private_home()
        try:
            try:
                os.mkdir(name, mode=0o700, dir_fd=home_fd)
            except FileExistsError:
                pass
            try:
                return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
            except OSError as error:
                raise BoundaryError(f"拒绝不安全的 private/{name} 目录") from error
        finally:
            os.close(home_fd)

    @staticmethod
    def _read_json_at(directory_fd: int, name: str) -> dict[str, object]:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
                payload = json.load(handle)
        finally:
            os.close(descriptor)
        if not isinstance(payload, dict):
            raise ValidationError("private JSON 顶层必须是 object")
        return payload

    @staticmethod
    def _write_json_at(directory_fd: int, name: str, payload: Mapping[str, object], *, mode: int = 0o600) -> None:
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        temporary = f".{name}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=directory_fd,
        )
        try:
            encoded = rendered.encode("utf-8")
            written = 0
            while written < len(encoded):
                written += os.write(descriptor, encoded[written:])
            os.fsync(descriptor)
            os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)
        try:
            os.rename(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass

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

    @staticmethod
    def _pid_alive(pid: object) -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _export_lock_is_stale(self, locks_fd: int) -> bool:
        try:
            lock_fd = os.open(
                "kb-export.lock",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=locks_fd,
            )
        except FileNotFoundError:
            return False
        except OSError as error:
            raise BoundaryError("拒绝不安全的 export lock") from error
        try:
            try:
                owner = self._read_json_at(lock_fd, "owner.json")
                started = datetime.fromisoformat(str(owner["started_at"]))
                if started.tzinfo is None:
                    return False
                age = (self.now().astimezone(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()
                owner_dead = owner.get("host") == socket.gethostname() and not self._pid_alive(owner.get("pid"))
                return age > self.lock_stale_after_seconds and owner_dead
            except FileNotFoundError:
                lock_stat = os.stat("kb-export.lock", dir_fd=locks_fd, follow_symlinks=False)
                return self.now().timestamp() - lock_stat.st_mtime > self.lock_stale_after_seconds
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                return False
        finally:
            os.close(lock_fd)

    @staticmethod
    def _cleanup_stale_lock(locks_fd: int, stale_name: str) -> None:
        stale_fd = os.open(stale_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=locks_fd)
        try:
            try:
                os.unlink("owner.json", dir_fd=stale_fd)
            except FileNotFoundError:
                pass
        finally:
            os.close(stale_fd)
        try:
            os.rmdir(stale_name, dir_fd=locks_fd)
        except OSError:
            pass

    def _acquire_export_lock(self) -> tuple[int, str]:
        locks_fd = self._open_private_subdir("locks")
        deadline = time.monotonic() + self.lock_wait_seconds
        while True:
            acquired = False
            with exclusive_arbitration(locks_fd, ".kb-export-arbitration.lock"):
                try:
                    os.mkdir("kb-export.lock", mode=0o700, dir_fd=locks_fd)
                    acquired = True
                except FileExistsError:
                    if self._export_lock_is_stale(locks_fd):
                        stale_name = f".kb-export.stale.{uuid.uuid4().hex}"
                        os.rename(
                            "kb-export.lock", stale_name, src_dir_fd=locks_fd, dst_dir_fd=locks_fd
                        )
                        self._cleanup_stale_lock(locks_fd, stale_name)
                        os.mkdir("kb-export.lock", mode=0o700, dir_fd=locks_fd)
                        acquired = True
                if acquired:
                    token = uuid.uuid4().hex
                    lock_fd = os.open(
                        "kb-export.lock",
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=locks_fd,
                    )
                    try:
                        self._write_json_at(
                            lock_fd,
                            "owner.json",
                            {
                                "token": token,
                                "pid": os.getpid(),
                                "host": socket.gethostname(),
                                "started_at": self.now().astimezone(timezone.utc).isoformat(),
                            },
                        )
                    finally:
                        os.close(lock_fd)
                    return locks_fd, token
            if time.monotonic() >= deadline:
                os.close(locks_fd)
                raise ValidationError("知识库导出锁超时")
            time.sleep(0.01)

    def _release_export_lock(self, locks_fd: int, token: str) -> None:
        try:
            with exclusive_arbitration(locks_fd, ".kb-export-arbitration.lock"):
                try:
                    lock_fd = os.open(
                        "kb-export.lock",
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=locks_fd,
                    )
                except FileNotFoundError:
                    return
                try:
                    owner = self._read_json_at(lock_fd, "owner.json")
                    if owner.get("token") != token:
                        return
                    os.unlink("owner.json", dir_fd=lock_fd)
                finally:
                    os.close(lock_fd)
                os.rmdir("kb-export.lock", dir_fd=locks_fd)
        finally:
            os.close(locks_fd)

    def export(self, kind: str, report: Mapping[str, object], *, period_key: str | None = None) -> Path:
        filename = self._page_name(kind, period_key)
        content = self.render(report)
        locks_fd, lock_token = self._acquire_export_lock()
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
            self._release_export_lock(locks_fd, lock_token)

    @staticmethod
    def _validate_bridge_name(name: str) -> None:
        if name not in BRIDGE_NAMES:
            raise ValidationError("bridge 文件名不在固定允许列表中")

    @classmethod
    def _validate_bridge_payload(cls, name: str, payload: object) -> dict[str, object]:
        if not isinstance(payload, Mapping):
            raise ValidationError("bridge payload 必须是 object")
        cls._validate_json_domain(payload)
        operation, exact_keys, id_field, id_prefix = BRIDGE_PAYLOAD_SCHEMAS[name]
        if set(payload) != exact_keys:
            raise ValidationError("bridge payload 字段不符合固定 schema")
        if payload["operation"] != operation:
            raise ValidationError("bridge operation 不在该文件的固定允许值中")

        validated: dict[str, object] = {"operation": operation}
        if id_field is not None and id_prefix is not None:
            identifiers = payload[id_field]
            if not isinstance(identifiers, list) or not identifiers:
                raise ValidationError(f"{id_field} 必须是非空 JSON array")
            prefix = f"{id_prefix}:"
            if any(
                not isinstance(item, str)
                or not item.startswith(prefix)
                or not UUID_PATTERN.fullmatch(item[len(prefix):])
                for item in identifiers
            ):
                raise ValidationError(f"{id_field} 只能包含 {id_prefix}:<lowercase UUID>")
            normalized = [unicodedata.normalize("NFKC", item).casefold() for item in identifiers]
            if len(set(normalized)) != len(normalized):
                raise ValidationError(f"{id_field} 不得包含重复项")
            validated[id_field] = list(identifiers)
        return validated

    def write_bridge(
        self,
        name: str,
        payload: Mapping[str, object],
        *,
        broad_sources: Sequence[str],
        targeted_searches: Sequence[str],
    ) -> Path:
        self._validate_bridge_name(name)
        broad, broad_keys = self._normalize_source_collection(broad_sources, label="broad_sources")
        targeted, targeted_keys = self._normalize_source_collection(
            targeted_searches, label="targeted_searches"
        )
        if broad_keys & targeted_keys:
            raise ValidationError("broad_sources 与 targeted_searches 不得重叠")
        validated_payload = self._validate_bridge_payload(name, payload)
        if (
            contains_secret(validated_payload)
            or contains_secret([broad, targeted])
            or self._contains_private_path(validated_payload)
            or self._contains_private_path([broad, targeted])
        ):
            raise ValidationError("bridge 不得包含秘密")
        if not broad or any(not isinstance(item, str) or not item.strip() for item in broad):
            raise ValidationError("broad_sources 不能为空")
        if any(not isinstance(item, str) or not item.strip() for item in targeted):
            raise ValidationError("targeted_searches 格式无效")
        if len(targeted) * 5 > len(broad) + len(targeted):
            raise ValidationError("定向搜索占比不得超过 20%")

        created = self.now().astimezone(timezone.utc)
        document = {
            "schema_version": 1,
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(days=14)).isoformat(),
            "broad_sources": broad,
            "targeted_searches": targeted,
            "payload": validated_payload,
            "policy": {"mode": "add_only", "broad_sources_locked": True},
        }
        self._validate_json_domain(document)
        if len(json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")) > 65_536:
            raise ValidationError("bridge JSON 总大小超过 64 KiB")
        bridge_fd = self._open_private_subdir("bridge")
        try:
            self._write_json_at(bridge_fd, name, document)
        finally:
            os.close(bridge_fd)
        return self.private_home / "bridge" / name

    def read_bridge(self, name: str) -> dict[str, object] | None:
        self._validate_bridge_name(name)
        bridge_fd = self._open_private_subdir("bridge")
        try:
            payload = self._read_json_at(bridge_fd, name)
            expires = datetime.fromisoformat(str(payload["expires_at"]))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValidationError("bridge 文件损坏") from error
        finally:
            if "expires" not in locals():
                os.close(bridge_fd)
        try:
            if expires.tzinfo is None:
                raise ValidationError("bridge expires_at 缺少 timezone")
            if self.now().astimezone(timezone.utc) >= expires.astimezone(timezone.utc):
                os.unlink(name, dir_fd=bridge_fd)
                return None
            return payload
        finally:
            os.close(bridge_fd)
