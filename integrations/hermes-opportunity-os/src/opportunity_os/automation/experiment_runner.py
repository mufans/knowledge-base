"""Deterministic experiment execution for researched and candidate opportunities.

The state machine declared ``minimum_experiment`` but nothing ever ran it, so 21
cards stayed in ``researched`` forever and ``experiments/`` held only a handful
of hand-written records. This runner materializes the declared minimum
experiment into an ``experiments/*.json`` run record, evaluates a deterministic
success rule against the card's evidence, and advances the opportunity to
``researched``/``validated`` or keeps it in place.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from opportunity_os.contracts import stable_id
from opportunity_os.errors import ValidationError
from opportunity_os.models import Experiment
from opportunity_os.store import PrivateStore

EXPERIMENT_STATUSES = ("candidate", "researched")


class ExperimentRunner:
    """Plan and execute declared minimum experiments without external action."""

    def __init__(self, home: str | Path) -> None:
        self.store = PrivateStore(home)

    def eligible(self) -> list[dict[str, Any]]:
        """Opportunities in candidate/researched that still declare an experiment."""

        result: list[dict[str, Any]] = []
        for opportunity in self.store.list_opportunities():
            if opportunity.get("status") not in EXPERIMENT_STATUSES:
                continue
            if not opportunity.get("minimum_experiment"):
                continue
            if self.has_experiment(str(opportunity["id"])):
                continue
            result.append(opportunity)
        return result

    def has_experiment(self, opportunity_id: str) -> bool:
        directory = self.store.home / "experiments"
        if not directory.is_dir():
            return False
        for path in directory.glob("*.json"):
            try:
                payload = self.store._read_json(path)
            except (OSError, ValueError):
                continue
            if payload.get("opportunity_id") == opportunity_id:
                return True
        return False

    @staticmethod
    def _experiment_id(opportunity_id: str, day: str) -> str:
        return f"exp-{opportunity_id.removeprefix('opp-')}-{day}"

    @staticmethod
    def _judge_success(supporting: list[dict[str, Any]], opposing: list[dict[str, Any]]) -> bool:
        """Deterministic success proxy: verifiable support, contrary evidence, net support."""

        support_facts = [item for item in supporting if item.get("kind") == "fact"]
        return bool(support_facts) and bool(opposing) and len(supporting) >= len(opposing)

    def plan(self) -> list[dict[str, Any]]:
        day = date.today().isoformat()
        result = []
        for opportunity in self.eligible():
            experiment = Experiment.from_dict(opportunity["minimum_experiment"])
            supporting = opportunity.get("supporting_evidence", [])
            opposing = opportunity.get("opposing_evidence", [])
            result.append(
                {
                    "opportunity_id": opportunity["id"],
                    "title": opportunity["title"],
                    "status": opportunity["status"],
                    "experiment_id": self._experiment_id(opportunity["id"], day),
                    "experiment_title": experiment.title,
                    "success_metric": experiment.success_metric,
                    "predicted_success": self._judge_success(supporting, opposing),
                }
            )
        return result

    def run(
        self,
        opportunity_id: str,
        *,
        run_id: str,
        apply: bool = False,
        today: str | None = None,
    ) -> dict[str, Any]:
        opportunity = self.store.get_opportunity(opportunity_id)
        status = opportunity.get("status", "candidate")
        if status not in EXPERIMENT_STATUSES:
            raise ValidationError(f"机会状态 {status} 不可进入实验")
        if not opportunity.get("minimum_experiment"):
            raise ValidationError("机会缺少 minimum_experiment")

        day = today or date.today().isoformat()
        experiment = Experiment.from_dict(opportunity["minimum_experiment"])
        experiment_id = self._experiment_id(opportunity_id, day)
        supporting = opportunity.get("supporting_evidence", [])
        opposing = opportunity.get("opposing_evidence", [])
        success = self._judge_success(supporting, opposing)
        evidence = [*supporting, *opposing]
        next_state = "researched" if status == "candidate" else "validated"

        plan = {
            "applied": False,
            "opportunity_id": opportunity_id,
            "status": status,
            "experiment_id": experiment_id,
            "success": success,
            "next_state": next_state if success else status,
        }
        if not apply:
            return plan

        self.store.record_experiment(
            experiment_id=experiment_id,
            opportunity_id=opportunity_id,
            experiment=experiment,
            evidence=evidence,
        )
        if not success:
            return {**plan, "applied": True}

        new_evidence_ids = [
            stable_id("evidence", item.get("claim"), item.get("source_url"), item.get("observed_at"))
            for item in supporting
        ]
        opposing_evidence_ids = [
            stable_id("evidence", item.get("claim"), item.get("source_url"), item.get("observed_at"))
            for item in opposing
        ]
        transition = self.store.transition_opportunity(
            opportunity_id=opportunity_id,
            to_state=next_state,
            trigger_reason=f"最小实验 {experiment_id} 成功指标满足",
            new_evidence_ids=new_evidence_ids,
            opposing_evidence_ids=opposing_evidence_ids,
            next_experiment_id=experiment_id,
            user_decision=None,
            automatic_rule="minimum_experiment_success",
            run_id=run_id,
        )
        return {**plan, "applied": True, "transition": transition}
