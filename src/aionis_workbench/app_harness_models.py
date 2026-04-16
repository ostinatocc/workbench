from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _string_list_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, raw_items in value.items():
        if not isinstance(key, str):
            continue
        cleaned_key = key.strip()
        if not cleaned_key:
            continue
        items = _string_list(raw_items)
        if items:
            normalized[cleaned_key] = items
    return normalized


@dataclass
class EvaluatorCriterion:
    name: str
    description: str = ""
    threshold: float = 0.0
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "EvaluatorCriterion | None":
        if not isinstance(value, dict):
            return None
        name = _string(value.get("name"))
        if not name:
            return None
        return cls(
            name=name,
            description=_string(value.get("description")),
            threshold=float(value.get("threshold") or 0.0),
            weight=float(value.get("weight") or 1.0),
        )


@dataclass
class SprintContract:
    sprint_id: str
    goal: str
    scope: list[str] = field(default_factory=list)
    acceptance_checks: list[str] = field(default_factory=list)
    done_definition: list[str] = field(default_factory=list)
    proposed_by: str = ""
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SprintContract | None":
        if not isinstance(value, dict):
            return None
        sprint_id = _string(value.get("sprint_id"))
        goal = _string(value.get("goal"))
        if not sprint_id or not goal:
            return None
        return cls(
            sprint_id=sprint_id,
            goal=goal,
            scope=_string_list(value.get("scope")),
            acceptance_checks=_string_list(value.get("acceptance_checks")),
            done_definition=_string_list(value.get("done_definition")),
            proposed_by=_string(value.get("proposed_by")),
            approved=value.get("approved") is True,
        )


@dataclass
class ProductSpec:
    prompt: str
    title: str = ""
    app_type: str = ""
    stack: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    feature_groups: dict[str, list[str]] = field(default_factory=dict)
    feature_rationale: dict[str, str] = field(default_factory=dict)
    design_direction: str = ""
    sprint_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ProductSpec | None":
        if not isinstance(value, dict):
            return None
        prompt = _string(value.get("prompt"))
        if not prompt:
            return None
        return cls(
            prompt=prompt,
            title=_string(value.get("title")),
            app_type=_string(value.get("app_type")),
            stack=_string_list(value.get("stack")),
            features=_string_list(value.get("features")),
            feature_groups=_string_list_map(value.get("feature_groups")),
            feature_rationale={
                key: cleaned
                for key, raw in (value.get("feature_rationale") or {}).items()
                if isinstance(key, str) and (cleaned := _string(raw))
            },
            design_direction=_string(value.get("design_direction")),
            sprint_ids=_string_list(value.get("sprint_ids")),
        )


@dataclass
class SprintEvaluation:
    sprint_id: str
    status: str = ""
    summary: str = ""
    evaluator_mode: str = ""
    criteria_scores: dict[str, float] = field(default_factory=dict)
    passing_criteria: list[str] = field(default_factory=list)
    failing_criteria: list[str] = field(default_factory=list)
    blocker_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SprintEvaluation | None":
        if not isinstance(value, dict):
            return None
        sprint_id = _string(value.get("sprint_id"))
        if not sprint_id:
            return None
        raw_scores = value.get("criteria_scores")
        criteria_scores: dict[str, float] = {}
        if isinstance(raw_scores, dict):
            for key, score in raw_scores.items():
                if not isinstance(key, str):
                    continue
                cleaned = key.strip()
                if not cleaned:
                    continue
                criteria_scores[cleaned] = float(score or 0.0)
        return cls(
            sprint_id=sprint_id,
            status=_string(value.get("status")),
            summary=_string(value.get("summary")),
            evaluator_mode=_string(value.get("evaluator_mode")),
            criteria_scores=criteria_scores,
            passing_criteria=_string_list(value.get("passing_criteria")),
            failing_criteria=_string_list(value.get("failing_criteria")),
            blocker_notes=_string_list(value.get("blocker_notes")),
        )


@dataclass
class SprintNegotiationRound:
    sprint_id: str
    planner_mode: str = ""
    evaluator_mode: str = ""
    evaluator_status: str = ""
    objections: list[str] = field(default_factory=list)
    planner_response: list[str] = field(default_factory=list)
    recommended_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SprintNegotiationRound | None":
        if not isinstance(value, dict):
            return None
        sprint_id = _string(value.get("sprint_id"))
        if not sprint_id:
            return None
        return cls(
            sprint_id=sprint_id,
            planner_mode=_string(value.get("planner_mode")),
            evaluator_mode=_string(value.get("evaluator_mode")),
            evaluator_status=_string(value.get("evaluator_status")),
            objections=_string_list(value.get("objections")),
            planner_response=_string_list(value.get("planner_response")),
            recommended_action=_string(value.get("recommended_action")),
        )


