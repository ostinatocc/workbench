from __future__ import annotations

import json
from typing import Any, Callable

from .backfill_service import BackfillService
from .context_layers import assemble_context_layers
from .controller_shell import controller_action_bar_payload
from .dream_service import DreamService
from .evaluation_service import EvaluationService
from .policies import (
    build_continuity_snapshot,
    promote_insights,
    refresh_collaboration_patterns,
    refresh_delegation_packets,
    reproject_shared_memory,
    select_collaboration_strategy,
)
from .provenance import build_provenance_surfaces
from .recovery_service import RecoveryService, ValidationResult
from .session import (
    SessionState,
    bootstrap_path,
    load_auto_learning_snapshot,
    load_recent_sessions,
    project_bootstrap_path,
    save_auto_learning_snapshot,
    save_session,
)
from .session_service import SessionService
from .tracing import normalize_target_paths
from .workflow_surface_service import WorkflowSurfaceService


class SurfaceService:
    def __init__(
        self,
        *,
        repo_root: str,
        project_identity: str,
        project_scope: str,
        sessions: SessionService,
        recovery: RecoveryService,
        build_execution_packet_fn: Callable[[SessionState], tuple[Any, Any]],
        build_instrumentation_summary_fn: Callable[[str, str, SessionState], Any],
        load_family_prior_fn: Callable[[str, str, str], dict[str, Any]],
        doctor_fn: Callable[..., dict[str, Any]],
        dashboard_fn: Callable[..., dict[str, Any]],
        background_status_fn: Callable[[], dict[str, Any]],
        host_contract_fn: Callable[[], dict[str, Any]],
        maybe_auto_consolidate_fn: Callable[..., dict[str, Any]],
    ) -> None:
        self._repo_root = repo_root
        self._project_identity = project_identity
        self._project_scope = project_scope
        self._sessions = sessions
        self._recovery = recovery
        self._build_execution_packet = build_execution_packet_fn
        self._build_instrumentation_summary = build_instrumentation_summary_fn
        self._load_family_prior = load_family_prior_fn
        self._doctor = doctor_fn
        self._dashboard = dashboard_fn
        self._background_status = background_status_fn
        self._host_contract = host_contract_fn
        self._maybe_auto_consolidate = maybe_auto_consolidate_fn
        self._dream = DreamService(repo_root=repo_root, project_scope=project_scope)
        self._evaluation = EvaluationService(
            repo_root=repo_root,
            project_identity=project_identity,
            project_scope=project_scope,
            bootstrap_snapshot_fn=self.bootstrap_snapshot,
            bootstrap_canonical_views_fn=self.bootstrap_canonical_views,
            save_session_fn=self.save_session,
            dashboard_fn=dashboard_fn,
            background_status_fn=background_status_fn,
            host_contract_fn=host_contract_fn,
        )
        self._workflow = WorkflowSurfaceService(
            repo_root=repo_root,
            project_scope=project_scope,
            sessions=sessions,
            load_family_prior_fn=load_family_prior_fn,
            save_session_fn=self.save_session,
            canonical_views_fn=self._evaluation.canonical_views,
        )
        self._backfill = BackfillService(
            repo_root=repo_root,
            project_identity=project_identity,
            project_scope=project_scope,
            sessions=sessions,
            recovery=recovery,
            maybe_auto_consolidate_fn=maybe_auto_consolidate_fn,
            save_session_fn=self.save_session,
            canonical_surface_fn=self._evaluation.canonical_surface,
            canonical_views_fn=self._evaluation.canonical_views,
            evaluate_session_model_fn=self._evaluation.evaluate_session_model,
        )

    def bootstrap_snapshot(self) -> dict[str, Any]:
        return self._sessions.bootstrap_snapshot()

    def bootstrap_canonical_views(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        working_set = list(snapshot.get("bootstrap_working_set") or [])
        validation_paths = list(snapshot.get("bootstrap_validation_commands") or [])
        notes = list(snapshot.get("notes") or [])
        next_action = str(snapshot.get("next_action") or "Create the first narrow task for this project.")
        return {
            "task_state": {
                "task_id": None,
                "status": str(snapshot.get("status") or "bootstrap_ready"),
                "project_scope": self._project_scope,
                "last_result_preview": "No task sessions exist yet. Bootstrap the project with one narrow first task.",
                "aionis_replay_run_id": "",
                "validation_ok": None,
                "validation_summary": None,
            },
            "planner": {
                "stage": "cold_start_bootstrap",
                "active_role": "orchestrator",
                "next_action": next_action,
                "target_files": working_set[:6],
                "pending_validations": validation_paths[:3],
                "blockers": [],
            },
            "strategy": {
                "trust_signal": "cold_start_bootstrap",
                "task_family": "task:cold-start",
                "family_scope": "cold_start",
                "family_candidate_count": 0,
                "strategy_profile": "bootstrap_first_loop",
                "validation_style": "bootstrap_first",
                "role_sequence": ["investigator", "implementer", "verifier"],
                "working_set": working_set[:6],
                "validation_paths": validation_paths[:3],
                "selected_patterns": [],
                "preferred_artifacts": [],
                "artifact_budget": 0,
                "memory_source_limit": 0,
                "explanation": "No prior sessions exist yet; the shell is using repository structure and test roots as the bootstrap working surface.",
            },
            "routing": {
                "summary": {
                    "task_family": "task:cold-start",
                    "family_scope": "cold_start",
                    "routed_role_count": 0,
                    "routed_artifact_ref_count": 0,
                    "inherited_evidence_count": 0,
                    "hit_roles": [],
                    "miss_roles": ["investigator", "implementer", "verifier"],
                    "routing_reasons": [],
                }
            },
            "workflow": {
                "workflow_mode": "bootstrap",
                "stage": "cold_start_bootstrap",
                "active_role": "orchestrator",
            },
            "pattern_signals": {
                "dominant_affinity": "cold_start",
                "trusted_pattern_count": 0,
                "trusted_patterns": [],
                "task_family": "task:cold-start",
                "trust_signal": "cold_start_bootstrap",
            },
            "maintenance": {
                "summary": "Bootstrap context is active until the first successful task is recorded.",
                "continuity_status": "bootstrap_ready",
                "artifact_status": "empty",
                "memory_status": "bootstrap_only",
            },
            "instrumentation": {
                "status": "cold_start",
                "explanation": "There are no prior sessions yet; bootstrap hints come from the repository structure only.",
                "task_family": "task:cold-start",
                "selected_pattern_hit_count": 0,
                "routed_artifact_hit_rate": 0.0,
                "routed_same_family_task_ids": [],
            },
            "context_layers": {
                "facts": notes[:4],
                "episodes": [],
                "rules": [
                    "keep the first task narrow",
                    "prefer one runnable validation command before expanding the project surface",
                ],
                "static": [
                    f"Project identity: {self._project_identity}",
                    f"Project scope: {self._project_scope}",
                ],
                "decisions": [
                    "Stage: cold_start_bootstrap",
                    f"Next action: {next_action}",
                ],
                "tools": validation_paths[:3],
                "citations": working_set[:4],
            },
            "continuity": {
                "project_identity": self._project_identity,
                "project_scope": self._project_scope,
                "task_goal": "Bootstrap the project and record the first narrow task.",
                "strategy_profile": "bootstrap_first_loop",
                "validation_style": "bootstrap_first",
                "task_family": "task:cold-start",
                "bootstrap": snapshot,
            },
        }

    def bootstrap_overview(self) -> dict[str, Any]:
        snapshot = self.bootstrap_snapshot()
        canonical_views = self.bootstrap_canonical_views(snapshot)
        return {
            "task_id": None,
            "session_path": None,
            "bootstrap_snapshot": snapshot,
            "canonical_surface": {
                "execution_packet": None,
                "execution_packet_summary": None,
                "planner_packet": None,
                "strategy_summary": None,
                "pattern_signal_summary": None,
                "workflow_signal_summary": None,
                "routing_signal_summary": None,
                "maintenance_summary": None,
                "instrumentation_summary": None,
                "continuity_snapshot": canonical_views["continuity"],
                "context_layers_snapshot": canonical_views["context_layers"],
            },
            "canonical_views": canonical_views,
            "evaluation": {
                "status": str(snapshot.get("status") or "bootstrap_ready"),
                "score": None,
                "explanation": "Bootstrap context is active. Record the first narrow task to start family learning.",
            },
        }

    def initialize_project(self) -> dict[str, Any]:
        payload = self.bootstrap_overview()
        bootstrap_snapshot = payload["bootstrap_snapshot"]
        local_path = bootstrap_path(self._repo_root)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(bootstrap_snapshot, ensure_ascii=False, indent=2)
        local_path.write_text(serialized)
        project_path = project_bootstrap_path(self._project_scope)
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(serialized)
        doctor_payload = self._doctor()
        payload["initialized"] = True
        payload["bootstrap_path"] = str(local_path)
        payload["project_bootstrap_path"] = str(project_path)
        payload["setup"] = {
            "mode": doctor_payload.get("mode", "inspect-only"),
            "live_ready": bool(doctor_payload.get("live_ready")),
            "live_ready_summary": doctor_payload.get("live_ready_summary", doctor_payload.get("mode", "inspect-only")),
            "checks": doctor_payload.get("checks", []),
            "next_steps": doctor_payload.get("recommendations", []),
        }
        payload["host_contract"] = doctor_payload.get("host_contract")
        return payload

    def refresh_selected_strategy(self, session: SessionState) -> None:
        continuity = session.continuity_snapshot or {}
        passive = continuity.get("passive_observation") if isinstance(continuity, dict) else {}
        learning = continuity.get("learning") if isinstance(continuity, dict) else {}
        observed_files: list[str] = []
        if isinstance(passive, dict):
            changed_files = passive.get("changed_files")
            if isinstance(changed_files, list):
                observed_files = [item for item in changed_files if isinstance(item, str) and item.strip()][:6]
        observed_validation = ""
        if isinstance(learning, dict):
            observed_validation = str(learning.get("validation_command") or "").strip()
        effective_target_files = self._sessions.normalize_target_files([*observed_files, *session.target_files])
        effective_validation_commands = self._sessions.normalize_validation_commands(
            [*([observed_validation] if observed_validation else []), *session.validation_commands]
        )
        prior_sessions = load_recent_sessions(
            self._repo_root,
            project_scope=self._project_scope,
            exclude_task_id=session.task_id,
            limit=24,
        )
        for prior in prior_sessions:
            prior.target_files = normalize_target_paths(prior.target_files, repo_root=self._repo_root, limit=12)
            prior.validation_commands = self._sessions.normalize_validation_commands(prior.validation_commands)
        strategy = select_collaboration_strategy(
            prior_sessions=prior_sessions,
            target_files=effective_target_files,
            validation_commands=effective_validation_commands,
            task_text=session.goal,
            validation_summary=str((session.last_validation_result or {}).get("summary") or ""),
            failure_name=self._recovery.load_correction_failure_name(session),
        )
        session.selected_strategy_profile = strategy.strategy_profile
        session.selected_validation_style = strategy.validation_style
        session.selected_artifact_budget = strategy.artifact_limit
        session.selected_memory_source_limit = strategy.memory_source_limit
        session.selected_trust_signal = strategy.trust_signal
        session.selected_task_family = strategy.task_family
        session.selected_family_scope = strategy.family_scope
        session.selected_family_candidate_count = strategy.family_candidate_count
        session.selected_role_sequence = strategy.role_sequence[:3]
        session.selected_pattern_summaries = strategy.selected_pattern_summaries[:4]
        family_prior = self._load_family_prior(
            self._repo_root,
            self._project_scope,
            strategy.task_family,
        )
        if family_prior and bool(family_prior.get("seed_ready")):
            prior_strategy_profile = str(family_prior.get("dominant_strategy_profile") or "").strip()
            prior_validation_style = str(family_prior.get("dominant_validation_style") or "").strip()
            if prior_strategy_profile:
                session.selected_strategy_profile = prior_strategy_profile
            if prior_validation_style:
                session.selected_validation_style = prior_validation_style

    def record_learning(self, *, session: SessionState, source: str, validation: ValidationResult, auto_absorbed: bool) -> None:
        if not validation.ok:
            return
        observed_changed_files = (
            validation.changed_files[:6]
            if source == "validate" and isinstance(validation.changed_files, list) and validation.changed_files
            else []
        )
        learning_working_set = observed_changed_files or session.target_files[:6]
        if validation.command:
            session.validation_commands = self._sessions.normalize_validation_commands(
                [validation.command, *session.validation_commands]
            )
        learning = {
            "auto_absorbed": auto_absorbed,
            "source": source,
            "task_family": session.selected_task_family,
            "strategy_profile": session.selected_strategy_profile,
            "validation_style": session.selected_validation_style,
            "validation_command": validation.command or "",
            "validation_summary": validation.summary,
            "working_set": learning_working_set,
            "role_sequence": session.selected_role_sequence[:3],
            "artifact_refs": [item.path for item in session.artifacts[:4]],
        }
        snapshot = dict(session.continuity_snapshot or {})
        snapshot["learning"] = learning
        if observed_changed_files:
            session.target_files = self._sessions.normalize_target_files([*observed_changed_files, *session.target_files])
            snapshot["passive_observation"] = {
                "recorded": True,
                "source": "validate",
                "changed_files": observed_changed_files,
                "summary": "Observed successful validation against the current repo diff.",
            }
        session.continuity_snapshot = snapshot
        learning_label = "Auto-learned" if auto_absorbed else "Recorded validated"
        learning_lines = [
            f"{learning_label} success path via {source}.",
            *([f"{learning_label} validation: {validation.command}"] if validation.command else []),
            *([f"{learning_label} family: {session.selected_task_family}"] if session.selected_task_family else []),
            *(["Observed changed files via validate: " + ", ".join(observed_changed_files[:4])] if observed_changed_files else []),
        ]
        for line in learning_lines:
            if line not in session.promoted_insights:
                session.promoted_insights.append(line)

    def record_auto_learning(self, *, session: SessionState, source: str, validation: ValidationResult) -> None:
        self.record_learning(session=session, source=source, validation=validation, auto_absorbed=True)

    def record_recorded_learning(self, *, session: SessionState, source: str, validation: ValidationResult) -> None:
        self.record_learning(session=session, source=source, validation=validation, auto_absorbed=False)

    def refresh_auto_learning_store(self, session: SessionState) -> None:
        learning = (session.continuity_snapshot or {}).get("learning")
        if not isinstance(learning, dict) or not learning.get("auto_absorbed"):
            return
        existing = load_auto_learning_snapshot(self._repo_root, project_scope=self._project_scope)
        recent_samples = existing.get("recent_samples") if isinstance(existing, dict) else []
        if not isinstance(recent_samples, list):
            recent_samples = []
        passive = (session.continuity_snapshot or {}).get("passive_observation")
        observed_changed_files: list[str] = []
        if isinstance(passive, dict):
            changed_files = passive.get("changed_files")
            if isinstance(changed_files, list):
                observed_changed_files = [item for item in changed_files if isinstance(item, str) and item.strip()][:6]
        sample = {
            "task_id": session.task_id,
            "source": str(learning.get("source") or ""),
            "task_family": str(learning.get("task_family") or session.selected_task_family or ""),
            "strategy_profile": str(learning.get("strategy_profile") or session.selected_strategy_profile or ""),
            "validation_style": str(learning.get("validation_style") or session.selected_validation_style or ""),
            "validation_command": str(learning.get("validation_command") or ""),
            "validation_summary": str(learning.get("validation_summary") or ""),
            "working_set": (observed_changed_files or list(learning.get("working_set") or []))[:6],
            "observed_changed_files": observed_changed_files,
            "role_sequence": list(learning.get("role_sequence") or [])[:3],
            "artifact_refs": list(learning.get("artifact_refs") or [])[:4],
            "project_scope": session.project_scope,
            "project_identity": session.project_identity,
        }
        deduped = [sample]
        seen = {session.task_id}
        for item in recent_samples:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id") or "").strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            deduped.append(item)
        save_auto_learning_snapshot(
            repo_root=self._repo_root,
            project_scope=self._project_scope,
            payload={
                "project_identity": session.project_identity,
                "project_scope": session.project_scope,
                "recent_samples": deduped[:12],
            },
        )

    def save_session(self, session: SessionState):
        continuity = session.continuity_snapshot or {}
        if bool(continuity.get("app_delivery_mode")):
            session.delegation_packets = []
            session.delegation_returns = []
            session.collaboration_patterns = []
            session.selected_role_sequence = []
            session.selected_pattern_summaries = []
            session.execution_packet = None
            session.execution_packet_summary = None
            session.planner_packet = None
            session.strategy_summary = None
            session.pattern_signal_summary = None
            session.workflow_signal_summary = None
            session.routing_signal_summary = None
            session.maintenance_summary = None
            session.continuity_snapshot = build_continuity_snapshot(session)
            session.instrumentation_summary = self._build_instrumentation_summary(
                self._repo_root,
                self._project_scope,
                session,
            )
            self.refresh_auto_learning_store(session)
            reproject_shared_memory(session)
            session.context_layers_snapshot = {}
            return save_session(session)
        refresh_delegation_packets(session)
        refresh_collaboration_patterns(session)
        self.refresh_selected_strategy(session)
        refresh_delegation_packets(session)
        packet, summary = self._build_execution_packet(session)
        session.execution_packet = packet
        session.execution_packet_summary = summary
        (
            session.planner_packet,
            session.strategy_summary,
            session.pattern_signal_summary,
            session.workflow_signal_summary,
            session.routing_signal_summary,
            session.maintenance_summary,
        ) = build_provenance_surfaces(session, packet)
        session.continuity_snapshot = build_continuity_snapshot(session)
        session.instrumentation_summary = self._build_instrumentation_summary(
            self._repo_root,
            self._project_scope,
            session,
        )
        self.refresh_auto_learning_store(session)
        reproject_shared_memory(session)
        session.context_layers_snapshot = assemble_context_layers(session=session)
        return save_session(session)

    def canonical_surface(self, session: SessionState) -> dict[str, Any]:
        return self._evaluation.canonical_surface(session)

    def canonical_views(self, session: SessionState) -> dict[str, Any]:
        return self._evaluation.canonical_views(session)

    def serialized_session(self, session: SessionState) -> dict[str, Any]:
        return self._evaluation.serialized_session(session)

    def _task_controller_action_bar(self, *, task_id: str, session: SessionState) -> dict[str, Any] | None:
        canonical_views = self._evaluation.canonical_views(session)
        return controller_action_bar_payload(canonical_views.get("controller"), task_id=task_id)

    def persist_doc_result(
        self,
        *,
        task_id: str | None,
        action: str,
        doc_input: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not task_id:
            return payload
        session = self._sessions.load_session(task_id=task_id)
        if session is None:
            return payload
        created = self._sessions.record_doc_result(
            session=session,
            action=action,
            doc_input=doc_input,
            payload=payload,
        )
        path = self.save_session(session)
        enriched = dict(payload)
        enriched["task_id"] = task_id
        enriched["session_path"] = str(path)
        enriched["recorded_artifacts"] = [item.path for item in created]
        enriched["controller_action_bar"] = self._task_controller_action_bar(task_id=task_id, session=session)
        return enriched

    def persist_doc_event(
        self,
        *,
        task_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        session = self._sessions.load_session(task_id=task_id)
        if session is None:
            return dict(event)
        created = self._sessions.record_doc_event(session=session, event=event)
        path = self.save_session(session)
        payload = dict((event.get("payload") or {}) if isinstance(event, dict) else {})
        payload.setdefault("shell_view", f"doc_{event.get('doc_action', 'event')}")
        payload.setdefault("doc_action", event.get("doc_action"))
        payload.setdefault("doc_input", event.get("doc_input"))
        payload.setdefault("status", event.get("status"))
        payload["event_version"] = event.get("event_version")
        payload["event_source"] = event.get("event_source")
        payload["event_origin"] = "editor_extension"
        payload["recording_mode"] = "editor_event"
        payload["task_id"] = task_id
        payload["session_path"] = str(path)
        payload["recorded_artifacts"] = [item.path for item in created]
        payload["controller_action_bar"] = self._task_controller_action_bar(task_id=task_id, session=session)
        return payload

    def evaluate_session_model(self, session: SessionState) -> dict[str, Any]:
        return self._evaluation.evaluate_session_model(session)

    def collect_changed_files(self) -> list[str]:
        return self._workflow.collect_changed_files()

    def run_validation_commands(self, commands: list[str]) -> ValidationResult:
        return self._workflow.run_validation_commands(commands)

    def inspect_session(self, *, task_id: str) -> dict[str, Any]:
        return self._evaluation.inspect_session(task_id=task_id)

    def evaluate_session(self, *, task_id: str) -> dict[str, Any]:
        return self._evaluation.evaluate_session(task_id=task_id)

    def validate_session(
        self,
        *,
        task_id: str,
        learning_source: str = "validate",
        apply_validation_feedback_fn: Callable[[SessionState, ValidationResult], None],
        record_auto_learning_fn: Callable[..., None],
    ) -> dict[str, Any]:
        return self._workflow.validate_session(
            task_id=task_id,
            learning_source=learning_source,
            apply_validation_feedback_fn=apply_validation_feedback_fn,
            record_auto_learning_fn=record_auto_learning_fn,
        )

    def workflow_next(
        self,
        *,
        task_id: str,
        validate_session_fn: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        return self._workflow.workflow_next(
            task_id=task_id,
            validate_session_fn=validate_session_fn,
        )

    def workflow_fix(
        self,
        *,
        task_id: str,
        validate_session_fn: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        return self._workflow.workflow_fix(
            task_id=task_id,
            validate_session_fn=validate_session_fn,
        )

    def shell_status(self, *, task_id: str | None = None) -> dict[str, Any]:
        return self._evaluation.shell_status(task_id=task_id)

    def backfill(
        self,
        *,
        task_id: str,
        rerun_recovery: bool = False,
        apply_validation_feedback_fn: Callable[[SessionState, ValidationResult], None],
        persist_artifacts_fn: Callable[..., None],
    ) -> dict[str, Any]:
        return self._backfill.backfill(
            task_id=task_id,
            rerun_recovery=rerun_recovery,
            apply_validation_feedback_fn=apply_validation_feedback_fn,
            persist_artifacts_fn=persist_artifacts_fn,
        )
