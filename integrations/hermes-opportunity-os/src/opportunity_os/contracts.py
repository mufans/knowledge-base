"""Versioned contracts shared by OpenClaw, Hermes and the Knowledge Compiler."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timezone
from typing import Annotated, Any, ClassVar, Literal, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opportunity_os.errors import ValidationError


SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,119}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TAG_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
PageType = Literal["concept", "entity", "source", "synthesis"]
ClaimType = Literal["fact", "inference", "hypothesis"]
EvidenceStance = Literal["support", "oppose"]


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: object) -> str:
    rendered = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    normalized = "\0".join(canonical_json(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:20]}"


def _as_utc_datetime(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(value), time.min, tzinfo=timezone.utc)
            except ValueError as error:
                raise ValueError(f"{label} must be ISO 8601") from error
    else:
        raise ValueError(f"{label} must be ISO 8601")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ContractBase(BaseModel):
    """Metadata every cross-component record must carry."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal[1] = SCHEMA_VERSION
    id: str
    source_url: str
    collected_at: datetime
    content_hash: str
    run_id: str

    @field_validator("id", "run_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("must be a stable lowercase identifier")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("source_url must not contain credentials")
        return value

    @field_validator("collected_at", mode="before")
    @classmethod
    def validate_collected_at(cls, value: object) -> datetime:
        return _as_utc_datetime(value, "collected_at")

    @field_validator("content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not HASH_PATTERN.fullmatch(value):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        return value


class SignalContract(ContractBase):
    title: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=80)
    relative_path: str = Field(min_length=1, max_length=1000)
    excerpt: str = Field(min_length=1, max_length=4000)
    source_urls: tuple[str, ...] = Field(min_length=1)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if value.startswith(("/", "~")) or ".." in value.split("/") or not value.startswith("raw/inbox/"):
            raise ValueError("relative_path must remain inside raw/inbox")
        return value

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            ContractBase.validate_source_url(value)
        if len(set(values)) != len(values):
            raise ValueError("source_urls must be unique")
        return values

    @model_validator(mode="after")
    def primary_source_is_listed(self) -> "SignalContract":
        if self.source_url not in self.source_urls:
            raise ValueError("source_url must be included in source_urls")
        return self


class EvidenceContract(ContractBase):
    claim_type: ClaimType
    stance: EvidenceStance
    claim: str = Field(min_length=1, max_length=8000)
    source_name: str = Field(min_length=1, max_length=500)
    source_tier: Literal["official", "primary", "secondary", "community"]
    locator: str | None = Field(default=None, max_length=500)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: str
    claim_type: ClaimType
    text: str = Field(min_length=1, max_length=8000)
    evidence_ids: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("claim id must be stable")
        return value


class AnalysisContract(ContractBase):
    signal_ids: tuple[str, ...] = Field(min_length=1)
    claims: tuple[Claim, ...] = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...] = Field(min_length=1)
    opposing_evidence_ids: tuple[str, ...] = Field(min_length=1)
    conflicts: tuple[str, ...] = ()
    knowledge_gaps: tuple[str, ...] = ()
    collection_questions: tuple[str, ...] = ()


