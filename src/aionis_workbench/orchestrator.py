from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import AionisConfig, WorkbenchConfig
from .context_layers import assemble_context_layers
from .execution_host_contract import ExecutionHostAdapter
from .policies import (
    build_continuity_snapshot,
    build_delegation_prompt,
    build_memory_prompts,
    normalize_session_memory,
    promote_insights,
    refresh_delegation_packets,
    seed_continuity_snapshot,
    seed_shared_memory,
    trace_summary,
)
from .recovery_service import RecoveryService, ValidationResult
from .reviewer_contracts import (
    continuity_review_pack_summary_from_runtime,
    evolution_review_pack_summary_from_runtime,
)
from .runtime_bridge_host import AionisRuntimeHost
from .session import SessionState, load_session
from .session_service import SessionService
from .tracing import TraceRecorder, extract_target_files
from .utils import stringify_result


def _has_timeout_pressure(session: SessionState) -> bool:
    if any(item.kind == "timeout_artifact" for item in session.artifacts):
        return True
    if session.last_result_preview and "timed out" in session.last_result_preview.lower():
        return True
    return False


def _result_preview(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return text.strip()[:240]


def _extract_replay_run_id(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    run_id = payload.get("replay_run_id")
    return run_id.strip() if isinstance(run_id, str) else ""


def _extract_handoff_context(handoff: dict[str, Any]) -> str | None:
    root = handoff.get("handoff") or {}
    prompt_safe = root.get("prompt_safe_handoff") or {}
    execution_ready = root.get("execution_ready_handoff") or {}
    lines = []
    for label, value in [
        ("Summary", root.get("summary") or prompt_safe.get("summary")),
        ("Handoff", root.get("handoff_text") or prompt_safe.get("handoff_text")),
        ("Next action", root.get("next_action") or execution_ready.get("next_action")),
        ("Repo root", root.get("repo_root") or prompt_safe.get("repo_root") or execution_ready.get("repo_root")),
    ]:
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}: {value.strip()}")
    target_files = execution_ready.get("target_files") or root.get("target_files")
    if isinstance(target_files, list):
        cleaned = [value.strip() for value in target_files if isinstance(value, str) and value.strip()]
        if cleaned:
            lines.append(f"Target files: {', '.join(cleaned[:8])}")
    return "\n".join(lines) if lines else None


def _build_failure_handoff(
    *,
    task: str,
    exc: Exception,
    repo_root: str,
    trace_steps: list[Any],
    next_action: str,
) -> str:
    lines = [
        "Workbench execution halted before completion.",
        f"Task: {task}",
        f"Failure: {str(exc).strip()}",
        f"Repo root: {repo_root}",
        f"Suggested next action: {next_action}",
    ]
    targets = extract_target_files(trace_steps, repo_root=repo_root)
    if targets:
        lines.append(f"Target files: {', '.join(targets[:8])}")
    recent = [f"{step.step_index}. {step.tool_name} [{step.status}]" for step in trace_steps[-6:]]
    if recent:
        lines.append("Recent steps:")
        lines.extend(recent)
    return "\n".join(lines)


@dataclass
class OrchestrationResult:
    task_id: str
    runner: str
    content: str
    session: SessionState
    session_path: Path
    aionis: dict[str, Any]


class Orchestrator:
    def __init__(
        self,
        *,
        workbench_config: WorkbenchConfig,
        aionis_config: AionisConfig,
        execution_host: ExecutionHostAdapter,
        runtime_host: AionisRuntimeHost,
        trace: TraceRecorder,
        sessions: SessionService,
        recovery: RecoveryService,
        save_session_fn: Callable[[SessionState], Path],
        run_validation_commands_fn: Callable[[list[str]], ValidationResult],
        apply_validation_feedback_fn: Callable[[SessionState, ValidationResult], None],
        persist_artifacts_fn: Callable[..., None],
        record_auto_learning_fn: Callable[..., None],
        record_recorded_learning_fn: Callable[..., None],
        maybe_auto_consolidate_fn: Callable[..., dict[str, Any]],
    ) -> None:
        self._config = workbench_config
        self._aionis = aionis_config
        self._execution_host = execution_host
        self._runtime_host = runtime_host
        self._trace = trace
        self._sessions = sessions
        self._recovery = recovery
        self._save_session = save_session_fn
        self._run_validation_commands = run_validation_commands_fn
        self._apply_validation_feedback = apply_validation_feedback_fn
        self._persist_artifacts = persist_artifacts_fn
        self._record_auto_learning = record_auto_learning_fn
        self._record_recorded_learning = record_recorded_learning_fn
        self._maybe_auto_consolidate = maybe_auto_consolidate_fn

    def _attach_runtime_review_packs(
        self,
        *,
        session: SessionState,
        continuity_payload: dict[str, Any] | None = None,
        evolution_payload: dict[str, Any] | None = None,
    ) -> None:
        if continuity_payload:
            continuity_pack = continuity_review_pack_summary_from_runtime(continuity_payload)
            if continuity_pack is not None:
                session.continuity_review_pack = continuity_pack
        if evolution_payload:
            evolution_pack = evolution_review_pack_summary_from_runtime(evolution_payload)
            if evolution_pack is not None:
                session.evolution_review_pack = evolution_pack

    def _build_agent(self, session: SessionState, prompt_parts: list[str]):
        timeout_pressure = _has_timeout_pressure(session)
        system_parts = [
            self._config.system_prompt or "You are Aionis Workbench, a multi-agent software engineering orchestrator.",
            (
                "You are not a simple bugfix shell. Use subagents proactively for investigation, implementation, "
                "and verification when the task is non-trivial. Preserve shared memory, keep working memory tight, "
                "and prefer durable, reusable summaries over verbose scratch output."
            ),
            *(
                [
                    "Timeout-pressure mode is active. Keep the plan minimal, stay on the narrowest working set, avoid broad context expansion, and prefer direct local correction before delegating."
                ]
                if timeout_pressure
                else []
            ),
            f"Tenant: {self._aionis.tenant_id}",
            f"Project identity: {self._config.project_identity}",
            f"Project scope: {self._config.project_scope}",
            *build_memory_prompts(session),
            build_delegation_prompt(session),
            *[part for part in prompt_parts if part],
        ]
        memory_source_limit = 8
        if timeout_pressure:
            memory_source_limit = 4
        elif session.collaboration_patterns:
            memory_source_limit = 14
        memory_sources = list(session.target_files[: memory_source_limit // 2])
        for artifact in session.artifacts[: memory_source_limit]:
            if artifact.path not in memory_sources:
                memory_sources.append(artifact.path)
            if len(memory_sources) >= memory_source_limit:
                break
        return self._execution_host.build_agent(
            system_parts=system_parts,
            memory_sources=memory_sources,
            timeout_pressure=timeout_pressure,
        )

    def _ingest_validation_result(
        self,
        *,
        validation_ok: bool,
        validation_commands: list[str],
        validation_summary: str | None,
        changed_files: list[str],
    ) -> ValidationResult:
        normalized_commands = self._sessions.normalize_validation_commands(validation_commands)
        summary = (validation_summary or "").strip()
        if validation_ok:
            if not summary:
                summary = "Validated externally before ingest."
            return ValidationResult(
                ok=True,
                command=normalized_commands[-1] if normalized_commands else None,
                exit_code=0 if normalized_commands else None,
                summary=summary,
                output="",
                changed_files=self._sessions.normalize_target_files(changed_files),
            )
        if not summary:
            summary = "External validation reported a failure before ingest."
        return ValidationResult(
            ok=False,
            command=normalized_commands[-1] if normalized_commands else None,
            exit_code=1,
            summary=summary,
            output="",
            changed_files=self._sessions.normalize_target_files(changed_files),
        )

    def run(
        self,
        *,
        task_id: str,
        task: str,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
    ) -> OrchestrationResult:
        session = self._sessions.initial_session(
            task_id=task_id,
            task=task,
            target_files=target_files or [],
            validation_commands=validation_commands or [],
            apply_strategy=True,
        )
        session.status = "running"
        self._save_session(session)
        task_session = self._runtime_host.open_task_session(
            task_id=task_id,
            text=task,
            title=session.goal or task,
            summary=session.goal or task,
            metadata={
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
            },
        )
        startup_context = {
            "host": "aionis-workbench",
            "tenant_id": self._aionis.tenant_id,
            "project_identity": self._config.project_identity,
            "project_scope": self._config.project_scope,
            "repo_root": self._config.repo_root,
            "cwd": self._config.repo_root,
            "target_files": session.target_files,
            "validation_commands": session.validation_commands,
            "delegation_packets": [packet.__dict__ for packet in session.delegation_packets],
        }
        started = task_session.plan_task_start(
            context=startup_context,
        )
        first_action = started.get("first_action") or {}
        decision = started.get("decision") or {}
        task_context = started.get("task_context") or {}
        delegation_learning = task_context.get("delegation_learning") or {}
        learning_summary = delegation_learning.get("learning_summary") or {}
        if isinstance(learning_summary.get("task_family"), str) and learning_summary["task_family"].strip():
            session.selected_task_family = learning_summary["task_family"].strip()
        session.continuity_snapshot = seed_continuity_snapshot(session=session, kickoff=started)
        seed_shared_memory(session=session, kickoff=started)
        self._recovery.apply_timeout_strategy(session)
        session.continuity_snapshot = build_continuity_snapshot(session)
        session.context_layers_snapshot = assemble_context_layers(session=session)
        kickoff_lines = []
        if first_action.get("selected_tool"):
            kickoff_lines.append(f"Preferred tool: {first_action['selected_tool']}")
        if first_action.get("file_path"):
            kickoff_lines.append(f"Focused file: {first_action['file_path']}")
        if first_action.get("next_action"):
            kickoff_lines.append(f"Next action: {first_action['next_action']}")
        if decision.get("planner_explanation"):
            kickoff_lines.append(f"Planner explanation: {decision['planner_explanation']}")
        if decision.get("task_family"):
            kickoff_lines.append(f"Task family: {decision['task_family']}")
        if isinstance(decision.get("matched_records"), int) and decision["matched_records"] > 0:
            kickoff_lines.append(f"Matched delegation records: {decision['matched_records']}")
        prompt_parts = []
        if kickoff_lines:
            prompt_parts.append("Aionis kickoff guidance:\n" + "\n".join(kickoff_lines))
        if session.target_files:
            prompt_parts.append("Current working set:\n" + "\n".join(f"- {value}" for value in session.target_files[:10]))
        if session.validation_commands:
            prompt_parts.append("Validation commands:\n" + "\n".join(f"- {value}" for value in session.validation_commands[:6]))
        agent = self._build_agent(session, prompt_parts)
        try:
            result = self._execution_host.invoke(agent, {"messages": [{"role": "user", "content": task}]})
        except Exception as exc:
            trace_steps = self._trace.export()
            inferred_files = extract_target_files(trace_steps, repo_root=self._config.repo_root)
            failure_artifact = self._recovery.failure_artifact_payload(
                session=session,
                exc=exc,
                trace_steps=trace_steps,
                changed_files=inferred_files,
            )
            paused = task_session.pause_task(
                summary=f"Workbench run failed for {task_id}",
                handoff_text=_build_failure_handoff(
                    task=task,
                    exc=exc,
                    repo_root=self._config.repo_root,
                    trace_steps=trace_steps,
                    next_action=first_action.get("next_action") or "Resume the session and continue from the latest delegation context.",
                ),
                repo_root=self._config.repo_root,
                target_files=self._sessions.normalize_target_files([*session.target_files, *inferred_files]),
                next_action=first_action.get("next_action") or "Resume the session and continue from the latest delegation context.",
                execution_result_summary=trace_summary(trace_steps),
                execution_evidence=[{"kind": "workbench_exception", "message": str(exc)}],
            )
            session.last_trace_summary = trace_summary(trace_steps)
            session.working_memory = [f"{step.tool_name} [{step.status}]" for step in trace_steps[-6:]]
            session.status = "paused"
            session.last_result_preview = _result_preview(str(exc))
            self._persist_artifacts(
                session=session,
                validation=None,
                failure=failure_artifact,
                correction=self._recovery.build_correction_packet(session),
            )
            refresh_delegation_packets(session)
            path = self._save_session(session)
            raise RuntimeError(
                json.dumps(
                    {
                        "pause": paused,
                        "task_session_state": task_session.snapshot_state(),
                        "session_path": str(path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            ) from exc

        content = stringify_result(result)
        session.last_result_preview = _result_preview(content)
        trace_steps = self._trace.export()
        validation = self._run_validation_commands(session.validation_commands)
        if any(item.kind == "correction_packet_artifact" for item in session.artifacts):
            validation = self._recovery.apply_narrow_scope_guard(
                session=session,
                trace_steps=trace_steps,
                validation=validation,
            )
            validation = self._recovery.apply_regression_expansion_guard(
                session=session,
                validation=validation,
            )
        promote_insights(
            session=session,
            trace_steps=trace_steps,
            content=content,
            validation_ok=validation.ok,
            validation_command=validation.command,
            validation_summary=validation.summary,
            changed_files=validation.changed_files,
        )
        self._apply_validation_feedback(session, validation)
        self._persist_artifacts(
            session=session,
            validation=validation,
            correction=None if validation.ok else self._recovery.build_correction_packet(session),
            rollback=self._recovery.build_rollback_hint(session=session, validation=validation),
        )
        session.last_trace_summary = trace_summary(trace_steps)
        if not validation.ok:
            paused = task_session.pause_task(
                summary=f"Workbench run requires another pass for {task_id}",
                handoff_text="\n".join(
                    [
                        "Validation failed after a workbench run.",
                        f"Task: {task}",
                        f"Failure: {validation.summary}",
                        *(["Failing command: " + validation.command] if validation.command else []),
                        *(["Changed files: " + ', '.join(validation.changed_files[:8])] if validation.changed_files else []),
                        *(["Output:\n" + validation.output] if validation.output else []),
                    ]
                ),
                repo_root=self._config.repo_root,
                target_files=self._sessions.normalize_target_files([*session.target_files, *validation.changed_files]),
                next_action="Correct the validation failure using the failing command, changed files, and latest output as the primary signals.",
                execution_result_summary={
                    **trace_summary(trace_steps),
                    "validation_ok": False,
                    "validation_command": validation.command,
                    "validation_exit_code": validation.exit_code,
                },
                execution_evidence=[
                    {
                        "kind": "validation_failure",
                        "command": validation.command,
                        "exit_code": validation.exit_code,
                        "summary": validation.summary,
                        "output": validation.output,
                    }
                ],
            )
            path = self._save_session(session)
            return OrchestrationResult(
                task_id=task_id,
                runner="run",
                content=content,
                session=session,
                session_path=path,
                aionis={
                    "start": started,
                    "pause": paused,
                    "task_session_state": task_session.snapshot_state(),
                    "validation": validation.__dict__,
                },
            )
        self._record_auto_learning(session=session, source="run", validation=validation)
        try:
            evolution_review = self._runtime_host.evolution_review_pack(
                task_id=task_id,
                text=task,
                repo_root=self._config.repo_root,
                target_files=session.target_files,
            )
        except Exception:
            evolution_review = None
        self._attach_runtime_review_packs(
            session=session,
            evolution_payload=(evolution_review or {}).get("payload") if isinstance(evolution_review, dict) else None,
        )
        completed = task_session.complete_task(
            summary=f"Workbench run completed for {task_id}",
            output=content,
            tool_steps=trace_steps,
            metadata={
                "host": "aionis-workbench",
                "tenant_id": self._aionis.tenant_id,
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
                "target_files": session.target_files,
                "validation_commands": session.validation_commands,
                "promoted_insights": session.promoted_insights[:8],
                "artifacts": [item.path for item in session.artifacts[:8]],
                "validation": validation.__dict__,
            },
        )
        session.status = "completed"
        session.aionis_replay_run_id = _extract_replay_run_id(completed)
        path = self._save_session(session)
        auto_consolidation = self._maybe_auto_consolidate(trigger="run")
        return OrchestrationResult(
            task_id=task_id,
            runner="run",
            content=content,
            session=session,
            session_path=path,
            aionis={
                "start": started,
                "complete": completed,
                "task_session_state": task_session.snapshot_state(),
                "validation": validation.__dict__,
                "auto_consolidation": auto_consolidation,
            },
        )

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
    ) -> OrchestrationResult:
        explicit_target_files = self._sessions.normalize_target_files(target_files or [])
        explicit_validation_commands = self._sessions.normalize_validation_commands(validation_commands or [])
        session = self._sessions.initial_session(
            task_id=task_id,
            task=task,
            target_files=explicit_target_files,
            validation_commands=explicit_validation_commands,
            apply_strategy=False,
        )
        changed = self._sessions.normalize_target_files(changed_files or explicit_target_files or session.target_files)
        session.target_files = self._sessions.normalize_target_files([*explicit_target_files, *changed])
        if explicit_validation_commands:
            session.validation_commands = explicit_validation_commands
        validation = self._ingest_validation_result(
            validation_ok=validation_ok,
            validation_commands=explicit_validation_commands or session.validation_commands,
            validation_summary=validation_summary,
            changed_files=changed,
        )
        session.last_result_preview = _result_preview(summary)
        session.shared_memory.append(
            "Ingested validated task into project continuity."
            if validation.ok
            else "Ingested unresolved task into project continuity."
        )
        if changed:
            session.shared_memory.append("Ingested changed files: " + ", ".join(changed[:8]))
        promote_insights(
            session=session,
            trace_steps=[],
            content=summary,
            validation_ok=validation.ok,
            validation_command=validation.command,
            validation_summary=validation.summary,
            changed_files=changed,
        )
        self._apply_validation_feedback(session, validation)
        self._persist_artifacts(
            session=session,
            validation=validation,
            correction=None if validation.ok else self._recovery.build_correction_packet(session),
            rollback=self._recovery.build_rollback_hint(session=session, validation=validation),
        )
        self._record_recorded_learning(
            session=session,
            source="manual_ingest",
            validation=validation,
        )
        session.last_trace_summary = {
            "steps_observed": 0,
            "tool_steps": 0,
            "model_steps": 0,
            "successful_steps": 0,
            "errored_steps": 0,
            "ingested": 1,
        }
        session.status = "ingested" if validation.ok else "ingested_needs_attention"
        normalize_session_memory(session)
        recorded = self._runtime_host.record_task(
            task_id=task_id,
            text=task,
            summary=f"Ingested validated task for {task_id}" if validation.ok else f"Ingested unresolved task for {task_id}",
            metadata={
                "host": "aionis-workbench",
                "tenant_id": self._aionis.tenant_id,
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
                "target_files": session.target_files,
                "validation_commands": session.validation_commands,
                "promoted_insights": session.promoted_insights[:8],
                "artifacts": [item.path for item in session.artifacts[:8]],
                "validation": validation.__dict__,
                "recording_mode": "ingest",
                "execution_source": "externally_validated_task",
            },
        )
        session.aionis_replay_run_id = _extract_replay_run_id(recorded)
        path = self._save_session(session)
        auto_consolidation = self._maybe_auto_consolidate(trigger="ingest")
        return OrchestrationResult(
            task_id=task_id,
            runner="ingest",
            content=summary,
            session=session,
            session_path=path,
            aionis={"record": recorded, "validation": validation.__dict__, "auto_consolidation": auto_consolidation},
        )

    def resume(
        self,
        *,
        task_id: str,
        fallback_task: str | None = None,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
    ) -> OrchestrationResult:
        session = load_session(self._config.repo_root, task_id, project_scope=self._config.project_scope)
        if session is None:
            session = self._sessions.initial_session(
                task_id=task_id,
                task=fallback_task or "",
                target_files=target_files or [],
                validation_commands=validation_commands or [],
            )
        else:
            session.repo_root = self._config.repo_root
            session.project_identity = session.project_identity or self._config.project_identity
            session.project_scope = session.project_scope or self._config.project_scope
            session.target_files = self._sessions.normalize_target_files(session.target_files)
            session.validation_commands = self._sessions.normalize_validation_commands(session.validation_commands)
            normalize_session_memory(session)
        if target_files:
            session.target_files = self._sessions.normalize_target_files([*session.target_files, *target_files])
        if validation_commands:
            session.validation_commands = self._sessions.normalize_validation_commands(validation_commands)
        rollback_payload = self._recovery.load_rollback_payload(session)
        rollback_working_set = [
            value
            for value in rollback_payload.get("working_set", [])
            if isinstance(value, str) and value.strip()
        ]
        rollback_command = rollback_payload.get("command")
        if rollback_working_set:
            session.target_files = self._sessions.normalize_target_files(rollback_working_set)
        if isinstance(rollback_command, str) and rollback_command.strip():
            session.validation_commands = self._sessions.normalize_validation_commands([rollback_command.strip()])
        refresh_delegation_packets(session)
        session.status = "running"
        self._save_session(session)
        resume_seed_text = fallback_task or session.goal or f"Resume task {task_id}"
        task_session = self._runtime_host.open_task_session(
            task_id=task_id,
            text=resume_seed_text,
            title=session.goal or resume_seed_text,
            summary=session.goal or resume_seed_text,
            metadata={
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
                "resumed": True,
            },
        )
        resumed = task_session.resume_task(repo_root=self._config.repo_root)
        try:
            continuity_review = self._runtime_host.continuity_review_pack(
                task_id=task_id,
                repo_root=self._config.repo_root,
                file_path=(session.target_files[0] if session.target_files else None),
            )
        except Exception:
            continuity_review = None
        self._attach_runtime_review_packs(
            session=session,
            continuity_payload=(continuity_review or {}).get("payload") if isinstance(continuity_review, dict) else None,
        )
        handoff_context = _extract_handoff_context(resumed)
        if not handoff_context:
            session.working_memory = session.working_memory[-8:]
        task = fallback_task or session.goal or handoff_context or ""
        if not task:
            raise ValueError("No session goal or recovered handoff context was available. Pass --task to provide the task text.")
        session.goal = task
        resume_task_context: dict[str, Any] = {}
        resume_context = {
            "host": "aionis-workbench",
            "tenant_id": self._aionis.tenant_id,
            "project_identity": self._config.project_identity,
            "project_scope": self._config.project_scope,
            "repo_root": self._config.repo_root,
            "cwd": self._config.repo_root,
            "target_files": session.target_files,
            "validation_commands": session.validation_commands,
            "delegation_packets": [packet.__dict__ for packet in session.delegation_packets],
            "resumed": True,
        }
        try:
            inspected = task_session.inspect_task_context(text=task, context=resume_context)
            if isinstance(inspected, dict):
                resume_task_context = inspected
        except Exception:
            resume_task_context = {}
        delegation_learning = resume_task_context.get("delegation_learning") or {}
        learning_summary = delegation_learning.get("learning_summary") or {}
        if isinstance(learning_summary.get("task_family"), str) and learning_summary["task_family"].strip():
            session.selected_task_family = learning_summary["task_family"].strip()
        planning_context = resume_task_context.get("planning_context") or {}
        planning_summary = planning_context.get("planning_summary") or {}
        session.continuity_snapshot = seed_continuity_snapshot(session=session, handoff_context=handoff_context)
        seed_shared_memory(session=session, handoff_context=handoff_context)
        self._recovery.apply_timeout_strategy(session)
        session.continuity_snapshot = build_continuity_snapshot(session)
        session.context_layers_snapshot = assemble_context_layers(session=session)
        rollback_recovery = self._recovery.attempt_rollback_recovery(session)
        if rollback_recovery and rollback_recovery.get("attempted"):
            suspicious_file = rollback_recovery.get("suspicious_file") or ""
            session.working_memory.append(
                f"Rollback recovery: {rollback_recovery.get('summary', '').strip()[:240]}"
            )
            if suspicious_file:
                session.working_memory.append("Rollback suspicious file: " + str(suspicious_file))
            validation = rollback_recovery.get("validation")
            if isinstance(validation, ValidationResult):
                self._apply_validation_feedback(session, validation)
                self._persist_artifacts(
                    session=session,
                    validation=validation,
                    correction=None if validation.ok else self._recovery.build_correction_packet(session),
                    rollback=self._recovery.build_rollback_hint(
                        session=session,
                        validation=validation,
                        recovery_result=rollback_recovery,
                    ),
                )
                self._save_session(session)
                if validation.ok:
                    self._record_auto_learning(session=session, source="resume", validation=validation)
                    try:
                        evolution_review = self._runtime_host.evolution_review_pack(
                            task_id=task_id,
                            text=task,
                            repo_root=self._config.repo_root,
                            target_files=session.target_files,
                        )
                    except Exception:
                        evolution_review = None
                    self._attach_runtime_review_packs(
                        session=session,
                        evolution_payload=(evolution_review or {}).get("payload") if isinstance(evolution_review, dict) else None,
                    )
                    content = rollback_recovery.get("summary") or "Automatic rollback recovery succeeded."
                    session.last_result_preview = _result_preview(content)
                    session.last_trace_summary = {
                        "steps_observed": 0,
                        "tool_steps": 0,
                        "model_steps": 0,
                        "successful_steps": 0,
                        "errored_steps": 0,
                        "rollback_recovery": 1,
                    }
                    completed = task_session.complete_task(
                        text=task,
                        summary=f"Workbench resumed run completed for {task_id}",
                        output=content,
                        tool_steps=[],
                        metadata={
                            "host": "aionis-workbench",
                            "tenant_id": self._aionis.tenant_id,
                            "project_identity": self._config.project_identity,
                            "project_scope": self._config.project_scope,
                            "repo_root": self._config.repo_root,
                            "resumed": True,
                            "rollback_recovery": True,
                            "target_files": session.target_files,
                            "validation_commands": session.validation_commands,
                            "promoted_insights": session.promoted_insights[:8],
                            "artifacts": [item.path for item in session.artifacts[:8]],
                            "validation": validation.__dict__,
                        },
                    )
                    session.status = "completed"
                    session.aionis_replay_run_id = _extract_replay_run_id(completed)
                    path = self._save_session(session)
                    auto_consolidation = self._maybe_auto_consolidate(trigger="resume")
                    return OrchestrationResult(
                        task_id=task_id,
                        runner="resume",
                        content=content,
                        session=session,
                        session_path=path,
                        aionis={
                            "resume": resumed,
                            "task_context": resume_task_context,
                            "complete": completed,
                            "task_session_state": task_session.snapshot_state(),
                            "validation": validation.__dict__,
                            "auto_consolidation": auto_consolidation,
                        },
                    )
        prompt_parts = ["Recovered Aionis handoff:\n" + handoff_context] if handoff_context else [
            "Resume from the persisted project session. Reuse the shared memory lane, promoted insights, delegation packets, and current working set before expanding scope."
        ]
        resume_guidance_lines = []
        planner_explanation = planning_summary.get("planner_explanation")
        if isinstance(planner_explanation, str) and planner_explanation.strip():
            resume_guidance_lines.append(f"Planner explanation: {planner_explanation.strip()}")
        if isinstance(learning_summary.get("task_family"), str) and learning_summary["task_family"].strip():
            resume_guidance_lines.append(f"Task family: {learning_summary['task_family'].strip()}")
        if isinstance(learning_summary.get("matched_records"), int) and learning_summary["matched_records"] > 0:
            resume_guidance_lines.append(f"Matched delegation records: {learning_summary['matched_records']}")
        if isinstance(learning_summary.get("recommendation_count"), int) and learning_summary["recommendation_count"] > 0:
            resume_guidance_lines.append(f"Learning recommendations: {learning_summary['recommendation_count']}")
        if resume_guidance_lines:
            prompt_parts.insert(0, "Resume operator guidance:\n" + "\n".join(resume_guidance_lines))
        if rollback_payload:
            rollback_lines = []
            summary = rollback_payload.get("summary")
            if isinstance(summary, str) and summary.strip():
                rollback_lines.append(summary.strip())
            suspicious_file = rollback_payload.get("suspicious_file")
            if isinstance(suspicious_file, str) and suspicious_file.strip():
                rollback_lines.append("Suspicious file: " + suspicious_file.strip())
            revert_spans = rollback_payload.get("revert_spans")
            if isinstance(revert_spans, list):
                rollback_lines.extend(
                    "Revert span: " + value.strip()
                    for value in revert_spans[:3]
                    if isinstance(value, str) and value.strip()
                )
            if rollback_lines:
                prompt_parts.insert(0, "Rollback-first recovery:\n" + "\n".join(rollback_lines))
        if session.target_files:
            prompt_parts.append("Current working set:\n" + "\n".join(f"- {value}" for value in session.target_files[:10]))
        if session.validation_commands:
            prompt_parts.append("Validation commands:\n" + "\n".join(f"- {value}" for value in session.validation_commands[:6]))
        agent = self._build_agent(session, prompt_parts)
        try:
            result = self._execution_host.invoke(agent, {"messages": [{"role": "user", "content": task}]})
        except Exception as exc:
            trace_steps = self._trace.export()
            inferred_files = extract_target_files(trace_steps, repo_root=self._config.repo_root)
            failure_artifact = self._recovery.failure_artifact_payload(
                session=session,
                exc=exc,
                trace_steps=trace_steps,
                changed_files=inferred_files,
            )
            paused = task_session.pause_task(
                summary=f"Workbench resume failed for {task_id}",
                handoff_text=_build_failure_handoff(
                    task=task,
                    exc=exc,
                    repo_root=self._config.repo_root,
                    trace_steps=trace_steps,
                    next_action="Resume the persisted session and continue from the latest delegation context.",
                ),
                repo_root=self._config.repo_root,
                target_files=self._sessions.normalize_target_files([*session.target_files, *inferred_files]),
                next_action="Resume the persisted session and continue from the latest delegation context.",
                execution_result_summary=trace_summary(trace_steps),
                execution_evidence=[{"kind": "workbench_exception", "message": str(exc)}],
            )
            session.last_trace_summary = trace_summary(trace_steps)
            session.working_memory = [f"{step.tool_name} [{step.status}]" for step in trace_steps[-6:]]
            session.status = "paused"
            session.last_result_preview = _result_preview(str(exc))
            self._persist_artifacts(
                session=session,
                validation=None,
                failure=failure_artifact,
                correction=self._recovery.build_correction_packet(session),
            )
            refresh_delegation_packets(session)
            path = self._save_session(session)
            raise RuntimeError(
                json.dumps(
                    {
                        "pause": paused,
                        "task_session_state": task_session.snapshot_state(),
                        "session_path": str(path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            ) from exc
        content = stringify_result(result)
        session.last_result_preview = _result_preview(content)
        trace_steps = self._trace.export()
        validation = self._run_validation_commands(session.validation_commands)
        if any(item.kind == "correction_packet_artifact" for item in session.artifacts):
            validation = self._recovery.apply_narrow_scope_guard(
                session=session,
                trace_steps=trace_steps,
                validation=validation,
            )
            validation = self._recovery.apply_regression_expansion_guard(
                session=session,
                validation=validation,
            )
        promote_insights(
            session=session,
            trace_steps=trace_steps,
            content=content,
            validation_ok=validation.ok,
            validation_command=validation.command,
            validation_summary=validation.summary,
            changed_files=validation.changed_files,
        )
        self._apply_validation_feedback(session, validation)
        self._persist_artifacts(
            session=session,
            validation=validation,
            correction=None if validation.ok else self._recovery.build_correction_packet(session),
            rollback=self._recovery.build_rollback_hint(session=session, validation=validation),
        )
        session.last_trace_summary = trace_summary(trace_steps)
        if not validation.ok:
            paused = task_session.pause_task(
                summary=f"Workbench resume requires another pass for {task_id}",
                handoff_text="\n".join(
                    [
                        "Validation failed after a resumed workbench run.",
                        f"Task: {task}",
                        f"Failure: {validation.summary}",
                        *(["Failing command: " + validation.command] if validation.command else []),
                        *(["Changed files: " + ', '.join(validation.changed_files[:8])] if validation.changed_files else []),
                        *(["Output:\n" + validation.output] if validation.output else []),
                    ]
                ),
                repo_root=self._config.repo_root,
                target_files=self._sessions.normalize_target_files([*session.target_files, *validation.changed_files]),
                next_action="Use the failing validation command and output as the primary correction signal before broadening scope.",
                execution_result_summary={
                    **trace_summary(trace_steps),
                    "validation_ok": False,
                    "validation_command": validation.command,
                    "validation_exit_code": validation.exit_code,
                },
                execution_evidence=[
                    {
                        "kind": "validation_failure",
                        "command": validation.command,
                        "exit_code": validation.exit_code,
                        "summary": validation.summary,
                        "output": validation.output,
                    }
                ],
            )
            session.status = "paused"
            path = self._save_session(session)
            return OrchestrationResult(
                task_id=task_id,
                runner="resume",
                content=content,
                session=session,
                session_path=path,
                aionis={
                    "resume": resumed,
                    "task_context": resume_task_context,
                    "pause": paused,
                    "task_session_state": task_session.snapshot_state(),
                    "validation": validation.__dict__,
                },
            )
        self._record_auto_learning(session=session, source="resume", validation=validation)
        try:
            evolution_review = self._runtime_host.evolution_review_pack(
                task_id=task_id,
                text=task,
                repo_root=self._config.repo_root,
                target_files=session.target_files,
            )
        except Exception:
            evolution_review = None
        self._attach_runtime_review_packs(
            session=session,
            evolution_payload=(evolution_review or {}).get("payload") if isinstance(evolution_review, dict) else None,
        )
        completed = task_session.complete_task(
            text=task,
            summary=f"Workbench resumed run completed for {task_id}",
            output=content,
            tool_steps=trace_steps,
            metadata={
                "host": "aionis-workbench",
                "tenant_id": self._aionis.tenant_id,
                "project_identity": self._config.project_identity,
                "project_scope": self._config.project_scope,
                "repo_root": self._config.repo_root,
                "resumed": True,
                "target_files": session.target_files,
                "validation_commands": session.validation_commands,
                "promoted_insights": session.promoted_insights[:8],
                "artifacts": [item.path for item in session.artifacts[:8]],
                "validation": validation.__dict__,
            },
        )
        session.status = "completed"
        session.aionis_replay_run_id = _extract_replay_run_id(completed)
        path = self._save_session(session)
        auto_consolidation = self._maybe_auto_consolidate(trigger="resume")
        return OrchestrationResult(
            task_id=task_id,
            runner="resume",
            content=content,
            session=session,
            session_path=path,
            aionis={
                "resume": resumed,
                "task_context": resume_task_context,
                "complete": completed,
                "task_session_state": task_session.snapshot_state(),
                "validation": validation.__dict__,
                "auto_consolidation": auto_consolidation,
            },
        )
