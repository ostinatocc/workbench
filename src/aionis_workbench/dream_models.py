from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DreamSample:
    task_id: str
    project_identity: str = ""
    project_scope: str = ""
    task_family: str = ""
    source: str = ""
    strategy_profile: str = ""
    validation_style: str = ""
    validation_command: str = ""
    working_set: list[str] = field(default_factory=list)
    observed_changed_files: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    doc_input: str = ""
    source_doc_id: str = ""
    doc_action: str = ""
    handoff_anchor: str = ""
    selected_tool: str = ""
    event_source: str = ""
    recorded_at: str = ""
    reviewer_standard: str = ""
    reviewer_required_outputs: list[str] = field(default_factory=list)
    reviewer_acceptance_checks: list[str] = field(default_factory=list)
    reviewer_pack_source: str = ""
    reviewer_selected_tool: str = ""
    reviewer_resume_anchor: str = ""
    reviewer_ready_required: bool = False
    reviewer_rollback_required: bool = False
    instrumentation_status: str = "unknown"
    artifact_hit_rate: float = 0.0
    pattern_hit_count: int = 0
    suppressed_forgetting_count: int = 0
    evicted_forgetting_count: int = 0
    stale_guidance_count: int = 0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "DreamSample | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class StrategyCandidate:
    candidate_id: str
    task_family: str
    strategy_profile: str
    validation_style: str
    dominant_validation_command: str
    dominant_working_set: list[str] = field(default_factory=list)
    dominant_doc_input: str = ""
    dominant_source_doc_id: str = ""
    dominant_doc_action: str = ""
    dominant_selected_tool: str = ""
    dominant_event_source: str = ""
    latest_recorded_at: str = ""
    doc_sample_count: int = 0
    editor_sync_count: int = 0
    dominant_reviewer_standard: str = ""
    dominant_reviewer_outputs: list[str] = field(default_factory=list)
    dominant_reviewer_checks: list[str] = field(default_factory=list)
    dominant_reviewer_pack_source: str = ""
    dominant_reviewer_selected_tool: str = ""
    dominant_reviewer_resume_anchor: str = ""
    reviewer_sample_count: int = 0
    reviewer_ready_count: int = 0
    reviewer_rollback_count: int = 0
    supporting_task_ids: list[str] = field(default_factory=list)
    sample_count: int = 0
    recent_success_count: int = 0
    avg_artifact_hit_rate: float = 0.0
    avg_pattern_hit_count: float = 0.0
    source_weight: float = 0.0
    suppressed_forgetting_count: int = 0
    evicted_forgetting_count: int = 0
    stale_guidance_count: int = 0
    status: str = "candidate"
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "StrategyCandidate | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class CandidateVerification:
    candidate_id: str
    task_family: str
    coverage_count: int = 0
    heldout_count: int = 0
    heldout_match_rate: float = 0.0
    regression_risk: float = 0.0
    verification_status: str = "pending"
    verification_reason: str = ""
    verified_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "CandidateVerification | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)


@dataclass
class PromotedPrior:
    prior_id: str
    task_family: str
    strategy_profile: str
    validation_style: str
    dominant_validation_command: str
    dominant_working_set: list[str] = field(default_factory=list)
    dominant_doc_input: str = ""
    dominant_source_doc_id: str = ""
    dominant_doc_action: str = ""
    dominant_selected_tool: str = ""
    dominant_event_source: str = ""
    latest_recorded_at: str = ""
    doc_sample_count: int = 0
    editor_sync_count: int = 0
    dominant_reviewer_standard: str = ""
    dominant_reviewer_outputs: list[str] = field(default_factory=list)
    dominant_reviewer_checks: list[str] = field(default_factory=list)
    dominant_reviewer_pack_source: str = ""
    dominant_reviewer_selected_tool: str = ""
    dominant_reviewer_resume_anchor: str = ""
    reviewer_sample_count: int = 0
    reviewer_ready_count: int = 0
    reviewer_rollback_count: int = 0
    promotion_status: str = "trial"
    promotion_reason: str = ""
    confidence: float = 0.0
    sample_count: int = 0
    recent_success_count: int = 0
    verification_summary: str = ""
    promoted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "PromotedPrior | None":
        if not isinstance(value, dict):
            return None
        return cls(**value)
