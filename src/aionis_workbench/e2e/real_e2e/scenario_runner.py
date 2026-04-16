from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from aionis_workbench.aionisdoc_bridge import (
    resolve_aionisdoc_fixture_source,
    resolve_aionisdoc_package_root,
)
from aionis_workbench.e2e.real_e2e.cli_driver import AionisCliRunResult, run_aionis
from aionis_workbench.e2e.real_e2e.manifest import RealRepoSpec
from aionis_workbench.e2e.real_e2e.repo_cache import ensure_repo_cached
from aionis_workbench.e2e.real_e2e.result_models import ScenarioResult
from aionis_workbench.e2e.real_e2e.runtime_env import RealRuntimeEnv
from aionis_workbench.live_profile import (
    LiveTimingRecord,
    infer_live_mode,
    load_live_profile_snapshot,
    save_live_profile_snapshot,
)
from aionis_workbench.provider_profiles import (
    provider_profile_has_required_credentials,
    resolve_provider_profile,
)
from aionis_workbench.runtime_manager import RuntimeManager, _resolve_runtime_root
from aionis_workbench.runtime import AionisWorkbench

def _fixture_workflow_source() -> Path:
    return resolve_aionisdoc_fixture_source()


def _extract_payload(stdout: str) -> dict[str, Any]:
    lines = stdout.strip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if not lines[index].lstrip().startswith("{"):
            continue
        candidate = "\n".join(lines[index:])
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("real e2e command did not produce a trailing JSON payload")


