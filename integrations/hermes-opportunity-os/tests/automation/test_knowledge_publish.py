import json
from pathlib import Path

import pytest

from opportunity_os.automation.hermes_sync import HermesKnowledgeBridge
from opportunity_os.automation.knowledge_publish import (
    KnowledgePublishRunner,
    build_candidate,
    derive_tags,
)
from opportunity_os.contracts import Claim, content_hash
from opportunity_os.errors import ValidationError


def evidence(eid: str, stance: str, claim: str) -> dict:
    return {
        "schema_version": 1,
        "id": eid,
        "source_url": "https://example.com/source",
        "collected_at": "2026-08-13T00:00:00Z",
        "content_hash": content_hash(claim),
        "run_id": "run-publish-fixture",
        "claim_type": "fact" if stance == "support" else "inference",
        "stance": stance,
        "claim": claim,
        "source_name": "Source",
        "source_tier": "official" if stance == "support" else "secondary",
        "locator": None,
    }


def analysis(payload: dict) -> dict:
    base = {
        "schema_version": 1,
        "id": "analysis-publish-fixture",
        "source_url": "https://example.com/source",
        "collected_at": "2026-08-13T00:00:00Z",
        "content_hash": content_hash("analysis-core"),
        "run_id": "run-publish-fixture",
        "signal_ids": ["signal-fixture"],
        "claims": [
            Claim(
                id="claim-support-fixture",
                claim_type="fact",
                text="移动端 Agent 工具调用支持可验证。",
                evidence_ids=("evidence-support",),
            ).model_dump(mode="json"),
            Claim(
                id="claim-oppose-fixture",
                claim_type="inference",
                text="端侧推理延迟仍需验证。",
                evidence_ids=("evidence-oppose",),
            ).model_dump(mode="json"),
        ],
        "supporting_evidence_ids": ["evidence-support"],
        "opposing_evidence_ids": ["evidence-oppose"],
        "conflicts": ["移动端 Agent 安全边界仍需统一。"],
        "knowledge_gaps": ["需要验证端侧工具调用的延迟上限。"],
        "collection_questions": [],
    }
    base.update(payload)
    return base


def dossier(*, title: str = "移动端 Agent 端侧推理综合观察", **overrides) -> dict:
    value = {
        "schema_version": 1,
        "review_id": "daily-publish-fixture",
        "review_title": title,
        "analysis": analysis({}),
        "evidence": [
            evidence("evidence-support", "support", "移动端 Agent 工具调用支持可验证。"),
            evidence("evidence-oppose", "oppose", "端侧推理延迟仍需验证。"),
        ],
        "next_stage": "wiki_candidate",
    }
    value.update(overrides)
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def roots(tmp_path: Path) -> tuple[Path, Path]:
    knowledge = tmp_path / "knowledge"
    private = tmp_path / "private"
    (knowledge / "raw").mkdir(parents=True)
    for name in ("concepts", "entities", "sources", "syntheses"):
        directory = knowledge / "wiki" / name
        directory.mkdir(parents=True)
        (directory / "index.md").write_text(f"# {name}\n", encoding="utf-8")
    (knowledge / "log.md").write_text("", encoding="utf-8")
    write_json(private / "compiler" / "dossiers" / "daily-publish-fixture.json", dossier())
    return knowledge, private


def test_build_candidate_produces_reviewable_synthesis(tmp_path: Path) -> None:
    knowledge, _ = roots(tmp_path)

    candidate, records = build_candidate(dossier(), knowledge_root=knowledge)

    assert candidate.page_type == "synthesis"
    assert candidate.action == "create"
    assert candidate.human_decision == "approved"
    assert candidate.purpose_relevance == 1.0
    assert candidate.novelty_score >= 0.2
    assert candidate.target_path.startswith("wiki/syntheses/")
    assert {record.id for record in records} == {"evidence-support", "evidence-oppose"}
    assert all(section.strip() for section in candidate.sections.values())


def test_derive_tags_is_purpose_bounded(tmp_path: Path) -> None:
    tags = derive_tags("移动端 Agent 工具调用 + RAG 与 MCP")
    assert "Agent" in tags
    assert "Mobile" in tags
    assert 2 <= len(tags) <= 5


def test_publish_writes_wiki_page_index_log_and_markers(tmp_path: Path) -> None:
    knowledge, private = roots(tmp_path)
    raw_before = tuple((knowledge / "raw").rglob("*"))

    runner = KnowledgePublishRunner(private, knowledge)
    record = runner.run(run_id="run-publish-test-20260813")

    assert record.status == "success"
    assert record.published == 1
    assert record.rejected == 0
    syntheses = knowledge / "wiki" / "syntheses"
    pages = [path for path in syntheses.glob("*.md") if path.name != "index.md"]
    assert len(pages) == 1
    assert "**Fact**" in pages[0].read_text(encoding="utf-8")
    assert "移动端 Agent 端侧推理综合观察" in (syntheses / "index.md").read_text(encoding="utf-8")
    assert "Knowledge Compiler" in (knowledge / "log.md").read_text(encoding="utf-8")
    assert list((private / "compiler" / "published").glob("*.json"))
    run_file = list((private / "compiler" / "runs").glob("*.json"))
    assert run_file and json.loads(run_file[0].read_text())["published"] == 1
    assert tuple((knowledge / "raw").rglob("*")) == raw_before


