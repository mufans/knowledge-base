from dataclasses import asdict, dataclass, fields
from typing import Annotated

from pydantic import Field

from opportunity_os.errors import ValidationError


Score = Annotated[float, Field(ge=0, le=10)]


@dataclass(frozen=True, slots=True)
class OpportunityScores:
    market_demand: Score
    experience_advantage: Score
    growth_potential: Score
    low_cost_validation: Score
    long_term_asset: Score
    cashflow_potential: Score
    interest_signal: Score

    WEIGHTS = {
        "market_demand": 0.25,
        "experience_advantage": 0.20,
        "growth_potential": 0.15,
        "low_cost_validation": 0.15,
        "long_term_asset": 0.10,
        "cashflow_potential": 0.10,
        "interest_signal": 0.05,
    }

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"{field.name} 必须是数字")
            if not 0 <= float(value) <= 10:
                raise ValidationError(f"{field.name} 必须位于 0 到 10")

    @property
    def weighted_score(self) -> float:
        total = sum(float(getattr(self, key)) * weight for key, weight in self.WEIGHTS.items())
        return round(total, 2)

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, float]) -> "OpportunityScores":
        expected = set(cls.WEIGHTS)
        if set(value) != expected:
            missing = sorted(expected - set(value))
            extra = sorted(set(value) - expected)
            raise ValidationError(f"机会评分字段不完整，缺少={missing}，多余={extra}")
        return cls(**value)
