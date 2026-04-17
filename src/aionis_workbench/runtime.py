from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .ab_test_baseline import normalize_baseline_result
from .ab_test_report import build_benchmark_comparison
from .ab_test_runner import benchmark_result_from_aionis_payload
from .app_harness_models import EvaluatorCriterion
from .app_harness_models import SprintContract
from .app_artifact_export import export_latest_app_artifact
from .app_harness_service import AppHarnessService
from .bootstrap import build_bootstrap_snapshot
from .aionisdoc_bridge import AionisdocBridge
from .aionisdoc_service import AionisdocService
from .consolidation import describe_family_prior_seed
from .consolidation_state import load_consolidation_summary
from .config import load_aionis_config, load_workbench_config, resolve_aionis_base_url, resolve_repo_root
from .controller_shell import controller_action_bar_payload
from .controller_state import apply_session_controller_gates
from .delivery_executor import DeliveryExecutor
from .delivery_families import (
    NODE_EXPRESS_API,
    NEXTJS_WEB,
    PYTHON_FASTAPI_API,
    REACT_VITE_WEB,
    SVELTE_VITE_WEB,
    VUE_VITE_WEB,
    delivery_family_contract_instructions,
    delivery_family_evaluator_criteria_specs,
    delivery_family_ship_acceptance_checks,
    delivery_family_ship_done_definition,
    delivery_family_targets,
    delivery_family_validation_commands,
    identify_delivery_family,
    infer_delivery_family_from_prompt,
)
from .delivery_results import DeliveryExecutionResult
from .delivery_workspace import DeliveryWorkspaceAdapter
from .doc_learning import inspect_doc_target, list_doc_learning_records
from .execution_host import ModelInvokeTimeout
from .execution_host_contract import ExecutionHostAdapter
from .execution_host_factory import build_execution_host
from .failure_classification import classify_execution_failure_reason
from .launcher_state import launcher_paths
from .live_profile import infer_live_mode, load_live_profile_snapshot, resolve_live_profile_snapshot_path
from .provider_profiles import get_provider_profile, resolve_provider_profile
from .reviewer_contracts import ResumeAnchor, ReviewerContract
from .reviewer_contracts import build_effective_reviewer_contract
from .runtime_bridge_host import AionisRuntimeHost
from .execution_packet import ExecutionPacket, ExecutionPacketSummary, InstrumentationSummary
from .execution_packet import (
    MaintenanceSummary,
    PatternSignalSummary,
    PlannerPacket,
    RoutingSignalSummary,
    StrategySummary,
    WorkflowSignalSummary,
)
from .policies import trace_summary
from .orchestrator import Orchestrator, OrchestrationResult
from .ops_service import OpsService
from .recovery_service import RecoveryService, ValidationResult
from .session_service import SessionService
from .surface_service import SurfaceService
from .session import (
    SessionState,
    load_recent_sessions,
    load_session,
)
from .session import project_session_path
from .tracing import TraceRecorder, extract_target_files

_DOC_RECORDING_KEYS = {"event_source", "event_origin", "recorded_at"}


def _load_workbench_env(repo_root: str | None) -> None:
    candidates: list[Path] = []
    resolved_root: Path | None = None
    if repo_root:
        resolved_root = Path(repo_root).expanduser().resolve()
    else:
        try:
            resolved_root = Path(resolve_repo_root(repo_root)).expanduser().resolve()
        except ValueError:
            resolved_root = None
    if resolved_root is not None:
        candidates.append(resolved_root / ".env")
        candidates.append(resolved_root / ".env.local")
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            env_key, env_value = stripped.split("=", 1)
            env_key = env_key.strip()
            env_value = env_value.strip().strip("\"'")
            if not env_key or env_key in os.environ:
                continue
            os.environ[env_key] = env_value


def _parse_evaluator_criteria(values: list[str] | None) -> list[EvaluatorCriterion]:
    criteria: list[EvaluatorCriterion] = []
    for raw in values or []:
        if not isinstance(raw, str):
            continue
        parts = [item.strip() for item in raw.split(":")]
        name = parts[0] if parts else ""
        if not name:
            continue
        threshold = 0.0
        weight = 1.0
        if len(parts) >= 2 and parts[1]:
            try:
                threshold = float(parts[1])
            except ValueError:
                threshold = 0.0
        if len(parts) >= 3 and parts[2]:
            try:
                weight = float(parts[2])
            except ValueError:
                weight = 1.0
        criteria.append(EvaluatorCriterion(name=name, threshold=threshold, weight=weight))
    return criteria


