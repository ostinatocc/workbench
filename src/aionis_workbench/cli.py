from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .provider_profiles import SAFE_CREDENTIALS_HINT

_COMMAND_TIERS: dict[str, tuple[str, ...]] = {
    "stable": ("init", "doctor", "ready", "status", "run", "resume", "session"),
    "beta": ("setup", "shell", "live-profile", "compare-family", "recent-tasks", "dashboard", "consolidate"),
    "internal": ("start", "stop", "ship", "ingest", "evaluate", "hosts", "dream", "ab-test", "app", "doc", "backfill"),
}


def _add_doc_recording_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-source", required=False, help=argparse.SUPPRESS)
    parser.add_argument("--event-origin", required=False, help=argparse.SUPPRESS)
    parser.add_argument("--recorded-at", required=False, help=argparse.SUPPRESS)


def _doc_recording_kwargs(args: argparse.Namespace) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    for key in ("event_source", "event_origin", "recorded_at"):
        value = getattr(args, key, None)
        if isinstance(value, str) and value.strip():
            kwargs[key] = value.strip()
    return kwargs


def create_workbench(repo_root: str | None):
    from .runtime import AionisWorkbench

    return AionisWorkbench(repo_root=repo_root, load_env=_cli_load_env_files())


def _cli_load_env_files() -> bool:
    value = os.environ.get("AIONIS_LOAD_ENV_FILES")
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _command_tier(command_name: str) -> str:
    normalized = str(command_name).strip()
    for tier, commands in _COMMAND_TIERS.items():
        if normalized in commands:
            return tier
    return "internal"


def _tiered_help(command_name: str, text: str) -> str:
    return f"[{_command_tier(command_name)}] {text}"


def _root_help_epilog() -> str:
    stable = ", ".join(_COMMAND_TIERS["stable"])
    beta = ", ".join(_COMMAND_TIERS["beta"])
    internal = ", ".join(_COMMAND_TIERS["internal"])
    return (
        "Recommended stable path:\n"
        "  aionis ready --repo-root /path/to/repo\n"
        "  aionis run --repo-root /path/to/repo --task-id task-1 --task \"...\"\n"
        "  aionis resume --repo-root /path/to/repo --task-id task-1\n\n"
        f"Stable commands: {stable}\n"
        f"Beta commands: {beta}\n"
        f"Internal commands: {internal}\n\n"
        "Use beta and internal commands for advanced evaluation, maintenance, and experimental workflows."
    )


def create_runtime_manager():
    from .runtime_manager import RuntimeManager

    return RuntimeManager()


def _payload_exit_code(command: str, payload: object) -> int:
    if command == "doc" and isinstance(payload, dict):
        status = str(payload.get("status") or "").strip().lower()
        return 1 if status in {"failed", "error"} else 0
    if command in {"run", "resume"} and isinstance(payload, dict):
        shell_view = str(payload.get("shell_view") or "")
        if shell_view == "host_error":
            return 1
        if shell_view in {"live_preflight", "live_preflight_one_line"}:
            return 0 if bool(payload.get("ready")) else 1
        session = payload.get("session") or {}
        session = session if isinstance(session, dict) else {}
        status = str(session.get("status") or "").strip()
        if status in {"needs_attention", "paused", "ingested_needs_attention"}:
            return 1
    if command == "ready" and isinstance(payload, dict):
        return 0 if bool(payload.get("live_ready")) else 1
    if command not in {"doctor", "setup"} or not isinstance(payload, dict):
        return 0
    shell_view = str(payload.get("shell_view") or "")
    if shell_view not in {"doctor_check", "setup_check"}:
        return 0
    if not payload.get("found"):
        return 2
    item = payload.get("item") or {}
    status = str(item.get("status") or "").strip()
    return 0 if status in {"done", "available"} else 1


def _payload_one_line(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    text = str(payload.get("summary_line") or "").strip()
    return text or None


def _live_preflight_summary_line(payload: dict[str, object]) -> str:
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


def _inspect_only_recommendation() -> str:
    return "continue in inspect-only mode via shell -> /work, /review, /validate, or /ingest"


def _host_contract_payload(workbench) -> dict:
    factory = getattr(workbench, "host_contract", None)
    if not callable(factory):
        return {}
    try:
        payload = factory()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _doctor_payload(workbench) -> dict:
    factory = getattr(workbench, "doctor", None)
    if not callable(factory):
        return {}
    try:
        payload = factory()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _setup_payload(workbench) -> dict:
    factory = getattr(workbench, "setup", None)
    if not callable(factory):
        return {}
    try:
        payload = factory()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _checklist_command_hint(doctor_payload: dict[str, object], name: str) -> str:
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
    doctor_payload: dict[str, object] | None = None,
) -> tuple[str, str]:
    doctor_payload = doctor_payload if isinstance(doctor_payload, dict) else {}
    capability_state = str(doctor_payload.get("capability_state") or "")
    credentials_hint = _checklist_command_hint(doctor_payload, "credentials_configured") or SAFE_CREDENTIALS_HINT
    runtime_hint = _checklist_command_hint(doctor_payload, "runtime_available") or "curl -fsS ${AIONIS_BASE_URL:-http://127.0.0.1:3101}/health"
    if ready:
        return "ready", "aionis run --repo-root /path/to/repo --task-id task-1 --task \"...\""
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
    return "unknown", "aionis doctor --repo-root /path/to/repo"


