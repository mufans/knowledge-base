import pytest

from opportunity_os.errors import ValidationError
from opportunity_os.freshness import StableGates, TechState


def all_gates() -> StableGates:
    return StableGates(
        official_stable_release=True,
        complete_documentation=True,
        compatibility_test_passed=True,
        no_severe_known_issue=True,
        rollback_path_ready=True,
    )


def test_stable_state_requires_all_five_gates() -> None:
    with pytest.raises(ValidationError, match="五项"):
        TechState(
            technology="Hermes Agent",
            known_latest="0.19.0",
            recommended_stable="0.18.2",
            maturity="stable",
            official_sources=["https://github.com/NousResearch/hermes-agent/releases"],
            observed_at="2026-07-19",
            review_due_at="2026-08-02",
            confidence="high",
            stable_gates=StableGates(
                official_stable_release=True,
                complete_documentation=True,
                compatibility_test_passed=False,
                no_severe_known_issue=True,
                rollback_path_ready=True,
            ),
            rollback_path="uv tool install hermes-agent==0.18.2",
        )


def test_frontier_can_track_latest_without_replacing_stable() -> None:
    state = TechState(
        technology="Hermes Agent",
        known_latest="0.19.0",
        recommended_stable="0.18.2",
        maturity="frontier",
        official_sources=["https://github.com/NousResearch/hermes-agent/releases"],
        observed_at="2026-07-19",
        review_due_at="2026-08-02",
        confidence="medium",
        stable_gates=StableGates(),
        rollback_path="uv tool install hermes-agent==0.18.2",
    )

    assert state.known_latest == "0.19.0"
    assert state.recommended_stable == "0.18.2"


def test_review_due_is_a_review_signal_not_automatic_invalidation() -> None:
    state = TechState(
        technology="Hermes Agent",
        known_latest="0.18.2",
        recommended_stable="0.18.2",
        maturity="stable",
        official_sources=["https://github.com/NousResearch/hermes-agent/releases"],
        observed_at="2026-07-01",
        review_due_at="2026-07-10",
        confidence="high",
        stable_gates=all_gates(),
        rollback_path="uv tool install hermes-agent==0.18.1",
    )

    assert state.needs_review("2026-07-19") is True
    assert state.maturity == "stable"
