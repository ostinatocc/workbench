from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .controller_shell import controller_action_bar_payload
from .policies import normalize_session_memory, refresh_collaboration_patterns
from .recovery_service import RecoveryService, ValidationResult
from .session import SessionState, load_session
from .session_service import SessionService


def _result_preview(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return text.strip()[:240]


def _strip_repo_root_prefix(command: str, repo_root: str) -> str:
    cleaned = command.strip()
    repo_root_path = str(Path(repo_root).expanduser().resolve())
    prefixes = (
        f"cd {repo_root_path} && ",
        f'cd "{repo_root_path}" && ',
        f"cd '{repo_root_path}' && ",
    )
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):].strip()
    cleaned = re.sub(r"""^cd\s+(?:"[^"]+"|'[^']+'|[^\s]+)\s*&&\s*""", "", cleaned)
    return cleaned


def _normalize_legacy_evidence_line(line: str, repo_root: str) -> str:
    cleaned = line.strip()
    if cleaned.startswith("Executed: "):
        command = cleaned[len("Executed: ") :]
        command = re.sub(r"PYTHONPATH=/src(?=\s|$)", "PYTHONPATH=src", command)
        command = re.sub(r"(^|\s)/((?:src|tests)/)", r"\1\2", command)
        command = command.replace("sh /.aionis-workbench/", "sh .aionis-workbench/")
        return "Executed: " + _strip_repo_root_prefix(command, repo_root)
    return cleaned


class BackfillService:
    def __init__(
        self,
        *,
        repo_root: str,
        project_identity: str,
        project_scope: str,
        sessions: SessionService,
        recovery: RecoveryService,
        maybe_auto_consolidate_fn: Callable[..., dict[str, Any]],
        save_session_fn: Callable[[SessionState], Any],
        canonical_surface_fn: Callable[[SessionState], dict[str, Any]],
        canonical_views_fn: Callable[[SessionState], dict[str, Any]],
        evaluate_session_model_fn: Callable[[SessionState], dict[str, Any]],
    ) -> None:
        self._repo_root = repo_root
        self._project_identity = project_identity
        self._project_scope = project_scope
        self._sessions = sessions
        self._recovery = recovery
        self._maybe_auto_consolidate = maybe_auto_consolidate_fn
        self._save_session = save_session_fn
        self._canonical_surface = canonical_surface_fn
        self._canonical_views = canonical_views_fn
        self._evaluate_session_model = evaluate_session_model_fn

    def backfill(
        self,
        *,
        task_id: str,
        rerun_recovery: bool = False,
        apply_validation_feedback_fn: Callable[[SessionState, ValidationResult], None],
        persist_artifacts_fn: Callable[..., None],
    ) -> dict[str, Any]:
        session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._repo_root
        session.project_identity = session.project_identity or self._project_identity
        session.project_scope = session.project_scope or self._project_scope
        session.target_files = self._sessions.normalize_target_files(session.target_files)
        session.validation_commands = self._sessions.normalize_validation_commands(session.validation_commands)
        for item in session.delegation_returns:
            item.acceptance_checks = self._sessions.normalize_validation_commands(item.acceptance_checks)
            item.evidence = [
                _normalize_legacy_evidence_line(line, self._repo_root)
                for line in item.evidence
                if isinstance(line, str) and line.strip()
            ][:6]
        if not session.last_result_preview:
            latest = next(
                (
                    item.split("Latest execution outcome: ", 1)[1].strip()
                    for item in session.promoted_insights
                    if isinstance(item, str) and item.startswith("Latest execution outcome: ")
                ),
                "",
            )
            session.last_result_preview = latest[:240]
        if not session.last_validation_result:
            for artifact in session.artifacts:
                if artifact.kind != "validation_result":
                    continue
                artifact_path = Path(self._repo_root) / artifact.path
                if not artifact_path.exists():
                    continue
                try:
                    session.last_validation_result = json.loads(artifact_path.read_text())
                except Exception:
                    session.last_validation_result = {}
                break
        if session.last_validation_result and session.status in {"", "pending", "running"}:
            session.status = "validated" if session.last_validation_result.get("ok") else "needs_attention"
        failure_artifact = None
        if session.status == "paused" and not any(
            artifact.kind in {"timeout_artifact", "exception_artifact"} for artifact in session.artifacts
        ):
            message = session.last_result_preview or "Workbench execution paused."
            failure_artifact = {
                "kind": "timeout_artifact" if "timed out" in message.lower() else "exception_artifact",
                "role": "orchestrator",
                "summary": f"Workbench execution failed: {message}",
                "message": message,
                "trace_summary": session.last_trace_summary,
                "working_set": session.target_files[:8],
                "changed_files": [],
                "evidence": session.working_memory[:8],
            }
        correction_packet = self._recovery.build_correction_packet(session)
        synthesized_validation = None
        if session.last_validation_result:
            synthesized_validation = ValidationResult(
                ok=bool(session.last_validation_result.get("ok")),
                command=session.last_validation_result.get("command"),
                exit_code=session.last_validation_result.get("exit_code"),
                summary=str(session.last_validation_result.get("summary") or ""),
                output=str(session.last_validation_result.get("output") or ""),
                changed_files=[
                    value
                    for value in session.last_validation_result.get("changed_files", [])
                    if isinstance(value, str) and value.strip()
                ],
            )
        rollback_recovery = None
        if (
            synthesized_validation
            and not synthesized_validation.ok
            and any(artifact.kind == "rollback_hint_artifact" for artifact in session.artifacts)
            and any(artifact.kind == "correction_packet_artifact" for artifact in session.artifacts)
        ):
            if rerun_recovery:
                rollback_recovery = self._recovery.attempt_rollback_recovery(
                    session,
                    max_single_candidates=2,
                    max_pair_candidates=1,
                    max_triple_candidates=0,
                )
                if (
                    isinstance(rollback_recovery, dict)
                    and rollback_recovery.get("attempted")
                    and isinstance(rollback_recovery.get("validation"), ValidationResult)
                ):
                    synthesized_validation = rollback_recovery["validation"]
                    session.last_validation_result = dict(synthesized_validation.__dict__)
                    session.last_result_preview = _result_preview(synthesized_validation.summary)
                    apply_validation_feedback_fn(session, synthesized_validation)
            else:
                rollback_recovery = self._recovery.build_existing_rollback_recovery(session)
        refresh_collaboration_patterns(session)
        normalize_session_memory(session)
        self._recovery.apply_timeout_strategy(session)
        persist_artifacts_fn(
            session=session,
            validation=synthesized_validation,
            failure=failure_artifact,
            correction=correction_packet,
            rollback=self._recovery.build_rollback_hint(
                session=session,
                validation=synthesized_validation,
                recovery_result=rollback_recovery,
            ),
        )
        path = self._save_session(session)
        auto_consolidation = self._maybe_auto_consolidate(trigger="backfill")
        canonical_views = self._canonical_views(session)
        return {
            "session_path": str(path),
            "session": json.loads(session.to_json()),
            "canonical_surface": self._canonical_surface(session),
            "canonical_views": canonical_views,
            "controller_action_bar": controller_action_bar_payload(
                canonical_views.get("controller"),
                task_id=session.task_id,
            ),
            "evaluation": self._evaluate_session_model(session),
            "auto_consolidation": auto_consolidation,
        }
