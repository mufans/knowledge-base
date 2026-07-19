import json
from pathlib import Path

import pytest

from opportunity_os.errors import BoundaryError, CapacityError, ValidationError
from opportunity_os.freshness import StableGates, TechState
from opportunity_os.models import Direction, Evidence, Experiment, Opportunity, Review
from opportunity_os.scoring import OpportunityScores
from opportunity_os.store import PrivateStore


def sample_opportunity(identifier: str = "mobile-agent-service", bucket: str = "strength") -> Opportunity:
    return Opportunity(
        id=identifier,
        title=f"机会 {identifier}",
        opportunity_type="service",
        summary="通过低成本外部实验验证需求。",
        presentation_bucket=bucket,
        supporting_evidence=[
            Evidence(
                kind="fact",
                stance="support",
                claim="官方资料显示相关能力已发布。",
                source_name="官方资料",
                source_url="https://example.com/official",
                observed_at="2026-07-19",
            )
        ],
        opposing_evidence=[
            Evidence(
                kind="inference",
                stance="oppose",
                claim="尚未看到明确付费意愿。",
                source_name="岗位样本",
                source_url="https://example.com/jobs",
                observed_at="2026-07-19",
                source_tier="secondary",
            )
        ],
        invalidation_conditions=["两轮实验均无有效反馈"],
        experience_fit="移动端经验可用于形成差异化。",
        minimum_experiment=Experiment(
            title="岗位样本验证",
            hypothesis="市场需要交叉能力。",
            starts_at="2026-07-20",
            ends_at="2026-07-27",
            cost_level="low",
            action="分析公开岗位。",
            success_metric="至少十个匹配岗位。",
            continue_criteria=["匹配率达到三分之一"],
            stop_criteria=["匹配岗位少于三个"],
        ),
        continue_criteria=["获得外部需求证据"],
        stop_criteria=["无任何外部需求"],
        scores=OpportunityScores(8, 7, 8, 9, 6, 5, 5),
    )


def test_store_initializes_only_inside_private_home(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)

    store.initialize()

    assert {path.name for path in home.iterdir()} >= {
        "opportunities", "experiments", "tech_states", "reviews", "events.jsonl", "portfolio.json"
    }


