"""Stable, aggregate-only data contracts for dashboard readers."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    opportunity_state_counts: dict[str, int] = field(default_factory=dict)
    active_experiments: int = 0
    pending_candidates: int = 0
    dossier_count: int = 0
    rejected_count: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    user_outcome_counts: dict[str, int] = field(default_factory=dict)
    run_failures: int = 0
    run_timeouts: int = 0
    delivery_errors: int = 0
    today_collected: int = 0
    week_collected: int = 0
    today_published: int = 0
    week_published: int = 0
    conversion_rate: float = 0.0
    citation_coverage: float | None = None
    numeric_citation_coverage: float | None = None
    broken_links: int | None = None
    duplicate_candidates: int | None = None


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
    opportunity_state_counts: dict[str, int] = Field(default_factory=dict)
    pipeline_metrics: dict[str, int | float | str | None] = Field(default_factory=dict)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    user_outcome_counts: dict[str, int] = Field(default_factory=dict)
