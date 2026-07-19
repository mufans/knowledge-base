from datetime import date, timedelta

import pytest

from opportunity_os.errors import ValidationError
from opportunity_os.models import Evidence, Experiment, Opportunity
from opportunity_os.scoring import OpportunityScores


def scores() -> OpportunityScores:
    return OpportunityScores(
        market_demand=8,
        experience_advantage=7,
        growth_potential=8,
        low_cost_validation=9,
        long_term_asset=6,
        cashflow_potential=5,
        interest_signal=5,
    )


def evidence(kind: str = "fact", stance: str = "support") -> Evidence:
    return Evidence(
        kind=kind,
        stance=stance,
        claim="官方文档显示该能力已正式发布。",
        source_name="官方文档",
        source_url="https://example.com/official",
        observed_at="2026-07-19",
    )


def experiment() -> Experiment:
    return Experiment(
        title="验证岗位需求",
        hypothesis="目标岗位会明确要求移动端与 Agent 交叉能力。",
        starts_at="2026-07-20",
        ends_at="2026-07-27",
        cost_level="low",
        action="分析 30 个公开岗位并制作技能矩阵。",
        success_metric="至少 10 个岗位同时命中两类能力。",
        continue_criteria=["命中率达到三分之一"],
        stop_criteria=["命中岗位少于 3 个"],
    )


@pytest.mark.parametrize("kind", ["fact", "inference", "hypothesis"])
def test_evidence_accepts_only_declared_reasoning_kinds(kind: str) -> None:
    assert evidence(kind=kind).kind == kind


def test_evidence_rejects_community_claim_as_fact_without_official_source() -> None:
    with pytest.raises(ValidationError, match="Fact.*官方"):
        Evidence(
            kind="fact",
            stance="support",
            claim="社区认为市场正在增长。",
            source_name="社区帖子",
            source_url="https://example.com/community",
            observed_at="2026-07-19",
            source_tier="community",
        )


def test_experiment_must_fit_one_to_two_weeks() -> None:
    too_long = date(2026, 7, 20) + timedelta(days=15)

    with pytest.raises(ValidationError, match="1 到 14 天"):
        Experiment(
            title="过长实验",
            hypothesis="假设",
            starts_at="2026-07-20",
            ends_at=too_long.isoformat(),
            cost_level="low",
            action="执行",
            success_metric="指标",
            continue_criteria=["继续"],
            stop_criteria=["停止"],
        )


def test_opportunity_requires_positive_and_opposing_evidence() -> None:
    with pytest.raises(ValidationError, match="反对证据"):
        Opportunity(
            id="mobile-agent-service",
            title="移动端 Agent 咨询服务",
            opportunity_type="service",
            summary="将移动端经验用于 Agent 工程咨询。",
            presentation_bucket="strength",
            supporting_evidence=[evidence()],
            opposing_evidence=[],
            invalidation_conditions=["连续两轮实验无外部需求"],
            experience_fit="12 年移动开发经验可形成差异化。",
            minimum_experiment=experiment(),
            continue_criteria=["获得 2 个有效访谈"],
            stop_criteria=["无人愿意接受访谈"],
            scores=scores(),
        )


def test_opportunity_round_trip_preserves_contract_and_computed_score() -> None:
    card = Opportunity(
        id="mobile-agent-service",
        title="移动端 Agent 咨询服务",
        opportunity_type="service",
        summary="将移动端经验用于 Agent 工程咨询。",
        presentation_bucket="strength",
        supporting_evidence=[evidence()],
        opposing_evidence=[evidence(kind="inference", stance="oppose")],
        invalidation_conditions=["连续两轮实验无外部需求"],
        experience_fit="12 年移动开发经验可形成差异化。",
        minimum_experiment=experiment(),
        continue_criteria=["获得 2 个有效访谈"],
        stop_criteria=["无人愿意接受访谈"],
        scores=scores(),
    )

    restored = Opportunity.from_dict(card.to_dict())

    assert restored.to_dict() == card.to_dict()
    assert restored.total_score == pytest.approx(7.3)