def _cli_host_error_payload(operation: str, exc: Exception, workbench, *, task_id: str | None = None) -> dict:
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
    recommendations: list[str] = [_inspect_only_recommendation()]
    if execution_reason == "model_credentials_missing":
        recommendations.append("configure model credentials to enable live execution")
    if runtime_reason == "runtime_health_unreachable":
        recommendations.append("start or configure Aionis Runtime via AIONIS_BASE_URL")
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


def _cli_live_preflight_payload(operation: str, workbench, *, task_id: str | None = None) -> dict:
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
        recommendations.append(f"start live execution with `aionis {operation} ...`")
    elif not ready:
        inspect_only = _inspect_only_recommendation()
        if inspect_only not in recommendations:
            recommendations.insert(0, inspect_only)
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


def _repo_root_hint(workbench, explicit_repo_root: str | None, setup_payload: dict[str, object], doctor_payload: dict[str, object]) -> str:
    for candidate in (
        explicit_repo_root,
        str(setup_payload.get("repo_root") or "").strip(),
        str(doctor_payload.get("repo_root") or "").strip(),
        str(getattr(workbench, "repo_root", "") or "").strip(),
    ):
        if candidate:
            return candidate
    return "/absolute/path/to/repo"


def _pending_command_steps(setup_payload: dict[str, object], doctor_payload: dict[str, object]) -> list[str]:
    steps: list[str] = []
    pending_items = setup_payload.get("pending_items") or []
    if not isinstance(pending_items, list):
        pending_items = []
    for item in pending_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("command_hint") or item.get("next_step") or "").strip()
        if text and text not in steps:
            steps.append(text)
    if steps:
        return steps[:3]
    checklist = doctor_payload.get("setup_checklist") or []
    if not isinstance(checklist, list):
        checklist = []
    for item in checklist:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip() != "pending":
            continue
        text = str(item.get("command_hint") or item.get("next_step") or "").strip()
        if text and text not in steps:
            steps.append(text)
    return steps[:3]


