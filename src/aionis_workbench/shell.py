from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .controller_shell import (
    format_controller_action_bar,
    format_controller_action_bar_payload,
    primary_action_from_action_bar,
    primary_controller_action,
)
from .shell_dispatch import dispatch_shell_input


def _json_default(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        return data
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _payload_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)


def _payload_task_id(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    task_id = payload.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        return task_id.strip()
    evaluation = payload.get("evaluation")
    if isinstance(evaluation, dict):
        task_id = evaluation.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()
    anchor = payload.get("anchor")
    if isinstance(anchor, dict):
        task_id = anchor.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()
    canonical_views = payload.get("canonical_views")
    if isinstance(canonical_views, dict):
        task_state = canonical_views.get("task_state")
        if isinstance(task_state, dict):
            task_id = task_state.get("task_id")
            if isinstance(task_id, str) and task_id.strip():
                return task_id.strip()
    return None


def _format_prior_stats(prior: dict[str, Any]) -> str:
    confidence = float(prior.get("confidence") or 0.0)
    sample_count = int(prior.get("sample_count") or prior.get("session_count") or 0)
    recent_success_count = int(prior.get("recent_success_count") or 0)
    manual_ingest_count = int(prior.get("manual_ingest_count") or 0)
    workflow_closure_count = int(prior.get("workflow_closure_count") or 0)
    validate_count = int(prior.get("validate_count") or 0)
    passive_observation_count = int(prior.get("passive_observation_count") or 0)
    summary = (
        f"confidence={confidence:.2f} samples={sample_count} recent_success={recent_success_count} "
    )
    if manual_ingest_count or workflow_closure_count or validate_count or passive_observation_count:
        summary += (
            f"manual={manual_ingest_count} workflow={workflow_closure_count} "
            f"validate={validate_count} passive={passive_observation_count}"
        )
    return summary.rstrip()


def _format_prior_seed(prior: dict[str, Any]) -> str:
    seed_ready = bool(prior.get("seed_ready"))
    seed_gate = str(prior.get("seed_gate") or ("ready" if seed_ready else "unknown"))
    seed_reason = str(prior.get("seed_reason") or "").strip() or "no seed explanation"
    return f"{'ready' if seed_ready else 'blocked'} gate={seed_gate} reason={seed_reason}"


def _format_dream_reason(prior: dict[str, Any]) -> str:
    reason = str(
        prior.get("dream_promotion_reason")
        or prior.get("dream_verification_summary")
        or prior.get("verification_summary")
        or ""
    ).strip()
    return reason


def _format_reviewer_prior_summary(prior: dict[str, Any]) -> str | None:
    if not isinstance(prior, dict):
        return None
    standard = str(prior.get("dominant_standard") or "").strip()
    if not standard:
        return None
    outputs = [
        item.strip() for item in (prior.get("dominant_required_outputs") or []) if isinstance(item, str) and item.strip()
    ]
    checks = [
        item.strip() for item in (prior.get("dominant_acceptance_checks") or []) if isinstance(item, str) and item.strip()
    ]
    source = str(prior.get("dominant_pack_source") or "").strip() or "unknown"
    sample_count = int(prior.get("sample_count") or 0)
    seed = "ready" if prior.get("seed_ready") else "blocked"
    return (
        f"reviewer_prior={standard} source={source} "
        f"outputs={'|'.join(outputs) or 'none'} "
        f"checks={', '.join(checks) or 'none'} "
        f"samples={sample_count} seed={seed}"
    )


def _format_reviewer_prior_usage(prior: dict[str, Any]) -> str | None:
    if not isinstance(prior, dict):
        return None
    if not str(prior.get("dominant_standard") or "").strip():
        return None
    selected_tool = str(prior.get("dominant_selected_tool") or "").strip() or "none"
    anchor = str(prior.get("dominant_resume_anchor") or "").strip() or "none"
    ready_required_count = int(prior.get("ready_required_count") or 0)
    rollback_required_count = int(prior.get("rollback_required_count") or 0)
    return (
        f"reviewer_usage=ready_required:{ready_required_count} "
        f"rollback_required:{rollback_required_count} "
        f"anchor={anchor} tool={selected_tool}"
    )


def _format_reviewer_summary(reviewer: dict[str, Any]) -> str | None:
    standard = str(reviewer.get("standard") or "").strip()
    required_outputs = [
        item.strip() for item in (reviewer.get("required_outputs") or []) if isinstance(item, str) and item.strip()
    ]
    acceptance_checks = [
        item.strip() for item in (reviewer.get("acceptance_checks") or []) if isinstance(item, str) and item.strip()
    ]
    anchor = str(reviewer.get("resume_anchor") or "").strip()
    ready_required = reviewer.get("ready_required") is True
    rollback_required = reviewer.get("rollback_required") is True
    if not (standard or required_outputs or acceptance_checks or anchor or ready_required or rollback_required):
        return None
    outputs = "|".join(
        required_outputs
    ) or "none"
    acceptance = ", ".join(acceptance_checks) or "none"
    rollback = "yes" if rollback_required else "no"
    ready = "yes" if ready_required else "no"
    anchor = anchor or "none"
    return (
        f"reviewer={(standard or 'none')} outputs={outputs} "
        f"acceptance={acceptance} rollback={rollback} ready={ready} anchor={anchor}"
    )


def _format_controller_summary(controller: dict[str, Any] | None) -> str | None:
    if not isinstance(controller, dict) or not controller:
        return None
    status = str(controller.get("status") or "").strip() or "unknown"
    allowed = ", ".join(
        str(item).strip()
        for item in (controller.get("allowed_actions") or [])[:4]
        if isinstance(item, str) and item.strip()
    ) or "none"
    blocked = ", ".join(
        str(item).strip()
        for item in (controller.get("blocked_actions") or [])[:3]
        if isinstance(item, str) and item.strip()
    ) or "none"
    transition = str(controller.get("last_transition_kind") or "").strip() or "none"
    return f"controller={status} allowed={allowed} blocked={blocked} transition={transition}"


def _payload_controller(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    controller = payload.get("controller")
    if isinstance(controller, dict):
        return controller
    canonical_views = payload.get("canonical_views")
    if not isinstance(canonical_views, dict):
        return None
    controller = canonical_views.get("controller")
    return controller if isinstance(controller, dict) else None


def _payload_controller_action_bar(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    action_bar = payload.get("controller_action_bar")
    return action_bar if isinstance(action_bar, dict) else None


def _format_review_pack_summary(review_packs: dict[str, Any]) -> str | None:
    if not isinstance(review_packs, dict):
        return None
    parts: list[str] = []
    for label in ("continuity", "evolution"):
        pack = review_packs.get(label)
        if not isinstance(pack, dict):
            continue
        standard = str(pack.get("standard") or "").strip()
        next_action = str(pack.get("next_action") or "").strip()
        selected_tool = str(pack.get("selected_tool") or "").strip()
        if not any([standard, next_action, selected_tool]):
            continue
        segment = f"{label}:{standard or 'none'}"
        if selected_tool:
            segment += f"/{selected_tool}"
        if next_action:
            segment += f" next={next_action}"
        parts.append(segment)
    if not parts:
        return None
    return "review_packs=" + " | ".join(parts)


def _format_reviewer_gate_summary(reviewer_gate: dict[str, Any] | None) -> str | None:
    if not isinstance(reviewer_gate, dict):
        return None
    standard = str(reviewer_gate.get("standard") or "").strip()
    acceptance_checks = [
        item.strip() for item in (reviewer_gate.get("acceptance_checks") or []) if isinstance(item, str) and item.strip()
    ]
    resume_anchor = str(reviewer_gate.get("resume_anchor") or "").strip()
    ready_required = reviewer_gate.get("ready_required") is True
    gated_validation = reviewer_gate.get("gated_validation") is True
    if not any([standard, acceptance_checks, resume_anchor, ready_required, gated_validation]):
        return None
    checks = ", ".join(acceptance_checks) or "none"
    return (
        f"reviewer_gate={(standard or 'none')} checks={checks} "
        f"ready={'yes' if ready_required else 'no'} "
        f"gated={'yes' if gated_validation else 'no'} "
        f"anchor={(resume_anchor or 'none')}"
    )


def _format_host_summary(contract: dict[str, Any] | None) -> str:
    contract = contract or {}
    product_shell = contract.get("product_shell") or {}
    learning_engine = contract.get("learning_engine") or {}
    execution_host = contract.get("execution_host") or {}
    return (
        f"shell={product_shell.get('name', 'unknown')} "
        f"learning={learning_engine.get('name', 'unknown')} "
        f"execution={execution_host.get('name', 'unknown')}"
    )


def _format_host_health_hint(contract: dict[str, Any] | None) -> str | None:
    contract = contract or {}
    execution_host = contract.get("execution_host") or {}
    runtime_host = contract.get("runtime_host") or {}
    raw_execution_health = execution_host.get("health_status")
    raw_runtime_health = runtime_host.get("health_status")
    execution_health = str(raw_execution_health or "unknown")
    runtime_health = str(raw_runtime_health or "unknown")
    has_explicit_health = raw_execution_health is not None or raw_runtime_health is not None
    if not has_explicit_health:
        return None
    if execution_health in {"available", "unknown"} and runtime_health in {"available", "unknown"}:
        return None
    execution_mode = str(execution_host.get("mode") or "unknown")
    execution_reason = str(execution_host.get("health_reason") or "none")
    runtime_reason = str(runtime_host.get("health_reason") or "none")
    return (
        f"host_mode={execution_mode} "
        f"execution={execution_health}({execution_reason}) "
        f"runtime={runtime_health}({runtime_reason})"
    )


def _host_execution_mode(contract: dict[str, Any] | None) -> str:
    contract = contract or {}
    execution_host = contract.get("execution_host") or {}
    return str(execution_host.get("mode") or "live_enabled")


def _format_recovery_note(payload: dict[str, Any]) -> str | None:
    summary = str(payload.get("recovery_summary") or "").strip()
    if summary:
        return summary
    normalized = str(payload.get("recovery_class") or "").strip()
    if normalized == "ready":
        return "live preflight is green"
    if normalized == "missing_credentials":
        return "model credentials are missing; runtime may already be reachable"
    if normalized == "missing_runtime":
        return "runtime is missing or unreachable; credentials may already be configured"
    if normalized == "missing_credentials_and_runtime":
        return "both model credentials and runtime availability must be restored"
    if normalized == "runtime_degraded":
        return "runtime is configured but unhealthy; inspect the health endpoint before retrying"
    if normalized == "degraded":
        return "host state is degraded; follow the first recommendation before retrying"
    return None


def _summary_line(payload: dict[str, Any], field: str, *, fallback: str) -> str:
    value = str(payload.get(field) or "").strip()
    return value or fallback


def _inspect_only_surface_hint() -> str:
    return "inspect-only path remains usable via shell -> /work, /review, /validate, or /ingest"


def _split_recommendations(recommendations: list[Any] | None) -> tuple[str, str]:
    inspect_only = ""
    repair = ""
    for item in recommendations or []:
        text = str(item or "").strip()
        if not text:
            continue
        if "inspect-only" in text and not inspect_only:
            inspect_only = text
            continue
        if not repair:
            repair = text
    return inspect_only, repair


def _startup_mode_hint(workbench) -> str | None:
    doctor = getattr(workbench, "doctor", None)
    if not callable(doctor):
        return None
    try:
        payload = doctor()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    mode = str(payload.get("mode") or "").strip()
    if not mode:
        return None
    live_ready_summary = str(payload.get("live_ready_summary") or "").strip()
    capability_summary = str(payload.get("capability_summary") or "").strip()
    recovery_summary = str(payload.get("recovery_summary") or "").strip()
    capability_state = str(payload.get("capability_state") or "").strip()
    checklist = payload.get("setup_checklist") or []
    recommendations = payload.get("recommendations") or []
    next_step = ""
    for item in checklist:
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue
        command_hint = str(item.get("command_hint") or "").strip()
        next_hint = str(item.get("next_step") or "").strip()
        next_step = command_hint or next_hint
        if next_step:
            break
    if recommendations and isinstance(recommendations, list):
        next_step = next_step or str(recommendations[0] or "").strip()
    parts = [f"mode: {live_ready_summary or mode}"]
    if capability_state:
        parts.append(f"state: {capability_state}")
    if capability_summary:
        parts.append(f"capabilities: {capability_summary}")
    if recovery_summary and not bool(payload.get("live_ready")):
        parts.append(f"recovery: {recovery_summary}")
    if next_step:
        parts.append(f"next: {next_step}")
    return " | ".join(parts)


def _render_result_payload(payload: dict[str, Any]) -> list[str]:
    if payload.get("shell_view") == "ship":
        task_id = str(payload.get("task_id") or _payload_task_id(payload) or "unknown")
        ship_mode = str(payload.get("ship_mode") or "unknown")
        delegated_shell_view = str(payload.get("delegated_shell_view") or "unknown")
        route_summary = str(payload.get("route_summary") or "task_intake->context_scan->route")
        route_reason = str(payload.get("route_reason") or "none")
        context_summary = str(payload.get("context_summary") or "none")
        if ship_mode == "app_delivery":
            status = str(payload.get("status") or "unknown")
            phase = str(payload.get("phase") or "unknown")
            active_sprint_id = str(payload.get("active_sprint_id") or "none")
            entrypoint = str(payload.get("entrypoint") or "none")
            preview_command = str(payload.get("preview_command") or "none")
            validation_summary = str(payload.get("validation_summary") or "none")
            failure_reason = str(payload.get("failure_reason") or payload.get("error") or "").strip()
            failure_class = str(payload.get("failure_class") or "").strip()
            live_provider_id = str(payload.get("live_provider_id") or "unknown")
            live_model = str(payload.get("live_model") or "unknown")
            lines = [
                f"ship: {task_id} mode={ship_mode} delegate={delegated_shell_view} status={status} phase={phase} sprint={active_sprint_id}",
                f"  route={route_summary} reason={route_reason} context={context_summary}",
                f"  entrypoint={entrypoint} preview={preview_command} validation={validation_summary} provider={live_provider_id}/{live_model}",
            ]
            if failure_reason:
                detail = f"  failure={failure_reason}"
                if failure_class:
                    detail += f" failure_class={failure_class}"
                lines.append(detail)
            lines.append(_payload_json(payload))
            return lines
        canonical_views = payload.get("canonical_views") or {}
        task_state = canonical_views.get("task_state") or {}
        planner = canonical_views.get("planner") or {}
        instrumentation = canonical_views.get("instrumentation") or {}
        controller = canonical_views.get("controller") or {}
        validation_status = task_state.get("validation_ok")
        validation_label = "unknown"
        if validation_status is True:
            validation_label = "ok"
        elif validation_status is False:
            validation_label = "failed"
        live_provider_id = str(payload.get("live_provider_id") or "unknown")
        live_model = str(payload.get("live_model") or "unknown")
        lines = [
            f"ship: {task_id} mode={ship_mode} delegate={delegated_shell_view} runner={payload.get('runner', 'unknown')}",
            (
                f"  route={route_summary} reason={route_reason} context={context_summary} "
                f"status={task_state.get('status', 'unknown')} validation={validation_label} provider={live_provider_id}/{live_model}"
            ),
            (
                f"  next={planner.get('next_action', 'unknown')} "
                f"instrumentation={instrumentation.get('status', 'unknown')} "
                f"session={payload.get('session_path', 'n/a')}"
            ),
        ]
        controller_line = _format_controller_summary(controller)
        if controller_line:
            lines.append(f"  {controller_line}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "app_ship":
        task_id = str(payload.get("task_id") or _payload_task_id(payload) or "unknown")
        route_summary = str(payload.get("route_summary") or "task_intake->context_scan->plan->sprint->generate->export")
        active_sprint_id = str(payload.get("active_sprint_id") or "none")
        status = str(payload.get("status") or "unknown")
        phase = str(payload.get("phase") or "unknown")
        entrypoint = str(payload.get("entrypoint") or "none")
        validation_summary = str(payload.get("validation_summary") or "none")
        failure_reason = str(payload.get("failure_reason") or payload.get("error") or "").strip()
        failure_class = str(payload.get("failure_class") or "").strip()
        context_summary = str(payload.get("context_summary") or "none")
        preview_command = str(payload.get("preview_command") or "none")
        live_provider_id = str(payload.get("live_provider_id") or "unknown")
        live_model = str(payload.get("live_model") or "unknown")
        lines = [
            f"app_ship: {task_id} status={status} phase={phase} sprint={active_sprint_id}",
            f"  route={route_summary} context={context_summary} entrypoint={entrypoint} preview={preview_command} provider={live_provider_id}/{live_model}",
        ]
        detail_parts = [f"validation={validation_summary}"]
        if failure_reason:
            detail_parts.append(f"failure={failure_reason}")
        if failure_class:
            detail_parts.append(f"failure_class={failure_class}")
        lines.append("  " + " ".join(detail_parts))
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "app_export":
        task_id = str(payload.get("task_id") or _payload_task_id(payload) or "unknown")
        export_root = str(payload.get("export_root") or "none")
        entrypoint = str(payload.get("entrypoint") or "none")
        preview_command = str(payload.get("preview_command") or "none")
        validation_summary = str(payload.get("validation_summary") or "none")
        changed_files = payload.get("changed_files") or []
        changed_files = changed_files if isinstance(changed_files, list) else []
        changed_preview = ",".join(str(item).strip() for item in changed_files[:4] if str(item).strip()) or "none"
        lines = [
            f"app_export: {task_id} export_root={export_root}",
            f"  entrypoint={entrypoint} preview={preview_command} changed={changed_preview} validation={validation_summary}",
        ]
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") in {"app_show", "app_plan", "app_sprint", "app_negotiate", "app_generate", "app_qa", "app_retry", "app_advance", "app_replan", "app_escalate"}:
        harness = (payload.get("canonical_views") or {}).get("app_harness") or {}
        harness = harness if isinstance(harness, dict) else {}
        product = harness.get("product_spec") or {}
        product = product if isinstance(product, dict) else {}
        sprint = harness.get("active_sprint_contract") or {}
        sprint = sprint if isinstance(sprint, dict) else {}
        evaluation = harness.get("latest_sprint_evaluation") or {}
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        task_id = str(payload.get("task_id") or _payload_task_id(payload) or "unknown")
        title = str(product.get("title") or "untitled")
        sprint_id = str(sprint.get("sprint_id") or "none")
        status = str(evaluation.get("status") or "unknown")
        loop_status = str(harness.get("loop_status") or "unknown")
        app_type = str(product.get("app_type") or "unknown")
        planner_mode = str(harness.get("planner_mode") or payload.get("planner_mode") or "deterministic")
        feature_count = int(product.get("feature_count") or 0)
        feature_groups = product.get("feature_groups") or []
        feature_groups = feature_groups if isinstance(feature_groups, list) else []
        evaluator_count = int(harness.get("evaluator_criteria_count") or 0)
        approved = bool(sprint.get("approved"))
        proposed_by = str(sprint.get("proposed_by") or "unknown")
        planned_sprints = harness.get("planned_sprint_contracts") or []
        planned_sprints = planned_sprints if isinstance(planned_sprints, list) else []
        rationale = harness.get("planning_rationale") or []
        rationale = rationale if isinstance(rationale, list) else []
        negotiation_notes = harness.get("sprint_negotiation_notes") or []
        negotiation_notes = negotiation_notes if isinstance(negotiation_notes, list) else []
        negotiation_round = harness.get("latest_negotiation_round") or {}
        negotiation_round = negotiation_round if isinstance(negotiation_round, dict) else {}
        recommended_action = str(negotiation_round.get("recommended_action") or "none")
        negotiation_planner_mode = str(negotiation_round.get("planner_mode") or "").strip()
        objections = negotiation_round.get("objections") or []
        objections = objections if isinstance(objections, list) else []
        objection_preview = "|".join(
            str(item).strip() for item in objections[:2] if isinstance(item, str) and str(item).strip()
        ) or "none"
        next_sprint_ids = [
            str(item.get("sprint_id") or "").strip()
            for item in planned_sprints
            if isinstance(item, dict) and str(item.get("sprint_id") or "").strip()
        ]
        summary = str(evaluation.get("summary") or "no evaluator summary")
        evaluator_mode = str(evaluation.get("evaluator_mode") or "unknown")
        failing_criteria = evaluation.get("failing_criteria") or []
        failing_criteria = failing_criteria if isinstance(failing_criteria, list) else []
        failing_preview = ",".join(
            str(item).strip() for item in failing_criteria if isinstance(item, str) and str(item).strip()
        ) or "none"
        latest_revision = harness.get("latest_revision") or {}
        latest_revision = latest_revision if isinstance(latest_revision, dict) else {}
        revision_id = str(latest_revision.get("revision_id") or "none")
        latest_execution_attempt = harness.get("latest_execution_attempt") or {}
        latest_execution_attempt = latest_execution_attempt if isinstance(latest_execution_attempt, dict) else {}
        execution_attempt_id = str(latest_execution_attempt.get("attempt_id") or "none")
        execution_target_kind = str(latest_execution_attempt.get("execution_target_kind") or "none")
        execution_mode = str(latest_execution_attempt.get("execution_mode") or "none")
        artifact_kind = str(latest_execution_attempt.get("artifact_kind") or "none")
        artifact_path = str(latest_execution_attempt.get("artifact_path") or "none")
        trace_path = str(latest_execution_attempt.get("trace_path") or "").strip()
        failure_reason = str(latest_execution_attempt.get("failure_reason") or "").strip()
        failure_class = str(latest_execution_attempt.get("failure_class") or "").strip()
        validation_summary = str(latest_execution_attempt.get("validation_summary") or "").strip()
        execution_history_count = int(harness.get("execution_history_count") or 0)
        current_sprint_execution_count = int(harness.get("current_sprint_execution_count") or 0)
        policy_stage = str(harness.get("policy_stage") or "base")
        replan_depth = int(harness.get("replan_depth") or 0)
        replan_root_sprint_id = str(harness.get("replan_root_sprint_id") or "none")
        retry_count = int(harness.get("retry_count") or 0)
        retry_budget = int(harness.get("retry_budget") or 0)
        last_execution_gate_transition = str(harness.get("last_execution_gate_transition") or "none")
        last_policy_action = str(harness.get("last_policy_action") or "none")
        execution_outcome_ready = bool(harness.get("execution_outcome_ready"))
        execution_gate = str(
            harness.get("execution_gate")
            or ("no_execution" if execution_attempt_id == "none" else "unsettled")
        )
        retry_available = bool(harness.get("retry_available"))
        retry_remaining = int(harness.get("retry_remaining") or 0)
        next_sprint_ready = bool(harness.get("next_sprint_ready"))
        next_sprint_candidate_id = str(harness.get("next_sprint_candidate_id") or "none")
        recommended_next_action = str(harness.get("recommended_next_action") or "none")
        negotiation_label = (
            f"{recommended_action}@{negotiation_planner_mode}"
            if negotiation_planner_mode
            else recommended_action
        )
        shell_view = str(payload.get("shell_view") or "app_show")
        lines = [
            f"{shell_view}: {task_id} title={title} sprint={sprint_id} status={status} loop={loop_status}",
            f"  planner={planner_mode} type={app_type} features={feature_count} groups={','.join(feature_groups) or 'none'} criteria={evaluator_count} proposed_by={proposed_by} approved={str(approved).lower()} next={','.join(next_sprint_ids) or 'none'} evaluator={evaluator_mode} failing={failing_preview} negotiation={negotiation_label} objections={objection_preview} revision={revision_id} execution={execution_attempt_id}@{execution_mode}/{execution_target_kind} artifact={artifact_kind}@{artifact_path} execution_count={execution_history_count} current_execution_count={current_sprint_execution_count} stage={policy_stage} replan={replan_depth}@{replan_root_sprint_id} exec_ready={str(execution_outcome_ready).lower()} exec_gate={execution_gate} gate_flow={last_execution_gate_transition}@{last_policy_action} retry={retry_count}/{retry_budget} retry_available={str(retry_available).lower()} retry_remaining={retry_remaining} next_ready={str(next_sprint_ready).lower()} next_candidate={next_sprint_candidate_id} action={recommended_next_action} rationale={len(rationale)} negotiation_notes={len(negotiation_notes)} summary={summary}",
        ]
        if failure_reason or validation_summary:
            detail_parts = []
            if failure_reason:
                detail_parts.append(f"failure={failure_reason}")
            if failure_class:
                detail_parts.append(f"failure_class={failure_class}")
            if validation_summary:
                detail_parts.append(f"validation={validation_summary}")
            if trace_path:
                detail_parts.append(f"trace={trace_path}")
            lines.append("  " + " ".join(detail_parts))
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "doc_show":
        learning = payload.get("doc_learning") or {}
        learning = learning if isinstance(learning, dict) else {}
        task_id = str(payload.get("task_id") or _payload_task_id(payload) or "unknown")
        latest_action = str(learning.get("latest_action") or "unknown")
        latest_status = str(learning.get("latest_status") or "unknown")
        source_doc_id = str(learning.get("source_doc_id") or "unknown")
        handoff_anchor = str(learning.get("handoff_anchor") or "none")
        selected_tool = str(learning.get("selected_tool") or "none")
        event_source = str(learning.get("event_source") or "none")
        recorded_at = str(learning.get("recorded_at") or "none")
        history = learning.get("history") or []
        history = history if isinstance(history, list) else []
        history_preview = " -> ".join(
            str(item.get("action") or "").strip()
            for item in history[:4]
            if isinstance(item, dict) and str(item.get("action") or "").strip()
        ) or "none"
        lines = [
            f"doc_show: {task_id} action={latest_action} status={latest_status} doc={source_doc_id}",
            f"  anchor={handoff_anchor} tool={selected_tool} sync={event_source} at={recorded_at} history={history_preview}",
        ]
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "doc_list":
        docs = payload.get("docs") or []
        docs = docs if isinstance(docs, list) else []
        preview = ", ".join(
            (
                f"{item.get('path')}"
                + (f":{item.get('latest_action')}" if item.get("latest_action") else "")
            )
            for item in docs[:3]
            if isinstance(item, dict)
        ) or "none"
        return [
            f"doc_list: count={payload.get('doc_count', len(docs))} top={preview}",
            _payload_json(payload),
        ]
    if payload.get("shell_view") == "doc_inspect":
        inspect_kind = str(payload.get("inspect_kind") or "unknown")
        target = str(payload.get("resolved_target") or payload.get("target") or "unknown")
        if inspect_kind == "artifact":
            summary = payload.get("artifact_summary") or {}
            summary = summary if isinstance(summary, dict) else {}
            lines = [
                f"doc_inspect: artifact target={target} kind={summary.get('kind') or 'unknown'} status={summary.get('status') or 'unknown'}",
                f"  action={summary.get('doc_action') or 'unknown'} doc={summary.get('source_doc_id') or 'unknown'} anchor={summary.get('handoff_anchor') or 'none'}",
            ]
            controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
            if controller_action_bar:
                lines.append(f"  {controller_action_bar}")
            lines.append(_payload_json(payload))
            return lines
        latest = payload.get("latest_record") or {}
        latest = latest if isinstance(latest, dict) else {}
        lines = [
            f"doc_inspect: workflow target={target} evidence={payload.get('evidence_count', 0)} exists={'yes' if payload.get('exists') else 'no'}",
            f"  latest={latest.get('latest_action') or 'unknown'}/{latest.get('latest_status') or 'unknown'} doc={latest.get('source_doc_id') or 'unknown'} anchor={latest.get('handoff_anchor') or 'none'} tool={latest.get('selected_tool') or 'none'}",
        ]
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if str(payload.get("shell_view") or "").startswith("doc_"):
        action = str(payload.get("doc_action") or payload.get("shell_view") or "doc").replace("doc_", "")
        input_path = str(payload.get("doc_input") or "unknown")
        status = str(payload.get("status") or "unknown")
        registry_path = str(payload.get("doc_registry") or "").strip()
        result_key = {
            "compile": "compile_result",
            "run": "run_result",
            "execute": "execute_result",
            "runtime_handoff": "runtime_handoff",
            "handoff_store": "handoff_store_request",
            "publish": "publish_result",
            "recover": "recover_result",
            "resume": "resume_result",
        }.get(action, "")
        result_payload = payload.get(result_key) if result_key else {}
        result_payload = result_payload if isinstance(result_payload, dict) else {}
        lines = [
            f"doc: {action} status={status}",
            f"  input={input_path}",
        ]
        if registry_path:
            lines.append(f"  registry={registry_path}")
        if action == "compile":
            summary = result_payload.get("summary") or {}
            summary = summary if isinstance(summary, dict) else {}
            diagnostics = result_payload.get("diagnostics") or []
            diagnostics = diagnostics if isinstance(diagnostics, list) else []
            lines.append(
                "  "
                f"diagnostics={len(diagnostics)} "
                f"errors={summary.get('error_count', 0)} "
                f"warnings={summary.get('warning_count', 0)} "
                f"artifact={result_payload.get('selected_artifact', 'all')}"
            )
        elif action in {"run", "execute"}:
            outputs = result_payload.get("outputs") or {}
            outputs = outputs if isinstance(outputs, dict) else {}
            lines.append(f"  outputs={len(outputs)}")
        elif action in {"publish", "recover", "resume"}:
            handoff_id = (
                result_payload.get("handoff_id")
                or result_payload.get("id")
                or ((result_payload.get("handoff") or {}) if isinstance(result_payload.get("handoff"), dict) else {}).get("id")
                or "none"
            )
            lines.append(f"  handoff={handoff_id}")
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "ready":
        host_contract = payload.get("host_contract") or {}
        pending_items = payload.get("pending_items") or []
        checks = payload.get("checks") or []
        pending_preview = ", ".join(
            str(item.get("name") or "unknown")
            for item in pending_items[:4]
            if isinstance(item, dict)
        ) or "none"
        check_preview = ", ".join(
            f"{item.get('name', 'unknown')}:{item.get('status', 'unknown')}"
            for item in checks[:4]
            if isinstance(item, dict)
        ) or "none"
        next_steps = payload.get("next_steps") or []
        lines = [
            f"ready: {payload.get('live_ready_summary') or payload.get('mode', 'inspect-only')} live_ready={payload.get('live_ready', False)}",
            f"  repo={payload.get('repo_root', 'unknown')}",
            f"  state={payload.get('capability_state', 'unknown')}",
            f"  capabilities={payload.get('capability_summary', 'unknown')}",
            f"  pending={payload.get('pending_count', 0)} items={pending_preview}",
            f"  checks={check_preview}",
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if not bool(payload.get("live_ready")):
            lines.append(f"  now={_inspect_only_surface_hint()}")
        recovery_summary = str(payload.get("recovery_summary") or "").strip()
        if recovery_summary:
            lines.append(f"  recovery={recovery_summary}")
        if next_steps:
            lines.append(f"  first={next_steps[0]}")
            if len(next_steps) > 1:
                lines.append(f"  then={next_steps[1]}")
            if len(next_steps) > 2:
                lines.append(f"  then_after={next_steps[2]}")
        lines.append(f"  launch={payload.get('launch_command', 'aionis --repo-root /absolute/path/to/repo')}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "live_profile":
        provider_id = str(payload.get("provider_id") or "unknown")
        live_mode = str(payload.get("live_mode") or "unknown")
        model = str(payload.get("model") or "unknown")
        timeout_seconds = int(payload.get("timeout_seconds") or 0)
        max_completion_tokens = int(payload.get("max_completion_tokens") or 0)
        latest_scenario = str(payload.get("latest_scenario_id") or "none")
        latest_at = str(payload.get("latest_recorded_at") or "none")
        ready_seconds = float(payload.get("latest_ready_duration_seconds") or 0.0)
        run_seconds = float(payload.get("latest_run_duration_seconds") or 0.0)
        resume_seconds = float(payload.get("latest_resume_duration_seconds") or 0.0)
        total_seconds = float(payload.get("latest_total_duration_seconds") or 0.0)
        timing_summary = str(payload.get("latest_timing_summary") or "").strip() or "none"
        execution_focus = str(payload.get("latest_execution_focus") or "").strip() or "none"
        execution_gate = str(payload.get("latest_execution_gate") or "").strip() or "unknown"
        execution_gate_transition = str(payload.get("latest_execution_gate_transition") or "").strip() or "none"
        execution_outcome_ready = bool(payload.get("latest_execution_outcome_ready"))
        last_policy_action = str(payload.get("latest_last_policy_action") or "").strip() or "none"
        convergence_signal = str(payload.get("latest_convergence_signal") or "").strip() or "none"
        recent_convergence_signals = payload.get("recent_convergence_signals") or []
        recent_convergence_signals = [
            str(item).strip() for item in recent_convergence_signals if str(item).strip()
        ]
        recent_preview = ", ".join(recent_convergence_signals[:4]) or "none"
        return [
            f"live-profile: provider={provider_id} mode={live_mode} model={model}",
            f"  budget=timeout:{timeout_seconds}s max_tokens:{max_completion_tokens} live={payload.get('supports_live', False)} tier={payload.get('release_tier', 'unknown')}",
            f"  latest={latest_scenario} ready={ready_seconds:.3f}s run={run_seconds:.3f}s resume={resume_seconds:.3f}s total={total_seconds:.3f}s at={latest_at}",
            f"  policy=gate:{execution_gate} flow={execution_gate_transition}@{last_policy_action} outcome_ready:{str(execution_outcome_ready).lower()} focus={execution_focus}",
            f"  signal={convergence_signal}",
            f"  recent_signals={recent_preview}",
            f"  timing={timing_summary}",
            _payload_json(payload),
        ]
    if payload.get("shell_view") == "ab_test_compare":
        baseline = payload.get("baseline") or {}
        aionis = payload.get("aionis") or {}
        comparison = payload.get("comparison") or {}
        return [
            f"ab-test: {payload.get('scenario_id', 'unknown')} task={payload.get('task_id', 'unknown')} winner={comparison.get('winner', 'unknown')}",
            f"  baseline=end:{baseline.get('ended_in', 'stalled')} duration:{float(baseline.get('total_duration_seconds') or 0.0):.3f}s retry:{int(baseline.get('retry_count') or 0)} replan:{int(baseline.get('replan_depth') or 0)} gate:{baseline.get('final_execution_gate', 'none') or 'none'} signal={baseline.get('latest_convergence_signal', 'none') or 'none'}",
            f"  aionis=end:{aionis.get('ended_in', 'stalled')} duration:{float(aionis.get('total_duration_seconds') or 0.0):.3f}s retry:{int(aionis.get('retry_count') or 0)} replan:{int(aionis.get('replan_depth') or 0)} gate:{aionis.get('final_execution_gate', 'none') or 'none'} signal={aionis.get('latest_convergence_signal', 'none') or 'none'}",
            f"  delta=duration:{float(comparison.get('duration_delta_seconds') or 0.0):.3f}s retry:{int(comparison.get('retry_delta') or 0)} replan:{int(comparison.get('replan_delta') or 0)}",
            f"  summary={payload.get('benchmark_summary', comparison.get('summary', 'none'))}",
            _payload_json(payload),
        ]
    if payload.get("shell_view") in {"doctor_one_line", "setup_one_line", "live_preflight_one_line"}:
        summary_line = str(payload.get("summary_line") or "").strip() or payload.get("shell_view", "summary")
        return [summary_line, _payload_json(payload)]
    if payload.get("shell_view") == "doctor_summary":
        host_contract = payload.get("host_contract") or {}
        lines = [
            f"doctor-summary: {payload.get('live_ready_summary') or payload.get('mode', 'unknown')} live_ready={payload.get('live_ready', False)}",
            f"  state={payload.get('capability_state', 'unknown')}",
            f"  capabilities={payload.get('capability_summary', 'unknown')}",
            f"  pending={payload.get('pending_checklist_count', 0)}",
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if not bool(payload.get("live_ready")):
            lines.append(f"  now={_inspect_only_surface_hint()}")
        recovery_summary = str(payload.get("recovery_summary") or "").strip()
        if recovery_summary:
            lines.append(f"  recovery={recovery_summary}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.append(f"  {host_hint}")
        recommendation = str(payload.get("recommendation") or "").strip()
        if recommendation:
            lines.append(f"  next={recommendation}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "doctor_check":
        host_contract = payload.get("host_contract") or {}
        item = payload.get("item") or {}
        lines = [
            f"doctor-check: {payload.get('check_name', 'unknown')} found={payload.get('found', False)}",
            f"  state={payload.get('capability_state', 'unknown')}",
            f"  source={payload.get('source', 'unknown')}",
        ]
        if item:
            lines.append(
                f"  status={item.get('status', 'unknown')} reason={item.get('reason', 'unknown')}"
            )
            next_step = str(item.get("command_hint") or item.get("next_step") or "").strip()
            if next_step:
                lines.append(f"  next={next_step}")
        else:
            available = ", ".join(payload.get("available_checks") or []) or "none"
            lines.append(f"  available={available}")
        lines.append(f"  hosts={_format_host_summary(host_contract)}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "setup_summary":
        host_contract = payload.get("host_contract") or {}
        lines = [
            f"setup-summary: {payload.get('live_ready_summary') or payload.get('mode', 'unknown')} live_ready={payload.get('live_ready', False)}",
            f"  state={payload.get('capability_state', 'unknown')}",
            f"  capabilities={payload.get('capability_summary', 'unknown')}",
            (
                f"  counts=pending:{payload.get('pending_count', 0)} "
                f"completed:{payload.get('completed_count', 0)}"
            ),
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if not bool(payload.get("live_ready")):
            lines.append(f"  now={_inspect_only_surface_hint()}")
        recovery_summary = str(payload.get("recovery_summary") or "").strip()
        if recovery_summary:
            lines.append(f"  recovery={recovery_summary}")
        next_step = str(payload.get("next_step") or "").strip()
        if next_step:
            lines.append(f"  next={next_step}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "setup_check":
        host_contract = payload.get("host_contract") or {}
        item = payload.get("item") or {}
        lines = [
            f"setup-check: {payload.get('check_name', 'unknown')} found={payload.get('found', False)}",
            f"  state={payload.get('capability_state', 'unknown')}",
        ]
        if item:
            lines.append(
                f"  status={item.get('status', 'unknown')} reason={item.get('reason', 'unknown')}"
            )
            next_step = str(item.get("command_hint") or item.get("next_step") or "").strip()
            if next_step:
                lines.append(f"  next={next_step}")
        else:
            available = ", ".join(payload.get("available_checks") or []) or "none"
            lines.append(f"  available={available}")
        lines.append(f"  hosts={_format_host_summary(host_contract)}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "setup":
        checklist = payload.get("pending_items") or []
        host_contract = payload.get("host_contract") or {}
        pending_preview = "; ".join(
            f"{item.get('name')}->{str(item.get('command_hint') or item.get('next_step') or '').strip()}"
            for item in checklist[:3]
            if isinstance(item, dict)
        ) or "none"
        lines = [
            (
                f"setup: {payload.get('live_ready_summary') or payload.get('mode', 'inspect-only')} "
                f"live_ready={payload.get('live_ready', False)} "
                f"pending={payload.get('pending_count', 0)}"
            ),
            f"  repo={payload.get('repo_root', 'unknown')}",
            f"  state={payload.get('capability_state', 'unknown')}",
            f"  capabilities={payload.get('capability_summary', 'unknown')}",
            f"  view={'pending_only' if payload.get('pending_only') else 'full'}",
            f"  pending={pending_preview}",
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if not bool(payload.get("live_ready")):
            lines.append(f"  now={_inspect_only_surface_hint()}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.append(f"  {host_hint}")
        next_steps = payload.get("next_steps") or []
        if next_steps:
            lines.append(f"  next={next_steps[0]}")
        if len(next_steps) > 1:
            lines.append(f"  then={next_steps[1]}")
        lines.append("  suggested=run /doctor after completing the pending setup steps")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "doctor":
        host_contract = payload.get("host_contract") or {}
        checks = payload.get("checks") or []
        checklist = payload.get("setup_checklist") or []
        check_preview = ", ".join(
            f"{item.get('name')}:{item.get('status')}"
            for item in checks[:5]
            if isinstance(item, dict)
        ) or "none"
        checklist_preview = ", ".join(
            f"{item.get('name')}:{item.get('status')}"
            for item in checklist[:4]
            if isinstance(item, dict)
        ) or "none"
        checklist_fix = "; ".join(
            f"{item.get('name')}->{str(item.get('command_hint') or item.get('next_step') or '').strip()}"
            for item in checklist[:3]
            if isinstance(item, dict) and item.get("status") == "pending" and str(item.get("command_hint") or item.get("next_step") or "").strip()
        ) or "none"
        recommendations = payload.get("recommendations") or []
        lines = [
            f"doctor: {payload.get('live_ready_summary') or payload.get('mode', 'unknown')} live_ready={payload.get('live_ready', False)}",
            f"  repo={payload.get('repo_root', 'unknown')}",
            f"  state={payload.get('capability_state', 'unknown')}",
            f"  capabilities={payload.get('capability_summary', 'unknown')}",
            f"  checks={check_preview}",
            f"  checklist={checklist_preview}",
            f"  fixes={checklist_fix}",
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if not bool(payload.get("live_ready")):
            lines.append(f"  now={_inspect_only_surface_hint()}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.append(f"  {host_hint}")
        if recommendations:
            lines.append(f"  recommendation={recommendations[0]}")
            if len(recommendations) > 1:
                lines.append(f"  next={recommendations[1]}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "host_error":
        host_contract = payload.get("host_contract") or {}
        recommendations = payload.get("recommendations") or []
        recovery_note = _format_recovery_note(payload)
        inspect_only, repair = _split_recommendations(recommendations)
        lines = [
            (
                f"{payload.get('operation', 'task')} failed: "
                f"{payload.get('task_id') or 'unknown'} mode={payload.get('execution_mode', 'unknown')}"
            ),
            f"  error={payload.get('error', 'unknown error')}",
            f"  recovery={payload.get('recovery_class', 'unknown')} hint={payload.get('recovery_command_hint', 'none')}",
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if recovery_note:
            lines.append(f"  recovery_note={recovery_note}")
        if inspect_only or str(payload.get("execution_mode") or "") == "inspect_only":
            lines.append(f"  now={inspect_only or _inspect_only_surface_hint()}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.append(f"  {host_hint}")
        if repair:
            lines.append(f"  repair={repair}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "live_preflight":
        host_contract = payload.get("host_contract") or {}
        recommendations = payload.get("recommendations") or []
        recovery_note = _format_recovery_note(payload)
        inspect_only, repair = _split_recommendations(recommendations)
        lines = [
            (
                f"{payload.get('operation', 'task')} preflight: "
                f"{payload.get('task_id') or 'unknown'} ready={payload.get('ready', False)} "
                f"mode={payload.get('execution_mode', 'unknown')}"
            ),
            (
                f"  status={payload.get('status', 'unknown')} "
                f"execution={payload.get('execution_health', 'unknown')} "
                f"runtime={payload.get('runtime_health', 'unknown')}"
            ),
            f"  recovery={payload.get('recovery_class', 'unknown')} hint={payload.get('recovery_command_hint', 'none')}",
            f"  hosts={_format_host_summary(host_contract)}",
        ]
        if recovery_note:
            lines.append(f"  recovery_note={recovery_note}")
        if not bool(payload.get("ready")) and (inspect_only or str(payload.get("execution_mode") or "") == "inspect_only"):
            lines.append(f"  now={inspect_only or _inspect_only_surface_hint()}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.append(f"  {host_hint}")
        if recommendations and bool(payload.get("ready")):
            lines.append(f"  next={recommendations[0]}")
        elif repair:
            lines.append(f"  repair={repair}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "controller_preflight":
        controller = (payload.get("canonical_views") or {}).get("controller") or {}
        controller_line = _format_controller_summary(controller)
        lines = [
            (
                f"{payload.get('command', 'task')} controller preflight: "
                f"{payload.get('task_id', 'unknown')} status={payload.get('controller_status', 'unknown')} "
                f"required={payload.get('required_action', 'unknown')}"
            ),
            f"  reason={payload.get('reason', 'controller action is blocked')}",
            f"  recommended={payload.get('recommended_command', '/show')}",
        ]
        if controller_line:
            lines.append(f"  {controller_line}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "hosts":
        contract = payload.get("contract") or {}
        product_shell = contract.get("product_shell") or {}
        learning_engine = contract.get("learning_engine") or {}
        execution_host = contract.get("execution_host") or {}
        runtime_host = contract.get("runtime_host") or {}
        workflow = ", ".join(product_shell.get("default_workflow") or []) or "none"
        inspection = ", ".join(product_shell.get("inspection_commands") or []) or "none"
        surfaces = ", ".join((learning_engine.get("canonical_surfaces") or [])[:4]) or "none"
        return [
            (
                f"hosts: shell={product_shell.get('name', 'unknown')} "
                f"learning={learning_engine.get('name', 'unknown')} "
                f"execution={execution_host.get('name', 'unknown')} "
                f"runtime={runtime_host.get('name', 'unknown')}"
            ),
            (
                f"  entrypoint={payload.get('recommended_entrypoint', 'aionis --repo-root <repo>')} "
                f"mode={product_shell.get('mode', 'unknown')} "
                f"execution_mode={execution_host.get('mode', 'unknown')} "
                f"runtime_mode={runtime_host.get('replay_mode', 'unknown')}"
            ),
            f"  workflow={workflow}",
            f"  inspection={inspection}",
            (
                f"  health=shell:{product_shell.get('health_status', 'unknown')} "
                f"learning:{learning_engine.get('health_status', 'unknown')} "
                f"execution:{execution_host.get('health_status', 'unknown')} "
                f"runtime:{runtime_host.get('health_status', 'unknown')}"
            ),
            (
                f"  execution_runtime={execution_host.get('execution_runtime', 'unknown')} "
                f"backend={execution_host.get('backend', 'unknown')} "
                f"provider={execution_host.get('model_provider', 'unknown')} "
                f"live_tasks={execution_host.get('supports_live_tasks', False)} "
                f"reason={execution_host.get('health_reason', 'none') or 'none'}"
            ),
            (
                f"  learning=bootstrap:{learning_engine.get('cold_start_bootstrap', False)} "
                f"auto:{learning_engine.get('auto_learning', False)} "
                f"passive:{learning_engine.get('passive_observation', False)} "
                f"consolidation:{learning_engine.get('consolidation', False)}"
            ),
            (
                f"  runtime_base_url={runtime_host.get('base_url', 'unknown')} "
                f"bridge_configured={runtime_host.get('bridge_configured', False)} "
                f"reason={runtime_host.get('health_reason', 'none') or 'none'}"
            ),
            f"  canonical_surfaces={surfaces}",
            _payload_json(payload),
        ]
    if payload.get("shell_view") == "background":
        summary = payload.get("summary") or {}
        lines = [
            f"background: status={payload.get('status', 'unknown')} enabled={payload.get('enabled', False)} lock={payload.get('lock_active', False)}",
            (
                f"  trigger={payload.get('last_trigger') or 'none'} "
                f"reason={payload.get('last_reason') or 'none'} "
                f"new_sessions={payload.get('last_new_session_count', 0)}"
            ),
            (
                f"  sessions={summary.get('sessions_reviewed', 0)} "
                f"families={summary.get('families_reviewed', 0)} "
                f"merged={summary.get('patterns_merged', 0)} "
                f"suppressed={summary.get('patterns_suppressed', 0)} "
                f"continuity_cleaned={summary.get('continuity_cleaned', 0)}"
            ),
            _payload_json(payload),
        ]
        return lines
    if payload.get("shell_view") == "consolidate":
        family_rows = payload.get("family_rows") or []
        top_families = ", ".join(
            f"{item.get('task_family', 'task:unknown')}:{item.get('status', 'unknown')}"
            for item in family_rows[:3]
            if isinstance(item, dict)
        ) or "none"
        dream_summary = payload.get("dream_summary") or {}
        dream_suffix = ""
        if dream_summary:
            dream_suffix = (
                " "
                f"dream=seed_ready:{dream_summary.get('seed_ready_count', 0)} "
                f"trial:{dream_summary.get('trial_count', 0)} "
                f"candidate:{dream_summary.get('candidate_count', 0)} "
                f"deprecated:{dream_summary.get('deprecated_count', 0)}"
            )
        lines = [
            (
                f"dream: sessions={payload.get('sessions_reviewed', 0)} "
                f"families={payload.get('families_reviewed', 0)} "
                f"merged={payload.get('patterns_merged', 0)} "
                f"suppressed={payload.get('patterns_suppressed', 0)} "
                f"continuity_cleaned={payload.get('continuity_cleaned', 0)}"
            ),
            (
                f"  artifacts={payload.get('artifacts_reviewed', 0)} "
                f"recovery_samples={payload.get('recovery_samples_reviewed', 0)} "
                f"top={top_families}{dream_suffix}"
            ),
            f"  path={payload.get('consolidation_path', 'n/a')}",
            _payload_json(payload),
        ]
        return lines
    if payload.get("shell_view") == "dream":
        dream_summary = payload.get("dream_summary") or {}
        promotions = payload.get("dream_promotions") or []
        candidates = payload.get("dream_candidates") or []
        status_filter = str(payload.get("dream_status_filter") or "all")
        top_promotions = ", ".join(
            (
                f"{item.get('task_family', 'task:unknown')}:{item.get('promotion_status', 'unknown')}:"
                f"{float(item.get('confidence') or 0.0):.2f}"
            )
            for item in promotions[:3]
            if isinstance(item, dict)
        ) or "none"
        top_candidates = ", ".join(
            (
                f"{item.get('task_family', 'task:unknown')}:{item.get('strategy_profile', 'unknown')}:"
                f"{int(item.get('sample_count') or 0)}"
            )
            for item in candidates[:3]
            if isinstance(item, dict)
        ) or "none"
        top_docs = ", ".join(
            (
                f"{item.get('task_family', 'task:unknown')}:"
                f"{item.get('dominant_source_doc_id') or item.get('dominant_doc_input') or 'unknown'}:"
                f"{item.get('dominant_doc_action') or 'unknown'}:"
                f"{item.get('dominant_selected_tool') or 'none'}"
            )
            for item in promotions[:3]
            if isinstance(item, dict)
            and (
                str(item.get("dominant_source_doc_id") or "").strip()
                or str(item.get("dominant_doc_input") or "").strip()
            )
        ) or "none"
        top_reasons = " | ".join(
            (
                f"{item.get('task_family', 'task:unknown')}:{item.get('promotion_status', 'unknown')}:"
                f"{str(item.get('promotion_reason') or item.get('verification_summary') or 'no reason').strip()}"
            )
            for item in promotions[:2]
            if isinstance(item, dict)
        ) or "none"
        top_doc_syncs = ", ".join(
            (
                f"{item.get('task_family', 'task:unknown')}:"
                f"{item.get('dominant_event_source') or 'unknown'}:"
                f"{int(item.get('editor_sync_count') or 0)}:"
                f"{item.get('latest_recorded_at') or 'unknown'}"
            )
            for item in promotions[:3]
            if isinstance(item, dict)
            and (
                str(item.get("dominant_event_source") or "").strip()
                or int(item.get("editor_sync_count") or 0) > 0
            )
        ) or "none"
        top_reviewers = ", ".join(
            (
                f"{item.get('task_family', 'task:unknown')}:"
                f"{item.get('dominant_reviewer_standard') or 'unknown'}:"
                f"{item.get('dominant_reviewer_pack_source') or 'unknown'}:"
                f"{int(item.get('reviewer_sample_count') or 0)}"
            )
            for item in promotions[:3]
            if isinstance(item, dict) and str(item.get("dominant_reviewer_standard") or "").strip()
        ) or "none"
        lines = [
            (
                f"dream-detail: seed_ready={dream_summary.get('seed_ready_count', 0)} "
                f"trial={dream_summary.get('trial_count', 0)} "
                f"candidate={dream_summary.get('candidate_count', 0)} "
                f"deprecated={dream_summary.get('deprecated_count', 0)}"
            ),
            (
                f"  filter={status_filter} "
                f"promotions={payload.get('dream_promotion_count', len(promotions))} "
                f"candidates={payload.get('dream_candidate_count', len(candidates))} "
                f"top_promotions={top_promotions}"
            ),
            f"  top_candidates={top_candidates}",
            f"  top_docs={top_docs}",
            f"  top_doc_syncs={top_doc_syncs}",
            f"  top_reviewers={top_reviewers}",
            f"  reasons={top_reasons}",
            _payload_json(payload),
        ]
        return lines
    if payload.get("bootstrap_snapshot"):
        canonical_views = payload.get("canonical_views") or {}
        task_state = canonical_views.get("task_state") or {}
        strategy = canonical_views.get("strategy") or {}
        planner = canonical_views.get("planner") or {}
        instrumentation = canonical_views.get("instrumentation") or {}
        evaluation = payload.get("evaluation") or {}
        host_contract = payload.get("host_contract") or {}
        bootstrap = payload.get("bootstrap_snapshot") or {}
        focus = ", ".join((bootstrap.get("bootstrap_focus") or [])[:3]) or "none"
        working_set = ", ".join((bootstrap.get("bootstrap_working_set") or [])[:4]) or "none"
        validation = ", ".join((bootstrap.get("bootstrap_validation_commands") or [])[:2]) or "none"
        first_step = str(bootstrap.get("bootstrap_first_step") or planner.get("next_action") or "Create the first narrow task.")
        validation_step = str(bootstrap.get("bootstrap_validation_step") or "Define one runnable validation command before expanding the working set.")
        reuse = str(bootstrap.get("bootstrap_reuse_summary") or "no reusable prior yet; the first validated success will seed future family reuse")
        notes = "; ".join((bootstrap.get("notes") or [])[:2]) or "No source/test roots were detected yet."
        history = ", ".join((bootstrap.get("recent_commit_subjects") or [])[:2]) or "none"
        family_priors = ", ".join(
            f"{item.get('task_family', 'task:unknown')}:{item.get('dominant_strategy_profile', 'unknown')}"
            for item in (bootstrap.get("recent_family_priors") or [])[:3]
            if isinstance(item, dict)
        ) or "none"
        setup = payload.get("setup") or {}
        view_name = payload.get("shell_view") or "bootstrap"
        lines = [
            f"{view_name}: bootstrap",
            (
                f"  status={task_state.get('status', 'bootstrap_ready')} "
                f"family={strategy.get('task_family', 'task:cold-start')} "
                f"strategy={strategy.get('strategy_profile', 'bootstrap_first_loop')} "
                f"evaluation={evaluation.get('status', 'bootstrap_ready')}"
            ),
            f"  focus={focus}",
            f"  first_step={first_step}",
            f"  validate_first={validation_step}",
            f"  reuse={reuse}",
            f"  next_action={planner.get('next_action', 'Create the first narrow task.')}",
            f"  working_set={working_set}",
            f"  validate={validation}",
            f"  instrumentation={instrumentation.get('status', 'cold_start')} notes={notes}",
            f"  history={history}",
            f"  priors={family_priors}",
            f"  hosts={_format_host_summary(host_contract)}",
            "  workflow=/init -> /doctor -> /run -> /work -> /next -> /fix -> /validate",
            "  suggested=/run TASK_ID \"task\" [--target-file PATH] [--validation-command CMD] or /ingest TASK_ID \"task\" \"summary\" ...",
        ]
        if setup:
            lines.insert(
                -1,
                f"  setup_mode={setup.get('live_ready_summary') or setup.get('mode', 'inspect-only')} live_ready={setup.get('live_ready', False)}",
            )
            next_steps = setup.get("next_steps") or []
            if next_steps:
                lines.insert(-1, f"  next={next_steps[0]}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.insert(-1, f"  {host_hint}")
        if payload.get("bootstrap_path"):
            lines.append(f"  bootstrap_path={payload.get('bootstrap_path')}")
        lines.append(_payload_json(payload))
        return lines
    if payload.get("shell_view") == "plan":
        canonical_views = payload.get("canonical_views") or {}
        task_state = canonical_views.get("task_state") or {}
        strategy = canonical_views.get("strategy") or {}
        planner = canonical_views.get("planner") or {}
        reviewer = (payload.get("reviewer") or canonical_views.get("reviewer") or {})
        review_packs = (payload.get("review_packs") or canonical_views.get("review_packs") or {})
        evaluation = payload.get("evaluation") or {}
        peer_summary = payload.get("peer_summary") or {}
        family_row = payload.get("family_row") or {}
        family_prior = payload.get("family_prior") or {}
        workflow_next = payload.get("workflow_next") or {}
        host_contract = payload.get("host_contract") or {}
        next_action = workflow_next.get("action", "show")
        next_reason = workflow_next.get("reason") or planner.get("next_action") or "Inspect the task."
        recommendation = (
            str(workflow_next.get("recommendation") or family_prior.get("seed_recommendation") or "").strip()
            if not family_prior.get("seed_ready")
            else ""
        )
        next_validation = payload.get("next_validation") or "none"
        workflow_path = str(payload.get("workflow_path") or "/plan -> /review -> /fix -> /validate")
        recommended_command = str(payload.get("recommended_command") or f"/review {task_state.get('task_id', payload.get('task_id', 'unknown'))}").strip()
        reviewer_line = _format_reviewer_summary(reviewer)
        review_pack_line = _format_review_pack_summary(review_packs)
        lines = [
            f"plan: {task_state.get('task_id', payload.get('task_id', 'unknown'))}",
            (
                f"  status={task_state.get('status', 'unknown')} "
                f"family={payload.get('task_family', strategy.get('task_family', 'unknown'))} "
                f"strategy={strategy.get('strategy_profile', 'unknown')} "
                f"evaluation={evaluation.get('status', 'unknown')}"
            ),
            (
                f"  next_action={next_action} "
                f"reason={next_reason}"
            ),
            (
                f"  validate={next_validation}"
            ),
            f"  value={_summary_line(payload, 'value_summary', fallback='no explicit value summary')}",
            f"  reuse={_summary_line(payload, 'reuse_summary', fallback='no explicit reuse summary')}",
            (
                f"  family_status={family_row.get('status', 'unknown')} "
                f"trend={family_row.get('trend_status', 'unknown')} "
                f"strong={peer_summary.get('strong_match_count', 0)} "
                f"usable={peer_summary.get('usable_match_count', 0)} "
                f"weak={peer_summary.get('weak_match_count', 0)}"
            ),
            (
                f"  prior_strategy={family_prior.get('dominant_strategy_profile', 'unknown')} "
                f"prior_validation={family_prior.get('dominant_validation_style', 'unknown')}"
            ),
            f"  prior_stats={_format_prior_stats(family_prior)}",
            f"  prior_seed={_format_prior_seed(family_prior)}",
            f"  hosts={_format_host_summary(host_contract)}",
            f"  workflow={workflow_path}",
        ]
        if reviewer_line:
            lines.insert(-1, f"  {reviewer_line}")
        if review_pack_line:
            lines.insert(-1, f"  {review_pack_line}")
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.insert(-1, f"  {controller_action_bar}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.append(f"  {host_hint}")
        if recommendation:
            lines.append(f"  recommendation={recommendation}")
        lines.extend(
            [
                f"  recommended={recommended_command}",
                "  suggested=/review -> /fix",
                _payload_json(payload),
            ]
        )
        return lines
    if payload.get("shell_view") == "fix":
        workflow_next = payload.get("workflow_next") or {}
        reviewer_gate_line = _format_reviewer_gate_summary(payload.get("reviewer_gate"))
        host_contract = payload.get("host_contract") or {}
        action = workflow_next.get("action", "show")
        reason = workflow_next.get("reason", "No next action was recorded.")
        recommendation = str(workflow_next.get("recommendation") or "").strip()
        execution_mode = _host_execution_mode(host_contract)
        host_hint = _format_host_health_hint(host_contract)
        task_id = (
            payload.get("task_id")
            or ((payload.get("canonical_views") or {}).get("task_state") or {}).get("task_id")
            or "unknown"
        )
        if "validation" in payload:
            validation = payload.get("validation") or {}
            state = "ok" if validation.get("ok") else "failed"
            command = validation.get("command") or "n/a"
            exit_code = validation.get("exit_code")
            action_label = (
                f"validated via {execution_mode} workflow"
                if execution_mode != "live_enabled"
                else f"executed {action}"
            )
            lines = [
                f"fix: {task_id} {action_label}",
                f"  reason={reason}",
            ]
            if host_hint:
                lines.append(f"  {host_hint}")
            if recommendation:
                lines.append(f"  recommendation={recommendation}")
            if reviewer_gate_line:
                lines.append(f"  {reviewer_gate_line}")
            lines.extend(
                [
                    f"  validation={state} exit={exit_code if exit_code is not None else 'n/a'} command={command}",
                    _payload_json(payload),
                ]
            )
            return lines
        canonical_views = payload.get("canonical_views") or {}
        planner = canonical_views.get("planner") or {}
        action_label = (
            f"recommended {action} in {execution_mode} mode"
            if execution_mode != "live_enabled"
            else f"recommended {action}"
        )
        lines = [
            f"fix: {task_id} {action_label}",
            f"  reason={reason}",
        ]
        if host_hint:
            lines.append(f"  {host_hint}")
        if recommendation:
            lines.append(f"  recommendation={recommendation}")
        if reviewer_gate_line:
            lines.append(f"  {reviewer_gate_line}")
        lines.extend(
            [
                f"  next_action={planner.get('next_action', 'unknown')}",
                _payload_json(payload),
            ]
        )
        return lines
    if payload.get("shell_view") == "review":
        canonical_views = payload.get("canonical_views") or {}
        task_state = canonical_views.get("task_state") or {}
        strategy = canonical_views.get("strategy") or {}
        planner = canonical_views.get("planner") or {}
        reviewer = (payload.get("reviewer") or canonical_views.get("reviewer") or {})
        review_packs = (payload.get("review_packs") or canonical_views.get("review_packs") or {})
        maintenance = canonical_views.get("maintenance") or {}
        routing = ((canonical_views.get("routing") or {}).get("summary") or {})
        instrumentation = canonical_views.get("instrumentation") or {}
        controller = canonical_views.get("controller") or {}
        evaluation = payload.get("evaluation") or {}
        peer_summary = payload.get("peer_summary") or {}
        family_row = payload.get("family_row") or {}
        family_prior = payload.get("family_prior") or {}
        host_contract = payload.get("host_contract") or {}
        validation_paths = strategy.get("validation_paths") or planner.get("pending_validations") or []
        primary_validation = validation_paths[0] if validation_paths else (
            family_prior.get("dominant_validation_command") or "none"
        )
        workflow_path = str(payload.get("workflow_path") or "/review -> /fix -> /validate")
        recommended_command = str(payload.get("recommended_command") or f"/fix {task_state.get('task_id', payload.get('task_id', 'unknown'))}").strip()
        reviewer_line = _format_reviewer_summary(reviewer)
        review_pack_line = _format_review_pack_summary(review_packs)
        top_peers = ", ".join(
            item.get("task_id", "?")
            for item in (payload.get("peers") or [])[:3]
            if isinstance(item, dict)
        )
        lines = [
            f"review: {task_state.get('task_id', payload.get('task_id', 'unknown'))}",
            (
                f"  status={task_state.get('status', 'unknown')} "
                f"family={payload.get('task_family', strategy.get('task_family', 'unknown'))} "
                f"strategy={strategy.get('strategy_profile', 'unknown')} "
                f"trust={strategy.get('trust_signal', 'unknown')}"
            ),
            (
                f"  evaluation={evaluation.get('status', 'unknown')} "
                f"score={evaluation.get('score', 'n/a')} "
                f"next={planner.get('next_action', 'unknown')}"
            ),
            f"  value={_summary_line(payload, 'value_summary', fallback='no explicit value summary')}",
            f"  reuse={_summary_line(payload, 'reuse_summary', fallback='no explicit reuse summary')}",
            (
                f"  family_status={family_row.get('status', 'unknown')} "
                f"trend={family_row.get('trend_status', 'unknown')} "
                f"strong={peer_summary.get('strong_match_count', 0)} "
                f"usable={peer_summary.get('usable_match_count', 0)} "
                f"weak={peer_summary.get('weak_match_count', 0)}"
            ),
            (
                f"  prior_strategy={family_prior.get('dominant_strategy_profile', 'unknown')} "
                f"prior_validation={family_prior.get('dominant_validation_style', 'unknown')}"
            ),
            f"  prior_stats={_format_prior_stats(family_prior)}",
            f"  prior_seed={_format_prior_seed(family_prior)}",
            f"  hosts={_format_host_summary(host_contract)}",
            (
                f"  validation={primary_validation} "
                f"instrumentation={instrumentation.get('status', 'unknown')} "
                f"routed_roles={routing.get('routed_role_count', 0)} "
                f"artifacts={routing.get('routed_artifact_ref_count', 0)}"
            ),
            (
                f"  learning={maintenance.get('auto_learning_status', 'manual_only')} "
                f"source={maintenance.get('last_learning_source', 'none') or 'none'} "
                f"observed={maintenance.get('observed_changed_file_count', 0)}"
            ),
            f"  top_peers={top_peers or 'none'}",
            f"  workflow={workflow_path}",
            f"  recommended={recommended_command}",
            _payload_json(payload),
        ]
        if reviewer_line:
            lines.insert(10, f"  {reviewer_line}")
        if review_pack_line:
            lines.insert(11, f"  {review_pack_line}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.insert(8, f"  {host_hint}")
        controller_line = _format_controller_summary(controller)
        if controller_line:
            lines.insert(-1, f"  {controller_line}")
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.insert(-1, f"  {controller_action_bar}")
        return lines
    if payload.get("shell_view") == "next":
        workflow_next = payload.get("workflow_next") or {}
        reviewer_gate_line = _format_reviewer_gate_summary(payload.get("reviewer_gate"))
        host_contract = payload.get("host_contract") or {}
        action = workflow_next.get("action", "show")
        reason = workflow_next.get("reason", "No next action was recorded.")
        recommendation = str(workflow_next.get("recommendation") or "").strip()
        execution_mode = _host_execution_mode(host_contract)
        host_hint = _format_host_health_hint(host_contract)
        task_id = (
            payload.get("task_id")
            or ((payload.get("canonical_views") or {}).get("task_state") or {}).get("task_id")
            or "unknown"
        )
        if "validation" in payload:
            validation = payload.get("validation") or {}
            state = "ok" if validation.get("ok") else "failed"
            command = validation.get("command") or "n/a"
            exit_code = validation.get("exit_code")
            action_label = (
                f"validated via {execution_mode} workflow"
                if execution_mode != "live_enabled"
                else f"executed {action}"
            )
            lines = [
                f"next: {task_id} {action_label}",
                f"  reason={reason}",
            ]
            if host_hint:
                lines.append(f"  {host_hint}")
            if recommendation:
                lines.append(f"  recommendation={recommendation}")
            if reviewer_gate_line:
                lines.append(f"  {reviewer_gate_line}")
            lines.extend(
                [
                    f"  validation={state} exit={exit_code if exit_code is not None else 'n/a'} command={command}",
                    _payload_json(payload),
                ]
            )
            return lines
        canonical_views = payload.get("canonical_views") or {}
        planner = canonical_views.get("planner") or {}
        action_label = (
            f"recommended {action} in {execution_mode} mode"
            if execution_mode != "live_enabled"
            else f"recommended {action}"
        )
        lines = [
            f"next: {task_id} {action_label}",
            f"  reason={reason}",
        ]
        if host_hint:
            lines.append(f"  {host_hint}")
        if recommendation:
            lines.append(f"  recommendation={recommendation}")
        if reviewer_gate_line:
            lines.append(f"  {reviewer_gate_line}")
        lines.extend(
            [
                f"  next_action={planner.get('next_action', 'unknown')}",
                _payload_json(payload),
            ]
        )
        return lines
    if payload.get("shell_view") == "work":
        canonical_views = payload.get("canonical_views") or {}
        task_state = canonical_views.get("task_state") or {}
        strategy = canonical_views.get("strategy") or {}
        planner = canonical_views.get("planner") or {}
        reviewer = (payload.get("reviewer") or canonical_views.get("reviewer") or {})
        review_packs = (payload.get("review_packs") or canonical_views.get("review_packs") or {})
        maintenance = canonical_views.get("maintenance") or {}
        routing = ((canonical_views.get("routing") or {}).get("summary") or {})
        instrumentation = canonical_views.get("instrumentation") or {}
        evaluation = payload.get("evaluation") or {}
        peer_summary = payload.get("peer_summary") or {}
        family_row = payload.get("family_row") or {}
        family_prior = payload.get("family_prior") or {}
        host_contract = payload.get("host_contract") or {}
        validation_paths = strategy.get("validation_paths") or planner.get("pending_validations") or []
        primary_validation = validation_paths[0] if validation_paths else (
            family_prior.get("dominant_validation_command") or "none"
        )
        workflow_path = str(payload.get("workflow_path") or "/work -> /next -> /fix -> /validate")
        recommended_command = str(payload.get("recommended_command") or f"/next {task_state.get('task_id', payload.get('task_id', 'unknown'))}").strip()
        reviewer_line = _format_reviewer_summary(reviewer)
        review_pack_line = _format_review_pack_summary(review_packs)
        top_peers = ", ".join(
            item.get("task_id", "?")
            for item in (payload.get("peers") or [])[:3]
            if isinstance(item, dict)
        )
        lines = [
            f"work: {task_state.get('task_id', payload.get('task_id', 'unknown'))}",
            (
                f"  status={task_state.get('status', 'unknown')} "
                f"family={payload.get('task_family', strategy.get('task_family', 'unknown'))} "
                f"strategy={strategy.get('strategy_profile', 'unknown')} "
                f"score={evaluation.get('score', 'n/a')}"
            ),
            (
                f"  next={planner.get('next_action', 'unknown')} "
                f"validation={primary_validation}"
            ),
            f"  value={_summary_line(payload, 'value_summary', fallback='no explicit value summary')}",
            f"  reuse={_summary_line(payload, 'reuse_summary', fallback='no explicit reuse summary')}",
            (
                f"  family_status={family_row.get('status', 'unknown')} "
                f"trend={family_row.get('trend_status', 'unknown')} "
                f"strong={peer_summary.get('strong_match_count', 0)} "
                f"usable={peer_summary.get('usable_match_count', 0)} "
                f"weak={peer_summary.get('weak_match_count', 0)}"
            ),
            (
                f"  prior_strategy={family_prior.get('dominant_strategy_profile', 'unknown')} "
                f"prior_validation={family_prior.get('dominant_validation_style', 'unknown')}"
            ),
            f"  prior_stats={_format_prior_stats(family_prior)}",
            f"  prior_seed={_format_prior_seed(family_prior)}",
            f"  hosts={_format_host_summary(host_contract)}",
            (
                f"  instrumentation={instrumentation.get('status', 'unknown')} "
                f"routed_roles={routing.get('routed_role_count', 0)} "
                f"artifacts={routing.get('routed_artifact_ref_count', 0)}"
            ),
            (
                f"  learning={maintenance.get('auto_learning_status', 'manual_only')} "
                f"source={maintenance.get('last_learning_source', 'none') or 'none'} "
                f"observed={maintenance.get('observed_changed_file_count', 0)}"
            ),
            f"  top_peers={top_peers or 'none'}",
            f"  workflow={workflow_path}",
            f"  recommended={recommended_command}",
            _payload_json(payload),
        ]
        if reviewer_line:
            lines.insert(10, f"  {reviewer_line}")
        if review_pack_line:
            lines.insert(11, f"  {review_pack_line}")
        host_hint = _format_host_health_hint(host_contract)
        if host_hint:
            lines.insert(8, f"  {host_hint}")
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.insert(-1, f"  {controller_action_bar}")
        return lines
    if "validation" in payload:
        validation = payload.get("validation") or {}
        task_id = (
            payload.get("task_id")
            or ((payload.get("canonical_views") or {}).get("task_state") or {}).get("task_id")
            or "unknown"
        )
        state = "ok" if validation.get("ok") else "failed"
        command = validation.get("command") or "n/a"
        exit_code = validation.get("exit_code")
        return [
            f"validate: {task_id} {state} exit={exit_code if exit_code is not None else 'n/a'} command={command}",
            _payload_json(payload),
        ]
    if payload.get("shell_view") == "family":
        peer_summary = payload.get("peer_summary") or {}
        family_row = payload.get("family_row") or {}
        background = payload.get("background") or {}
        family_prior = payload.get("family_prior") or {}
        top_peers = ", ".join(
            item.get("task_id", "?")
            for item in (payload.get("peers") or [])[:3]
            if isinstance(item, dict)
        )
        lines = [
            f"family: {payload.get('task_family', 'unknown')} anchor={payload.get('task_id', 'unknown')}",
            (
                f"  family_status={family_row.get('status', 'unknown')} "
                f"trend={family_row.get('trend_status', 'unknown')} "
                f"peers={payload.get('peer_count', 0)}"
            ),
            (
                f"  strong={peer_summary.get('strong_match_count', 0)} "
                f"usable={peer_summary.get('usable_match_count', 0)} "
                f"weak={peer_summary.get('weak_match_count', 0)} "
                f"artifact_hit_rate={family_row.get('avg_artifact_hit_rate', 'n/a')}"
            ),
            f"  consolidation={background.get('status_line', 'unknown')}",
            f"  value={_summary_line(payload, 'value_summary', fallback='no explicit value summary')}",
            f"  reuse={_summary_line(payload, 'reuse_summary', fallback=str(payload.get('prior_seed_summary') or 'no explicit reuse summary'))}",
            (
                f"  prior_strategy={family_prior.get('dominant_strategy_profile', 'unknown')} "
                f"prior_validation={family_prior.get('dominant_validation_style', 'unknown')}"
            ),
            f"  prior_stats={_format_prior_stats(family_prior)}",
            f"  prior_seed={_format_prior_seed(family_prior)}",
        ]
        doc_prior = family_prior.get("family_doc_prior") or {}
        if isinstance(doc_prior, dict) and doc_prior:
            lines.append(
                "  "
                f"doc_prior={doc_prior.get('dominant_source_doc_id') or doc_prior.get('dominant_doc_input') or 'unknown'} "
                f"action={doc_prior.get('dominant_action') or 'unknown'} "
                f"tool={doc_prior.get('dominant_selected_tool') or 'none'} "
                f"samples={doc_prior.get('sample_count', 0)} "
                f"seed={'ready' if doc_prior.get('seed_ready') else 'blocked'}"
            )
            doc_sync_source = str(doc_prior.get("dominant_event_source") or "").strip()
            doc_sync_at = str(doc_prior.get("latest_recorded_at") or "").strip()
            doc_sync_count = int(doc_prior.get("editor_sync_count", 0) or 0)
            if doc_sync_source or doc_sync_at or doc_sync_count:
                lines.append(
                    "  "
                    f"doc_sync={doc_sync_source or 'unknown'} "
                    f"count={doc_sync_count} "
                    f"last={doc_sync_at or 'unknown'}"
                )
        reviewer_prior = family_prior.get("family_reviewer_prior") or {}
        reviewer_prior_line = _format_reviewer_prior_summary(reviewer_prior)
        if reviewer_prior_line:
            lines.append(f"  {reviewer_prior_line}")
        reviewer_usage_line = _format_reviewer_prior_usage(reviewer_prior)
        if reviewer_usage_line:
            lines.append(f"  {reviewer_usage_line}")
        if not family_prior.get("seed_ready"):
            lines.append(
                f"  recommendation={family_prior.get('seed_recommendation', 'record more successful samples for this family')}"
            )
        dream_reason = _format_dream_reason(family_prior)
        if dream_reason:
            lines.append(f"  dream_reason={dream_reason}")
        lines.extend(
            [
                f"  top_peers={top_peers or 'none'}",
                _payload_json(payload),
            ]
        )
        return lines
    if payload.get("shell_view") == "show" and "session_path" in payload and "canonical_views" in payload:
        task_state = (payload.get("canonical_views") or {}).get("task_state", {})
        strategy = (payload.get("canonical_views") or {}).get("strategy", {})
        planner = (payload.get("canonical_views") or {}).get("planner", {})
        maintenance = (payload.get("canonical_views") or {}).get("maintenance", {})
        routing = ((payload.get("canonical_views") or {}).get("routing") or {}).get("summary", {})
        instrumentation = (payload.get("canonical_views") or {}).get("instrumentation", {})
        controller = (payload.get("canonical_views") or {}).get("controller", {})
        validation_status = task_state.get("validation_ok")
        validation_label = "unknown"
        if validation_status is True:
            validation_label = "ok"
        elif validation_status is False:
            validation_label = "failed"
        lines = [
            f"show: {task_state.get('task_id', 'unknown')}",
            (
                f"  status={task_state.get('status', 'unknown')} "
                f"family={strategy.get('task_family', 'unknown')} "
                f"strategy={strategy.get('strategy_profile', 'unknown')} "
                f"trust={strategy.get('trust_signal', 'unknown')}"
            ),
            (
                f"  next={planner.get('next_action', 'unknown')} "
                f"validation={validation_label} "
                f"instrumentation={instrumentation.get('status', 'unknown')}"
            ),
            (
                f"  roles={','.join(strategy.get('role_sequence', []) or ['unknown'])} "
                f"routed_roles={routing.get('routed_role_count', 0)} "
                f"artifacts={routing.get('routed_artifact_ref_count', 0)}"
            ),
            (
                f"  learning={maintenance.get('auto_learning_status', 'manual_only')} "
                f"source={maintenance.get('last_learning_source', 'none') or 'none'} "
                f"observed={maintenance.get('observed_changed_file_count', 0)}"
            ),
        ]
        controller_line = _format_controller_summary(controller)
        if controller_line:
            lines.append(f"  {controller_line}")
        controller_action_bar = format_controller_action_bar_payload(
            payload.get("controller_action_bar")
        ) or format_controller_action_bar(
            controller,
            task_id=task_state.get("task_id"),
        )
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if "evaluation" in payload:
        evaluation = payload["evaluation"] or {}
        task_id = (
            evaluation.get("task_id")
            or payload.get("task_id")
            or ((payload.get("canonical_views") or {}).get("task_state") or {}).get("task_id")
            or "unknown"
        )
        lines = [
            f"evaluation: {task_id} {evaluation.get('status', 'unknown')} score={evaluation.get('score', 'n/a')}",
        ]
        controller_action_bar = format_controller_action_bar_payload(payload.get("controller_action_bar"))
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if "peer_summary" in payload and "task_family" in payload:
        peer_summary = payload["peer_summary"] or {}
        anchor = payload.get("anchor") or {}
        background = payload.get("background") or {}
        top_peers = ", ".join(item.get("task_id", "?") for item in (payload.get("peers") or [])[:2] if isinstance(item, dict))
        top_suffix = f" top={top_peers}" if top_peers else ""
        return [
            f"compare-family: {anchor.get('task_id', payload.get('task_id', 'unknown'))} family={payload.get('task_family')} peers={payload.get('peer_count', 0)} strong={peer_summary.get('strong_match_count', 0)} usable={peer_summary.get('usable_match_count', 0)} weak={peer_summary.get('weak_match_count', 0)} consolidation={background.get('status_line', 'unknown')}{top_suffix}",
            _payload_json(payload),
        ]
    if "dashboard_summary" in payload and "family_rows" in payload:
        summary = payload["dashboard_summary"] or {}
        background = payload.get("background") or {}
        blocked_recommendations = summary.get("blocked_family_recommendations") or []
        top_families = ", ".join(
            f"{item.get('task_family')}:{item.get('status')}:{'ready' if item.get('prior_seed_ready') else 'blocked'}"
            for item in (payload.get("family_rows") or [])[:2]
            if isinstance(item, dict)
        )
        top_suffix = f" top={top_families}" if top_families else ""
        blocker_suffix = ""
        if blocked_recommendations and isinstance(blocked_recommendations, list):
            preview = ", ".join(
                f"{item.get('task_family')}:{item.get('gate')}"
                for item in blocked_recommendations[:2]
                if isinstance(item, dict)
            )
            if preview:
                blocker_suffix = f" blockers={preview}"
        doc_ready = int(summary.get("doc_prior_ready_count", 0) or 0)
        doc_blocked = int(summary.get("doc_prior_blocked_count", 0) or 0)
        doc_suffix = f" doc_priors={doc_ready}/{doc_blocked}" if (doc_ready or doc_blocked) else ""
        lines = [
            f"dashboard: sessions={summary.get('session_count', 0)} families={summary.get('family_count', 0)} strong={summary.get('strong_match_count', 0)} usable={summary.get('usable_match_count', 0)} weak={summary.get('weak_match_count', 0)} seed_ready={summary.get('prior_seed_ready_count', 0)} blocked={summary.get('prior_seed_blocked_count', 0)} consolidation={background.get('status_line', 'unknown')}{top_suffix}{blocker_suffix}{doc_suffix}",
            f"  proof={_summary_line(summary, 'proof_summary', fallback='no explicit proof summary')}",
        ]
        if doc_ready or doc_blocked:
            top_doc = next(
                (
                    item
                    for item in (payload.get("family_rows") or [])
                    if isinstance(item, dict) and int(item.get("prior_doc_sample_count", 0) or 0) > 0
                ),
                {},
            )
            top_doc_suffix = ""
            if isinstance(top_doc, dict) and top_doc:
                top_doc_family = str(top_doc.get("task_family") or "").strip()
                top_doc_id = str(top_doc.get("prior_doc_source_doc_id") or "").strip()
                if top_doc_family and top_doc_id:
                    top_doc_suffix = f" top={top_doc_family}:{top_doc_id}"
            lines.append(f"  doc_priors={doc_ready} ready / {doc_blocked} blocked{top_doc_suffix}")
        editor_sync_families = int(summary.get("doc_editor_sync_family_count", 0) or 0)
        editor_sync_events = int(summary.get("doc_editor_sync_event_count", 0) or 0)
        if editor_sync_families or editor_sync_events:
            sync_family = str(summary.get("top_doc_editor_sync_family") or "").strip()
            sync_source = str(summary.get("top_doc_editor_sync_source") or "").strip()
            sync_at = str(summary.get("top_doc_editor_sync_at") or "").strip()
            top_sync_suffix = ""
            if sync_family and sync_source:
                top_sync_suffix = f" top={sync_family}:{sync_source}"
            if sync_at:
                top_sync_suffix = f"{top_sync_suffix} at={sync_at}".rstrip()
            lines.append(f"  editor_syncs={editor_sync_events} across {editor_sync_families} families{top_sync_suffix}")
        if (
            blocked_recommendations
            and isinstance(blocked_recommendations, list)
            and isinstance(blocked_recommendations[0], dict)
        ):
            blocker_reason = str((blocked_recommendations[0] or {}).get("reason") or "").strip()
            if blocker_reason:
                lines.append(f"  blocker_reason={blocker_reason}")
        lines.append(_payload_json(payload))
        return lines
    if "tasks" in payload and "task_count" in payload:
        tasks = payload.get("tasks") or []
        preview = ", ".join(
            f"{item.get('index')}) {item.get('task_id')}:{item.get('instrumentation_status')}"
            for item in tasks[:3]
            if isinstance(item, dict)
        )
        preview_suffix = f" top={preview}" if preview else ""
        return [
            f"tasks: count={payload.get('task_count', 0)}{preview_suffix}",
            _payload_json(payload),
        ]
    if "session_path" in payload and "canonical_views" in payload:
        task_state = (payload.get("canonical_views") or {}).get("task_state", {})
        strategy = (payload.get("canonical_views") or {}).get("strategy", {})
        controller = (payload.get("canonical_views") or {}).get("controller", {})
        validation_status = task_state.get("validation_ok")
        validation_label = "unknown"
        if validation_status is True:
            validation_label = "ok"
        elif validation_status is False:
            validation_label = "failed"
        lines = [
            (
                f"session: {task_state.get('task_id', 'unknown')} "
                f"status={task_state.get('status', 'unknown')} "
                f"family={strategy.get('task_family', 'unknown')} "
                f"strategy={strategy.get('strategy_profile', 'unknown')} "
                f"trust={strategy.get('trust_signal', 'unknown')} "
                f"validation={validation_label}"
            ),
        ]
        controller_line = _format_controller_summary(controller)
        if controller_line:
            lines.append(f"  {controller_line}")
        controller_action_bar = format_controller_action_bar_payload(
            payload.get("controller_action_bar")
        ) or format_controller_action_bar(
            controller,
            task_id=task_state.get("task_id"),
        )
        if controller_action_bar:
            lines.append(f"  {controller_action_bar}")
        lines.append(_payload_json(payload))
        return lines
    if "task_id" in payload and ("runner" in payload or "session_path" in payload):
        return [
            f"task: {payload.get('task_id')} runner={payload.get('runner', 'unknown')} session={payload.get('session_path', 'n/a')}",
            _payload_json(payload),
        ]
    return [_payload_json(payload)]


def run_shell(
    workbench,
    initial_task_id: str | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    write_fn: Callable[[str], None] = print,
) -> int:
    raw_mode = False
    current_task_id = initial_task_id
    current_prompt_action: str | None = None
    cleared_current_task = False
    repo_root = getattr(getattr(workbench, "_config", None), "repo_root", None) or getattr(workbench, "repo_root", None) or "."
    project_scope = getattr(getattr(workbench, "_config", None), "project_scope", None)
    write_fn("Aionis shell")
    write_fn(f"repo: {repo_root}")
    if project_scope:
        write_fn(f"scope: {project_scope}")
    if initial_task_id:
        write_fn(f"task: {initial_task_id}")
    status_payload = workbench.shell_status(task_id=initial_task_id)
    current_task_id = current_task_id or status_payload.get("task_id")
    write_fn(status_payload["text"])
    startup_action_bar = _payload_controller_action_bar(status_payload)
    startup_controller_hint = format_controller_action_bar_payload(startup_action_bar) or format_controller_action_bar(
        status_payload.get("controller"),
        task_id=status_payload.get("task_id"),
    )
    current_prompt_action = primary_action_from_action_bar(startup_action_bar) or primary_controller_action(
        status_payload.get("controller")
    )
    if startup_controller_hint:
        write_fn(startup_controller_hint)
    startup_hint = _startup_mode_hint(workbench)
    if startup_hint:
        write_fn(startup_hint)
    write_fn("Use /help to see available commands.")

    while True:
        try:
            if current_task_id and current_prompt_action:
                prompt = f"aionis[{current_task_id}|{current_prompt_action}]> "
            elif current_task_id:
                prompt = f"aionis[{current_task_id}]> "
            else:
                prompt = "aionis> "
            raw = input_fn(prompt)
        except EOFError:
            return 0

        result = dispatch_shell_input(workbench, raw, current_task_id=current_task_id)
        kind = result["kind"]
        text = result.get("text") or ""
        payload = result.get("payload")
        prior_task_id = current_task_id
        payload_task_id = _payload_task_id(payload)
        if payload_task_id:
            current_task_id = payload_task_id
        payload_controller = _payload_controller(payload)
        payload_action_bar = _payload_controller_action_bar(payload)
        if payload_controller is not None:
            current_prompt_action = primary_action_from_action_bar(payload_action_bar) or primary_controller_action(
                payload_controller
            )
        elif payload_action_bar is not None:
            current_prompt_action = primary_action_from_action_bar(payload_action_bar)
        elif payload_task_id and payload_task_id != prior_task_id:
            current_prompt_action = None

        if text:
            write_fn(text)
        if payload and kind == "status":
            status_controller_hint = format_controller_action_bar_payload(payload_action_bar) or format_controller_action_bar(
                payload.get("controller"),
                task_id=payload.get("task_id"),
            )
            if status_controller_hint:
                write_fn(status_controller_hint)
        if kind == "setting" and payload:
            if payload.get("setting") == "raw_mode":
                requested = payload.get("value")
                if requested == "toggle":
                    raw_mode = not raw_mode
                elif requested == "on":
                    raw_mode = True
                elif requested == "off":
                    raw_mode = False
                write_fn(f"raw mode: {'on' if raw_mode else 'off'}")
            if payload.get("setting") == "current_task":
                requested_task = payload.get("value")
                current_task_id = requested_task if isinstance(requested_task, str) and requested_task.strip() else None
                current_prompt_action = None
                cleared_current_task = current_task_id is None
        if payload and kind in {"result", "show"}:
            lines = _render_result_payload(payload)
            summary, details = lines[0], lines[1:]
            write_fn(summary)
            if kind == "show":
                for line in details[:-1]:
                    write_fn(line)
                if raw_mode and details:
                    write_fn(details[-1])
            elif raw_mode:
                for line in details:
                    write_fn(line)
        if payload and kind == "error":
            lines = _render_result_payload(payload)
            summary, details = lines[0], lines[1:]
            write_fn(summary)
            for line in details[:-1]:
                write_fn(line)
            if raw_mode and details:
                write_fn(details[-1])
        if payload and kind == "status" and raw_mode:
            write_fn(_payload_json(payload))
        if payload and kind == "error" and raw_mode and not isinstance(payload, dict):
            write_fn(_payload_json({"error": text}))
        if result.get("should_refresh_status"):
            status_payload = workbench.shell_status(task_id=current_task_id)
            if not cleared_current_task:
                current_task_id = status_payload.get("task_id") or current_task_id
            else:
                cleared_current_task = False
            write_fn(status_payload["text"])
            refresh_action_bar = _payload_controller_action_bar(status_payload)
            current_prompt_action = primary_action_from_action_bar(refresh_action_bar) or primary_controller_action(
                status_payload.get("controller")
            )
            refresh_controller_hint = format_controller_action_bar_payload(refresh_action_bar) or format_controller_action_bar(
                status_payload.get("controller"),
                task_id=status_payload.get("task_id"),
            )
            if refresh_controller_hint:
                write_fn(refresh_controller_hint)
        if result.get("should_exit"):
            return 0
