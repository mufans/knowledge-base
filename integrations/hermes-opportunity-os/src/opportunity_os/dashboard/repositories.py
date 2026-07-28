"""Read-only access to private Opportunity OS state."""

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from opportunity_os.dashboard.schemas import PrivateStateSnapshot
from opportunity_os.store import DIRECTION_CAPACITY
from opportunity_os.state_machine import normalize_state


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

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _compiler_metrics(self) -> dict[str, Any]:
        runs = self._records("compiler/runs")
        dossiers = self._records("compiler/dossiers")
        rejections = self._records("compiler/rejections")
        now = datetime.now(timezone.utc)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        today_collected = week_collected = today_published = week_published = 0
        failures = timeouts = delivery_errors = 0
        reasons: Counter[str] = Counter()
        for run in runs:
            started = self._parse_time(run.get("started_at"))
            input_count = int(run.get("input_reviews", run.get("input_count", 0)) or 0)
            published = int(run.get("published", run.get("output_count", 0)) or 0)
            if started and started.date() == today:
                today_collected += input_count
                today_published += published
            if started and started.date() >= week_start:
                week_collected += input_count
                week_published += published
            if run.get("status") not in {"success", "skipped_duplicate"}:
                failures += 1
            error = str(run.get("error_class", ""))
            timeouts += int("timeout" in error or bool(run.get("timeout")))
            delivery_errors += int("delivery" in error or bool(run.get("delivery_error")))
            for reason, count in (run.get("rejection_reasons") or {}).items():
                reasons[str(reason)] += int(count)
        for rejection in rejections:
            for reason in rejection.get("reasons", []):
                reasons[str(reason)] += 1
        quality_path = self.home / "compiler" / "quality" / "latest.json"
        quality = self._read_json(quality_path) if quality_path.is_file() else {}
        quality_metrics = (
            quality.get("metrics", {}) if isinstance(quality.get("metrics"), dict) else {}
        )
        return {
            "dossier_count": len(dossiers),
            "rejected_count": len(rejections),
            "rejection_reasons": dict(reasons.most_common(8)),
            "run_failures": failures,
            "run_timeouts": timeouts,
            "delivery_errors": delivery_errors,
            "today_collected": today_collected,
            "week_collected": week_collected,
            "today_published": today_published,
            "week_published": week_published,
            "conversion_rate": round(week_published / week_collected, 4) if week_collected else 0.0,
            "citation_coverage": quality_metrics.get("fact_citation_coverage"),
            "numeric_citation_coverage": quality_metrics.get("numeric_citation_coverage"),
            "broken_links": quality_metrics.get("broken_links"),
            "duplicate_candidates": quality_metrics.get("duplicate_titles"),
        }

    def snapshot(self) -> PrivateStateSnapshot:
        """Return only aggregate counts and review/event metadata."""
        opportunities = self._records("opportunities")
        experiments = self._records("experiments")
        reviews = self._records("reviews")
        tech_states = self._records("tech_states")
        candidates = self._records("wiki_candidates")
        outcomes = self._records("user_outcomes")
        compiler = self._compiler_metrics()
        state_counts = Counter(
            normalize_state(str(item.get("status", "candidate"))) for item in opportunities
        )
        outcome_counts = Counter(str(item.get("outcome", "unknown")) for item in outcomes)
        active_experiments = sum(
            item.get("status") == "active"
            or (isinstance(item.get("experiment"), dict) and item["experiment"].get("status") == "active")
            for item in experiments
        )
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
            opportunity_state_counts=dict(state_counts),
            active_experiments=active_experiments,
            pending_candidates=sum(
                item.get("human_decision", "pending") == "pending" for item in candidates
            ),
            dossier_count=compiler["dossier_count"],
            rejected_count=compiler["rejected_count"],
            rejection_reasons=compiler["rejection_reasons"],
            user_outcome_counts=dict(outcome_counts),
            run_failures=compiler["run_failures"],
            run_timeouts=compiler["run_timeouts"],
            delivery_errors=compiler["delivery_errors"],
            today_collected=compiler["today_collected"],
            week_collected=compiler["week_collected"],
            today_published=compiler["today_published"],
            week_published=compiler["week_published"],
            conversion_rate=compiler["conversion_rate"],
            citation_coverage=compiler["citation_coverage"],
            numeric_citation_coverage=compiler["numeric_citation_coverage"],
            broken_links=compiler["broken_links"],
            duplicate_candidates=compiler["duplicate_candidates"],
        )
