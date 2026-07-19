from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from opportunity_os.errors import ValidationError


TechMaturity = Literal["frontier", "stable"]
Confidence = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class StableGates:
    official_stable_release: bool = False
    complete_documentation: bool = False
    compatibility_test_passed: bool = False
    no_severe_known_issue: bool = False
    rollback_path_ready: bool = False

    @property
    def all_passed(self) -> bool:
        return all(asdict(self).values())

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, bool]) -> "StableGates":
        return cls(**value)


@dataclass(frozen=True, slots=True)
class TechState:
    technology: str
    known_latest: str
    recommended_stable: str
    maturity: TechMaturity
    official_sources: list[str]
    observed_at: str
    review_due_at: str
    confidence: Confidence
    stable_gates: StableGates
    rollback_path: str

    def __post_init__(self) -> None:
        if self.maturity not in {"frontier", "stable"}:
            raise ValidationError("技术成熟度必须是 frontier 或 stable")
        if self.confidence not in {"low", "medium", "high"}:
            raise ValidationError("置信度必须是 low、medium 或 high")
        if not self.technology.strip() or not self.known_latest.strip() or not self.recommended_stable.strip():
            raise ValidationError("技术名称和版本不能为空")
        if not self.official_sources or not all(source.startswith("https://") for source in self.official_sources):
            raise ValidationError("TechState 必须包含 HTTPS 官方来源")
        date.fromisoformat(self.observed_at)
        date.fromisoformat(self.review_due_at)
        if not self.rollback_path.strip():
            raise ValidationError("必须提供回滚路径")
        if self.maturity == "stable" and not self.stable_gates.all_passed:
            raise ValidationError("Stable 晋升必须通过五项门槛")

    def needs_review(self, today: str) -> bool:
        return date.fromisoformat(today) >= date.fromisoformat(self.review_due_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "technology": self.technology,
            "known_latest": self.known_latest,
            "recommended_stable": self.recommended_stable,
            "maturity": self.maturity,
            "official_sources": list(self.official_sources),
            "observed_at": self.observed_at,
            "review_due_at": self.review_due_at,
            "confidence": self.confidence,
            "stable_gates": self.stable_gates.to_dict(),
            "rollback_path": self.rollback_path,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TechState":
        payload = dict(value)
        payload["stable_gates"] = StableGates.from_dict(payload["stable_gates"])
        return cls(**payload)