@dataclass
class SprintRevision:
    revision_id: str
    sprint_id: str
    planner_mode: str = ""
    source_negotiation_action: str = ""
    must_fix: list[str] = field(default_factory=list)
    must_keep: list[str] = field(default_factory=list)
    revision_summary: str = ""
    revision_diff_summary: list[str] = field(default_factory=list)
    baseline_status: str = ""
    baseline_failing_criteria: list[str] = field(default_factory=list)
    outcome_status: str = ""
    outcome_failing_criteria: list[str] = field(default_factory=list)
    outcome_summary: str = ""
    improvement_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SprintRevision | None":
        if not isinstance(value, dict):
            return None
        revision_id = _string(value.get("revision_id"))
        sprint_id = _string(value.get("sprint_id"))
        if not revision_id or not sprint_id:
            return None
        return cls(
            revision_id=revision_id,
            sprint_id=sprint_id,
            planner_mode=_string(value.get("planner_mode")),
            source_negotiation_action=_string(value.get("source_negotiation_action")),
            must_fix=_string_list(value.get("must_fix")),
            must_keep=_string_list(value.get("must_keep")),
            revision_summary=_string(value.get("revision_summary")),
            revision_diff_summary=_string_list(value.get("revision_diff_summary")),
            baseline_status=_string(value.get("baseline_status")),
            baseline_failing_criteria=_string_list(value.get("baseline_failing_criteria")),
            outcome_status=_string(value.get("outcome_status")),
            outcome_failing_criteria=_string_list(value.get("outcome_failing_criteria")),
            outcome_summary=_string(value.get("outcome_summary")),
            improvement_status=_string(value.get("improvement_status")),
        )


@dataclass
class SprintExecutionAttempt:
    attempt_id: str
    sprint_id: str
    revision_id: str = ""
    execution_target_kind: str = ""
    execution_mode: str = ""
    changed_target_hints: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    execution_summary: str = ""
    artifact_root: str = ""
    artifact_kind: str = ""
    artifact_path: str = ""
    preview_command: str = ""
    trace_path: str = ""
    validation_command: str = ""
    validation_summary: str = ""
    failure_reason: str = ""
    status: str = ""
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SprintExecutionAttempt | None":
        if not isinstance(value, dict):
            return None
        attempt_id = _string(value.get("attempt_id"))
        sprint_id = _string(value.get("sprint_id"))
        if not attempt_id or not sprint_id:
            return None
        return cls(
            attempt_id=attempt_id,
            sprint_id=sprint_id,
            revision_id=_string(value.get("revision_id")),
            execution_target_kind=_string(value.get("execution_target_kind")),
            execution_mode=_string(value.get("execution_mode")),
            changed_target_hints=_string_list(value.get("changed_target_hints")),
            changed_files=_string_list(value.get("changed_files")),
            execution_summary=_string(value.get("execution_summary")),
            artifact_root=_string(value.get("artifact_root")),
            artifact_kind=_string(value.get("artifact_kind")),
            artifact_path=_string(value.get("artifact_path")),
            preview_command=_string(value.get("preview_command")),
            trace_path=_string(value.get("trace_path")),
            validation_command=_string(value.get("validation_command")),
            validation_summary=_string(value.get("validation_summary")),
            failure_reason=_string(value.get("failure_reason")),
            status=_string(value.get("status")),
            success=value.get("success") is True,
        )


