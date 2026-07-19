"""Typed, read-only domain queries for the OpenClaw Skill boundary."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from opportunity_os.sanitizer import sanitize_public


MAX_STATE_BYTES = 1_048_576
QUERY_NAMES = frozenset(
    {"status", "latest_review", "directions", "opportunities", "learning"}
)


class DomainQueryError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, object]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_STATE_BYTES:
            raise DomainQueryError("invalid_state_file")
        data = os.read(descriptor, MAX_STATE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > MAX_STATE_BYTES:
        raise DomainQueryError("invalid_state_file")
    try:
        value = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DomainQueryError("invalid_state_json") from error
    if not isinstance(value, dict):
        raise DomainQueryError("invalid_state_schema")
    return value


def _objects(directory: Path) -> list[dict[str, object]]:
    if not directory.is_dir():
        return []
    values: list[dict[str, object]] = []
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        if not entry.name.endswith(".json") or not entry.is_file(follow_symlinks=False):
            continue
        values.append(_read_object(Path(entry.path)))
    return values


def _fields(value: dict[str, object], names: tuple[str, ...]) -> dict[str, object]:
    return {name: value[name] for name in names if name in value}


class DomainQueryService:
    """Expose bounded Opportunity OS knowledge without system-control authority."""

    def __init__(self, home: str | Path) -> None:
        self.home = Path(home).expanduser().resolve()

    def query(self, name: str) -> dict[str, object]:
        if name not in QUERY_NAMES:
            raise DomainQueryError("unsupported_query")
        portfolio = _read_object(self.home / "portfolio.json")
        opportunities = _objects(self.home / "opportunities")
        reviews = _objects(self.home / "reviews")
        tech_states = _objects(self.home / "tech_states")
        latest = max(
            reviews,
            key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))),
            default=None,
        )

        if name == "status":
            directions = portfolio.get("directions", [])
            if not isinstance(directions, list):
                raise DomainQueryError("invalid_state_schema")
            payload: dict[str, object] = {
                "opportunity_count": len(opportunities),
                "review_count": len(reviews),
                "technology_count": len(tech_states),
                "direction_count": len(directions),
                "latest_review_at": latest.get("created_at") if latest else None,
            }
        elif name == "latest_review":
            payload = {
                "review": _fields(
                    latest,
                    (
                        "id", "period", "title", "summary", "surprise_signal",
                        "opportunity_ids", "facts", "inferences", "hypotheses",
                        "proposed_experiment_ids", "created_at",
                    ),
                ) if latest else None
            }
        elif name == "directions":
            raw = portfolio.get("directions", [])
            if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
                raise DomainQueryError("invalid_state_schema")
            payload = {
                "directions": [
                    _fields(
                        item,
                        ("id", "title", "status", "opportunity_ids", "rationale", "next_review_at"),
                    )
                    for item in raw
                ]
            }
        elif name == "opportunities":
            payload = {
                "opportunities": [
                    _fields(
                        item,
                        (
                            "id", "title", "opportunity_type", "summary",
                            "presentation_bucket", "status", "total_score",
                            "invalidation_conditions", "continue_criteria", "stop_criteria",
                        ),
                    )
                    for item in opportunities[:100]
                ]
            }
        else:
            payload = {
                "review_learning": _fields(
                    latest, ("facts", "inferences", "hypotheses", "created_at")
                ) if latest else None,
                "technologies": [
                    _fields(
                        item,
                        (
                            "technology", "known_latest", "recommended_stable",
                            "maturity", "official_sources", "observed_at",
                            "review_due_at", "confidence",
                        ),
                    )
                    for item in tech_states[:100]
                ],
            }
        return sanitize_public(payload)  # type: ignore[return-value]
