from __future__ import annotations

from dataclasses import dataclass, field

from .reviewer_contracts import ResumeAnchor, ReviewerContract


@dataclass
class ExecutionPacket:
    packet_version: int = 1
    current_stage: str = "pending"
    active_role: str = "orchestrator"
    task_brief: str = ""
    target_files: list[str] = field(default_factory=list)
    next_action: str | None = None
    hard_constraints: list[str] = field(default_factory=list)
    accepted_facts: list[str] = field(default_factory=list)
    pending_validations: list[str] = field(default_factory=list)
    unresolved_blockers: list[str] = field(default_factory=list)
    rollback_notes: list[str] = field(default_factory=list)
    review_contract: ReviewerContract | None = None
    reviewer_ready_required: bool = False
    resume_anchor: ResumeAnchor | None = None
    artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict | None) -> "ExecutionPacket | None":
        if not isinstance(value, dict):
            return None
        data = dict(value)
        data["review_contract"] = ReviewerContract.from_dict(data.get("review_contract"))
        data["reviewer_ready_required"] = data.get("reviewer_ready_required") is True
        data["resume_anchor"] = ResumeAnchor.from_dict(data.get("resume_anchor"))
        return cls(**data)


@dataclass
class ExecutionPacketSummary:
    packet_version: int = 1
    current_stage: str = "pending"
    active_role: str = "orchestrator"
    task_brief: str = ""
    next_action: str | None = None
    target_file_count: int = 0
    pending_validation_count: int = 0
    unresolved_blocker_count: int = 0
    review_contract_present: bool = False
    reviewer_ready_required: bool = False
    resume_anchor_present: bool = False
    artifact_ref_count: int = 0
    evidence_ref_count: int = 0

    @classmethod
    def from_dict(cls, value: dict | None) -> "ExecutionPacketSummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class PlannerPacket:
    packet_version: int = 1
    current_stage: str = "pending"
    active_role: str = "orchestrator"
    task_brief: str = ""
    target_files: list[str] = field(default_factory=list)
    next_action: str | None = None
    trusted_pattern_summaries: list[str] = field(default_factory=list)
    preferred_artifact_refs: list[str] = field(default_factory=list)
    pending_validations: list[str] = field(default_factory=list)
    unresolved_blockers: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict | None) -> "PlannerPacket | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class StrategySummary:
    trust_signal: str = "broader_similarity"
    strategy_profile: str = "broad_discovery"
    validation_style: str = "targeted_then_expand"
    task_family: str = ""
    family_scope: str = "broader_similarity"
    family_candidate_count: int = 0
    selected_working_set: list[str] = field(default_factory=list)
    selected_validation_paths: list[str] = field(default_factory=list)
    selected_role_sequence: list[str] = field(default_factory=list)
    preferred_artifact_refs: list[str] = field(default_factory=list)
    selected_pattern_summaries: list[str] = field(default_factory=list)
    artifact_budget: int = 6
    memory_source_limit: int = 14
    explanation: str = ""

    @classmethod
    def from_dict(cls, value: dict | None) -> "StrategySummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class PatternSignalSummary:
    trusted_pattern_count: int = 0
    contested_pattern_count: int = 0
    trusted_patterns: list[str] = field(default_factory=list)
    dominant_affinity: str = "broader_similarity"

    @classmethod
    def from_dict(cls, value: dict | None) -> "PatternSignalSummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class WorkflowSignalSummary:
    role_sequence: list[str] = field(default_factory=list)
    workflow_mode: str = "default"
    active_role: str = "orchestrator"
    stage: str = "pending"

    @classmethod
    def from_dict(cls, value: dict | None) -> "WorkflowSignalSummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class RoutingSignalSummary:
    task_family: str = ""
    family_scope: str = "broader_similarity"
    routed_role_count: int = 0
    routed_artifact_ref_count: int = 0
    inherited_evidence_count: int = 0
    hit_roles: list[str] = field(default_factory=list)
    miss_roles: list[str] = field(default_factory=list)
    routing_reasons: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict | None) -> "RoutingSignalSummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class MaintenanceSummary:
    promoted_insight_count: int = 0
    forgetting_backlog_count: int = 0
    suppressed_count: int = 0
    evicted_count: int = 0
    auto_learning_status: str = "manual_only"
    last_learning_source: str = ""
    passive_observation_status: str = "none"
    observed_changed_file_count: int = 0
    recommended_action: str = ""

    @classmethod
    def from_dict(cls, value: dict | None) -> "MaintenanceSummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class InstrumentationSummary:
    task_family: str = ""
    family_scope: str = "broader_similarity"
    family_hit: bool = False
    family_reason: str = ""
    selected_pattern_hit_count: int = 0
    selected_pattern_miss_count: int = 0
    routed_artifact_known_count: int = 0
    routed_artifact_same_family_count: int = 0
    routed_artifact_other_family_count: int = 0
    routed_artifact_unknown_count: int = 0
    routed_artifact_hit_rate: float = 0.0
    routed_same_family_task_ids: list[str] = field(default_factory=list)
    routed_other_family_task_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict | None) -> "InstrumentationSummary | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)
