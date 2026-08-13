"""Hermes dossier -> WikiCandidate -> quality gate -> Wiki publication loop.

This closes the P0 knowledge-loop gap: ``hermes_sync`` materializes dossiers in
``compiler/dossiers/`` but nothing ever turned them into publishable Wiki pages.
This module deterministically compiles each dossier into a schema-v1
``WikiCandidateContract``, runs the independent quality gate, publishes
``publish`` decisions into ``wiki/``, and records observable rejections and
``needs_human`` outcomes. It never writes ``raw/`` and never reaches outside the
knowledge repository.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from opportunity_os.contracts import (
    AnalysisContract,
    EvidenceContract,
    WikiCandidateContract,
    content_hash,
    load_contract,
    stable_id,
)
from opportunity_os.errors import BoundaryError, ValidationError
from opportunity_os.knowledge_compiler import KnowledgeCompiler

TAG_HINTS = (
    ("agent", "Agent"),
    ("mobile", "Mobile"),
    ("android", "Android"),
    ("swift", "Swift"),
    ("ios", "iOS"),
    ("harmony", "HarmonyOS"),
    ("rag", "RAG"),
    ("mcp", "MCP"),
    ("llm", "LLM"),
    ("codex", "Codex"),
    ("needle", "Needle"),
    ("colibri", "Colibri"),
    ("prompt", "PromptEngineering"),
)
_DEFAULT_TAGS = ("Agent", "Mobile")
_MAX_SECTION_CHARS = 6000


def _slug(title: str) -> str:
    cleaned = re.sub(r"[^\w\u3400-\u9fff]+", "-", title, flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned[:80] or "dossier"


def _bullets(texts: list[str]) -> str:
    return "\n".join(f"- {text.strip()}" for text in texts if text and text.strip())


def _cap(text: str) -> str:
    return text if len(text) <= _MAX_SECTION_CHARS else text[:_MAX_SECTION_CHARS] + "\n- …"


def derive_tags(combined_text: str) -> tuple[str, ...]:
    lowered = combined_text.casefold()
    tags: list[str] = []
    for needle, tag in TAG_HINTS:
        if needle in lowered and tag not in tags:
            tags.append(tag)
    for fallback in _DEFAULT_TAGS:
        if fallback not in tags:
            tags.append(fallback)
        if len(tags) >= 5:
            break
    return tuple(tags[:5])


def build_candidate(
    dossier: Mapping[str, Any],
    *,
    knowledge_root: str | Path,
    human_decision: str = "approved",
) -> tuple[WikiCandidateContract, tuple[EvidenceContract, ...]]:
    """Deterministically compile one dossier into a reviewable candidate."""

    if not isinstance(dossier, Mapping):
        raise ValidationError("dossier must be an object")
    analysis_value = dossier.get("analysis")
    evidence_value = dossier.get("evidence")
    if not isinstance(analysis_value, Mapping) or not isinstance(evidence_value, (list, tuple)):
        raise ValidationError("dossier is missing analysis or evidence")
    analysis = load_contract("analysis", dict(analysis_value))
    if not isinstance(analysis, AnalysisContract):
        raise ValidationError("dossier analysis has an unexpected contract type")
    records = tuple(load_contract("evidence", dict(item)) for item in evidence_value)
    if any(not isinstance(record, EvidenceContract) for record in records):
        raise ValidationError("dossier evidence has an unexpected contract type")
    evidence_records = tuple(record for record in records if isinstance(record, EvidenceContract))
    by_id = {record.id: record for record in evidence_records}

    title = str(dossier.get("review_title") or dossier.get("review_id") or analysis.id).strip()
    if not title:
        raise ValidationError("dossier has no title")

    support: list[str] = []
    oppose: list[str] = []
    for claim in analysis.claims:
        record = by_id.get(claim.evidence_ids[0]) if claim.evidence_ids else None
        stance = record.stance if record is not None else "support"
        (support if stance == "support" else oppose).append(claim.text)

    trends = [text for text in analysis.conflicts if text.strip()]
    if not trends:
        trends = [claim.text for claim in analysis.claims if claim.claim_type == "inference"]
    gaps = [text for text in analysis.knowledge_gaps if text.strip()]
    next_step = (
        analysis.collection_questions[0].strip()
        if analysis.collection_questions and analysis.collection_questions[0].strip()
        else f"围绕「{title}」的正反证据安排一次最小实验，验证关键假设。"
    )

    sections = {
        "多来源共同点": _cap(_bullets(support)),
        "冲突": _cap(_bullets(oppose)),
        "趋势判断": _cap(_bullets(trends)),
        "行动建议": _cap(_bullets([*gaps, next_step])),
    }
    for name, text in sections.items():
        if not text.strip():
            raise ValidationError(f"dossier section '{name}' is empty")

    slug = _slug(title)
    target_path = f"wiki/syntheses/{slug}.md"
    target = (Path(knowledge_root).expanduser().resolve() / target_path).resolve()
    action = "update" if target.is_file() else "create"

    combined = title + "\n" + "\n".join(sections.values())
    candidate_id = stable_id("candidate", analysis.id)
    candidate = WikiCandidateContract(
        id=candidate_id,
        source_url=analysis.source_url,
        collected_at=analysis.collected_at,
        content_hash=content_hash(sections),
        run_id=analysis.run_id,
        page_type="synthesis",
        action=action,
        title=title,
        tags=derive_tags(combined),
        target_path=target_path,
        analysis_id=analysis.id,
        claims=analysis.claims,
        evidence_ids=tuple(record.id for record in evidence_records),
        opposing_evidence_ids=analysis.opposing_evidence_ids,
        sections=sections,
        novelty_summary=(
            f"本页综合 {len(support)} 条支持证据与 {len(oppose)} 条反方证据，"
            f"形成关于「{title}」的多来源判断。"
        ),
        novelty_score=round(min(1.0, 0.3 + 0.05 * len(analysis.claims)), 2),
        purpose_relevance=1.0,
        actionable_next_step=next_step,
        human_decision=human_decision,
    )
    return candidate, evidence_records


@dataclass(frozen=True, slots=True)
class PublishRun:
    run_id: str
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    input_reviews: int
    published: int
    rejected: int
    needs_human: int
    skipped: int
    validation_errors: int
    rejection_reasons: dict[str, int]
    plan: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
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


class KnowledgePublishRunner:
    """Compile dossiers and publish the ones that pass the quality gate."""

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
            raise BoundaryError("publish private state must remain outside the knowledge repository")
        self.compiler = KnowledgeCompiler(self.knowledge_root, self.private_home)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _dossier_paths(self) -> list[Path]:
        directory = self.private_home / "compiler" / "dossiers"
        if not directory.is_dir():
            return []
        return sorted(path for path in directory.glob("*.json"))

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValidationError("dossier JSON must be an object")
        return value

    def _marker(self, candidate_id: str) -> Path:
        return self.private_home / "compiler" / "published" / f"{candidate_id}.json"

    def _already_published(self, candidate_id: str, analysis_hash: str) -> bool:
        marker = self._marker(candidate_id)
        if not marker.is_file():
            return False
        try:
            return self._read_object(marker).get("analysis_hash") == analysis_hash
        except (OSError, json.JSONDecodeError, ValidationError):
            return False

    def _record_rejection(
        self,
        run_id: str,
        review_id: str,
        decision: str,
        errors: tuple[str, ...],
    ) -> None:
        _atomic_json(
            self.private_home / "compiler" / "rejections" / f"{review_id}.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "review_id": review_id,
                "status": decision,
                "reasons": list(errors),
                "at": self.now().astimezone(timezone.utc).isoformat(),
            },
        )

    def _review_only(self, candidate: WikiCandidateContract, evidence) -> dict[str, Any]:
        """Dry-run review: no mutation to wiki, compiler state, or markers."""

        review = self.compiler.gate.review(candidate, tuple(evidence))
        return {
            "candidate_id": candidate.id,
            "title": candidate.title,
            "action": candidate.action,
            "target_path": candidate.target_path,
            "decision": review.decision,
            "reasons": list(review.reasons),
            "errors": list(review.validation_errors),
            "fact_citation_coverage": review.fact_citation_coverage,
        }

    def run(self, *, run_id: str | None = None, dry_run: bool = False) -> PublishRun:
        started = self.now().astimezone(timezone.utc)
        resolved_run_id = run_id or stable_id("run", "kb-publish", started.isoformat())
        started_monotonic = time.monotonic()

        seen = published = rejected = needs_human = skipped = validation_errors = 0
        reasons: dict[str, int] = {}
        plan: list[dict[str, Any]] = []

        for path in self._dossier_paths():
            try:
                dossier = self._read_object(path)
            except (OSError, json.JSONDecodeError, ValidationError):
                validation_errors += 1
                continue
            try:
                candidate, evidence = build_candidate(dossier, knowledge_root=self.knowledge_root)
            except ValidationError:
                validation_errors += 1
                continue
            seen += 1

            analysis_hash = str(dossier.get("analysis", {}).get("content_hash", ""))
            if self._already_published(candidate.id, analysis_hash):
                skipped += 1
                continue

            if dry_run:
                plan.append(self._review_only(candidate, evidence))
                continue

            outcome = self.compiler.run(candidate, evidence)
            review = outcome.review
            if review.decision == "publish":
                published += 1
                _atomic_json(
                    self._marker(candidate.id),
                    {
                        "schema_version": 1,
                        "candidate_id": candidate.id,
                        "analysis_hash": analysis_hash,
                        "review_id": review.id,
                        "published_path": outcome.published_path,
                        "at": self.now().astimezone(timezone.utc).isoformat(),
                    },
                )
            elif review.decision in {"reject", "needs_human"}:
                if review.decision == "needs_human":
                    needs_human += 1
                else:
                    rejected += 1
                for code in review.validation_errors:
                    key = code.split(":", 1)[0]
                    reasons[key] = reasons.get(key, 0) + 1
                self._record_rejection(
                    resolved_run_id, review.id, review.decision, review.validation_errors
                )

        ended = self.now().astimezone(timezone.utc)
        record = PublishRun(
            run_id=resolved_run_id,
            status="success",
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_seconds=round(time.monotonic() - started_monotonic, 6),
            input_reviews=seen,
            published=published,
            rejected=rejected,
            needs_human=needs_human,
            skipped=skipped,
            validation_errors=validation_errors,
            rejection_reasons=reasons,
            plan=tuple(plan),
        )
        if not dry_run:
            run_payload = {
                key: value
                for key, value in record.to_dict().items()
                if key != "plan"
            }
            _atomic_json(
                self.private_home / "compiler" / "runs" / f"{resolved_run_id}.json",
                run_payload,
            )
        return record
