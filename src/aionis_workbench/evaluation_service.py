from __future__ import annotations

import json
from typing import Any, Callable

from .aionis_bridge import _build_task_session_transition_guards
from .controller_shell import controller_action_bar_payload
from .controller_state import apply_session_controller_gates
from .doc_learning import build_doc_learning_record
from .execution_packet import InstrumentationSummary
from .failure_classification import classify_execution_failure_reason
from .session import SessionState, load_recent_sessions, load_session
from .statusline import build_statusline_input, render_statusline


def _count_legacy_prior_lines(shared_memory: list[str]) -> int:
    prefixes = (
        "Prior strategy working set: ",
        "Prior strategy validation: ",
        "Prior planner next action: ",
        "Prior collaboration pattern: ",
        "Prior artifact reference: ",
        "Prior insight: ",
        "Prior trusted pattern: ",
    )
    return sum(
        1
        for item in shared_memory
        if isinstance(item, str) and any(item.startswith(prefix) for prefix in prefixes)
    )


def _instrumentation_grade(instrumentation: InstrumentationSummary | None) -> tuple[str, str]:
    if instrumentation is None:
        return ("unknown", "No instrumentation summary was available for this session.")
    if not instrumentation.task_family:
        return ("unknown", "Task family was not established for this session.")
    if not instrumentation.family_hit:
        return ("weak_match", instrumentation.family_reason or "Task family did not match the selected reuse scope.")
    if instrumentation.routed_artifact_hit_rate >= 1.0 and instrumentation.selected_pattern_hit_count > 0:
        return ("strong_match", "Family, pattern reuse, and routed artifacts all aligned with prior successful work.")
    if instrumentation.routed_artifact_hit_rate >= 0.8:
        return ("usable_match", "Family alignment is good and most routed artifacts came from the same family.")
    return ("weak_match", "Family matched, but pattern reuse or routed artifacts were only partially aligned.")


def _controller_status_for_session(session: SessionState) -> str:
    status = str(session.status or "").strip()
    if status == "paused":
        return "paused"
    if status in {"completed", "validated"}:
        return "completed"
    return "active"


