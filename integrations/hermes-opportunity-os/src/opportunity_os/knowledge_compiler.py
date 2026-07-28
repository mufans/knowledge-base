"""Deterministic quality gates and publication for evidence-backed Wiki candidates."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import unquote, urlsplit

from opportunity_os.contracts import (
    EvidenceContract,
    ReviewResultContract,
    WikiCandidateContract,
    content_hash,
    stable_id,
)
from opportunity_os.errors import BoundaryError, ValidationError


PAGE_DIRECTORIES = {
    "concept": "concepts",
    "entity": "entities",
    "source": "sources",
    "synthesis": "syntheses",
}
REQUIRED_SECTIONS = {
    "concept": ("原理", "适用条件", "限制", "实现机制"),
    "entity": ("真实能力", "架构", "成熟度", "适用场景"),
    "source": ("来源结论", "方法", "数据", "局限"),
    "synthesis": ("多来源共同点", "冲突", "趋势判断", "行动建议"),
}
MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
NUMERIC_OR_API = re.compile(
    r"(?:\b(?:v?\d+(?:\.\d+){0,3})\b|%|\b(?:ms|s|MB|GB|tokens?|QPS|FPS)\b|\bAPI\b)",
    re.IGNORECASE,
)
PURPOSE_TERMS = (
    "agent", "llm", "rag", "mcp", "android", "mobile", "swift", "harmony",
    "移动", "鸿蒙", "端侧", "vibe coding", "代码生成", "知识",
)


@dataclass(frozen=True, slots=True)
class CompilerOutcome:
    status: str
    review: ReviewResultContract
    published_path: str | None


def _atomic_text(path: Path, content: str, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    _atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        mode=0o600,
    )


class QualityGate:
    def __init__(self, knowledge_root: str | Path) -> None:
        self.knowledge_root = Path(knowledge_root).expanduser().resolve()
        self.wiki_root = (self.knowledge_root / "wiki").resolve()
        self.raw_root = (self.knowledge_root / "raw").resolve()
        if not self.wiki_root.is_dir() or not self.raw_root.is_dir():
            raise ValidationError("knowledge root must contain wiki and raw")

    @staticmethod
    def _evidence_map(evidence: Iterable[EvidenceContract]) -> dict[str, EvidenceContract]:
        result: dict[str, EvidenceContract] = {}
        for record in evidence:
            if record.id in result:
                raise ValidationError(f"duplicate evidence id: {record.id}")
            result[record.id] = record
        return result

    def _target(self, candidate: WikiCandidateContract) -> Path | None:
        if candidate.target_path is None:
            return None
        target = (self.knowledge_root / candidate.target_path).resolve()
        if not target.is_relative_to(self.wiki_root):
            raise BoundaryError("candidate target escaped wiki")
        expected = self.wiki_root / PAGE_DIRECTORIES[candidate.page_type]
        if target.parent != expected.resolve():
            raise ValidationError("candidate target does not match page_type")
        return target

    @staticmethod
    def _normalized_title(value: str) -> str:
        return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.casefold())

    def _duplicate(self, candidate: WikiCandidateContract, target: Path | None) -> str | None:
        title = self._normalized_title(candidate.title)
        for path in self.wiki_root.rglob("*.md"):
            if path.name == "index.md":
                continue
            existing = self._normalized_title(path.stem)
            try:
                first_heading = next(
                    line[2:].strip()
                    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.startswith("# ")
                )
            except StopIteration:
                first_heading = path.stem
            heading = self._normalized_title(first_heading)
            if title in {existing, heading} or (
                title
                and max(
                    SequenceMatcher(None, title, existing).ratio(),
                    SequenceMatcher(None, title, heading).ratio(),
                )
                >= 0.94
            ):
                if target is None or path.resolve() != target:
                    return str(path.relative_to(self.knowledge_root))
        return None

    def _broken_links(
        self,
        candidate: WikiCandidateContract,
        target: Path | None,
    ) -> tuple[str, ...]:
        if target is None:
            return ("missing_target_path",)
        broken: list[str] = []
        for text in candidate.sections.values():
            for _, raw_target in MARKDOWN_LINK.findall(text):
                decoded = unquote(raw_target.strip())
                parsed = urlsplit(decoded)
                if parsed.scheme in {"http", "https", "mailto"}:
                    if parsed.scheme in {"http", "https"} and not parsed.netloc:
                        broken.append(raw_target)
                    continue
                if decoded.startswith("#"):
                    continue
                relative = decoded.split("#", 1)[0]
                if not relative:
                    continue
                if relative.startswith(("/", "~")):
                    broken.append(raw_target)
                    continue
                resolved = (target.parent / relative).resolve()
                if not resolved.is_relative_to(self.knowledge_root) or not resolved.exists():
                    broken.append(raw_target)
        return tuple(sorted(set(broken)))

    def review(
        self,
        candidate: WikiCandidateContract,
        evidence: Iterable[EvidenceContract],
    ) -> ReviewResultContract:
        records = self._evidence_map(evidence)
        errors: list[str] = []
        reasons: list[str] = []
        try:
            target = self._target(candidate)
        except (BoundaryError, ValidationError):
            target = None
            errors.append("target_path_invalid")

        required = REQUIRED_SECTIONS[candidate.page_type]
        missing_sections = [
            section
            for section in required
            if not isinstance(candidate.sections.get(section), str)
            or not candidate.sections[section].strip()
        ]
        if missing_sections:
            errors.append("page_type_sections_missing")
        if any(not str(value).strip() for value in candidate.sections.values()):
            errors.append("empty_section")

        evidence_ids = set(candidate.evidence_ids)
        opposing_ids = set(candidate.opposing_evidence_ids)
        if missing := sorted(evidence_ids - set(records)):
            errors.append(f"evidence_missing:{len(missing)}")
        if missing := sorted(opposing_ids - set(records)):
            errors.append(f"opposing_evidence_missing:{len(missing)}")
        if not opposing_ids or not any(
            identifier in records and records[identifier].stance == "oppose"
            for identifier in opposing_ids
        ):
            errors.append("opposing_evidence_required")

        fact_claims = [claim for claim in candidate.claims if claim.claim_type == "fact"]
        cited_facts = [
            claim
            for claim in fact_claims
            if claim.evidence_ids and set(claim.evidence_ids).issubset(evidence_ids & set(records))
        ]
        fact_coverage = len(cited_facts) / len(fact_claims) if fact_claims else 1.0
        numeric_claims = [claim for claim in candidate.claims if NUMERIC_OR_API.search(claim.text)]
        cited_numeric = [
            claim
            for claim in numeric_claims
            if claim.evidence_ids and set(claim.evidence_ids).issubset(evidence_ids & set(records))
        ]
        numeric_coverage = len(cited_numeric) / len(numeric_claims) if numeric_claims else 1.0
        if fact_coverage < 0.9:
            errors.append("fact_citation_coverage_below_90_percent")
        if numeric_coverage < 1:
            errors.append("numeric_version_performance_api_coverage_below_100_percent")
        if any(
            evidence_id not in evidence_ids
            for claim in candidate.claims
            for evidence_id in claim.evidence_ids
        ):
            errors.append("claim_references_undeclared_evidence")

        combined = f"{candidate.title}\n" + "\n".join(candidate.sections.values())
        if candidate.purpose_relevance < 0.7 or not any(
            term in combined.casefold() for term in PURPOSE_TERMS
        ):
            errors.append("purpose_mismatch")
        if candidate.action == "create" and candidate.novelty_score < 0.2:
            errors.append("insufficient_information_gain")
        if candidate.action == "update" and candidate.novelty_score < 0.05:
            errors.append("insufficient_update_gain")
        if target is None:
            errors.append("target_path_required")
        elif candidate.action == "create" and target.exists():
            errors.append("create_target_exists_use_update")
        elif candidate.action == "update" and not target.is_file():
            errors.append("update_target_missing")

        duplicate = self._duplicate(candidate, target)
        if duplicate and candidate.action == "create":
            errors.append("duplicate_candidate_use_update")

        broken_links = self._broken_links(candidate, target)
        if broken_links:
            errors.append("broken_local_links")
        if "```" in combined and not cited_facts:
            errors.append("unverifiable_code_or_parameters")
        if "[[" in combined or "]]" in combined:
            errors.append("obsidian_links_forbidden")
        without_links = MARKDOWN_LINK.sub("", combined)
        if re.search(r"https?://", without_links):
            errors.append("bare_url_forbidden")

        if candidate.action == "reject":
            decision = "reject"
            reasons.append("candidate_self_rejected")
        elif errors:
            decision = "reject"
            reasons.append("quality_gate_failed")
        elif candidate.human_decision == "rejected":
            decision = "reject"
            reasons.append("human_rejected")
        elif candidate.human_decision == "pending":
            decision = "needs_human"
            reasons.append("human_decision_required")
        else:
            decision = "publish"
            reasons.append("quality_gate_passed")

        review_core = {
            "candidate_id": candidate.id,
            "decision": decision,
            "reasons": reasons,
            "errors": errors,
            "fact_coverage": fact_coverage,
            "numeric_coverage": numeric_coverage,
            "broken_links": broken_links,
            "duplicate": duplicate,
        }
        return ReviewResultContract(
            id=stable_id("review-result", candidate.id, content_hash(review_core)),
            source_url=candidate.source_url,
            collected_at=candidate.collected_at,
            content_hash=content_hash(review_core),
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            decision=decision,
            reasons=tuple(reasons),
            validation_errors=tuple(errors),
            fact_citation_coverage=round(fact_coverage, 4),
            numeric_citation_coverage=round(numeric_coverage, 4),
            broken_links=broken_links,
            duplicate_target=duplicate,
        )


class KnowledgeCompiler:
    def __init__(self, knowledge_root: str | Path, private_home: str | Path) -> None:
        self.knowledge_root = Path(knowledge_root).expanduser().resolve()
        self.private_home = Path(private_home).expanduser().resolve()
        if self.private_home == self.knowledge_root or self.private_home.is_relative_to(self.knowledge_root):
            raise BoundaryError("compiler state must remain outside knowledge")
        self.gate = QualityGate(self.knowledge_root)

    @staticmethod
    def _claim_lines(
        candidate: WikiCandidateContract,
        records: Mapping[str, EvidenceContract],
    ) -> list[str]:
        labels = {"fact": "Fact", "inference": "Inference", "hypothesis": "Hypothesis"}
        lines: list[str] = []
        for claim in candidate.claims:
            sources = []
            for evidence_id in claim.evidence_ids:
                record = records.get(evidence_id)
                if record is not None:
                    sources.append(f"[{record.source_name}]({record.source_url})")
            citation = f"（{'、'.join(sources)}）" if sources else ""
            lines.append(f"- **{labels[claim.claim_type]}**：{claim.text}{citation}")
        return lines

    def render(
        self,
        candidate: WikiCandidateContract,
        evidence: Iterable[EvidenceContract],
        *,
        include_title: bool = True,
    ) -> str:
        records = {record.id: record for record in evidence}
        lines: list[str] = []
        if include_title:
            lines.extend((
                f"# {candidate.title}",
                "",
                f"> tags: {' '.join(f'#{tag}' for tag in candidate.tags)}",
                f"> evidence: {len(candidate.evidence_ids)} supporting/total | "
                f"{len(candidate.opposing_evidence_ids)} opposing",
                f"> compiler: schema v{candidate.schema_version} | candidate `{candidate.id}`",
                "",
            ))
        for section in REQUIRED_SECTIONS[candidate.page_type]:
            lines.extend((f"## {section}", "", candidate.sections[section].strip(), ""))
        lines.extend(("## 证据化声明", "", *self._claim_lines(candidate, records), ""))
        lines.extend(("## 信息增量", "", candidate.novelty_summary, ""))
        return "\n".join(lines).rstrip() + "\n"

    def _publish(
        self,
        candidate: WikiCandidateContract,
        review: ReviewResultContract,
        evidence: Iterable[EvidenceContract],
    ) -> Path:
        if review.decision != "publish":
            raise ValidationError("only publish decisions may mutate wiki")
        if candidate.target_path is None:
            raise ValidationError("publish target is missing")
        target = (self.knowledge_root / candidate.target_path).resolve()
        if not target.is_relative_to((self.knowledge_root / "wiki").resolve()):
            raise BoundaryError("publish target escaped wiki")

        if candidate.action == "create":
            if target.exists():
                raise ValidationError("create target already exists")
            _atomic_text(target, self.render(candidate, evidence))
            index = target.parent / "index.md"
            entry = f"- [{candidate.title}]({target.name})"
            index_text = index.read_text(encoding="utf-8") if index.is_file() else f"# {target.parent.name}\n\n"
            if entry not in index_text:
                if not index_text.endswith("\n"):
                    index_text += "\n"
                _atomic_text(index, index_text + entry + "\n")
        elif candidate.action == "update":
            if not target.is_file():
                raise ValidationError("update target does not exist")
            existing = target.read_text(encoding="utf-8")
            date_label = datetime.now(timezone.utc).date().isoformat()
            update = (
                f"\n\n### {date_label} Knowledge Compiler 更新\n\n"
                + self.render(candidate, evidence, include_title=False)
            )
            _atomic_text(target, existing.rstrip() + update)
        else:
            raise ValidationError("rejected candidate cannot publish")

        log = self.knowledge_root / "log.md"
        at = datetime.now(timezone.utc).date().isoformat()
        action = "ingest" if candidate.action == "create" else "update"
        line = (
            f"{at} | {action} | {candidate.target_path} | Knowledge Compiler 发布 "
            f"{candidate.id}（fact citation {review.fact_citation_coverage:.0%}）\n"
        )
        with log.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return target

    def run(
        self,
        candidate: WikiCandidateContract,
        evidence: Iterable[EvidenceContract],
    ) -> CompilerOutcome:
        records = tuple(evidence)
        review = self.gate.review(candidate, records)
        _atomic_json(
            self.private_home / "compiler" / "reviews" / f"{review.id}.json",
            review.model_dump(mode="json"),
        )
        published: Path | None = None
        if review.decision == "publish":
            published = self._publish(candidate, review, records)
        return CompilerOutcome(
            status="success",
            review=review,
            published_path=(
                str(published.relative_to(self.knowledge_root))
                if published is not None
                else None
            ),
        )
