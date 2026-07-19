"""Stable, aggregate-only data contracts for dashboard readers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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


class ComponentHealth(BaseModel):
    """Public-safe outcome of one fixed, read-only runtime check."""

    component: Literal["openclaw", "hermes", "opportunity_os", "dashboard", "ngrok", "knowledge_publish"]
    status: Literal["healthy", "degraded", "down", "unknown"]
    checked_at: datetime
    last_success_at: datetime | None = None
    duration_ms: int
    error_code: str | None = None


class DashboardSnapshot(BaseModel):
    """Aggregate dashboard payload with no private-state contents or paths."""

    generated_at: datetime
    components: list[ComponentHealth]
    opportunity_counts: dict[str, int]
    portfolio_counts: dict[str, int]
    portfolio_capacity: dict[str, int]
    latest_review_at: datetime | None
    overdue_tech_states: int
    pending_approvals: int
    active_incidents: int
