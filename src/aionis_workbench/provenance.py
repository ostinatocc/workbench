from __future__ import annotations

from .execution_packet import (
    ExecutionPacket,
    MaintenanceSummary,
    PatternSignalSummary,
    PlannerPacket,
    RoutingSignalSummary,
    StrategySummary,
    WorkflowSignalSummary,
)
from .session import SessionState


def dominant_trust_signal(session: SessionState) -> str:
    order = {
        "exact_task_signature": 3,
        "same_task_family": 2,
        "same_error_family": 1,
        "broader_similarity": 0,
    }
    best = "broader_similarity"
    for pattern in session.collaboration_patterns:
        level = (pattern.affinity_level or "broader_similarity").strip()
        if order.get(level, 0) > order.get(best, 0):
            best = level
    return best


def infer_role_sequence(session: SessionState) -> list[str]:
    if session.selected_role_sequence:
        return session.selected_role_sequence[:3]
    for pattern in session.collaboration_patterns:
        if pattern.kind == "role_sequence_strategy" and pattern.reuse_hint.strip():
            return [item.strip() for item in pattern.reuse_hint.split(",") if item.strip()][:3]
    return [packet.role for packet in session.delegation_packets[:3] if getattr(packet, "role", None)]


def build_provenance_surfaces(
    session: SessionState,
    packet: ExecutionPacket,
) -> tuple[PlannerPacket, StrategySummary, PatternSignalSummary, WorkflowSignalSummary, RoutingSignalSummary, MaintenanceSummary]:
    trusted_patterns = [
        pattern
        for pattern in session.collaboration_patterns
        if (pattern.affinity_level or "broader_similarity") != "broader_similarity" or pattern.confidence >= 0.75
    ]
    dominant_affinity = session.selected_trust_signal or dominant_trust_signal(session)
    preferred_artifact_refs = packet.artifact_refs[:3]
    role_sequence = infer_role_sequence(session)
    workflow_mode = "default"
    if packet.current_stage == "rollback_recovery":
        workflow_mode = "rollback_first"
    elif packet.current_stage == "paused_timeout":
        workflow_mode = "timeout_aware"
    elif packet.current_stage.startswith("paused_"):
        workflow_mode = "guarded_recovery"

    trusted_pattern_summaries = list(
        dict.fromkeys(f"[{item.role}/{item.kind}] {item.summary}" for item in trusted_patterns[:6])
    )[:4]
    existing_strategy = session.strategy_summary
    preferred_artifact_refs = (
        existing_strategy.preferred_artifact_refs[:3]
        if existing_strategy and existing_strategy.preferred_artifact_refs
        else preferred_artifact_refs
    )
    selected_working_set = (
        existing_strategy.selected_working_set[:6]
        if existing_strategy and existing_strategy.selected_working_set
        else packet.target_files[:6]
    )
    selected_validation_paths = (
        existing_strategy.selected_validation_paths[:3]
        if existing_strategy and existing_strategy.selected_validation_paths
        else packet.pending_validations[:3]
    )
    selected_pattern_summaries = (
        existing_strategy.selected_pattern_summaries[:4]
        if existing_strategy and existing_strategy.selected_pattern_summaries
        else session.selected_pattern_summaries[:4]
    )
    planner_packet = PlannerPacket(
        packet_version=packet.packet_version,
        current_stage=packet.current_stage,
        active_role=packet.active_role,
        task_brief=packet.task_brief,
        target_files=packet.target_files[:6],
        next_action=packet.next_action,
        trusted_pattern_summaries=trusted_pattern_summaries,
        preferred_artifact_refs=preferred_artifact_refs,
        pending_validations=packet.pending_validations[:3],
        unresolved_blockers=packet.unresolved_blockers[:4],
    )

    trust_phrase = {
        "exact_task_signature": "exact task signature matched prior successful work",
        "same_task_family": "same task family matched prior successful work",
        "same_error_family": "same error family matched prior recovery or validation work",
        "broader_similarity": "broader module similarity matched prior work",
    }[dominant_affinity]
    routing_phrase = ""
    if any(pattern.kind == "artifact_routing_strategy" for pattern in trusted_patterns):
        routing_phrase = " Routing feedback confirmed that prior agent handoffs can be reused directly."
    strategy_summary = StrategySummary(
        trust_signal=dominant_affinity,
        strategy_profile=session.selected_strategy_profile,
        validation_style=session.selected_validation_style,
        task_family=session.selected_task_family,
        family_scope=session.selected_family_scope,
        family_candidate_count=session.selected_family_candidate_count,
        selected_working_set=selected_working_set,
        selected_validation_paths=selected_validation_paths,
        selected_role_sequence=role_sequence,
        selected_pattern_summaries=selected_pattern_summaries,
        preferred_artifact_refs=preferred_artifact_refs,
        artifact_budget=session.selected_artifact_budget,
        memory_source_limit=session.selected_memory_source_limit,
        explanation=(
            f"Selected because {trust_phrase}."
            f" Family scope: {session.selected_family_scope or 'broader_similarity'}."
            f"{routing_phrase}"
        ).strip(),
    )

    pattern_signal_summary = PatternSignalSummary(
        trusted_pattern_count=len(trusted_patterns),
        contested_pattern_count=max(0, len(session.collaboration_patterns) - len(trusted_patterns)),
        trusted_patterns=trusted_pattern_summaries,
        dominant_affinity=dominant_affinity,
    )

    workflow_signal_summary = WorkflowSignalSummary(
        role_sequence=role_sequence,
        workflow_mode=workflow_mode,
        active_role=packet.active_role,
        stage=packet.current_stage,
    )

    hit_roles: list[str] = []
    miss_roles: list[str] = []
    routing_reasons: list[str] = []
    routed_artifact_ref_count = 0
    inherited_evidence_count = 0
    trusted_effective_scope = any(pattern.kind == "effective_edit_scope_strategy" for pattern in trusted_patterns)
    return_by_role = {item.role: item for item in session.delegation_returns if getattr(item, "role", "")}
    packet_by_role = {item.role: item for item in session.delegation_packets if getattr(item, "role", "")}
    for delegation_packet in session.delegation_packets:
        has_artifacts = bool(delegation_packet.preferred_artifact_refs)
        has_evidence = bool(delegation_packet.inherited_evidence)
        if has_artifacts or has_evidence:
            hit_roles.append(delegation_packet.role)
        else:
            miss_roles.append(delegation_packet.role)
        routed_artifact_ref_count += len(delegation_packet.preferred_artifact_refs)
        inherited_evidence_count += len(delegation_packet.inherited_evidence)
        if delegation_packet.routing_reason:
            routing_reasons.append(f"{delegation_packet.role}: {delegation_packet.routing_reason}")

    routing_signal_summary = RoutingSignalSummary(
        task_family=session.selected_task_family,
        family_scope=session.selected_family_scope or dominant_affinity,
        routed_role_count=len(hit_roles),
        routed_artifact_ref_count=routed_artifact_ref_count,
        inherited_evidence_count=inherited_evidence_count,
        implementer_effective_scope=(
            return_by_role["implementer"].working_set[:6]
            if "implementer" in return_by_role
            else []
        ),
        implementer_artifact_scope=(
            (
                return_by_role["implementer"].artifact_refs
                or packet_by_role["implementer"].preferred_artifact_refs
            )[:4]
            if "implementer" in return_by_role and "implementer" in packet_by_role
            else (
                return_by_role["implementer"].artifact_refs[:4]
                if "implementer" in return_by_role
                else (
                    packet_by_role["implementer"].preferred_artifact_refs[:4]
                    if "implementer" in packet_by_role
                    else []
                )
            )
        ),
        implementer_scope_narrowed=(
            "implementer" in return_by_role
            and bool(return_by_role["implementer"].working_set)
            and (
                (
                    "implementer" in packet_by_role
                    and return_by_role["implementer"].working_set[:6] != packet_by_role["implementer"].working_set[:6]
                )
                or trusted_effective_scope
            )
        ),
        implementer_scope_source=(
            "investigator_narrowed"
            if (
                "implementer" in return_by_role
                and bool(return_by_role["implementer"].working_set)
                and (
                    (
                        "implementer" in packet_by_role
                        and return_by_role["implementer"].working_set[:6] != packet_by_role["implementer"].working_set[:6]
                    )
                    or trusted_effective_scope
                )
            )
            else "delegation_packet"
        ),
        hit_roles=hit_roles[:6],
        miss_roles=miss_roles[:6],
        routing_reasons=routing_reasons[:6],
    )

    suppressed_count = sum(1 for item in session.forgetting_backlog if item.state == "suppressed")
    evicted_count = sum(1 for item in session.forgetting_backlog if item.state == "evicted")
    learning = session.continuity_snapshot.get("learning") if isinstance(session.continuity_snapshot, dict) else {}
    passive = session.continuity_snapshot.get("passive_observation") if isinstance(session.continuity_snapshot, dict) else {}
    auto_learning_status = "manual_only"
    last_learning_source = ""
    passive_observation_status = "none"
    observed_changed_file_count = 0
    if isinstance(learning, dict) and learning:
        auto_learning_status = "auto_absorbed" if learning.get("auto_absorbed") else "recorded"
        last_learning_source = str(learning.get("source") or "").strip()
    if isinstance(passive, dict) and passive:
        passive_observation_status = "recorded" if passive.get("recorded") else "captured"
        changed_files = passive.get("changed_files")
        if isinstance(changed_files, list):
            observed_changed_file_count = len([item for item in changed_files if isinstance(item, str) and item.strip()])
    maintenance_action = "keep current memory set stable"
    if evicted_count:
        maintenance_action = "review evicted guidance before promoting new overlapping insights"
    elif suppressed_count:
        maintenance_action = "prefer newer insights and avoid reseeding suppressed guidance"
    elif passive_observation_status == "recorded":
        maintenance_action = "reuse the latest observed changed files and validation path before widening scope"
    elif auto_learning_status == "auto_absorbed":
        maintenance_action = "reuse the latest auto-absorbed success path before falling back to manual ingest"
    elif session.promoted_insights:
        maintenance_action = "promote the latest validated strategy and artifact references"
    maintenance_summary = MaintenanceSummary(
        promoted_insight_count=len(session.promoted_insights),
        forgetting_backlog_count=len(session.forgetting_backlog),
        suppressed_count=suppressed_count,
        evicted_count=evicted_count,
        auto_learning_status=auto_learning_status,
        last_learning_source=last_learning_source,
        passive_observation_status=passive_observation_status,
        observed_changed_file_count=observed_changed_file_count,
        recommended_action=maintenance_action,
    )
    return (
        planner_packet,
        strategy_summary,
        pattern_signal_summary,
        workflow_signal_summary,
        routing_signal_summary,
        maintenance_summary,
    )
