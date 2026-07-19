"""Typed, bounded, read-only domain queries for the OpenClaw Skill boundary."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from opportunity_os.sanitizer import sanitize_public


MAX_STATE_BYTES = 1_048_576
MAX_STATE_FILES_PER_DIRECTORY = 256
MAX_STATE_FILES_TOTAL = 512
MAX_STATE_BYTES_TOTAL = 8 * 1_048_576
MAX_QUERY_OUTPUT_BYTES = 64 * 1_024
QUERY_NAMES = frozenset(
    {"status", "latest_review", "directions", "opportunities", "learning"}
)


class DomainQueryError(ValueError):
    """A stable domain boundary error containing no filesystem details."""


@dataclass(slots=True)
class _ReadBudget:
    files: int = 0
    bytes: int = 0

    def add(self, size: int) -> None:
        self.files += 1
        self.bytes += size
        if self.files > MAX_STATE_FILES_TOTAL:
            raise DomainQueryError("state_file_limit")
        if self.bytes > MAX_STATE_BYTES_TOTAL:
            raise DomainQueryError("state_byte_limit")


def _directory_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _open_directory(path: str | Path, *, dir_fd: int | None = None) -> int:
    try:
        descriptor = os.open(path, _directory_flags(), dir_fd=dir_fd)
    except OSError as error:
        raise DomainQueryError("state_unavailable") from error
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise DomainQueryError("state_unavailable")
    return descriptor


def _read_object_at(directory_fd: int, name: str, budget: _ReadBudget) -> dict[str, object]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise DomainQueryError("state_unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_STATE_BYTES:
            raise DomainQueryError("invalid_state_file")
        budget.add(metadata.st_size)
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


def _objects_at(home_fd: int, directory_name: str, budget: _ReadBudget) -> list[dict[str, object]]:
    try:
        directory_fd = _open_directory(directory_name, dir_fd=home_fd)
    except DomainQueryError as error:
        if error.__cause__ is not None and getattr(error.__cause__, "errno", None) == 2:
            return []
        raise
    try:
        names: list[str] = []
        try:
            with os.scandir(directory_fd) as entries:
                for entry in entries:
                    if not entry.name.endswith(".json") or not entry.is_file(follow_symlinks=False):
                        continue
                    names.append(entry.name)
                    if len(names) > MAX_STATE_FILES_PER_DIRECTORY:
                        raise DomainQueryError("state_file_limit")
        except OSError as error:
            raise DomainQueryError("state_unavailable") from error
        return [_read_object_at(directory_fd, name, budget) for name in sorted(names)]
    finally:
        os.close(directory_fd)


def _fields(value: dict[str, object], names: tuple[str, ...]) -> dict[str, object]:
    return {name: value[name] for name in names if name in value}


def _bounded_public(payload: dict[str, object]) -> dict[str, object]:
    sanitized = sanitize_public(payload)
    if not isinstance(sanitized, dict):
        raise DomainQueryError("invalid_state_schema")
    rendered = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    if len(rendered.encode("utf-8")) + 1 > MAX_QUERY_OUTPUT_BYTES:
        raise DomainQueryError("query_output_too_large")
    return sanitized


class DomainQueryService:
    """Expose a bounded Opportunity OS projection without control authority."""

    def __init__(self, home: str | Path) -> None:
        self.home = Path(os.path.abspath(Path(home).expanduser()))

    def query(self, name: str) -> dict[str, object]:
        if name not in QUERY_NAMES:
            raise DomainQueryError("unsupported_query")
        home_fd = _open_directory(self.home)
        try:
            budget = _ReadBudget()
            portfolio = _read_object_at(home_fd, "portfolio.json", budget)
            opportunities = _objects_at(home_fd, "opportunities", budget)
            reviews = _objects_at(home_fd, "reviews", budget)
            tech_states = _objects_at(home_fd, "tech_states", budget)
        finally:
            os.close(home_fd)
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
        return _bounded_public(payload)
