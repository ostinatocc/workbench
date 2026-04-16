from __future__ import annotations

import shlex
from typing import Any

from .controller_shell import build_controller_action_bar, controller_action_bar_payload
from .provider_profiles import SAFE_CREDENTIALS_HINT
from .shell_commands import find_shell_command


def parse_shell_input(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    if not stripped:
        return None, ""
    if stripped.startswith("/"):
        stripped = stripped[1:]
    parts = stripped.split(" ", 1)
    command_name = parts[0].strip() if parts and parts[0] else None
    args = parts[1].strip() if len(parts) > 1 else ""
    return command_name, args


def _parse_shell_args(args: str) -> tuple[list[str], dict[str, list[str]]]:
    positional: list[str] = []
    options: dict[str, list[str]] = {}
    tokens = shlex.split(args)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                options.setdefault(token, []).append("true")
                index += 1
                continue
            options.setdefault(token, []).append(tokens[index + 1])
            index += 2
            continue
        positional.append(token)
        index += 1
    return positional, options


def _coerce_payload(result: Any) -> dict[str, Any]:
    if hasattr(result, "__dict__"):
        payload = dict(result.__dict__)
        canonical_surface = payload.get("canonical_surface")
        canonical_views = payload.get("canonical_views")
        if hasattr(canonical_surface, "__dict__"):
            payload["canonical_surface"] = dict(canonical_surface.__dict__)
        if hasattr(canonical_views, "__dict__"):
            payload["canonical_views"] = dict(canonical_views.__dict__)
        return payload
    if isinstance(result, dict):
        return result
    return {"value": result}


def _live_preflight_summary_line(payload: dict[str, Any]) -> str:
    operation = str(payload.get("operation") or "task")
    task_id = str(payload.get("task_id") or "unknown")
    status = "ready" if bool(payload.get("ready")) else "blocked"
    live_ready_summary = str(payload.get("live_ready_summary") or payload.get("mode") or "unknown")
    recovery_summary = str(payload.get("recovery_summary") or "").strip()
    recovery_hint = str(payload.get("recovery_command_hint") or "").strip()
    parts = [f"{operation}-preflight: {task_id}", status, live_ready_summary]
    if recovery_summary:
        parts.append(f"recovery={recovery_summary}")
    if recovery_hint and status != "ready":
        parts.append(f"hint={recovery_hint}")
    return " | ".join(parts)


def _host_contract_payload(workbench) -> dict[str, Any]:
    factory = getattr(workbench, "host_contract", None)
    if not callable(factory):
        return {}
    try:
        payload = factory()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _doctor_payload(workbench) -> dict[str, Any]:
    factory = getattr(workbench, "doctor", None)
    if not callable(factory):
        return {}
    try:
        payload = factory()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _primary_validation_path(canonical_views: dict[str, Any], family_prior: dict[str, Any]) -> str:
    strategy = canonical_views.get("strategy") or {}
    planner = canonical_views.get("planner") or {}
    validation_paths = strategy.get("validation_paths") or planner.get("pending_validations") or []
    if validation_paths:
        first = validation_paths[0]
        return first if isinstance(first, str) and first.strip() else "none"
    fallback = family_prior.get("dominant_validation_command")
    return fallback.strip() if isinstance(fallback, str) and fallback.strip() else "none"


def _reuse_summary(
    *,
    peer_summary: dict[str, Any],
    family_row: dict[str, Any],
    family_prior: dict[str, Any],
    primary_validation: str,
) -> str:
    strong = int(peer_summary.get("strong_match_count") or 0)
    usable = int(peer_summary.get("usable_match_count") or 0)
    family_status = str(family_row.get("status") or "unknown")
    strategy = str(family_prior.get("dominant_strategy_profile") or "unknown")
    if family_prior.get("seed_ready"):
        return (
            f"seed_ready family={family_status} strong={strong} usable={usable} "
            f"strategy={strategy} validation={primary_validation}"
        )
    gate = str(family_prior.get("seed_gate") or "unknown")
    return (
        f"seed_blocked family={family_status} strong={strong} usable={usable} "
        f"gate={gate} validation={primary_validation}"
    )


def _value_summary(
    *,
    peer_summary: dict[str, Any],
    family_prior: dict[str, Any],
    primary_validation: str,
    instrumentation_status: str,
) -> str:
    strong = int(peer_summary.get("strong_match_count") or 0)
    usable = int(peer_summary.get("usable_match_count") or 0)
    recommendation = str(family_prior.get("seed_recommendation") or "").strip()
    if family_prior.get("seed_ready") and strong > 0 and primary_validation != "none":
        return "ready family reuse is available with a trusted prior and a focused validation path"
    if family_prior.get("seed_ready") and primary_validation != "none":
        return "family reuse is available; validate the focused path before widening scope"
    if (strong > 0 or usable > 0) and recommendation:
        return f"reuse signals exist but the prior is still blocked; {recommendation}"
    if instrumentation_status in {"strong_match", "usable_match"} and primary_validation != "none":
        return "reuse is plausible on this task; validate the focused path to strengthen the family prior"
    if primary_validation != "none":
        return "no strong family prior yet; use the focused validation path to record one"
    return "no reusable family prior yet; keep the next task narrow and record one validated success"


def _workflow_path(view: str) -> str:
    if view == "plan":
        return "/plan -> /review -> /fix -> /validate"
    if view == "review":
        return "/review -> /fix -> /validate"
    return "/work -> /next -> /fix -> /validate"


def _recommended_command(*, view: str, task_id: str, primary_validation: str) -> str:
    if view == "plan":
        return f"/review {task_id}".strip()
    if view == "review":
        return f"/fix {task_id}".strip() if primary_validation != "none" else f"/next {task_id}".strip()
    if primary_validation != "none":
        return f"/next {task_id}".strip()
    return f"/review {task_id}".strip()


def _reviewer_payload(canonical_views: dict[str, Any]) -> dict[str, Any]:
    reviewer = canonical_views.get("reviewer")
    return reviewer if isinstance(reviewer, dict) else {}


def _review_pack_payload(canonical_views: dict[str, Any]) -> dict[str, Any]:
    review_packs = canonical_views.get("review_packs")
    return review_packs if isinstance(review_packs, dict) else {}


def _controller_action_bar_from_payload(
    payload: dict[str, Any] | None,
    *,
    task_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    existing = payload.get("controller_action_bar")
    if isinstance(existing, dict):
        return existing
    canonical_views = payload.get("canonical_views")
    if not isinstance(canonical_views, dict):
        return None
    task_state = canonical_views.get("task_state")
    resolved_task_id = task_id
    if not resolved_task_id and isinstance(task_state, dict):
        raw_task_id = task_state.get("task_id")
        if isinstance(raw_task_id, str) and raw_task_id.strip():
            resolved_task_id = raw_task_id.strip()
    controller = canonical_views.get("controller")
    return controller_action_bar_payload(controller, task_id=resolved_task_id)


def _attach_controller_action_bar(
    payload: dict[str, Any],
    *,
    task_id: str | None,
) -> dict[str, Any]:
    action_bar = _controller_action_bar_from_payload(payload, task_id=task_id)
    if action_bar is None:
        return payload
    enriched = dict(payload)
    enriched["controller_action_bar"] = action_bar
    return enriched


def _controller_payload(workbench, *, task_id: str | None) -> dict[str, Any]:
    if not task_id:
        return {}
    inspector = getattr(workbench, "inspect_session", None)
    if not callable(inspector):
        return {}
    try:
        payload = inspector(task_id=task_id)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    canonical_views = payload.get("canonical_views")
    if not isinstance(canonical_views, dict):
        return {}
    controller = canonical_views.get("controller")
    return controller if isinstance(controller, dict) else {}


def _contextual_help_text(workbench, *, task_id: str | None) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        return ""
    controller = _controller_payload(workbench, task_id=task_id)
    if not controller:
        return ""
    action_bar = build_controller_action_bar(controller, task_id=task_id)
    if action_bar is None:
        return ""
    return (
        "\n"
        f"Current task controller: {task_id} status={action_bar.status}\n"
        f"controller_actions: recommended={action_bar.recommended_command} "
        f"allowed={' | '.join(action_bar.allowed_commands[:3])}"
    )


def _controller_preflight_payload(
    workbench,
    *,
    task_id: str,
    shell_command: str,
    required_action: str,
) -> dict[str, Any] | None:
    controller = _controller_payload(workbench, task_id=task_id)
    if not controller:
        return None
    allowed_actions = [
        item.strip()
        for item in (controller.get("allowed_actions") or [])
        if isinstance(item, str) and item.strip()
    ]
    if required_action in allowed_actions:
        return None
    guard_reasons = controller.get("guard_reasons") or []
    reason = next(
        (
            str(item.get("reason") or "").strip()
            for item in guard_reasons
            if isinstance(item, dict)
            and str(item.get("action") or "").strip() == required_action
            and str(item.get("reason") or "").strip()
        ),
        "",
    )
    recommended_command = f"/show {task_id}".strip()
    if "resume" in allowed_actions and required_action == "plan_start":
        recommended_command = f"/resume {task_id}".strip()
    elif "inspect_context" in allowed_actions and required_action == "resume":
        recommended_command = f"/show {task_id}".strip()
    return {
        "shell_view": "controller_preflight",
        "task_id": task_id,
        "command": shell_command,
        "status": "blocked",
        "controller_status": str(controller.get("status") or "unknown"),
        "required_action": required_action,
        "allowed_actions": allowed_actions,
        "reason": reason or "controller action is not allowed in the current task-session state",
        "recommended_command": recommended_command,
        "canonical_views": {"controller": controller},
    }


def _checklist_command_hint(doctor_payload: dict[str, Any], name: str) -> str:
    checklist = doctor_payload.get("setup_checklist") or []
    if not isinstance(checklist, list):
        return ""
    for item in checklist:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "") != name:
            continue
        return str(item.get("command_hint") or "")
    return ""


def _recovery_summary(recovery_class: str) -> str:
    normalized = str(recovery_class or "").strip()
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
    return "host recovery state is unknown; inspect doctor/setup output"


def _recovery_guidance(
    *,
    ready: bool,
    execution_reason: str,
    runtime_reason: str,
    recommendations: list[str],
    doctor_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    doctor_payload = doctor_payload if isinstance(doctor_payload, dict) else {}
    capability_state = str(doctor_payload.get("capability_state") or "")
    credentials_hint = _checklist_command_hint(doctor_payload, "credentials_configured") or SAFE_CREDENTIALS_HINT
    runtime_hint = _checklist_command_hint(doctor_payload, "runtime_available") or "curl -fsS ${AIONIS_BASE_URL:-http://127.0.0.1:3101}/health"
    if ready:
        return "ready", "/run TASK_ID \"task description\""
    if capability_state == "inspect_only_missing_credentials_and_runtime":
        return "missing_credentials_and_runtime", credentials_hint
    if capability_state == "inspect_only_missing_credentials":
        return "missing_credentials", credentials_hint
    if capability_state == "inspect_only_missing_runtime":
        return "missing_runtime", runtime_hint
    if execution_reason == "model_credentials_missing" and runtime_reason == "runtime_health_unreachable":
        return "missing_credentials_and_runtime", credentials_hint
    if execution_reason == "model_credentials_missing":
        return "missing_credentials", credentials_hint
    if runtime_reason == "runtime_health_unreachable":
        return "missing_runtime", runtime_hint
    if runtime_reason.startswith("runtime_health_http_"):
        return "runtime_degraded", runtime_hint
    if recommendations:
        return "degraded", recommendations[0]
    return "unknown", "/doctor"


def _structured_host_error(operation: str, exc: Exception, workbench, *, task_id: str | None = None) -> dict[str, Any]:
    doctor_payload = _doctor_payload(workbench)
    host_payload = _host_contract_payload(workbench)
    contract = host_payload.get("contract") if isinstance(host_payload, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    execution_host = contract.get("execution_host") or {}
    runtime_host = contract.get("runtime_host") or {}
    execution_mode = str(execution_host.get("mode") or "live_enabled")
    execution_health = str(execution_host.get("health_status") or "unknown")
    execution_reason = str(execution_host.get("health_reason") or "none")
    runtime_health = str(runtime_host.get("health_status") or "unknown")
    runtime_reason = str(runtime_host.get("health_reason") or "none")

    recommendations: list[str] = []
    if execution_reason == "model_credentials_missing":
        recommendations.append("configure model credentials to enable live execution")
    if runtime_reason == "runtime_health_unreachable":
        recommendations.append("start or configure Aionis Runtime via AIONIS_BASE_URL")
    recommendations.append("continue in inspect-only mode via /plan, /work, /review, /validate, or /ingest")
    recovery_class, recovery_command_hint = _recovery_guidance(
        ready=False,
        execution_reason=execution_reason,
        runtime_reason=runtime_reason,
        recommendations=recommendations,
        doctor_payload=doctor_payload,
    )
    recovery_summary = _recovery_summary(recovery_class)

    return {
        "shell_view": "host_error",
        "operation": operation,
        "task_id": task_id,
        "error": str(exc),
        "host_contract": contract,
        "execution_mode": execution_mode,
        "execution_health": execution_health,
        "execution_reason": execution_reason,
        "runtime_health": runtime_health,
        "runtime_reason": runtime_reason,
        "recovery_class": recovery_class,
        "recovery_summary": recovery_summary,
        "recovery_command_hint": recovery_command_hint,
        "recommendations": recommendations,
    }


def _live_execution_preflight_payload(workbench, *, operation: str, task_id: str | None = None) -> dict[str, Any]:
    doctor_payload = _doctor_payload(workbench)
    host_payload = _host_contract_payload(workbench)
    contract = host_payload.get("contract") if isinstance(host_payload, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    execution_host = contract.get("execution_host") or {}
    runtime_host = contract.get("runtime_host") or {}
    execution_mode = str(execution_host.get("mode") or doctor_payload.get("mode") or "inspect_only")
    execution_health = str(execution_host.get("health_status") or "unknown")
    execution_reason = str(execution_host.get("health_reason") or "none")
    runtime_health = str(runtime_host.get("health_status") or "unknown")
    runtime_reason = str(runtime_host.get("health_reason") or "none")
    ready = bool(doctor_payload.get("live_ready"))
    recommendations = list(doctor_payload.get("recommendations") or [])
    if ready and not recommendations:
        recommendations.append(f"start live execution with /{operation}")
    elif not ready and not recommendations:
        recommendations.append("continue in inspect-only mode via /plan, /work, /review, /validate, or /ingest")
    recovery_class, recovery_command_hint = _recovery_guidance(
        ready=ready,
        execution_reason=execution_reason,
        runtime_reason=runtime_reason,
        recommendations=recommendations,
        doctor_payload=doctor_payload,
    )
    recovery_summary = _recovery_summary(recovery_class)
    return {
        "shell_view": "live_preflight",
        "operation": operation,
        "task_id": task_id,
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "mode": str(doctor_payload.get("mode") or "inspect-only"),
        "live_ready_summary": str(doctor_payload.get("live_ready_summary") or ("live-ready" if ready else "inspect-only")),
        "capability_state": str(doctor_payload.get("capability_state") or ""),
        "capability_summary": str(doctor_payload.get("capability_summary") or ""),
        "execution_mode": execution_mode,
        "execution_health": execution_health,
        "execution_reason": execution_reason,
        "runtime_health": runtime_health,
        "runtime_reason": runtime_reason,
        "recovery_class": recovery_class,
        "recovery_summary": recovery_summary,
        "recovery_command_hint": recovery_command_hint,
        "host_contract": contract,
        "recommendations": recommendations,
    }


def _live_execution_preflight_error(workbench, *, operation: str, task_id: str | None = None) -> dict[str, Any] | None:
    host_payload = _host_contract_payload(workbench)
    contract = host_payload.get("contract") if isinstance(host_payload, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    execution_host = contract.get("execution_host") or {}
    runtime_host = contract.get("runtime_host") or {}
    raw_execution_health = execution_host.get("health_status")
    raw_runtime_health = runtime_host.get("health_status")
    if raw_execution_health is None and raw_runtime_health is None:
        return None
    execution_health = str(raw_execution_health or "unknown")
    runtime_health = str(raw_runtime_health or "unknown")
    if execution_health == "available" and runtime_health == "available":
        return None
    return {
        "kind": "error",
        "text": "",
        "payload": _structured_host_error(
            operation,
            RuntimeError("live execution blocked by host preflight"),
            workbench,
            task_id=task_id,
        ),
        "should_exit": False,
        "should_refresh_status": False,
    }


def _resolve_task_id(raw: str, current_task_id: str | None) -> str | None:
    resolved = raw.strip()
    if resolved:
        return resolved
    return current_task_id


def dispatch_shell_input(workbench, text: str, *, current_task_id: str | None = None) -> dict[str, Any]:
    stripped_text = text.strip()
    if stripped_text and not stripped_text.startswith("/") and " " in stripped_text:
        return {
            "kind": "help",
            "text": "Use /run, /resume, /ingest, or /help.",
            "payload": None,
            "should_exit": False,
            "should_refresh_status": False,
        }

    command_name, args = parse_shell_input(text)
    if not command_name:
        return {
            "kind": "noop",
            "text": "",
            "payload": None,
            "should_exit": False,
            "should_refresh_status": False,
        }

    command = find_shell_command(command_name)
    if command is None:
        return {
            "kind": "help",
            "text": "Use /run, /resume, /ingest, or /help.",
            "payload": None,
            "should_exit": False,
            "should_refresh_status": False,
        }

    if command.name == "exit":
        return {
            "kind": "exit",
            "text": "Exiting Aionis shell.",
            "payload": None,
            "should_exit": True,
            "should_refresh_status": False,
        }
    if command.name == "help":
        return {
            "kind": "help",
            "text": "Available commands: /init | /setup | /doctor | /run TASK_ID \"task\" [--target-file PATH] [--validation-command CMD] [--preflight-only] [--one-line] | /resume [TASK_ID] [\"fallback task\"] [--target-file PATH] [--validation-command CMD] [--preflight-only] [--one-line] | /ingest TASK_ID \"task\" \"summary\" [--target-file PATH] [--changed-file PATH] [--validation-command CMD] [--validation-summary TEXT] [--validation-ok true|false] | /work [TASK_ID] | /next [TASK_ID] | /fix [TASK_ID] | /plan [TASK_ID] | /review [TASK_ID] | /show [TASK_ID] | /family [TASK_ID] [--limit N] | /hosts | /validate [TASK_ID] | /session [TASK_ID] | /evaluate [TASK_ID] | /compare-family [TASK_ID] [--limit N] | /dashboard [--limit N] [--family-limit N] | /consolidate [--limit N] [--family-limit N] | /app show [TASK_ID] | /app plan [TASK_ID] --prompt TEXT [--title TEXT] [--type TYPE] [--stack ITEM] [--feature ITEM] [--design-direction TEXT] [--criterion NAME[:THRESHOLD[:WEIGHT]]] [--live] | /app sprint [TASK_ID] --sprint-id ID --goal TEXT [--scope ITEM] [--acceptance-check CMD] [--done-definition TEXT] [--proposed-by WHO] [--approved] | /app negotiate [TASK_ID] [--sprint-id ID] [--objection NOTE] [--live] | /app retry [TASK_ID] [--sprint-id ID] [--revision-note NOTE] [--live] | /app qa [TASK_ID] --sprint-id ID [--status passed|failed|auto] [--summary TEXT] [--score NAME=VALUE] [--blocker NOTE] [--live] | /doc show [TASK_ID] | /doc list [--limit N] | /doc inspect TARGET [--limit N] | /doc compile INPUT [--emit MODE] [--strict] | /doc run INPUT --registry PATH [--input-kind KIND] | /doc publish INPUT [--input-kind KIND] | /doc recover INPUT [--input-kind KIND] | /doc resume INPUT [--input-kind KIND] [--query-text TEXT] [--candidate TOOL] | /background | /tasks [--limit N] | /latest | /pick N | /status [TASK_ID] | /use TASK_ID | /clear | /raw [on|off|toggle] | /exit"
            + _contextual_help_text(workbench, task_id=current_task_id),
            "payload": None,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "hosts":
        try:
            payload = workbench.host_contract()
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"hosts failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "init":
        try:
            payload = workbench.initialize_project()
            payload["shell_view"] = "init"
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"init failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "setup":
        positional, options = _parse_shell_args(args)
        try:
            payload = workbench.setup(
                pending_only="--pending-only" in options,
                summary="--summary" in options,
                check=options.get("--check", [None])[-1],
                one_line="--one-line" in options,
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"setup failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "doctor":
        positional, options = _parse_shell_args(args)
        try:
            payload = workbench.doctor(
                summary="--summary" in options,
                check=options.get("--check", [None])[-1],
                one_line="--one-line" in options,
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"doctor failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "latest":
        try:
            status_payload = workbench.shell_status(task_id=None)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"latest failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_id = status_payload.get("task_id")
        if not task_id:
            return {
                "kind": "error",
                "text": "latest failed: no recent task was found for this project scope",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "setting",
            "text": f"using latest task: {task_id}",
            "payload": {"setting": "current_task", "value": task_id},
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "tasks":
        positional, options = _parse_shell_args(args)
        limit = 8
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        try:
            payload = workbench.recent_tasks(limit=limit)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"tasks failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "consolidate":
        positional, options = _parse_shell_args(args)
        limit = 48
        family_limit = 8
        status_filter = None
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        if "--family-limit" in options:
            family_limit = int(options["--family-limit"][-1])
        if "--status" in options:
            status_filter = str(options["--status"][-1]).strip()
        try:
            if command_name == "dream" and callable(getattr(workbench, "dream", None)):
                payload = workbench.dream(limit=limit, family_limit=family_limit, status_filter=status_filter)
            else:
                payload = workbench.consolidate(limit=limit, family_limit=family_limit)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"{'dream' if command_name == 'dream' else 'consolidate'} failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "background":
        try:
            payload = workbench.background_status()
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"background failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "doc":
        positional, options = _parse_shell_args(args)
        if not positional:
            return {
                "kind": "help",
                "text": "Usage: /doc show [TASK_ID] | /doc list [--limit N] | /doc inspect TARGET [--limit N] | /doc compile INPUT [--emit MODE] [--strict] | /doc run INPUT --registry PATH [--input-kind KIND] | /doc publish INPUT [--input-kind KIND] | /doc recover INPUT [--input-kind KIND] | /doc resume INPUT [--input-kind KIND] [--query-text TEXT] [--candidate TOOL]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        doc_command = positional[0]
        doc_task_kwargs = {"task_id": current_task_id} if current_task_id else {}
        try:
            if doc_command == "show":
                task_id = current_task_id if len(positional) < 2 else positional[1]
                if not task_id:
                    return {
                        "kind": "help",
                        "text": "Usage: /doc show [TASK_ID]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                payload = workbench.inspect_session(task_id=task_id)
                payload["shell_view"] = "doc_show"
                payload["task_id"] = task_id
            elif doc_command == "list":
                limit = 24
                if "--limit" in options:
                    limit = int(options["--limit"][-1])
                payload = workbench.doc_list(limit=limit)
            elif doc_command == "inspect":
                if len(positional) < 2:
                    return {
                        "kind": "help",
                        "text": "Usage: /doc inspect TARGET [--limit N]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                limit = 8
                if "--limit" in options:
                    limit = int(options["--limit"][-1])
                payload = workbench.doc_inspect(target=positional[1], limit=limit)
            else:
                if len(positional) < 2:
                    return {
                        "kind": "help",
                        "text": "Usage: /doc show [TASK_ID] | /doc list [--limit N] | /doc inspect TARGET [--limit N] | /doc compile INPUT [--emit MODE] [--strict] | /doc run INPUT --registry PATH [--input-kind KIND] | /doc publish INPUT [--input-kind KIND] | /doc recover INPUT [--input-kind KIND] | /doc resume INPUT [--input-kind KIND] [--query-text TEXT] [--candidate TOOL]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                input_path = positional[1]
            if doc_command in {"show", "list", "inspect"}:
                pass
            elif doc_command == "compile":
                payload = workbench.doc_compile(
                    input_path=input_path,
                    emit=(options.get("--emit") or ["all"])[-1],
                    strict="--strict" in options,
                    **doc_task_kwargs,
                )
            elif doc_command == "run":
                registry_path = (options.get("--registry") or [None])[-1]
                if not registry_path:
                    return {
                        "kind": "help",
                        "text": "Usage: /doc run INPUT --registry PATH [--input-kind KIND]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                payload = workbench.doc_run(
                    input_path=input_path,
                    registry_path=registry_path,
                    input_kind=(options.get("--input-kind") or ["source"])[-1],
                    **doc_task_kwargs,
                )
            elif doc_command == "publish":
                payload = workbench.doc_publish(
                    input_path=input_path,
                    input_kind=(options.get("--input-kind") or ["source"])[-1],
                    **doc_task_kwargs,
                )
            elif doc_command == "recover":
                payload = workbench.doc_recover(
                    input_path=input_path,
                    input_kind=(options.get("--input-kind") or ["source"])[-1],
                    **doc_task_kwargs,
                )
            elif doc_command == "resume":
                payload = workbench.doc_resume(
                    input_path=input_path,
                    input_kind=(options.get("--input-kind") or ["recover-result"])[-1],
                    query_text=(options.get("--query-text") or [None])[-1],
                    candidates=options.get("--candidate", []),
                    **doc_task_kwargs,
                )
            else:
                return {
                    "kind": "help",
                    "text": "Usage: /doc show [TASK_ID] | /doc list [--limit N] | /doc inspect TARGET [--limit N] | /doc compile INPUT [--emit MODE] [--strict] | /doc run INPUT --registry PATH [--input-kind KIND] | /doc publish INPUT [--input-kind KIND] | /doc recover INPUT [--input-kind KIND] | /doc resume INPUT [--input-kind KIND] [--query-text TEXT] [--candidate TOOL]",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"doc {doc_command} failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "app":
        positional, options = _parse_shell_args(args)
        if not positional:
            return {
                "kind": "help",
                "text": "Usage: /app show [TASK_ID] | /app plan [TASK_ID] --prompt TEXT [--title TEXT] [--type TYPE] [--stack ITEM] [--feature ITEM] [--design-direction TEXT] [--criterion NAME[:THRESHOLD[:WEIGHT]]] [--live] | /app sprint [TASK_ID] --sprint-id ID --goal TEXT [--scope ITEM] [--acceptance-check CMD] [--done-definition TEXT] [--proposed-by WHO] [--approved] | /app negotiate [TASK_ID] [--sprint-id ID] [--objection NOTE] [--live] | /app retry [TASK_ID] [--sprint-id ID] [--revision-note NOTE] [--live] | /app qa [TASK_ID] --sprint-id ID [--status passed|failed|auto] [--summary TEXT] [--score NAME=VALUE] [--blocker NOTE] [--live]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        app_command = positional[0]
        task_id = current_task_id if len(positional) < 2 else positional[1]
        if app_command == "show":
            if not task_id:
                return {
                    "kind": "help",
                    "text": "Usage: /app show [TASK_ID]",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            try:
                payload = workbench.app_show(task_id=task_id)
            except Exception as exc:
                return {
                    "kind": "error",
                    "text": f"app show failed: {exc}",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        if app_command == "ship":
            prompt = (options.get("--prompt") or [None])[-1]
            if not task_id or not prompt:
                return {
                    "kind": "help",
                    "text": "Usage: /app ship [TASK_ID] --prompt TEXT [--output-dir PATH] [--live] [--live-plan]",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            try:
                payload = workbench.app_ship(
                    task_id=task_id,
                    prompt=prompt,
                    output_dir=(options.get("--output-dir") or [""])[-1],
                    use_live_planner="--live-plan" in options or "--use-live-planner" in options,
                    use_live_generator="--live" in options or "--use-live-generator" in options,
                )
            except Exception as exc:
                return {
                    "kind": "error",
                    "text": f"app ship failed: {exc}",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        if not task_id:
            return {
                "kind": "help",
                "text": f"Usage: /app {app_command} [TASK_ID] ...",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            if app_command == "plan":
                prompt = (options.get("--prompt") or [None])[-1]
                if not prompt:
                    return {
                        "kind": "help",
                        "text": "Usage: /app plan [TASK_ID] --prompt TEXT [--title TEXT] [--type TYPE] [--stack ITEM] [--feature ITEM] [--design-direction TEXT] [--criterion NAME[:THRESHOLD[:WEIGHT]]] [--live]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                payload = workbench.app_plan(
                    task_id=task_id,
                    prompt=prompt,
                    title=(options.get("--title") or [""])[-1],
                    app_type=(options.get("--type") or [""])[-1],
                    stack=options.get("--stack", []),
                    features=options.get("--feature", []),
                    design_direction=(options.get("--design-direction") or [""])[-1],
                    criteria=options.get("--criterion", []),
                    use_live_planner="--live" in options,
                )
            elif app_command == "sprint":
                sprint_id = (options.get("--sprint-id") or [None])[-1]
                goal = (options.get("--goal") or [None])[-1]
                if not sprint_id or not goal:
                    return {
                        "kind": "help",
                        "text": "Usage: /app sprint [TASK_ID] --sprint-id ID --goal TEXT [--scope ITEM] [--acceptance-check CMD] [--done-definition TEXT] [--proposed-by WHO] [--approved]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                payload = workbench.app_sprint(
                    task_id=task_id,
                    sprint_id=sprint_id,
                    goal=goal,
                    scope=options.get("--scope", []),
                    acceptance_checks=options.get("--acceptance-check", []),
                    done_definition=options.get("--done-definition", []),
                    proposed_by=(options.get("--proposed-by") or [""])[-1],
                    approved=(options.get("--approved") or ["false"])[-1].lower() == "true",
                )
            elif app_command == "negotiate":
                payload = workbench.app_negotiate(
                    task_id=task_id,
                    sprint_id=(options.get("--sprint-id") or [""])[-1],
                    objections=options.get("--objection", []),
                    use_live_planner="--live" in options,
                )
            elif app_command == "generate":
                payload = workbench.app_generate(
                    task_id=task_id,
                    sprint_id=(options.get("--sprint-id") or [""])[-1],
                    execution_summary=(options.get("--summary") or [""])[-1],
                    changed_target_hints=options.get("--target", []),
                    use_live_generator="--live" in options,
                )
            elif app_command == "export":
                payload = workbench.app_export(
                    task_id=task_id,
                    output_dir=(options.get("--output-dir") or [""])[-1],
                )
            elif app_command == "retry":
                payload = workbench.app_retry(
                    task_id=task_id,
                    sprint_id=(options.get("--sprint-id") or [""])[-1],
                    revision_notes=options.get("--revision-note", []),
                    use_live_planner="--live" in options,
                )
            elif app_command == "advance":
                payload = workbench.app_advance(
                    task_id=task_id,
                    sprint_id=(options.get("--sprint-id") or [""])[-1],
                )
            elif app_command == "replan":
                payload = workbench.app_replan(
                    task_id=task_id,
                    sprint_id=(options.get("--sprint-id") or [""])[-1],
                    note=(options.get("--note") or [""])[-1],
                    use_live_planner="--live" in options,
                )
            elif app_command == "escalate":
                payload = workbench.app_escalate(
                    task_id=task_id,
                    sprint_id=(options.get("--sprint-id") or [""])[-1],
                    note=(options.get("--note") or [""])[-1],
                )
            elif app_command == "qa":
                sprint_id = (options.get("--sprint-id") or [None])[-1]
                status = (options.get("--status") or ["auto"])[-1]
                if not sprint_id:
                    return {
                        "kind": "help",
                        "text": "Usage: /app qa [TASK_ID] --sprint-id ID [--status passed|failed|auto] [--summary TEXT] [--score NAME=VALUE] [--blocker NOTE] [--live]",
                        "payload": None,
                        "should_exit": False,
                        "should_refresh_status": False,
                    }
                payload = workbench.app_qa(
                    task_id=task_id,
                    sprint_id=sprint_id,
                    status=status or "auto",
                    summary=(options.get("--summary") or [""])[-1],
                    scores=options.get("--score", []),
                    blocker_notes=options.get("--blocker", []),
                    use_live_evaluator="--live" in options,
                )
            else:
                return {
                    "kind": "help",
                    "text": "Usage: /app show [TASK_ID] | /app plan [TASK_ID] --prompt TEXT [--title TEXT] [--type TYPE] [--stack ITEM] [--feature ITEM] [--design-direction TEXT] [--criterion NAME[:THRESHOLD[:WEIGHT]]] [--live] | /app sprint [TASK_ID] --sprint-id ID --goal TEXT [--scope ITEM] [--acceptance-check CMD] [--done-definition TEXT] [--proposed-by WHO] [--approved] | /app negotiate [TASK_ID] [--sprint-id ID] [--objection NOTE] [--live] | /app generate [TASK_ID] [--sprint-id ID] [--summary TEXT] [--target ITEM] [--live] | /app retry [TASK_ID] [--sprint-id ID] [--revision-note NOTE] [--live] | /app advance [TASK_ID] [--sprint-id ID] | /app replan [TASK_ID] [--sprint-id ID] [--note TEXT] | /app escalate [TASK_ID] [--sprint-id ID] [--note TEXT] | /app qa [TASK_ID] --sprint-id ID [--status passed|failed|auto] [--summary TEXT] [--score NAME=VALUE] [--blocker NOTE] [--live]",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"app {app_command} failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "ab-test":
        positional, options = _parse_shell_args(args)
        if not positional or positional[0] != "compare":
            return {
                "kind": "help",
                "text": "Usage: /ab-test compare [TASK_ID] --scenario-id ID [--baseline-ended-in ENDING] [--baseline-duration-seconds N] [--baseline-retry-count N] [--baseline-replan-depth N] [--baseline-convergence-signal TEXT] [--baseline-final-execution-gate GATE] [--baseline-gate-flow FLOW] [--baseline-note TEXT] [--baseline-advance-reached] [--baseline-escalated]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_id = current_task_id if len(positional) < 2 else positional[1]
        scenario_id = (options.get("--scenario-id") or [None])[-1]
        if not task_id or not scenario_id:
            return {
                "kind": "help",
                "text": "Usage: /ab-test compare [TASK_ID] --scenario-id ID [--baseline-ended-in ENDING] [--baseline-duration-seconds N] [--baseline-retry-count N] [--baseline-replan-depth N] [--baseline-convergence-signal TEXT] [--baseline-final-execution-gate GATE] [--baseline-gate-flow FLOW] [--baseline-note TEXT] [--baseline-advance-reached] [--baseline-escalated]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.ab_test_compare(
                task_id=task_id,
                scenario_id=scenario_id,
                baseline_ended_in=(options.get("--baseline-ended-in") or [""])[-1],
                baseline_duration_seconds=float((options.get("--baseline-duration-seconds") or ["0"])[-1] or 0.0),
                baseline_retry_count=int((options.get("--baseline-retry-count") or ["0"])[-1] or 0),
                baseline_replan_depth=int((options.get("--baseline-replan-depth") or ["0"])[-1] or 0),
                baseline_convergence_signal=(options.get("--baseline-convergence-signal") or [""])[-1],
                baseline_final_execution_gate=(options.get("--baseline-final-execution-gate") or [""])[-1],
                baseline_gate_flow=(options.get("--baseline-gate-flow") or [""])[-1],
                baseline_notes=options.get("--baseline-note", []),
                baseline_advance_reached=(options.get("--baseline-advance-reached") or ["false"])[-1].lower() == "true",
                baseline_escalated=(options.get("--baseline-escalated") or ["false"])[-1].lower() == "true",
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"ab-test compare failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "pick":
        positional, options = _parse_shell_args(args)
        if not positional:
            return {
                "kind": "help",
                "text": "Usage: /pick N",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            pick_index = int(positional[0])
        except ValueError:
            return {
                "kind": "help",
                "text": "Usage: /pick N",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        if pick_index < 1:
            return {
                "kind": "help",
                "text": "Usage: /pick N",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.recent_tasks(limit=max(pick_index, 8))
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"pick failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        tasks = payload.get("tasks") or []
        if pick_index > len(tasks):
            return {
                "kind": "error",
                "text": f"pick failed: index {pick_index} is out of range for {len(tasks)} recent tasks",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        selected = tasks[pick_index - 1]
        task_id = selected.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return {
                "kind": "error",
                "text": f"pick failed: task #{pick_index} did not include a usable task id",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "setting",
            "text": f"picked task {pick_index}: {task_id}",
            "payload": {"setting": "current_task", "value": task_id},
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "use":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /use TASK_ID",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "setting",
            "text": f"using task: {task_id}",
            "payload": {"setting": "current_task", "value": task_id},
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "clear":
        return {
            "kind": "setting",
            "text": "cleared current task context",
            "payload": {"setting": "current_task", "value": None},
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "raw":
        normalized = (args or "toggle").strip().lower()
        if normalized not in {"on", "off", "toggle", ""}:
            return {
                "kind": "help",
                "text": "Usage: /raw [on|off|toggle]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "setting",
            "text": normalized or "toggle",
            "payload": {"setting": "raw_mode", "value": normalized or "toggle"},
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "run":
        positional, options = _parse_shell_args(args)
        if len(positional) < 1 or ("--preflight-only" not in options and len(positional) < 2):
            return {
                "kind": "help",
                "text": "Usage: /run TASK_ID [\"task description\"] [--target-file PATH] [--validation-command CMD] [--preflight-only] [--one-line]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        if "--preflight-only" in options:
            payload = _live_execution_preflight_payload(workbench, operation="run", task_id=positional[0])
            if "--one-line" in options:
                payload["shell_view"] = "live_preflight_one_line"
                payload["summary_line"] = _live_preflight_summary_line(payload)
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        preflight_error = _live_execution_preflight_error(workbench, operation="run", task_id=positional[0])
        if preflight_error is not None:
            return preflight_error
        try:
            payload = _coerce_payload(
                workbench.run(
                    task_id=positional[0],
                    task=positional[1],
                    target_files=options.get("--target-file", []),
                    validation_commands=options.get("--validation-command", []),
                )
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": "",
                "payload": _structured_host_error("run", exc, workbench, task_id=positional[0]),
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "resume":
        positional, options = _parse_shell_args(args)
        if not positional and not current_task_id:
            return {
                "kind": "help",
                "text": "Usage: /resume [TASK_ID] [\"fallback task\"] [--target-file PATH] [--validation-command CMD] [--preflight-only] [--one-line]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_id = current_task_id if not positional else positional[0]
        if "--preflight-only" in options:
            payload = _live_execution_preflight_payload(workbench, operation="resume", task_id=task_id)
            if "--one-line" in options:
                payload["shell_view"] = "live_preflight_one_line"
                payload["summary_line"] = _live_preflight_summary_line(payload)
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        controller_preflight = _controller_preflight_payload(
            workbench,
            task_id=task_id,
            shell_command="resume",
            required_action="resume",
        )
        if controller_preflight is not None:
            return {
                "kind": "show",
                "text": "",
                "payload": controller_preflight,
                "should_exit": False,
                "should_refresh_status": False,
            }
        preflight_error = _live_execution_preflight_error(workbench, operation="resume", task_id=task_id)
        if preflight_error is not None:
            return preflight_error
        try:
            payload = _coerce_payload(
                workbench.resume(
                    task_id=task_id,
                    fallback_task=positional[1] if len(positional) > 1 else None,
                    target_files=options.get("--target-file", []),
                    validation_commands=options.get("--validation-command", []),
                )
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": "",
                "payload": _structured_host_error("resume", exc, workbench, task_id=task_id),
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "ingest":
        positional, options = _parse_shell_args(args)
        if len(positional) < 3:
            return {
                "kind": "help",
                "text": "Usage: /ingest TASK_ID \"task\" \"summary\" [--target-file PATH] [--changed-file PATH] [--validation-command CMD] [--validation-summary TEXT] [--validation-ok true|false]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        validation_ok = True
        if "--validation-ok" in options:
            raw = options["--validation-ok"][-1].strip().lower()
            validation_ok = raw not in {"false", "0", "no"}
        try:
            payload = _coerce_payload(
                workbench.ingest(
                    task_id=positional[0],
                    task=positional[1],
                    summary=positional[2],
                    target_files=options.get("--target-file", []),
                    changed_files=options.get("--changed-file", []),
                    validation_commands=options.get("--validation-command", []),
                    validation_summary=(options.get("--validation-summary") or [None])[-1],
                    validation_ok=validation_ok,
                )
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"ingest failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "ship":
        positional, options = _parse_shell_args(args)
        if len(positional) < 2:
            return {
                "kind": "help",
                "text": "Usage: /ship TASK_ID \"task\" [--target-file PATH] [--validation-command CMD] [--output-dir PATH] [--live] [--live-plan]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = _coerce_payload(
                workbench.ship(
                    task_id=positional[0],
                    task=positional[1],
                    target_files=options.get("--target-file", []),
                    validation_commands=options.get("--validation-command", []),
                    output_dir=(options.get("--output-dir") or [""])[-1],
                    use_live_planner="--live-plan" in options or "--use-live-planner" in options,
                    use_live_generator="--live" in options or "--use-live-generator" in options,
                )
            )
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"ship failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "status":
        try:
            payload = workbench.shell_status(task_id=_resolve_task_id(args, current_task_id))
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"status failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "status",
            "text": payload["text"],
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "show":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            try:
                payload = workbench.bootstrap_overview()
                payload["shell_view"] = "show"
            except Exception as exc:
                return {
                    "kind": "error",
                    "text": f"show failed: {exc}",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.inspect_session(task_id=task_id)
            payload["shell_view"] = "show"
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"show failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "work":
        positional, options = _parse_shell_args(args)
        task_id = current_task_id if not positional else positional[0]
        if not task_id:
            try:
                payload = workbench.bootstrap_overview()
                payload["shell_view"] = "work"
                payload["host_contract"] = _host_contract_payload(workbench).get("contract")
            except Exception as exc:
                return {
                    "kind": "error",
                    "text": f"work failed: {exc}",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        limit = 6
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        try:
            session_payload = workbench.inspect_session(task_id=task_id)
            compare_payload = workbench.compare_family(task_id=task_id, limit=limit)
            dashboard_payload = workbench.dashboard(limit=24, family_limit=12)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"work failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_family = compare_payload.get("task_family")
        family_row = None
        for row in dashboard_payload.get("family_rows", []):
            if row.get("task_family") == task_family:
                family_row = row
                break
        payload = {
            "shell_view": "work",
            "task_id": task_id,
            "session_path": session_payload.get("session_path"),
            "canonical_views": session_payload.get("canonical_views"),
            "evaluation": session_payload.get("evaluation"),
            "task_family": task_family,
            "anchor": compare_payload.get("anchor"),
            "peer_count": compare_payload.get("peer_count"),
            "peer_summary": compare_payload.get("peer_summary"),
            "peers": compare_payload.get("peers"),
            "family_row": family_row,
            "family_prior": compare_payload.get("family_prior"),
            "host_contract": _host_contract_payload(workbench).get("contract"),
        }
        controller_action_bar = _controller_action_bar_from_payload(session_payload, task_id=task_id)
        if controller_action_bar is not None:
            payload["controller_action_bar"] = controller_action_bar
        payload["reviewer"] = _reviewer_payload(payload.get("canonical_views") or {})
        payload["review_packs"] = _review_pack_payload(payload.get("canonical_views") or {})
        family_prior = payload.get("family_prior") or {}
        primary_validation = _primary_validation_path(payload.get("canonical_views") or {}, family_prior)
        instrumentation_status = str(
            ((payload.get("canonical_views") or {}).get("instrumentation") or {}).get("status") or "unknown"
        )
        payload["reuse_summary"] = _reuse_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_row=payload.get("family_row") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
        )
        payload["value_summary"] = _value_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
            instrumentation_status=instrumentation_status,
        )
        payload["workflow_path"] = _workflow_path("work")
        payload["recommended_command"] = _recommended_command(
            view="work",
            task_id=task_id,
            primary_validation=primary_validation,
        )
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "next":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /next [TASK_ID]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        controller_preflight = _controller_preflight_payload(
            workbench,
            task_id=task_id,
            shell_command="next",
            required_action="plan_start",
        )
        if controller_preflight is not None:
            return {
                "kind": "show",
                "text": "",
                "payload": controller_preflight,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.workflow_next(task_id=task_id)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"next failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": _attach_controller_action_bar(
                {
                    **payload,
                    "reviewer": _reviewer_payload((payload.get("canonical_views") or {})),
                    "review_packs": _review_pack_payload((payload.get("canonical_views") or {})),
                    "host_contract": _host_contract_payload(workbench).get("contract"),
                },
                task_id=task_id,
            ),
            "should_exit": False,
            "should_refresh_status": payload.get("workflow_next", {}).get("action") == "validate",
        }
    if command.name == "fix":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /fix [TASK_ID]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        controller_preflight = _controller_preflight_payload(
            workbench,
            task_id=task_id,
            shell_command="fix",
            required_action="plan_start",
        )
        if controller_preflight is not None:
            return {
                "kind": "show",
                "text": "",
                "payload": controller_preflight,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.workflow_fix(task_id=task_id)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"fix failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "show",
            "text": "",
            "payload": _attach_controller_action_bar(
                {
                    **payload,
                    "reviewer": _reviewer_payload((payload.get("canonical_views") or {})),
                    "review_packs": _review_pack_payload((payload.get("canonical_views") or {})),
                    "host_contract": _host_contract_payload(workbench).get("contract"),
                },
                task_id=task_id,
            ),
            "should_exit": False,
            "should_refresh_status": payload.get("workflow_next", {}).get("action") == "validate",
        }
    if command.name == "plan":
        positional, options = _parse_shell_args(args)
        task_id = current_task_id if not positional else positional[0]
        if not task_id:
            try:
                payload = workbench.bootstrap_overview()
                payload["shell_view"] = "plan"
                payload["host_contract"] = _host_contract_payload(workbench).get("contract")
            except Exception as exc:
                return {
                    "kind": "error",
                    "text": f"plan failed: {exc}",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        limit = 6
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        try:
            session_payload = workbench.inspect_session(task_id=task_id)
            evaluation_payload = workbench.evaluate_session(task_id=task_id)
            compare_payload = workbench.compare_family(task_id=task_id, limit=limit)
            dashboard_payload = workbench.dashboard(limit=24, family_limit=12)
            next_payload = workbench.workflow_next(task_id=task_id)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"plan failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_family = compare_payload.get("task_family")
        family_row = None
        for row in dashboard_payload.get("family_rows", []):
            if row.get("task_family") == task_family:
                family_row = row
                break
        payload = {
            "shell_view": "plan",
            "task_id": task_id,
            "session_path": session_payload.get("session_path"),
            "canonical_views": session_payload.get("canonical_views"),
            "evaluation": evaluation_payload.get("evaluation") or session_payload.get("evaluation"),
            "task_family": task_family,
            "anchor": compare_payload.get("anchor"),
            "peer_count": compare_payload.get("peer_count"),
            "peer_summary": compare_payload.get("peer_summary"),
            "peers": compare_payload.get("peers"),
            "family_row": family_row,
            "family_prior": compare_payload.get("family_prior"),
            "workflow_next": next_payload.get("workflow_next"),
            "next_validation": (next_payload.get("validation") or {}).get("command")
            or ((compare_payload.get("family_prior") or {}).get("dominant_validation_command") or None),
            "host_contract": _host_contract_payload(workbench).get("contract"),
        }
        controller_action_bar = _controller_action_bar_from_payload(session_payload, task_id=task_id)
        if controller_action_bar is not None:
            payload["controller_action_bar"] = controller_action_bar
        payload["reviewer"] = _reviewer_payload(payload.get("canonical_views") or {})
        payload["review_packs"] = _review_pack_payload(payload.get("canonical_views") or {})
        family_prior = payload.get("family_prior") or {}
        primary_validation = str(payload.get("next_validation") or _primary_validation_path(payload.get("canonical_views") or {}, family_prior) or "none")
        instrumentation_status = str(
            ((payload.get("canonical_views") or {}).get("instrumentation") or {}).get("status") or "unknown"
        )
        payload["reuse_summary"] = _reuse_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_row=payload.get("family_row") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
        )
        payload["value_summary"] = _value_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
            instrumentation_status=instrumentation_status,
        )
        payload["workflow_path"] = _workflow_path("plan")
        payload["recommended_command"] = _recommended_command(
            view="plan",
            task_id=task_id,
            primary_validation=primary_validation,
        )
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "review":
        positional, options = _parse_shell_args(args)
        task_id = current_task_id if not positional else positional[0]
        if not task_id:
            try:
                payload = workbench.bootstrap_overview()
                payload["shell_view"] = "review"
                payload["host_contract"] = _host_contract_payload(workbench).get("contract")
            except Exception as exc:
                return {
                    "kind": "error",
                    "text": f"review failed: {exc}",
                    "payload": None,
                    "should_exit": False,
                    "should_refresh_status": False,
                }
            return {
                "kind": "show",
                "text": "",
                "payload": payload,
                "should_exit": False,
                "should_refresh_status": False,
            }
        limit = 6
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        try:
            session_payload = workbench.inspect_session(task_id=task_id)
            evaluation_payload = workbench.evaluate_session(task_id=task_id)
            compare_payload = workbench.compare_family(task_id=task_id, limit=limit)
            dashboard_payload = workbench.dashboard(limit=24, family_limit=12)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"review failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_family = compare_payload.get("task_family")
        family_row = None
        for row in dashboard_payload.get("family_rows", []):
            if row.get("task_family") == task_family:
                family_row = row
                break
        payload = {
            "shell_view": "review",
            "task_id": task_id,
            "session_path": session_payload.get("session_path"),
            "canonical_views": session_payload.get("canonical_views"),
            "evaluation": evaluation_payload.get("evaluation") or session_payload.get("evaluation"),
            "task_family": task_family,
            "anchor": compare_payload.get("anchor"),
            "peer_count": compare_payload.get("peer_count"),
            "peer_summary": compare_payload.get("peer_summary"),
            "peers": compare_payload.get("peers"),
            "family_row": family_row,
            "family_prior": compare_payload.get("family_prior"),
            "host_contract": _host_contract_payload(workbench).get("contract"),
        }
        controller_action_bar = _controller_action_bar_from_payload(session_payload, task_id=task_id)
        if controller_action_bar is not None:
            payload["controller_action_bar"] = controller_action_bar
        payload["reviewer"] = _reviewer_payload(payload.get("canonical_views") or {})
        payload["review_packs"] = _review_pack_payload(payload.get("canonical_views") or {})
        family_prior = payload.get("family_prior") or {}
        primary_validation = _primary_validation_path(payload.get("canonical_views") or {}, family_prior)
        instrumentation_status = str(
            ((payload.get("canonical_views") or {}).get("instrumentation") or {}).get("status") or "unknown"
        )
        payload["reuse_summary"] = _reuse_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_row=payload.get("family_row") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
        )
        payload["value_summary"] = _value_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
            instrumentation_status=instrumentation_status,
        )
        payload["workflow_path"] = _workflow_path("review")
        payload["recommended_command"] = _recommended_command(
            view="review",
            task_id=task_id,
            primary_validation=primary_validation,
        )
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "family":
        positional, options = _parse_shell_args(args)
        task_id = current_task_id if not positional else positional[0]
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /family [TASK_ID] [--limit N]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        limit = 6
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        try:
            compare_payload = workbench.compare_family(task_id=task_id, limit=limit)
            dashboard_payload = workbench.dashboard(limit=24, family_limit=12)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"family failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_family = compare_payload.get("task_family")
        family_row = None
        for row in dashboard_payload.get("family_rows", []):
            if row.get("task_family") == task_family:
                family_row = row
                break
        payload = {
            "shell_view": "family",
            "task_id": compare_payload.get("task_id"),
            "task_family": task_family,
            "anchor": compare_payload.get("anchor"),
            "peer_count": compare_payload.get("peer_count"),
            "peer_summary": compare_payload.get("peer_summary"),
            "peers": compare_payload.get("peers"),
            "family_row": family_row,
            "family_prior": compare_payload.get("family_prior"),
            "background": compare_payload.get("background"),
            "prior_seed_summary": compare_payload.get("prior_seed_summary"),
        }
        family_prior = payload.get("family_prior") or {}
        primary_validation = str(family_prior.get("dominant_validation_command") or "none")
        payload["reuse_summary"] = _reuse_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_row=payload.get("family_row") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
        )
        payload["value_summary"] = _value_summary(
            peer_summary=payload.get("peer_summary") or {},
            family_prior=family_prior,
            primary_validation=primary_validation,
            instrumentation_status="strong_match" if (payload.get("peer_summary") or {}).get("strong_match_count") else "unknown",
        )
        return {
            "kind": "show",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "validate":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /validate [TASK_ID]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.validate_session(task_id=task_id)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"validate failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": True,
        }
    if command.name == "session":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /session [TASK_ID]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.inspect_session(task_id=task_id)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"session failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "evaluate":
        task_id = _resolve_task_id(args, current_task_id)
        if not task_id:
            return {
                "kind": "help",
                "text": "Usage: /evaluate [TASK_ID]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        try:
            payload = workbench.evaluate_session(task_id=task_id)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"evaluate failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "compare-family":
        positional, options = _parse_shell_args(args)
        if not positional and not current_task_id:
            return {
                "kind": "help",
                "text": "Usage: /compare-family [TASK_ID] [--limit N]",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        task_id = current_task_id if not positional else positional[0]
        limit = 6
        if "--limit" in options:
            limit = int(options["--limit"][-1])
        try:
            payload = workbench.compare_family(task_id=task_id, limit=limit)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"compare-family failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }
    if command.name == "dashboard":
        argv = shlex.split(args)
        limit = 24
        family_limit = 8
        if "--limit" in argv:
            idx = argv.index("--limit")
            if idx + 1 < len(argv):
                limit = int(argv[idx + 1])
        if "--family-limit" in argv:
            idx = argv.index("--family-limit")
            if idx + 1 < len(argv):
                family_limit = int(argv[idx + 1])
        try:
            payload = workbench.dashboard(limit=limit, family_limit=family_limit)
        except Exception as exc:
            return {
                "kind": "error",
                "text": f"dashboard failed: {exc}",
                "payload": None,
                "should_exit": False,
                "should_refresh_status": False,
            }
        return {
            "kind": "result",
            "text": "",
            "payload": payload,
            "should_exit": False,
            "should_refresh_status": False,
        }

    return {
        "kind": "help",
        "text": "Use /run, /resume, /ingest, or /help.",
        "payload": None,
        "should_exit": False,
        "should_refresh_status": False,
    }
