"""Aggregate private-state metadata and runtime checks into dashboard output."""

from datetime import datetime, timezone
from typing import Iterable, Protocol

from opportunity_os.dashboard.probes import RuntimeProbe
from opportunity_os.dashboard.schemas import DashboardSnapshot, PrivateStateSnapshot


class PrivateStateSnapshotReader(Protocol):
    """The minimal, aggregate-only repository surface required by the dashboard."""

    def snapshot(self) -> PrivateStateSnapshot: ...


class DashboardReadModel:
    """Build a public-safe dashboard snapshot from aggregate-only inputs."""

    def __init__(self, private_repository: PrivateStateSnapshotReader, probes: Iterable[RuntimeProbe]) -> None:
        self._private_repository = private_repository
        self._probes = tuple(probes)

    def snapshot(self) -> DashboardSnapshot:
        private_state = self._private_repository.snapshot()
        components = [probe.check() for probe in self._probes]
        return DashboardSnapshot(
            generated_at=datetime.now(timezone.utc),
            components=components,
            opportunity_counts={
                "opportunities": private_state.opportunity_count,
                "experiments": private_state.experiment_count,
                "reviews": private_state.review_count,
                "tech_states": private_state.tech_state_count,
            },
            portfolio_counts=dict(private_state.portfolio_counts),
            portfolio_capacity=dict(private_state.portfolio_capacity),
            latest_review_at=private_state.latest_review_at,
            overdue_tech_states=private_state.overdue_tech_states,
            pending_approvals=0,
            active_incidents=sum(component.status in {"degraded", "down"} for component in components),
            opportunity_state_counts=dict(private_state.opportunity_state_counts),
            pipeline_metrics={
                "active_experiments": private_state.active_experiments,
                "pending_candidates": private_state.pending_candidates,
                "dossiers": private_state.dossier_count,
                "rejected": private_state.rejected_count,
                "run_failures": private_state.run_failures,
                "run_timeouts": private_state.run_timeouts,
                "delivery_errors": private_state.delivery_errors,
                "today_collected": private_state.today_collected,
                "week_collected": private_state.week_collected,
                "today_published": private_state.today_published,
                "week_published": private_state.week_published,
                "conversion_rate": private_state.conversion_rate,
                "citation_coverage": private_state.citation_coverage,
                "numeric_citation_coverage": private_state.numeric_citation_coverage,
                "broken_links": private_state.broken_links,
                "duplicate_candidates": private_state.duplicate_candidates,
            },
            rejection_reasons=dict(private_state.rejection_reasons),
            user_outcome_counts=dict(private_state.user_outcome_counts),
        )