def _parse_score_map(values: list[str] | None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for raw in values or []:
        if not isinstance(raw, str) or "=" not in raw:
            continue
        name, score = raw.split("=", 1)
        name = name.strip()
        if not name:
            continue
        try:
            scores[name] = float(score.strip())
        except ValueError:
            continue
    return scores


def _normalize_string_items(value: object) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        cleaned = str(item).strip()
        if cleaned:
            items.append(cleaned)
    return items


def _execution_attempt_for_live_evaluator(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = dict(value)
    if str(payload.get("status") or "").strip() == "recorded":
        payload["success"] = None
    return payload


def _execution_focus_for_live_attempt(value: object, *, fallback: str = "") -> str:
    if not isinstance(value, dict):
        return fallback.strip()
    summary = str(value.get("execution_summary") or "").strip()
    hints = _normalize_string_items(value.get("changed_target_hints"))
    if summary:
        return summary
    hint_summary = ", ".join(hints[:2]).strip()
    return hint_summary or fallback.strip()


def _delivery_bootstrap_family(product_spec: object) -> str:
    return identify_delivery_family(product_spec)


def _build_app_delivery_contract(
    *,
    product_spec: dict[str, Any],
    sprint_contract: dict[str, Any],
    revision: dict[str, Any],
    execution_summary: str,
    changed_target_hints: list[str],
    selected_targets: list[str],
    validation_commands: list[str],
) -> tuple[list[str], str]:
    goal = str(sprint_contract.get("goal") or "").strip()
    scope = _normalize_string_items(sprint_contract.get("scope"))
    acceptance_checks = _normalize_string_items(sprint_contract.get("acceptance_checks"))
    done_definition = _normalize_string_items(sprint_contract.get("done_definition"))
    title = str(product_spec.get("title") or "").strip()
    prompt = str(product_spec.get("prompt") or "").strip()
    design_direction = str(product_spec.get("design_direction") or "").strip()
    features = _normalize_string_items(product_spec.get("features"))
    revision_must_fix = _normalize_string_items(revision.get("must_fix"))

    system_parts = [
        "You are Aionis delivery executor. Perform one bounded implementation attempt in the local repository.",
        "Make real file edits. Do not stop at prose, plans, summaries, TODOs, or implementation sketches.",
        "Leave behind a runnable artifact and keep the task workspace in a buildable state.",
        "Stay narrow: complete the current sprint slice before widening scope.",
        "Inspect the workspace quickly, then start editing. Do not spend multiple turns on directory listing, extended planning, or todo management.",
        "Use at most one short discovery pass before editing the target files.",
        "Important shell rule: execute() commands already run inside the task workspace. Never prefix shell commands with `cd /` or any other root reset.",
        "Important path rule: `/src/...` style paths are only for filesystem tools like read_file/write_file/edit_file. For shell commands, run `npm run build` directly from the current workspace.",
    ]
    delivery_family = _delivery_bootstrap_family(product_spec)
    system_parts.extend(delivery_family_contract_instructions(delivery_family))
    if selected_targets:
        system_parts.append(
            "Current working set:\n" + "\n".join(f"- {value}" for value in selected_targets[:10])
        )
    if validation_commands:
        system_parts.append(
            "Validation commands:\n" + "\n".join(f"- {value}" for value in validation_commands[:6])
        )

    task_parts = [
        f"Product title: {title}" if title else "",
        f"Product prompt: {prompt}" if prompt else "",
        f"Design direction: {design_direction}" if design_direction else "",
        (
            "Primary features:\n" + "\n".join(f"- {value}" for value in features[:6])
            if features
            else ""
        ),
        f"Sprint goal: {goal}" if goal else "",
        (
            "Sprint scope:\n" + "\n".join(f"- {value}" for value in scope[:6])
            if scope
            else ""
        ),
        (
            "Current execution focus:\n" + "\n".join(f"- {value}" for value in [execution_summary] if value)
            if execution_summary
            else ""
        ),
        (
            "Changed target hints:\n" + "\n".join(f"- {value}" for value in changed_target_hints[:6])
            if changed_target_hints
            else ""
        ),
        (
            "Revision must fix:\n" + "\n".join(f"- {value}" for value in revision_must_fix[:6])
            if revision_must_fix
            else ""
        ),
        (
            "Done definition:\n" + "\n".join(f"- {value}" for value in done_definition[:6])
            if done_definition
            else ""
        ),
        (
            "Acceptance checks:\n" + "\n".join(f"- {value}" for value in acceptance_checks[:6])
            if acceptance_checks
            else ""
        ),
        "Implement the bounded attempt now. Produce real code changes, keep the app coherent, and leave the workspace ready for preview/build validation.",
    ]
    return system_parts, "\n\n".join(part for part in task_parts if part)


def _simple_web_delivery_targets(product_spec: dict[str, Any]) -> list[str]:
    return delivery_family_targets(REACT_VITE_WEB.family_id, product_spec)


def _vue_web_delivery_targets(product_spec: dict[str, Any]) -> list[str]:
    return delivery_family_targets(VUE_VITE_WEB.family_id, product_spec)


def _svelte_web_delivery_targets(product_spec: dict[str, Any]) -> list[str]:
    return delivery_family_targets(SVELTE_VITE_WEB.family_id, product_spec)


def _nextjs_web_delivery_targets(product_spec: dict[str, Any]) -> list[str]:
    return delivery_family_targets(NEXTJS_WEB.family_id, product_spec)


def _python_api_delivery_targets(product_spec: dict[str, Any]) -> list[str]:
    return delivery_family_targets(PYTHON_FASTAPI_API.family_id, product_spec)


def _node_api_delivery_targets(product_spec: dict[str, Any]) -> list[str]:
    return delivery_family_targets(NODE_EXPRESS_API.family_id, product_spec)


def _default_app_session_targets(prompt: str = "") -> list[str]:
    family_id = infer_delivery_family_from_prompt(prompt)
    return delivery_family_targets(family_id, {})


def _default_app_session_validation_commands(prompt: str = "") -> list[str]:
    family_id = infer_delivery_family_from_prompt(prompt)
    return delivery_family_validation_commands(family_id)


def _default_task_entry_goal(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", prompt.strip()).strip(" .,:;!?")
    if not cleaned:
        return "Ship the first usable release path."
    lowered = cleaned.lower()
    if lowered.startswith(("build ", "create ", "make ", "design ", "ship ", "prototype ", "plan ")):
        return f"Ship the first usable version of: {cleaned}"
    return f"Ship the first usable version of {cleaned}."


def _looks_like_app_delivery_task(task: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(task or "").strip().lower())
    if not normalized:
        return False
    strong_delivery_markers = (
        "landing page",
        "homepage",
        "dashboard",
        "explorer",
        "editor",
        "studio",
        "demo",
        "website",
        "web app",
        "product site",
        "api service",
        "backend service",
        "fastapi",
        "express",
        "next.js",
        "nextjs",
        "vue",
        "svelte",
        "from scratch",
        "new project",
        "new app",
    )
    if any(marker in normalized for marker in strong_delivery_markers):
        return True
    starts_with_delivery_verb = normalized.startswith(
        ("build ", "create ", "make ", "design ", "ship ", "prototype ")
    )
    generic_delivery_nouns = (" app", " site", " page", " api", " service")
    return starts_with_delivery_verb and any(noun in normalized for noun in generic_delivery_nouns)


def _ship_route(
    *,
    task: str,
    target_files: list[str],
    validation_commands: list[str],
    output_dir: str,
) -> tuple[str, str]:
    if target_files:
        return "project_workflow", "explicit target files were provided, so this is treated as an existing-project task"
    if validation_commands:
        return "project_workflow", "explicit validation commands were provided, so this is treated as an existing-project task"
    if str(output_dir or "").strip():
        return "app_delivery", "an output directory was requested, so this is treated as a delivery task"
    if _looks_like_app_delivery_task(task):
        return "app_delivery", "the task reads like a new app/site/api delivery request"
    return "project_workflow", "no delivery-family signals were strong enough, so this defaults to the existing-project workflow"


def _short_result_preview(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return text.strip()[:240]


def _app_delivery_shared_memory(session: SessionState) -> list[str]:
    lines = [
        f"Project identity: {session.project_identity}" if session.project_identity else "",
        f"Project scope: {session.project_scope}" if session.project_scope else "",
        "Session working set: " + ", ".join(session.target_files[:8]) if session.target_files else "",
        "Session validation path: " + "; ".join(session.validation_commands[:4]) if session.validation_commands else "",
    ]
    return [line for line in lines if line]


def _reset_app_delivery_session(session: SessionState, *, prompt: str) -> SessionState:
    bootstrap = (
        dict((session.continuity_snapshot or {}).get("bootstrap") or {})
        if isinstance((session.continuity_snapshot or {}).get("bootstrap"), dict)
        else {}
    )
    session.goal = prompt.strip() or session.goal
    session.status = "ingested"
    session.target_files = _default_app_session_targets(session.goal)
    session.validation_commands = _default_app_session_validation_commands(session.goal)
    session.shared_memory = _app_delivery_shared_memory(session)
    session.working_memory = []
    session.promoted_insights = []
    session.forgetting_backlog = []
    session.delegation_packets = []
    session.delegation_returns = []
    session.collaboration_patterns = []
    session.artifacts = []
    session.selected_strategy_profile = "delivery_first"
    session.selected_validation_style = "artifact_first"
    session.selected_artifact_budget = 4
    session.selected_memory_source_limit = 4
    session.selected_trust_signal = "direct_app_session"
    session.selected_task_family = "task:web-app-delivery"
    session.selected_family_scope = "direct_task"
    session.selected_family_candidate_count = 0
    session.selected_role_sequence = []
    session.selected_pattern_summaries = []
    session.execution_packet = None
    session.execution_packet_summary = None
    session.continuity_review_pack = None
    session.evolution_review_pack = None
    session.app_harness_state = None
    session.planner_packet = None
    session.strategy_summary = None
    session.pattern_signal_summary = None
    session.workflow_signal_summary = None
    session.routing_signal_summary = None
    session.maintenance_summary = None
    session.instrumentation_summary = None
    session.context_layers_snapshot = {}
    session.last_trace_summary = {}
    session.continuity_snapshot = {
        "app_delivery_mode": True,
        "bootstrap": bootstrap,
        "project_identity": session.project_identity,
        "project_scope": session.project_scope,
        "session_working_set": session.target_files[:8],
        "session_validation_paths": session.validation_commands[:4],
        "task_goal": session.goal,
        "strategy_profile": session.selected_strategy_profile,
        "validation_style": session.selected_validation_style,
        "task_family": session.selected_task_family,
        "selected_family_scope": session.selected_family_scope,
        "selected_trust_signal": session.selected_trust_signal,
    }
    session.last_result_preview = "Created an app harness session from app plan."
    session.last_validation_result = {
        "ok": True,
        "command": "npm run build",
        "exit_code": 0,
        "summary": "Session initialized for app planning.",
        "output": "",
        "changed_files": [],
    }
    return session


def _default_live_execution_summary(
    *,
    sprint_contract: SprintContract | None,
    revision: Any | None,
    latest_execution_attempt: object,
    sprint_negotiation_notes: list[str] | None = None,
    fallback_task: str = "",
) -> str:
    revision_summary = str(getattr(revision, "revision_summary", "") or "").strip()
    negotiation_focus = _normalize_string_items(sprint_negotiation_notes)
    execution_focus = _execution_focus_for_live_attempt(
        latest_execution_attempt.to_dict() if hasattr(latest_execution_attempt, "to_dict") else latest_execution_attempt,
        fallback=str(getattr(sprint_contract, "goal", "") or fallback_task or "").strip(),
    )
    if revision_summary and negotiation_focus:
        for note in negotiation_focus:
            if note.startswith(revision_summary) and note != revision_summary:
                return note
    for note in negotiation_focus:
        if "Previous execution outcome:" in note:
            return note
    if revision_summary and execution_focus and execution_focus != revision_summary:
        return f"{revision_summary} Previous execution outcome: {execution_focus}"
    if revision_summary:
        return revision_summary
    if execution_focus:
        return execution_focus
    sprint_goal = str(getattr(sprint_contract, "goal", "") or fallback_task or "").strip()
    if sprint_goal:
        return sprint_goal
    if negotiation_focus:
        return negotiation_focus[0]
    return ""


def _default_live_changed_target_hints(
    *,
    sprint_contract: SprintContract | None,
    revision: Any | None,
    session_targets: list[str],
) -> list[str]:
    revision_must_fix = _normalize_string_items(getattr(revision, "must_fix", []))
    sprint_scope = list(getattr(sprint_contract, "scope", []) or [])
    if any(target == "package.json" for target in session_targets):
        return list(
            dict.fromkeys(
                list(session_targets[:7])
                + revision_must_fix[:4]
            )
        )
    return list(
        dict.fromkeys(
            list(session_targets[:4])
            + revision_must_fix[:4]
            + sprint_scope[:4]
        )
    )


@dataclass
class WorkbenchRunResult:
    task_id: str
    runner: str
    content: str
    session_path: str
    session: dict[str, Any]
    canonical_surface: dict[str, Any]
    canonical_views: dict[str, Any]
    controller_action_bar: dict[str, Any] | None
    aionis: dict[str, Any]
    trace_summary: dict[str, int]


def _controller_view_from_aionis(aionis: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(aionis, dict):
        return None
    task_session_state = aionis.get("task_session_state")
    if not isinstance(task_session_state, dict):
        return None
    allowed_actions = [
        item.strip()
        for item in (task_session_state.get("allowed_actions") or [])
        if isinstance(item, str) and item.strip()
    ]
    guards = [
        item
        for item in (task_session_state.get("transition_guards") or [])
        if isinstance(item, dict)
    ]
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
    last_transition = task_session_state.get("last_transition")
    if not isinstance(last_transition, dict):
        last_transition = {}
    transitions = task_session_state.get("transitions") or []
    transition_count = int(task_session_state.get("transition_count") or 0)
    if transition_count <= 0 and isinstance(transitions, list):
        transition_count = len(transitions)
    return {
        "status": str(task_session_state.get("status") or ""),
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "transition_count": transition_count,
        "last_transition_kind": str(last_transition.get("transition_kind") or ""),
        "last_transition_at": str(last_transition.get("at") or ""),
        "last_transition_detail": str(last_transition.get("detail") or ""),
        "last_startup_mode": str(task_session_state.get("last_startup_mode") or ""),
        "last_handoff_anchor": str(task_session_state.get("last_handoff_anchor") or ""),
        "last_event_text": str(task_session_state.get("last_event_text") or ""),
        "guard_reasons": guard_reasons,
    }


def _task_id_from_artifact_path(path: str) -> str:
    if not isinstance(path, str):
        return ""
    match = re.search(r"/artifacts/([^/]+)/[^/]+\.json$", path)
    return match.group(1) if match else ""


def _artifact_paths_from_text(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return list(dict.fromkeys(re.findall(r"\.aionis-workbench/artifacts/[^\s,;]+?\.json", value)))


def _task_ids_from_pattern_summary(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return list(dict.fromkeys(re.findall(r"click-\d+(?:-[a-z]+)*-\d+", value)))


def _session_family(session: SessionState) -> str:
    return (
        session.selected_task_family
        or (session.strategy_summary.task_family if session.strategy_summary else "")
        or str((session.continuity_snapshot or {}).get("task_family") or "")
    )


def _resolve_task_family(
    config_repo_root: str,
    project_scope: str,
    family_cache: dict[str, str],
    task_id: str,
) -> str:
    if not task_id:
        return ""
    if task_id in family_cache:
        return family_cache[task_id]
    prior = load_session(config_repo_root, task_id, project_scope=project_scope)
    family = _session_family(prior) if prior else ""
    family_cache[task_id] = family
    return family


def _load_family_prior(repo_root: str, project_scope: str, task_family: str) -> dict[str, Any]:
    if not task_family:
        return {}
    summary = load_consolidation_summary(
        repo_root=repo_root,
        project_scope=project_scope,
    )
    family_rows = summary.get("family_rows", [])
    if not isinstance(family_rows, list):
        return {}
    for row in family_rows:
        if isinstance(row, dict) and row.get("task_family") == task_family:
            annotated = dict(row)
            annotated.update(describe_family_prior_seed(annotated))
            return annotated
    return {}


def _family_prior_is_strong(row: dict[str, Any]) -> bool:
    return bool(describe_family_prior_seed(row).get("seed_ready"))


def _build_instrumentation_summary(config_repo_root: str, project_scope: str, session: SessionState) -> InstrumentationSummary:
    current_family = _session_family(session)
    family_scope = session.selected_family_scope or (session.strategy_summary.family_scope if session.strategy_summary else "") or "broader_similarity"
    recent = load_recent_sessions(
        config_repo_root,
        project_scope=project_scope,
        exclude_task_id=None,
        limit=24,
    )
    task_family_map: dict[str, str] = {session.task_id: current_family}
    for prior in recent:
        if prior.task_id and prior.task_id not in task_family_map:
            task_family_map[prior.task_id] = _session_family(prior)

    selected_pattern_task_ids: list[str] = []
    for summary in session.selected_pattern_summaries[:8]:
        selected_pattern_task_ids.extend(_task_ids_from_pattern_summary(summary))
    selected_pattern_task_ids = list(dict.fromkeys(selected_pattern_task_ids))
    selected_pattern_hit_count = sum(
        1
        for task_id in selected_pattern_task_ids
        if task_id != session.task_id
        and _resolve_task_family(config_repo_root, project_scope, task_family_map, task_id) == current_family
    )
    selected_pattern_miss_count = sum(
        1
        for task_id in selected_pattern_task_ids
        if task_id != session.task_id
        and (family := _resolve_task_family(config_repo_root, project_scope, task_family_map, task_id))
        and family != current_family
    )

    routed_same: list[str] = []
    routed_other: list[str] = []
    routed_known_count = 0
    routed_same_count = 0
    routed_other_count = 0
    routed_unknown_count = 0
    for packet in session.delegation_packets:
        packet_paths = list(packet.preferred_artifact_refs)
        for evidence in packet.inherited_evidence:
            packet_paths.extend(_artifact_paths_from_text(evidence))
        for path in list(dict.fromkeys(packet_paths)):
            task_id = _task_id_from_artifact_path(path)
            if not task_id:
                routed_unknown_count += 1
                continue
            family = _resolve_task_family(config_repo_root, project_scope, task_family_map, task_id)
            if not family:
                routed_unknown_count += 1
                continue
            routed_known_count += 1
            if family == current_family:
                routed_same_count += 1
                if task_id != session.task_id:
                    routed_same.append(task_id)
            else:
                routed_other_count += 1
                routed_other.append(task_id)

    hit_rate = round((routed_same_count / routed_known_count), 3) if routed_known_count else 0.0
    family_hit = family_scope in {"exact_task_signature", "same_task_family"} and bool(current_family)
    if family_hit:
        family_reason = f"Family-scoped strategy matched {current_family}."
    elif current_family:
        family_reason = f"Strategy fell back to {family_scope} for {current_family}."
    else:
        family_reason = "Task family was not resolved."

    return InstrumentationSummary(
        task_family=current_family,
        family_scope=family_scope or "broader_similarity",
        family_hit=family_hit,
        family_reason=family_reason,
        selected_pattern_hit_count=selected_pattern_hit_count,
        selected_pattern_miss_count=selected_pattern_miss_count,
        routed_artifact_known_count=routed_known_count,
        routed_artifact_same_family_count=routed_same_count,
        routed_artifact_other_family_count=routed_other_count,
        routed_artifact_unknown_count=routed_unknown_count,
        routed_artifact_hit_rate=hit_rate,
        routed_same_family_task_ids=list(dict.fromkeys(routed_same))[:8],
        routed_other_family_task_ids=list(dict.fromkeys(routed_other))[:8],
    )


def _load_correction_failure_name(session: SessionState) -> str:
    packet = session.execution_packet
    if packet:
        for candidate in packet.accepted_facts:
            if not isinstance(candidate, str):
                continue
            match = re.search(r"baseline failing test is\s+(.+)", candidate, re.IGNORECASE)
            if match and match.group(1).strip():
                return match.group(1).strip()[:240]
    for candidate in (session.context_layers_snapshot or {}).get("facts", []):
        if not isinstance(candidate, str):
            continue
        match = re.search(r"Baseline failing test:\s*(.+)", candidate)
        if match and match.group(1).strip():
            return match.group(1).strip()[:240]
    rollback_artifact = next((item for item in session.artifacts if item.kind == "rollback_hint_artifact"), None)
    if rollback_artifact is not None:
        artifact_path = Path(session.repo_root) / rollback_artifact.path
        if artifact_path.exists():
            try:
                payload = json.loads(artifact_path.read_text())
                command = payload.get("command")
                if isinstance(command, str):
                    match = re.search(r"""\s-k\s+(?:"([^"]+)"|'([^']+)'|([^\s]+))""", command)
                    if match:
                        exact = next((group for group in match.groups() if isinstance(group, str) and group.strip()), "")
                        if exact:
                            return exact.strip()[:240]
                for candidate in (
                    *((payload.get("evidence") or []) if isinstance(payload.get("evidence"), list) else []),
                    payload.get("summary"),
                    payload.get("message"),
                ):
                    if not isinstance(candidate, str):
                        continue
                    match = re.search(r"Baseline failing test:\s*(.+)", candidate)
                    if match and match.group(1).strip():
                        return match.group(1).strip()[:240]
            except Exception:
                pass
    artifact = next((item for item in session.artifacts if item.kind == "correction_packet_artifact"), None)
    if artifact is None:
        return ""
    failure_name = artifact.metadata.get("failure_name")
    if isinstance(failure_name, str) and failure_name.strip():
        return failure_name.strip()
    artifact_path = Path(session.repo_root) / artifact.path
    if artifact_path.exists():
        try:
            payload = json.loads(artifact_path.read_text())
            failure_name = payload.get("failure_name")
            if isinstance(failure_name, str) and failure_name.strip():
                return failure_name.strip()
            command = payload.get("command")
            if isinstance(command, str):
                match = re.search(r"""\s-k\s+(?:"([^"]+)"|'([^']+)'|([^\s]+))""", command)
                if match:
                    exact = next((group for group in match.groups() if isinstance(group, str) and group.strip()), "")
                    if exact:
                        return exact.strip()[:240]
            for candidate in (
                payload.get("message"),
                payload.get("summary"),
                *((payload.get("evidence") or []) if isinstance(payload.get("evidence"), list) else []),
            ):
                if not isinstance(candidate, str):
                    continue
                match = re.search(r"Baseline failing test:\s*(.+)", candidate)
                if match and match.group(1).strip():
                    return match.group(1).strip()[:240]
        except Exception:
            pass
    validation_output = (session.last_validation_result or {}).get("output")
    if isinstance(validation_output, str):
        match = re.search(r"Baseline failing test:\s*(.+)", validation_output)
        if match and match.group(1).strip():
            return match.group(1).strip()[:240]
    return ""


def _determine_packet_stage(session: SessionState) -> tuple[str, str]:
    validation_ok = (session.last_validation_result or {}).get("ok")
    validation_summary = str((session.last_validation_result or {}).get("summary") or "")
    has_timeout = any(item.kind == "timeout_artifact" for item in session.artifacts)
    has_rollback = any(item.kind == "rollback_hint_artifact" for item in session.artifacts)
    has_correction = any(item.kind == "correction_packet_artifact" for item in session.artifacts)

    if session.status == "completed":
        return "completed", "orchestrator"
    if has_rollback:
        return "rollback_recovery", "implementer"
    if has_timeout or "timed out" in session.last_result_preview.lower():
        return "paused_timeout", "orchestrator"
    if validation_summary.startswith("Regression expansion detected:"):
        return "paused_regression_expansion", "implementer"
    if validation_summary.startswith("Scope drift detected:"):
        return "paused_scope_drift", "implementer"
    if session.status == "running":
        return "implementing", "implementer"
    if validation_ok is False or has_correction:
        return "verifying", "verifier"
    if session.delegation_packets:
        return "investigating", session.delegation_packets[0].role
    return "pending", "orchestrator"


def _is_arc_session(session: SessionState) -> bool:
    continuity = session.continuity_snapshot or {}
    if isinstance(continuity.get("arc_bridge"), dict):
        return True
    task_family = (
        session.selected_task_family
        or (session.strategy_summary.task_family if session.strategy_summary else "")
        or str(continuity.get("task_family") or "")
    )
    if isinstance(task_family, str) and task_family.endswith("-arc"):
        return True
    return any(isinstance(path, str) and path.startswith("arc_games/") for path in session.target_files)


def _preferred_review_pack(session: SessionState):
    continuity_pack = session.continuity_review_pack
    evolution_pack = session.evolution_review_pack
    if evolution_pack and evolution_pack.review_contract:
        return evolution_pack
    if continuity_pack and continuity_pack.review_contract:
        return continuity_pack
    return continuity_pack or evolution_pack


def _derive_review_contract(
    session: SessionState,
    *,
    rollback_artifact,
    correction_artifact,
    pending_validations: list[str],
) -> ReviewerContract | None:
    effective_contract = build_effective_reviewer_contract(
        packet=None,
        continuity_pack=session.continuity_review_pack,
        evolution_pack=session.evolution_review_pack,
    )
    if effective_contract is not None:
        return effective_contract

    validation_failed = (session.last_validation_result or {}).get("ok") is False
    if not (rollback_artifact or correction_artifact or validation_failed or pending_validations):
        return None

    standard = "strict_review" if (rollback_artifact or correction_artifact or validation_failed) else "targeted_review"
    required_outputs: list[str] = ["patch"]
    if pending_validations:
        required_outputs.append("tests")
    if rollback_artifact:
        required_outputs.append("rollback_plan")
    acceptance_checks = list(dict.fromkeys(item for item in pending_validations if isinstance(item, str) and item.strip()))[:4]
    return ReviewerContract(
        standard=standard,
        required_outputs=list(dict.fromkeys(required_outputs)),
        acceptance_checks=acceptance_checks,
        rollback_required=rollback_artifact is not None,
    )


def _derive_resume_anchor(session: SessionState) -> ResumeAnchor | None:
    preferred_pack = _preferred_review_pack(session)
    if preferred_pack:
        for candidate in (
            preferred_pack.recovered_handoff,
            preferred_pack.latest_handoff,
            preferred_pack.latest_resume,
            preferred_pack.stable_workflow,
            preferred_pack.promotion_ready_workflow,
        ):
            if not isinstance(candidate, dict):
                continue
            anchor = str(candidate.get("anchor") or candidate.get("anchor_id") or "").strip()
            if not anchor:
                continue
            file_path = str(candidate.get("file_path") or preferred_pack.file_path or "").strip() or None
            if not file_path and preferred_pack.target_files:
                file_path = preferred_pack.target_files[0]
            symbol = str(candidate.get("symbol") or "").strip() or None
            return ResumeAnchor(anchor=anchor, file_path=file_path, symbol=symbol, repo_root=session.repo_root)

    target = next((item for item in session.target_files if isinstance(item, str) and item.strip()), "")
    if target:
        return ResumeAnchor(anchor=f"resume:{target}", file_path=target, repo_root=session.repo_root)
    return None


def _reviewer_ready_required(
    session: SessionState,
    *,
    current_stage: str,
    review_contract: ReviewerContract | None,
    rollback_artifact,
    correction_artifact,
) -> bool:
    if review_contract is None:
        return False
    if session.continuity_review_pack or session.evolution_review_pack:
        return True
    if rollback_artifact or correction_artifact:
        return True
    if (session.last_validation_result or {}).get("ok") is False:
        return True
    return current_stage in {
        "verifying",
        "rollback_recovery",
        "paused_timeout",
        "paused_regression_expansion",
        "paused_scope_drift",
    }


def _build_execution_packet(session: SessionState) -> tuple[ExecutionPacket, ExecutionPacketSummary]:
    current_stage, active_role = _determine_packet_stage(session)
    validation_summary = str((session.last_validation_result or {}).get("summary") or "")
    baseline_failure = _load_correction_failure_name(session)
    rollback_artifact = next((item for item in session.artifacts if item.kind == "rollback_hint_artifact"), None)
    correction_artifact = next((item for item in session.artifacts if item.kind == "correction_packet_artifact"), None)
    arc_bridge = session.continuity_snapshot.get("arc_bridge") if isinstance(session.continuity_snapshot, dict) else {}
    arc_bridge = arc_bridge if isinstance(arc_bridge, dict) else {}
    arc_session = _is_arc_session(session)

    hard_constraints = ["keep validation narrow", "prefer artifact references over long summaries"]
    if correction_artifact:
        hard_constraints.append("do not expand beyond the correction working set without new evidence")
    if arc_session:
        hard_constraints = [
            "treat ARC scorecard and step digest as the primary evidence surface",
            "prefer action-chain evidence over generic repo heuristics",
            "preserve benchmark semantics and avoid mutating the game definition mid-run",
        ]

    accepted_facts: list[str] = []
    if baseline_failure:
        accepted_facts.append(f"baseline failing test is {baseline_failure}")
    if session.target_files:
        accepted_facts.append(f"target file focus starts with {session.target_files[0]}")
    if rollback_artifact:
        suspicious_file = rollback_artifact.metadata.get("suspicious_file")
        if isinstance(suspicious_file, str) and suspicious_file.strip():
            accepted_facts.append(f"suspicious file is {suspicious_file.strip()}")
    if arc_session:
        action_distribution = arc_bridge.get("action_distribution")
        if isinstance(action_distribution, dict) and action_distribution:
            dominant_actions = ", ".join(
                f"{name}={count}"
                for name, count in sorted(
                    ((str(name).strip(), int(count)) for name, count in action_distribution.items() if str(name).strip()),
                    key=lambda item: (-item[1], item[0]),
                )[:4]
            )
            if dominant_actions:
                accepted_facts.append(f"dominant ARC actions are {dominant_actions}")
        recent_actions = arc_bridge.get("recent_actions")
        if isinstance(recent_actions, list) and recent_actions:
            chain = " -> ".join(str(item).strip() for item in recent_actions[:6] if str(item).strip())
            if chain:
                accepted_facts.append(f"recent ARC chain is {chain}")

    unresolved_blockers: list[str] = []
    if any(item.kind == "timeout_artifact" for item in session.artifacts):
        unresolved_blockers.append("provider timeout")
    if validation_summary and session.last_validation_result and not session.last_validation_result.get("ok"):
        cleaned_summary = validation_summary[:240]
        if re.match(r"Validation failed:\s*F{8,}", cleaned_summary):
            cleaned_summary = "validation still fails on the current correction target"
        unresolved_blockers.append(cleaned_summary)

    rollback_notes: list[str] = []
    if rollback_artifact:
        rollback_notes.append(rollback_artifact.summary)
        rollback_notes.extend(
            item
            for item in rollback_artifact.metadata.get("evidence", [])[:2]
            if isinstance(item, str) and item.strip()
        )

    pending_validations = []
    rollback_command = ""
    if rollback_artifact:
        command = rollback_artifact.metadata.get("command")
        if isinstance(command, str) and command.strip():
            rollback_command = command.strip()
    if session.status != "completed":
        if rollback_command:
            pending_validations = [rollback_command]
        else:
            pending_validations = session.validation_commands[:4]
    review_contract = _derive_review_contract(
        session,
        rollback_artifact=rollback_artifact,
        correction_artifact=correction_artifact,
        pending_validations=pending_validations,
    )
    resume_anchor = _derive_resume_anchor(session)
    reviewer_ready_required = _reviewer_ready_required(
        session,
        current_stage=current_stage,
        review_contract=review_contract,
        rollback_artifact=rollback_artifact,
        correction_artifact=correction_artifact,
    )

    next_action = "Continue from the latest session state."
    if session.status == "completed":
        next_action = "Archive the successful packet and reuse the promoted strategy on similar tasks."
    elif rollback_artifact:
        next_action = "Try the rollback hint against the exact baseline failing test before broadening scope."
    elif correction_artifact:
        next_action = "Use the correction packet and latest validation output to make one narrow fix."
    elif any(item.kind == "timeout_artifact" for item in session.artifacts):
        next_action = "Resume in timeout-aware mode and stay on the narrowest working set."
    elif pending_validations:
        next_action = "Run the first targeted validation command and keep the working set narrow."
    if arc_session:
        score = arc_bridge.get("score")
        levels_completed = arc_bridge.get("levels_completed")
        recent_actions = arc_bridge.get("recent_actions")
        recent_chain = (
            " -> ".join(str(item).strip() for item in recent_actions[:6] if str(item).strip())
            if isinstance(recent_actions, list)
            else ""
        )
        if session.status == "completed" or (isinstance(levels_completed, int) and levels_completed > 0) or (isinstance(score, (int, float)) and float(score) > 0):
            next_action = "Reuse the successful ARC action chain on the next same-family benchmark run before widening exploration."
        else:
            chain_suffix = f" Recent chain: {recent_chain}." if recent_chain else ""
            next_action = (
                "Review the ARC step digest and scorecard, compare the dominant action chain against same-family runs, "
                "then launch one narrow retry."
                + chain_suffix
            )

    packet = ExecutionPacket(
        packet_version=1,
        current_stage=current_stage,
        active_role=active_role,
        task_brief=session.goal[:240],
        target_files=session.target_files[:8],
        next_action=next_action,
        hard_constraints=list(dict.fromkeys(hard_constraints))[:6],
        accepted_facts=list(dict.fromkeys(accepted_facts))[:6],
        pending_validations=list(dict.fromkeys(pending_validations))[:4],
        unresolved_blockers=list(dict.fromkeys(unresolved_blockers))[:6],
        rollback_notes=list(dict.fromkeys(rollback_notes))[:4],
        review_contract=review_contract,
        reviewer_ready_required=reviewer_ready_required,
        resume_anchor=resume_anchor,
        artifact_refs=[artifact.path for artifact in session.artifacts[:8]],
        evidence_refs=[
            line
            for artifact in session.artifacts[:4]
            for line in artifact.metadata.get("evidence", [])[:2]
            if isinstance(line, str) and line.strip()
        ][:8],
    )
    summary = ExecutionPacketSummary(
        packet_version=packet.packet_version,
        current_stage=packet.current_stage,
        active_role=packet.active_role,
        task_brief=packet.task_brief,
        next_action=packet.next_action,
        target_file_count=len(packet.target_files),
        pending_validation_count=len(packet.pending_validations),
        unresolved_blocker_count=len(packet.unresolved_blockers),
        review_contract_present=packet.review_contract is not None,
        reviewer_ready_required=packet.reviewer_ready_required,
        resume_anchor_present=packet.resume_anchor is not None,
        artifact_ref_count=len(packet.artifact_refs),
        evidence_ref_count=len(packet.evidence_refs),
    )
    return packet, summary


class AionisWorkbench:
    def __init__(self, *, repo_root: str | None = None, load_env: bool = False) -> None:
        if load_env:
            _load_workbench_env(repo_root)
        workbench = load_workbench_config(repo_root)
        aionis = load_aionis_config(workbench.project_scope)
        self._aionis = aionis
        self._config = workbench
        self._trace = TraceRecorder()
        self._execution_host: ExecutionHostAdapter = build_execution_host(
            config=self._config,
            trace=self._trace,
        )
        self._runtime_host = AionisRuntimeHost(
            config=self._aionis,
        )
        self._ops = OpsService(
            workbench_config=self._config,
            aionis_config=self._aionis,
            execution_host=self._execution_host,
            runtime_host=self._runtime_host,
            save_session_fn=self._save_session,
        )
        self._aionisdoc = AionisdocService(
            repo_root=self._config.repo_root,
            bridge=AionisdocBridge(workspace_root=self._config.repo_root),
        )
        self._app_harness = AppHarnessService()
        self._sessions = SessionService(
            repo_root=self._config.repo_root,
            project_identity=self._config.project_identity,
            project_scope=self._config.project_scope,
            save_session_fn=self._save_session,
        )
        self._recovery = RecoveryService(
            repo_root=self._config.repo_root,
            trace_summary_fn=trace_summary,
            extract_target_files_fn=extract_target_files,
            run_validation_commands_fn=self._run_validation_commands,
            model_timeout_type=ModelInvokeTimeout,
        )
        self._surface = SurfaceService(
            repo_root=self._config.repo_root,
            project_identity=self._config.project_identity,
            project_scope=self._config.project_scope,
            sessions=self._sessions,
            recovery=self._recovery,
            build_execution_packet_fn=_build_execution_packet,
            build_instrumentation_summary_fn=_build_instrumentation_summary,
            load_family_prior_fn=_load_family_prior,
            doctor_fn=self._ops.doctor,
            dashboard_fn=self._ops.dashboard,
            background_status_fn=self._ops.background_status,
            host_contract_fn=self._ops.host_contract,
            maybe_auto_consolidate_fn=self._ops.maybe_auto_consolidate,
        )
        self._orchestrator = Orchestrator(
            workbench_config=self._config,
            aionis_config=self._aionis,
            execution_host=self._execution_host,
            runtime_host=self._runtime_host,
            trace=self._trace,
            sessions=self._sessions,
            recovery=self._recovery,
            save_session_fn=self._save_session,
            run_validation_commands_fn=self._run_validation_commands,
            apply_validation_feedback_fn=self._apply_validation_feedback,
            persist_artifacts_fn=self._persist_artifacts,
            record_auto_learning_fn=self._record_auto_learning,
            record_recorded_learning_fn=self._record_recorded_learning,
            maybe_auto_consolidate_fn=self._maybe_auto_consolidate,
        )
        self._delivery = DeliveryExecutor(
            execution_host=self._execution_host,
            trace=self._trace,
            workspace=DeliveryWorkspaceAdapter(
                repo_root=self._config.repo_root,
                collect_changed_files_fn=self._collect_changed_files,
            ),
            run_validation_commands_fn=self._run_validation_commands,
        )

    def host_contract(self) -> dict[str, Any]:
        return self._ops.host_contract()

    def _live_recovery_summary(
        self,
        *,
        capability_state: str,
        execution_reason: str,
        runtime_reason: str,
    ) -> str:
        if capability_state == "live_ready":
            return "live execution is ready"
        if capability_state == "inspect_only_missing_credentials_and_runtime":
            return "configure model credentials and restore runtime availability before retrying live execution"
        if capability_state == "inspect_only_missing_credentials":
            return "configure model credentials before retrying live execution"
        if capability_state == "inspect_only_missing_runtime":
            return "restore runtime availability before retrying live execution"
        if runtime_reason.startswith("runtime_health_http_"):
            return "runtime is configured but unhealthy; inspect the health endpoint before retrying live execution"
        if execution_reason == "model_credentials_missing":
            return "configure model credentials before retrying live execution"
        if runtime_reason == "runtime_health_unreachable":
            return "restore runtime availability before retrying live execution"
        return "live execution is currently degraded; inspect doctor/setup guidance before retrying"

    def _doctor_summary_line(
        self,
        *,
        live_ready_summary: str,
        pending_checklist_count: int,
        recovery_summary: str,
        recommendation: str,
    ) -> str:
        parts = [f"doctor-summary: {live_ready_summary}", f"pending={pending_checklist_count}"]
        if recovery_summary:
            parts.append(f"recovery={recovery_summary}")
        if recommendation:
            parts.append(f"next={recommendation}")
        return " | ".join(parts)

    def _setup_summary_line(
        self,
        *,
        live_ready_summary: str,
        pending_count: int,
        recovery_summary: str,
        next_step: str,
    ) -> str:
        parts = [f"setup-summary: {live_ready_summary}", f"pending={pending_count}"]
        if recovery_summary:
            parts.append(f"recovery={recovery_summary}")
        if next_step:
            parts.append(f"next={next_step}")
        return " | ".join(parts)

    def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False) -> dict[str, Any]:
        return self._ops.doctor(summary=summary, check=check, one_line=one_line)

    def setup(
        self,
        *,
        pending_only: bool = False,
        summary: bool = False,
        check: str | None = None,
        one_line: bool = False,
    ) -> dict[str, Any]:
        return self._ops.setup(
            pending_only=pending_only,
            summary=summary,
            check=check,
            one_line=one_line,
        )

    def _normalize_target_files(self, target_files: list[str]) -> list[str]:
        return self._sessions.normalize_target_files(target_files)

    def _normalize_validation_commands(self, validation_commands: list[str]) -> list[str]:
        return self._sessions.normalize_validation_commands(validation_commands)

    def _bootstrap_snapshot(self) -> dict[str, Any]:
        return self._surface.bootstrap_snapshot()

    def _bootstrap_canonical_views(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self._surface.bootstrap_canonical_views(snapshot)

    def bootstrap_overview(self) -> dict[str, Any]:
        return self._surface.bootstrap_overview()

    def initialize_project(self) -> dict[str, Any]:
        return self._surface.initialize_project()

    def _refresh_selected_strategy(self, session: SessionState) -> None:
        self._surface.refresh_selected_strategy(session)

    def _record_learning(
        self,
        *,
        session: SessionState,
        source: str,
        validation: ValidationResult,
        auto_absorbed: bool,
    ) -> None:
        self._surface.record_learning(
            session=session,
            source=source,
            validation=validation,
            auto_absorbed=auto_absorbed,
        )

    def _record_auto_learning(
        self,
        *,
        session: SessionState,
        source: str,
        validation: ValidationResult,
    ) -> None:
        self._surface.record_auto_learning(session=session, source=source, validation=validation)

    def _record_recorded_learning(
        self,
        *,
        session: SessionState,
        source: str,
        validation: ValidationResult,
    ) -> None:
        self._surface.record_recorded_learning(session=session, source=source, validation=validation)

    def _refresh_auto_learning_store(self, session: SessionState) -> None:
        self._surface.refresh_auto_learning_store(session)

    def _save_session(self, session: SessionState):
        return self._surface.save_session(session)

    def _canonical_surface(self, session: SessionState) -> dict[str, Any]:
        return self._surface.canonical_surface(session)

    def _canonical_views(self, session: SessionState) -> dict[str, Any]:
        return self._surface.canonical_views(session)

    def _serialized_session(self, session: SessionState) -> dict[str, Any]:
        return self._surface.serialized_session(session)

    def _evaluate_session(self, session: SessionState) -> dict[str, Any]:
        return self._surface.evaluate_session_model(session)

    def _result_payload(
        self,
        *,
        task_id: str,
        runner: str,
        content: str,
        session: SessionState,
        session_path: Path,
        aionis: dict[str, Any],
    ) -> WorkbenchRunResult:
        canonical_views = self._canonical_views(session)
        controller_view = _controller_view_from_aionis(aionis)
        if controller_view:
            controller_view = apply_session_controller_gates(controller_view, session) or controller_view
            canonical_views = {
                **canonical_views,
                "controller": controller_view,
            }
        return WorkbenchRunResult(
            task_id=task_id,
            runner=runner,
            content=content,
            session_path=str(session_path),
            session=self._serialized_session(session),
            canonical_surface=self._canonical_surface(session),
            canonical_views=canonical_views,
            controller_action_bar=controller_action_bar_payload(
                canonical_views.get("controller"),
                task_id=task_id,
            ),
            aionis=aionis,
            trace_summary=session.last_trace_summary,
        )

    def _result_from_orchestration(self, result: OrchestrationResult) -> WorkbenchRunResult:
        return self._result_payload(
            task_id=result.task_id,
            runner=result.runner,
            content=result.content,
            session=result.session,
            session_path=result.session_path,
            aionis=result.aionis,
        )

    def _collect_changed_files(self) -> list[str]:
        return self._surface.collect_changed_files()

    def _run_validation_commands(self, commands: list[str]) -> ValidationResult:
        return self._surface.run_validation_commands(commands)

    def _persist_artifacts(
        self,
        *,
        session: SessionState,
        validation: ValidationResult | None = None,
        failure: dict[str, Any] | None = None,
        correction: dict[str, Any] | None = None,
        rollback: dict[str, Any] | None = None,
    ) -> None:
        self._recovery.persist_artifacts(
            session=session,
            validation=validation,
            failure=failure,
            correction=correction,
            rollback=rollback,
        )

    def _apply_validation_feedback(self, session: SessionState, validation: ValidationResult) -> None:
        self._recovery.apply_validation_feedback(session, validation)

    def _initial_session(
        self,
        *,
        task_id: str,
        task: str,
        target_files: list[str],
        validation_commands: list[str],
        apply_strategy: bool = True,
        seed_priors: bool = True,
    ) -> SessionState:
        return self._sessions.initial_session(
            task_id=task_id,
            task=task,
            target_files=target_files,
            validation_commands=validation_commands,
            apply_strategy=apply_strategy,
            seed_priors=seed_priors,
        )

    def run(
        self,
        *,
        task_id: str,
        task: str,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
    ) -> WorkbenchRunResult:
        result = self._orchestrator.run(
            task_id=task_id,
            task=task,
            target_files=target_files,
            validation_commands=validation_commands,
        )
        return self._result_from_orchestration(result)

    def _workbench_run_payload(self, result: WorkbenchRunResult) -> dict[str, Any]:
        return {
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

    def ship(
        self,
        *,
        task_id: str,
        task: str,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
        output_dir: str = "",
        use_live_planner: bool = False,
        use_live_generator: bool = False,
    ) -> dict[str, Any]:
        normalized_target_files = list(target_files or [])
        normalized_validation_commands = list(validation_commands or [])
        route_mode, route_reason = _ship_route(
            task=task,
            target_files=normalized_target_files,
            validation_commands=normalized_validation_commands,
            output_dir=output_dir,
        )
        context = self._app_task_context()
        if route_mode == "app_delivery":
            payload = self.app_ship(
                task_id=task_id,
                prompt=task,
                output_dir=output_dir,
                use_live_planner=use_live_planner,
                use_live_generator=use_live_generator,
            )
            wrapped = dict(payload)
            wrapped["shell_view"] = "ship"
            wrapped["ship_mode"] = route_mode
            wrapped["delegated_shell_view"] = str(payload.get("shell_view") or "app_ship")
            wrapped["route_reason"] = route_reason
            wrapped["route_summary"] = str(payload.get("route_summary") or "task_intake->context_scan->route->app_ship")
            wrapped["context"] = payload.get("context") or context
            wrapped["context_summary"] = str((payload.get("context") or context).get("summary") or payload.get("context_summary") or "")
            wrapped.update(self._ship_live_profile_fields())
            return wrapped

        result = self.run(
            task_id=task_id,
            task=task,
            target_files=normalized_target_files,
            validation_commands=normalized_validation_commands,
        )
        payload = self._workbench_run_payload(result)
        payload["shell_view"] = "ship"
        payload["ship_mode"] = route_mode
        payload["delegated_shell_view"] = "run"
        payload["route_reason"] = route_reason
        payload["route_summary"] = "task_intake->context_scan->route->run"
        payload["context"] = context
        payload["context_summary"] = str(context.get("summary") or "")
        payload.update(self._ship_live_profile_fields())
        return payload

    def ingest(
        self,
        *,
        task_id: str,
        task: str,
        summary: str,
        target_files: list[str] | None = None,
        changed_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
        validation_ok: bool = True,
        validation_summary: str | None = None,
    ) -> WorkbenchRunResult:
        result = self._orchestrator.ingest(
            task_id=task_id,
            task=task,
            summary=summary,
            target_files=target_files,
            changed_files=changed_files,
            validation_commands=validation_commands,
            validation_ok=validation_ok,
            validation_summary=validation_summary,
        )
        return self._result_from_orchestration(result)

    def resume(
        self,
        *,
        task_id: str,
        fallback_task: str | None = None,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
    ) -> WorkbenchRunResult:
        result = self._orchestrator.resume(
            task_id=task_id,
            fallback_task=fallback_task,
            target_files=target_files,
            validation_commands=validation_commands,
        )
        return self._result_from_orchestration(result)

    def inspect_session(self, *, task_id: str) -> dict[str, Any]:
        return self._surface.inspect_session(task_id=task_id)

    def _load_required_session(self, *, task_id: str) -> SessionState:
        session = load_session(
            self._config.repo_root,
            task_id,
            project_scope=self._config.project_scope,
        )
        if session is None:
            raise ValueError(f"session not found: {task_id}")
        return session

    def _load_or_initialize_app_session(
        self,
        *,
        task_id: str,
        prompt: str,
    ) -> SessionState:
        session = load_session(
            self._config.repo_root,
            task_id,
            project_scope=self._config.project_scope,
        )
        if session is not None:
            _reset_app_delivery_session(session, prompt=prompt)
            self._delivery.reset_task_workspace(task_id=task_id)
            self._save_session(session)
            return session
        session = self._initial_session(
            task_id=task_id,
            task=prompt,
            target_files=_default_app_session_targets(prompt),
            validation_commands=_default_app_session_validation_commands(prompt),
            apply_strategy=False,
            seed_priors=False,
        )
        _reset_app_delivery_session(session, prompt=prompt)
        self._delivery.reset_task_workspace(task_id=task_id)
        self._save_session(session)
        return session

    def app_show(self, *, task_id: str) -> dict[str, Any]:
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_show"
        payload["task_id"] = task_id
        return payload

    def _controller_action_bar_for_task(
        self,
        *,
        task_id: str,
        canonical_views: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        resolved_views = canonical_views if isinstance(canonical_views, dict) else None
        if resolved_views is None:
            try:
                session = self._load_required_session(task_id=task_id)
            except ValueError:
                return None
            resolved_views = self._canonical_views(session)
        return controller_action_bar_payload(resolved_views.get("controller"), task_id=task_id)

    def _app_task_context(self) -> dict[str, Any]:
        repo_root = Path(self._config.repo_root)
        entries: list[str] = []
        existing_markers: list[str] = []
        for child in sorted(repo_root.iterdir(), key=lambda item: item.name.lower()):
            name = child.name
            if name.startswith(".") and name not in {".env", ".env.local"}:
                continue
            entries.append(name + ("/" if child.is_dir() else ""))
            if len(entries) >= 12:
                break
        for candidate in ("README.md", "package.json", "pyproject.toml", "src", "app", "frontend", "backend"):
            path = repo_root / candidate
            if path.exists():
                existing_markers.append(candidate + ("/" if path.is_dir() else ""))
        summary_parts = [
            f"repo={repo_root}",
            f"top={', '.join(entries[:6]) or 'empty'}",
        ]
        if existing_markers:
            summary_parts.append(f"markers={', '.join(existing_markers[:6])}")
        return {
            "repo_root": str(repo_root),
            "top_level_entries": entries,
            "existing_markers": existing_markers,
            "summary": " | ".join(summary_parts),
        }

    def _ship_live_profile_fields(self) -> dict[str, str]:
        payload = self.live_profile()
        return {
            "live_provider_id": str(payload.get("provider_id") or ""),
            "live_provider_label": str(payload.get("provider_label") or ""),
            "live_model": str(payload.get("model") or ""),
            "live_release_tier": str(payload.get("release_tier") or ""),
            "live_mode": str(payload.get("live_mode") or ""),
        }

    def _app_ship_failure_payload(
        self,
        *,
        task_id: str,
        phase: str,
        prompt: str,
        context: dict[str, Any],
        exc: Exception,
        last_payload: dict[str, Any] | None = None,
        route_steps: list[str] | None = None,
        phase_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        normalized_steps = list(route_steps or ["task_intake", "context_scan", "plan", "sprint", "generate", "export"])
        payload: dict[str, Any] = {
            "shell_view": "app_ship",
            "task_id": task_id,
            "prompt": prompt,
            "phase": phase,
            "status": "failed",
            "context": context,
            "context_summary": str(context.get("summary") or ""),
            "route_summary": "->".join(normalized_steps),
            "error": str(exc),
        }
        failure_reason = str(exc).strip()
        failure_class = classify_execution_failure_reason(failure_reason)
        payload.update(self._ship_live_profile_fields())
        if phase_history:
            payload["phase_history"] = [dict(item) for item in phase_history]
        if isinstance(last_payload, dict):
            latest_attempt = self._app_ship_harness_view(last_payload).get("latest_execution_attempt") or {}
            failure_reason = str(latest_attempt.get("failure_reason") or "").strip() or failure_reason
            failure_class = str(latest_attempt.get("failure_class") or "").strip() or failure_class
            payload["canonical_views"] = last_payload.get("canonical_views") or {}
            payload["active_sprint_id"] = (
                (
                    ((last_payload.get("canonical_views") or {}).get("app_harness") or {}).get("active_sprint_contract") or {}
                ).get("sprint_id")
                or ""
            )
            payload["latest_phase_payload"] = last_payload
        trace_failure_reason = self._app_ship_trace_failure_reason(task_id=task_id)
        if trace_failure_reason:
            if not failure_reason or failure_class == "execution_failure":
                failure_reason = trace_failure_reason
                failure_class = classify_execution_failure_reason(trace_failure_reason)
        payload["failure_reason"] = failure_reason
        payload["failure_class"] = failure_class
        payload["controller_action_bar"] = self._controller_action_bar_for_task(
            task_id=task_id,
            canonical_views=payload.get("canonical_views"),
        )
        return payload

    def _app_ship_harness_view(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return ((payload.get("canonical_views") or {}).get("app_harness") or {})

    def _app_ship_trace_failure_reason(self, *, task_id: str) -> str:
        trace_path = self._delivery.task_workspace_root(task_id=task_id) / ".aionis-delivery-trace.json"
        if not trace_path.exists():
            return ""
        try:
            payload = json.loads(trace_path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("failure_reason") or payload.get("last_error_message") or "").strip()

    def _app_ship_missing_execution_failure(
        self,
        *,
        task_id: str,
        payload: dict[str, Any] | None,
    ) -> str:
        trace_failure = self._app_ship_trace_failure_reason(task_id=task_id)
        if classify_execution_failure_reason(trace_failure) == "provider_first_turn_stall":
            return trace_failure
        harness = self._app_ship_harness_view(payload)
        latest_execution = harness.get("latest_execution_attempt") or {}
        if str(latest_execution.get("attempt_id") or "").strip():
            return ""
        return trace_failure or (
            "App ship did not record an execution attempt after generate."
        )

    def _app_ship_active_sprint_id(self, payload: dict[str, Any] | None) -> str:
        harness = self._app_ship_harness_view(payload)
        sprint = harness.get("active_sprint_contract") or {}
        return str(sprint.get("sprint_id") or "").strip()

    def _app_ship_phase_entry(
        self,
        *,
        phase: str,
        payload: dict[str, Any] | None,
        note: str = "",
    ) -> dict[str, str]:
        harness = self._app_ship_harness_view(payload)
        return {
            "phase": phase,
            "sprint_id": str(((harness.get("active_sprint_contract") or {}).get("sprint_id") or "")).strip(),
            "loop_status": str(harness.get("loop_status") or "").strip(),
            "recommended_next_action": str(harness.get("recommended_next_action") or "").strip(),
            "note": note.strip(),
        }

    def _app_ship_qa_inputs(self, payload: dict[str, Any] | None) -> tuple[str, str, list[str]]:
        harness = self._app_ship_harness_view(payload)
        attempt = harness.get("latest_execution_attempt") or {}
        failure_reason = str(attempt.get("failure_reason") or "").strip()
        validation_summary = str(attempt.get("validation_summary") or "").strip()
        execution_summary = str(attempt.get("execution_summary") or "").strip()

        summary = validation_summary or failure_reason or execution_summary
        blockers: list[str] = []
        status = "auto"
        lowered_validation = validation_summary.lower()
        if failure_reason:
            status = "failed"
            blockers.append(failure_reason)
        elif validation_summary and "passed" not in lowered_validation and any(
            token in lowered_validation for token in ("fail", "error", "timed out")
        ):
            status = "failed"
            blockers.append(validation_summary)
        return status, summary, blockers

    def _app_ship_reconcile_execution_attempt(
        self,
        *,
        task_id: str,
        sprint_id: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        harness = self._app_ship_harness_view(payload)
        latest_execution = harness.get("latest_execution_attempt") or {}
        if str(latest_execution.get("attempt_id") or "").strip():
            return payload or {}
        trace_failure = self._app_ship_trace_failure_reason(task_id=task_id)
        if classify_execution_failure_reason(trace_failure) in {
            "provider_transient_error",
            "provider_first_turn_stall",
        }:
            return payload or {}
        session = self._load_required_session(task_id=task_id)
        state = session.app_harness_state
        active_sprint = state.active_sprint_contract if state else None
        selected_sprint_id = sprint_id or (active_sprint.sprint_id if active_sprint else "")
        execution_summary = (
            str(latest_execution.get("execution_summary") or "").strip()
            or (active_sprint.goal if active_sprint else "")
            or _default_task_entry_goal(session.goal)
        )
        changed_target_hints = (
            _normalize_string_items(latest_execution.get("changed_target_hints") or [])
            or delivery_family_targets(
                _delivery_bootstrap_family(state.product_spec.to_dict()) if state and state.product_spec else "",
                state.product_spec.to_dict() if state and state.product_spec else {},
            )[:4]
            or list(session.target_files[:4])
        )
        validation_commands = self._normalize_validation_commands(
            list(active_sprint.acceptance_checks if active_sprint and active_sprint.sprint_id == selected_sprint_id else [])
        )
        recovered = self._delivery.recover_app_generate(
            session=session,
            validation_commands=validation_commands,
            execution_summary=execution_summary,
            changed_target_hints=changed_target_hints,
        )
        if recovered is None:
            return payload or {}
        artifact_path = recovered.artifact_paths[0] if recovered.artifact_paths else ""
        self._app_harness.record_execution_attempt(
            session,
            sprint_id=selected_sprint_id,
            execution_mode="live",
            execution_summary=recovered.execution_summary,
            changed_target_hints=recovered.changed_target_hints,
            changed_files=recovered.changed_files,
            artifact_root=recovered.artifact_root,
            artifact_kind=recovered.artifact_kind,
            artifact_path=artifact_path,
            preview_command=recovered.preview_command,
            trace_path=recovered.trace_path,
            validation_command=recovered.validation_command,
            validation_summary=recovered.validation_summary,
            failure_reason=recovered.failure_reason,
            status="recorded",
            success=recovered.validation_ok,
        )
        session.last_result_preview = _short_result_preview(
            recovered.validation_summary
            or recovered.execution_summary
            or "Recovered a delivery artifact from the task workspace."
        )
        session.last_validation_result = {
            "ok": recovered.validation_ok,
            "command": recovered.validation_command,
            "summary": recovered.validation_summary,
            "changed_files": recovered.changed_files[:8],
        }
        self._save_session(session)
        refreshed = self._surface.inspect_session(task_id=task_id)
        refreshed["shell_view"] = "app_generate"
        refreshed["task_id"] = task_id
        return refreshed

    def _app_ship_approve_active_sprint(self, *, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        harness = self._app_ship_harness_view(payload)
        sprint = harness.get("active_sprint_contract") or {}
        sprint_id = str(sprint.get("sprint_id") or "").strip()
        if not sprint_id:
            return payload
        return self.app_sprint(
            task_id=task_id,
            sprint_id=sprint_id,
            goal=str(sprint.get("goal") or "").strip(),
            scope=_normalize_string_items(sprint.get("scope")),
            acceptance_checks=_normalize_string_items(sprint.get("acceptance_checks")),
            done_definition=_normalize_string_items(sprint.get("done_definition")),
            proposed_by=str(sprint.get("proposed_by") or "").strip() or "task_entry",
            approved=True,
        )

    def app_plan(
        self,
        *,
        task_id: str,
        prompt: str,
        title: str = "",
        app_type: str = "",
        stack: list[str] | None = None,
        features: list[str] | None = None,
        design_direction: str = "",
        criteria: list[str] | None = None,
        use_live_planner: bool = False,
    ) -> dict[str, Any]:
        session = self._load_or_initialize_app_session(task_id=task_id, prompt=prompt)
        explicit_criteria = list(criteria or [])
        if not explicit_criteria:
            inferred_family = infer_delivery_family_from_prompt(prompt)
            explicit_criteria = delivery_family_evaluator_criteria_specs(inferred_family)
        evaluator_criteria = _parse_evaluator_criteria(explicit_criteria)
        planner_mode = "deterministic"
        if use_live_planner:
            live_plan = self._execution_host.plan_app_live(prompt=prompt)
            sprint_1 = live_plan.get("sprint_1") if isinstance(live_plan.get("sprint_1"), dict) else {}
            initial_sprint = SprintContract(
                sprint_id="sprint-1",
                goal=str(sprint_1.get("goal") or "").strip() or "Ship the first usable release path.",
                scope=[str(item).strip() for item in (sprint_1.get("scope") or []) if str(item).strip()],
                acceptance_checks=[
                    str(item).strip() for item in (sprint_1.get("acceptance_checks") or []) if str(item).strip()
                ],
                done_definition=[
                    str(item).strip() for item in (sprint_1.get("done_definition") or []) if str(item).strip()
                ],
                proposed_by="live_planner",
                approved=False,
            )
            self._app_harness.plan_app(
                session,
                prompt=prompt,
                title=str(live_plan.get("title") or title or "").strip(),
                app_type=str(live_plan.get("app_type") or app_type or "").strip(),
                stack=[
                    str(item).strip() for item in (live_plan.get("stack") or stack or []) if str(item).strip()
                ],
                features=[
                    str(item).strip()
                    for item in (live_plan.get("features") or features or [])
                    if str(item).strip()
                ],
                design_direction=str(live_plan.get("design_direction") or design_direction or "").strip(),
                evaluator_criteria=evaluator_criteria,
                planning_rationale=[
                    str(item).strip()
                    for item in (live_plan.get("planning_rationale") or [])
                    if str(item).strip()
                ],
                initial_sprint_contract=initial_sprint,
                planner_mode="live",
            )
            planner_mode = "live"
        else:
            self._app_harness.plan_app(
                session,
                prompt=prompt,
                title=title,
                app_type=app_type,
                stack=stack,
                features=features,
                design_direction=design_direction,
                evaluator_criteria=evaluator_criteria,
                planner_mode="deterministic",
            )
        if session.app_harness_state and session.app_harness_state.active_sprint_contract:
            delivery_family = infer_delivery_family_from_prompt(prompt)
            family_acceptance_checks = delivery_family_ship_acceptance_checks(delivery_family)
            family_done_definition = delivery_family_ship_done_definition(delivery_family)
            if family_acceptance_checks:
                session.app_harness_state.active_sprint_contract.acceptance_checks = list(family_acceptance_checks)
            if family_done_definition:
                session.app_harness_state.active_sprint_contract.done_definition = list(family_done_definition)
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_plan"
        payload["task_id"] = task_id
        payload["planner_mode"] = planner_mode
        if use_live_planner:
            payload["app_planner_timeout_seconds"] = int(self._execution_host.live_app_planner_timeout_seconds())
            payload["app_planner_max_completion_tokens"] = int(self._execution_host.live_app_planner_max_completion_tokens())
        return payload

    def app_ship(
        self,
        *,
        task_id: str,
        prompt: str,
        output_dir: str = "",
        use_live_planner: bool = False,
        use_live_generator: bool = False,
    ) -> dict[str, Any]:
        context = self._app_task_context()
        route_steps = ["task_intake", "context_scan"]
        phase_history = [self._app_ship_phase_entry(phase="context_scan", payload=None, note=str(context.get("summary") or ""))]

        try:
            plan_payload = self.app_plan(
                task_id=task_id,
                prompt=prompt,
                use_live_planner=use_live_planner,
            )
        except Exception as exc:
            return self._app_ship_failure_payload(
                task_id=task_id,
                phase="plan",
                prompt=prompt,
                context=context,
                exc=exc,
                route_steps=route_steps,
                phase_history=phase_history,
            )
        route_steps.append("plan")
        phase_history.append(self._app_ship_phase_entry(phase="plan", payload=plan_payload))

        app_harness = ((plan_payload.get("canonical_views") or {}).get("app_harness") or {})
        product_spec = app_harness.get("product_spec") or {}
        sprint = (app_harness.get("active_sprint_contract") or {})
        sprint_id = str(sprint.get("sprint_id") or "").strip() or "sprint-1"
        goal = str(sprint.get("goal") or "").strip() or _default_task_entry_goal(prompt)
        scope = _normalize_string_items(sprint.get("scope"))
        acceptance_checks = _normalize_string_items(sprint.get("acceptance_checks"))
        done_definition = _normalize_string_items(sprint.get("done_definition"))
        proposed_by = str(sprint.get("proposed_by") or "").strip() or "task_entry"
        delivery_family = _delivery_bootstrap_family(product_spec)
        family_acceptance_checks = delivery_family_ship_acceptance_checks(delivery_family)
        family_done_definition = delivery_family_ship_done_definition(delivery_family)
        if family_acceptance_checks:
            acceptance_checks = family_acceptance_checks
        if family_done_definition and not done_definition:
            done_definition = family_done_definition

        try:
            sprint_payload = self.app_sprint(
                task_id=task_id,
                sprint_id=sprint_id,
                goal=goal,
                scope=scope,
                acceptance_checks=acceptance_checks,
                done_definition=done_definition,
                proposed_by=proposed_by,
                approved=True,
            )
        except Exception as exc:
            return self._app_ship_failure_payload(
                task_id=task_id,
                phase="sprint",
                prompt=prompt,
                context=context,
                exc=exc,
                last_payload=plan_payload,
                route_steps=route_steps,
                phase_history=phase_history,
            )
        route_steps.append("sprint")
        phase_history.append(self._app_ship_phase_entry(phase="sprint", payload=sprint_payload))

        try:
            generate_payload = self.app_generate(
                task_id=task_id,
                sprint_id=sprint_id,
                use_live_generator=use_live_generator,
            )
        except Exception as exc:
            return self._app_ship_failure_payload(
                task_id=task_id,
                phase="generate",
                prompt=prompt,
                context=context,
                exc=exc,
                last_payload=sprint_payload,
                route_steps=route_steps,
                phase_history=phase_history,
            )
        route_steps.append("generate")
        phase_history.append(self._app_ship_phase_entry(phase="generate", payload=generate_payload))

        current_payload = self._app_ship_reconcile_execution_attempt(
            task_id=task_id,
            sprint_id=sprint_id,
            payload=generate_payload,
        )
        if current_payload is not generate_payload:
            phase_history[-1] = self._app_ship_phase_entry(phase="generate", payload=current_payload)
        missing_execution_failure = self._app_ship_missing_execution_failure(
            task_id=task_id,
            payload=current_payload,
        )
        if missing_execution_failure:
            return self._app_ship_failure_payload(
                task_id=task_id,
                phase="generate",
                prompt=prompt,
                context=context,
                exc=RuntimeError(missing_execution_failure),
                last_payload=current_payload,
                route_steps=route_steps,
                phase_history=phase_history,
            )
        retry_cycle_ran = False
        replan_cycle_ran = False
        pending_advance_sprint_id = ""

        while True:
            harness = self._app_ship_harness_view(current_payload)
            current_sprint_id = self._app_ship_active_sprint_id(current_payload) or sprint_id
            recommended_next_action = str(harness.get("recommended_next_action") or "").strip()
            execution_gate = str(harness.get("execution_gate") or "").strip()

            if recommended_next_action == "evaluate_current_execution" or execution_gate == "needs_qa":
                qa_status, qa_summary, qa_blockers = self._app_ship_qa_inputs(current_payload)
                try:
                    current_payload = self.app_qa(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        status=qa_status,
                        summary=qa_summary,
                        blocker_notes=qa_blockers,
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="qa",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("qa")
                phase_history.append(self._app_ship_phase_entry(phase="qa", payload=current_payload, note=qa_status))
                continue

            if recommended_next_action == "advance_to_next_sprint":
                next_sprint_id = str(harness.get("next_sprint_candidate_id") or "").strip()
                pending_advance_sprint_id = next_sprint_id
                break

            if recommended_next_action == "negotiate_current_sprint" and not retry_cycle_ran:
                try:
                    current_payload = self.app_negotiate(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        use_live_planner=use_live_planner,
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="negotiate",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("negotiate")
                phase_history.append(self._app_ship_phase_entry(phase="negotiate", payload=current_payload))
                recommended_next_action = "retry_current_sprint"

            if recommended_next_action == "retry_current_sprint" and not retry_cycle_ran:
                try:
                    current_payload = self.app_retry(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        use_live_planner=use_live_planner,
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="retry",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("retry")
                phase_history.append(self._app_ship_phase_entry(phase="retry", payload=current_payload))
                retry_cycle_ran = True
                current_sprint_id = self._app_ship_active_sprint_id(current_payload) or current_sprint_id
                try:
                    current_payload = self.app_generate(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        use_live_generator=use_live_generator,
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="generate",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("generate")
                current_payload = self._app_ship_reconcile_execution_attempt(
                    task_id=task_id,
                    sprint_id=current_sprint_id,
                    payload=current_payload,
                )
                phase_history.append(self._app_ship_phase_entry(phase="generate", payload=current_payload, note="retry"))
                missing_execution_failure = self._app_ship_missing_execution_failure(
                    task_id=task_id,
                    payload=current_payload,
                )
                if missing_execution_failure:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="generate",
                        prompt=prompt,
                        context=context,
                        exc=RuntimeError(missing_execution_failure),
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                continue

            if recommended_next_action == "replan_or_escalate" and not replan_cycle_ran:
                try:
                    current_payload = self.app_escalate(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        note="auto-escalate after bounded retry budget exhaustion",
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="escalate",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("escalate")
                phase_history.append(self._app_ship_phase_entry(phase="escalate", payload=current_payload))
                try:
                    current_payload = self.app_replan(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        note="Auto-replan the current sprint around the latest blocked execution path.",
                        use_live_planner=use_live_planner,
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="replan",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("replan")
                phase_history.append(self._app_ship_phase_entry(phase="replan", payload=current_payload))
                try:
                    current_payload = self._app_ship_approve_active_sprint(task_id=task_id, payload=current_payload)
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="sprint",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("sprint")
                phase_history.append(self._app_ship_phase_entry(phase="sprint", payload=current_payload, note="replan approval"))
                replan_cycle_ran = True
                current_sprint_id = self._app_ship_active_sprint_id(current_payload) or current_sprint_id
                try:
                    current_payload = self.app_generate(
                        task_id=task_id,
                        sprint_id=current_sprint_id,
                        use_live_generator=use_live_generator,
                    )
                except Exception as exc:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="generate",
                        prompt=prompt,
                        context=context,
                        exc=exc,
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                route_steps.append("generate")
                current_payload = self._app_ship_reconcile_execution_attempt(
                    task_id=task_id,
                    sprint_id=current_sprint_id,
                    payload=current_payload,
                )
                phase_history.append(self._app_ship_phase_entry(phase="generate", payload=current_payload, note="replan"))
                missing_execution_failure = self._app_ship_missing_execution_failure(
                    task_id=task_id,
                    payload=current_payload,
                )
                if missing_execution_failure:
                    return self._app_ship_failure_payload(
                        task_id=task_id,
                        phase="generate",
                        prompt=prompt,
                        context=context,
                        exc=RuntimeError(missing_execution_failure),
                        last_payload=current_payload,
                        route_steps=route_steps,
                        phase_history=phase_history,
                    )
                continue

            break

        try:
            export_payload = self.app_export(
                task_id=task_id,
                output_dir=output_dir,
            )
        except Exception as exc:
            return self._app_ship_failure_payload(
                task_id=task_id,
                phase="export",
                prompt=prompt,
                context=context,
                exc=exc,
                last_payload=current_payload,
                route_steps=route_steps,
                phase_history=phase_history,
            )
        route_steps.append("export")
        phase_history.append(self._app_ship_phase_entry(phase="export", payload=current_payload))

        if pending_advance_sprint_id:
            try:
                current_payload = self.app_advance(
                    task_id=task_id,
                    sprint_id=pending_advance_sprint_id,
                )
            except Exception as exc:
                return self._app_ship_failure_payload(
                    task_id=task_id,
                    phase="advance",
                    prompt=prompt,
                    context=context,
                    exc=exc,
                    last_payload=current_payload,
                    route_steps=route_steps,
                    phase_history=phase_history,
                )
            route_steps.append("advance")
            phase_history.append(
                self._app_ship_phase_entry(
                    phase="advance",
                    payload=current_payload,
                    note=pending_advance_sprint_id,
                )
            )

        latest_attempt = (self._app_ship_harness_view(current_payload).get("latest_execution_attempt") or {})
        failure_reason = str(latest_attempt.get("failure_reason") or "")
        result_payload = {
            "shell_view": "app_ship",
            "task_id": task_id,
            "prompt": prompt,
            "status": "completed",
            "phase": "complete",
            "context": context,
            "context_summary": str(context.get("summary") or ""),
            "route_summary": "->".join(route_steps),
            "phase_history": phase_history,
            "active_sprint_id": self._app_ship_active_sprint_id(current_payload) or sprint_id,
            "planner_mode": plan_payload.get("planner_mode") or "deterministic",
            "canonical_views": current_payload.get("canonical_views") or {},
            "export_root": export_payload.get("export_root") or "",
            "entrypoint": export_payload.get("entrypoint") or "",
            "preview_command": export_payload.get("preview_command") or "",
            "validation_summary": export_payload.get("validation_summary") or str(latest_attempt.get("validation_summary") or ""),
            "failure_reason": failure_reason,
            "failure_class": classify_execution_failure_reason(failure_reason),
            "plan_payload": plan_payload,
            "sprint_payload": sprint_payload,
            "generate_payload": generate_payload,
            "final_phase_payload": current_payload,
            "export_payload": export_payload,
            "controller_action_bar": self._controller_action_bar_for_task(
                task_id=task_id,
                canonical_views=current_payload.get("canonical_views") if isinstance(current_payload, dict) else None,
            ),
        }
        result_payload.update(self._ship_live_profile_fields())
        if use_live_generator:
            result_payload["app_generator_timeout_seconds"] = int(self._execution_host.live_app_generator_timeout_seconds())
            result_payload["app_generator_max_completion_tokens"] = int(self._execution_host.live_app_generator_max_completion_tokens())
        return result_payload

    def app_sprint(
        self,
        *,
        task_id: str,
        sprint_id: str,
        goal: str,
        scope: list[str] | None = None,
        acceptance_checks: list[str] | None = None,
        done_definition: list[str] | None = None,
        proposed_by: str = "",
        approved: bool = False,
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        self._app_harness.set_sprint_contract(
            session,
            sprint_id=sprint_id,
            goal=goal,
            scope=scope,
            acceptance_checks=acceptance_checks,
            done_definition=done_definition,
            proposed_by=proposed_by,
            approved=approved,
        )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_sprint"
        payload["task_id"] = task_id
        return payload

    def app_qa(
        self,
        *,
        task_id: str,
        sprint_id: str,
        status: str = "auto",
        summary: str = "",
        scores: list[str] | None = None,
        blocker_notes: list[str] | None = None,
        use_live_evaluator: bool = False,
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        parsed_scores = _parse_score_map(scores)
        app_state = session.app_harness_state
        active_sprint = app_state.active_sprint_contract if app_state else None
        if sprint_id and active_sprint and active_sprint.sprint_id != sprint_id:
            self._save_session(session)
            payload = self._surface.inspect_session(task_id=task_id)
            payload["shell_view"] = "app_qa"
            payload["task_id"] = task_id
            return payload
        if use_live_evaluator:
            product_spec = app_state.product_spec.to_dict() if app_state and app_state.product_spec else {}
            sprint_contract = (
                app_state.active_sprint_contract.to_dict()
                if app_state and app_state.active_sprint_contract and app_state.active_sprint_contract.sprint_id == sprint_id
                else {}
            )
            evaluator_criteria = [
                item.to_dict() for item in (app_state.evaluator_criteria if app_state else [])
            ]
            live_evaluation = self._execution_host.evaluate_sprint_live(
                product_spec=product_spec,
                sprint_contract=sprint_contract,
                evaluator_criteria=evaluator_criteria,
                latest_execution_attempt=_execution_attempt_for_live_evaluator(
                    app_state.latest_execution_attempt.to_dict()
                    if app_state and app_state.latest_execution_attempt and app_state.latest_execution_attempt.sprint_id == sprint_id
                    else {}
                ),
                execution_focus=_execution_focus_for_live_attempt(
                    app_state.latest_execution_attempt.to_dict()
                    if app_state and app_state.latest_execution_attempt and app_state.latest_execution_attempt.sprint_id == sprint_id
                    else {}
                ),
                summary=summary,
                blocker_notes=list(blocker_notes or []),
                requested_status=status,
                criteria_scores=parsed_scores,
            )
            self._app_harness.record_sprint_evaluation(
                session,
                sprint_id=sprint_id,
                status=str(live_evaluation.get("status") or status or "").strip(),
                summary=str(live_evaluation.get("summary") or summary or "").strip(),
                criteria_scores={
                    key: float(value)
                    for key, value in (live_evaluation.get("criteria_scores") or {}).items()
                    if isinstance(key, str)
                },
                blocker_notes=_normalize_string_items(live_evaluation.get("blocker_notes") or blocker_notes or []),
                evaluator_mode="live",
                passing_criteria=_normalize_string_items(live_evaluation.get("passing_criteria") or []),
                failing_criteria=_normalize_string_items(live_evaluation.get("failing_criteria") or []),
            )
        else:
            self._app_harness.record_sprint_evaluation(
                session,
                sprint_id=sprint_id,
                status=status,
                summary=summary,
                criteria_scores=parsed_scores,
                blocker_notes=blocker_notes,
            )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_qa"
        payload["task_id"] = task_id
        if use_live_evaluator:
            payload["app_evaluator_timeout_seconds"] = int(self._execution_host.live_app_evaluator_timeout_seconds())
            payload["app_evaluator_max_completion_tokens"] = int(self._execution_host.live_app_evaluator_max_completion_tokens())
        return payload

    def app_negotiate(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        objections: list[str] | None = None,
        use_live_planner: bool = False,
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        app_state = session.app_harness_state
        active_sprint = app_state.active_sprint_contract if app_state else None
        if sprint_id and active_sprint and active_sprint.sprint_id != sprint_id:
            self._save_session(session)
            payload = self._surface.inspect_session(task_id=task_id)
            payload["shell_view"] = "app_negotiate"
            payload["task_id"] = task_id
            return payload
        if use_live_planner:
            selected_sprint = active_sprint
            selected_evaluation = (
                app_state.latest_sprint_evaluation
                if app_state and app_state.latest_sprint_evaluation and selected_sprint and app_state.latest_sprint_evaluation.sprint_id == selected_sprint.sprint_id
                else None
            )
            live_negotiation = self._execution_host.negotiate_sprint_live(
                product_spec=app_state.product_spec.to_dict() if app_state and app_state.product_spec else {},
                sprint_contract=selected_sprint.to_dict() if selected_sprint else {},
                latest_evaluation=selected_evaluation.to_dict() if selected_evaluation else {},
                planned_sprints=[
                    item.to_dict() for item in (app_state.planned_sprint_contracts if app_state else [])
                ],
                objections=list(objections or []),
            )
            self._app_harness.negotiate_sprint(
                session,
                sprint_id=sprint_id,
                evaluator_objections=objections,
                planner_mode="live",
                planner_response=[
                    str(item).strip()
                    for item in (live_negotiation.get("planner_response") or [])
                    if str(item).strip()
                ],
                recommended_action=str(live_negotiation.get("recommended_action") or "").strip(),
                sprint_negotiation_notes=[
                    str(item).strip()
                    for item in (live_negotiation.get("sprint_negotiation_notes") or [])
                    if str(item).strip()
                ],
            )
        else:
            self._app_harness.negotiate_sprint(
                session,
                sprint_id=sprint_id,
                evaluator_objections=objections,
            )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_negotiate"
        payload["task_id"] = task_id
        if use_live_planner:
            payload["app_negotiator_timeout_seconds"] = int(self._execution_host.live_app_negotiator_timeout_seconds())
            payload["app_negotiator_max_completion_tokens"] = int(self._execution_host.live_app_negotiator_max_completion_tokens())
        return payload

    def app_retry(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        revision_notes: list[str] | None = None,
        use_live_planner: bool = False,
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        app_state = session.app_harness_state
        active_sprint = app_state.active_sprint_contract if app_state else None
        if sprint_id and active_sprint and active_sprint.sprint_id != sprint_id:
            self._save_session(session)
            payload = self._surface.inspect_session(task_id=task_id)
            payload["shell_view"] = "app_retry"
            payload["task_id"] = task_id
            return payload
        if use_live_planner:
            selected_sprint = active_sprint
            selected_evaluation = (
                app_state.latest_sprint_evaluation
                if app_state and app_state.latest_sprint_evaluation and selected_sprint and app_state.latest_sprint_evaluation.sprint_id == selected_sprint.sprint_id
                else None
            )
            selected_negotiation = (
                app_state.latest_negotiation_round
                if app_state and app_state.latest_negotiation_round and selected_sprint and app_state.latest_negotiation_round.sprint_id == selected_sprint.sprint_id
                else None
            )
            live_revision = self._execution_host.revise_sprint_live(
                product_spec=app_state.product_spec.to_dict() if app_state and app_state.product_spec else {},
                sprint_contract=selected_sprint.to_dict() if selected_sprint else {},
                latest_evaluation=selected_evaluation.to_dict() if selected_evaluation else {},
                latest_negotiation_round=selected_negotiation.to_dict() if selected_negotiation else {},
                revision_notes=list(revision_notes or []),
            )
            self._app_harness.apply_revision_attempt(
                session,
                sprint_id=sprint_id,
                planner_mode="live",
                revision_summary=str(live_revision.get("revision_summary") or "").strip(),
                must_fix=[
                    str(item).strip()
                    for item in (live_revision.get("must_fix") or [])
                    if str(item).strip()
                ],
                must_keep=[
                    str(item).strip()
                    for item in (live_revision.get("must_keep") or [])
                    if str(item).strip()
                ],
                explicit_notes=revision_notes,
                merge_with_derived=False,
            )
        else:
            self._app_harness.apply_revision_attempt(
                session,
                sprint_id=sprint_id,
                planner_mode="deterministic",
                explicit_notes=revision_notes,
            )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_retry"
        payload["task_id"] = task_id
        if use_live_planner:
            payload["app_revisor_timeout_seconds"] = int(self._execution_host.live_app_revisor_timeout_seconds())
            payload["app_revisor_max_completion_tokens"] = int(self._execution_host.live_app_revisor_max_completion_tokens())
        return payload

    def app_generate(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        execution_summary: str = "",
        changed_target_hints: list[str] | None = None,
        use_live_generator: bool = False,
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        app_state = session.app_harness_state
        active_sprint = app_state.active_sprint_contract if app_state else None
        selected_sprint = active_sprint
        selected_revision = (
            app_state.latest_revision
            if app_state and app_state.latest_revision and selected_sprint and app_state.latest_revision.sprint_id == selected_sprint.sprint_id
            else None
        )
        if sprint_id and active_sprint and active_sprint.sprint_id != sprint_id:
            self._save_session(session)
            payload = self._surface.inspect_session(task_id=task_id)
            payload["shell_view"] = "app_generate"
            payload["task_id"] = task_id
            return payload
        if use_live_generator:
            selected_evaluation = (
                app_state.latest_sprint_evaluation
                if app_state and app_state.latest_sprint_evaluation and selected_sprint and app_state.latest_sprint_evaluation.sprint_id == selected_sprint.sprint_id
                else None
            )
            selected_negotiation = (
                app_state.latest_negotiation_round
                if app_state and app_state.latest_negotiation_round and selected_sprint and app_state.latest_negotiation_round.sprint_id == selected_sprint.sprint_id
                else None
            )
            product_spec_payload = app_state.product_spec.to_dict() if app_state and app_state.product_spec else {}
            delivery_family = _delivery_bootstrap_family(product_spec_payload)
            use_direct_delivery_contract = bool(delivery_family)
            selected_attempt = (
                app_state.latest_execution_attempt
                if app_state and app_state.latest_execution_attempt and selected_sprint and app_state.latest_execution_attempt.sprint_id == selected_sprint.sprint_id
                else None
            )
            focus_attempt = selected_attempt or (app_state.latest_execution_attempt if app_state else None)
            execution_summary = (
                str(execution_summary or "").strip()
                or _default_live_execution_summary(
                    sprint_contract=selected_sprint,
                    revision=selected_revision,
                    latest_execution_attempt=focus_attempt,
                    sprint_negotiation_notes=app_state.sprint_negotiation_notes if app_state else [],
                    fallback_task=session.goal,
                )
            )
            changed_target_hints = list(changed_target_hints or []) or _default_live_changed_target_hints(
                sprint_contract=selected_sprint,
                revision=selected_revision,
                session_targets=session.target_files,
            )
            if delivery_family == REACT_VITE_WEB.family_id:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            _simple_web_delivery_targets(product_spec_payload)
                            + list(changed_target_hints or [])
                            + list(session.target_files[:7])
                        )
                    )
                )
            elif delivery_family == NEXTJS_WEB.family_id:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            _nextjs_web_delivery_targets(product_spec_payload)
                            + list(changed_target_hints or [])
                            + list(session.target_files[:7])
                        )
                    )
                )
            elif delivery_family == VUE_VITE_WEB.family_id:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            _vue_web_delivery_targets(product_spec_payload)
                            + list(changed_target_hints or [])
                            + list(session.target_files[:7])
                        )
                    )
                )
            elif delivery_family == SVELTE_VITE_WEB.family_id:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            _svelte_web_delivery_targets(product_spec_payload)
                            + list(changed_target_hints or [])
                            + list(session.target_files[:7])
                        )
                    )
                )
            elif delivery_family == PYTHON_FASTAPI_API.family_id:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            _python_api_delivery_targets(product_spec_payload)
                            + list(changed_target_hints or [])
                            + list(session.target_files[:4])
                        )
                    )
                )
            elif delivery_family == NODE_EXPRESS_API.family_id:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            _node_api_delivery_targets(product_spec_payload)
                            + list(changed_target_hints or [])
                            + list(session.target_files[:4])
                        )
                    )
                )
            else:
                selected_targets = self._normalize_target_files(
                    list(
                        dict.fromkeys(
                            list(selected_sprint.scope[:3] if selected_sprint else [])
                            + list(changed_target_hints or [])
                            + list(session.target_files[:4])
                        )
                    )
                )
            if delivery_family in {
                REACT_VITE_WEB.family_id,
                VUE_VITE_WEB.family_id,
                SVELTE_VITE_WEB.family_id,
                NEXTJS_WEB.family_id,
                PYTHON_FASTAPI_API.family_id,
                NODE_EXPRESS_API.family_id,
            }:
                validation_commands = delivery_family_validation_commands(delivery_family)
            else:
                validation_commands = self._normalize_validation_commands(
                    list(selected_sprint.acceptance_checks if selected_sprint and selected_sprint.acceptance_checks else [])
                )
            system_parts, delivery_task = _build_app_delivery_contract(
                product_spec=product_spec_payload,
                sprint_contract=selected_sprint.to_dict() if selected_sprint else {},
                revision=selected_revision.to_dict() if selected_revision else {},
                execution_summary=execution_summary,
                changed_target_hints=list(changed_target_hints or []),
                selected_targets=selected_targets,
                validation_commands=validation_commands,
            )
            if self._execution_host.supports_live_tasks():
                delivery_result = self._delivery.execute_app_generate(
                    session=session,
                    delivery_family=delivery_family,
                    system_parts=system_parts,
                    task=delivery_task,
                    memory_sources=selected_targets,
                    validation_commands=validation_commands,
                    execution_summary=execution_summary,
                    changed_target_hints=list(changed_target_hints or []),
                )
            else:
                delivery_result = self._delivery.bootstrap_app_generate(
                    session=session,
                    delivery_family=delivery_family,
                    validation_commands=validation_commands,
                    execution_summary=execution_summary,
                    changed_target_hints=list(changed_target_hints or []),
                    install_and_build=True,
                )
        else:
            delivery_result = DeliveryExecutionResult(
                execution_summary=execution_summary,
                changed_target_hints=list(changed_target_hints or []),
            )
        artifact_path = delivery_result.artifact_paths[0] if delivery_result.artifact_paths else ""
        self._app_harness.record_execution_attempt(
            session,
            sprint_id=sprint_id,
            execution_mode="live" if use_live_generator else "deterministic",
            execution_summary=delivery_result.execution_summary or execution_summary,
            changed_target_hints=delivery_result.changed_target_hints or changed_target_hints,
            changed_files=delivery_result.changed_files,
            artifact_root=delivery_result.artifact_root,
            artifact_kind=delivery_result.artifact_kind,
            artifact_path=artifact_path,
            preview_command=delivery_result.preview_command,
            trace_path=delivery_result.trace_path,
            validation_command=delivery_result.validation_command,
            validation_summary=delivery_result.validation_summary,
            failure_reason=delivery_result.failure_reason,
        )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_generate"
        payload["task_id"] = task_id
        if use_live_generator:
            payload["app_generator_timeout_seconds"] = int(self._execution_host.live_app_generator_timeout_seconds())
            payload["app_generator_max_completion_tokens"] = int(self._execution_host.live_app_generator_max_completion_tokens())
        return payload

    def app_export(
        self,
        *,
        task_id: str,
        output_dir: str = "",
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        destination = output_dir.strip() or str(
            Path(self._config.repo_root)
            / ".aionis-workbench"
            / "exports"
            / task_id
            / "latest"
        )
        payload = export_latest_app_artifact(
            session=session,
            output_dir=destination,
        )
        payload["task_id"] = task_id
        payload["shell_view"] = "app_export"
        payload["controller_action_bar"] = self._controller_action_bar_for_task(task_id=task_id)
        return payload

    def app_advance(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        self._app_harness.advance_to_next_sprint(
            session,
            sprint_id=sprint_id,
        )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        canonical_views = payload.get("canonical_views")
        if isinstance(canonical_views, dict):
            canonical_views["app_harness"] = self._app_harness.app_state_summary(session)
        payload["shell_view"] = "app_advance"
        payload["task_id"] = task_id
        return payload

    def app_replan(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        note: str = "",
        use_live_planner: bool = False,
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        app_state = session.app_harness_state
        active_sprint = app_state.active_sprint_contract if app_state else None
        if sprint_id and active_sprint and active_sprint.sprint_id != sprint_id:
            self._save_session(session)
            payload = self._surface.inspect_session(task_id=task_id)
            payload["shell_view"] = "app_replan"
            payload["task_id"] = task_id
            return payload
        if use_live_planner:
            selected_sprint = active_sprint
            selected_evaluation = (
                app_state.latest_sprint_evaluation
                if app_state and app_state.latest_sprint_evaluation and selected_sprint and app_state.latest_sprint_evaluation.sprint_id == selected_sprint.sprint_id
                else None
            )
            selected_revision = (
                app_state.latest_revision
                if app_state and app_state.latest_revision and selected_sprint and app_state.latest_revision.sprint_id == selected_sprint.sprint_id
                else None
            )
            selected_execution_attempt = (
                app_state.latest_execution_attempt
                if app_state and app_state.latest_execution_attempt and selected_sprint and app_state.latest_execution_attempt.sprint_id == selected_sprint.sprint_id
                else None
            )
            live_replan = self._execution_host.replan_sprint_live(
                product_spec=app_state.product_spec.to_dict() if app_state and app_state.product_spec else {},
                sprint_contract=selected_sprint.to_dict() if selected_sprint else {},
                latest_evaluation=selected_evaluation.to_dict() if selected_evaluation else {},
                latest_revision=selected_revision.to_dict() if selected_revision else {},
                latest_execution_attempt=selected_execution_attempt.to_dict() if selected_execution_attempt else {},
                execution_focus=_execution_focus_for_live_attempt(
                    selected_execution_attempt.to_dict() if selected_execution_attempt else {}
                ),
                note=note,
            )
            self._app_harness.replan_current_sprint(
                session,
                sprint_id=sprint_id,
                note=str(live_replan.get("replan_note") or note or "").strip(),
                planner_mode="live",
                goal=str(live_replan.get("goal") or "").strip(),
                scope=[str(item).strip() for item in (live_replan.get("scope") or []) if str(item).strip()],
                acceptance_checks=[
                    str(item).strip() for item in (live_replan.get("acceptance_checks") or []) if str(item).strip()
                ],
                done_definition=[
                    str(item).strip() for item in (live_replan.get("done_definition") or []) if str(item).strip()
                ],
            )
        else:
            self._app_harness.replan_current_sprint(
                session,
                sprint_id=sprint_id,
                note=note,
            )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_replan"
        payload["task_id"] = task_id
        if use_live_planner:
            payload["app_replanner_timeout_seconds"] = int(self._execution_host.live_app_planner_timeout_seconds())
            payload["app_replanner_max_completion_tokens"] = int(self._execution_host.live_app_planner_max_completion_tokens())
        return payload

    def app_escalate(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        session = self._load_required_session(task_id=task_id)
        self._app_harness.escalate_current_sprint(
            session,
            sprint_id=sprint_id,
            note=note,
        )
        self._save_session(session)
        payload = self._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_escalate"
        payload["task_id"] = task_id
        return payload

    def evaluate_session(self, *, task_id: str) -> dict[str, Any]:
        return self._surface.evaluate_session(task_id=task_id)

    def validate_session(self, *, task_id: str, learning_source: str = "validate") -> dict[str, Any]:
        return self._surface.validate_session(
            task_id=task_id,
            learning_source=learning_source,
            apply_validation_feedback_fn=self._apply_validation_feedback,
            record_auto_learning_fn=self._record_auto_learning,
        )

    def workflow_next(self, *, task_id: str) -> dict[str, Any]:
        return self._surface.workflow_next(
            task_id=task_id,
            validate_session_fn=self.validate_session,
        )

    def workflow_fix(self, *, task_id: str) -> dict[str, Any]:
        return self._surface.workflow_fix(
            task_id=task_id,
            validate_session_fn=self.validate_session,
        )

    def shell_status(self, *, task_id: str | None = None) -> dict[str, Any]:
        return self._surface.shell_status(task_id=task_id)

    def background_status(self) -> dict[str, Any]:
        return self._ops.background_status()

    def recent_tasks(self, *, limit: int = 8) -> dict[str, Any]:
        return self._ops.recent_tasks(limit=limit)

    def compare_family(self, *, task_id: str, limit: int = 6) -> dict[str, Any]:
        return self._ops.compare_family(task_id=task_id, limit=limit)

    def dashboard(self, *, limit: int = 24, family_limit: int = 8) -> dict[str, Any]:
        return self._ops.dashboard(limit=limit, family_limit=family_limit)

    def consolidate(self, *, limit: int = 48, family_limit: int = 8) -> dict[str, Any]:
        return self._ops.consolidate(limit=limit, family_limit=family_limit)

    def dream(self, *, limit: int = 48, family_limit: int = 8, status_filter: str | None = None) -> dict[str, Any]:
        return self._ops.dream(limit=limit, family_limit=family_limit, status_filter=status_filter)

    def live_profile(self) -> dict[str, Any]:
        provider_profile = resolve_provider_profile()
        snapshot = load_live_profile_snapshot(repo_root=self._config.repo_root)
        snapshot_path = resolve_live_profile_snapshot_path(repo_root=self._config.repo_root)
        snapshot_provider_id = str(snapshot.get("provider_id") or "").strip()
        snapshot_profile = None
        if snapshot_provider_id:
            try:
                snapshot_profile = get_provider_profile(snapshot_provider_id)
            except ValueError:
                snapshot_profile = None
        effective_profile = snapshot_profile or provider_profile
        latest_scenario_id = str(snapshot.get("scenario_id") or "")
        latest_execution_gate_transition = str(snapshot.get("execution_gate_transition") or "")
        latest_last_policy_action = str(snapshot.get("last_policy_action") or "")
        latest_convergence_signal = "none"
        if latest_execution_gate_transition or latest_last_policy_action:
            signal = latest_execution_gate_transition or "none"
            if latest_last_policy_action:
                signal = f"{signal}@{latest_last_policy_action}"
            if latest_scenario_id:
                signal = f"{latest_scenario_id}:{signal}"
            latest_convergence_signal = signal
        recent_convergence_signals = [
            str(item).strip()
            for item in (snapshot.get("recent_convergence_signals") or [])
            if str(item).strip()
        ][:4]
        if not recent_convergence_signals and latest_convergence_signal != "none":
            recent_convergence_signals = [latest_convergence_signal]
        return {
            "shell_view": "live_profile",
            "provider_id": snapshot_provider_id or (effective_profile.provider_id if effective_profile is not None else ""),
            "provider_label": effective_profile.label if effective_profile is not None else "unknown",
            "release_tier": effective_profile.release_tier if effective_profile is not None else "unknown",
            "supports_live": bool(effective_profile.supports_live) if effective_profile is not None else False,
            "model": str(snapshot.get("model") or self._config.model or (effective_profile.model if effective_profile is not None else "")),
            "timeout_seconds": int(
                snapshot.get("timeout_seconds")
                or self._config.model_timeout_seconds
                or (effective_profile.timeout_seconds if effective_profile is not None else 0)
            ),
            "max_completion_tokens": int(
                snapshot.get("max_completion_tokens")
                or self._config.max_completion_tokens
                or (effective_profile.max_completion_tokens if effective_profile is not None else 0)
            ),
            "live_mode": str(snapshot.get("live_mode") or infer_live_mode()),
            "latest_recorded_at": str(snapshot.get("recorded_at") or ""),
            "latest_scenario_id": latest_scenario_id,
            "latest_ready_duration_seconds": float(snapshot.get("ready_duration_seconds") or 0.0),
            "latest_run_duration_seconds": float(snapshot.get("run_duration_seconds") or 0.0),
            "latest_resume_duration_seconds": float(snapshot.get("resume_duration_seconds") or 0.0),
            "latest_total_duration_seconds": float(snapshot.get("total_duration_seconds") or 0.0),
            "latest_timing_summary": str(snapshot.get("timing_summary") or ""),
            "latest_execution_focus": str(snapshot.get("execution_focus") or ""),
            "latest_execution_gate": str(snapshot.get("execution_gate") or ""),
            "latest_execution_gate_transition": latest_execution_gate_transition,
            "latest_execution_outcome_ready": bool(snapshot.get("execution_outcome_ready")) if "execution_outcome_ready" in snapshot else False,
            "latest_last_policy_action": latest_last_policy_action,
            "latest_convergence_signal": latest_convergence_signal,
            "recent_convergence_signals": recent_convergence_signals,
            "latest_profile_path": str(snapshot_path),
            "latest_snapshot": snapshot,
        }

    def ab_test_compare(
        self,
        *,
        task_id: str,
        scenario_id: str,
        baseline_ended_in: str = "",
        baseline_duration_seconds: float = 0.0,
        baseline_retry_count: int = 0,
        baseline_replan_depth: int = 0,
        baseline_convergence_signal: str = "",
        baseline_final_execution_gate: str = "",
        baseline_gate_flow: str = "",
        baseline_notes: list[str] | None = None,
        baseline_advance_reached: bool = False,
        baseline_escalated: bool = False,
    ) -> dict[str, Any]:
        inspect_payload = self._surface.inspect_session(task_id=task_id)
        live_profile_payload = self.live_profile()
        aionis_payload = dict(inspect_payload)
        aionis_payload["live_profile"] = live_profile_payload
        baseline = normalize_baseline_result(
            scenario_id=scenario_id,
            provider_id=str(live_profile_payload.get("provider_id") or ""),
            model=str(live_profile_payload.get("model") or ""),
            thin_loop_result={
                "ended_in": baseline_ended_in,
                "total_duration_seconds": baseline_duration_seconds,
                "retry_count": baseline_retry_count,
                "replan_depth": baseline_replan_depth,
                "latest_convergence_signal": baseline_convergence_signal,
                "final_execution_gate": baseline_final_execution_gate,
                "gate_flow": baseline_gate_flow,
                "notes": list(baseline_notes or []),
                "advance_reached": baseline_advance_reached,
                "escalated": baseline_escalated,
            },
        )
        aionis = benchmark_result_from_aionis_payload(
            scenario_id=scenario_id,
            payload=aionis_payload,
            provider_id=str(live_profile_payload.get("provider_id") or ""),
            model=str(live_profile_payload.get("model") or ""),
        )
        comparison = build_benchmark_comparison(
            scenario_id=scenario_id,
            baseline=baseline,
            aionis=aionis,
        )
        return {
            "shell_view": "ab_test_compare",
            "task_id": task_id,
            "scenario_id": scenario_id,
            "baseline": baseline.to_dict(),
            "aionis": aionis.to_dict(),
            "comparison": comparison.to_dict(),
            "benchmark_summary": comparison.summary,
        }

    def doc_compile(self, *, input_path: str, task_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        doc_kwargs, recording = self._split_doc_recording_kwargs(kwargs)
        payload = self._aionisdoc.compile(input_path=input_path, **doc_kwargs)
        payload.update({key: value for key, value in recording.items() if value})
        return self._surface.persist_doc_result(task_id=task_id, action="compile", doc_input=input_path, payload=payload)

    def doc_run(self, *, input_path: str, registry_path: str, task_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        doc_kwargs, recording = self._split_doc_recording_kwargs(kwargs)
        payload = self._aionisdoc.run(input_path=input_path, registry_path=registry_path, **doc_kwargs)
        payload.update({key: value for key, value in recording.items() if value})
        return self._surface.persist_doc_result(task_id=task_id, action="run", doc_input=input_path, payload=payload)

    def doc_publish(self, *, input_path: str, task_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        doc_kwargs, recording = self._split_doc_recording_kwargs(kwargs)
        doc_kwargs = self._apply_doc_bridge_defaults(input_path=input_path, kwargs=doc_kwargs)
        payload = self._aionisdoc.publish(input_path=input_path, **doc_kwargs)
        payload.update({key: value for key, value in recording.items() if value})
        return self._surface.persist_doc_result(task_id=task_id, action="publish", doc_input=input_path, payload=payload)

    def doc_recover(self, *, input_path: str, task_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        doc_kwargs, recording = self._split_doc_recording_kwargs(kwargs)
        doc_kwargs = self._apply_doc_bridge_defaults(input_path=input_path, kwargs=doc_kwargs)
        payload = self._aionisdoc.recover(input_path=input_path, **doc_kwargs)
        payload.update({key: value for key, value in recording.items() if value})
        return self._surface.persist_doc_result(task_id=task_id, action="recover", doc_input=input_path, payload=payload)

    def doc_resume(self, *, input_path: str, task_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        doc_kwargs, recording = self._split_doc_recording_kwargs(kwargs)
        doc_kwargs = self._apply_doc_bridge_defaults(input_path=input_path, kwargs=doc_kwargs)
        payload = self._aionisdoc.resume(input_path=input_path, **doc_kwargs)
        payload.update({key: value for key, value in recording.items() if value})
        return self._surface.persist_doc_result(task_id=task_id, action="resume", doc_input=input_path, payload=payload)

    def doc_event(self, *, task_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return self._surface.persist_doc_event(task_id=task_id, event=event)

    def doc_list(self, *, limit: int = 24) -> dict[str, Any]:
        rows = list_doc_learning_records(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
            limit=limit,
        )
        enriched_rows: list[dict[str, Any]] = []
        for row in rows:
            enriched = dict(row)
            latest_task_id = str(enriched.get("latest_task_id") or "").strip()
            if latest_task_id:
                enriched["controller_action_bar"] = self._controller_action_bar_for_task(task_id=latest_task_id)
            enriched_rows.append(enriched)
        return {
            "shell_view": "doc_list",
            "repo_root": self._config.repo_root,
            "doc_count": len(enriched_rows),
            "docs": enriched_rows,
        }

    def doc_inspect(self, *, target: str, limit: int = 8) -> dict[str, Any]:
        payload = inspect_doc_target(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
            target=target,
            limit=limit,
        )
        result = {
            "shell_view": "doc_inspect",
            "repo_root": self._config.repo_root,
            **payload,
        }
        latest_record = result.get("latest_record") or {}
        if isinstance(latest_record, dict):
            latest_task_id = str(latest_record.get("task_id") or "").strip()
            if latest_task_id:
                result["controller_action_bar"] = self._controller_action_bar_for_task(task_id=latest_task_id)
        return result

    def _count_new_sessions_since(self, since: datetime | None) -> int:
        sessions_dir = project_session_path(self._config.project_scope, "_placeholder").parent
        if not sessions_dir.exists():
            return 0
        count = 0
        for path in sessions_dir.glob("*.json"):
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if since is None or modified_at > since:
                count += 1
        return count

    @staticmethod
    def _split_doc_recording_kwargs(kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        doc_kwargs: dict[str, Any] = {}
        recording: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key in _DOC_RECORDING_KEYS:
                recording[key] = value
            else:
                doc_kwargs[key] = value
        return doc_kwargs, recording

    def _apply_doc_bridge_defaults(self, *, input_path: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(kwargs)
        if not str(enriched.get("base_url") or "").strip():
            enriched["base_url"] = resolve_aionis_base_url()
        if not str(enriched.get("repo_root") or "").strip():
            enriched["repo_root"] = self._config.repo_root
        input_kind = str(enriched.get("input_kind") or "source").strip() or "source"
        if input_kind == "source" and not str(enriched.get("file_path") or "").strip():
            enriched["file_path"] = self._default_doc_file_path(input_path)
        return enriched

    def _default_doc_file_path(self, input_path: str) -> str:
        path = Path(input_path).expanduser().resolve()
        repo_root = Path(self._config.repo_root).expanduser().resolve()
        try:
            return str(path.relative_to(repo_root))
        except ValueError:
            return f"flows/{path.name}"

    def _maybe_auto_consolidate(self, *, trigger: str, limit: int = 48, family_limit: int = 8) -> dict[str, Any]:
        return self._ops.maybe_auto_consolidate(trigger=trigger, limit=limit, family_limit=family_limit)

    def backfill(self, *, task_id: str, rerun_recovery: bool = False) -> dict[str, Any]:
        return self._surface.backfill(
            task_id=task_id,
            rerun_recovery=rerun_recovery,
            apply_validation_feedback_fn=self._apply_validation_feedback,
            persist_artifacts_fn=self._persist_artifacts,
        )
