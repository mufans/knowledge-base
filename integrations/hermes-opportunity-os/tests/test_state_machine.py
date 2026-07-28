import json
from pathlib import Path

import pytest

from opportunity_os.errors import ValidationError
from opportunity_os.store import PrivateStore
from test_store import sample_opportunity


def test_research_transition_is_persisted_with_full_audit_context(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.save_opportunity(sample_opportunity())

    result = store.transition_opportunity(
        opportunity_id="mobile-agent-service",
        to_state="researched",
        trigger_reason="完成正反证据整理",
        new_evidence_ids=["evidence-support-001"],
        opposing_evidence_ids=["evidence-oppose-001"],
        next_experiment_id="experiment-job-scan",
        user_decision=None,
        automatic_rule="support_and_oppose_present",
        run_id="run-phase3-20260729",
        occurred_at="2026-07-29T08:00:00Z",
    )

    assert result["from_state"] == "candidate"
    assert result["to_state"] == "researched"
    assert store.get_opportunity("mobile-agent-service")["status"] == "researched"
    history = json.loads(
        (store.home / "state_transitions/mobile-agent-service.jsonl").read_text().splitlines()[0]
    )
    assert history["run_id"] == "run-phase3-20260729"
    assert history["opposing_evidence_ids"] == ["evidence-oppose-001"]


def test_state_machine_rejects_skipped_validation_stage(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.save_opportunity(sample_opportunity())

    with pytest.raises(ValidationError, match="candidate -> active"):
        store.transition_opportunity(
            opportunity_id="mobile-agent-service",
            to_state="active",
            trigger_reason="跳过验证",
            new_evidence_ids=["evidence-support-001"],
            opposing_evidence_ids=["evidence-oppose-001"],
            next_experiment_id="experiment-job-scan",
            user_decision=None,
            automatic_rule="unsafe_skip",
            run_id="run-phase3-20260729",
        )


def test_researched_transition_requires_opposing_evidence_and_decision_rule(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.save_opportunity(sample_opportunity())

    with pytest.raises(ValidationError, match="user_decision or automatic_rule|opposing evidence"):
        store.transition_opportunity(
            opportunity_id="mobile-agent-service",
            to_state="researched",
            trigger_reason="证据不完整",
            new_evidence_ids=["evidence-support-001"],
            opposing_evidence_ids=[],
            next_experiment_id=None,
            user_decision=None,
            automatic_rule=None,
            run_id="run-phase3-20260729",
        )


def test_legacy_statuses_are_explicitly_migrated_on_read(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    payload = sample_opportunity().to_dict()
    payload["status"] = "observing"
    store._write_json(store.home / "opportunities/mobile-agent-service.json", payload)

    assert store.list_opportunities()[0]["status"] == "researched"