def _controller_view_from_session(session: SessionState) -> dict[str, Any]:
    controller_status = _controller_status_for_session(session)
    guards = _build_task_session_transition_guards(controller_status)
    blocked_actions = [
        str(item.get("action") or "").strip()
        for item in guards
        if item.get("allowed") is not True and str(item.get("action") or "").strip()
    ]
    guard_reasons = [
        {
            "action": str(item.get("action") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
        }
        for item in guards
        if item.get("allowed") is not True
        and str(item.get("action") or "").strip()
        and str(item.get("reason") or "").strip()
    ][:6]
    controller = {
        "status": controller_status,
        "allowed_actions": [
            str(item.get("action") or "").strip()
            for item in guards
            if item.get("allowed") is True and str(item.get("action") or "").strip()
        ],
        "blocked_actions": blocked_actions,
        "transition_count": 0,
        "last_transition_kind": "",
        "last_transition_at": "",
        "last_transition_detail": "",
        "last_startup_mode": "",
        "last_handoff_anchor": "",
        "last_event_text": "",
        "guard_reasons": guard_reasons,
        "projection_source": "session_status",
        "source_status": str(session.status or ""),
    }
    return apply_session_controller_gates(controller, session) or controller


class EvaluationService:
    def __init__(
        self,
        *,
        repo_root: str,
        project_identity: str,
        project_scope: str,
        bootstrap_snapshot_fn: Callable[[], dict[str, Any]],
        bootstrap_canonical_views_fn: Callable[[dict[str, Any]], dict[str, Any]],
        save_session_fn: Callable[[SessionState], Any],
        dashboard_fn: Callable[..., dict[str, Any]],
        background_status_fn: Callable[[], dict[str, Any]],
        host_contract_fn: Callable[[], dict[str, Any]],
    ) -> None:
        self._repo_root = repo_root
        self._project_identity = project_identity
        self._project_scope = project_scope
        self._bootstrap_snapshot = bootstrap_snapshot_fn
        self._bootstrap_canonical_views = bootstrap_canonical_views_fn
        self._save_session = save_session_fn
        self._dashboard = dashboard_fn
        self._background_status = background_status_fn
        self._host_contract = host_contract_fn

    def canonical_surface(self, session: SessionState) -> dict[str, Any]:
        return {
            "execution_packet": session.execution_packet.__dict__ if session.execution_packet else None,
            "execution_packet_summary": (
                session.execution_packet_summary.__dict__ if session.execution_packet_summary else None
            ),
            "planner_packet": session.planner_packet.__dict__ if session.planner_packet else None,
            "strategy_summary": session.strategy_summary.__dict__ if session.strategy_summary else None,
            "pattern_signal_summary": session.pattern_signal_summary.__dict__ if session.pattern_signal_summary else None,
            "workflow_signal_summary": session.workflow_signal_summary.__dict__ if session.workflow_signal_summary else None,
            "routing_signal_summary": session.routing_signal_summary.__dict__ if session.routing_signal_summary else None,
            "maintenance_summary": session.maintenance_summary.__dict__ if session.maintenance_summary else None,
            "instrumentation_summary": (
                session.instrumentation_summary.__dict__ if session.instrumentation_summary else None
            ),
            "continuity_snapshot": session.continuity_snapshot,
            "context_layers_snapshot": session.context_layers_snapshot,
        }

    def canonical_views(self, session: SessionState) -> dict[str, Any]:
        planner = session.planner_packet
        execution_packet = session.execution_packet
        strategy = session.strategy_summary
        workflow = session.workflow_signal_summary
        routing = session.routing_signal_summary
        maintenance = session.maintenance_summary
        instrumentation = session.instrumentation_summary
        pattern = session.pattern_signal_summary
        context = session.context_layers_snapshot or {}
        continuity = session.continuity_snapshot or {}
        validation = session.last_validation_result or {}
        instrumentation_grade, instrumentation_explanation = _instrumentation_grade(instrumentation)
        continuity_pack = session.continuity_review_pack
        evolution_pack = session.evolution_review_pack
        app_harness = session.app_harness_state
        product_spec = app_harness.product_spec if app_harness else None
        active_sprint = app_harness.active_sprint_contract if app_harness else None
        active_sprint_id = active_sprint.sprint_id if active_sprint else ""
        latest_evaluation = (
            app_harness.latest_sprint_evaluation
            if app_harness
            and app_harness.latest_sprint_evaluation
            and app_harness.latest_sprint_evaluation.sprint_id == active_sprint_id
            else None
        )
        latest_visible_execution = (
            app_harness.latest_execution_attempt
            if app_harness and app_harness.latest_execution_attempt
            else (app_harness.execution_history[-1] if app_harness and app_harness.execution_history else None)
        )
        current_sprint_execution_count = (
            sum(
                1
                for item in app_harness.execution_history
                if isinstance(item.sprint_id, str) and item.sprint_id == active_sprint_id
            )
            if app_harness and active_sprint_id
            else 0
        )
        replan_depth = active_sprint_id.count("-replan-") if active_sprint_id else 0
        replan_root_sprint_id = active_sprint_id.split("-replan-", 1)[0] if active_sprint_id else ""
        policy = {
            "execution_outcome_ready": False,
            "execution_gate": "",
            "execution_focus": "",
            "next_sprint_ready": False,
            "next_sprint_candidate_id": "",
            "retry_available": False,
            "retry_remaining": 0,
            "recommended_next_action": "",
        }
        if app_harness:
            from .app_harness_service import (
                _derive_execution_outcome_projection,
                _derive_policy_stage,
                _derive_post_revision_policy,
                _latest_execution_attempt_for_sprint,
            )

            policy = _derive_post_revision_policy(app_harness)
            latest_attempt = _latest_execution_attempt_for_sprint(
                app_harness,
                sprint_id=active_sprint_id,
            )
            execution_projection = _derive_execution_outcome_projection(latest_attempt)
        else:
            latest_attempt = None
            execution_projection = {
                "execution_outcome_ready": False,
                "execution_gate": "",
                "execution_focus": "",
            }
        policy_stage = (
            _derive_policy_stage(active_sprint_id)
            if app_harness and active_sprint_id
            else "base"
        )
        return {
            "task_state": {
                "task_id": session.task_id,
                "status": session.status,
                "project_scope": session.project_scope,
                "last_result_preview": session.last_result_preview,
                "aionis_replay_run_id": session.aionis_replay_run_id,
                "validation_ok": validation.get("ok"),
                "validation_summary": validation.get("summary"),
            },
            "planner": {
                "stage": planner.current_stage if planner else None,
                "active_role": planner.active_role if planner else None,
                "next_action": planner.next_action if planner else None,
                "target_files": planner.target_files[:6] if planner else [],
                "pending_validations": planner.pending_validations[:3] if planner else [],
                "blockers": planner.unresolved_blockers[:4] if planner else [],
            },
            "reviewer": {
                "standard": (
                    execution_packet.review_contract.standard
                    if execution_packet and execution_packet.review_contract
                    else None
                ),
                "required_outputs": (
                    execution_packet.review_contract.required_outputs[:4]
                    if execution_packet and execution_packet.review_contract
                    else []
                ),
                "acceptance_checks": (
                    execution_packet.review_contract.acceptance_checks[:4]
                    if execution_packet and execution_packet.review_contract
                    else []
                ),
                "rollback_required": (
                    execution_packet.review_contract.rollback_required
                    if execution_packet and execution_packet.review_contract
                    else False
                ),
                "ready_required": execution_packet.reviewer_ready_required if execution_packet else False,
                "resume_anchor": (
                    execution_packet.resume_anchor.anchor
                    if execution_packet and execution_packet.resume_anchor
                    else None
                ),
                "resume_file": (
                    execution_packet.resume_anchor.file_path
                    if execution_packet and execution_packet.resume_anchor
                    else None
                ),
            },
            "review_packs": {
                "continuity": {
                    "pack_version": continuity_pack.pack_version if continuity_pack else None,
                    "source": continuity_pack.source if continuity_pack else None,
                    "standard": (
                        continuity_pack.review_contract.standard
                        if continuity_pack and continuity_pack.review_contract
                        else None
                    ),
                    "selected_tool": continuity_pack.selected_tool if continuity_pack else None,
                    "next_action": continuity_pack.next_action if continuity_pack else None,
                    "target_files": continuity_pack.target_files[:4] if continuity_pack else [],
                    "artifact_refs": continuity_pack.artifact_refs[:4] if continuity_pack else [],
                },
                "evolution": {
                    "pack_version": evolution_pack.pack_version if evolution_pack else None,
                    "source": evolution_pack.source if evolution_pack else None,
                    "standard": (
                        evolution_pack.review_contract.standard
                        if evolution_pack and evolution_pack.review_contract
                        else None
                    ),
                    "selected_tool": evolution_pack.selected_tool if evolution_pack else None,
                    "next_action": evolution_pack.next_action if evolution_pack else None,
                    "target_files": evolution_pack.target_files[:4] if evolution_pack else [],
                    "artifact_refs": evolution_pack.artifact_refs[:4] if evolution_pack else [],
                },
            },
            "app_harness": {
                "product_spec": {
                    "title": product_spec.title if product_spec else "",
                    "prompt": product_spec.prompt if product_spec else "",
                    "app_type": product_spec.app_type if product_spec else "",
                    "feature_count": len(product_spec.features) if product_spec else 0,
                    "feature_groups": list((product_spec.feature_groups or {}).keys())[:4] if product_spec else [],
                    "stack": product_spec.stack[:4] if product_spec else [],
                    "sprint_ids": product_spec.sprint_ids[:6] if product_spec else [],
                },
                "planner_mode": app_harness.planner_mode if app_harness else "",
                "active_sprint_contract": {
                    "sprint_id": active_sprint.sprint_id if active_sprint else "",
                    "goal": active_sprint.goal if active_sprint else "",
                    "scope": active_sprint.scope[:4] if active_sprint else [],
                    "acceptance_checks": active_sprint.acceptance_checks[:3] if active_sprint else [],
                    "done_definition": active_sprint.done_definition[:3] if active_sprint else [],
                    "proposed_by": active_sprint.proposed_by if active_sprint else "",
                    "approved": active_sprint.approved if active_sprint else False,
                },
                "planned_sprint_contracts": [
                    {
                        "sprint_id": item.sprint_id,
                        "goal": item.goal,
                        "scope": item.scope[:4],
                        "proposed_by": item.proposed_by,
                        "approved": item.approved,
                    }
                    for item in (app_harness.planned_sprint_contracts[:3] if app_harness else [])
                ],
                "planning_rationale": app_harness.planning_rationale[:4] if app_harness else [],
                "sprint_negotiation_notes": app_harness.sprint_negotiation_notes[:4] if app_harness else [],
                "latest_negotiation_round": {
                    "sprint_id": app_harness.latest_negotiation_round.sprint_id if app_harness and app_harness.latest_negotiation_round else "",
                    "planner_mode": app_harness.latest_negotiation_round.planner_mode if app_harness and app_harness.latest_negotiation_round else "",
                    "evaluator_mode": app_harness.latest_negotiation_round.evaluator_mode if app_harness and app_harness.latest_negotiation_round else "",
                    "evaluator_status": app_harness.latest_negotiation_round.evaluator_status if app_harness and app_harness.latest_negotiation_round else "",
                    "objections": app_harness.latest_negotiation_round.objections[:4] if app_harness and app_harness.latest_negotiation_round else [],
                    "planner_response": app_harness.latest_negotiation_round.planner_response[:4] if app_harness and app_harness.latest_negotiation_round else [],
                    "recommended_action": app_harness.latest_negotiation_round.recommended_action if app_harness and app_harness.latest_negotiation_round else "",
                },
                "negotiation_history_count": len(app_harness.negotiation_history) if app_harness else 0,
                "latest_revision": {
                    "revision_id": app_harness.latest_revision.revision_id if app_harness and app_harness.latest_revision else "",
                    "sprint_id": app_harness.latest_revision.sprint_id if app_harness and app_harness.latest_revision else "",
                    "planner_mode": app_harness.latest_revision.planner_mode if app_harness and app_harness.latest_revision else "",
                    "source_negotiation_action": app_harness.latest_revision.source_negotiation_action if app_harness and app_harness.latest_revision else "",
                    "must_fix": app_harness.latest_revision.must_fix[:4] if app_harness and app_harness.latest_revision else [],
                    "must_keep": app_harness.latest_revision.must_keep[:4] if app_harness and app_harness.latest_revision else [],
                    "revision_summary": app_harness.latest_revision.revision_summary if app_harness and app_harness.latest_revision else "",
                    "revision_diff_summary": app_harness.latest_revision.revision_diff_summary[:3] if app_harness and app_harness.latest_revision else [],
                    "baseline_status": app_harness.latest_revision.baseline_status if app_harness and app_harness.latest_revision else "",
                    "baseline_failing_criteria": app_harness.latest_revision.baseline_failing_criteria[:4] if app_harness and app_harness.latest_revision else [],
                    "outcome_status": app_harness.latest_revision.outcome_status if app_harness and app_harness.latest_revision else "",
                    "outcome_failing_criteria": app_harness.latest_revision.outcome_failing_criteria[:4] if app_harness and app_harness.latest_revision else [],
                    "outcome_summary": app_harness.latest_revision.outcome_summary if app_harness and app_harness.latest_revision else "",
                    "improvement_status": app_harness.latest_revision.improvement_status if app_harness and app_harness.latest_revision else "",
                },
                "revision_history_count": len(app_harness.revision_history) if app_harness else 0,
                "latest_execution_attempt": {
                    "attempt_id": latest_visible_execution.attempt_id if latest_visible_execution else "",
                    "sprint_id": latest_visible_execution.sprint_id if latest_visible_execution else "",
                    "revision_id": latest_visible_execution.revision_id if latest_visible_execution else "",
                    "execution_target_kind": latest_visible_execution.execution_target_kind if latest_visible_execution else "",
                    "execution_mode": latest_visible_execution.execution_mode if latest_visible_execution else "",
                    "changed_target_hints": latest_visible_execution.changed_target_hints[:4] if latest_visible_execution else [],
                    "changed_files": latest_visible_execution.changed_files[:8] if latest_visible_execution else [],
                    "execution_summary": latest_visible_execution.execution_summary if latest_visible_execution else "",
                    "artifact_root": latest_visible_execution.artifact_root if latest_visible_execution else "",
                    "artifact_kind": latest_visible_execution.artifact_kind if latest_visible_execution else "",
                    "artifact_path": latest_visible_execution.artifact_path if latest_visible_execution else "",
                    "preview_command": latest_visible_execution.preview_command if latest_visible_execution else "",
                    "validation_command": latest_visible_execution.validation_command if latest_visible_execution else "",
                    "validation_summary": latest_visible_execution.validation_summary if latest_visible_execution else "",
                    "failure_reason": latest_visible_execution.failure_reason if latest_visible_execution else "",
                    "failure_class": (
                        classify_execution_failure_reason(latest_visible_execution.failure_reason)
                        if latest_visible_execution
                        else ""
                    ),
                    "status": latest_visible_execution.status if latest_visible_execution else "",
                    "success": latest_visible_execution.success if latest_visible_execution else False,
                },
                "execution_history_count": len(app_harness.execution_history) if app_harness else 0,
                "current_sprint_execution_count": current_sprint_execution_count,
                "policy_stage": policy_stage,
                "replan_depth": replan_depth,
                "replan_root_sprint_id": replan_root_sprint_id,
                "retry_budget": app_harness.retry_budget if app_harness else 0,
                "retry_count": app_harness.retry_count if app_harness else 0,
                "last_execution_gate_from": app_harness.last_execution_gate_from if app_harness else "",
                "last_execution_gate_to": app_harness.last_execution_gate_to if app_harness else "",
                "last_execution_gate_transition": app_harness.last_execution_gate_transition if app_harness else "",
                "last_policy_action": app_harness.last_policy_action if app_harness else "",
                "execution_outcome_ready": bool(policy.get("execution_outcome_ready")),
                "execution_gate": str(policy.get("execution_gate") or execution_projection.get("execution_gate") or ""),
                "execution_focus": str(policy.get("execution_focus") or execution_projection.get("execution_focus") or ""),
                "retry_available": bool(policy.get("retry_available")),
                "retry_remaining": int(policy.get("retry_remaining") or 0),
                "next_sprint_ready": bool(policy.get("next_sprint_ready")),
                "next_sprint_candidate_id": str(policy.get("next_sprint_candidate_id") or ""),
                "recommended_next_action": str(policy.get("recommended_next_action") or ""),
                "latest_sprint_evaluation": {
                    "sprint_id": latest_evaluation.sprint_id if latest_evaluation else "",
                    "status": latest_evaluation.status if latest_evaluation else "",
                    "summary": latest_evaluation.summary if latest_evaluation else "",
                    "evaluator_mode": latest_evaluation.evaluator_mode if latest_evaluation else "",
                    "criteria_scores": dict(latest_evaluation.criteria_scores) if latest_evaluation else {},
                    "passing_criteria": latest_evaluation.passing_criteria[:4] if latest_evaluation else [],
                    "failing_criteria": latest_evaluation.failing_criteria[:4] if latest_evaluation else [],
                    "blocker_notes": latest_evaluation.blocker_notes[:4] if latest_evaluation else [],
                },
                "evaluator_criteria_count": len(app_harness.evaluator_criteria) if app_harness else 0,
                "loop_status": app_harness.loop_status if app_harness else "",
            },
            "strategy": {
                "trust_signal": strategy.trust_signal if strategy else None,
                "task_family": strategy.task_family if strategy else None,
                "family_scope": strategy.family_scope if strategy else None,
                "family_candidate_count": strategy.family_candidate_count if strategy else 0,
                "strategy_profile": strategy.strategy_profile if strategy else None,
                "validation_style": strategy.validation_style if strategy else None,
                "role_sequence": strategy.selected_role_sequence[:3] if strategy else [],
                "working_set": strategy.selected_working_set[:6] if strategy else [],
                "validation_paths": strategy.selected_validation_paths[:3] if strategy else [],
                "selected_patterns": strategy.selected_pattern_summaries[:4] if strategy else [],
                "preferred_artifacts": strategy.preferred_artifact_refs[:4] if strategy else [],
                "artifact_budget": strategy.artifact_budget if strategy else None,
                "memory_source_limit": strategy.memory_source_limit if strategy else None,
                "specialist_recommendation": strategy.specialist_recommendation if strategy else None,
                "explanation": strategy.explanation if strategy else None,
            },
            "routing": {
                "summary": {
                    "task_family": routing.task_family if routing else None,
                    "family_scope": routing.family_scope if routing else None,
                    "routed_role_count": routing.routed_role_count if routing else 0,
                    "routed_artifact_ref_count": routing.routed_artifact_ref_count if routing else 0,
                    "inherited_evidence_count": routing.inherited_evidence_count if routing else 0,
                    "implementer_effective_scope": routing.implementer_effective_scope[:6] if routing else [],
                    "implementer_artifact_scope": routing.implementer_artifact_scope[:4] if routing else [],
                    "implementer_scope_narrowed": routing.implementer_scope_narrowed if routing else False,
                    "implementer_scope_source": routing.implementer_scope_source if routing else "",
                    "specialist_handoff_chain": routing.specialist_handoff_chain[:6] if routing else [],
                    "specialist_next_actions": routing.specialist_next_actions[:6] if routing else [],
                    "verifier_blockers": routing.verifier_blockers[:4] if routing else [],
                    "verifier_validation_intent": routing.verifier_validation_intent[:4] if routing else [],
                    "hit_roles": routing.hit_roles[:6] if routing else [],
                    "miss_roles": routing.miss_roles[:6] if routing else [],
                    "routing_reasons": routing.routing_reasons[:6] if routing else [],
                },
                **{
                    packet.role: {
                        "artifacts": packet.preferred_artifact_refs[:4],
                        "inherited_evidence": packet.inherited_evidence[:4],
                        "routing_reason": packet.routing_reason,
                    }
                    for packet in session.delegation_packets
                },
            },
            "workflow": {
                "workflow_mode": workflow.workflow_mode if workflow else None,
                "stage": workflow.stage if workflow else None,
                "active_role": workflow.active_role if workflow else None,
            },
            "pattern_signals": {
                "dominant_affinity": pattern.dominant_affinity if pattern else None,
                "trusted_pattern_count": pattern.trusted_pattern_count if pattern else 0,
                "contested_pattern_count": pattern.contested_pattern_count if pattern else 0,
                "trusted_patterns": pattern.trusted_patterns[:4] if pattern else [],
            },
            "maintenance": {
                "promoted_insight_count": maintenance.promoted_insight_count if maintenance else 0,
                "forgetting_backlog_count": maintenance.forgetting_backlog_count if maintenance else 0,
                "suppressed_count": maintenance.suppressed_count if maintenance else 0,
                "evicted_count": maintenance.evicted_count if maintenance else 0,
                "auto_learning_status": maintenance.auto_learning_status if maintenance else "manual_only",
                "last_learning_source": maintenance.last_learning_source if maintenance else None,
                "passive_observation_status": maintenance.passive_observation_status if maintenance else "none",
                "observed_changed_file_count": maintenance.observed_changed_file_count if maintenance else 0,
                "recommended_action": maintenance.recommended_action if maintenance else None,
            },
            "instrumentation": {
                "status": instrumentation_grade,
                "explanation": instrumentation_explanation,
                "task_family": instrumentation.task_family if instrumentation else None,
                "family_scope": instrumentation.family_scope if instrumentation else None,
                "family_hit": instrumentation.family_hit if instrumentation else False,
                "family_reason": instrumentation.family_reason if instrumentation else None,
                "pattern_reuse": {
                    "hit_count": instrumentation.selected_pattern_hit_count if instrumentation else 0,
                    "miss_count": instrumentation.selected_pattern_miss_count if instrumentation else 0,
                },
                "artifact_routing": {
                    "known_count": instrumentation.routed_artifact_known_count if instrumentation else 0,
                    "same_family_count": instrumentation.routed_artifact_same_family_count if instrumentation else 0,
                    "other_family_count": instrumentation.routed_artifact_other_family_count if instrumentation else 0,
                    "unknown_count": instrumentation.routed_artifact_unknown_count if instrumentation else 0,
                    "hit_rate": instrumentation.routed_artifact_hit_rate if instrumentation else 0.0,
                    "same_family_task_ids": instrumentation.routed_same_family_task_ids[:6] if instrumentation else [],
                    "other_family_task_ids": instrumentation.routed_other_family_task_ids[:6] if instrumentation else [],
                },
            },
            "continuity": continuity,
            "context_layers": {layer: values[:4] for layer, values in context.items() if values},
            "controller": _controller_view_from_session(session),
        }

    def serialized_session(self, session: SessionState) -> dict[str, Any]:
        return json.loads(session.to_json())

    def evaluate_session_model(self, session: SessionState) -> dict[str, Any]:
        canonical_surface = self.canonical_surface(session)
        canonical_views = self.canonical_views(session)
        continuity = session.continuity_snapshot or {}
        context = session.context_layers_snapshot or {}
        shared_memory = session.shared_memory or []
        legacy_prior_lines = _count_legacy_prior_lines(shared_memory)
        checks = {
            "execution_packet_present": bool(session.execution_packet and session.execution_packet_summary),
            "planner_surface_present": bool(session.planner_packet and session.strategy_summary),
            "provenance_surface_present": bool(
                session.pattern_signal_summary
                and session.workflow_signal_summary
                and session.routing_signal_summary
                and session.maintenance_summary
            ),
            "context_layers_present": bool(context and any(context.values())),
            "continuity_snapshot_present": bool(continuity),
            "continuity_has_prior_memory": bool(
                continuity.get("prior_artifact_refs")
                or continuity.get("prior_collaboration_patterns")
                or continuity.get("prior_strategy_working_sets")
            ),
            "shared_memory_is_thin": legacy_prior_lines == 0,
            "canonical_views_present": bool(canonical_views),
        }
        passed = sum(1 for value in checks.values() if value)
        total = len(checks)
        score = round((passed / total) * 100, 1) if total else 0.0
        blockers: list[str] = []
        if legacy_prior_lines:
            blockers.append(f"shared_memory still carries {legacy_prior_lines} legacy prior lines")
        if not checks["continuity_has_prior_memory"]:
            blockers.append("continuity_snapshot does not yet expose reusable prior continuity")
        if not checks["context_layers_present"]:
            blockers.append("context_layers_snapshot is missing or empty")
        if not checks["planner_surface_present"]:
            blockers.append("planner/strategy summaries are missing")
        if session.delegation_packets and not (session.routing_signal_summary and session.routing_signal_summary.routed_role_count):
            blockers.append("routing summary did not route any role packets")
        status = "ready"
        if score < 100:
            status = "in_progress"
        if score < 62.5:
            status = "needs_attention"
        return {
            "status": status,
            "score": score,
            "passed_checks": passed,
            "total_checks": total,
            "checks": checks,
            "legacy_prior_line_count": legacy_prior_lines,
            "blockers": blockers,
            "task_state": canonical_views.get("task_state", {}),
            "strategy": canonical_views.get("strategy", {}),
            "workflow": canonical_views.get("workflow", {}),
            "routing": canonical_views.get("routing", {}),
            "instrumentation": canonical_views.get("instrumentation", {}),
            "instrumentation_status": canonical_views.get("instrumentation", {}).get("status"),
            "continuity": canonical_views.get("continuity", {}),
            "canonical_surface_keys": sorted(key for key, value in canonical_surface.items() if value),
        }

    def inspect_session(self, *, task_id: str) -> dict[str, Any]:
        session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._repo_root
        path = self._save_session(session)
        doc_learning = build_doc_learning_record(session)
        canonical_views = self.canonical_views(session)
        controller_action_bar = controller_action_bar_payload(canonical_views.get("controller"), task_id=task_id)
        return {
            "session_path": str(path),
            "session": json.loads(session.to_json()),
            "canonical_surface": self.canonical_surface(session),
            "canonical_views": canonical_views,
            "controller_action_bar": controller_action_bar,
            "evaluation": self.evaluate_session_model(session),
            "doc_learning": doc_learning,
        }

    def evaluate_session(self, *, task_id: str) -> dict[str, Any]:
        session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._repo_root
        path = self._save_session(session)
        canonical_views = self.canonical_views(session)
        return {
            "session_path": str(path),
            "evaluation": self.evaluate_session_model(session),
            "canonical_views": canonical_views,
            "controller_action_bar": controller_action_bar_payload(canonical_views.get("controller"), task_id=task_id),
        }

    def shell_status(self, *, task_id: str | None = None) -> dict[str, Any]:
        session: SessionState | None
        if task_id:
            session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        else:
            recent = load_recent_sessions(self._repo_root, project_scope=self._project_scope, exclude_task_id=None, limit=1)
            session = recent[0] if recent else None
        canonical_views: dict[str, Any] = {}
        resolved_task_id = task_id
        if session is not None:
            session.repo_root = self._repo_root
            self._save_session(session)
            canonical_views = self.canonical_views(session)
            resolved_task_id = session.task_id
        else:
            canonical_views = self._bootstrap_canonical_views(self._bootstrap_snapshot())
        dashboard_payload = self._dashboard(limit=24, family_limit=8)
        background_payload = self._background_status()
        host_payload = self._host_contract()
        status_input = build_statusline_input(
            project_identity=self._project_identity,
            project_scope=self._project_scope,
            task_id=resolved_task_id,
            canonical_views=canonical_views,
            dashboard_payload=dashboard_payload,
            background_payload=background_payload,
            host_payload=host_payload,
        )
        controller = canonical_views.get("controller", {})
        return {
            "task_id": resolved_task_id,
            "status_line": status_input.to_dict(),
            "text": render_statusline(status_input),
            "controller": controller,
            "controller_action_bar": controller_action_bar_payload(controller, task_id=resolved_task_id),
            "dashboard_summary": dashboard_payload.get("dashboard_summary", {}),
            "background": background_payload,
            "host_contract": host_payload.get("contract"),
        }
