from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from opportunity_os.dashboard.read_model import DashboardReadModel
from opportunity_os.dashboard.schemas import ComponentHealth, PrivateStateSnapshot


@dataclass
class FakePrivateRepository:
    def snapshot(self) -> PrivateStateSnapshot:
        return PrivateStateSnapshot(
            opportunity_count=3,
            experiment_count=2,
            review_count=1,
            tech_state_count=4,
            portfolio_counts={"observe": 1, "validate": 1, "active": 1},
            portfolio_capacity={"observe": 5, "validate": 2, "active": 1},
            latest_review_id="private-weekly-review",
            latest_review_period="weekly",
            latest_review_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            overdue_tech_states=2,
            event_cursor=9,
        )


@dataclass
class FakeProbe:
    component: str

    def check(self) -> ComponentHealth:
        return ComponentHealth(
            component=self.component,
            status="healthy",
            checked_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            last_success_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            duration_ms=5,
        )


def test_read_model_never_exposes_paths_or_directions() -> None:
    private_repo = FakePrivateRepository()
    fake_probes = [FakeProbe("openclaw"), FakeProbe("hermes")]

    payload = DashboardReadModel(private_repo, fake_probes).snapshot().model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False)

    assert "/Users/" not in rendered
    assert "directions" not in rendered
    assert payload["opportunity_counts"] == {
        "opportunities": 3,
        "experiments": 2,
        "reviews": 1,
        "tech_states": 4,
    }
    assert payload["pending_approvals"] == 0
    assert payload["active_incidents"] == 0