def test_publish_is_idempotent_via_marker(tmp_path: Path) -> None:
    knowledge, private = roots(tmp_path)
    runner = KnowledgePublishRunner(private, knowledge)

    first = runner.run(run_id="run-publish-first")
    second = runner.run(run_id="run-publish-second")

    assert first.published == 1
    assert second.published == 0
    assert second.skipped == 1


def test_purpose_irrelevant_dossier_is_observable_rejection(tmp_path: Path) -> None:
    knowledge, private = roots(tmp_path)
    irrelevant = dossier(
        review_id="daily-irrelevant",
        title="完全无关主题的综合观察",
        analysis=analysis(
            {
                "claims": [
                    Claim(
                        id="claim-support-fixture",
                        claim_type="fact",
                        text="数据库索引优化收益可验证。",
                        evidence_ids=("evidence-support",),
                    ).model_dump(mode="json"),
                    Claim(
                        id="claim-oppose-fixture",
                        claim_type="inference",
                        text="写入放大仍然存在。",
                        evidence_ids=("evidence-oppose",),
                    ).model_dump(mode="json"),
                ],
                "conflicts": ["数据库迁移风险仍需评估。"],
                "knowledge_gaps": ["需要验证索引维护成本。"],
            }
        ),
        evidence=[
            evidence("evidence-support", "support", "数据库索引优化收益可验证。"),
            evidence("evidence-oppose", "oppose", "写入放大仍然存在。"),
        ],
    )
    write_json(private / "compiler" / "dossiers" / "irrelevant.json", irrelevant)
    (private / "compiler" / "dossiers" / "daily-publish-fixture.json").unlink()

    record = KnowledgePublishRunner(private, knowledge).run(run_id="run-publish-reject")

    assert record.rejected == 1
    rejections = list((private / "compiler" / "rejections").glob("*.json"))
    assert rejections
    pages = [path for path in (knowledge / "wiki" / "syntheses").glob("*.md") if path.name != "index.md"]
    assert not pages


def test_dry_run_reviews_without_mutation(tmp_path: Path) -> None:
    knowledge, private = roots(tmp_path)
    runner = KnowledgePublishRunner(private, knowledge)

    record = runner.run(run_id="run-publish-dry", dry_run=True)

    assert record.published == 0
    assert record.plan and record.plan[0]["decision"] == "publish"
    assert not list((private / "compiler" / "published").glob("*.json"))
    pages = [path for path in (knowledge / "wiki" / "syntheses").glob("*.md") if path.name != "index.md"]
    assert not pages


def test_end_to_end_sync_then_publish_never_touches_raw(tmp_path: Path) -> None:
    knowledge, private = roots(tmp_path)
    (private / "compiler" / "dossiers" / "daily-publish-fixture.json").unlink()

    experiment = {
        "title": "最小实验",
        "hypothesis": "假设",
        "starts_at": "2026-08-13",
        "ends_at": "2026-08-15",
        "cost_level": "low",
        "action": "执行",
        "success_metric": "通过",
        "continue_criteria": ["通过"],
        "stop_criteria": ["失败"],
    }
    opp = {
        "id": "opp-mobile-agent",
        "title": "移动 Agent",
        "opportunity_type": "cross_domain",
        "summary": "摘要",
        "presentation_bucket": "surprise",
        "supporting_evidence": [
            {
                "kind": "fact", "stance": "support", "claim": "移动端 Agent 工具调用支持可验证。",
                "source_name": "Source", "source_url": "https://example.com/source",
                "observed_at": "2026-08-13", "source_tier": "official",
            }
        ],
        "opposing_evidence": [
            {
                "kind": "inference", "stance": "oppose", "claim": "端侧推理延迟仍需验证。",
                "source_name": "Source", "source_url": "https://example.com/source",
                "observed_at": "2026-08-13", "source_tier": "secondary",
            }
        ],
        "invalidation_conditions": ["条件"],
        "experience_fit": "移动开发",
        "minimum_experiment": experiment,
        "continue_criteria": ["继续"],
        "stop_criteria": ["停止"],
        "scores": {
            "market_demand": 8, "experience_advantage": 8, "growth_potential": 8,
            "low_cost_validation": 8, "long_term_asset": 8, "cashflow_potential": 8,
            "interest_signal": 8,
        },
        "status": "candidate",
        "total_score": 8,
    }
    review = {
        "id": "daily-e2e",
        "period": "daily",
        "title": "移动端 Agent 端侧推理综合观察",
        "summary": "摘要",
        "opportunity_ids": ["opp-mobile-agent"],
        "surprise_signal": "意外发现",
        "presentation_counts": {"strength": 0, "broad": 0, "surprise": 1},
        "proposed_experiment_ids": [],
        "facts": ["事实"],
        "inferences": ["推断"],
        "hypotheses": ["假设"],
        "created_at": "2026-08-13T00:00:00+00:00",
    }
    write_json(private / "opportunities" / "opp-mobile-agent.json", opp)
    write_json(private / "reviews" / "daily-e2e.json", review)
    raw_before = tuple((knowledge / "raw").rglob("*"))

    sync = HermesKnowledgeBridge(private, knowledge).run(days=14, run_id="run-sync-e2e")
    assert sync.dossiers_written == 1

    publish = KnowledgePublishRunner(private, knowledge).run(run_id="run-publish-e2e")
    assert publish.published == 1
    assert tuple((knowledge / "raw").rglob("*")) == raw_before