@dataclass
class AppHarnessState:
    product_spec: ProductSpec | None = None
    evaluator_criteria: list[EvaluatorCriterion] = field(default_factory=list)
    planner_mode: str = ""
    active_sprint_contract: SprintContract | None = None
    planned_sprint_contracts: list[SprintContract] = field(default_factory=list)
    planning_rationale: list[str] = field(default_factory=list)
    sprint_negotiation_notes: list[str] = field(default_factory=list)
    latest_negotiation_round: SprintNegotiationRound | None = None
    negotiation_history: list[SprintNegotiationRound] = field(default_factory=list)
    latest_revision: SprintRevision | None = None
    revision_history: list[SprintRevision] = field(default_factory=list)
    latest_execution_attempt: SprintExecutionAttempt | None = None
    execution_history: list[SprintExecutionAttempt] = field(default_factory=list)
    retry_budget: int = 1
    retry_count: int = 0
    last_execution_gate_from: str = ""
    last_execution_gate_to: str = ""
    last_execution_gate_transition: str = ""
    last_policy_action: str = ""
    sprint_history: list[SprintContract] = field(default_factory=list)
    latest_sprint_evaluation: SprintEvaluation | None = None
    loop_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_spec": self.product_spec.to_dict() if self.product_spec else None,
            "evaluator_criteria": [item.to_dict() for item in self.evaluator_criteria],
            "planner_mode": self.planner_mode,
            "active_sprint_contract": self.active_sprint_contract.to_dict() if self.active_sprint_contract else None,
            "planned_sprint_contracts": [item.to_dict() for item in self.planned_sprint_contracts],
            "planning_rationale": list(self.planning_rationale),
            "sprint_negotiation_notes": list(self.sprint_negotiation_notes),
            "latest_negotiation_round": self.latest_negotiation_round.to_dict() if self.latest_negotiation_round else None,
            "negotiation_history": [item.to_dict() for item in self.negotiation_history],
            "latest_revision": self.latest_revision.to_dict() if self.latest_revision else None,
            "revision_history": [item.to_dict() for item in self.revision_history],
            "latest_execution_attempt": self.latest_execution_attempt.to_dict() if self.latest_execution_attempt else None,
            "execution_history": [item.to_dict() for item in self.execution_history],
            "retry_budget": self.retry_budget,
            "retry_count": self.retry_count,
            "last_execution_gate_from": self.last_execution_gate_from,
            "last_execution_gate_to": self.last_execution_gate_to,
            "last_execution_gate_transition": self.last_execution_gate_transition,
            "last_policy_action": self.last_policy_action,
            "sprint_history": [item.to_dict() for item in self.sprint_history],
            "latest_sprint_evaluation": self.latest_sprint_evaluation.to_dict() if self.latest_sprint_evaluation else None,
            "loop_status": self.loop_status,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "AppHarnessState | None":
        if not isinstance(value, dict):
            return None
        product_spec = ProductSpec.from_dict(value.get("product_spec"))
        evaluator_criteria = [
            item
            for raw in (value.get("evaluator_criteria") or [])
            if (item := EvaluatorCriterion.from_dict(raw)) is not None
        ]
        planner_mode = _string(value.get("planner_mode"))
        active_sprint_contract = SprintContract.from_dict(value.get("active_sprint_contract"))
        planned_sprint_contracts = [
            item
            for raw in (value.get("planned_sprint_contracts") or [])
            if (item := SprintContract.from_dict(raw)) is not None
        ]
        planning_rationale = _string_list(value.get("planning_rationale"))
        sprint_negotiation_notes = _string_list(value.get("sprint_negotiation_notes"))
        latest_negotiation_round = SprintNegotiationRound.from_dict(value.get("latest_negotiation_round"))
        negotiation_history = [
            item
            for raw in (value.get("negotiation_history") or [])
            if (item := SprintNegotiationRound.from_dict(raw)) is not None
        ]
        latest_revision = SprintRevision.from_dict(value.get("latest_revision"))
        revision_history = [
            item
            for raw in (value.get("revision_history") or [])
            if (item := SprintRevision.from_dict(raw)) is not None
        ]
        latest_execution_attempt = SprintExecutionAttempt.from_dict(value.get("latest_execution_attempt"))
        execution_history = [
            item
            for raw in (value.get("execution_history") or [])
            if (item := SprintExecutionAttempt.from_dict(raw)) is not None
        ]
        retry_budget = max(0, int(value.get("retry_budget") or 0))
        retry_count = max(0, int(value.get("retry_count") or 0))
        last_execution_gate_from = _string(value.get("last_execution_gate_from"))
        last_execution_gate_to = _string(value.get("last_execution_gate_to"))
        last_execution_gate_transition = _string(value.get("last_execution_gate_transition"))
        last_policy_action = _string(value.get("last_policy_action"))
        sprint_history = [
            item
            for raw in (value.get("sprint_history") or [])
            if (item := SprintContract.from_dict(raw)) is not None
        ]
        latest_sprint_evaluation = SprintEvaluation.from_dict(value.get("latest_sprint_evaluation"))
        loop_status = _string(value.get("loop_status"))
        if not any(
            [
                product_spec,
                evaluator_criteria,
                planner_mode,
                active_sprint_contract,
                planned_sprint_contracts,
                planning_rationale,
                sprint_negotiation_notes,
                latest_negotiation_round,
                negotiation_history,
                latest_revision,
                revision_history,
                latest_execution_attempt,
                execution_history,
                retry_budget,
                retry_count,
                last_execution_gate_from,
                last_execution_gate_to,
                last_execution_gate_transition,
                last_policy_action,
                sprint_history,
                latest_sprint_evaluation,
                loop_status,
            ]
        ):
            return None
        return cls(
            product_spec=product_spec,
            evaluator_criteria=evaluator_criteria,
            planner_mode=planner_mode,
            active_sprint_contract=active_sprint_contract,
            planned_sprint_contracts=planned_sprint_contracts,
            planning_rationale=planning_rationale,
            sprint_negotiation_notes=sprint_negotiation_notes,
            latest_negotiation_round=latest_negotiation_round,
            negotiation_history=negotiation_history,
            latest_revision=latest_revision,
            revision_history=revision_history,
            latest_execution_attempt=latest_execution_attempt,
            execution_history=execution_history,
            retry_budget=retry_budget or 1,
            retry_count=retry_count,
            last_execution_gate_from=last_execution_gate_from,
            last_execution_gate_to=last_execution_gate_to,
            last_execution_gate_transition=last_execution_gate_transition,
            last_policy_action=last_policy_action,
            sprint_history=sprint_history,
            latest_sprint_evaluation=latest_sprint_evaluation,
            loop_status=loop_status,
        )
