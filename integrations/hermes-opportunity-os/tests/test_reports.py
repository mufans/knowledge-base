from pathlib import Path

from opportunity_os.models import Evidence, Experiment, Opportunity, Review
from opportunity_os.reports import render_review
from opportunity_os.scoring import OpportunityScores
from opportunity_os.store import PrivateStore


def seed_review(store: PrivateStore) -> str:
    opportunity = Opportunity(
        id="cross-domain-quality",
        title="工业质检端侧 Agent",
        opportunity_type="cross_domain",
        summary="验证移动端工程能力是否能迁移到工业现场。",
        presentation_bucket="surprise",
        supporting_evidence=[Evidence("fact", "support", "论文报告现场部署。", "原始论文", "https://example.edu/paper", "2026-07-19")],
        opposing_evidence=[Evidence("inference", "oppose", "行业销售周期可能较长。", "行业分析", "https://example.com/report", "2026-07-19", "secondary")],
        invalidation_conditions=["无法找到可访谈的行业从业者"],
        experience_fit="端侧性能经验可迁移，但缺少行业知识。",
        minimum_experiment=Experiment(
            "行业访谈", "存在未满足需求", "2026-07-20", "2026-07-27", "low", "访谈三人", "两人确认痛点", ["两人确认"], ["无人确认"]
        ),
        continue_criteria=["获得两项真实痛点"],
        stop_criteria=["无真实痛点"],
        scores=OpportunityScores(7, 6, 8, 8, 7, 5, 4),
    )
    store.save_opportunity(opportunity)
    review = Review(
        id="weekly-2026-07-19",
        period="weekly",
        title="首次每周机会发现",
        summary="形成一张跨领域机会卡。",
        opportunity_ids=[opportunity.id],
        surprise_signal="工业质检正在采用轻量模型。",
        presentation_counts={"strength": 0, "broad": 0, "surprise": 1},
        proposed_experiment_ids=["industry-interview"],
        facts=["原始论文报告现场部署"],
        inferences=["工程经验可能迁移"],
        hypotheses=["可形成小型咨询服务"],
        created_at="2026-07-19T10:00:00+08:00",
    )
    store.save_review(review)
    return review.id


def test_render_review_labels_reasoning_and_both_evidence_sides(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    review_id = seed_review(store)

    markdown = render_review(store, review_id)

    assert "## Fact" in markdown
    assert "## Inference" in markdown
    assert "## Hypothesis" in markdown
    assert "## 意外发现" in markdown
    assert "### 支持证据" in markdown
    assert "### 反对证据" in markdown
    assert "### 最小实验" in markdown
    assert "2026-07-19" in markdown


def test_render_latest_review_uses_created_at_order(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    seed_review(store)

    assert "首次每周机会发现" in render_review(store, latest=True)
