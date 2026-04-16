from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .config import AionisConfig, WorkbenchConfig
from .consolidation import build_consolidation_summary
from .consolidation_state import (
    acquire_consolidation_lock,
    consolidation_lock_active,
    load_consolidation_state,
    load_consolidation_summary,
    release_consolidation_lock,
    save_consolidation_state,
    save_consolidation_summary,
)
from .dream_service import DreamService
from .dream_state import load_dream_candidates, load_dream_promotions
from .host_contract import build_unified_host_contract
from .provider_profiles import SAFE_CREDENTIALS_HINT
from .session import (
    SessionState,
    bootstrap_path,
    load_recent_sessions,
    load_session,
    project_bootstrap_path,
    project_session_path,
    session_path,
    session_signal_score,
)


def _session_family(session: SessionState) -> str:
    return (
        session.selected_task_family
        or (session.strategy_summary.task_family if session.strategy_summary else "")
        or str((session.continuity_snapshot or {}).get("task_family") or "")
    )


def _instrumentation_grade(instrumentation) -> tuple[str, str]:
    if not instrumentation:
        return ("unknown", "Instrumentation has not been recorded yet.")
    if not instrumentation.family_hit:
        return ("weak_match", instrumentation.family_reason or "Task family did not match the selected reuse scope.")
    if instrumentation.routed_artifact_hit_rate >= 1.0 and instrumentation.selected_pattern_hit_count > 0:
        return ("strong_match", "Family, pattern reuse, and routed artifacts all aligned with prior successful work.")
    if instrumentation.routed_artifact_hit_rate >= 0.8:
        return ("usable_match", "Family alignment is good and most routed artifacts came from the same family.")
    return ("weak_match", "Family matched, but pattern reuse or routed artifacts were only partially aligned.")


def _family_compare_entry(session: SessionState) -> dict[str, Any]:
    instrumentation = session.instrumentation_summary
    grade, explanation = _instrumentation_grade(instrumentation)
    strategy = session.strategy_summary
    validation = session.last_validation_result or {}
    return {
        "task_id": session.task_id,
        "status": session.status,
        "task_family": _session_family(session),
        "strategy_profile": strategy.strategy_profile if strategy else session.selected_strategy_profile,
        "validation_style": strategy.validation_style if strategy else session.selected_validation_style,
        "trust_signal": strategy.trust_signal if strategy else session.selected_trust_signal,
        "instrumentation_status": grade,
        "instrumentation_explanation": explanation,
        "pattern_hit_count": instrumentation.selected_pattern_hit_count if instrumentation else 0,
        "pattern_miss_count": instrumentation.selected_pattern_miss_count if instrumentation else 0,
        "artifact_hit_rate": instrumentation.routed_artifact_hit_rate if instrumentation else 0.0,
        "same_family_task_ids": instrumentation.routed_same_family_task_ids[:6] if instrumentation else [],
        "other_family_task_ids": instrumentation.routed_other_family_task_ids[:6] if instrumentation else [],
        "validation_ok": validation.get("ok"),
        "validation_summary": validation.get("summary"),
    }


def _dashboard_recent_sessions(repo_root: str, project_scope: str, limit: int) -> list[SessionState]:
    candidate_dirs = [
        project_session_path(project_scope, "_placeholder").parent,
        session_path(repo_root, "_placeholder").parent,
    ]
    seen_task_ids: set[str] = set()
    loaded: list[tuple[float, SessionState]] = []
    for sessions_dir in candidate_dirs:
        if not sessions_dir.exists():
            continue
        for path in sessions_dir.glob("*.json"):
            if path.stem in seen_task_ids:
                continue
            session = load_session(repo_root, path.stem, project_scope=project_scope)
            if session is None:
                continue
            if session_signal_score(session) <= 0:
                continue
            seen_task_ids.add(path.stem)
            loaded.append((path.stat().st_mtime, session))
    loaded.sort(key=lambda item: item[0], reverse=True)
    return [session for _, session in loaded[:limit]]


