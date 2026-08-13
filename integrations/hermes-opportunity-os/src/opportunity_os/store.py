import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from opportunity_os.errors import BoundaryError, CapacityError, ValidationError
from opportunity_os.freshness import TechState
from opportunity_os.contracts import (
    AnalysisContract,
    UserOutcomeContract,
    WikiCandidateContract,
    stable_id,
)
from opportunity_os.models import Direction, Evidence, Experiment, Opportunity, Review
from opportunity_os.sanitizer import SENSITIVE_FIELDS
from opportunity_os.semantic_dedup import DEFAULT_DUPLICATE_THRESHOLD, semantic_similarity
from opportunity_os.state_machine import normalize_state, validate_transition


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")
DIRECTION_CAPACITY = {"observe": 5, "validate": 2, "active": 1}


def _validate_identifier(identifier: str) -> None:
    if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
        raise ValidationError("实体 ID 只能使用小写字母、数字、连字符或下划线")


def _reject_sensitive_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in SENSITIVE_FIELDS:
                raise ValidationError(f"禁止保存敏感字段: {key}")
            _reject_sensitive_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive_fields(item)


class PrivateStore:
    def __init__(self, home: str | Path, *, knowledge_root: str | Path | None = None) -> None:
        self.home = Path(home).expanduser().resolve()
        self.knowledge_root = Path(knowledge_root).expanduser().resolve() if knowledge_root else None
        if self.knowledge_root and (self.home == self.knowledge_root or self.home.is_relative_to(self.knowledge_root)):
            raise BoundaryError("私人状态目录必须位于知识库之外")

    @property
    def portfolio_path(self) -> Path:
        return self.home / "portfolio.json"

    def initialize(self) -> None:
        for name in (
            "opportunities",
            "experiments",
            "tech_states",
            "reviews",
            "snapshots",
            "cadence",
            "state_transitions",
            "analyses",
            "wiki_candidates",
            "user_outcomes",
        ):
            (self.home / name).mkdir(parents=True, exist_ok=True)
        events = self.home / "events.jsonl"
        events.touch(mode=0o600, exist_ok=True)
        if not self.portfolio_path.exists():
            self._write_json(self.portfolio_path, {"directions": []})

    def _ensure_initialized(self) -> None:
        if not self.portfolio_path.is_file():
            raise ValidationError("私人状态尚未初始化")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _event(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        *,
        run_id: str | None = None,
        status: str | None = None,
        reason: str | None = None,
    ) -> None:
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_id": entity_id,
            "entity_type": entity_type,
        }
        if run_id is not None:
            record["run_id"] = run_id
        if status is not None:
            record["status"] = status
        if reason is not None:
            record["reason"] = reason
        with (self.home / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def save_payload(self, entity_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_sensitive_fields(payload)
        if entity_type != "opportunity":
            raise ValidationError("save_payload 目前只接受 opportunity")
        return self.save_opportunity(Opportunity.from_dict(payload))

    def find_duplicate(self, opportunity: Opportunity, *, threshold: float = DEFAULT_DUPLICATE_THRESHOLD) -> tuple[str, float] | None:
        """Return the id and similarity of the closest existing card, if above threshold."""

        payload = opportunity.to_dict()
        best_id: str | None = None
        best_score = 0.0
        for existing in self._iter_opportunities():
            if existing.get("id") == opportunity.id:
                continue
            similarity = semantic_similarity(payload, existing)
            if similarity > best_score:
                best_score = similarity
                best_id = str(existing.get("id", ""))
        if best_id is not None and best_score >= threshold:
            return best_id, best_score
        return None

    def save_opportunity(self, opportunity: Opportunity) -> dict[str, Any]:
        self._ensure_initialized()
        _validate_identifier(opportunity.id)
        duplicate = self.find_duplicate(opportunity)
        if duplicate is not None:
            raise ValidationError(
                f"语义重复机会已存在: {duplicate[0]}（相似度 {duplicate[1]:.2f}）"
            )
        payload = opportunity.to_dict()
        _reject_sensitive_fields(payload)
        self._write_json(self.home / "opportunities" / f"{opportunity.id}.json", payload)
        self._event("save_opportunity", "opportunity", opportunity.id)
        return payload

    def transition_opportunity(
        self,
        *,
        opportunity_id: str,
        to_state: str,
        trigger_reason: str,
        new_evidence_ids: list[str],
        opposing_evidence_ids: list[str],
        next_experiment_id: str | None,
        user_decision: str | None,
        automatic_rule: str | None,
        run_id: str,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        opportunity = self.get_opportunity(opportunity_id)
        from_state = normalize_state(str(opportunity.get("status", "candidate")))
        at = occurred_at or datetime.now(timezone.utc).isoformat()
        transition = validate_transition(
            {
                "schema_version": 1,
                "id": stable_id("transition", opportunity_id, from_state, to_state, at, run_id),
                "opportunity_id": opportunity_id,
                "from_state": from_state,
                "to_state": to_state,
                "trigger_reason": trigger_reason,
                "new_evidence_ids": new_evidence_ids,
                "opposing_evidence_ids": opposing_evidence_ids,
                "next_experiment_id": next_experiment_id,
                "user_decision": user_decision,
                "automatic_rule": automatic_rule,
                "occurred_at": at,
                "run_id": run_id,
            }
        )
        opportunity["status"] = transition.to_state
        _reject_sensitive_fields(opportunity)
        self._write_json(self.home / "opportunities" / f"{opportunity_id}.json", opportunity)
        history_path = self.home / "state_transitions" / f"{opportunity_id}.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(transition.model_dump_json() + "\n")
        os.chmod(history_path, 0o600)
        self._event(
            "transition_opportunity",
            "opportunity",
            opportunity_id,
            run_id=run_id,
            status=transition.to_state,
            reason=trigger_reason,
        )
        return transition.model_dump(mode="json")

    def save_analysis(self, analysis: AnalysisContract) -> dict[str, Any]:
        return self._save_contract("analyses", "analysis", analysis.id, analysis.model_dump(mode="json"))

    def save_wiki_candidate(self, candidate: WikiCandidateContract) -> dict[str, Any]:
        return self._save_contract(
            "wiki_candidates", "wiki_candidate", candidate.id, candidate.model_dump(mode="json")
        )

    def record_user_outcome(self, outcome: UserOutcomeContract) -> dict[str, Any]:
        return self._save_contract(
            "user_outcomes", "user_outcome", outcome.id, outcome.model_dump(mode="json")
        )

    def _save_contract(
        self, directory: str, entity_type: str, identifier: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_initialized()
        _validate_identifier(identifier)
        _reject_sensitive_fields(payload)
        self._write_json(self.home / directory / f"{identifier}.json", payload)
        self._event(
            f"save_{entity_type}",
            entity_type,
            identifier,
            run_id=str(payload.get("run_id")) if payload.get("run_id") else None,
        )
        return payload

    def _iter_opportunities(self):
        directory = self.home / "opportunities"
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                yield self._read_json(path)
            except (OSError, json.JSONDecodeError):
                continue

    def list_opportunities(self, status: str | None = None) -> list[dict[str, Any]]:
        self._ensure_initialized()
        result = list(self._iter_opportunities())
        for item in result:
            item["status"] = normalize_state(str(item.get("status", "candidate")))
        if status:
            result = [item for item in result if item.get("status") == normalize_state(status)]
        return sorted(result, key=lambda item: (-float(item["total_score"]), item["id"]))

    def group_duplicates(self, *, threshold: float = DEFAULT_DUPLICATE_THRESHOLD) -> list[list[dict[str, Any]]]:
        """Union-find grouping of semantically duplicated opportunity cards."""

        opportunities = self.list_opportunities()
        parent = list(range(len(opportunities)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for left in range(len(opportunities)):
            for right in range(left + 1, len(opportunities)):
                if semantic_similarity(opportunities[left], opportunities[right]) >= threshold:
                    union(left, right)
        grouped: dict[int, list[dict[str, Any]]] = {}
        for index in range(len(opportunities)):
            grouped.setdefault(find(index), []).append(opportunities[index])
        return [members for members in grouped.values() if len(members) > 1]

    def merge_duplicates(
        self,
        *,
        threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
        apply: bool = False,
        run_id: str = "run-semantic-merge",
    ) -> dict[str, Any]:
        """Keep the highest-scoring card and archive the rest in each duplicate group."""

        self._ensure_initialized()
        groups = self.group_duplicates(threshold=threshold)
        result_groups: list[dict[str, Any]] = []
        archived: list[str] = []
        for members in groups:
            ordered = sorted(
                members,
                key=lambda item: (-float(item.get("total_score", 0)), str(item.get("id", ""))),
            )
            winner = ordered[0]
            losers = ordered[1:]
            result_groups.append(
                {
                    "keep": winner["id"],
                    "archived": [item["id"] for item in losers],
                    "similarity": max(
                        semantic_similarity(winner, item) for item in losers
                    ),
                }
            )
            if apply:
                for loser in losers:
                    if normalize_state(str(loser.get("status", "candidate"))) == "archived":
                        continue
                    self.transition_opportunity(
                        opportunity_id=str(loser["id"]),
                        to_state="archived",
                        trigger_reason=f"与 {winner['id']} 语义重复，合并归档",
                        new_evidence_ids=[],
                        opposing_evidence_ids=[],
                        next_experiment_id=None,
                        user_decision=None,
                        automatic_rule="semantic_duplicate_merge",
                        run_id=run_id,
                    )
                    archived.append(str(loser["id"]))
        return {"groups": result_groups, "archived": archived, "applied": apply}

    def record_experiment(
        self,
        *,
        experiment_id: str,
        opportunity_id: str,
        experiment: Experiment,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._ensure_initialized()
        _validate_identifier(experiment_id)
        _validate_identifier(opportunity_id)
        self.get_opportunity(opportunity_id)
        parsed_evidence = [Evidence.from_dict(item) for item in evidence]
        payload = {
            "id": experiment_id,
            "opportunity_id": opportunity_id,
            "experiment": experiment.to_dict(),
            "evidence": [item.to_dict() for item in parsed_evidence],
        }
        _reject_sensitive_fields(payload)
        self._write_json(self.home / "experiments" / f"{experiment_id}.json", payload)
        self._event("record_experiment", "experiment", experiment_id)
        return payload

    def get_portfolio(self) -> dict[str, Any]:
        self._ensure_initialized()
        portfolio = self._read_json(self.portfolio_path)
        counts = {status: 0 for status in DIRECTION_CAPACITY}
        for direction in portfolio["directions"]:
            counts[direction["status"]] += 1
        return {"directions": portfolio["directions"], "counts": counts, "capacity": dict(DIRECTION_CAPACITY)}

    def set_direction(self, direction: Direction) -> dict[str, Any]:
        self._ensure_initialized()
        _validate_identifier(direction.id)
        portfolio = self._read_json(self.portfolio_path)
        remaining = [item for item in portfolio["directions"] if item["id"] != direction.id]
        count = sum(item["status"] == direction.status for item in remaining)
        if count >= DIRECTION_CAPACITY[direction.status]:
            raise CapacityError(f"{direction.status} 方向容量上限为 {DIRECTION_CAPACITY[direction.status]}")
        remaining.append(direction.to_dict())
        remaining.sort(key=lambda item: (item["status"], item["id"]))
        self._write_json(self.portfolio_path, {"directions": remaining})
        self._event("set_direction", "direction", direction.id)
        return direction.to_dict()

    @staticmethod
    def _expected_mix(total: int) -> dict[str, int]:
        strength = math.floor(total * 0.4 + 0.5)
        broad = math.floor(total * 0.4 + 0.5)
        return {"strength": strength, "broad": broad, "surprise": total - strength - broad}

    def save_review(self, review: Review) -> dict[str, Any]:
        self._ensure_initialized()
        _validate_identifier(review.id)
        if review.period in {"daily", "weekly"} and not review.surprise_signal.strip():
            raise ValidationError("每日或每周复盘必须包含意外发现")
        if sum(review.presentation_counts.values()) != len(review.opportunity_ids):
            raise ValidationError("呈现计数必须等于机会卡数量")
        if review.period == "weekly" and review.presentation_counts != self._expected_mix(len(review.opportunity_ids)):
            raise ValidationError("每周复盘必须遵守整数取整后的 40/40/20 呈现配额")
        payload = review.to_dict()
        _reject_sensitive_fields(payload)
        self._write_json(self.home / "reviews" / f"{review.id}.json", payload)
        self._ensure_run_record(review)
        self._event("save_review", "review", review.id)
        return payload

    @staticmethod
    def _review_run_key(period: str, created_at: str) -> tuple[str, str] | None:
        cadence = {"daily": "daily", "weekly": "weekly"}.get(period)
        if cadence is None:
            return None
        day = str(created_at)[:10]
        try:
            parsed = date.fromisoformat(day)
        except ValueError:
            return None
        if cadence == "weekly":
            iso = parsed.isocalendar()
            return cadence, f"{iso.year}-W{iso.week:02d}"
        return cadence, day

    def _ensure_run_record(self, review: Review) -> None:
        """Idempotently guarantee one run record per review so review and run are 1:1."""

        key = self._review_run_key(review.period, review.created_at)
        if key is None:
            return
        cadence, period_key = key
        path = self.home / "dashboard" / "runs" / cadence / f"{period_key}.json"
        if path.is_file():
            return
        payload = {
            "run_id": stable_id("run", "review-derived", cadence, period_key),
            "cadence": cadence,
            "period_key": period_key,
            "idempotency_key": f"{cadence}:{period_key}",
            "status": "derived",
            "started_at": review.created_at,
            "ended_at": review.created_at,
            "duration_seconds": 0.0,
            "error_class": None,
            "component": "hermes",
            "derived_from_review": review.id,
        }
        self._write_json(path, payload)

    def reconcile_run_records(self, *, apply: bool = False) -> dict[str, Any]:
        """Report and optionally backfill run records missing for saved reviews."""

        self._ensure_initialized()
        missing: list[dict[str, str]] = []
        directory = self.home / "reviews"
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    payload = self._read_json(path)
                except (OSError, json.JSONDecodeError):
                    continue
                key = self._review_run_key(
                    str(payload.get("period", "")), str(payload.get("created_at", ""))
                )
                if key is None:
                    continue
                cadence, period_key = key
                run_path = self.home / "dashboard" / "runs" / cadence / f"{period_key}.json"
                if run_path.is_file():
                    continue
                missing.append(
                    {"review_id": str(payload.get("id", path.stem)), "cadence": cadence, "period_key": period_key}
                )
                if apply:
                    try:
                        self._ensure_run_record(Review.from_dict(payload))
                    except (ValidationError, TypeError, KeyError, ValueError):
                        continue
        return {
            "missing": missing,
            "backfilled": len(missing) if apply else 0,
            "applied": apply,
        }

    def get_review(self, review_id: str | None = None, *, latest: bool = False) -> dict[str, Any]:
        self._ensure_initialized()
        if latest:
            reviews = [self._read_json(path) for path in (self.home / "reviews").glob("*.json")]
            if not reviews:
                raise ValidationError("尚无可渲染的复盘")
            return max(reviews, key=lambda item: (item["created_at"], item["id"]))
        if review_id is None:
            raise ValidationError("必须提供 review_id 或 latest=True")
        _validate_identifier(review_id)
        path = self.home / "reviews" / f"{review_id}.json"
        if not path.is_file():
            raise ValidationError(f"复盘不存在: {review_id}")
        return self._read_json(path)

    def get_opportunity(self, opportunity_id: str) -> dict[str, Any]:
        _validate_identifier(opportunity_id)
        path = self.home / "opportunities" / f"{opportunity_id}.json"
        if not path.is_file():
            raise ValidationError(f"机会不存在: {opportunity_id}")
        return self._read_json(path)

    def system_status(self) -> dict[str, Any]:
        self._ensure_initialized()
        portfolio = self._read_json(self.portfolio_path)
        counts = {status: 0 for status in DIRECTION_CAPACITY}
        for direction in portfolio["directions"]:
            counts[direction["status"]] += 1
        return {
            "opportunity_count": len(list((self.home / "opportunities").glob("*.json"))),
            "experiment_count": len(list((self.home / "experiments").glob("*.json"))),
            "review_count": len(list((self.home / "reviews").glob("*.json"))),
            "tech_state_count": len(list((self.home / "tech_states").glob("*.json"))),
            "analysis_count": len(list((self.home / "analyses").glob("*.json"))),
            "wiki_candidate_count": len(list((self.home / "wiki_candidates").glob("*.json"))),
            "user_outcome_count": len(list((self.home / "user_outcomes").glob("*.json"))),
            "portfolio": {"counts": counts, "capacity": dict(DIRECTION_CAPACITY)},
        }

    @staticmethod
    def _tech_identifier(technology: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", technology.casefold()).strip("-")
        if not slug:
            raise ValidationError("技术名称无法生成安全 ID")
        return slug[:80]

    def record_tech_state(self, state: TechState) -> dict[str, Any]:
        self._ensure_initialized()
        identifier = self._tech_identifier(state.technology)
        path = self.home / "tech_states" / f"{identifier}.json"
        if path.exists():
            existing = TechState.from_dict(self._read_json(path))
            if state.maturity == "frontier" and state.recommended_stable != existing.recommended_stable:
                raise ValidationError("未验证 Frontier 不能替换 recommended Stable 基线")
        payload = state.to_dict()
        self._write_json(path, payload)
        self._event("record_tech_state", "tech_state", identifier)
        return payload
