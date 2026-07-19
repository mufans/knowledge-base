"""Stable, aggregate-only data contracts for dashboard readers."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PrivateStateSnapshot:
    """Aggregate private-state metadata without direction or review content."""

    opportunity_count: int
    experiment_count: int
    review_count: int
    tech_state_count: int
    portfolio_counts: dict[str, int]
    portfolio_capacity: dict[str, int]
    latest_review_id: str | None
    latest_review_period: str | None
    latest_review_at: datetime | None
    overdue_tech_states: int
    event_cursor: int
