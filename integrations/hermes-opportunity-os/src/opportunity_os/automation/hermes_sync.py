"""Hermes private-state to Knowledge Compiler dossier bridge.

The bridge never writes ``raw/`` or ``wiki/``. It validates Hermes artifacts,
materializes traceable research dossiers in private state, and records every
rejection as an observable successful outcome.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from opportunity_os.contracts import (
    AnalysisContract,
    Claim,
    EvidenceContract,
    content_hash,
    load_contract,
    stable_id,
)
from opportunity_os.errors import BoundaryError, ValidationError
from opportunity_os.models import Opportunity, Review


@dataclass(frozen=True, slots=True)
class HermesSyncRun:
    run_id: str
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    input_reviews: int
    dossiers_written: int
    skipped_unchanged: int
    rejected: int
    rejection_reasons: dict[str, int]
    validation_errors: int
    published: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class HermesKnowledgeBridge:
    def __init__(
        self,
        private_home: str | Path,
        knowledge_root: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.private_home = Path(private_home).expanduser().resolve()
        self.knowledge_root = Path(knowledge_root).expanduser().resolve()
        if self.private_home == self.knowledge_root or self.private_home.is_relative_to(self.knowledge_root):
            raise BoundaryError("Hermes private state must remain outside the knowledge repository")
        if not (self.knowledge_root / "raw").is_dir() or not (self.knowledge_root / "wiki").is_dir():
            raise ValidationError("knowledge root is missing raw or wiki")
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValidationError("artifact JSON must be an object")
        return value

    @staticmethod
    def _safe_created_at(review: Review) -> str:
        return review.created_at

    def _review_paths(self, days: int) -> list[Path]:
        if days < 1 or days > 365:
            raise ValidationError("days must be between 1 and 365")
        cutoff = self.now().astimezone(timezone.utc) - timedelta(days=days)
        result: list[Path] = []
        for path in sorted((self.private_home / "reviews").glob("*.json")):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if modified >= cutoff:
                result.append(path)
        return result

    def _evidence(
        self,
        opportunity: Opportunity,
        run_id: str,
    ) -> tuple[list[EvidenceContract], list[str]]:
        valid: list[EvidenceContract] = []
        errors: list[str] = []
        for position, evidence in enumerate(
            [*opportunity.supporting_evidence, *opportunity.opposing_evidence]
        ):
            payload = evidence.to_dict()
            payload["run_id"] = run_id
            try:
                record = load_contract("evidence", payload)
            except ValidationError:
                errors.append(f"invalid_evidence_contract:{opportunity.id}:{position}")
                continue
            if not isinstance(record, EvidenceContract):
                errors.append(f"invalid_evidence_type:{opportunity.id}:{position}")
                continue
            valid.append(record)
        return valid, errors

    def _build_dossier(
        self,
        review_payload: dict[str, Any],
        run_id: str,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        try:
            review = Review.from_dict(review_payload)
        except (KeyError, TypeError, ValidationError, ValueError):
            return None, ["invalid_review_contract"]

        evidence_records: list[EvidenceContract] = []
        errors: list[str] = []
        for opportunity_id in review.opportunity_ids:
            path = self.private_home / "opportunities" / f"{opportunity_id}.json"
            if not path.is_file():
                errors.append(f"missing_opportunity:{opportunity_id}")
                continue
            try:
                opportunity = Opportunity.from_dict(self._read_object(path))
            except (json.JSONDecodeError, KeyError, TypeError, ValidationError, ValueError):
                errors.append(f"invalid_opportunity:{opportunity_id}")
                continue
            valid, invalid = self._evidence(opportunity, run_id)
            evidence_records.extend(valid)
            errors.extend(invalid)

        support = [record for record in evidence_records if record.stance == "support"]
        oppose = [record for record in evidence_records if record.stance == "oppose"]
        if not support:
            errors.append("missing_supporting_evidence")
        if not oppose:
            errors.append("missing_opposing_evidence")
        if errors:
            return None, errors

        claims = tuple(
            Claim(
                id=stable_id("claim", record.id, record.claim),
                claim_type=record.claim_type,
                text=record.claim,
                evidence_ids=(record.id,),
            )
            for record in evidence_records
        )
        analysis_core = {
            "review_id": review.id,
            "opportunity_ids": review.opportunity_ids,
            "evidence_ids": [record.id for record in evidence_records],
        }
        analysis = AnalysisContract(
            id=stable_id("analysis", analysis_core),
            source_url=support[0].source_url,
            collected_at=self._safe_created_at(review),
            content_hash=content_hash(analysis_core),
            run_id=run_id,
            signal_ids=tuple(stable_id("signal", record.source_url) for record in evidence_records),
            claims=claims,
            supporting_evidence_ids=tuple(record.id for record in support),
            opposing_evidence_ids=tuple(record.id for record in oppose),
            conflicts=tuple(review.inferences),
            knowledge_gaps=tuple(review.hypotheses),
            collection_questions=(),
        )
        return {
            "schema_version": 1,
            "review_id": review.id,
            "review_title": review.title,
            "analysis": analysis.model_dump(mode="json"),
            "evidence": [record.model_dump(mode="json") for record in evidence_records],
            "next_stage": "wiki_candidate",
        }, []

    def run(self, *, days: int = 14, run_id: str | None = None) -> HermesSyncRun:
        started = self.now().astimezone(timezone.utc)
        resolved_run_id = run_id or stable_id("run", "hermes-kb-sync", started.isoformat())
        started_monotonic = time.monotonic()
        paths = self._review_paths(days)
        written = skipped = rejected = validation_errors = 0
        reasons: dict[str, int] = {}
        dossier_dir = self.private_home / "compiler" / "dossiers"
        rejection_dir = self.private_home / "compiler" / "rejections"

        for path in paths:
            try:
                payload = self._read_object(path)
            except (OSError, json.JSONDecodeError, ValidationError):
                payload = {"id": path.stem}
                dossier = None
                errors = ["invalid_review_json"]
            else:
                dossier, errors = self._build_dossier(payload, resolved_run_id)
            review_id = str(payload.get("id") or path.stem)
            if dossier is None:
                rejected += 1
                validation_errors += len(errors)
                for reason in errors:
                    code = reason.split(":", 1)[0]
                    reasons[code] = reasons.get(code, 0) + 1
                self._atomic_json(
                    rejection_dir / f"{review_id}.json",
                    {
                        "schema_version": 1,
                        "review_id": review_id,
                        "run_id": resolved_run_id,
                        "status": "rejected",
                        "reasons": errors,
                        "at": started.isoformat(),
                    },
                )
                continue
            destination = dossier_dir / f"{review_id}.json"
            if destination.is_file():
                try:
                    existing = self._read_object(destination)
                except (OSError, json.JSONDecodeError, ValidationError):
                    existing = {}
                if existing.get("analysis", {}).get("content_hash") == dossier["analysis"]["content_hash"]:
                    skipped += 1
                    continue
            self._atomic_json(destination, dossier)
            written += 1

        ended = self.now().astimezone(timezone.utc)
        record = HermesSyncRun(
            run_id=resolved_run_id,
            status="success",
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_seconds=round(time.monotonic() - started_monotonic, 6),
            input_reviews=len(paths),
            dossiers_written=written,
            skipped_unchanged=skipped,
            rejected=rejected,
            rejection_reasons=reasons,
            validation_errors=validation_errors,
        )
        self._atomic_json(self.private_home / "compiler" / "runs" / f"{resolved_run_id}.json", record.to_dict())
        return record