def test_store_rejects_private_home_inside_knowledge_repo(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()

    with pytest.raises(BoundaryError, match="知识库之外"):
        PrivateStore(knowledge / "private", knowledge_root=knowledge)


def test_save_opportunity_is_atomic_and_appends_redacted_event(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    saved = store.save_opportunity(sample_opportunity())

    assert saved["id"] == "mobile-agent-service"
    assert json.loads((store.home / "opportunities/mobile-agent-service.json").read_text())["total_score"] == 7.3
    event = json.loads((store.home / "events.jsonl").read_text().splitlines()[-1])
    assert event == {
        "at": event["at"],
        "action": "save_opportunity",
        "entity_id": "mobile-agent-service",
        "entity_type": "opportunity",
    }
    assert not list(store.home.rglob("*.tmp"))


@pytest.mark.parametrize("identifier", ["../escape", "a/b", ".hidden", "A Space"])
def test_entity_ids_cannot_escape_private_home(tmp_path: Path, identifier: str) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    with pytest.raises(ValidationError, match="ID"):
        store.save_opportunity(sample_opportunity(identifier=identifier))


@pytest.mark.parametrize("forbidden_key", ["api_key", "token", "password", "secret", "cash_amount", "private_contact", "application_message"])
def test_store_rejects_sensitive_fields(tmp_path: Path, forbidden_key: str) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    payload = sample_opportunity().to_dict()
    payload["metadata"] = {forbidden_key: "must-not-land"}

    with pytest.raises(ValidationError, match="敏感字段"):
        store.save_payload("opportunity", payload)


def test_direction_capacity_allows_five_observe_two_validate_one_active(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    for index in range(5):
        store.set_direction(Direction(f"observe-{index}", f"观察 {index}", "observe", [], "观察", "2026-08-30"))
    for index in range(2):
        store.set_direction(Direction(f"validate-{index}", f"验证 {index}", "validate", [], "验证", "2026-08-30"))
    store.set_direction(Direction("active-0", "主动方向", "active", [], "主动", "2026-08-30"))

    assert store.get_portfolio()["counts"] == {"observe": 5, "validate": 2, "active": 1}


@pytest.mark.parametrize("status,existing_count", [("observe", 5), ("validate", 2), ("active", 1)])
def test_direction_capacity_rejects_overflow(tmp_path: Path, status: str, existing_count: int) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    for index in range(existing_count):
        store.set_direction(Direction(f"{status}-{index}", f"方向 {index}", status, [], "依据", "2026-08-30"))

    with pytest.raises(CapacityError, match="容量"):
        store.set_direction(Direction(f"{status}-overflow", "超额", status, [], "依据", "2026-08-30"))


def test_zero_active_direction_is_valid(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    assert store.get_portfolio()["counts"]["active"] == 0


def test_public_status_never_returns_directions(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    status = store.system_status()

    assert status["portfolio"] == {
        "counts": {"observe": 0, "validate": 0, "active": 0},
        "capacity": {"observe": 5, "validate": 2, "active": 1},
    }
    assert "directions" not in repr(status)


def test_daily_review_requires_a_surprise(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    review = Review(
        id="daily-2026-07-19",
        period="daily",
        title="每日机会扫描",
        summary="发现三项变化。",
        opportunity_ids=[],
        surprise_signal="",
        presentation_counts={"strength": 2, "broad": 2, "surprise": 0},
        proposed_experiment_ids=[],
        facts=["有官方发布"],
        inferences=["需求可能增长"],
        hypotheses=["值得验证"],
        created_at="2026-07-19T10:00:00+08:00",
    )

    with pytest.raises(ValidationError, match="意外发现"):
        store.save_review(review)


def test_weekly_review_enforces_integer_rounded_40_40_20_mix(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    review = Review(
        id="weekly-2026-07-19",
        period="weekly",
        title="每周机会扫描",
        summary="五张机会卡形成方向候选。",
        opportunity_ids=["a", "b", "c", "d", "e"],
        surprise_signal="工业小模型进入现场质检。",
        presentation_counts={"strength": 2, "broad": 2, "surprise": 1},
        proposed_experiment_ids=["exp-a"],
        facts=["有官方来源"],
        inferences=["跨领域需求正在形成"],
        hypotheses=["移动端经验可迁移"],
        created_at="2026-07-19T10:00:00+08:00",
    )

    assert store.save_review(review)["presentation_counts"] == {"strength": 2, "broad": 2, "surprise": 1}


def test_weekly_review_rejects_cocooned_mix(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    review = Review(
        id="weekly-2026-07-19",
        period="weekly",
        title="每周机会扫描",
        summary="五张卡全部来自既有优势。",
        opportunity_ids=["a", "b", "c", "d", "e"],
        surprise_signal="有意外发现但未进入卡片。",
        presentation_counts={"strength": 5, "broad": 0, "surprise": 0},
        proposed_experiment_ids=[],
        facts=["事实"],
        inferences=["推断"],
        hypotheses=["假设"],
        created_at="2026-07-19T10:00:00+08:00",
    )

    with pytest.raises(ValidationError, match="40/40/20"):
        store.save_review(review)


def test_review_rejects_invalid_created_at_before_persistence(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    with pytest.raises(ValidationError, match="created_at"):
        store.save_review(Review(
            id="daily-invalid-time",
            period="daily",
            title="每日机会扫描",
            summary="发现一项变化。",
            opportunity_ids=[],
            surprise_signal="新的变化。",
            presentation_counts={"strength": 0, "broad": 0, "surprise": 0},
            proposed_experiment_ids=[],
            facts=["有官方发布"],
            inferences=["需求可能增长"],
            hypotheses=["值得验证"],
            created_at="not-a-timestamp",
        ))

    assert not list((store.home / "reviews").glob("*.json"))


def stable_state() -> TechState:
    return TechState(
        technology="Hermes Agent",
        known_latest="0.18.2",
        recommended_stable="0.18.2",
        maturity="stable",
        official_sources=["https://github.com/NousResearch/hermes-agent/releases"],
        observed_at="2026-07-19",
        review_due_at="2026-08-02",
        confidence="high",
        stable_gates=StableGates(True, True, True, True, True),
        rollback_path="uv tool install hermes-agent==0.18.1",
    )


def test_frontier_record_cannot_replace_recommended_stable_without_gates(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.record_tech_state(stable_state())
    unsafe = TechState(
        technology="Hermes Agent",
        known_latest="0.19.0",
        recommended_stable="0.19.0",
        maturity="frontier",
        official_sources=["https://github.com/NousResearch/hermes-agent/releases"],
        observed_at="2026-07-20",
        review_due_at="2026-08-03",
        confidence="medium",
        stable_gates=StableGates(),
        rollback_path="uv tool install hermes-agent==0.18.2",
    )

    with pytest.raises(ValidationError, match="Stable 基线"):
        store.record_tech_state(unsafe)


def test_record_experiment_links_existing_opportunity_and_evidence(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.save_opportunity(sample_opportunity())
    result = store.record_experiment(
        experiment_id="exp-job-scan",
        opportunity_id="mobile-agent-service",
        experiment=sample_opportunity().minimum_experiment,
        evidence=[{"kind": "inference", "stance": "support", "claim": "岗位样本命中。", "source_name": "岗位样本", "source_url": "https://example.com/jobs", "observed_at": "2026-07-28", "source_tier": "primary"}],
    )

    assert result["opportunity_id"] == "mobile-agent-service"
    assert result["evidence"][0]["stance"] == "support"


def test_record_experiment_rejects_unknown_opportunity(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()

    with pytest.raises(ValidationError, match="机会不存在"):
        store.record_experiment(
            experiment_id="exp-missing",
            opportunity_id="missing-opportunity",
            experiment=sample_opportunity().minimum_experiment,
            evidence=[],
        )
