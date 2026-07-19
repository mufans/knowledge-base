import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opportunity_os.errors import BoundaryError, CapacityError, ValidationError
from opportunity_os.freshness import TechState
from opportunity_os.models import Direction, Evidence, Experiment, Opportunity, Review


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")
SENSITIVE_FIELDS = {
    "api_key", "apikey", "token", "password", "secret", "cash_amount",
    "private_contact", "application_message",
}
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
        for name in ("opportunities", "experiments", "tech_states", "reviews", "snapshots", "cadence"):
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

    def _event(self, action: str, entity_type: str, entity_id: str) -> None:
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_id": entity_id,
            "entity_type": entity_type,
        }
        with (self.home / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def save_payload(self, entity_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_sensitive_fields(payload)
        if entity_type != "opportunity":
            raise ValidationError("save_payload 目前只接受 opportunity")
        return self.save_opportunity(Opportunity.from_dict(payload))

    def save_opportunity(self, opportunity: Opportunity) -> dict[str, Any]:
        self._ensure_initialized()
        _validate_identifier(opportunity.id)
        payload = opportunity.to_dict()
        _reject_sensitive_fields(payload)
        self._write_json(self.home / "opportunities" / f"{opportunity.id}.json", payload)
        self._event("save_opportunity", "opportunity", opportunity.id)
        return payload

    def list_opportunities(self, status: str | None = None) -> list[dict[str, Any]]:
        self._ensure_initialized()
        result = [self._read_json(path) for path in sorted((self.home / "opportunities").glob("*.json"))]
        if status:
            result = [item for item in result if item.get("status") == status]
        return sorted(result, key=lambda item: (-float(item["total_score"]), item["id"]))

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
        self._event("save_review", "review", review.id)
        return payload

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
        portfolio = self.get_portfolio()
        return {
            "opportunity_count": len(list((self.home / "opportunities").glob("*.json"))),
            "experiment_count": len(list((self.home / "experiments").glob("*.json"))),
            "review_count": len(list((self.home / "reviews").glob("*.json"))),
            "tech_state_count": len(list((self.home / "tech_states").glob("*.json"))),
            "portfolio": portfolio,
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
