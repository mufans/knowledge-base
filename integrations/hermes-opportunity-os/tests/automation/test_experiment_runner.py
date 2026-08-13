from dataclasses import replace
from pathlib import Path

import pytest

from opportunity_os.automation.experiment_runner import ExperimentRunner
from opportunity_os.errors import ValidationError
from opportunity_os.models import Evidence, Experiment, Opportunity
from opportunity_os.scoring import OpportunityScores
from opportunity_os.store import PrivateStore


def sample_opportunity(identifier: str = "mobile-agent-service") -> Opportunity:
    return Opportunity(
        id=identifier,
        title=f"机会 {identifier}",
        opportunity_type="service",
        summary="通过低成本外部实验验证需求。",
        presentation_bucket="strength",
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


def test_eligible_filters_researched_cards_with_experiments(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)
    store.initialize()
    store.save_opportunity(replace(sample_opportunity(), status="researched"))
    store.save_opportunity(replace(sample_opportunity("completed-card"), status="completed"))

    runner = ExperimentRunner(home)
    eligible = runner.plan()

    assert [item["opportunity_id"] for item in eligible] == ["mobile-agent-service"]
    assert eligible[0]["predicted_success"] is True


def test_run_dry_is_non_mutating(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)
    store.initialize()
    store.save_opportunity(replace(sample_opportunity(), status="researched"))

    result = ExperimentRunner(home).run(
        "mobile-agent-service", run_id="run-exp-dry", apply=False
    )

    assert result["applied"] is False
    assert result["next_state"] == "validated"
    assert not list((home / "experiments").glob("*.json"))
    assert store.get_opportunity("mobile-agent-service")["status"] == "researched"


def test_run_records_experiment_and_advances_to_validated(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)
    store.initialize()
    store.save_opportunity(replace(sample_opportunity(), status="researched"))

    result = ExperimentRunner(home).run(
        "mobile-agent-service", run_id="run-exp-apply", apply=True
    )

    assert result["applied"] is True
    assert result["success"] is True
    assert result["transition"]["to_state"] == "validated"
    assert store.get_opportunity("mobile-agent-service")["status"] == "validated"
    experiment_files = list((home / "experiments").glob("*.json"))
    assert len(experiment_files) == 1
    assert store._read_json(experiment_files[0])["opportunity_id"] == "mobile-agent-service"


def test_run_rejects_non_researched_candidate(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)
    store.initialize()
    store.save_opportunity(replace(sample_opportunity(), status="completed"))

    with pytest.raises(ValidationError, match="不可进入实验"):
        ExperimentRunner(home).run("mobile-agent-service", run_id="run-exp-invalid", apply=True)