class WikiCandidateContract(ContractBase):
    page_type: PageType
    action: Literal["create", "update", "reject"]
    title: str = Field(min_length=1, max_length=500)
    tags: tuple[str, ...] = Field(min_length=2, max_length=5)
    target_path: str | None = Field(default=None, max_length=1000)
    analysis_id: str
    claims: tuple[Claim, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    opposing_evidence_ids: tuple[str, ...] = Field(min_length=1)
    sections: Mapping[str, str]
    novelty_summary: str = Field(min_length=1, max_length=4000)
    novelty_score: float = Field(ge=0, le=1)
    purpose_relevance: float = Field(ge=0, le=1)
    actionable_next_step: str = Field(min_length=1, max_length=4000)
    human_decision: Literal["pending", "approved", "rejected"] = "pending"

    @field_validator("analysis_id")
    @classmethod
    def validate_analysis_id(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("analysis_id must be stable")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not TAG_PATTERN.fullmatch(value) for value in values):
            raise ValueError("tags must be 2-5 English technical identifiers")
        if len(set(values)) != len(values):
            raise ValueError("tags must be unique")
        return values

    @field_validator("target_path")
    @classmethod
    def validate_target_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith(("/", "~")) or ".." in value.split("/") or not value.startswith("wiki/"):
            raise ValueError("target_path must remain inside wiki")
        if not value.endswith(".md"):
            raise ValueError("target_path must end in .md")
        return value

    @model_validator(mode="after")
    def action_matches_target(self) -> "WikiCandidateContract":
        if self.action == "update" and self.target_path is None:
            raise ValueError("update candidates require target_path")
        return self


class ReviewResultContract(ContractBase):
    candidate_id: str
    decision: Literal["publish", "needs_human", "reject"]
    reasons: tuple[str, ...]
    validation_errors: tuple[str, ...] = ()
    fact_citation_coverage: float = Field(ge=0, le=1)
    numeric_citation_coverage: float = Field(ge=0, le=1)
    broken_links: tuple[str, ...] = ()
    duplicate_target: str | None = None

    @field_validator("candidate_id")
    @classmethod
    def validate_candidate_id(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("candidate_id must be stable")
        return value


class ExperimentContract(ContractBase):
    opportunity_id: str
    hypothesis: str = Field(min_length=1, max_length=4000)
    action: str = Field(min_length=1, max_length=4000)
    success_metric: str = Field(min_length=1, max_length=2000)
    starts_at: date
    ends_at: date
    continue_criteria: tuple[str, ...] = Field(min_length=1)
    stop_criteria: tuple[str, ...] = Field(min_length=1)
    status: Literal["proposed", "active", "completed", "rejected", "archived"] = "proposed"

    @model_validator(mode="after")
    def validate_duration(self) -> "ExperimentContract":
        duration = (self.ends_at - self.starts_at).days
        if not 1 <= duration <= 14:
            raise ValueError("experiment duration must be between 1 and 14 days")
        return self


class UserOutcomeContract(ContractBase):
    subject_id: str
    subject_type: Literal["candidate", "experiment", "opportunity", "wiki"]
    outcome: Literal["adopted", "ignored", "rejected", "revised"]
    rationale: str = Field(min_length=1, max_length=4000)
    decided_at: datetime

    @field_validator("decided_at", mode="before")
    @classmethod
    def validate_decided_at(cls, value: object) -> datetime:
        return _as_utc_datetime(value, "decided_at")


Contract = Annotated[
    SignalContract
    | EvidenceContract
    | AnalysisContract
    | WikiCandidateContract
    | ReviewResultContract
    | ExperimentContract
    | UserOutcomeContract,
    Field(discriminator=None),
]

CONTRACT_TYPES: dict[str, type[ContractBase]] = {
    "signal": SignalContract,
    "evidence": EvidenceContract,
    "analysis": AnalysisContract,
    "wiki_candidate": WikiCandidateContract,
    "review_result": ReviewResultContract,
    "experiment": ExperimentContract,
    "user_outcome": UserOutcomeContract,
}


def _legacy_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    claim = payload.get("claim") or payload.get("fact") or payload.get("description") or payload.get("text")
    source_url = payload.get("source_url") or payload.get("source") or payload.get("url")
    observed = payload.get("observed_at") or payload.get("collected_at")
    if not all(isinstance(value, str) and value.strip() for value in (claim, source_url, observed)):
        raise ValidationError("legacy evidence is missing claim, source_url or observed_at")
    normalized = {
        "claim_type": payload.get("claim_type", payload.get("kind", "fact")),
        "stance": payload.get("stance", "support"),
        "claim": claim,
        "source_name": payload.get("source_name") or urlsplit(source_url).netloc,
        "source_tier": payload.get("source_tier", "secondary"),
        "locator": payload.get("locator"),
    }
    return {
        "schema_version": 1,
        "id": payload.get("id") or stable_id("evidence", normalized, source_url, observed),
        "source_url": source_url,
        "collected_at": observed,
        "content_hash": payload.get("content_hash") or content_hash(normalized),
        "run_id": payload.get("run_id") or stable_id("run", "legacy", observed),
        **normalized,
    }


def _legacy_signal(payload: Mapping[str, Any]) -> dict[str, Any]:
    urls = payload.get("source_urls") or ([payload["source_url"]] if payload.get("source_url") else [])
    if not isinstance(urls, (list, tuple)) or not urls:
        raise ValidationError("legacy signal is missing source_urls")
    core = {
        "title": payload.get("title"),
        "category": payload.get("category", "other"),
        "relative_path": payload.get("relative_path"),
        "excerpt": payload.get("excerpt"),
        "source_urls": list(urls),
    }
    if not all(isinstance(core[key], str) and str(core[key]).strip() for key in ("title", "relative_path", "excerpt")):
        raise ValidationError("legacy signal is missing title, relative_path or excerpt")
    collected = payload.get("collected_at")
    if not isinstance(collected, str) or not collected:
        raise ValidationError("legacy signal is missing collected_at")
    return {
        "schema_version": 1,
        "id": payload.get("id") or stable_id("signal", core),
        "source_url": urls[0],
        "collected_at": collected,
        "content_hash": payload.get("content_hash") or content_hash(core),
        "run_id": payload.get("run_id") or stable_id("run", "legacy", collected),
        **core,
    }


LEGACY_MIGRATORS: dict[str, Any] = {
    "evidence": _legacy_evidence,
    "signal": _legacy_signal,
}


def load_contract(kind: str, payload: Mapping[str, Any]) -> ContractBase:
    """Validate v1, migrate supported v0 inputs, and reject unknown versions."""

    model = CONTRACT_TYPES.get(kind)
    if model is None:
        raise ValidationError(f"unknown contract kind: {kind}")
    version = payload.get("schema_version", 0)
    if version == 0:
        migrator = LEGACY_MIGRATORS.get(kind)
        if migrator is None:
            raise ValidationError(f"{kind} requires an explicit v0 migration")
        payload = migrator(payload)
    elif version != SCHEMA_VERSION:
        raise ValidationError(f"unsupported {kind} schema_version: {version}")
    try:
        return model.model_validate(payload)
    except Exception as error:
        raise ValidationError(f"{kind} validation failed: {error}") from error
