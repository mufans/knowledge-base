from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from opportunity_os.errors import ValidationError
from opportunity_os.scoring import OpportunityScores


def _required_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} 不能为空")


def _required_list(value: list[Any], label: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{label} 不能为空")


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: str
    stance: str
    claim: str
    source_name: str
    source_url: str
    observed_at: str
    source_tier: str = "official"

    def __post_init__(self) -> None:
        if self.kind not in {"fact", "inference", "hypothesis"}:
            raise ValidationError("Evidence.kind 必须是 fact、inference 或 hypothesis")
        if self.stance not in {"support", "oppose"}:
            raise ValidationError("Evidence.stance 必须是 support 或 oppose")
        for value, label in (
            (self.claim, "证据声明"),
            (self.source_name, "来源名称"),
            (self.source_url, "来源 URL"),
        ):
            _required_text(value, label)
        date.fromisoformat(self.observed_at)
        if self.kind == "fact" and self.source_tier not in {"official", "primary"}:
            raise ValidationError("Fact 必须引用官方或一手来源")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Evidence":
        return cls(**value)


@dataclass(frozen=True, slots=True)
class Experiment:
    title: str
    hypothesis: str
    starts_at: str
    ends_at: str
    cost_level: str
    action: str
    success_metric: str
    continue_criteria: list[str]
    stop_criteria: list[str]

    def __post_init__(self) -> None:
        for value, label in (
            (self.title, "实验标题"),
            (self.hypothesis, "实验假设"),
            (self.action, "实验动作"),
            (self.success_metric, "成功指标"),
        ):
            _required_text(value, label)
        if self.cost_level not in {"none", "low", "medium"}:
            raise ValidationError("实验成本只能是 none、low 或 medium")
        duration = (date.fromisoformat(self.ends_at) - date.fromisoformat(self.starts_at)).days
        if duration < 1 or duration > 14:
            raise ValidationError("最小实验必须在 1 到 14 天内完成")
        _required_list(self.continue_criteria, "继续标准")
        _required_list(self.stop_criteria, "停止标准")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Experiment":
        return cls(**value)


@dataclass(frozen=True, slots=True)
class Opportunity:
    id: str
    title: str
    opportunity_type: str
    summary: str
    presentation_bucket: str
    supporting_evidence: list[Evidence]
    opposing_evidence: list[Evidence]
    invalidation_conditions: list[str]
    experience_fit: str
    minimum_experiment: Experiment
    continue_criteria: list[str]
    stop_criteria: list[str]
    scores: OpportunityScores
    status: str = "candidate"

    def __post_init__(self) -> None:
        for value, label in (
            (self.id, "机会 ID"),
            (self.title, "机会标题"),
            (self.summary, "机会摘要"),
            (self.experience_fit, "经验组合关系"),
        ):
            _required_text(value, label)
        if self.opportunity_type not in {
            "career", "technology", "product", "service", "open_source", "content", "network", "cross_domain"
        }:
            raise ValidationError("不支持的机会类型")
        if self.presentation_bucket not in {"strength", "broad", "surprise"}:
            raise ValidationError("presentation_bucket 必须是 strength、broad 或 surprise")
        if self.status not in {"candidate", "observing", "validating", "active", "paused", "stopped"}:
            raise ValidationError("不支持的机会状态")
        _required_list(self.supporting_evidence, "支持证据")
        _required_list(self.opposing_evidence, "反对证据")
        if any(item.stance != "support" for item in self.supporting_evidence):
            raise ValidationError("支持证据的 stance 必须是 support")
        if any(item.stance != "oppose" for item in self.opposing_evidence):
            raise ValidationError("反对证据的 stance 必须是 oppose")
        _required_list(self.invalidation_conditions, "失效条件")
        _required_list(self.continue_criteria, "机会继续标准")
        _required_list(self.stop_criteria, "机会停止标准")

    @property
    def total_score(self) -> float:
        return self.scores.weighted_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "opportunity_type": self.opportunity_type,
            "summary": self.summary,
            "presentation_bucket": self.presentation_bucket,
            "supporting_evidence": [item.to_dict() for item in self.supporting_evidence],
            "opposing_evidence": [item.to_dict() for item in self.opposing_evidence],
            "invalidation_conditions": list(self.invalidation_conditions),
            "experience_fit": self.experience_fit,
            "minimum_experiment": self.minimum_experiment.to_dict(),
            "continue_criteria": list(self.continue_criteria),
            "stop_criteria": list(self.stop_criteria),
            "scores": self.scores.to_dict(),
            "status": self.status,
            "total_score": self.total_score,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Opportunity":
        payload = dict(value)
        payload.pop("total_score", None)
        payload["supporting_evidence"] = [Evidence.from_dict(item) for item in payload["supporting_evidence"]]
        payload["opposing_evidence"] = [Evidence.from_dict(item) for item in payload["opposing_evidence"]]
        payload["minimum_experiment"] = Experiment.from_dict(payload["minimum_experiment"])
        payload["scores"] = OpportunityScores.from_dict(payload["scores"])
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class Direction:
    id: str
    title: str
    status: str
    opportunity_ids: list[str]
    rationale: str
    next_review_at: str

    def __post_init__(self) -> None:
        _required_text(self.id, "方向 ID")
        _required_text(self.title, "方向标题")
        _required_text(self.rationale, "方向依据")
        if self.status not in {"observe", "validate", "active"}:
            raise ValidationError("方向状态必须是 observe、validate 或 active")
        date.fromisoformat(self.next_review_at)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Direction":
        return cls(**value)


@dataclass(frozen=True, slots=True)
class Review:
    id: str
    period: str
    title: str
    summary: str
    opportunity_ids: list[str]
    surprise_signal: str
    presentation_counts: dict[str, int]
    proposed_experiment_ids: list[str]
    facts: list[str]
    inferences: list[str]
    hypotheses: list[str]
    created_at: str

    def __post_init__(self) -> None:
        _required_text(self.id, "复盘 ID")
        _required_text(self.title, "复盘标题")
        _required_text(self.summary, "复盘摘要")
        if self.period not in {"daily", "weekly", "six_week", "quarterly"}:
            raise ValidationError("不支持的复盘周期")
        if set(self.presentation_counts) != {"strength", "broad", "surprise"}:
            raise ValidationError("呈现计数必须包含 strength、broad、surprise")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in self.presentation_counts.values()):
            raise ValidationError("呈现计数必须是非负整数")
        _required_list(self.facts, "Fact 列表")
        _required_list(self.inferences, "Inference 列表")
        _required_list(self.hypotheses, "Hypothesis 列表")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Review":
        return cls(**value)