def _dashboard_family_trend(entries: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    if not entries:
        return ("unknown", "No recent sessions were available for this family.", [])
    recent_statuses = [str(item["instrumentation_status"]) for item in entries[:5]]
    score_map = {"weak_match": 0, "usable_match": 1, "strong_match": 2}
    recent_scores = [score_map.get(item["instrumentation_status"], 0) for item in entries[:3]]
    older_scores = [score_map.get(item["instrumentation_status"], 0) for item in entries[3:6]]
    if not older_scores:
        if all(score == 2 for score in recent_scores):
            return ("stable", "Recent sessions in this family are already landing as strong matches.", recent_statuses)
        return ("emerging", "This family has only a small recent sample, so trend is still forming.", recent_statuses)
    recent_avg = sum(recent_scores) / len(recent_scores)
    older_avg = sum(older_scores) / len(older_scores)
    if recent_avg > older_avg + 0.34:
        return ("improving", "The recent slice is stronger than the preceding slice for this family.", recent_statuses)
    if recent_avg < older_avg - 0.34:
        return ("regressing", "The recent slice is weaker than the preceding slice for this family.", recent_statuses)
    if all(score == 2 for score in recent_scores):
        return ("stable", "Recent sessions in this family remain consistently strong.", recent_statuses)
    return ("flat", "Recent sessions in this family are roughly holding their current quality level.", recent_statuses)


def _dashboard_family_entry(task_family: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    strong = sum(1 for item in entries if item["instrumentation_status"] == "strong_match")
    usable = sum(1 for item in entries if item["instrumentation_status"] == "usable_match")
    weak = sum(1 for item in entries if item["instrumentation_status"] == "weak_match")
    artifact_rates = [float(item["artifact_hit_rate"]) for item in entries]
    pattern_hits = [int(item["pattern_hit_count"]) for item in entries]
    strategy_profiles = list(dict.fromkeys(item["strategy_profile"] for item in entries if item["strategy_profile"]))[:4]
    trust_signals = list(dict.fromkeys(item["trust_signal"] for item in entries if item["trust_signal"]))[:4]
    sample_tasks = [item["task_id"] for item in entries[:6]]
    avg_artifact_hit_rate = round(sum(artifact_rates) / len(artifact_rates), 3) if artifact_rates else 0.0
    avg_pattern_hits = round(sum(pattern_hits) / len(pattern_hits), 2) if pattern_hits else 0.0
    trend_status, trend_explanation, recent_statuses = _dashboard_family_trend(entries)
    if strong == len(entries):
        status = "strong_family"
        explanation = "Recent sessions in this family are consistently reusing same-family patterns and routed artifacts."
    elif strong + usable == len(entries):
        status = "stable_family"
        explanation = "Recent sessions in this family are mostly reusing the right prior evidence."
    else:
        status = "mixed_family"
        explanation = "This family still shows uneven reuse quality across recent sessions."
    return {
        "task_family": task_family,
        "status": status,
        "explanation": explanation,
        "session_count": len(entries),
        "strong_match_count": strong,
        "usable_match_count": usable,
        "weak_match_count": weak,
        "avg_artifact_hit_rate": avg_artifact_hit_rate,
        "avg_pattern_hit_count": avg_pattern_hits,
        "strategy_profiles": strategy_profiles,
        "trust_signals": trust_signals,
        "sample_tasks": sample_tasks,
        "trend_status": trend_status,
        "trend_explanation": trend_explanation,
        "recent_statuses": recent_statuses,
    }


def _prior_seed_summary(prior: dict[str, Any]) -> str:
    if not isinstance(prior, dict) or not prior:
        return "no consolidated prior is available for this family yet"
    seed_ready = bool(prior.get("seed_ready"))
    confidence = float(prior.get("confidence") or 0.0)
    sample_count = int(prior.get("sample_count") or prior.get("session_count") or 0)
    gate = str(prior.get("seed_gate") or ("ready" if seed_ready else "unknown"))
    recommendation = str(prior.get("seed_recommendation") or "").strip()
    reason = str(prior.get("seed_reason") or "").strip()
    if seed_ready:
        return f"seed-ready prior with confidence {confidence:.2f} across {sample_count} samples"
    if recommendation:
        return f"seed blocked at {gate}; {recommendation}"
    if reason:
        return f"seed blocked at {gate}; {reason}"
    return f"seed blocked at {gate}"


def _dashboard_proof_summary(
    *,
    session_count: int,
    prior_seed_ready_count: int,
    prior_seed_blocked_count: int,
    doc_prior_ready_count: int,
    doc_editor_sync_event_count: int,
    blocked_family_recommendations: list[dict[str, Any]],
) -> str:
    if session_count <= 0:
        return "no recent sessions yet, so reuse proof has not formed"
    if doc_prior_ready_count > 0 and doc_editor_sync_event_count > 0:
        return "recent families already have seed-ready priors, and editor-driven doc reuse is live"
    if prior_seed_ready_count > 0 and prior_seed_blocked_count <= 0:
        return "recent families already have seed-ready priors, so reuse proof is live"
    if prior_seed_ready_count > 0:
        return "some families are seed-ready, but blocked priors still need strengthening"
    if blocked_family_recommendations:
        top = blocked_family_recommendations[0]
        family = str(top.get("task_family") or "task:unknown")
        gate = str(top.get("gate") or "unknown")
        return f"reuse signals exist, but no family prior is seed-ready yet; top blocker is {family} at {gate}"
    return "reuse signals exist, but no family prior is seed-ready yet"


def _dream_priority(status: str) -> int:
    return {
        "seed_ready": 3,
        "trial": 2,
        "candidate": 1,
        "deprecated": 0,
    }.get(status, -1)


def _select_best_dream_promotion(promotions: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        promotions,
        key=lambda item: (
            _dream_priority(str(item.get("promotion_status") or "")),
            float(item.get("confidence") or 0.0),
            int(item.get("sample_count") or 0),
        ),
        reverse=True,
    )
    return ranked[0] if ranked else {}


def _dream_status_priority(status: str) -> int:
    return {
        "seed_ready": 3,
        "trial": 2,
        "candidate": 1,
        "deprecated": 0,
    }.get(status, -1)


def _normalize_dream_status_filter(status_filter: str | None) -> str:
    normalized = str(status_filter or "").strip().lower()
    if normalized in {"seed_ready", "trial", "candidate", "deprecated"}:
        return normalized
    return "all"


class OpsService:
    def __init__(
        self,
        *,
        workbench_config: WorkbenchConfig,
        aionis_config: AionisConfig,
        execution_host,
        runtime_host,
        save_session_fn: Callable[[SessionState], Any],
    ) -> None:
        self._config = workbench_config
        self._aionis = aionis_config
        self._execution_host = execution_host
        self._runtime_host = runtime_host
        self._save_session = save_session_fn
        self._dream = DreamService(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )

    def host_contract(self) -> dict[str, Any]:
        contract = build_unified_host_contract(
            workbench_config=self._config,
            aionis_config=self._aionis,
            execution_host_description=self._execution_host.describe(),
            runtime_host_description=self._runtime_host.describe(),
        ).to_dict()
        return {
            "project_identity": self._config.project_identity,
            "project_scope": self._config.project_scope,
            "shell_view": "hosts",
            "recommended_entrypoint": f"aionis --repo-root {self._config.repo_root}",
            "contract": contract,
            "background": self.background_status(),
        }

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
        host_payload = self.host_contract()
        contract = host_payload.get("contract") or {}
        execution_host = contract.get("execution_host") or {}
        runtime_host = contract.get("runtime_host") or {}
        repo_root_path = Path(self._config.repo_root)
        local_bootstrap = bootstrap_path(self._config.repo_root)
        scoped_bootstrap = project_bootstrap_path(self._config.project_scope)
        repo_exists = repo_root_path.exists()
        git_present = (repo_root_path / ".git").exists()
        bootstrap_exists = local_bootstrap.exists() or scoped_bootstrap.exists()
        execution_health = str(execution_host.get("health_status") or "unknown")
        runtime_health = str(runtime_host.get("health_status") or "unknown")
        live_ready = execution_health == "available" and runtime_health == "available"
        mode = "live" if live_ready else "inspect-only"
        execution_reason = str(execution_host.get("health_reason") or "")
        runtime_reason = str(runtime_host.get("health_reason") or "")

        if live_ready:
            capability_state = "live_ready"
            capability_summary = "can run live tasks, inspect, validate, and ingest"
        elif execution_reason == "model_credentials_missing" and runtime_reason == "runtime_health_unreachable":
            capability_state = "inspect_only_missing_credentials_and_runtime"
            capability_summary = "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime"
        elif execution_reason == "model_credentials_missing":
            capability_state = "inspect_only_missing_credentials"
            capability_summary = "can inspect, validate, and ingest; live tasks blocked by missing credentials"
        elif runtime_reason == "runtime_health_unreachable":
            capability_state = "inspect_only_missing_runtime"
            capability_summary = "can inspect, validate, and ingest; live tasks blocked by runtime availability"
        else:
            capability_state = "inspect_only_degraded"
            capability_summary = "can inspect, validate, and ingest; live tasks are currently degraded"
        live_ready_summary = {
            "live_ready": "live-ready",
            "inspect_only_missing_credentials": "inspect-only: missing credentials",
            "inspect_only_missing_runtime": "inspect-only: missing runtime",
            "inspect_only_missing_credentials_and_runtime": "inspect-only: missing credentials + runtime",
            "inspect_only_degraded": "inspect-only: degraded",
        }.get(capability_state, mode)
        recovery_summary = self._live_recovery_summary(
            capability_state=capability_state,
            execution_reason=execution_reason,
            runtime_reason=runtime_reason,
        )

        checks = [
            {
                "name": "repo_root",
                "status": "available" if repo_exists else "missing",
                "reason": str(repo_root_path) if repo_exists else "repo_root_missing",
            },
            {
                "name": "git",
                "status": "available" if git_present else "missing",
                "reason": ".git detected" if git_present else "git_metadata_missing",
            },
            {
                "name": "bootstrap",
                "status": "available" if bootstrap_exists else "missing",
                "reason": str(local_bootstrap if local_bootstrap.exists() else scoped_bootstrap) if bootstrap_exists else "bootstrap_missing",
            },
            {
                "name": "execution_host",
                "status": execution_health,
                "reason": execution_reason or execution_host.get("mode") or "unknown",
            },
            {
                "name": "runtime_host",
                "status": runtime_health,
                "reason": runtime_reason or runtime_host.get("replay_mode") or "unknown",
            },
        ]

        recommendations: list[str] = []
        if not bootstrap_exists:
            recommendations.append(f"run `aionis init --repo-root {self._config.repo_root}` to create bootstrap state")
        if execution_host.get("health_reason") == "model_credentials_missing":
            recommendations.append("configure model credentials to enable live execution")
        if runtime_host.get("health_reason") == "runtime_health_unreachable":
            recommendations.append("start or configure Aionis Runtime via AIONIS_BASE_URL")
        if not live_ready:
            recommendations.append("use inspect-only workflow via /plan, /work, /review, /validate, or /ingest")

        setup_checklist = [
            {
                "name": "bootstrap_initialized",
                "status": "done" if bootstrap_exists else "pending",
                "reason": "bootstrap ready" if bootstrap_exists else "bootstrap missing",
                "next_step": (
                    "bootstrap already initialized"
                    if bootstrap_exists
                    else "initialize bootstrap state for this repo"
                ),
                "command_hint": (
                    ""
                    if bootstrap_exists
                    else f"aionis init --repo-root {self._config.repo_root}"
                ),
            },
            {
                "name": "credentials_configured",
                "status": "done" if execution_reason != "model_credentials_missing" else "pending",
                "reason": execution_reason or "credentials configured",
                "next_step": (
                    "model credentials are configured"
                    if execution_reason != "model_credentials_missing"
                    else "configure model credentials for live execution"
                ),
                "command_hint": (
                    ""
                    if execution_reason != "model_credentials_missing"
                    else SAFE_CREDENTIALS_HINT
                ),
            },
            {
                "name": "runtime_available",
                "status": "done" if runtime_health == "available" else "pending",
                "reason": runtime_reason or ("runtime available" if runtime_health == "available" else "runtime not ready"),
                "next_step": (
                    "runtime is reachable"
                    if runtime_health == "available"
                    else (
                        "configure AIONIS_BASE_URL for the runtime"
                        if not self._aionis.base_url
                        else "start or restore the configured Aionis Runtime"
                    )
                ),
                "command_hint": (
                    ""
                    if runtime_health == "available"
                    else (
                        "export AIONIS_BASE_URL=http://127.0.0.1:3101"
                        if not self._aionis.base_url
                        else f"curl -fsS {self._aionis.base_url.rstrip('/')}/health"
                    )
                ),
            },
        ]

        payload = {
            "shell_view": "doctor",
            "project_identity": self._config.project_identity,
            "project_scope": self._config.project_scope,
            "repo_root": self._config.repo_root,
            "mode": mode,
            "live_ready": live_ready,
            "live_ready_summary": live_ready_summary,
            "recovery_summary": recovery_summary,
            "capability_state": capability_state,
            "capabilities": {
                "can_run_live_tasks": live_ready,
                "can_inspect": True,
                "can_validate": True,
                "can_ingest": True,
                "execution_health": execution_health,
                "runtime_health": runtime_health,
            },
            "capability_summary": capability_summary,
            "setup_checklist": setup_checklist,
            "checks": checks,
            "recommendations": recommendations,
            "host_contract": contract,
        }
        if check:
            named = str(check).strip()
            checklist_match = next(
                (
                    item
                    for item in setup_checklist
                    if isinstance(item, dict) and str(item.get("name") or "") == named
                ),
                None,
            )
            checks_match = next(
                (
                    item
                    for item in checks
                    if isinstance(item, dict) and str(item.get("name") or "") == named
                ),
                None,
            )
            matched = checklist_match or checks_match
            return {
                "shell_view": "doctor_check",
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
                "mode": mode,
                "live_ready": live_ready,
                "live_ready_summary": live_ready_summary,
                "recovery_summary": recovery_summary,
                "capability_state": capability_state,
                "check_name": named,
                "found": matched is not None,
                "source": "setup_checklist" if checklist_match else ("checks" if checks_match else "unknown"),
                "item": matched or {},
                "available_checks": [item["name"] for item in setup_checklist] + [item["name"] for item in checks],
                "recommendations": recommendations,
                "host_contract": contract,
            }
        if summary or one_line:
            summary_payload = {
                "shell_view": "doctor_summary",
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
                "mode": mode,
                "live_ready": live_ready,
                "live_ready_summary": live_ready_summary,
                "recovery_summary": recovery_summary,
                "capability_state": capability_state,
                "capability_summary": capability_summary,
                "pending_checklist_count": sum(1 for item in setup_checklist if item.get("status") == "pending"),
                "recommendation": recommendations[0] if recommendations else "",
                "host_contract": contract,
            }
            if one_line:
                summary_payload["shell_view"] = "doctor_one_line"
                summary_payload["summary_line"] = self._doctor_summary_line(
                    live_ready_summary=live_ready_summary,
                    pending_checklist_count=int(summary_payload["pending_checklist_count"]),
                    recovery_summary=recovery_summary,
                    recommendation=str(summary_payload["recommendation"] or ""),
                )
            return summary_payload
        return payload

    def setup(
        self,
        *,
        pending_only: bool = False,
        summary: bool = False,
        check: str | None = None,
        one_line: bool = False,
    ) -> dict[str, Any]:
        doctor_payload = self.doctor()
        checklist = doctor_payload.get("setup_checklist") or []
        pending_items = [
            item
            for item in checklist
            if isinstance(item, dict) and item.get("status") == "pending"
        ]
        completed_items = [
            item
            for item in checklist
            if isinstance(item, dict) and item.get("status") == "done"
        ]
        next_steps = [
            str(item.get("command_hint") or item.get("next_step") or "").strip()
            for item in pending_items
            if str(item.get("command_hint") or item.get("next_step") or "").strip()
        ]
        if not next_steps:
            next_steps = ["start the Aionis shell and begin with /plan or /work"]
        visible_pending_items = pending_items
        visible_completed_items = [] if pending_only else completed_items
        payload = {
            "shell_view": "setup",
            "project_identity": doctor_payload.get("project_identity"),
            "project_scope": doctor_payload.get("project_scope"),
            "repo_root": doctor_payload.get("repo_root"),
            "mode": doctor_payload.get("mode"),
            "live_ready": doctor_payload.get("live_ready"),
            "live_ready_summary": doctor_payload.get("live_ready_summary"),
            "recovery_summary": doctor_payload.get("recovery_summary"),
            "capability_state": doctor_payload.get("capability_state"),
            "capability_summary": doctor_payload.get("capability_summary"),
            "pending_only": pending_only,
            "pending_count": len(pending_items),
            "completed_count": len(completed_items),
            "pending_items": visible_pending_items,
            "completed_items": visible_completed_items,
            "next_steps": next_steps,
            "recommendations": doctor_payload.get("recommendations") or [],
            "host_contract": doctor_payload.get("host_contract") or {},
        }
        if check:
            named = str(check).strip()
            matched = next(
                (
                    item
                    for item in checklist
                    if isinstance(item, dict) and str(item.get("name") or "") == named
                ),
                None,
            )
            return {
                "shell_view": "setup_check",
                "project_identity": doctor_payload.get("project_identity"),
                "project_scope": doctor_payload.get("project_scope"),
                "repo_root": doctor_payload.get("repo_root"),
                "mode": doctor_payload.get("mode"),
                "live_ready": doctor_payload.get("live_ready"),
                "live_ready_summary": doctor_payload.get("live_ready_summary"),
                "recovery_summary": doctor_payload.get("recovery_summary"),
                "capability_state": doctor_payload.get("capability_state"),
                "check_name": named,
                "found": matched is not None,
                "item": matched or {},
                "available_checks": [item["name"] for item in checklist],
                "host_contract": doctor_payload.get("host_contract") or {},
            }
        if summary or one_line:
            summary_payload = {
                "shell_view": "setup_summary",
                "project_identity": doctor_payload.get("project_identity"),
                "project_scope": doctor_payload.get("project_scope"),
                "repo_root": doctor_payload.get("repo_root"),
                "mode": doctor_payload.get("mode"),
                "live_ready": doctor_payload.get("live_ready"),
                "live_ready_summary": doctor_payload.get("live_ready_summary"),
                "recovery_summary": doctor_payload.get("recovery_summary"),
                "capability_state": doctor_payload.get("capability_state"),
                "capability_summary": doctor_payload.get("capability_summary"),
                "pending_only": pending_only,
                "pending_count": len(pending_items),
                "completed_count": len(completed_items),
                "next_step": next_steps[0] if next_steps else "",
                "host_contract": doctor_payload.get("host_contract") or {},
            }
            if one_line:
                summary_payload["shell_view"] = "setup_one_line"
                summary_payload["summary_line"] = self._setup_summary_line(
                    live_ready_summary=str(summary_payload.get("live_ready_summary") or ""),
                    pending_count=int(summary_payload["pending_count"]),
                    recovery_summary=str(summary_payload.get("recovery_summary") or ""),
                    next_step=str(summary_payload.get("next_step") or ""),
                )
            return summary_payload
        return payload

    def background_status(self) -> dict[str, Any]:
        state = load_consolidation_state(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        summary = load_consolidation_summary(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        lock_active = consolidation_lock_active(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        if not self._config.auto_consolidation_enabled:
            status = "disabled"
        elif lock_active:
            status = "running"
        elif isinstance(state.get("last_status"), str) and state.get("last_status"):
            status = str(state.get("last_status"))
        elif summary:
            status = "completed"
        else:
            status = "idle"

        reason = str(state.get("last_reason") or "").strip()
        status_line = status
        if status == "skipped" and reason:
            status_line = f"skipped:{reason}"
        return {
            "shell_view": "background",
            "project_scope": self._config.project_scope,
            "status": status,
            "status_line": status_line,
            "lock_active": lock_active,
            "enabled": self._config.auto_consolidation_enabled,
            "last_trigger": state.get("last_trigger"),
            "last_reason": reason or None,
            "last_attempted_at": state.get("last_attempted_at"),
            "last_completed_at": state.get("last_completed_at"),
            "last_new_session_count": state.get("last_new_session_count"),
            "summary": {
                "sessions_reviewed": summary.get("sessions_reviewed", 0),
                "families_reviewed": summary.get("families_reviewed", 0),
                "patterns_merged": summary.get("patterns_merged", 0),
                "patterns_suppressed": summary.get("patterns_suppressed", 0),
                "continuity_cleaned": summary.get("continuity_cleaned", 0),
            },
            "consolidation_path": str(summary.get("consolidation_path") or ""),
        }

    def recent_tasks(self, *, limit: int = 8) -> dict[str, Any]:
        recent = load_recent_sessions(
            self._config.repo_root,
            project_scope=self._config.project_scope,
            exclude_task_id=None,
            limit=limit,
        )
        rows: list[dict[str, Any]] = []
        for index, session in enumerate(recent, start=1):
            session.repo_root = self._config.repo_root
            self._save_session(session)
            entry = _family_compare_entry(session)
            continuity = dict(session.continuity_snapshot or {})
            doc_workflow = continuity.get("doc_workflow")
            doc_workflow = dict(doc_workflow) if isinstance(doc_workflow, dict) else {}
            rows.append(
                {
                    "index": index,
                    "task_id": entry["task_id"],
                    "task_family": entry["task_family"],
                    "status": entry["status"],
                    "strategy_profile": entry["strategy_profile"],
                    "instrumentation_status": entry["instrumentation_status"],
                    "validation_ok": entry["validation_ok"],
                    "doc_input": str(doc_workflow.get("doc_input") or "").strip(),
                    "source_doc_id": str(doc_workflow.get("source_doc_id") or "").strip(),
                    "latest_doc_action": str(doc_workflow.get("latest_action") or "").strip(),
                }
            )
        return {
            "project_identity": self._config.project_identity,
            "project_scope": self._config.project_scope,
            "task_count": len(rows),
            "tasks": rows,
        }

    def compare_family(self, *, task_id: str, limit: int = 6) -> dict[str, Any]:
        session = load_session(self._config.repo_root, task_id, project_scope=self._config.project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._config.repo_root
        anchor_path = self._save_session(session)
        anchor_family = _session_family(session)

        peers: list[dict[str, Any]] = []
        recent = load_recent_sessions(
            self._config.repo_root,
            project_scope=self._config.project_scope,
            exclude_task_id=session.task_id,
            limit=24,
        )
        for prior in recent:
            prior.repo_root = self._config.repo_root
            if _session_family(prior) != anchor_family:
                continue
            self._save_session(prior)
            peers.append(_family_compare_entry(prior))
            if len(peers) >= limit:
                break

        anchor_entry = _family_compare_entry(session)
        same_count = sum(1 for item in peers if item["instrumentation_status"] == "strong_match")
        usable_count = sum(1 for item in peers if item["instrumentation_status"] == "usable_match")
        weak_count = sum(1 for item in peers if item["instrumentation_status"] == "weak_match")
        background = self.background_status()
        consolidation_summary = load_consolidation_summary(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        family_prior = next(
            (
                row
                for row in consolidation_summary.get("family_rows", [])
                if isinstance(row, dict) and row.get("task_family") == anchor_family
            ),
            {},
        )

        return {
            "session_path": str(anchor_path),
            "task_id": session.task_id,
            "task_family": anchor_family,
            "anchor": anchor_entry,
            "peer_count": len(peers),
            "peer_summary": {
                "strong_match_count": same_count,
                "usable_match_count": usable_count,
                "weak_match_count": weak_count,
            },
            "peers": peers,
            "background": background,
            "family_prior": family_prior,
            "prior_seed_summary": _prior_seed_summary(family_prior),
        }

    def dashboard(self, *, limit: int = 24, family_limit: int = 8) -> dict[str, Any]:
        recent = _dashboard_recent_sessions(
            self._config.repo_root,
            self._config.project_scope,
            max(limit, family_limit),
        )
        entries: list[dict[str, Any]] = []
        for session in recent:
            session.repo_root = self._config.repo_root
            self._save_session(session)
            entry = _family_compare_entry(session)
            entries.append(entry)

        family_buckets: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            family = str(entry.get("task_family") or "task:unknown")
            family_buckets.setdefault(family, []).append(entry)

        family_rows = [
            _dashboard_family_entry(task_family, bucket)
            for task_family, bucket in family_buckets.items()
        ]
        consolidation_summary = load_consolidation_summary(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        consolidated_family_rows = consolidation_summary.get("family_rows", [])
        if not isinstance(consolidated_family_rows, list):
            consolidated_family_rows = []
        consolidated_family_map = {
            str(row.get("task_family") or ""): row
            for row in consolidated_family_rows
            if isinstance(row, dict) and str(row.get("task_family") or "").strip()
        }
        known_families = {str(item.get("task_family") or "") for item in family_rows if isinstance(item, dict)}
        for task_family, prior in consolidated_family_map.items():
            if task_family in known_families:
                continue
            family_rows.append(
                {
                    "task_family": task_family,
                    "status": "prior_only",
                    "explanation": "No recent sessions were scored, but a consolidated prior already exists for this family.",
                    "session_count": 0,
                    "strong_match_count": 0,
                    "usable_match_count": 0,
                    "weak_match_count": 0,
                    "avg_artifact_hit_rate": 0.0,
                    "avg_pattern_hit_count": 0.0,
                    "strategy_profiles": [],
                    "trust_signals": [],
                    "sample_tasks": [],
                    "trend_status": "prior_only",
                    "trend_explanation": "This family is being surfaced from consolidation rather than recent instrumentation.",
                    "recent_statuses": [],
                }
            )
        for item in family_rows:
            prior = consolidated_family_map.get(str(item.get("task_family") or ""))
            if prior:
                item["prior_seed_ready"] = bool(prior.get("seed_ready"))
                item["prior_seed_gate"] = str(prior.get("seed_gate") or "")
                item["prior_seed_reason"] = str(prior.get("seed_reason") or "")
                item["prior_seed_recommendation"] = str(prior.get("seed_recommendation") or "")
                item["prior_dream_reason"] = str(
                    prior.get("dream_promotion_reason")
                    or prior.get("dream_verification_summary")
                    or ""
                ).strip()
                item["prior_confidence"] = float(prior.get("confidence") or 0.0)
                item["prior_seed_summary"] = _prior_seed_summary(prior)
                doc_prior = prior.get("family_doc_prior") or {}
                item["prior_doc_seed_ready"] = bool(doc_prior.get("seed_ready"))
                item["prior_doc_sample_count"] = int(doc_prior.get("sample_count") or 0)
                item["prior_doc_source_doc_id"] = str(
                    doc_prior.get("dominant_source_doc_id")
                    or doc_prior.get("dominant_doc_input")
                    or ""
                ).strip()
                item["prior_doc_action"] = str(doc_prior.get("dominant_action") or "").strip()
                item["prior_doc_event_source"] = str(doc_prior.get("dominant_event_source") or "").strip()
                item["prior_doc_recorded_at"] = str(doc_prior.get("latest_recorded_at") or "").strip()
                item["prior_doc_editor_sync_count"] = int(doc_prior.get("editor_sync_count") or 0)
            else:
                item["prior_seed_ready"] = False
                item["prior_seed_gate"] = "unavailable"
                item["prior_seed_reason"] = "no consolidated prior is available for this family"
                item["prior_seed_recommendation"] = "run more successful tasks in this family and consolidate again"
                item["prior_dream_reason"] = ""
                item["prior_confidence"] = 0.0
                item["prior_seed_summary"] = "no consolidated prior is available for this family yet"
                item["prior_doc_seed_ready"] = False
                item["prior_doc_sample_count"] = 0
                item["prior_doc_source_doc_id"] = ""
                item["prior_doc_action"] = ""
                item["prior_doc_event_source"] = ""
                item["prior_doc_recorded_at"] = ""
                item["prior_doc_editor_sync_count"] = 0
        family_rows.sort(
            key=lambda item: (
                {"strong_family": 2, "stable_family": 1, "mixed_family": 0, "prior_only": -1}.get(item["status"], -2),
                item["session_count"],
                item["avg_artifact_hit_rate"],
            ),
            reverse=True,
        )
        family_rows = family_rows[:family_limit]

        totals = {
            "session_count": len(entries),
            "family_count": len(family_buckets),
            "strong_match_count": sum(1 for item in entries if item["instrumentation_status"] == "strong_match"),
            "usable_match_count": sum(1 for item in entries if item["instrumentation_status"] == "usable_match"),
            "weak_match_count": sum(1 for item in entries if item["instrumentation_status"] == "weak_match"),
            "prior_seed_ready_count": sum(1 for item in family_rows if item.get("prior_seed_ready")),
            "prior_seed_blocked_count": sum(1 for item in family_rows if not item.get("prior_seed_ready")),
            "doc_prior_ready_count": sum(
                1
                for item in family_rows
                if item.get("prior_doc_sample_count", 0) > 0 and item.get("prior_doc_seed_ready")
            ),
            "doc_prior_blocked_count": sum(
                1
                for item in family_rows
                if item.get("prior_doc_sample_count", 0) > 0 and not item.get("prior_doc_seed_ready")
            ),
            "doc_editor_sync_family_count": sum(
                1 for item in family_rows if int(item.get("prior_doc_editor_sync_count", 0) or 0) > 0
            ),
            "doc_editor_sync_event_count": sum(
                int(item.get("prior_doc_editor_sync_count", 0) or 0) for item in family_rows
            ),
        }
        top_editor_sync = next(
            (
                item
                for item in family_rows
                if int(item.get("prior_doc_editor_sync_count", 0) or 0) > 0
            ),
            {},
        )
        totals["top_doc_editor_sync_family"] = str(top_editor_sync.get("task_family") or "").strip()
        totals["top_doc_editor_sync_source"] = str(top_editor_sync.get("prior_doc_event_source") or "").strip()
        totals["top_doc_editor_sync_at"] = str(top_editor_sync.get("prior_doc_recorded_at") or "").strip()
        blocked = [item for item in family_rows if not item.get("prior_seed_ready")]
        totals["blocked_family_recommendations"] = [
            {
                "task_family": str(item.get("task_family") or "task:unknown"),
                "gate": str(item.get("prior_seed_gate") or "unknown"),
                "recommendation": str(item.get("prior_seed_recommendation") or ""),
                "reason": str(item.get("prior_dream_reason") or item.get("prior_seed_reason") or ""),
            }
            for item in blocked[:3]
        ]
        totals["proof_summary"] = _dashboard_proof_summary(
            session_count=totals["session_count"],
            prior_seed_ready_count=totals["prior_seed_ready_count"],
            prior_seed_blocked_count=totals["prior_seed_blocked_count"],
            doc_prior_ready_count=totals["doc_prior_ready_count"],
            doc_editor_sync_event_count=totals["doc_editor_sync_event_count"],
            blocked_family_recommendations=totals["blocked_family_recommendations"],
        )
        background = self.background_status()

        return {
            "project_identity": self._config.project_identity,
            "project_scope": self._config.project_scope,
            "dashboard_summary": {
                "status": "ready" if entries else "empty",
                "explanation": (
                    "Recent project sessions have been grouped by task family and scored by reuse quality."
                    if entries
                    else "No recent sessions were found for this project scope."
                ),
                **totals,
            },
            "family_rows": family_rows,
            "recent_sessions": entries[: min(len(entries), 12)],
            "background": background,
        }

    def consolidate(self, *, limit: int = 48, family_limit: int = 8) -> dict[str, Any]:
        lock = acquire_consolidation_lock(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        try:
            payload = build_consolidation_summary(
                repo_root=self._config.repo_root,
                project_scope=self._config.project_scope,
                limit=limit,
                family_limit=family_limit,
            )
            dream_payload = self._dream.run_cycle(limit=limit)
            dream_summary = dream_payload.get("summary") or {}
            promotions = dream_payload.get("promotions") or []
            if isinstance(promotions, list):
                promotion_map: dict[str, dict[str, Any]] = {}
                for item in promotions:
                    if not hasattr(item, "task_family"):
                        continue
                    family = str(getattr(item, "task_family", "") or "").strip()
                    if not family:
                        continue
                    promotion_map.setdefault(family, []).append(
                        {
                            "promotion_status": str(getattr(item, "promotion_status", "") or ""),
                            "confidence": float(getattr(item, "confidence", 0.0) or 0.0),
                            "sample_count": int(getattr(item, "sample_count", 0) or 0),
                            "verification_summary": str(getattr(item, "verification_summary", "") or ""),
                            "promotion_reason": str(getattr(item, "promotion_reason", "") or ""),
                        }
                    )
                for row in payload.get("family_rows") or []:
                    if not isinstance(row, dict):
                        continue
                    family = str(row.get("task_family") or "")
                    best = _select_best_dream_promotion(promotion_map.get(family, []))
                    if not best:
                        continue
                    row["dream_promotion_status"] = best.get("promotion_status")
                    row["dream_confidence"] = best.get("confidence")
                    row["dream_sample_count"] = best.get("sample_count")
                    row["dream_verification_summary"] = best.get("verification_summary")
                    row["dream_promotion_reason"] = best.get("promotion_reason")
            payload["dream_summary"] = dream_summary
            payload["dream_candidate_path"] = dream_payload.get("candidate_path")
            payload["dream_project_candidate_path"] = dream_payload.get("project_candidate_path")
            payload["dream_promotion_path"] = dream_payload.get("promotion_path")
            payload["dream_project_promotion_path"] = dream_payload.get("project_promotion_path")
            local_path, project_path = save_consolidation_summary(
                repo_root=self._config.repo_root,
                project_scope=self._config.project_scope,
                payload=payload,
            )
            payload["shell_view"] = "consolidate"
            payload["consolidation_path"] = str(local_path)
            payload["project_consolidation_path"] = str(project_path)
            payload["lock_started_at"] = lock.started_at
            return payload
        finally:
            release_consolidation_lock(lock)

    def dream(self, *, limit: int = 48, family_limit: int = 8, status_filter: str | None = None) -> dict[str, Any]:
        payload = self.consolidate(limit=limit, family_limit=family_limit)
        normalized_filter = _normalize_dream_status_filter(status_filter)
        candidate_state = load_dream_candidates(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        promotion_state = load_dream_promotions(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        candidates = candidate_state.get("candidates", [])
        promotions = promotion_state.get("promotions", [])
        if not isinstance(candidates, list):
            candidates = []
        if not isinstance(promotions, list):
            promotions = []
        sorted_promotions = sorted(
            [item for item in promotions if isinstance(item, dict)],
            key=lambda item: (
                _dream_status_priority(str(item.get("promotion_status") or "")),
                float(item.get("confidence") or 0.0),
                int(item.get("sample_count") or 0),
            ),
            reverse=True,
        )
        sorted_candidates = sorted(
            [item for item in candidates if isinstance(item, dict)],
            key=lambda item: (
                int(item.get("sample_count") or 0),
                int(item.get("recent_success_count") or 0),
                float(item.get("avg_artifact_hit_rate") or 0.0),
            ),
            reverse=True,
        )
        filtered_promotions = (
            [item for item in sorted_promotions if str(item.get("promotion_status") or "") == normalized_filter]
            if normalized_filter != "all"
            else sorted_promotions
        )
        filtered_candidates = (
            sorted_candidates
            if normalized_filter in {"all", "candidate"}
            else []
        )
        payload["shell_view"] = "dream"
        payload["dream_candidates"] = filtered_candidates[:12]
        payload["dream_promotions"] = filtered_promotions[:12]
        payload["dream_candidate_count"] = len(filtered_candidates)
        payload["dream_promotion_count"] = len(filtered_promotions)
        payload["dream_status_filter"] = normalized_filter
        payload["dream_generated_at"] = (
            promotion_state.get("generated_at")
            or candidate_state.get("generated_at")
            or payload.get("generated_at")
        )
        return payload

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

    def maybe_auto_consolidate(self, *, trigger: str, limit: int = 48, family_limit: int = 8) -> dict[str, Any]:
        if not self._config.auto_consolidation_enabled:
            return {"status": "disabled", "trigger": trigger}

        recent = load_recent_sessions(
            self._config.repo_root,
            project_scope=self._config.project_scope,
            exclude_task_id=None,
            limit=1,
        )
        if not recent:
            return {"status": "skipped", "reason": "no_sessions", "trigger": trigger}

        now = datetime.now(timezone.utc)
        state = load_consolidation_state(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
        )
        last_attempted_at = None
        last_completed_at = None
        if isinstance(state.get("last_attempted_at"), str):
            try:
                last_attempted_at = datetime.fromisoformat(str(state["last_attempted_at"]))
            except ValueError:
                last_attempted_at = None
        if isinstance(state.get("last_completed_at"), str):
            try:
                last_completed_at = datetime.fromisoformat(str(state["last_completed_at"]))
            except ValueError:
                last_completed_at = None

        throttle_window = timedelta(minutes=self._config.auto_consolidation_scan_throttle_minutes)
        if last_attempted_at and now - last_attempted_at < throttle_window:
            return {
                "status": "skipped",
                "reason": "scan_throttle",
                "trigger": trigger,
                "throttle_minutes": self._config.auto_consolidation_scan_throttle_minutes,
            }

        hours_window = timedelta(hours=self._config.auto_consolidation_min_hours)
        if last_completed_at and now - last_completed_at < hours_window:
            save_consolidation_state(
                repo_root=self._config.repo_root,
                project_scope=self._config.project_scope,
                payload={
                    **state,
                    "last_attempted_at": now.isoformat(),
                    "last_trigger": trigger,
                    "last_status": "skipped",
                    "last_reason": "time_gate",
                },
            )
            return {
                "status": "skipped",
                "reason": "time_gate",
                "trigger": trigger,
                "min_hours": self._config.auto_consolidation_min_hours,
            }

        new_session_count = self._count_new_sessions_since(last_completed_at)
        if new_session_count < self._config.auto_consolidation_min_new_sessions:
            save_consolidation_state(
                repo_root=self._config.repo_root,
                project_scope=self._config.project_scope,
                payload={
                    **state,
                    "last_attempted_at": now.isoformat(),
                    "last_trigger": trigger,
                    "last_status": "skipped",
                    "last_reason": "session_gate",
                    "last_new_session_count": new_session_count,
                },
            )
            return {
                "status": "skipped",
                "reason": "session_gate",
                "trigger": trigger,
                "new_session_count": new_session_count,
                "min_new_sessions": self._config.auto_consolidation_min_new_sessions,
            }

        payload = self.consolidate(limit=limit, family_limit=family_limit)
        save_consolidation_state(
            repo_root=self._config.repo_root,
            project_scope=self._config.project_scope,
            payload={
                **state,
                "last_attempted_at": now.isoformat(),
                "last_completed_at": payload.get("generated_at") or now.isoformat(),
                "last_trigger": trigger,
                "last_status": "completed",
                "last_reason": "completed",
                "last_new_session_count": new_session_count,
            },
        )
        return {
            "status": "completed",
            "trigger": trigger,
            "new_session_count": new_session_count,
            "sessions_reviewed": payload.get("sessions_reviewed", 0),
            "families_reviewed": payload.get("families_reviewed", 0),
            "consolidation_path": payload.get("consolidation_path"),
        }
