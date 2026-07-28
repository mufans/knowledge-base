import json
from datetime import datetime, timezone
from pathlib import Path

from opportunity_os.automation.hermes_sync import HermesKnowledgeBridge


NOW = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def opportunity(source_url: str = "https://example.com/source") -> dict:
    experiment = {
        "title": "最小实验",
        "hypothesis": "假设",
        "starts_at": "2026-07-29",
        "ends_at": "2026-08-01",
        "cost_level": "low",
        "action": "执行",
        "success_metric": "通过",
        "continue_criteria": ["通过"],
        "stop_criteria": ["失败"],
    }
    evidence = lambda stance, claim: {
        "kind": "fact" if stance == "support" else "inference",
        "stance": stance,
        "claim": claim,
        "source_name": "Source",
        "source_url": source_url,
        "observed_at": "2026-07-29",
        "source_tier": "official" if stance == "support" else "secondary",
    }
    return {
        "id": "opp-fixture",
        "title": "移动 Agent",
        "opportunity_type": "cross_domain",
        "summary": "摘要",
        "presentation_bucket": "surprise",
        "supporting_evidence": [evidence("support", "可追溯支持事实")],
        "opposing_evidence": [evidence("oppose", "可追溯反方推断")],
        "invalidation_conditions": ["条件"],
        "experience_fit": "移动开发",
        "minimum_experiment": experiment,
        "continue_criteria": ["继续"],
        "stop_criteria": ["停止"],
        "scores": {
            "market_demand": 8,
            "experience_advantage": 8,
            "growth_potential": 8,
            "low_cost_validation": 8,
            "long_term_asset": 8,
            "cashflow_potential": 8,
            "interest_signal": 8
        },
        "status": "candidate",
        "total_score": 8
    }


def review() -> dict:
    return {
        "id": "daily-fixture",
        "period": "daily",
        "title": "每日复盘",
        "summary": "摘要",
        "opportunity_ids": ["opp-fixture"],
        "surprise_signal": "意外发现",
        "presentation_counts": {"strength": 0, "broad": 0, "surprise": 1},
        "proposed_experiment_ids": [],
        "facts": ["事实"],
        "inferences": ["推断"],
        "hypotheses": ["假设"],
        "created_at": "2026-07-29T00:00:00+00:00"
    }


def setup_roots(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "private"
    knowledge = tmp_path / "knowledge"
    (knowledge / "raw").mkdir(parents=True)
    (knowledge / "wiki").mkdir()
    write_json(private / "opportunities" / "opp-fixture.json", opportunity())
    write_json(private / "reviews" / "daily-fixture.json", review())
    return private, knowledge


def test_sync_golden_uses_claim_and_source_url_and_never_writes_raw(tmp_path: Path) -> None:
    private, knowledge = setup_roots(tmp_path)
    raw_before = tuple((knowledge / "raw").rglob("*"))

    record = HermesKnowledgeBridge(private, knowledge, now=lambda: NOW).run(
        days=14, run_id="run-sync-golden-20260729"
    )

    dossier = json.loads((private / "compiler" / "dossiers" / "daily-fixture.json").read_text())
    assert record.status == "success"
    assert record.dossiers_written == 1
    assert record.published == 0
    assert {item["claim"] for item in dossier["evidence"]} == {
        "可追溯支持事实", "可追溯反方推断"
    }
    assert all(item["source_url"] == "https://example.com/source" for item in dossier["evidence"])
    assert tuple((knowledge / "raw").rglob("*")) == raw_before


def test_invalid_evidence_is_observable_rejection_not_blank_markdown(tmp_path: Path) -> None:
    private, knowledge = setup_roots(tmp_path)
    write_json(private / "opportunities" / "opp-fixture.json", opportunity("raw/inbox/local.md"))

    record = HermesKnowledgeBridge(private, knowledge, now=lambda: NOW).run(
        days=14, run_id="run-sync-invalid-20260729"
    )

    rejection = json.loads((private / "compiler" / "rejections" / "daily-fixture.json").read_text())
    assert record.status == "success"
    assert record.dossiers_written == 0
    assert record.rejected == 1
    assert record.validation_errors > 0
    assert "invalid_evidence_contract" in record.rejection_reasons
    assert rejection["status"] == "rejected"
    assert not list((knowledge / "raw").glob("*.md"))


def test_unchanged_dossier_is_idempotently_skipped(tmp_path: Path) -> None:
    private, knowledge = setup_roots(tmp_path)
    bridge = HermesKnowledgeBridge(private, knowledge, now=lambda: NOW)

    first = bridge.run(days=14, run_id="run-sync-first-20260729")
    second = bridge.run(days=14, run_id="run-sync-second-20260729")

    assert first.dossiers_written == 1
    assert second.dossiers_written == 0
    assert second.skipped_unchanged == 1