def _cli_ready_payload(workbench, *, repo_root: str | None = None) -> dict:
    doctor_payload = _doctor_payload(workbench)
    setup_payload = _setup_payload(workbench)
    contract_payload = _host_contract_payload(workbench)
    contract = contract_payload.get("contract") if isinstance(contract_payload, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    resolved_repo_root = _repo_root_hint(workbench, repo_root, setup_payload, doctor_payload)
    next_steps = _pending_command_steps(setup_payload, doctor_payload)
    launch_command = f"aionis --repo-root {resolved_repo_root}"
    return {
        "shell_view": "ready",
        "repo_root": resolved_repo_root,
        "mode": str(doctor_payload.get("mode") or setup_payload.get("mode") or "inspect-only"),
        "live_ready": bool(doctor_payload.get("live_ready")),
        "live_ready_summary": str(
            doctor_payload.get("live_ready_summary")
            or setup_payload.get("live_ready_summary")
            or doctor_payload.get("mode")
            or "inspect-only"
        ),
        "capability_state": str(doctor_payload.get("capability_state") or setup_payload.get("capability_state") or ""),
        "capability_summary": str(
            doctor_payload.get("capability_summary") or setup_payload.get("capability_summary") or ""
        ),
        "pending_count": int(setup_payload.get("pending_count") or doctor_payload.get("pending_checklist_count") or 0),
        "pending_items": setup_payload.get("pending_items") or [],
        "checks": doctor_payload.get("checks") or [],
        "recovery_summary": str(
            doctor_payload.get("recovery_summary") or setup_payload.get("recovery_summary") or ""
        ),
        "host_contract": contract,
        "next_steps": next_steps,
        "launch_command": launch_command,
    }


def _print_payload(payload: object) -> None:
    def _json_default(value: Any) -> Any:
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        data = getattr(value, "__dict__", None)
        if isinstance(data, dict):
            return data
        raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

    one_line = _payload_one_line(payload)
    if one_line is not None:
        print(one_line)
        return
    if isinstance(payload, dict):
        shell_view = str(payload.get("shell_view") or "")
        if shell_view in {
            "ready",
            "doctor",
            "doctor_summary",
            "doctor_check",
            "setup",
            "setup_summary",
            "setup_check",
            "host_error",
            "live_preflight",
            "live_profile",
            "dream",
            "ship",
            "ab_test_compare",
            "app_show",
            "app_ship",
            "app_plan",
            "app_sprint",
            "app_negotiate",
            "app_qa",
            "app_retry",
            "app_generate",
            "app_export",
            "app_advance",
            "app_replan",
            "app_escalate",
        }:
            from .shell import _render_result_payload

            lines = _render_result_payload(payload)
            if lines and lines[-1].lstrip().startswith("{"):
                lines = lines[:-1]
            print("\n".join(lines))
            return
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


def _launcher_summary_line(payload: dict[str, object]) -> str:
    mode = str(payload.get("mode") or "unknown")
    health_status = str(payload.get("health_status") or "unknown")
    health_reason = str(payload.get("health_reason") or "none")
    base_url = str(payload.get("base_url") or "unknown")
    pid = payload.get("pid")
    pid_text = "none" if pid in {None, ""} else str(pid)
    action = str(payload.get("action") or "").strip()
    parts = [
        f"launcher-status: mode={mode}",
        f"health={health_status}",
        f"reason={health_reason}",
        f"base_url={base_url}",
        f"pid={pid_text}",
    ]
    if action:
        parts.append(f"action={action}")
    return " ".join(parts)


def _should_attempt_runtime_boot(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    mode = str(payload.get("mode") or "").strip()
    health_status = str(payload.get("health_status") or "").strip()
    if mode == "running" and health_status == "available":
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Aionis Workbench as a multi-agent product shell on top of Aionis Core.",
        epilog=_root_help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo-root", required=False)
    parser.add_argument("--task-id", required=False)
    subparsers = parser.add_subparsers(dest="command", required=False, metavar="COMMAND")

    def add_command_parser(name: str, help_text: str) -> argparse.ArgumentParser:
        tier = _command_tier(name)
        return subparsers.add_parser(
            name,
            help=_tiered_help(name, help_text),
            description=f"[{tier}] {help_text}",
        )

    start_parser = add_command_parser("start", "Start the local Aionis runtime managed by the launcher.")
    start_parser.add_argument("--repo-root", required=False)

    stop_parser = add_command_parser("stop", "Stop the local Aionis runtime managed by the launcher.")
    stop_parser.add_argument("--repo-root", required=False)

    status_parser = add_command_parser("status", "Show the local launcher and runtime status.")
    status_parser.add_argument("--repo-root", required=False)

    shell_parser = add_command_parser("shell", "Open the thin interactive Aionis shell.")
    shell_parser.add_argument("--repo-root", required=False)
    shell_parser.add_argument("--task-id", required=False)

    init_parser = add_command_parser("init", "Initialize cold-start bootstrap state for a repo.")
    init_parser.add_argument("--repo-root", required=False)

    setup_parser = add_command_parser("setup", "Show the current onboarding setup steps for a repo.")
    setup_parser.add_argument("--repo-root", required=False)
    setup_parser.add_argument("--pending-only", action=argparse.BooleanOptionalAction, default=False)
    setup_parser.add_argument("--summary", action=argparse.BooleanOptionalAction, default=False)
    setup_parser.add_argument("--check", required=False)
    setup_parser.add_argument("--one-line", action=argparse.BooleanOptionalAction, default=False)

    doctor_parser = add_command_parser("doctor", "Check whether the current repo is ready for live or inspect-only Aionis usage.")
    doctor_parser.add_argument("--repo-root", required=False)
    doctor_parser.add_argument("--summary", action=argparse.BooleanOptionalAction, default=False)
    doctor_parser.add_argument("--check", required=False)
    doctor_parser.add_argument("--one-line", action=argparse.BooleanOptionalAction, default=False)

    ready_parser = add_command_parser("ready", "Show the shortest combined init/setup/doctor readiness path for a repo.")
    ready_parser.add_argument("--repo-root", required=False)

    live_profile_parser = add_command_parser("live-profile", "Show the active live provider profile and the latest recorded live timing snapshot.")
    live_profile_parser.add_argument("--repo-root", required=False)

    run_parser = add_command_parser("run", "Start a new workbench session.")
    run_parser.add_argument("--repo-root", required=False)
    run_parser.add_argument("--task-id", required=True)
    run_parser.add_argument("--task", required=False)
    run_parser.add_argument("--target-file", action="append", default=[])
    run_parser.add_argument("--validation-command", action="append", default=[])
    run_parser.add_argument("--preflight-only", action=argparse.BooleanOptionalAction, default=False)
    run_parser.add_argument("--one-line", action=argparse.BooleanOptionalAction, default=False)

    ship_parser = add_command_parser("ship", "Route one task through the best current Workbench product entry.")
    ship_parser.add_argument("--repo-root", required=False)
    ship_parser.add_argument("--task-id", required=True)
    ship_parser.add_argument("--task", required=True)
    ship_parser.add_argument("--target-file", action="append", default=[])
    ship_parser.add_argument("--validation-command", action="append", default=[])
    ship_parser.add_argument("--output-dir", required=False, default="")
    ship_parser.add_argument("--use-live-planner", action=argparse.BooleanOptionalAction, default=False)
    ship_parser.add_argument("--use-live-generator", action=argparse.BooleanOptionalAction, default=False)

    resume_parser = add_command_parser("resume", "Resume an existing workbench session.")
    resume_parser.add_argument("--repo-root", required=False)
    resume_parser.add_argument("--task-id", required=True)
    resume_parser.add_argument("--task", required=False)
    resume_parser.add_argument("--target-file", action="append", default=[])
    resume_parser.add_argument("--validation-command", action="append", default=[])
    resume_parser.add_argument("--preflight-only", action=argparse.BooleanOptionalAction, default=False)
    resume_parser.add_argument("--one-line", action=argparse.BooleanOptionalAction, default=False)

    ingest_parser = add_command_parser("ingest", "Record externally completed validated work into project-scoped continuity.")
    ingest_parser.add_argument("--repo-root", required=False)
    ingest_parser.add_argument("--task-id", required=True)
    ingest_parser.add_argument("--task", required=True)
    ingest_parser.add_argument("--summary", required=True)
    ingest_parser.add_argument("--target-file", action="append", default=[])
    ingest_parser.add_argument("--changed-file", action="append", default=[])
    ingest_parser.add_argument("--validation-command", action="append", default=[])
    ingest_parser.add_argument("--validation-summary", required=False)
    ingest_parser.add_argument("--validation-ok", action=argparse.BooleanOptionalAction, default=True)

    session_parser = add_command_parser("session", "Inspect a persisted workbench session.")
    session_parser.add_argument("--repo-root", required=False)
    session_parser.add_argument("--task-id", required=True)

    evaluate_parser = add_command_parser("evaluate", "Evaluate whether a persisted session is using the canonical workbench surfaces cleanly.")
    evaluate_parser.add_argument("--repo-root", required=False)
    evaluate_parser.add_argument("--task-id", required=True)

    compare_family_parser = add_command_parser("compare-family", "Compare the current session against recent sessions from the same task family.")
    compare_family_parser.add_argument("--repo-root", required=False)
    compare_family_parser.add_argument("--task-id", required=True)
    compare_family_parser.add_argument("--limit", type=int, default=6)

    recent_tasks_parser = add_command_parser("recent-tasks", "List recent Workbench tasks for operator selection surfaces.")
    recent_tasks_parser.add_argument("--repo-root", required=False)
    recent_tasks_parser.add_argument("--limit", type=int, default=8)

    dashboard_parser = add_command_parser("dashboard", "Show a project-level live instrumentation dashboard grouped by task family.")
    dashboard_parser.add_argument("--repo-root", required=False)
    dashboard_parser.add_argument("--limit", type=int, default=24)
    dashboard_parser.add_argument("--family-limit", type=int, default=8)

    hosts_parser = add_command_parser("hosts", "Show the unified Aionis CLI, Workbench engine, and execution host contract.")
    hosts_parser.add_argument("--repo-root", required=False)

    consolidate_parser = add_command_parser("consolidate", "Run a conservative project-scoped consolidation pass over recent learning signals.")
    consolidate_parser.add_argument("--repo-root", required=False)
    consolidate_parser.add_argument("--limit", type=int, default=48)
    consolidate_parser.add_argument("--family-limit", type=int, default=8)

    dream_parser = add_command_parser("dream", "Inspect AutoDream promotions and candidates after running the latest dream maintenance cycle.")
    dream_parser.add_argument("--repo-root", required=False)
    dream_parser.add_argument("--limit", type=int, default=48)
    dream_parser.add_argument("--family-limit", type=int, default=8)
    dream_parser.add_argument("--status", required=False)

    ab_test_parser = add_command_parser("ab-test", "Compare a thin baseline loop against the current Aionis task state.")
    ab_test_parser.add_argument("--repo-root", required=False)
    ab_test_subparsers = ab_test_parser.add_subparsers(dest="ab_test_command", required=True)
    ab_test_compare_parser = ab_test_subparsers.add_parser("compare", help="Compare one baseline scenario result against the current Aionis task state.")
    ab_test_compare_parser.add_argument("--task-id", required=True)
    ab_test_compare_parser.add_argument("--scenario-id", required=True)
    ab_test_compare_parser.add_argument("--baseline-ended-in", required=False, default="")
    ab_test_compare_parser.add_argument("--baseline-duration-seconds", type=float, required=False, default=0.0)
    ab_test_compare_parser.add_argument("--baseline-retry-count", type=int, required=False, default=0)
    ab_test_compare_parser.add_argument("--baseline-replan-depth", type=int, required=False, default=0)
    ab_test_compare_parser.add_argument("--baseline-convergence-signal", required=False, default="")
    ab_test_compare_parser.add_argument("--baseline-final-execution-gate", required=False, default="")
    ab_test_compare_parser.add_argument("--baseline-gate-flow", required=False, default="")
    ab_test_compare_parser.add_argument("--baseline-note", action="append", default=[])
    ab_test_compare_parser.add_argument("--baseline-advance-reached", action=argparse.BooleanOptionalAction, default=False)
    ab_test_compare_parser.add_argument("--baseline-escalated", action=argparse.BooleanOptionalAction, default=False)

    app_parser = add_command_parser("app", "Inspect the persisted app harness state for a task.")
    app_parser.add_argument("--repo-root", required=False)
    app_subparsers = app_parser.add_subparsers(dest="app_command", required=True)
    app_show_parser = app_subparsers.add_parser("show", help="Show the current app harness state for a task.")
    app_show_parser.add_argument("--task-id", required=True)
    app_ship_parser = app_subparsers.add_parser("ship", help="Run the top-level Workbench app flow for one task.")
    app_ship_parser.add_argument("--task-id", required=True)
    app_ship_parser.add_argument("--prompt", required=True)
    app_ship_parser.add_argument("--output-dir", required=False, default="")
    app_ship_parser.add_argument("--use-live-planner", action=argparse.BooleanOptionalAction, default=False)
    app_ship_parser.add_argument("--use-live-generator", action=argparse.BooleanOptionalAction, default=False)
    app_plan_parser = app_subparsers.add_parser("plan", help="Record or update the product spec and evaluator criteria for a task.")
    app_plan_parser.add_argument("--task-id", required=True)
    app_plan_parser.add_argument("--prompt", required=True)
    app_plan_parser.add_argument("--title", required=False, default="")
    app_plan_parser.add_argument("--type", required=False, default="")
    app_plan_parser.add_argument("--stack", action="append", default=[])
    app_plan_parser.add_argument("--feature", action="append", default=[])
    app_plan_parser.add_argument("--design-direction", required=False, default="")
    app_plan_parser.add_argument("--criterion", action="append", default=[])
    app_plan_parser.add_argument("--use-live-planner", action=argparse.BooleanOptionalAction, default=False)
    app_sprint_parser = app_subparsers.add_parser("sprint", help="Record or update the active sprint contract for a task.")
    app_sprint_parser.add_argument("--task-id", required=True)
    app_sprint_parser.add_argument("--sprint-id", required=True)
    app_sprint_parser.add_argument("--goal", required=True)
    app_sprint_parser.add_argument("--scope", action="append", default=[])
    app_sprint_parser.add_argument("--acceptance-check", action="append", default=[])
    app_sprint_parser.add_argument("--done-definition", action="append", default=[])
    app_sprint_parser.add_argument("--proposed-by", required=False, default="")
    app_sprint_parser.add_argument("--approved", action=argparse.BooleanOptionalAction, default=True)
    app_negotiate_parser = app_subparsers.add_parser("negotiate", help="Record the latest planner/evaluator negotiation state for a sprint.")
    app_negotiate_parser.add_argument("--task-id", required=True)
    app_negotiate_parser.add_argument("--sprint-id", required=False, default="")
    app_negotiate_parser.add_argument("--objection", action="append", default=[])
    app_negotiate_parser.add_argument("--use-live-planner", action=argparse.BooleanOptionalAction, default=False)
    app_generate_parser = app_subparsers.add_parser("generate", help="Record one bounded generator execution attempt for the current sprint or revision.")
    app_generate_parser.add_argument("--task-id", required=True)
    app_generate_parser.add_argument("--sprint-id", required=False, default="")
    app_generate_parser.add_argument("--summary", required=False, default="")
    app_generate_parser.add_argument("--target", action="append", default=[])
    app_generate_parser.add_argument("--use-live-generator", action=argparse.BooleanOptionalAction, default=False)
    app_export_parser = app_subparsers.add_parser("export", help="Export the latest generated app artifact to a visible directory.")
    app_export_parser.add_argument("--task-id", required=True)
    app_export_parser.add_argument("--output-dir", required=False, default="")
    app_retry_parser = app_subparsers.add_parser("retry", help="Record one bounded revision attempt after planner/evaluator negotiation.")
    app_retry_parser.add_argument("--task-id", required=True)
    app_retry_parser.add_argument("--sprint-id", required=False, default="")
    app_retry_parser.add_argument("--revision-note", action="append", default=[])
    app_retry_parser.add_argument("--use-live-planner", action=argparse.BooleanOptionalAction, default=False)
    app_advance_parser = app_subparsers.add_parser("advance", help="Advance to the next planned sprint when policy marks it ready.")
    app_advance_parser.add_argument("--task-id", required=True)
    app_advance_parser.add_argument("--sprint-id", required=False, default="")
    app_replan_parser = app_subparsers.add_parser("replan", help="Return an escalated or exhausted sprint to a new replanned sprint proposal.")
    app_replan_parser.add_argument("--task-id", required=True)
    app_replan_parser.add_argument("--sprint-id", required=False, default="")
    app_replan_parser.add_argument("--note", required=False, default="")
    app_replan_parser.add_argument("--use-live-planner", action=argparse.BooleanOptionalAction, default=False)
    app_escalate_parser = app_subparsers.add_parser("escalate", help="Explicitly escalate the current sprint after retries are exhausted.")
    app_escalate_parser.add_argument("--task-id", required=True)
    app_escalate_parser.add_argument("--sprint-id", required=False, default="")
    app_escalate_parser.add_argument("--note", required=False, default="")
    app_qa_parser = app_subparsers.add_parser("qa", help="Record or derive the latest sprint evaluation for a task.")
    app_qa_parser.add_argument("--task-id", required=True)
    app_qa_parser.add_argument("--sprint-id", required=True)
    app_qa_parser.add_argument("--status", required=False, default="auto")
    app_qa_parser.add_argument("--summary", required=False, default="")
    app_qa_parser.add_argument("--score", action="append", default=[])
    app_qa_parser.add_argument("--blocker", action="append", default=[])
    app_qa_parser.add_argument("--use-live-evaluator", action=argparse.BooleanOptionalAction, default=False)

    doc_parser = add_command_parser("doc", "Run Aionisdoc compile/run/publish/recover/resume surfaces through Workbench.")
    doc_parser.add_argument("--repo-root", required=False)
    doc_subparsers = doc_parser.add_subparsers(dest="doc_command", required=True)

    doc_compile_parser = doc_subparsers.add_parser("compile", help="Compile an .aionis.md workflow.")
    doc_compile_parser.add_argument("--input", required=True)
    doc_compile_parser.add_argument("--task-id", required=False)
    doc_compile_parser.add_argument("--emit", required=False, default="all")
    doc_compile_parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=False)
    _add_doc_recording_args(doc_compile_parser)

    doc_run_parser = doc_subparsers.add_parser("run", help="Run an .aionis.md workflow with a module registry.")
    doc_run_parser.add_argument("--input", required=True)
    doc_run_parser.add_argument("--registry", required=True)
    doc_run_parser.add_argument("--task-id", required=False)
    doc_run_parser.add_argument("--input-kind", required=False, default="source")
    _add_doc_recording_args(doc_run_parser)

    doc_publish_parser = doc_subparsers.add_parser("publish", help="Publish an Aionisdoc workflow handoff to runtime.")
    doc_publish_parser.add_argument("--input", required=True)
    doc_publish_parser.add_argument("--task-id", required=False)
    doc_publish_parser.add_argument("--input-kind", required=False, default="source")
    _add_doc_recording_args(doc_publish_parser)

    doc_recover_parser = doc_subparsers.add_parser("recover", help="Recover continuity from an Aionisdoc publish or source input.")
    doc_recover_parser.add_argument("--input", required=True)
    doc_recover_parser.add_argument("--task-id", required=False)
    doc_recover_parser.add_argument("--input-kind", required=False, default="source")
    _add_doc_recording_args(doc_recover_parser)

    doc_resume_parser = doc_subparsers.add_parser("resume", help="Resume runtime selection from an Aionisdoc recover result or source input.")
    doc_resume_parser.add_argument("--input", required=True)
    doc_resume_parser.add_argument("--task-id", required=False)
    doc_resume_parser.add_argument("--input-kind", required=False, default="recover-result")
    doc_resume_parser.add_argument("--query-text", required=False)
    doc_resume_parser.add_argument("--candidate", action="append", default=[])
    _add_doc_recording_args(doc_resume_parser)

    doc_event_parser = doc_subparsers.add_parser("event", help="Record an editor-originated Aionisdoc event into Workbench continuity.")
    doc_event_parser.add_argument("--task-id", required=True)
    doc_event_parser.add_argument("--event", required=True)

    backfill_parser = add_command_parser("backfill", "Upgrade an existing session to the latest collaboration-memory schema.")
    backfill_parser.add_argument("--repo-root", required=False)
    backfill_parser.add_argument("--task-id", required=True)
    backfill_parser.add_argument("--rerun-recovery", action="store_true", default=False)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "shell"
    runtime_manager = create_runtime_manager()

    if command == "status":
        payload = runtime_manager.status()
        payload["shell_view"] = "launcher_status"
        payload["summary_line"] = _launcher_summary_line(payload)
    elif command == "start":
        payload = runtime_manager.start()
        payload["shell_view"] = "launcher_status"
        payload["summary_line"] = _launcher_summary_line(payload)
    elif command == "stop":
        payload = runtime_manager.stop()
        payload["shell_view"] = "launcher_status"
        payload["summary_line"] = _launcher_summary_line(payload)
    else:
        workbench = create_workbench(getattr(args, "repo_root", None))

    if command in {"status", "start", "stop"}:
        pass
    elif command == "shell":
        from .shell import run_shell

        runtime_status = runtime_manager.status()
        if _should_attempt_runtime_boot(runtime_status):
            runtime_manager.start()
        run_shell(workbench, initial_task_id=getattr(args, "task_id", None))
        return 0
    elif command == "init":
        payload = workbench.initialize_project()
    elif command == "setup":
        payload = workbench.setup(
            pending_only=args.pending_only,
            summary=args.summary,
            check=args.check,
            one_line=args.one_line,
        )
    elif command == "doctor":
        payload = workbench.doctor(summary=args.summary, check=args.check, one_line=args.one_line)
    elif command == "ready":
        payload = _cli_ready_payload(workbench, repo_root=getattr(args, "repo_root", None))
    elif command == "live-profile":
        payload = workbench.live_profile()
    elif command == "run":
        if not args.preflight_only and not args.task:
            parser.error("run requires --task unless --preflight-only is set")
        if args.preflight_only:
            payload = _cli_live_preflight_payload("run", workbench, task_id=args.task_id)
            if args.one_line:
                payload["shell_view"] = "live_preflight_one_line"
                payload["summary_line"] = _live_preflight_summary_line(payload)
        else:
            try:
                result = workbench.run(
                    task_id=args.task_id,
                    task=args.task,
                    target_files=args.target_file,
                    validation_commands=args.validation_command,
                )
                payload = {
                    "task_id": result.task_id,
                    "runner": result.runner,
                    "content": result.content,
                    "session_path": result.session_path,
                    "session": result.session,
                    "canonical_surface": result.canonical_surface,
                    "canonical_views": result.canonical_views,
                    "controller_action_bar": result.controller_action_bar,
                    "aionis": result.aionis,
                    "trace_summary": result.trace_summary,
                }
            except Exception as exc:
                payload = _cli_host_error_payload("run", exc, workbench, task_id=args.task_id)
    elif command == "ship":
        if args.use_live_generator:
            print(
                f"ship running: task_id={args.task_id} mode=live",
                file=sys.stderr,
                flush=True,
            )
        try:
            payload = workbench.ship(
                task_id=args.task_id,
                task=args.task,
                target_files=args.target_file,
                validation_commands=args.validation_command,
                output_dir=args.output_dir,
                use_live_planner=args.use_live_planner,
                use_live_generator=args.use_live_generator,
            )
        except Exception as exc:
            payload = _cli_host_error_payload("ship", exc, workbench, task_id=args.task_id)
    elif command == "resume":
        if args.preflight_only:
            payload = _cli_live_preflight_payload("resume", workbench, task_id=args.task_id)
            if args.one_line:
                payload["shell_view"] = "live_preflight_one_line"
                payload["summary_line"] = _live_preflight_summary_line(payload)
        else:
            try:
                result = workbench.resume(
                    task_id=args.task_id,
                    fallback_task=args.task,
                    target_files=args.target_file,
                    validation_commands=args.validation_command,
                )
                payload = {
                    "task_id": result.task_id,
                    "runner": result.runner,
                    "content": result.content,
                    "session_path": result.session_path,
                    "session": result.session,
                    "canonical_surface": result.canonical_surface,
                    "canonical_views": result.canonical_views,
                    "controller_action_bar": result.controller_action_bar,
                    "aionis": result.aionis,
                    "trace_summary": result.trace_summary,
                }
            except Exception as exc:
                payload = _cli_host_error_payload("resume", exc, workbench, task_id=args.task_id)
    elif command == "ingest":
        result = workbench.ingest(
            task_id=args.task_id,
            task=args.task,
            summary=args.summary,
            target_files=args.target_file,
            changed_files=args.changed_file,
            validation_commands=args.validation_command,
            validation_ok=args.validation_ok,
            validation_summary=args.validation_summary,
        )
        payload = {
            "task_id": result.task_id,
            "runner": result.runner,
            "content": result.content,
            "session_path": result.session_path,
            "session": result.session,
            "canonical_surface": result.canonical_surface,
            "canonical_views": result.canonical_views,
            "controller_action_bar": result.controller_action_bar,
            "aionis": result.aionis,
            "trace_summary": result.trace_summary,
        }
    elif command == "backfill":
        payload = workbench.backfill(task_id=args.task_id, rerun_recovery=args.rerun_recovery)
    elif command == "evaluate":
        payload = workbench.evaluate_session(task_id=args.task_id)
    elif command == "compare-family":
        payload = workbench.compare_family(task_id=args.task_id, limit=args.limit)
    elif command == "recent-tasks":
        payload = workbench.recent_tasks(limit=args.limit)
    elif command == "dashboard":
        payload = workbench.dashboard(limit=args.limit, family_limit=args.family_limit)
    elif command == "hosts":
        payload = workbench.host_contract()
    elif command == "consolidate":
        payload = workbench.consolidate(limit=args.limit, family_limit=args.family_limit)
    elif command == "dream":
        payload = workbench.dream(limit=args.limit, family_limit=args.family_limit, status_filter=args.status)
    elif command == "ab-test":
        if args.ab_test_command == "compare":
            payload = workbench.ab_test_compare(
                task_id=args.task_id,
                scenario_id=args.scenario_id,
                baseline_ended_in=args.baseline_ended_in,
                baseline_duration_seconds=args.baseline_duration_seconds,
                baseline_retry_count=args.baseline_retry_count,
                baseline_replan_depth=args.baseline_replan_depth,
                baseline_convergence_signal=args.baseline_convergence_signal,
                baseline_final_execution_gate=args.baseline_final_execution_gate,
                baseline_gate_flow=args.baseline_gate_flow,
                baseline_notes=args.baseline_note,
                baseline_advance_reached=args.baseline_advance_reached,
                baseline_escalated=args.baseline_escalated,
            )
        else:
            parser.error(f"unsupported ab-test command: {args.ab_test_command}")
    elif command == "app":
        if args.app_command == "show":
            payload = workbench.app_show(task_id=args.task_id)
        elif args.app_command == "ship":
            if args.use_live_generator:
                print(
                    f"app_ship running: task_id={args.task_id} mode=live",
                    file=sys.stderr,
                    flush=True,
                )
            payload = workbench.app_ship(
                task_id=args.task_id,
                prompt=args.prompt,
                output_dir=args.output_dir,
                use_live_planner=args.use_live_planner,
                use_live_generator=args.use_live_generator,
            )
        elif args.app_command == "plan":
            payload = workbench.app_plan(
                task_id=args.task_id,
                prompt=args.prompt,
                title=args.title,
                app_type=args.type,
                stack=args.stack,
                features=args.feature,
                design_direction=args.design_direction,
                criteria=args.criterion,
                use_live_planner=args.use_live_planner,
            )
        elif args.app_command == "sprint":
            payload = workbench.app_sprint(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                goal=args.goal,
                scope=args.scope,
                acceptance_checks=args.acceptance_check,
                done_definition=args.done_definition,
                proposed_by=args.proposed_by,
                approved=args.approved,
            )
        elif args.app_command == "negotiate":
            payload = workbench.app_negotiate(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                objections=args.objection,
                use_live_planner=args.use_live_planner,
            )
        elif args.app_command == "generate":
            if args.use_live_generator:
                print(
                    f"app_generate running: task_id={args.task_id} sprint_id={args.sprint_id or 'active'} mode=live",
                    file=sys.stderr,
                    flush=True,
                )
            payload = workbench.app_generate(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                execution_summary=args.summary,
                changed_target_hints=args.target,
                use_live_generator=args.use_live_generator,
            )
        elif args.app_command == "export":
            payload = workbench.app_export(
                task_id=args.task_id,
                output_dir=args.output_dir,
            )
        elif args.app_command == "retry":
            payload = workbench.app_retry(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                revision_notes=args.revision_note,
                use_live_planner=args.use_live_planner,
            )
        elif args.app_command == "advance":
            payload = workbench.app_advance(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
            )
        elif args.app_command == "replan":
            payload = workbench.app_replan(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                note=args.note,
                use_live_planner=args.use_live_planner,
            )
        elif args.app_command == "escalate":
            payload = workbench.app_escalate(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                note=args.note,
            )
        elif args.app_command == "qa":
            payload = workbench.app_qa(
                task_id=args.task_id,
                sprint_id=args.sprint_id,
                status=args.status,
                summary=args.summary,
                scores=args.score,
                blocker_notes=args.blocker,
                use_live_evaluator=args.use_live_evaluator,
            )
        else:
            parser.error(f"unsupported app command: {args.app_command}")
    elif command == "doc":
        doc_command = args.doc_command
        doc_task_id = getattr(args, "task_id", None)
        recording_kwargs = _doc_recording_kwargs(args)
        if doc_command == "compile":
            kwargs = {
                "input_path": args.input,
                "emit": args.emit,
                "strict": args.strict,
            }
            if doc_task_id:
                kwargs["task_id"] = doc_task_id
            kwargs.update(recording_kwargs)
            payload = workbench.doc_compile(**kwargs)
        elif doc_command == "run":
            kwargs = {
                "input_path": args.input,
                "registry_path": args.registry,
                "input_kind": args.input_kind,
            }
            if doc_task_id:
                kwargs["task_id"] = doc_task_id
            kwargs.update(recording_kwargs)
            payload = workbench.doc_run(**kwargs)
        elif doc_command == "publish":
            kwargs = {
                "input_path": args.input,
                "input_kind": args.input_kind,
            }
            if doc_task_id:
                kwargs["task_id"] = doc_task_id
            kwargs.update(recording_kwargs)
            payload = workbench.doc_publish(**kwargs)
        elif doc_command == "recover":
            kwargs = {
                "input_path": args.input,
                "input_kind": args.input_kind,
            }
            if doc_task_id:
                kwargs["task_id"] = doc_task_id
            kwargs.update(recording_kwargs)
            payload = workbench.doc_recover(**kwargs)
        elif doc_command == "resume":
            kwargs = {
                "input_path": args.input,
                "input_kind": args.input_kind,
                "query_text": args.query_text,
                "candidates": args.candidate,
            }
            if doc_task_id:
                kwargs["task_id"] = doc_task_id
            kwargs.update(recording_kwargs)
            payload = workbench.doc_resume(**kwargs)
        elif doc_command == "event":
            event_payload = json.loads(Path(args.event).read_text(encoding="utf-8"))
            payload = workbench.doc_event(task_id=args.task_id, event=event_payload)
        else:
            parser.error(f"unsupported doc command: {doc_command}")
    else:
        payload = workbench.inspect_session(task_id=args.task_id)

    _print_payload(payload)
    return _payload_exit_code(command, payload)


if __name__ == "__main__":
    raise SystemExit(main())
