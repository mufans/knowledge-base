"""Private opportunity discovery MCP server."""

import hashlib
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from opportunity_os.freshness import Confidence, StableGates, TechMaturity, TechState
from opportunity_os.models import (
    CostLevel,
    Direction,
    DirectionStatus,
    Evidence,
    Experiment,
    Opportunity,
    OpportunityStatus,
    OpportunityType,
    PresentationBucket,
    PresentationCounts,
    Review,
    ReviewPeriod,
)
from opportunity_os.reports import render_review as render_review_markdown
from opportunity_os.scoring import OpportunityScores
from opportunity_os.signals import SignalReader
from opportunity_os.store import PrivateStore


KNOWLEDGE_BASE_PATH = Path(os.environ.get("KNOWLEDGE_BASE_PATH", "")).expanduser()
OPPORTUNITY_OS_HOME = Path(os.environ.get("OPPORTUNITY_OS_HOME", "")).expanduser()

mcp = FastMCP("opportunity-discovery-os")


def _reader() -> SignalReader:
    return SignalReader(KNOWLEDGE_BASE_PATH)


def _store() -> PrivateStore:
    store = PrivateStore(OPPORTUNITY_OS_HOME, knowledge_root=KNOWLEDGE_BASE_PATH)
    store.initialize()
    return store


@mcp.tool()
def list_signals(days: int = 14, limit: int = 80, offset: int = 0, query: str | None = None, today: str | None = None) -> list[dict[str, Any]]:
    """List broad recent signals; query is optional and never applied by default."""
    return [item.to_dict() for item in _reader().list_signals(days=days, limit=limit, offset=offset, query=query, today=today)]


@mcp.tool()
def get_signal(relative_path: str) -> dict[str, str]:
    """Read one Markdown source beneath raw/inbox without modifying it."""
    return _reader().get_signal(relative_path)


@mcp.tool()
def save_opportunity(
    title: str,
    opportunity_type: OpportunityType,
    summary: str,
    presentation_bucket: PresentationBucket,
    supporting_evidence: list[Evidence],
    opposing_evidence: list[Evidence],
    invalidation_conditions: list[str],
    experience_fit: str,
    experiment: Experiment,
    continue_criteria: list[str],
    stop_criteria: list[str],
    scores: OpportunityScores,
) -> dict[str, Any]:
    """Validate and persist a complete opportunity card in private state.

    Every evidence item uses kind=fact|inference|hypothesis and
    stance=support|oppose; these values are not source tiers.
    Every evidence item uses source_tier=official|primary|secondary|community.
    Fact evidence requires official or primary; never use A/B/C tier aliases.
    """
    identifier = "opp-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]
    opportunity = Opportunity(
        id=identifier,
        title=title,
        opportunity_type=opportunity_type,
        summary=summary,
        presentation_bucket=presentation_bucket,
        supporting_evidence=[item if isinstance(item, Evidence) else Evidence.from_dict(item) for item in supporting_evidence],
        opposing_evidence=[item if isinstance(item, Evidence) else Evidence.from_dict(item) for item in opposing_evidence],
        invalidation_conditions=invalidation_conditions,
        experience_fit=experience_fit,
        minimum_experiment=experiment if isinstance(experiment, Experiment) else Experiment.from_dict(experiment),
        continue_criteria=continue_criteria,
        stop_criteria=stop_criteria,
        scores=scores if isinstance(scores, OpportunityScores) else OpportunityScores.from_dict(scores),
    )
    return _store().save_opportunity(opportunity)


@mcp.tool()
def list_opportunities(status: OpportunityStatus | None = None) -> list[dict[str, Any]]:
    """List private opportunity cards sorted by deterministic score."""
    return _store().list_opportunities(status)


@mcp.tool()
def record_experiment(
    opportunity_id: str,
    experiment_id: str,
    title: str,
    hypothesis: str,
    started_at: str,
    ends_at: str,
    cost_level: CostLevel,
    action: str,
    success_metric: str,
    continue_criteria: list[str],
    stop_criteria: list[str],
    evidence: list[Evidence],
) -> dict[str, Any]:
    """Persist a 1-14 day experiment and its supporting or opposing evidence."""
    experiment = Experiment(
        title=title,
        hypothesis=hypothesis,
        starts_at=started_at,
        ends_at=ends_at,
        cost_level=cost_level,
        action=action,
        success_metric=success_metric,
        continue_criteria=continue_criteria,
        stop_criteria=stop_criteria,
    )
    return _store().record_experiment(
        experiment_id=experiment_id,
        opportunity_id=opportunity_id,
        experiment=experiment,
        evidence=[item.to_dict() if isinstance(item, Evidence) else item for item in evidence],
    )


@mcp.tool()
def set_direction(
    direction_id: str,
    title: str,
    status: DirectionStatus,
    opportunity_ids: list[str],
    rationale: str,
    next_review_at: str,
) -> dict[str, Any]:
    """Set one direction while enforcing observe/validate/active capacity."""
    return _store().set_direction(
        Direction(direction_id, title, status, opportunity_ids, rationale, next_review_at)
    )


@mcp.tool()
def get_portfolio() -> dict[str, Any]:
    """Return direction contents, current counts, and hard capacities."""
    return _store().get_portfolio()


@mcp.tool()
def record_tech_state(
    technology: str,
    known_latest: str,
    recommended_stable: str,
    maturity: TechMaturity,
    official_sources: list[str],
    observed_at: str,
    review_due_at: str,
    confidence: Confidence,
    stable_gates: StableGates,
    rollback_path: str,
) -> dict[str, Any]:
    """Record latest and stable versions without unsafe automatic promotion."""
    state = TechState(
        technology=technology,
        known_latest=known_latest,
        recommended_stable=recommended_stable,
        maturity=maturity,
        official_sources=official_sources,
        observed_at=observed_at,
        review_due_at=review_due_at,
        confidence=confidence,
        stable_gates=stable_gates if isinstance(stable_gates, StableGates) else StableGates.from_dict(stable_gates),
        rollback_path=rollback_path,
    )
    return _store().record_tech_state(state)


@mcp.tool()
def save_review(
    period: ReviewPeriod,
    title: str,
    summary: str,
    opportunity_ids: list[str],
    surprise_signal: str,
    presentation_counts: PresentationCounts,
    proposed_experiment_ids: list[str],
    facts: list[str],
    inferences: list[str],
    hypotheses: list[str],
    created_at: str,
) -> dict[str, Any]:
    """Persist a review only when surprise and diversity invariants pass."""
    identifier = period + "-" + hashlib.sha256(f"{title}\0{created_at}".encode("utf-8")).hexdigest()[:12]
    review = Review(
        id=identifier,
        period=period,
        title=title,
        summary=summary,
        opportunity_ids=opportunity_ids,
        surprise_signal=surprise_signal,
        presentation_counts=presentation_counts,
        proposed_experiment_ids=proposed_experiment_ids,
        facts=facts,
        inferences=inferences,
        hypotheses=hypotheses,
        created_at=created_at,
    )
    return _store().save_review(review)


@mcp.tool()
def system_status() -> dict[str, Any]:
    """Return counts and portfolio invariants without private record contents."""
    return _store().system_status()


@mcp.tool()
def render_review(review_id: str | None = None, latest: bool = False) -> str:
    """Render a saved review as Chinese Markdown."""
    return render_review_markdown(_store(), review_id, latest=latest)


if __name__ == "__main__":
    mcp.run(transport="stdio")
