"""Explicit, auditable lifecycle for Hermes opportunities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opportunity_os.contracts import ID_PATTERN
from opportunity_os.errors import ValidationError


OpportunityState = Literal[
    "candidate", "researched", "validated", "active", "completed", "rejected", "archived"
]

LEGACY_STATES = {
    "observing": "researched",
    "validating": "validated",
    "paused": "validated",
    "stopped": "archived",
}

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "candidate": frozenset({"researched", "rejected", "archived"}),
    "researched": frozenset({"validated", "rejected", "archived"}),
    "validated": frozenset({"active", "rejected", "archived"}),
    "active": frozenset({"completed", "rejected", "archived"}),
    "completed": frozenset({"archived"}),
    "rejected": frozenset({"archived"}),
    "archived": frozenset(),
}


def normalize_state(value: str) -> str:
    return LEGACY_STATES.get(value, value)


class StateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal[1] = 1
    id: str
    opportunity_id: str
    from_state: OpportunityState
    to_state: OpportunityState
    trigger_reason: str = Field(min_length=1, max_length=4000)
    new_evidence_ids: tuple[str, ...] = ()
    opposing_evidence_ids: tuple[str, ...] = ()
    next_experiment_id: str | None = None
    user_decision: str | None = Field(default=None, max_length=4000)
    automatic_rule: str | None = Field(default=None, max_length=4000)
    occurred_at: datetime
    run_id: str

    @field_validator("id", "opportunity_id", "run_id", "next_experiment_id")
    @classmethod
    def stable_ids(cls, value: str | None) -> str | None:
        if value is not None and not ID_PATTERN.fullmatch(value):
            raise ValueError("transition identifiers must be stable lowercase IDs")
        return value

    @field_validator("occurred_at", mode="before")
    @classmethod
    def utc_time(cls, value: object) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            raise ValueError("occurred_at must be ISO 8601")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def transition_is_complete(self) -> "StateTransition":
        allowed = ALLOWED_TRANSITIONS[self.from_state]
        if self.to_state not in allowed:
            raise ValueError(f"invalid opportunity transition: {self.from_state} -> {self.to_state}")
        if not self.user_decision and not self.automatic_rule:
            raise ValueError("transition requires user_decision or automatic_rule")
        if self.to_state in {"researched", "validated", "active", "completed"}:
            if not self.new_evidence_ids:
                raise ValueError(f"{self.to_state} requires new evidence")
            if not self.opposing_evidence_ids:
                raise ValueError(f"{self.to_state} requires opposing evidence")
        if self.to_state in {"validated", "active"} and not self.next_experiment_id:
            raise ValueError(f"{self.to_state} requires next_experiment_id")
        return self


def validate_transition(payload: dict[str, object]) -> StateTransition:
    try:
        return StateTransition.model_validate(payload)
    except ValueError as error:
        raise ValidationError(str(error)) from error