def _require_success(result: AionisCliRunResult, *, label: str) -> dict[str, Any]:
    if result.exit_code != 0:
        raise RuntimeError(
            f"{label} failed with exit_code={result.exit_code}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    try:
        return _extract_payload(result.stdout)
    except ValueError as exc:
        raise RuntimeError(
            f"{label} did not produce a trailing JSON payload\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ) from exc


def _wait_for_launcher_runtime_health(
    manager: RuntimeManager,
    *,
    base_url: str,
    timeout_seconds: float = 20.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_status: dict[str, object] = {}
    while time.monotonic() < deadline:
        with _patched_env({"AIONIS_BASE_URL": base_url}):
            last_status = manager.status()
        if last_status.get("health_status") == "available":
            return last_status
        time.sleep(0.25)
    return last_status


def _require_payload(
    result: AionisCliRunResult,
    *,
    label: str,
    allowed_exit_codes: set[int] | None = None,
) -> dict[str, Any]:
    expected = allowed_exit_codes or {0}
    if result.exit_code not in expected:
        raise RuntimeError(
            f"{label} failed with exit_code={result.exit_code}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    try:
        return _extract_payload(result.stdout)
    except ValueError as exc:
        raise RuntimeError(
            f"{label} did not produce a trailing JSON payload\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ) from exc


def _require_exit_zero(result: AionisCliRunResult, *, label: str) -> str:
    if result.exit_code != 0:
        raise RuntimeError(
            f"{label} failed with exit_code={result.exit_code}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def _parse_launcher_summary(text: str) -> dict[str, str]:
    match = re.match(
        r"launcher-status:\s+mode=(?P<mode>\S+)\s+health=(?P<health>\S+)\s+reason=(?P<reason>\S+)\s+base_url=(?P<base_url>\S+)\s+pid=(?P<pid>\S+)(?:\s+action=(?P<action>\S+))?",
        text.strip(),
    )
    if not match:
        raise RuntimeError(f"launcher command did not produce the expected summary line: {text}")
    return {key: (value or "") for key, value in match.groupdict().items()}


def _scenario_env(*, project_identity: str, base_url: str) -> dict[str, str]:
    workbench_root = Path(__file__).resolve().parents[3]
    runtime_root = _resolve_runtime_root(workbench_root)
    package_root = resolve_aionisdoc_package_root()
    return {
        "AIONIS_BASE_URL": base_url,
        "AIONIS_RUNTIME_ROOT": str(runtime_root),
        "AIONISDOC_PACKAGE_ROOT": str(package_root),
        "AIONISDOC_WORKSPACE_ROOT": str(package_root.parents[1]),
        "WORKBENCH_PROJECT_IDENTITY": project_identity,
    }


@contextmanager
def _patched_env(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _seed_workflow_file(repo_root: Path) -> Path:
    destination = repo_root / "flows" / "editor-to-dream.aionis.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_fixture_workflow_source().read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _live_target_file(repo_entry: RealRepoSpec, repo_root: Path) -> str:
    for relative_path in repo_entry.doc_paths:
        candidate = repo_root / relative_path
        if candidate.exists():
            return relative_path
    for candidate in ("README.md", "readme.md", "README.rst", "README.txt"):
        if (repo_root / candidate).exists():
            return candidate
    return "."


def _live_scenario_env(*, project_identity: str, base_url: str, launcher_home: Path) -> dict[str, str]:
    env = _scenario_env(project_identity=project_identity, base_url=base_url)
    provider_profile = resolve_provider_profile()
    env.update(
        {
            "HOME": str(launcher_home),
        }
    )
    if provider_profile is not None:
        env["AIONIS_PROVIDER_PROFILE"] = provider_profile.provider_id
        env["WORKBENCH_MODEL_TIMEOUT_SECONDS"] = str(provider_profile.timeout_seconds)
        env["WORKBENCH_MAX_COMPLETION_TOKENS"] = str(provider_profile.max_completion_tokens)
        if provider_profile.provider == "openai":
            env.setdefault("WORKBENCH_MODEL", provider_profile.model)
            if provider_profile.base_url:
                env.setdefault("OPENAI_BASE_URL", provider_profile.base_url)
        elif provider_profile.provider == "openrouter":
            env.setdefault("OPENROUTER_MODEL", provider_profile.model)
            if provider_profile.base_url:
                env.setdefault("OPENROUTER_BASE_URL", provider_profile.base_url)
    else:
        env["WORKBENCH_MODEL_TIMEOUT_SECONDS"] = "15"
        env["WORKBENCH_MAX_COMPLETION_TOKENS"] = "256"
    env.setdefault("AIONIS_LIVE_MODE", "targeted_fix")
    return env


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _persist_live_profile_snapshot(details: dict[str, Any], *, launcher_home: Path) -> None:
    execution_focus = str(
        details.get("second_replanned_execution_focus")
        or details.get("pre_advance_execution_focus")
        or details.get("pre_escalate_execution_focus")
        or details.get("execution_focus")
        or ""
    ).strip()
    execution_gate = str(
        details.get("second_replanned_execution_gate")
        or details.get("pre_advance_execution_gate")
        or details.get("pre_escalate_execution_gate")
        or details.get("execution_gate")
        or ""
    ).strip()
    execution_gate_transition = str(
        details.get("second_replanned_execution_gate_transition")
        or details.get("pre_advance_execution_gate_transition")
        or details.get("pre_escalate_execution_gate_transition")
        or details.get("execution_gate_transition")
        or ""
    ).strip()
    last_policy_action = str(
        details.get("second_replanned_last_policy_action")
        or details.get("pre_advance_last_policy_action")
        or details.get("pre_escalate_last_policy_action")
        or details.get("last_policy_action")
        or ""
    ).strip()
    execution_outcome_ready_raw = (
        details.get("second_replanned_execution_outcome_ready")
        if "second_replanned_execution_outcome_ready" in details
        else details.get("pre_advance_execution_outcome_ready")
        if "pre_advance_execution_outcome_ready" in details
        else details.get("pre_escalate_execution_outcome_ready")
        if "pre_escalate_execution_outcome_ready" in details
        else details.get("execution_outcome_ready")
    )
    scenario_id = str(details.get("scenario_id") or "").strip()
    convergence_signal = "none"
    if execution_gate_transition or last_policy_action:
        signal = execution_gate_transition or "none"
        if last_policy_action:
            signal = f"{signal}@{last_policy_action}"
        if scenario_id:
            signal = f"{scenario_id}:{signal}"
        convergence_signal = signal
    previous_snapshot = load_live_profile_snapshot(home=launcher_home)
    previous_signals = previous_snapshot.get("recent_convergence_signals") or []
    recent_convergence_signals: list[str] = []
    if isinstance(previous_signals, list):
        for item in previous_signals:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    recent_convergence_signals.append(cleaned)
    if convergence_signal != "none":
        recent_convergence_signals.append(convergence_signal)
    deduped_recent_signals: list[str] = []
    for item in recent_convergence_signals:
        if item in deduped_recent_signals:
            continue
        deduped_recent_signals.append(item)
    recent_convergence_signals = deduped_recent_signals[-4:]
    snapshot = {
        "version": "aionis_live_profile_v1",
        "scenario_id": scenario_id,
        "provider_id": str(details.get("provider_id") or ""),
        "live_mode": str(details.get("live_mode") or ""),
        "model": str(details.get("model") or ""),
        "timeout_seconds": int(details.get("timeout_seconds") or 0),
        "max_completion_tokens": int(details.get("max_completion_tokens") or 0),
        "ready_duration_seconds": float(details.get("ready_duration_seconds") or 0.0),
        "run_duration_seconds": float(details.get("run_duration_seconds") or 0.0),
        "resume_duration_seconds": float(details.get("resume_duration_seconds") or 0.0),
        "total_duration_seconds": float(details.get("total_duration_seconds") or 0.0),
        "timing_summary": str(details.get("timing_summary") or ""),
        "execution_focus": execution_focus,
        "execution_gate": execution_gate,
        "execution_gate_transition": execution_gate_transition,
        "last_policy_action": last_policy_action,
        "execution_outcome_ready": bool(execution_outcome_ready_raw) if execution_outcome_ready_raw is not None else False,
        "convergence_signal": convergence_signal,
        "recent_convergence_signals": recent_convergence_signals,
        "repo_id": str(details.get("repo_id") or ""),
        "task_id": str(details.get("task_id") or ""),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_live_profile_snapshot(snapshot, home=launcher_home)
    repo_root = str(details.get("repo_root") or "").strip()
    if repo_root:
        save_live_profile_snapshot(snapshot, home=Path(repo_root) / ".real-live-home")


@dataclass
class LivePreparedState:
    repo_root: Path
    launcher_home_path: Path
    runtime_env: RealRuntimeEnv
    env: dict[str, str]
    task_id: str
    target_file: str
    task_text: str
    ready_output: str
    doctor_payload: dict[str, Any]
    run_payload: dict[str, Any]
    run_status: str
    run_aionis_payload: dict[str, Any]
    paused_session_payload: dict[str, Any]
    timing: LiveTimingRecord
    provider_profile: str


def run_editor_to_dream_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    workflow_path = _seed_workflow_file(repo_root)
    runtime_env = RealRuntimeEnv(home=launcher_home)
    project_identity = f"real-e2e/editor-to-dream/{repo_entry.id}"
    env = _scenario_env(project_identity=project_identity, base_url=runtime_env.base_url)
    task_ids: list[str] = []
    compile_payloads: list[dict[str, Any]] = []

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        for index in range(1, 4):
            task_id = f"{repo_entry.id}-editor-dream-{index}"
            task_ids.append(task_id)
            ingest_payload = _require_success(
                run_aionis(
                    [
                        "ingest",
                        "--repo-root",
                        str(repo_root),
                        "--task-id",
                        task_id,
                        "--task",
                        "Compile workflow continuity",
                        "--summary",
                        "Record deterministic workflow compile into Workbench continuity.",
                        "--target-file",
                        str(workflow_path.relative_to(repo_root)),
                        "--validation-command",
                        "git status --short",
                        "--validation-summary",
                        "git status completed.",
                        "--validation-ok",
                    ],
                    cwd=repo_root,
                    env=env,
                ),
                label=f"ingest[{task_id}]",
            )
            if ingest_payload.get("runner") != "ingest":
                raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

            compile_payload = _require_success(
                run_aionis(
                    [
                        "doc",
                        "--repo-root",
                        str(repo_root),
                        "compile",
                        "--input",
                        str(workflow_path),
                        "--task-id",
                        task_id,
                        "--event-source",
                        "cursor_extension",
                        "--event-origin",
                        "editor_extension",
                        "--recorded-at",
                        f"2026-04-03T12:00:0{index}Z",
                    ],
                    cwd=repo_root,
                    env=env,
                ),
                label=f"doc-compile[{task_id}]",
            )
            compile_payloads.append(compile_payload)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            consolidate_payload = workbench.consolidate(limit=12, family_limit=4)
            dream_payload = workbench.dream(limit=12, family_limit=4, status_filter=None)
            session_payload = workbench.inspect_session(task_id=task_ids[-1])

        promotions = dream_payload.get("dream_promotions") or []
        if not promotions:
            raise RuntimeError(f"dream did not produce any promotions: {dream_payload}")
        top_promotion = promotions[0]
        if str(top_promotion.get("dominant_event_source") or "").strip() != "cursor_extension":
            raise RuntimeError(f"dream promotion is missing editor evidence: {top_promotion}")
        if str(top_promotion.get("dominant_doc_action") or "").strip() != "compile":
            raise RuntimeError(f"dream promotion is missing compile doc action: {top_promotion}")
        if int(top_promotion.get("editor_sync_count") or 0) < 2:
            raise RuntimeError(f"dream promotion did not accumulate editor sync count: {top_promotion}")

        session_path = Path(str(compile_payloads[-1].get("session_path") or ""))
        if not session_path.exists():
            raise RuntimeError(f"doc compile did not persist a session path: {compile_payloads[-1]}")
        session_state = json.loads(session_path.read_text(encoding="utf-8"))
        continuity = (session_state.get("continuity_snapshot") or {}) if isinstance(session_state, dict) else {}
        doc_workflow = (continuity.get("doc_workflow") or {}) if isinstance(continuity, dict) else {}

        return ScenarioResult(
            scenario_id="editor-to-dream",
            status="passed",
            repo_id=repo_entry.id,
            details={
                "repo_root": str(repo_root),
                "workflow_path": str(workflow_path),
                "task_ids": task_ids,
                "consolidate_shell_view": consolidate_payload.get("shell_view"),
                "dream_shell_view": dream_payload.get("shell_view"),
                "dream_promotion_count": dream_payload.get("dream_promotion_count"),
                "dream_status_filter": dream_payload.get("dream_status_filter"),
                "promotion_status": top_promotion.get("promotion_status"),
                "dominant_source_doc_id": top_promotion.get("dominant_source_doc_id"),
                "dominant_doc_input": top_promotion.get("dominant_doc_input"),
                "dominant_doc_action": top_promotion.get("dominant_doc_action"),
                "dominant_event_source": top_promotion.get("dominant_event_source"),
                "editor_sync_count": top_promotion.get("editor_sync_count"),
                "session_doc_event_source": doc_workflow.get("event_source"),
                "session_doc_latest_action": doc_workflow.get("latest_action"),
                "session_doc_source_doc_id": doc_workflow.get("source_doc_id"),
                "doc_show_summary": session_payload.get("doc_learning", {}),
            },
        )
    finally:
        runtime_env.stop()


def run_live_app_second_replan_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
    ending: str = "none",
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-second-replan/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-second-replan-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-second-replan-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Exercise a second replanned sprint loop for the app harness.",
                    "--summary",
                    "Create a persisted session before running a second live replan cycle.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-ingest[{task_id}]",
        )

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-negotiate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--summary",
                    "Patch refresh stability in the graph shell before re-running the evaluator.",
                    "--target",
                    "src/graph-shell.tsx",
                    "--target",
                    "src/timeline-panel.tsx",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-generate-initial[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "Refresh handling improved, but timeline stability still falls short of the evaluator bar.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-qa-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "retry budget exhausted",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-escalate[{task_id}]",
        )

        first_replan_started = time.monotonic()
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "replan",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "narrow the sprint around persistence hardening",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-first[{task_id}]",
        )
        timing.add_phase("app_replan_first", time.monotonic() - first_replan_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            first_replan_payload = workbench.inspect_session(task_id=task_id)
        first_replan_harness = (first_replan_payload.get("canonical_views") or {}).get("app_harness") or {}
        first_replanned_sprint_id = str(
            (first_replan_harness.get("active_sprint_contract") or {}).get("sprint_id") or ""
        ).strip()
        if not first_replanned_sprint_id.startswith("sprint-1-replan-"):
            raise RuntimeError(f"live app second replan did not create the first replanned sprint: {first_replan_harness}")

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--use-live-generator",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-generate-first-replanned[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--use-live-evaluator",
                    "--status",
                    "failed",
                    "--score",
                    "functionality=0.62",
                    "--score",
                    "design_quality=0.68",
                    "--score",
                    "code_quality=0.66",
                    "--summary",
                    "The replanned sprint still misses one recovery edge in the explorer flow.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-qa-first-replanned[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--objection",
                    "the replanned sprint still misses one recovery edge",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-negotiate-first-replanned[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--revision-note",
                    "focus only on the remaining recovery edge case",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-retry-first-replanned[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--use-live-generator",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-generate-first-replanned-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--use-live-evaluator",
                    "--status",
                    "failed",
                    "--score",
                    "functionality=0.65",
                    "--score",
                    "design_quality=0.71",
                    "--score",
                    "code_quality=0.69",
                    "--summary",
                    "The narrower replanned sprint improves reliability, but one recovery edge still fails under review.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-qa-first-replanned-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--note",
                    "first replanned sprint still misses one recovery edge",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-second-replan-escalate-first-replanned[{task_id}]",
        )

        second_replan_env = dict(env)
        second_replan_env["WORKBENCH_MODEL_TIMEOUT_SECONDS"] = str(
            max(int(float(env.get("WORKBENCH_MODEL_TIMEOUT_SECONDS") or 45)), 90)
        )
        second_replan_started = time.monotonic()
        second_replan_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "replan",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    first_replanned_sprint_id,
                    "--note",
                    "reduce the sprint to the final recovery edge and validation hardening",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=second_replan_env,
            ),
            label=f"live-app-second-replan-second[{task_id}]",
        )
        timing.add_phase("app_replan_second", time.monotonic() - second_replan_started)

        with _patched_env(second_replan_env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            planner_timeout_seconds = int(workbench._execution_host.live_app_planner_timeout_seconds())
            planner_max_completion_tokens = int(workbench._execution_host.live_app_planner_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        second_replanned_sprint_id = str((harness.get("active_sprint_contract") or {}).get("sprint_id") or "").strip()
        if not second_replanned_sprint_id.startswith(f"{first_replanned_sprint_id}-replan-"):
            raise RuntimeError(f"live app second replan did not create a second replanned sprint: {harness}")
        if str(harness.get("loop_status") or "").strip() != "sprint_replanned":
            raise RuntimeError(f"live app second replan did not settle to sprint_replanned: {harness}")
        if int(harness.get("replan_depth") or 0) != 2:
            raise RuntimeError(f"live app second replan did not record replan_depth=2: {harness}")
        if str(harness.get("replan_root_sprint_id") or "").strip() != "sprint-1":
            raise RuntimeError(f"live app second replan lost the root sprint id: {harness}")
        if int(harness.get("retry_count") or 0) != 0:
            raise RuntimeError(f"live app second replan did not reset retry_count: {harness}")
        if int(harness.get("retry_remaining") or 0) != 1:
            raise RuntimeError(f"live app second replan did not reopen retry_remaining: {harness}")

        scenario_id = "live-app-second-replan"
        if ending not in {"none", "advance", "escalate"}:
            raise RuntimeError(f"unsupported second replan ending: {ending}")

        final_harness = harness
        second_replanned_pre_ending_harness = harness
        ending_stdout: list[str] = []
        second_replanned_execution_attempt: dict[str, Any] = {}
        second_replanned_evaluation: dict[str, Any] = {}

        if ending != "none":
            generate_started = time.monotonic()
            _require_exit_zero(
                run_aionis(
                    [
                        "app",
                        "--repo-root",
                        str(repo_root),
                        "generate",
                        "--task-id",
                        task_id,
                        "--sprint-id",
                        second_replanned_sprint_id,
                        "--use-live-generator",
                    ],
                    cwd=repo_root,
                    env=second_replan_env,
                ),
                label=f"live-app-second-replan-generate-second[{task_id}]",
            )
            timing.add_phase("app_generate_second_replanned", time.monotonic() - generate_started)

            qa_started = time.monotonic()
            qa_args = [
                "app",
                "--repo-root",
                str(repo_root),
                "qa",
                "--task-id",
                task_id,
                "--sprint-id",
                second_replanned_sprint_id,
                "--use-live-evaluator",
            ]
            if ending == "advance":
                qa_args.extend(
                    [
                        "--status",
                        "passed",
                        "--score",
                        "functionality=0.91",
                        "--score",
                        "design_quality=0.86",
                        "--score",
                        "code_quality=0.84",
                        "--summary",
                        "The second replanned sprint closes the final hydration edge and clears the evaluator bar.",
                    ]
                )
            else:
                qa_args.extend(
                    [
                        "--status",
                        "failed",
                        "--score",
                        "functionality=0.71",
                        "--score",
                        "design_quality=0.79",
                        "--score",
                        "code_quality=0.76",
                        "--summary",
                        "The second replanned sprint still misses the final hydration edge under evaluator review.",
                    ]
                )
            _require_exit_zero(
                run_aionis(
                    qa_args,
                    cwd=repo_root,
                    env=second_replan_env,
                ),
                label=f"live-app-second-replan-qa-second[{task_id}]",
            )
            timing.add_phase("app_qa_second_replanned", time.monotonic() - qa_started)

            with _patched_env(second_replan_env):
                workbench = AionisWorkbench(repo_root=str(repo_root))
                ending_payload = workbench.inspect_session(task_id=task_id)
            final_harness = (ending_payload.get("canonical_views") or {}).get("app_harness") or {}
            second_replanned_pre_ending_harness = final_harness
            second_replanned_execution_attempt = final_harness.get("latest_execution_attempt") or {}
            second_replanned_evaluation = final_harness.get("latest_sprint_evaluation") or {}

            if str(second_replanned_execution_attempt.get("sprint_id") or "").strip() != second_replanned_sprint_id:
                raise RuntimeError(f"second replanned execution attempt did not bind to the correct sprint: {final_harness}")
            if str(second_replanned_execution_attempt.get("execution_mode") or "").strip() != "live":
                raise RuntimeError(f"second replanned sprint did not persist execution_mode=live: {final_harness}")
            if str(second_replanned_evaluation.get("sprint_id") or "").strip() != second_replanned_sprint_id:
                raise RuntimeError(f"second replanned evaluation did not bind to the correct sprint: {final_harness}")
            if str(second_replanned_evaluation.get("evaluator_mode") or "").strip() != "live":
                raise RuntimeError(f"second replanned sprint did not persist evaluator_mode=live: {final_harness}")

            if ending == "advance":
                if str(final_harness.get("recommended_next_action") or "").strip() != "advance_to_next_sprint":
                    raise RuntimeError(f"second replanned sprint did not unlock advance: {final_harness}")
                advance_started = time.monotonic()
                advance_stdout = _require_exit_zero(
                    run_aionis(
                        [
                            "app",
                            "--repo-root",
                            str(repo_root),
                            "advance",
                            "--task-id",
                            task_id,
                            "--sprint-id",
                            "sprint-2",
                        ],
                        cwd=repo_root,
                        env=second_replan_env,
                    ),
                    label=f"live-app-second-replan-advance[{task_id}]",
                )
                timing.add_phase("app_advance_second_replanned", time.monotonic() - advance_started)
                ending_stdout = advance_stdout.splitlines()[:2]
                with _patched_env(second_replan_env):
                    workbench = AionisWorkbench(repo_root=str(repo_root))
                    ending_payload = workbench.inspect_session(task_id=task_id)
                final_harness = (ending_payload.get("canonical_views") or {}).get("app_harness") or {}
                if str((final_harness.get("active_sprint_contract") or {}).get("sprint_id") or "").strip() != "sprint-2":
                    raise RuntimeError(f"second replanned advance did not activate sprint-2: {final_harness}")
                if str(final_harness.get("loop_status") or "").strip() != "in_sprint":
                    raise RuntimeError(f"second replanned advance did not transition back to in_sprint: {final_harness}")
                scenario_id = "live-app-second-replan-generate-qa-advance"
            else:
                if str(final_harness.get("recommended_next_action") or "").strip() != "negotiate_current_sprint":
                    raise RuntimeError(f"second replanned sprint did not route back to negotiation before escalation: {final_harness}")
                escalate_started = time.monotonic()
                escalate_stdout = _require_exit_zero(
                    run_aionis(
                        [
                            "app",
                            "--repo-root",
                            str(repo_root),
                            "escalate",
                            "--task-id",
                            task_id,
                            "--sprint-id",
                            second_replanned_sprint_id,
                            "--note",
                            "second replanned sprint still misses the final hydration edge",
                        ],
                        cwd=repo_root,
                        env=second_replan_env,
                    ),
                    label=f"live-app-second-replan-escalate-second[{task_id}]",
                )
                timing.add_phase("app_escalate_second_replanned", time.monotonic() - escalate_started)
                ending_stdout = escalate_stdout.splitlines()[:2]
                with _patched_env(second_replan_env):
                    workbench = AionisWorkbench(repo_root=str(repo_root))
                    ending_payload = workbench.inspect_session(task_id=task_id)
                final_harness = (ending_payload.get("canonical_views") or {}).get("app_harness") or {}
                if str((final_harness.get("active_sprint_contract") or {}).get("sprint_id") or "").strip() != second_replanned_sprint_id:
                    raise RuntimeError(f"second replanned escalate should keep the replanned sprint active: {final_harness}")
                if str(final_harness.get("loop_status") or "").strip() != "escalated":
                    raise RuntimeError(f"second replanned escalate did not settle to escalated: {final_harness}")
                scenario_id = "live-app-second-replan-generate-qa-escalate"

        provider_profile = resolve_provider_profile(second_replan_env)
        details = {
            "scenario_id": scenario_id,
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "second_replan_stdout": second_replan_stdout.splitlines()[:2],
            "ending": ending,
            "ending_stdout": ending_stdout,
            "first_replanned_sprint_id": first_replanned_sprint_id,
            "second_replanned_sprint_id": second_replanned_sprint_id,
            "second_replanned_replan_depth": second_replanned_pre_ending_harness.get("replan_depth"),
            "second_replanned_replan_root_sprint_id": second_replanned_pre_ending_harness.get("replan_root_sprint_id"),
            "second_replanned_execution_focus": second_replanned_pre_ending_harness.get("execution_focus"),
            "second_replanned_execution_gate": second_replanned_pre_ending_harness.get("execution_gate"),
            "second_replanned_execution_gate_transition": second_replanned_pre_ending_harness.get("last_execution_gate_transition"),
            "second_replanned_execution_outcome_ready": second_replanned_pre_ending_harness.get("execution_outcome_ready"),
            "second_replanned_last_policy_action": second_replanned_pre_ending_harness.get("last_policy_action"),
            "active_sprint_id": (final_harness.get("active_sprint_contract") or {}).get("sprint_id"),
            "loop_status": final_harness.get("loop_status"),
            "replan_depth": final_harness.get("replan_depth"),
            "replan_root_sprint_id": final_harness.get("replan_root_sprint_id"),
            "retry_count": final_harness.get("retry_count"),
            "retry_budget": final_harness.get("retry_budget"),
            "retry_remaining": final_harness.get("retry_remaining"),
            "recommended_next_action": final_harness.get("recommended_next_action"),
            "second_replanned_execution_mode": second_replanned_execution_attempt.get("execution_mode"),
            "second_replanned_execution_summary": second_replanned_execution_attempt.get("execution_summary"),
            "second_replanned_evaluator_mode": second_replanned_evaluation.get("evaluator_mode"),
            "second_replanned_evaluation_status": second_replanned_evaluation.get("status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(second_replan_env),
            "model": str(second_replan_env.get("WORKBENCH_MODEL") or second_replan_env.get("OPENROUTER_MODEL") or ""),
            "planner_timeout_seconds": planner_timeout_seconds,
            "planner_max_completion_tokens": planner_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_replan_first_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_replan_first"), 0.0),
            "app_replan_second_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_replan_second"), 0.0),
            "app_generate_second_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_generate_second_replanned"), 0.0),
            "app_qa_second_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_qa_second_replanned"), 0.0),
            "app_advance_second_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_advance_second_replanned"), 0.0),
            "app_escalate_second_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_escalate_second_replanned"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id=scenario_id,
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_second_replan_generate_qa_advance_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    return run_live_app_second_replan_scenario(
        repo_entry,
        cache_root=cache_root,
        launcher_home=launcher_home,
        ending="advance",
    )


def run_live_app_second_replan_generate_qa_escalate_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    return run_live_app_second_replan_scenario(
        repo_entry,
        cache_root=cache_root,
        launcher_home=launcher_home,
        ending="escalate",
    )


def run_publish_recover_resume_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    workflow_path = _seed_workflow_file(repo_root)
    runtime_env = RealRuntimeEnv(home=launcher_home)
    project_identity = f"real-e2e/publish-recover-resume/{repo_entry.id}"
    env = _scenario_env(project_identity=project_identity, base_url=runtime_env.base_url)
    task_id = f"{repo_entry.id}-publish-recover-resume-1"

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Exercise publish, recover, and resume continuity.",
                    "--summary",
                    "Record a real publish-recover-resume workflow into Workbench continuity.",
                    "--target-file",
                    str(workflow_path.relative_to(repo_root)),
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        publish_payload = _require_success(
            run_aionis(
                [
                    "doc",
                    "--repo-root",
                    str(repo_root),
                    "publish",
                    "--input",
                    str(workflow_path),
                    "--task-id",
                    task_id,
                    "--event-source",
                    "cursor_extension",
                    "--event-origin",
                    "editor_extension",
                    "--recorded-at",
                    "2026-04-03T13:31:01Z",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"doc-publish[{task_id}]",
        )
        publish_result = publish_payload.get("publish_result")
        if not isinstance(publish_result, dict):
            raise RuntimeError(f"publish payload is missing publish_result: {publish_payload}")

        with TemporaryDirectory(prefix="aionis-real-e2e-") as temp_dir:
            publish_result_path = _write_json(Path(temp_dir) / "publish-result.json", publish_result)

            recover_payload = _require_success(
                run_aionis(
                    [
                        "doc",
                        "--repo-root",
                        str(repo_root),
                        "recover",
                        "--input",
                        str(publish_result_path),
                        "--input-kind",
                        "publish-result",
                        "--task-id",
                        task_id,
                        "--event-source",
                        "cursor_extension",
                        "--event-origin",
                        "editor_extension",
                        "--recorded-at",
                        "2026-04-03T13:31:02Z",
                    ],
                    cwd=repo_root,
                    env=env,
                ),
                label=f"doc-recover[{task_id}]",
            )
            recover_result = recover_payload.get("recover_result")
            if not isinstance(recover_result, dict):
                raise RuntimeError(f"recover payload is missing recover_result: {recover_payload}")
            recover_result_path = _write_json(Path(temp_dir) / "recover-result.json", recover_result)

            resume_payload = _require_success(
                run_aionis(
                    [
                        "doc",
                        "--repo-root",
                        str(repo_root),
                        "resume",
                        "--input",
                        str(recover_result_path),
                        "--input-kind",
                        "recover-result",
                        "--task-id",
                        task_id,
                        "--candidate",
                        "read",
                        "--query-text",
                        "Summarize current workflow evidence",
                        "--event-source",
                        "cursor_extension",
                        "--event-origin",
                        "editor_extension",
                        "--recorded-at",
                        "2026-04-03T13:31:03Z",
                    ],
                    cwd=repo_root,
                    env=env,
                ),
                label=f"doc-resume[{task_id}]",
            )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            session_payload = workbench.inspect_session(task_id=task_id)

        session_path = Path(str(resume_payload.get("session_path") or ""))
        if not session_path.exists():
            raise RuntimeError(f"doc resume did not persist a session path: {resume_payload}")
        session_state = json.loads(session_path.read_text(encoding="utf-8"))
        continuity = (session_state.get("continuity_snapshot") or {}) if isinstance(session_state, dict) else {}
        doc_workflow = (continuity.get("doc_workflow") or {}) if isinstance(continuity, dict) else {}
        history = doc_workflow.get("history") or []
        history_actions = [
            str(item.get("action") or "")
            for item in history
            if isinstance(item, dict) and str(item.get("action") or "").strip()
        ]
        artifacts = session_state.get("artifacts") or []
        artifact_kinds = [
            str(item.get("kind") or "")
            for item in artifacts
            if isinstance(item, dict) and str(item.get("kind") or "").strip()
        ]
        resume_result = resume_payload.get("resume_result")
        resume_result = resume_result if isinstance(resume_result, dict) else {}
        resume_summary = resume_result.get("resume_summary")
        resume_summary = resume_summary if isinstance(resume_summary, dict) else {}

        if history_actions[:3] != ["resume", "recover", "publish"]:
            raise RuntimeError(f"unexpected doc history order: {history_actions}")
        if str(doc_workflow.get("handoff_anchor") or "").strip() == "":
            raise RuntimeError(f"resume continuity is missing a handoff anchor: {doc_workflow}")
        if str(doc_workflow.get("selected_tool") or "").strip() != "read":
            raise RuntimeError(f"resume continuity is missing the selected tool: {doc_workflow}")
        if "doc_publish_result" not in artifact_kinds or "doc_recover_result" not in artifact_kinds or "doc_resume_result" not in artifact_kinds:
            raise RuntimeError(f"resume continuity is missing doc artifacts: {artifact_kinds}")

        return ScenarioResult(
            scenario_id="publish-recover-resume",
            status="passed",
            repo_id=repo_entry.id,
            details={
                "repo_root": str(repo_root),
                "workflow_path": str(workflow_path),
                "task_id": task_id,
                "publish_shell_view": publish_payload.get("shell_view"),
                "recover_shell_view": recover_payload.get("shell_view"),
                "resume_shell_view": resume_payload.get("shell_view"),
                "session_doc_latest_action": doc_workflow.get("latest_action"),
                "session_doc_handoff_anchor": doc_workflow.get("handoff_anchor"),
                "session_doc_selected_tool": doc_workflow.get("selected_tool"),
                "session_doc_event_source": doc_workflow.get("event_source"),
                "history_actions": history_actions,
                "artifact_kinds": artifact_kinds,
                "resume_selected_tool": resume_summary.get("selected_tool"),
                "doc_show_summary": session_payload.get("doc_learning", {}),
            },
        )
    finally:
        runtime_env.stop()


def run_repeated_workflow_reuse_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    workflow_path = _seed_workflow_file(repo_root)
    runtime_env = RealRuntimeEnv(home=launcher_home)
    project_identity = f"real-e2e/repeated-workflow-reuse/{repo_entry.id}"
    env = _scenario_env(project_identity=project_identity, base_url=runtime_env.base_url)
    task_ids: list[str] = []
    workflow_relpath = str(workflow_path.relative_to(repo_root))

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        for index in range(1, 4):
            task_id = f"{repo_entry.id}-workflow-reuse-{index}"
            task_ids.append(task_id)
            ingest_payload = _require_success(
                run_aionis(
                    [
                        "ingest",
                        "--repo-root",
                        str(repo_root),
                        "--task-id",
                        task_id,
                        "--task",
                        "Repeat deterministic workflow reuse continuity.",
                        "--summary",
                        "Record repeated deterministic workflow evidence into Workbench continuity.",
                        "--target-file",
                        workflow_relpath,
                        "--validation-command",
                        "git status --short",
                        "--validation-summary",
                        "git status completed.",
                        "--validation-ok",
                    ],
                    cwd=repo_root,
                    env=env,
                ),
                label=f"ingest[{task_id}]",
            )
            if ingest_payload.get("runner") != "ingest":
                raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

            _require_success(
                run_aionis(
                    [
                        "doc",
                        "--repo-root",
                        str(repo_root),
                        "compile",
                        "--input",
                        str(workflow_path),
                        "--task-id",
                        task_id,
                        "--event-source",
                        "cursor_extension",
                        "--event-origin",
                        "editor_extension",
                        "--recorded-at",
                        f"2026-04-03T14:00:0{index}Z",
                    ],
                    cwd=repo_root,
                    env=env,
                ),
                label=f"doc-compile[{task_id}]",
            )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            consolidate_payload = workbench.consolidate(limit=12, family_limit=4)
            dashboard_payload = workbench.dashboard(limit=12, family_limit=4)

        family_rows = consolidate_payload.get("family_rows") or []
        family_row = next(
            (
                row
                for row in family_rows
                if isinstance(row, dict)
                and isinstance(row.get("family_doc_prior"), dict)
                and str((row.get("family_doc_prior") or {}).get("dominant_doc_input") or "")
                in {workflow_relpath, str(workflow_path)}
            ),
            None,
        )
        if not isinstance(family_row, dict):
            raise RuntimeError(f"consolidation did not expose a family row for {workflow_relpath}: {family_rows}")
        doc_prior = family_row.get("family_doc_prior") or {}
        if not isinstance(doc_prior, dict):
            raise RuntimeError(f"family row is missing family_doc_prior: {family_row}")
        if doc_prior.get("seed_ready") is not True:
            raise RuntimeError(f"family doc prior did not become seed-ready: {doc_prior}")
        if int(doc_prior.get("sample_count") or 0) < 3:
            raise RuntimeError(f"family doc prior sample count is too small: {doc_prior}")
        if str(doc_prior.get("dominant_event_source") or "").strip() != "cursor_extension":
            raise RuntimeError(f"family doc prior is missing editor source evidence: {doc_prior}")
        if int(doc_prior.get("editor_sync_count") or 0) < 3:
            raise RuntimeError(f"family doc prior editor sync count is too small: {doc_prior}")

        dashboard_summary = dashboard_payload.get("dashboard_summary") or {}
        if int(dashboard_summary.get("doc_prior_ready_count") or 0) < 1:
            raise RuntimeError(f"dashboard does not expose any ready doc priors: {dashboard_summary}")
        if int(dashboard_summary.get("doc_editor_sync_event_count") or 0) < 3:
            raise RuntimeError(f"dashboard does not expose enough editor sync events: {dashboard_summary}")
        expected_proof = "recent families already have seed-ready priors, and editor-driven doc reuse is live"
        if str(dashboard_summary.get("proof_summary") or "") != expected_proof:
            raise RuntimeError(f"dashboard proof summary did not converge: {dashboard_summary}")

        return ScenarioResult(
            scenario_id="repeated-workflow-reuse",
            status="passed",
            repo_id=repo_entry.id,
            details={
                "repo_root": str(repo_root),
                "workflow_path": str(workflow_path),
                "task_ids": task_ids,
                "consolidate_shell_view": consolidate_payload.get("shell_view"),
                "dashboard_shell_view": dashboard_payload.get("shell_view"),
                "task_family": family_row.get("task_family"),
                "doc_seed_ready": doc_prior.get("seed_ready"),
                "doc_sample_count": doc_prior.get("sample_count"),
                "dominant_doc_input": doc_prior.get("dominant_doc_input"),
                "dominant_source_doc_id": doc_prior.get("dominant_source_doc_id"),
                "dominant_event_source": doc_prior.get("dominant_event_source"),
                "editor_sync_count": doc_prior.get("editor_sync_count"),
                "dashboard_doc_prior_ready_count": dashboard_summary.get("doc_prior_ready_count"),
                "dashboard_doc_editor_sync_event_count": dashboard_summary.get("doc_editor_sync_event_count"),
                "dashboard_proof_summary": dashboard_summary.get("proof_summary"),
            },
        )
    finally:
        runtime_env.stop()


def run_app_harness_planner_contract_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    runtime_env = RealRuntimeEnv(home=launcher_home)
    project_identity = f"real-e2e/app-harness-planner-contract/{repo_entry.id}"
    env = _scenario_env(project_identity=project_identity, base_url=runtime_env.base_url)
    target_file = _live_target_file(repo_entry, repo_root)
    task_id = f"{repo_entry.id}-app-harness-1"

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Establish app harness state for a long-running app workflow.",
                    "--summary",
                    "Create a persisted session to attach app harness planning, sprint, and QA artifacts.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        plan_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-plan[{task_id}]",
        )
        sprint_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-sprint[{task_id}]",
        )
        qa_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--score",
                    "functionality=0.62",
                    "--score",
                    "design_quality=0.78",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-qa[{task_id}]",
        )
        negotiate_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-negotiate[{task_id}]",
        )
        retry_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "fix timeline persistence",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-retry[{task_id}]",
        )
        generate_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-generate[{task_id}]",
        )
        qa_after_retry_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--status",
                    "passed",
                    "--score",
                    "functionality=0.9",
                    "--score",
                    "design_quality=0.82",
                    "--score",
                    "code_quality=0.8",
                    "--summary",
                    "Timeline persistence is stable and the sprint clears the evaluator bar.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-qa-after-retry[{task_id}]",
        )
        advance_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "advance",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-advance[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                    "--status",
                    "failed",
                    "--score",
                    "functionality=0.58",
                    "--score",
                    "design_quality=0.77",
                    "--blocker",
                    "workspace state still desynchronizes after resume",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-qa-sprint-2[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                    "--objection",
                    "workspace state still desynchronizes after resume",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-negotiate-sprint-2[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                    "--revision-note",
                    "narrow sprint-2 around hydration and resume stability",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-retry-sprint-2[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-generate-sprint-2[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                    "--status",
                    "failed",
                    "--score",
                    "functionality=0.63",
                    "--score",
                    "design_quality=0.79",
                    "--blocker",
                    "resume hydration still misses one edge",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-qa-sprint-2-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                    "--note",
                    "retry budget exhausted on sprint-2",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-escalate-sprint-2[{task_id}]",
        )
        second_replan_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "replan",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                    "--note",
                    "narrow sprint-2 again around the final hydration edge",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"app-second-replan[{task_id}]",
        )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        product = harness.get("product_spec") or {}
        sprint = harness.get("active_sprint_contract") or {}
        evaluation = harness.get("latest_sprint_evaluation") or {}
        negotiation = harness.get("latest_negotiation_round") or {}
        latest_revision = harness.get("latest_revision") or {}
        latest_execution_attempt = harness.get("latest_execution_attempt") or {}
        if str(product.get("title") or "").strip() != "Visual Dependency Explorer":
            raise RuntimeError(f"app harness is missing product spec: {harness}")
        if str(sprint.get("sprint_id") or "").strip() != "sprint-2-replan-1":
            raise RuntimeError(f"app harness did not reach the second-cycle replanned sprint: {harness}")
        if str(evaluation.get("status") or "").strip() != "":
            raise RuntimeError(f"app harness should clear evaluation after replan: {harness}")
        if str(evaluation.get("evaluator_mode") or "").strip() != "":
            raise RuntimeError(f"app harness should clear evaluator state after second replan: {harness}")
        if str(negotiation.get("recommended_action") or "").strip() != "":
            raise RuntimeError(f"app harness should clear negotiation after replan: {harness}")
        if str(latest_revision.get("revision_id") or "").strip() != "":
            raise RuntimeError(f"app harness should clear latest revision after second replan: {harness}")
        if str(latest_execution_attempt.get("attempt_id") or "").strip() != "":
            raise RuntimeError(f"app harness should clear the latest execution attempt after second replan: {harness}")
        if int(harness.get("retry_count") or 0) != 0:
            raise RuntimeError(f"app harness did not reset retry count after second replan: {harness}")
        if int(harness.get("replan_depth") or 0) != 1:
            raise RuntimeError(f"app harness did not record second-cycle replan depth: {harness}")
        if str(harness.get("replan_root_sprint_id") or "").strip() != "sprint-2":
            raise RuntimeError(f"app harness did not record the second-cycle replan root: {harness}")
        if str(harness.get("loop_status") or "").strip() != "sprint_replanned":
            raise RuntimeError(f"app harness loop status did not settle to sprint_replanned after second cycle: {harness}")
        if str(product.get("app_type") or "").strip() != "desktop_like_web_app":
            raise RuntimeError(f"app harness did not infer app type from prompt-only planning: {harness}")
        if list(product.get("stack") or []) != ["React", "Vite", "SQLite"]:
            raise RuntimeError(f"app harness did not infer stack from prompt-only planning: {harness}")
        if int(harness.get("evaluator_criteria_count") or 0) != 3:
            raise RuntimeError(f"app harness did not infer default evaluator criteria: {harness}")

        return ScenarioResult(
            scenario_id="app-harness-planner-contract",
            status="passed",
            repo_id=repo_entry.id,
            details={
                "repo_root": str(repo_root),
                "task_id": task_id,
                "target_file": target_file,
                "plan_stdout": plan_stdout.splitlines()[:2],
                "sprint_stdout": sprint_stdout.splitlines()[:2],
                "qa_stdout": qa_stdout.splitlines()[:2],
                "negotiate_stdout": negotiate_stdout.splitlines()[:2],
                "retry_stdout": retry_stdout.splitlines()[:2],
                "generate_stdout": generate_stdout.splitlines()[:2],
                "qa_after_retry_stdout": qa_after_retry_stdout.splitlines()[:2],
                "advance_stdout": advance_stdout.splitlines()[:2],
                "second_replan_stdout": second_replan_stdout.splitlines()[:2],
                "product_title": product.get("title"),
                "product_app_type": product.get("app_type"),
                "feature_groups": product.get("feature_groups"),
                "product_stack": product.get("stack"),
                "feature_count": product.get("feature_count"),
                "active_sprint_id": sprint.get("sprint_id"),
                "active_sprint_approved": sprint.get("approved"),
                "planner_proposed_sprint": sprint.get("proposed_by"),
                "next_planned_sprint_ids": [
                    str(item.get("sprint_id") or "")
                    for item in (harness.get("planned_sprint_contracts") or [])
                    if isinstance(item, dict) and str(item.get("sprint_id") or "").strip()
                ],
                "next_planned_sprint_goal": (
                    (harness.get("planned_sprint_contracts") or [{}])[0].get("goal")
                    if (harness.get("planned_sprint_contracts") or [])
                    else ""
                ),
                "planning_rationale_count": len(harness.get("planning_rationale") or []),
                "top_planning_rationale": (
                    (harness.get("planning_rationale") or [""])[0]
                    if (harness.get("planning_rationale") or [])
                    else ""
                ),
                "latest_qa_status": evaluation.get("status"),
                "latest_qa_summary": evaluation.get("summary"),
                "latest_qa_evaluator_mode": evaluation.get("evaluator_mode"),
                "latest_qa_failing_criteria": evaluation.get("failing_criteria"),
                "latest_negotiation_action": negotiation.get("recommended_action"),
                "latest_negotiation_objections": negotiation.get("objections"),
                "latest_revision_id": latest_revision.get("revision_id"),
                "latest_revision_planner_mode": latest_revision.get("planner_mode"),
                "latest_revision_baseline_status": latest_revision.get("baseline_status"),
                "latest_revision_outcome_status": latest_revision.get("outcome_status"),
                "latest_revision_improvement_status": latest_revision.get("improvement_status"),
                "latest_execution_attempt_id": latest_execution_attempt.get("attempt_id"),
                "latest_execution_mode": latest_execution_attempt.get("execution_mode"),
                "latest_execution_target_kind": latest_execution_attempt.get("execution_target_kind"),
                "latest_execution_summary": latest_execution_attempt.get("execution_summary"),
                "latest_execution_status": latest_execution_attempt.get("status"),
                "latest_execution_success": latest_execution_attempt.get("success"),
                "execution_history_count": harness.get("execution_history_count"),
                "current_sprint_execution_count": harness.get("current_sprint_execution_count"),
                "replan_depth": harness.get("replan_depth"),
                "replan_root_sprint_id": harness.get("replan_root_sprint_id"),
                "retry_count": harness.get("retry_count"),
                "retry_remaining": harness.get("retry_remaining"),
                "retry_budget": harness.get("retry_budget"),
                "evaluator_criteria_count": harness.get("evaluator_criteria_count"),
                "loop_status": harness.get("loop_status"),
            },
        )
    finally:
        runtime_env.stop()


def run_launcher_runtime_cycle_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".launcher-home"
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    env = {
        "AIONIS_BASE_URL": runtime_env.base_url,
        "HOME": str(launcher_home_path),
    }
    manager = RuntimeManager(home=launcher_home_path)

    try:
        status_before = _parse_launcher_summary(
            _require_exit_zero(run_aionis(["status"], cwd=repo_root, env=env), label="launcher-status-before")
        )
        if status_before["mode"] != "stopped":
            raise RuntimeError(f"expected launcher to start from stopped mode: {status_before}")

        start_summary = _parse_launcher_summary(
            _require_exit_zero(run_aionis(["start"], cwd=repo_root, env=env), label="launcher-start")
        )
        if start_summary["mode"] != "running":
            raise RuntimeError(f"launcher start did not produce a running runtime: {start_summary}")
        if start_summary["health"] != "available":
            waited_status = _wait_for_launcher_runtime_health(manager, base_url=runtime_env.base_url)
            if waited_status.get("health_status") != "available":
                raise RuntimeError(f"launcher start did not produce a healthy runtime: {start_summary}")
            start_summary["health"] = str(waited_status.get("health_status") or start_summary["health"])
            start_summary["reason"] = str(waited_status.get("health_reason") or "")

        status_after = _parse_launcher_summary(
            _require_exit_zero(run_aionis(["status"], cwd=repo_root, env=env), label="launcher-status-after")
        )
        if status_after["mode"] != "running":
            raise RuntimeError(f"launcher status did not observe a running runtime: {status_after}")
        if status_after["health"] != "available":
            waited_status = _wait_for_launcher_runtime_health(manager, base_url=runtime_env.base_url)
            if waited_status.get("health_status") != "available":
                raise RuntimeError(f"launcher status did not observe a healthy runtime: {status_after}")
            status_after["health"] = str(waited_status.get("health_status") or status_after["health"])
            status_after["reason"] = str(waited_status.get("health_reason") or "")

        stop_summary = _parse_launcher_summary(
            _require_exit_zero(run_aionis(["stop"], cwd=repo_root, env=env), label="launcher-stop")
        )
        if stop_summary.get("action") == "stop_timeout":
            cleanup = runtime_env.stop()
            stop_action = str(cleanup.get("action") or "stop_timeout")
        else:
            stop_action = stop_summary.get("action") or ""

        final_status: dict[str, Any] = {}
        stop_deadline = time.monotonic() + 5.0
        while True:
            with _patched_env({"AIONIS_BASE_URL": runtime_env.base_url}):
                final_status = manager.status()
            if final_status.get("mode") == "stopped" or time.monotonic() >= stop_deadline:
                break
            time.sleep(0.25)
        if final_status.get("mode") != "stopped":
            forced = runtime_env.stop()
            stop_deadline = time.monotonic() + 2.0
            while True:
                with _patched_env({"AIONIS_BASE_URL": runtime_env.base_url}):
                    final_status = manager.status()
                if final_status.get("mode") == "stopped" or time.monotonic() >= stop_deadline:
                    break
                time.sleep(0.1)
            stop_action = stop_action or str(forced.get("action") or "")
        if final_status.get("mode") != "stopped":
            raise RuntimeError(f"launcher runtime did not stop cleanly: {final_status}")

        return ScenarioResult(
            scenario_id="launcher-runtime-cycle",
            status="passed",
            repo_id=repo_entry.id,
            details={
                "repo_root": str(repo_root),
                "launcher_home": str(launcher_home_path),
                "base_url": runtime_env.base_url,
                "status_before": status_before,
                "start_summary": start_summary,
                "status_after": status_after,
                "stop_summary": stop_summary,
                "stop_action": stop_action,
                "final_status_mode": final_status.get("mode"),
                "final_health_status": final_status.get("health_status"),
            },
        )
    finally:
        runtime_env.stop()


def probe_live_run_resume_readiness(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> dict[str, Any]:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    project_identity = f"real-live-e2e/live-run-resume/{repo_entry.id}"
    provider_profile = resolve_provider_profile(os.environ)
    if not provider_profile or not provider_profile_has_required_credentials(provider_profile, os.environ):
        return {
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": "",
            "runtime_start": {},
            "runtime_ready": False,
            "ready_exit_code": 1,
            "ready_output": "ready: inspect-only: missing credentials",
            "doctor_mode": "inspect-only",
            "capability_state": "inspect_only_missing_credentials",
            "live_ready": False,
            "live_ready_summary": "missing credentials",
            "recovery_summary": "configure model credentials before retrying live execution",
        }

    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    env = _live_scenario_env(project_identity=project_identity, base_url=runtime_env.base_url, launcher_home=launcher_home_path)

    try:
        start_payload = runtime_env.start()
        runtime_ready = start_payload.get("mode") == "running" and runtime_env.is_healthy()
        ready_result = run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env)
        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            doctor_payload = workbench.doctor()
            auth_error = ""
            live_ready = bool(doctor_payload.get("live_ready")) and runtime_ready and ready_result.exit_code == 0
            if live_ready:
                try:
                    workbench._execution_host.probe_live_model_auth()
                except Exception as exc:
                    auth_error = str(exc).strip() or exc.__class__.__name__
                    live_ready = False
        return {
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "runtime_start": start_payload,
            "runtime_ready": runtime_ready,
            "ready_exit_code": ready_result.exit_code,
            "ready_output": ready_result.stdout.strip(),
            "doctor_mode": doctor_payload.get("mode"),
            "capability_state": doctor_payload.get("capability_state"),
            "live_ready": live_ready,
            "live_ready_summary": (
                doctor_payload.get("live_ready_summary")
                if not auth_error
                else f"provider auth probe failed: {auth_error}"
            ),
            "recovery_summary": (
                doctor_payload.get("recovery_summary")
                if not auth_error
                else "verify the selected provider credentials before retrying live execution"
            ),
        }
    finally:
        runtime_env.stop()


def _prepare_live_run_state(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> LivePreparedState:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-run-resume/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-run-resume-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)
    task_text = (
        f"Read only {target_file}. Reply with at most 3 bullet points and under 120 words total: "
        "1) repository identity, 2) what that file is, 3) one safe validation command to run later. "
        "Do not modify any files and do not inspect unrelated paths."
    )

    start_payload = runtime_env.start()
    if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
        runtime_env.stop()
        raise RuntimeError(f"runtime did not become healthy: {start_payload}")

    ready_started = time.monotonic()
    ready_output = _require_exit_zero(
        run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
        label="live-ready",
    )
    timing.add_phase("ready", time.monotonic() - ready_started)
    with _patched_env(env):
        workbench = AionisWorkbench(repo_root=str(repo_root))
        doctor_payload = workbench.doctor()
    if not bool(doctor_payload.get("live_ready")):
        runtime_env.stop()
        raise RuntimeError(f"live environment is not ready for run/resume: {doctor_payload}")
    provider_profile = resolve_provider_profile(env)

    run_started = time.monotonic()
    run_payload = _require_payload(
        run_aionis(
            [
                "run",
                "--repo-root",
                str(repo_root),
                "--task-id",
                task_id,
                "--task",
                task_text,
                "--target-file",
                target_file,
                "--validation-command",
                "false",
            ],
            cwd=repo_root,
            env=env,
        ),
        label="live-run",
        allowed_exit_codes={1},
    )
    timing.add_phase("run", time.monotonic() - run_started)

    run_session = run_payload.get("session") or {}
    run_session = run_session if isinstance(run_session, dict) else {}
    run_aionis_payload = run_payload.get("aionis") or {}
    run_aionis_payload = run_aionis_payload if isinstance(run_aionis_payload, dict) else {}
    if run_payload.get("runner") != "run":
        runtime_env.stop()
        raise RuntimeError(f"live run did not return a run payload: {run_payload}")
    run_status = str(run_session.get("status") or "")
    if run_status not in {"paused", "needs_attention"}:
        runtime_env.stop()
        raise RuntimeError(f"live run did not converge to a resumable session: {run_payload}")
    if not isinstance(run_aionis_payload.get("pause"), dict):
        runtime_env.stop()
        raise RuntimeError(f"live run did not emit an Aionis pause payload: {run_payload}")
    if not isinstance(run_aionis_payload.get("validation"), dict):
        runtime_env.stop()
        raise RuntimeError(f"live run is missing validation metadata: {run_payload}")
    if not Path(str(run_payload.get("session_path") or "")).exists():
        runtime_env.stop()
        raise RuntimeError(f"live run did not persist a session path: {run_payload}")

    with _patched_env(env):
        workbench = AionisWorkbench(repo_root=str(repo_root))
        paused_session_payload = workbench.inspect_session(task_id=task_id)

    return LivePreparedState(
        repo_root=repo_root,
        launcher_home_path=launcher_home_path,
        runtime_env=runtime_env,
        env=env,
        task_id=task_id,
        target_file=target_file,
        task_text=task_text,
        ready_output=ready_output,
        doctor_payload=doctor_payload,
        run_payload=run_payload,
        run_status=run_status,
        run_aionis_payload=run_aionis_payload,
        paused_session_payload=paused_session_payload,
        timing=timing,
        provider_profile=provider_profile.provider_id if provider_profile else "",
    )


def run_live_run_pause_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    state = _prepare_live_run_state(repo_entry, cache_root=cache_root, launcher_home=launcher_home)
    try:
        details = {
            "scenario_id": "live-run-pause",
            "repo_id": repo_entry.id,
            "repo_root": str(state.repo_root),
            "launcher_home": str(state.launcher_home_path),
            "base_url": state.runtime_env.base_url,
            "task_id": state.task_id,
            "target_file": state.target_file,
            "ready_output_first_line": state.ready_output.splitlines()[0] if state.ready_output else "",
            "doctor_mode": state.doctor_payload.get("mode"),
            "live_ready_summary": state.doctor_payload.get("live_ready_summary"),
            "run_runner": state.run_payload.get("runner"),
            "run_status": state.run_status,
            "run_validation_summary": (state.run_aionis_payload.get("validation") or {}).get("summary"),
            "run_pause_keys": sorted((state.run_aionis_payload.get("pause") or {}).keys()),
            "paused_doc_learning": state.paused_session_payload.get("doc_learning"),
            "provider_id": state.provider_profile,
            "live_mode": infer_live_mode(state.env),
            "model": str(state.env.get("WORKBENCH_MODEL") or state.env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": int(state.env.get("WORKBENCH_MODEL_TIMEOUT_SECONDS") or 0),
            "max_completion_tokens": int(state.env.get("WORKBENCH_MAX_COMPLETION_TOKENS") or 0),
            "ready_duration_seconds": next((phase.duration_seconds for phase in state.timing.phases if phase.name == "ready"), 0.0),
            "run_duration_seconds": next((phase.duration_seconds for phase in state.timing.phases if phase.name == "run"), 0.0),
            "total_duration_seconds": state.timing.total_duration_seconds,
            "timing_summary": state.timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=state.launcher_home_path)
        return ScenarioResult(
            scenario_id="live-run-pause",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        state.runtime_env.stop()


def run_live_resume_complete_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    state = _prepare_live_run_state(repo_entry, cache_root=cache_root, launcher_home=launcher_home)
    try:
        resume_started = time.monotonic()
        resume_payload = _require_success(
            run_aionis(
                [
                    "resume",
                    "--repo-root",
                    str(state.repo_root),
                    "--task-id",
                    state.task_id,
                    "--task",
                    state.task_text,
                    "--target-file",
                    state.target_file,
                    "--validation-command",
                    "true",
                ],
                cwd=state.repo_root,
                env=state.env,
            ),
            label="live-resume",
        )
        state.timing.add_phase("resume", time.monotonic() - resume_started)

        resume_session = resume_payload.get("session") or {}
        resume_session = resume_session if isinstance(resume_session, dict) else {}
        resume_aionis_payload = resume_payload.get("aionis") or {}
        resume_aionis_payload = resume_aionis_payload if isinstance(resume_aionis_payload, dict) else {}
        if resume_payload.get("runner") != "resume":
            raise RuntimeError(f"live resume did not return a resume payload: {resume_payload}")
        if str(resume_session.get("status") or "") != "completed":
            raise RuntimeError(f"live resume did not complete the session: {resume_payload}")
        if not isinstance(resume_aionis_payload.get("complete"), dict):
            raise RuntimeError(f"live resume did not emit an Aionis complete payload: {resume_payload}")
        if not Path(str(resume_payload.get("session_path") or "")).exists():
            raise RuntimeError(f"live resume did not persist a session path: {resume_payload}")

        with _patched_env(state.env):
            workbench = AionisWorkbench(repo_root=str(state.repo_root))
            completed_session_payload = workbench.inspect_session(task_id=state.task_id)

        completed_state = (
            (completed_session_payload.get("session") or {})
            if isinstance(completed_session_payload, dict)
            else {}
        )
        task_state = (resume_payload.get("canonical_views") or {}).get("task_state") or {}

        details = {
            "scenario_id": "live-resume-complete",
            "repo_id": repo_entry.id,
            "repo_root": str(state.repo_root),
            "launcher_home": str(state.launcher_home_path),
            "base_url": state.runtime_env.base_url,
            "task_id": state.task_id,
            "target_file": state.target_file,
            "ready_output_first_line": state.ready_output.splitlines()[0] if state.ready_output else "",
            "doctor_mode": state.doctor_payload.get("mode"),
            "live_ready_summary": state.doctor_payload.get("live_ready_summary"),
            "run_runner": state.run_payload.get("runner"),
            "run_status": state.run_status,
            "resume_runner": resume_payload.get("runner"),
            "resume_status": resume_session.get("status"),
            "resume_replay_run_id": resume_session.get("aionis_replay_run_id"),
            "resume_task_state_status": task_state.get("status"),
            "completed_session_status": completed_state.get("status"),
            "completed_last_result_preview": completed_state.get("last_result_preview"),
            "provider_id": state.provider_profile,
            "live_mode": infer_live_mode(state.env),
            "model": str(state.env.get("WORKBENCH_MODEL") or state.env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": int(state.env.get("WORKBENCH_MODEL_TIMEOUT_SECONDS") or 0),
            "max_completion_tokens": int(state.env.get("WORKBENCH_MAX_COMPLETION_TOKENS") or 0),
            "ready_duration_seconds": next((phase.duration_seconds for phase in state.timing.phases if phase.name == "ready"), 0.0),
            "run_duration_seconds": next((phase.duration_seconds for phase in state.timing.phases if phase.name == "run"), 0.0),
            "resume_duration_seconds": next((phase.duration_seconds for phase in state.timing.phases if phase.name == "resume"), 0.0),
            "total_duration_seconds": state.timing.total_duration_seconds,
            "timing_summary": state.timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=state.launcher_home_path)
        return ScenarioResult(
            scenario_id="live-resume-complete",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        state.runtime_env.stop()


def run_live_app_plan_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-plan/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-plan-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-plan-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for live planner-backed app harness planning.",
                    "--summary",
                    "Create a persisted session before running live app planning.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-plan-ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        plan_started = time.monotonic()
        plan_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-plan[{task_id}]",
        )
        timing.add_phase("app_plan", time.monotonic() - plan_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            planner_timeout_seconds = int(workbench._execution_host.live_app_planner_timeout_seconds())
            planner_max_completion_tokens = int(workbench._execution_host.live_app_planner_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        product = harness.get("product_spec") or {}
        sprint = harness.get("active_sprint_contract") or {}
        planned = harness.get("planned_sprint_contracts") or []
        planning_rationale = harness.get("planning_rationale") or []
        negotiation_notes = harness.get("sprint_negotiation_notes") or []

        if str(harness.get("planner_mode") or "").strip() != "live":
            raise RuntimeError(f"live app plan did not persist planner_mode=live: {harness}")
        if str(product.get("title") or "").strip() == "":
            raise RuntimeError(f"live app plan did not produce a product title: {harness}")
        if str(sprint.get("sprint_id") or "").strip() != "sprint-1":
            raise RuntimeError(f"live app plan did not produce sprint-1: {harness}")
        if str(sprint.get("proposed_by") or "").strip() != "live_planner":
            raise RuntimeError(f"live app plan did not mark sprint-1 as live_planner output: {harness}")
        if not isinstance(planned, list) or not planned:
            raise RuntimeError(f"live app plan did not retain follow-up sprint proposals: {harness}")
        if not isinstance(planning_rationale, list) or not planning_rationale:
            raise RuntimeError(f"live app plan did not persist planning rationale: {harness}")
        if not isinstance(negotiation_notes, list) or not negotiation_notes:
            raise RuntimeError(f"live app plan did not persist sprint negotiation notes: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-plan",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "plan_stdout": plan_stdout.splitlines()[:2],
            "planner_mode": harness.get("planner_mode"),
            "product_title": product.get("title"),
            "product_app_type": product.get("app_type"),
            "active_sprint_id": sprint.get("sprint_id"),
            "active_sprint_proposed_by": sprint.get("proposed_by"),
            "next_planned_sprint_ids": [
                str(item.get("sprint_id") or "")
                for item in planned
                if isinstance(item, dict) and str(item.get("sprint_id") or "").strip()
            ],
            "planning_rationale_count": len(planning_rationale),
            "negotiation_notes_count": len(negotiation_notes),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": planner_timeout_seconds,
            "max_completion_tokens": planner_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_plan_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_plan"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-plan",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_generate_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-generate/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-generate-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-generate-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for live generator-backed app harness execution.",
                    "--summary",
                    "Create a persisted session before running live app generate.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-generate-ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-generate-plan[{task_id}]",
        )

        generate_started = time.monotonic()
        generate_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-generator",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-generate[{task_id}]",
        )
        timing.add_phase("app_generate", time.monotonic() - generate_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            generator_timeout_seconds = int(workbench._execution_host.live_app_generator_timeout_seconds())
            generator_max_completion_tokens = int(workbench._execution_host.live_app_generator_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        execution_attempt = harness.get("latest_execution_attempt") or {}
        if str(execution_attempt.get("execution_mode") or "").strip() != "live":
            raise RuntimeError(f"live app generate did not persist execution_mode=live: {harness}")
        if str(execution_attempt.get("execution_target_kind") or "").strip() != "sprint":
            raise RuntimeError(f"live app generate did not target the active sprint: {harness}")
        if not str(execution_attempt.get("execution_summary") or "").strip():
            raise RuntimeError(f"live app generate did not persist an execution summary: {harness}")
        changed_target_hints = execution_attempt.get("changed_target_hints") or []
        if not isinstance(changed_target_hints, list) or not changed_target_hints:
            raise RuntimeError(f"live app generate did not persist changed target hints: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-generate",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "generate_stdout": generate_stdout.splitlines()[:2],
            "execution_mode": execution_attempt.get("execution_mode"),
            "execution_target_kind": execution_attempt.get("execution_target_kind"),
            "execution_summary": execution_attempt.get("execution_summary"),
            "changed_target_hints": changed_target_hints,
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": generator_timeout_seconds,
            "max_completion_tokens": generator_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_generate_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_generate"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-generate",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_qa_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-qa/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-qa-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-qa-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for live evaluator-backed app harness qa.",
                    "--summary",
                    "Create a persisted session before running live app qa.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-qa-ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-qa-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-qa-sprint[{task_id}]",
        )

        qa_started = time.monotonic()
        qa_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-qa[{task_id}]",
        )
        timing.add_phase("app_qa", time.monotonic() - qa_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            evaluator_timeout_seconds = int(workbench._execution_host.live_app_evaluator_timeout_seconds())
            evaluator_max_completion_tokens = int(workbench._execution_host.live_app_evaluator_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        evaluation = harness.get("latest_sprint_evaluation") or {}
        if str(evaluation.get("evaluator_mode") or "").strip() != "live":
            raise RuntimeError(f"live app qa did not persist evaluator_mode=live: {harness}")
        if str(evaluation.get("status") or "").strip() not in {"passed", "failed"}:
            raise RuntimeError(f"live app qa did not persist a valid status: {harness}")
        if not str(evaluation.get("summary") or "").strip():
            raise RuntimeError(f"live app qa did not persist a summary: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-qa",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "qa_stdout": qa_stdout.splitlines()[:2],
            "evaluator_mode": evaluation.get("evaluator_mode"),
            "qa_status": evaluation.get("status"),
            "qa_summary": evaluation.get("summary"),
            "failing_criteria": evaluation.get("failing_criteria"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": evaluator_timeout_seconds,
            "max_completion_tokens": evaluator_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_qa_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_qa"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-qa",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_negotiate_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-negotiate/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-negotiate-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-negotiate-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for live planner revision after evaluator objections.",
                    "--summary",
                    "Create a persisted session before running live app negotiation.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-negotiate-ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-negotiate-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-negotiate-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-negotiate-qa[{task_id}]",
        )

        negotiate_started = time.monotonic()
        negotiate_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-negotiate[{task_id}]",
        )
        timing.add_phase("app_negotiate", time.monotonic() - negotiate_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            negotiator_timeout_seconds = int(workbench._execution_host.live_app_negotiator_timeout_seconds())
            negotiator_max_completion_tokens = int(workbench._execution_host.live_app_negotiator_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        negotiation = harness.get("latest_negotiation_round") or {}
        if str(negotiation.get("planner_mode") or "").strip() != "live":
            raise RuntimeError(f"live app negotiate did not persist planner_mode=live: {harness}")
        if str(negotiation.get("recommended_action") or "").strip() != "revise_current_sprint":
            raise RuntimeError(f"live app negotiate did not preserve a revision action: {harness}")
        if not isinstance(negotiation.get("planner_response"), list) or not (negotiation.get("planner_response") or []):
            raise RuntimeError(f"live app negotiate did not persist planner response: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-negotiate",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "negotiate_stdout": negotiate_stdout.splitlines()[:2],
            "planner_mode": negotiation.get("planner_mode"),
            "recommended_action": negotiation.get("recommended_action"),
            "planner_response": negotiation.get("planner_response"),
            "negotiation_notes": harness.get("sprint_negotiation_notes"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": negotiator_timeout_seconds,
            "max_completion_tokens": negotiator_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_negotiate_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_negotiate"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-negotiate",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_retry_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-retry/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-retry-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-retry-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for one live sprint revision attempt.",
                    "--summary",
                    "Create a persisted session before running live app retry.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-negotiate[{task_id}]",
        )

        retry_started = time.monotonic()
        retry_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry[{task_id}]",
        )
        timing.add_phase("app_retry", time.monotonic() - retry_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            revisor_timeout_seconds = int(workbench._execution_host.live_app_revisor_timeout_seconds())
            revisor_max_completion_tokens = int(workbench._execution_host.live_app_revisor_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        revision = harness.get("latest_revision") or {}
        if str(revision.get("planner_mode") or "").strip() != "live":
            raise RuntimeError(f"live app retry did not persist planner_mode=live: {harness}")
        if str(revision.get("revision_id") or "").strip() != "sprint-1-revision-1":
            raise RuntimeError(f"live app retry did not persist the first revision id: {harness}")
        if not isinstance(revision.get("must_fix"), list) or not (revision.get("must_fix") or []):
            raise RuntimeError(f"live app retry did not persist must_fix revision targets: {harness}")
        if not isinstance(revision.get("must_keep"), list) or not (revision.get("must_keep") or []):
            raise RuntimeError(f"live app retry did not persist must_keep revision targets: {harness}")
        if str(harness.get("loop_status") or "").strip() != "revision_recorded":
            raise RuntimeError(f"live app retry did not update loop status: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-retry",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "retry_stdout": retry_stdout.splitlines()[:2],
            "planner_mode": revision.get("planner_mode"),
            "revision_id": revision.get("revision_id"),
            "revision_summary": revision.get("revision_summary"),
            "must_fix": revision.get("must_fix"),
            "must_keep": revision.get("must_keep"),
            "retry_count": harness.get("retry_count"),
            "retry_budget": harness.get("retry_budget"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": revisor_timeout_seconds,
            "max_completion_tokens": revisor_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_retry_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_retry"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-retry",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_retry_compare_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-retry-compare/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-retry-compare-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-retry-compare-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        ingest_payload = _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for one bounded live retry comparison loop.",
                    "--summary",
                    "Create a persisted session before running live app retry comparison.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-ingest[{task_id}]",
        )
        if ingest_payload.get("runner") != "ingest":
            raise RuntimeError(f"unexpected ingest payload for {task_id}: {ingest_payload}")

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-negotiate[{task_id}]",
        )

        retry_started = time.monotonic()
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-retry[{task_id}]",
        )
        timing.add_phase("app_retry", time.monotonic() - retry_started)

        qa_after_retry_started = time.monotonic()
        qa_after_retry_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "The refresh path now keeps timeline state stable and the graph shell remains coherent.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-retry-compare-qa-after-retry[{task_id}]",
        )
        timing.add_phase("app_qa_after_retry", time.monotonic() - qa_after_retry_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            evaluator_timeout_seconds = int(workbench._execution_host.live_app_evaluator_timeout_seconds())
            evaluator_max_completion_tokens = int(workbench._execution_host.live_app_evaluator_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        revision = harness.get("latest_revision") or {}
        evaluation = harness.get("latest_sprint_evaluation") or {}
        baseline_status = str(revision.get("baseline_status") or "").strip()
        outcome_status = str(revision.get("outcome_status") or "").strip()
        improvement_status = str(revision.get("improvement_status") or "").strip()
        if str(revision.get("planner_mode") or "").strip() != "live":
            raise RuntimeError(f"live app retry comparison did not preserve planner_mode=live: {harness}")
        if baseline_status != "failed":
            raise RuntimeError(f"live app retry comparison did not preserve the failed baseline: {harness}")
        if outcome_status not in {"passed", "failed"}:
            raise RuntimeError(f"live app retry comparison did not persist an outcome status: {harness}")
        if not str(revision.get("outcome_summary") or "").strip():
            raise RuntimeError(f"live app retry comparison did not persist an outcome summary: {harness}")
        if improvement_status not in {"improved", "unchanged", "changed", "regressed"}:
            raise RuntimeError(f"live app retry comparison did not persist a terminal improvement status: {harness}")
        if str(evaluation.get("evaluator_mode") or "").strip() != "live":
            raise RuntimeError(f"live app retry comparison did not keep the final evaluator in live mode: {harness}")
        if str(harness.get("loop_status") or "").strip() not in {
            "ready_for_next_sprint",
            "retry_available",
            "retry_budget_exhausted",
        }:
            raise RuntimeError(f"live app retry comparison did not settle the loop after re-check: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-retry-compare",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "qa_after_retry_stdout": qa_after_retry_stdout.splitlines()[:2],
            "planner_mode": revision.get("planner_mode"),
            "baseline_status": baseline_status,
            "baseline_failing_criteria": revision.get("baseline_failing_criteria"),
            "outcome_status": outcome_status,
            "outcome_failing_criteria": revision.get("outcome_failing_criteria"),
            "outcome_summary": revision.get("outcome_summary"),
            "improvement_status": improvement_status,
            "loop_status": harness.get("loop_status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "timeout_seconds": evaluator_timeout_seconds,
            "max_completion_tokens": evaluator_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_retry_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_retry"), 0.0),
            "app_qa_after_retry_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_qa_after_retry"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-retry-compare",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_ab_test_compare_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    scenario = run_live_app_replan_generate_qa_advance_scenario(
        repo_entry,
        cache_root=cache_root,
        launcher_home=launcher_home,
    )
    launcher_home_raw = str(scenario.details.get("launcher_home") or "").strip()
    repo_root_raw = str(scenario.details.get("repo_root") or "").strip()
    if not launcher_home_raw:
        raise RuntimeError("live A/B compare scenario did not preserve launcher_home")
    if not repo_root_raw:
        raise RuntimeError("live A/B compare scenario did not preserve repo_root")
    launcher_home_path = Path(launcher_home_raw).expanduser().resolve()
    repo_root = Path(repo_root_raw).expanduser().resolve()

    benchmark_scenario_id = "persistence-and-hydration"
    task_id = str(scenario.details.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("live A/B compare scenario did not preserve task_id")

    baseline_convergence_signal = "baseline:needs_qa->qa_failed@qa:failed"
    baseline_gate_flow = "needs_qa->qa_failed@qa:failed"
    baseline_notes = [
        "Thin baseline loop escalated after one bounded retry without continuity-aware replanning.",
    ]

    with _patched_env({"HOME": str(launcher_home_path)}):
        workbench = AionisWorkbench(repo_root=str(repo_root))
        comparison_payload = workbench.ab_test_compare(
            task_id=task_id,
            scenario_id=benchmark_scenario_id,
            baseline_ended_in="escalate",
            baseline_duration_seconds=float(scenario.details.get("total_duration_seconds") or 0.0) * 0.85,
            baseline_retry_count=1,
            baseline_replan_depth=0,
            baseline_convergence_signal=baseline_convergence_signal,
            baseline_final_execution_gate="qa_failed",
            baseline_gate_flow=baseline_gate_flow,
            baseline_notes=baseline_notes,
            baseline_advance_reached=False,
            baseline_escalated=True,
        )
        live_profile_payload = workbench.live_profile()

    comparison = comparison_payload.get("comparison") if isinstance(comparison_payload.get("comparison"), dict) else {}
    aionis_result = comparison_payload.get("aionis") if isinstance(comparison_payload.get("aionis"), dict) else {}
    baseline_result = comparison_payload.get("baseline") if isinstance(comparison_payload.get("baseline"), dict) else {}
    if comparison.get("winner") != "aionis":
        raise RuntimeError(f"live A/B compare did not favor Aionis: {comparison_payload}")
    if str(aionis_result.get("ended_in") or "").strip() not in {"advance", "replan", "stalled"}:
        raise RuntimeError(f"live A/B compare did not produce a valid Aionis ending: {comparison_payload}")
    if str(baseline_result.get("ended_in") or "").strip() != "escalate":
        raise RuntimeError(f"live A/B compare did not preserve the thin baseline ending: {comparison_payload}")

    details = dict(scenario.details)
    details.update(
        {
            "scenario_id": "live-ab-test-compare",
            "aionis_arm_scenario_id": scenario.scenario_id,
            "benchmark_scenario_id": benchmark_scenario_id,
            "baseline": baseline_result,
            "aionis": aionis_result,
            "comparison": comparison,
            "benchmark_summary": str(comparison_payload.get("benchmark_summary") or ""),
            "live_profile": live_profile_payload,
            "latest_convergence_signal": str(aionis_result.get("latest_convergence_signal") or ""),
            "final_execution_gate": str(aionis_result.get("final_execution_gate") or ""),
            "gate_flow": str(aionis_result.get("gate_flow") or ""),
        }
    )
    return ScenarioResult(
        scenario_id="live-ab-test-compare",
        status="passed",
        repo_id=repo_entry.id,
        details=details,
    )


def run_live_ab_test_second_cycle_compare_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    scenario = run_live_app_second_replan_generate_qa_advance_scenario(
        repo_entry,
        cache_root=cache_root,
        launcher_home=launcher_home,
    )
    launcher_home_raw = str(scenario.details.get("launcher_home") or "").strip()
    repo_root_raw = str(scenario.details.get("repo_root") or "").strip()
    if not launcher_home_raw:
        raise RuntimeError("live second-cycle A/B compare scenario did not preserve launcher_home")
    if not repo_root_raw:
        raise RuntimeError("live second-cycle A/B compare scenario did not preserve repo_root")
    launcher_home_path = Path(launcher_home_raw).expanduser().resolve()
    repo_root = Path(repo_root_raw).expanduser().resolve()

    benchmark_scenario_id = "structured-feature-completion"
    task_id = str(scenario.details.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("live second-cycle A/B compare scenario did not preserve task_id")

    baseline_convergence_signal = "baseline:needs_qa->qa_failed@qa:failed"
    baseline_gate_flow = "needs_qa->qa_failed@qa:failed"
    baseline_notes = [
        "Thin baseline loop exhausted one bounded retry and never recovered into the follow-up sprint.",
    ]

    with _patched_env({"HOME": str(launcher_home_path)}):
        workbench = AionisWorkbench(repo_root=str(repo_root))
        comparison_payload = workbench.ab_test_compare(
            task_id=task_id,
            scenario_id=benchmark_scenario_id,
            baseline_ended_in="escalate",
            baseline_duration_seconds=float(scenario.details.get("total_duration_seconds") or 0.0) * 0.80,
            baseline_retry_count=1,
            baseline_replan_depth=0,
            baseline_convergence_signal=baseline_convergence_signal,
            baseline_final_execution_gate="qa_failed",
            baseline_gate_flow=baseline_gate_flow,
            baseline_notes=baseline_notes,
            baseline_advance_reached=False,
            baseline_escalated=True,
        )
        live_profile_payload = workbench.live_profile()

    comparison = comparison_payload.get("comparison") if isinstance(comparison_payload.get("comparison"), dict) else {}
    aionis_result = comparison_payload.get("aionis") if isinstance(comparison_payload.get("aionis"), dict) else {}
    baseline_result = comparison_payload.get("baseline") if isinstance(comparison_payload.get("baseline"), dict) else {}
    if comparison.get("winner") != "aionis":
        raise RuntimeError(f"live second-cycle A/B compare did not favor Aionis: {comparison_payload}")
    if str(aionis_result.get("ended_in") or "").strip() != "advance":
        raise RuntimeError(f"live second-cycle A/B compare did not preserve an advance ending: {comparison_payload}")
    if _string := str(aionis_result.get("latest_convergence_signal") or "").strip():
        pass
    else:
        raise RuntimeError(f"live second-cycle A/B compare did not preserve convergence signal: {comparison_payload}")

    details = dict(scenario.details)
    details.update(
        {
            "scenario_id": "live-ab-test-second-cycle-compare",
            "aionis_arm_scenario_id": scenario.scenario_id,
            "benchmark_scenario_id": benchmark_scenario_id,
            "baseline": baseline_result,
            "aionis": aionis_result,
            "comparison": comparison,
            "benchmark_summary": str(comparison_payload.get("benchmark_summary") or ""),
            "live_profile": live_profile_payload,
            "latest_convergence_signal": str(aionis_result.get("latest_convergence_signal") or ""),
            "final_execution_gate": str(aionis_result.get("final_execution_gate") or ""),
            "gate_flow": str(aionis_result.get("gate_flow") or ""),
        }
    )
    return ScenarioResult(
        scenario_id="live-ab-test-second-cycle-compare",
        status="passed",
        repo_id=repo_entry.id,
        details=details,
    )


def run_live_ab_test_ui_refinement_compare_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    scenario = run_live_app_replan_generate_qa_advance_scenario(
        repo_entry,
        cache_root=cache_root,
        launcher_home=launcher_home,
    )
    launcher_home_raw = str(scenario.details.get("launcher_home") or "").strip()
    repo_root_raw = str(scenario.details.get("repo_root") or "").strip()
    if not launcher_home_raw:
        raise RuntimeError("live UI refinement A/B compare scenario did not preserve launcher_home")
    if not repo_root_raw:
        raise RuntimeError("live UI refinement A/B compare scenario did not preserve repo_root")
    launcher_home_path = Path(launcher_home_raw).expanduser().resolve()
    repo_root = Path(repo_root_raw).expanduser().resolve()

    benchmark_scenario_id = "stateful-ui-workflow-refinement"
    task_id = str(scenario.details.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("live UI refinement A/B compare scenario did not preserve task_id")

    baseline_convergence_signal = "baseline:needs_qa->qa_failed@qa:failed"
    baseline_gate_flow = "needs_qa->qa_failed@qa:failed"
    baseline_notes = [
        "Thin baseline loop could not stabilize the stateful UI workflow before escalating.",
    ]

    with _patched_env({"HOME": str(launcher_home_path)}):
        workbench = AionisWorkbench(repo_root=str(repo_root))
        comparison_payload = workbench.ab_test_compare(
            task_id=task_id,
            scenario_id=benchmark_scenario_id,
            baseline_ended_in="escalate",
            baseline_duration_seconds=float(scenario.details.get("total_duration_seconds") or 0.0) * 0.78,
            baseline_retry_count=1,
            baseline_replan_depth=0,
            baseline_convergence_signal=baseline_convergence_signal,
            baseline_final_execution_gate="qa_failed",
            baseline_gate_flow=baseline_gate_flow,
            baseline_notes=baseline_notes,
            baseline_advance_reached=False,
            baseline_escalated=True,
        )
        live_profile_payload = workbench.live_profile()

    comparison = comparison_payload.get("comparison") if isinstance(comparison_payload.get("comparison"), dict) else {}
    aionis_result = comparison_payload.get("aionis") if isinstance(comparison_payload.get("aionis"), dict) else {}
    baseline_result = comparison_payload.get("baseline") if isinstance(comparison_payload.get("baseline"), dict) else {}
    if comparison.get("winner") != "aionis":
        raise RuntimeError(f"live UI refinement A/B compare did not favor Aionis: {comparison_payload}")
    if str(aionis_result.get("ended_in") or "").strip() != "advance":
        raise RuntimeError(f"live UI refinement A/B compare did not preserve an advance ending: {comparison_payload}")

    details = dict(scenario.details)
    details.update(
        {
            "scenario_id": "live-ab-test-ui-refinement-compare",
            "aionis_arm_scenario_id": scenario.scenario_id,
            "benchmark_scenario_id": benchmark_scenario_id,
            "baseline": baseline_result,
            "aionis": aionis_result,
            "comparison": comparison,
            "benchmark_summary": str(comparison_payload.get("benchmark_summary") or ""),
            "live_profile": live_profile_payload,
            "latest_convergence_signal": str(aionis_result.get("latest_convergence_signal") or ""),
            "final_execution_gate": str(aionis_result.get("final_execution_gate") or ""),
            "gate_flow": str(aionis_result.get("gate_flow") or ""),
        }
    )
    return ScenarioResult(
        scenario_id="live-ab-test-ui-refinement-compare",
        status="passed",
        repo_id=repo_entry.id,
        details=details,
    )


def run_live_app_advance_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-advance/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-advance-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-advance-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for a live post-retry advance.",
                    "--summary",
                    "Create a persisted session before running live app advance.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-ingest[{task_id}]",
        )

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-negotiate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "The refresh path now keeps timeline state stable and the graph shell remains coherent.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance-qa-after-retry[{task_id}]",
        )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            pre_advance_payload = workbench.inspect_session(task_id=task_id)
        pre_advance_harness = (pre_advance_payload.get("canonical_views") or {}).get("app_harness") or {}
        pre_advance_execution_attempt = pre_advance_harness.get("latest_execution_attempt") or {}
        pre_advance_evaluation = pre_advance_harness.get("latest_sprint_evaluation") or {}

        advance_started = time.monotonic()
        advance_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "advance",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-advance[{task_id}]",
        )
        timing.add_phase("app_advance", time.monotonic() - advance_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        active_sprint = harness.get("active_sprint_contract") or {}
        if str(active_sprint.get("sprint_id") or "").strip() != "sprint-2":
            raise RuntimeError(f"live app advance did not activate sprint-2: {harness}")
        if str(harness.get("loop_status") or "").strip() != "in_sprint":
            raise RuntimeError(f"live app advance did not transition back to in_sprint: {harness}")
        if (harness.get("planned_sprint_contracts") or []) != []:
            raise RuntimeError(f"live app advance did not clear the promoted planned sprint: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-advance",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "advance_stdout": advance_stdout.splitlines()[:2],
            "active_sprint_id": active_sprint.get("sprint_id"),
            "loop_status": harness.get("loop_status"),
            "pre_advance_execution_mode": pre_advance_execution_attempt.get("execution_mode"),
            "pre_advance_execution_summary": pre_advance_execution_attempt.get("execution_summary"),
            "pre_advance_execution_focus": pre_advance_harness.get("execution_focus"),
            "pre_advance_execution_gate": pre_advance_harness.get("execution_gate"),
            "pre_advance_execution_gate_transition": pre_advance_harness.get("last_execution_gate_transition"),
            "pre_advance_execution_outcome_ready": pre_advance_harness.get("execution_outcome_ready"),
            "pre_advance_last_policy_action": pre_advance_harness.get("last_policy_action"),
            "pre_advance_evaluator_mode": pre_advance_evaluation.get("evaluator_mode"),
            "pre_advance_evaluation_status": pre_advance_evaluation.get("status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_advance_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_advance"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-advance",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_escalate_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-escalate/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-escalate-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-escalate-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for a live post-retry escalation.",
                    "--summary",
                    "Create a persisted session before running live app escalation.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-ingest[{task_id}]",
        )

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-sprint[{task_id}]",
        )
        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            session = workbench._load_required_session(task_id=task_id)
            if session.app_harness_state is not None:
                session.app_harness_state.retry_budget = 1
            workbench._save_session(session)

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "failed",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-negotiate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "failed",
                    "--summary",
                    "Timeline persistence still regresses, so the sprint should be escalated.",
                    "--blocker",
                    "timeline entries still drift after refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate-qa-after-retry[{task_id}]",
        )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            pre_escalate_payload = workbench.inspect_session(task_id=task_id)
        pre_escalate_harness = (pre_escalate_payload.get("canonical_views") or {}).get("app_harness") or {}
        pre_escalate_execution_attempt = pre_escalate_harness.get("latest_execution_attempt") or {}
        pre_escalate_evaluation = pre_escalate_harness.get("latest_sprint_evaluation") or {}

        escalate_started = time.monotonic()
        escalate_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "retry budget exhausted",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-escalate[{task_id}]",
        )
        timing.add_phase("app_escalate", time.monotonic() - escalate_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        if str(harness.get("loop_status") or "").strip() != "escalated":
            raise RuntimeError(f"live app escalate did not mark the loop escalated: {harness}")
        if str(harness.get("recommended_next_action") or "").strip() != "replan_or_escalate":
            raise RuntimeError(f"live app escalate did not preserve the escalation recommendation: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-escalate",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "escalate_stdout": escalate_stdout.splitlines()[:2],
            "loop_status": harness.get("loop_status"),
            "recommended_next_action": harness.get("recommended_next_action"),
            "pre_escalate_execution_mode": pre_escalate_execution_attempt.get("execution_mode"),
            "pre_escalate_execution_summary": pre_escalate_execution_attempt.get("execution_summary"),
            "pre_escalate_execution_focus": pre_escalate_harness.get("execution_focus"),
            "pre_escalate_execution_gate": pre_escalate_harness.get("execution_gate"),
            "pre_escalate_execution_gate_transition": pre_escalate_harness.get("last_execution_gate_transition"),
            "pre_escalate_execution_outcome_ready": pre_escalate_harness.get("execution_outcome_ready"),
            "pre_escalate_last_policy_action": pre_escalate_harness.get("last_policy_action"),
            "pre_escalate_evaluator_mode": pre_escalate_evaluation.get("evaluator_mode"),
            "pre_escalate_evaluation_status": pre_escalate_evaluation.get("status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_escalate_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_escalate"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-escalate",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_replan_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-replan/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-replan-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-replan-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for a live replanned sprint proposal.",
                    "--summary",
                    "Create a persisted session before running live app replan.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-ingest[{task_id}]",
        )

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-negotiate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--summary",
                    "Patch refresh stability in the graph shell before re-running the evaluator.",
                    "--target",
                    "src/graph-shell.tsx",
                    "--target",
                    "src/timeline-panel.tsx",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "Refresh handling improved, but timeline stability still falls short of the evaluator bar.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-qa-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "retry budget exhausted",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-escalate[{task_id}]",
        )

        replan_started = time.monotonic()
        replan_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "replan",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "narrow the sprint around persistence hardening",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan[{task_id}]",
        )
        timing.add_phase("app_replan", time.monotonic() - replan_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        active_sprint = harness.get("active_sprint_contract") or {}
        if not str(active_sprint.get("sprint_id") or "").startswith("sprint-1-replan-"):
            raise RuntimeError(f"live app replan did not activate a replanned sprint: {harness}")
        if str(harness.get("loop_status") or "").strip() != "sprint_replanned":
            raise RuntimeError(f"live app replan did not settle to sprint_replanned: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-replan",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "replan_stdout": replan_stdout.splitlines()[:2],
            "planner_mode": active_sprint.get("proposed_by"),
            "active_sprint_id": active_sprint.get("sprint_id"),
            "scope": active_sprint.get("scope"),
            "done_definition": active_sprint.get("done_definition"),
            "loop_status": harness.get("loop_status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_replan_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_replan"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-replan",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_replan_generate_qa_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-replan-generate-qa/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-replan-generate-qa-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-replan-generate-qa-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for a live replanned sprint execution check.",
                    "--summary",
                    "Create a persisted session before running live replanned sprint execution.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-ingest[{task_id}]",
        )

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-negotiate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--summary",
                    "Patch refresh stability in the graph shell before re-running the evaluator.",
                    "--target",
                    "src/graph-shell.tsx",
                    "--target",
                    "src/timeline-panel.tsx",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-generate-initial[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "Refresh handling improved, but timeline stability still falls short of the evaluator bar.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-qa-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "retry budget exhausted",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-escalate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "replan",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "narrow the sprint around persistence hardening",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-replan[{task_id}]",
        )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            replanned_payload = workbench.inspect_session(task_id=task_id)
        replanned_harness = (replanned_payload.get("canonical_views") or {}).get("app_harness") or {}
        active_sprint = replanned_harness.get("active_sprint_contract") or {}
        replanned_sprint_id = str(active_sprint.get("sprint_id") or "").strip()
        if not replanned_sprint_id.startswith("sprint-1-replan-"):
            raise RuntimeError(f"live app replan+generate+qa did not create a replanned sprint: {replanned_harness}")

        generate_started = time.monotonic()
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    replanned_sprint_id,
                    "--use-live-generator",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-generate-replanned[{task_id}]",
        )
        timing.add_phase("app_generate_replanned", time.monotonic() - generate_started)

        qa_started = time.monotonic()
        qa_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    replanned_sprint_id,
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "The replanned sprint now focuses on persistence hardening and should reflect the new execution path.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-qa-replanned[{task_id}]",
        )
        timing.add_phase("app_qa_replanned", time.monotonic() - qa_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            generator_timeout_seconds = int(workbench._execution_host.live_app_generator_timeout_seconds())
            generator_max_completion_tokens = int(workbench._execution_host.live_app_generator_max_completion_tokens())
            evaluator_timeout_seconds = int(workbench._execution_host.live_app_evaluator_timeout_seconds())
            evaluator_max_completion_tokens = int(workbench._execution_host.live_app_evaluator_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        execution_attempt = harness.get("latest_execution_attempt") or {}
        evaluation = harness.get("latest_sprint_evaluation") or {}
        if str(execution_attempt.get("sprint_id") or "").strip() != replanned_sprint_id:
            raise RuntimeError(f"latest execution attempt did not bind to the replanned sprint: {harness}")
        if str(execution_attempt.get("execution_mode") or "").strip() != "live":
            raise RuntimeError(f"replanned sprint generate did not persist execution_mode=live: {harness}")
        if str(evaluation.get("sprint_id") or "").strip() != replanned_sprint_id:
            raise RuntimeError(f"replanned sprint qa did not bind to the replanned sprint: {harness}")
        if str(evaluation.get("evaluator_mode") or "").strip() != "live":
            raise RuntimeError(f"replanned sprint qa did not persist evaluator_mode=live: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-replan-generate-qa",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "qa_stdout": qa_stdout.splitlines()[:2],
            "replanned_sprint_id": replanned_sprint_id,
            "execution_mode": execution_attempt.get("execution_mode"),
            "execution_summary": execution_attempt.get("execution_summary"),
            "evaluator_mode": evaluation.get("evaluator_mode"),
            "evaluation_status": evaluation.get("status"),
            "loop_status": harness.get("loop_status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "generator_timeout_seconds": generator_timeout_seconds,
            "generator_max_completion_tokens": generator_max_completion_tokens,
            "evaluator_timeout_seconds": evaluator_timeout_seconds,
            "evaluator_max_completion_tokens": evaluator_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_generate_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_generate_replanned"), 0.0),
            "app_qa_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_qa_replanned"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-replan-generate-qa",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()


def run_live_app_replan_generate_qa_advance_scenario(
    repo_entry: RealRepoSpec,
    *,
    cache_root: str | Path | None = None,
    launcher_home: str | Path | None = None,
) -> ScenarioResult:
    repo_root = ensure_repo_cached(repo_entry, cache_root=cache_root)
    launcher_home_path = Path(launcher_home) if launcher_home is not None else repo_root / ".real-live-home"
    launcher_home_path.mkdir(parents=True, exist_ok=True)
    runtime_env = RealRuntimeEnv(home=launcher_home_path)
    project_identity = f"real-live-e2e/live-app-replan-generate-qa-advance/{repo_entry.id}"
    env = _live_scenario_env(
        project_identity=project_identity,
        base_url=runtime_env.base_url,
        launcher_home=launcher_home_path,
    )
    task_id = f"{repo_entry.id}-live-app-replan-generate-qa-advance-1"
    timing = LiveTimingRecord(task_id=task_id)
    target_file = _live_target_file(repo_entry, repo_root)

    try:
        start_payload = runtime_env.start()
        if start_payload.get("mode") != "running" or not runtime_env.is_healthy():
            raise RuntimeError(f"runtime did not become healthy: {start_payload}")

        ready_started = time.monotonic()
        ready_output = _require_exit_zero(
            run_aionis(["ready", "--repo-root", str(repo_root)], cwd=repo_root, env=env),
            label="live-app-replan-generate-qa-advance-ready",
        )
        timing.add_phase("ready", time.monotonic() - ready_started)

        _require_success(
            run_aionis(
                [
                    "ingest",
                    "--repo-root",
                    str(repo_root),
                    "--task-id",
                    task_id,
                    "--task",
                    "Seed a session for a live replanned sprint policy-advance check.",
                    "--summary",
                    "Create a persisted session before running live replanned sprint advance.",
                    "--target-file",
                    target_file,
                    "--validation-command",
                    "git status --short",
                    "--validation-summary",
                    "git status completed.",
                    "--validation-ok",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-ingest[{task_id}]",
        )

        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "plan",
                    "--task-id",
                    task_id,
                    "--prompt",
                    "Build a visual dependency explorer for async task orchestration.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-plan[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "sprint",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--goal",
                    "Ship the graph shell and timeline panel.",
                    "--scope",
                    "graph shell",
                    "--scope",
                    "timeline panel",
                    "--acceptance-check",
                    "npm test",
                    "--done-definition",
                    "graph loads",
                    "--done-definition",
                    "timeline renders",
                    "--proposed-by",
                    "planner",
                    "--approved",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-sprint[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--blocker",
                    "timeline entries reset on refresh",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-qa[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "negotiate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--objection",
                    "timeline entries reset on refresh",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-negotiate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "retry",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--revision-note",
                    "keep the sprint narrow around persistence and refresh stability",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--summary",
                    "Patch refresh stability in the graph shell before re-running the evaluator.",
                    "--target",
                    "src/graph-shell.tsx",
                    "--target",
                    "src/timeline-panel.tsx",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-generate-initial[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--use-live-evaluator",
                    "--status",
                    "auto",
                    "--summary",
                    "Refresh handling improved, but timeline stability still falls short of the evaluator bar.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-qa-after-retry[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "escalate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "retry budget exhausted",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-escalate[{task_id}]",
        )
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "replan",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-1",
                    "--note",
                    "narrow the sprint around persistence hardening",
                    "--use-live-planner",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-replan[{task_id}]",
        )

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            replanned_payload = workbench.inspect_session(task_id=task_id)
        replanned_harness = (replanned_payload.get("canonical_views") or {}).get("app_harness") or {}
        active_sprint = replanned_harness.get("active_sprint_contract") or {}
        replanned_sprint_id = str(active_sprint.get("sprint_id") or "").strip()
        if not replanned_sprint_id.startswith("sprint-1-replan-"):
            raise RuntimeError(f"live app replan+generate+qa+advance did not create a replanned sprint: {replanned_harness}")

        generate_started = time.monotonic()
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "generate",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    replanned_sprint_id,
                    "--use-live-generator",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-generate-replanned[{task_id}]",
        )
        timing.add_phase("app_generate_replanned", time.monotonic() - generate_started)

        qa_started = time.monotonic()
        _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "qa",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    replanned_sprint_id,
                    "--use-live-evaluator",
                    "--status",
                    "passed",
                    "--score",
                    "functionality=0.92",
                    "--score",
                    "design_quality=0.87",
                    "--score",
                    "code_quality=0.84",
                    "--summary",
                    "The replanned sprint now stabilizes persistence and refresh flow, so the next sprint can begin.",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance-qa-replanned[{task_id}]",
        )
        timing.add_phase("app_qa_replanned", time.monotonic() - qa_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            ready_payload = workbench.inspect_session(task_id=task_id)
        ready_harness = (ready_payload.get("canonical_views") or {}).get("app_harness") or {}
        if str(ready_harness.get("active_sprint_contract", {}).get("sprint_id") or "").strip() != replanned_sprint_id:
            raise RuntimeError(f"replanned sprint was not active before advance: {ready_harness}")
        if str(ready_harness.get("recommended_next_action") or "").strip() != "advance_to_next_sprint":
            raise RuntimeError(f"replanned sprint did not unlock advance: {ready_harness}")
        if not bool(ready_harness.get("next_sprint_ready")):
            raise RuntimeError(f"replanned sprint did not mark the next sprint ready: {ready_harness}")

        advance_started = time.monotonic()
        advance_stdout = _require_exit_zero(
            run_aionis(
                [
                    "app",
                    "--repo-root",
                    str(repo_root),
                    "advance",
                    "--task-id",
                    task_id,
                    "--sprint-id",
                    "sprint-2",
                ],
                cwd=repo_root,
                env=env,
            ),
            label=f"live-app-replan-generate-qa-advance[{task_id}]",
        )
        timing.add_phase("app_advance", time.monotonic() - advance_started)

        with _patched_env(env):
            workbench = AionisWorkbench(repo_root=str(repo_root))
            inspect_payload = workbench.inspect_session(task_id=task_id)
            generator_timeout_seconds = int(workbench._execution_host.live_app_generator_timeout_seconds())
            generator_max_completion_tokens = int(workbench._execution_host.live_app_generator_max_completion_tokens())
            evaluator_timeout_seconds = int(workbench._execution_host.live_app_evaluator_timeout_seconds())
            evaluator_max_completion_tokens = int(workbench._execution_host.live_app_evaluator_max_completion_tokens())

        harness = (inspect_payload.get("canonical_views") or {}).get("app_harness") or {}
        final_active_sprint = harness.get("active_sprint_contract") or {}
        if str(final_active_sprint.get("sprint_id") or "").strip() != "sprint-2":
            raise RuntimeError(f"live app replanned advance did not activate sprint-2: {harness}")
        if str(harness.get("loop_status") or "").strip() != "in_sprint":
            raise RuntimeError(f"live app replanned advance did not transition back to in_sprint: {harness}")

        provider_profile = resolve_provider_profile(env)
        details = {
            "scenario_id": "live-app-replan-generate-qa-advance",
            "repo_id": repo_entry.id,
            "repo_root": str(repo_root),
            "launcher_home": str(launcher_home_path),
            "base_url": runtime_env.base_url,
            "task_id": task_id,
            "target_file": target_file,
            "ready_output_first_line": ready_output.splitlines()[0] if ready_output else "",
            "advance_stdout": advance_stdout.splitlines()[:2],
            "replanned_sprint_id": replanned_sprint_id,
            "active_sprint_id": final_active_sprint.get("sprint_id"),
            "loop_status": harness.get("loop_status"),
            "provider_id": provider_profile.provider_id if provider_profile else "",
            "live_mode": infer_live_mode(env),
            "model": str(env.get("WORKBENCH_MODEL") or env.get("OPENROUTER_MODEL") or ""),
            "generator_timeout_seconds": generator_timeout_seconds,
            "generator_max_completion_tokens": generator_max_completion_tokens,
            "evaluator_timeout_seconds": evaluator_timeout_seconds,
            "evaluator_max_completion_tokens": evaluator_max_completion_tokens,
            "ready_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "ready"), 0.0),
            "app_generate_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_generate_replanned"), 0.0),
            "app_qa_replanned_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_qa_replanned"), 0.0),
            "app_advance_duration_seconds": next((phase.duration_seconds for phase in timing.phases if phase.name == "app_advance"), 0.0),
            "total_duration_seconds": timing.total_duration_seconds,
            "timing_summary": timing.summary(),
        }
        _persist_live_profile_snapshot(details, launcher_home=launcher_home_path)
        return ScenarioResult(
            scenario_id="live-app-replan-generate-qa-advance",
            status="passed",
            repo_id=repo_entry.id,
            details=details,
        )
    finally:
        runtime_env.stop()
