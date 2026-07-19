"""Read-only access to private Opportunity OS state."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from opportunity_os.dashboard.schemas import PrivateStateSnapshot
from opportunity_os.store import DIRECTION_CAPACITY


class PrivateStateReadRepository:
    """Read aggregate dashboard metadata without initializing or mutating state."""

    def __init__(self, home: str | Path) -> None:
        self.home = Path(home).expanduser().resolve()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _records(self, directory: str) -> list[dict[str, Any]]:
        path = self.home / directory
        if not path.is_dir():
            return []
        return [self._read_json(item) for item in sorted(path.glob("*.json"))]

    def _portfolio_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in DIRECTION_CAPACITY}
        path = self.home / "portfolio.json"
        if not path.is_file():
            return counts
        for direction in self._read_json(path).get("directions", []):
            status = direction.get("status")
            if status in counts:
                counts[status] += 1
        return counts

    @staticmethod
    def _latest_review(reviews: list[dict[str, Any]]) -> tuple[str | None, str | None, datetime | None]:
        if not reviews:
            return None, None, None
        latest = max(reviews, key=lambda item: (item.get("created_at", ""), item.get("id", "")))
        created_at = latest.get("created_at")
        return latest.get("id"), latest.get("period"), datetime.fromisoformat(created_at) if created_at else None

    def _event_cursor(self) -> int:
        path = self.home / "events.jsonl"
        if not path.is_file():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def snapshot(self) -> PrivateStateSnapshot:
        """Return only aggregate counts and review/event metadata."""
        opportunities = self._records("opportunities")
        experiments = self._records("experiments")
        reviews = self._records("reviews")
        tech_states = self._records("tech_states")
        latest_review_id, latest_review_period, latest_review_at = self._latest_review(reviews)
        today = date.today()
        overdue_tech_states = sum(
            date.fromisoformat(state["review_due_at"]) <= today
            for state in tech_states
            if state.get("review_due_at")
        )
        return PrivateStateSnapshot(
            opportunity_count=len(opportunities),
            experiment_count=len(experiments),
            review_count=len(reviews),
            tech_state_count=len(tech_states),
            portfolio_counts=self._portfolio_counts(),
            portfolio_capacity=dict(DIRECTION_CAPACITY),
            latest_review_id=latest_review_id,
            latest_review_period=latest_review_period,
            latest_review_at=latest_review_at,
            overdue_tech_states=overdue_tech_states,
            event_cursor=self._event_cursor(),
        )
