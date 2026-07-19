import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from opportunity_os.errors import BoundaryError, ValidationError


@dataclass(frozen=True, slots=True)
class Signal:
    id: str
    title: str
    relative_path: str
    collected_at: str
    category: str
    excerpt: str
    source_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SignalReader:
    def __init__(self, knowledge_root: str | Path) -> None:
        self.knowledge_root = Path(knowledge_root).expanduser().resolve()
        self.inbox = (self.knowledge_root / "raw" / "inbox").resolve()
        if not self.inbox.is_dir():
            raise BoundaryError("知识库必须包含可读的 raw/inbox")

    @staticmethod
    def _date_from_name(path: Path) -> date | None:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _category(path: Path) -> str:
        name = path.name.lower()
        rules = (
            ("跨领域", "cross_domain"),
            ("技术", "technology"),
            ("论文", "research"),
            ("github", "github"),
            ("社交", "social"),
            ("新闻", "news"),
        )
        return next((category for marker, category in rules if marker in name), "other")

    def _resolve_signal_path(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or candidate.parts[:2] != ("raw", "inbox"):
            raise BoundaryError("只能读取知识库 raw/inbox 下的 Markdown 文件")
        resolved = (self.knowledge_root / candidate).resolve()
        if not resolved.is_relative_to(self.inbox) or resolved.suffix.lower() != ".md" or not resolved.is_file():
            raise BoundaryError("只能读取知识库 raw/inbox 下的 Markdown 文件")
        return resolved

    def get_signal(self, relative_path: str) -> dict[str, str]:
        path = self._resolve_signal_path(relative_path)
        return {
            "relative_path": str(path.relative_to(self.knowledge_root)),
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }

    def list_signals(
        self,
        *,
        days: int = 14,
        limit: int = 80,
        offset: int = 0,
        query: str | None = None,
        today: str | None = None,
    ) -> list[Signal]:
        if days < 1 or limit < 1 or offset < 0:
            raise ValidationError("days/limit 必须为正数，offset 不能为负数")
        current = date.fromisoformat(today) if today else date.today()
        cutoff = current - timedelta(days=days - 1)
        signals: list[Signal] = []
        for path in sorted(self.inbox.glob("*.md")):
            collected = self._date_from_name(path)
            if collected is None or collected < cutoff or collected > current:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            sections = re.split(r"(?m)^##\s+", text)
            for section in sections[1:]:
                lines = section.splitlines()
                title = lines[0].strip()
                content = "\n".join(lines[1:]).strip()
                if not title or (query and query.casefold() not in f"{title}\n{content}".casefold()):
                    continue
                rel = str(path.relative_to(self.knowledge_root))
                digest = hashlib.sha256(f"{rel}\0{title}".encode()).hexdigest()[:16]
                signals.append(
                    Signal(
                        id=f"signal-{digest}",
                        title=title,
                        relative_path=rel,
                        collected_at=collected.isoformat(),
                        category=self._category(path),
                        excerpt=re.sub(r"\s+", " ", content)[:800],
                        source_urls=re.findall(r"\[[^\]]+\]\((https://[^)]+)\)", content),
                    )
                )
        signals.sort(key=lambda item: (item.collected_at, item.relative_path, item.title), reverse=True)
        return signals[offset : offset + limit]
