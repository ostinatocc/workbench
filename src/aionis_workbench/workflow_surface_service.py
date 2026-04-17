from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from .controller_shell import controller_action_bar_payload
from .recovery_service import ValidationResult
from .session import SessionState, load_session
from .session_service import SessionService


def _first_signal_line(output: str) -> str:
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return ""


def _compact_output(output: str, *, limit: int = 1200) -> str:
    cleaned = output.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n...[truncated]"


def _validation_command_looks_runnable(command: str, repo_root: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return True
    if not tokens:
        return False
    index = 0
    while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith(("/", "./", "../")):
        index += 1
    if index >= len(tokens):
        return False
    runner = tokens[index]
    args = tokens[index + 1 :]
    candidate: str | None = None
    if runner.startswith("python") or runner in {"python", "python3", "python3.11", "sh", "bash", "zsh"}:
        filtered = [arg for arg in args if arg]
        if filtered:
            if filtered[0] in {"-m", "-c"}:
                return True
            candidate = next((arg for arg in filtered if not arg.startswith("-")), None)
            if candidate == "m":
                return True
            if candidate == "c":
                return True
    if runner == "node":
        filtered = [arg for arg in args if arg]
        if filtered and filtered[0] in {"-e", "--eval"}:
            return True
    if not candidate:
        return True
    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        return candidate_path.exists()
    return (Path(repo_root) / candidate_path).exists()


class WorkflowSurfaceService:
    def __init__(
        self,
        *,
        repo_root: str,
        project_scope: str,
        sessions: SessionService,
        load_family_prior_fn: Callable[[str, str, str], dict[str, Any]],
        save_session_fn: Callable[[SessionState], Any],
        canonical_views_fn: Callable[[SessionState], dict[str, Any]],
    ) -> None:
        self._repo_root = repo_root
        self._project_scope = project_scope
        self._sessions = sessions
        self._load_family_prior = load_family_prior_fn
        self._save_session = save_session_fn
        self._canonical_views = canonical_views_fn

    def _attach_controller_action_bar(
        self,
        payload: dict[str, Any],
        *,
        task_id: str,
        canonical_views: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        if isinstance(payload.get("controller_action_bar"), dict):
            return payload
        views = canonical_views if isinstance(canonical_views, dict) else payload.get("canonical_views")
        if not isinstance(views, dict):
            return payload
        action_bar = controller_action_bar_payload(views.get("controller"), task_id=task_id)
        if action_bar is None:
            return payload
        enriched = dict(payload)
        enriched["controller_action_bar"] = action_bar
        return enriched

    def _reviewer_acceptance_checks(self, canonical_views: dict[str, Any]) -> list[str]:
        reviewer = canonical_views.get("reviewer") or {}
        if not isinstance(reviewer, dict):
            return []
        acceptance_checks = reviewer.get("acceptance_checks") or []
        if not isinstance(acceptance_checks, list):
            return []
        return [item.strip() for item in acceptance_checks if isinstance(item, str) and item.strip()]

    def _reviewer_gate_summary(self, canonical_views: dict[str, Any]) -> dict[str, Any] | None:
        reviewer = canonical_views.get("reviewer") or {}
        if not isinstance(reviewer, dict):
            return None
        standard = str(reviewer.get("standard") or "").strip()
        ready_required = reviewer.get("ready_required") is True
        acceptance_checks = self._reviewer_acceptance_checks(canonical_views)
        resume_anchor = str(reviewer.get("resume_anchor") or "").strip() or None
        if not (standard or ready_required or acceptance_checks or resume_anchor):
            return None
        return {
            "standard": standard or None,
            "ready_required": ready_required,
            "acceptance_checks": acceptance_checks,
            "resume_anchor": resume_anchor,
            "gated_validation": bool(ready_required and acceptance_checks),
        }

    def collect_changed_files(self) -> list[str]:
        collected: list[str] = []
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self._repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            status_result = None
        if status_result and status_result.stdout:
            for raw_line in status_result.stdout.splitlines():
                line = raw_line.rstrip()
                if len(line) < 4:
                    continue
                path_text = line[3:].strip()
                if not path_text:
                    continue
                if " -> " in path_text:
                    path_text = path_text.split(" -> ", 1)[1].strip()
                if path_text:
                    collected.append(path_text)
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=self._repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            diff_result = None
        if diff_result and diff_result.stdout:
            collected.extend(line.strip() for line in diff_result.stdout.splitlines() if line.strip())
        return self._sessions.normalize_target_files(list(dict.fromkeys(collected)))

    def run_validation_commands(self, commands: list[str]) -> ValidationResult:
        normalized = self._sessions.normalize_validation_commands(commands)
        if not normalized:
            return ValidationResult(
                ok=True,
                command=None,
                exit_code=None,
                summary="No validation commands were configured.",
                output="",
                changed_files=self.collect_changed_files(),
            )
        env = os.environ.copy()
        env["PWD"] = self._repo_root
        changed_files = self.collect_changed_files()
        for command in normalized:
            completed = subprocess.run(
                command,
                cwd=self._repo_root,
                shell=True,
                capture_output=True,
                text=True,
                env=env,
            )
            combined_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
            if completed.returncode != 0:
                first_line = _first_signal_line(combined_output) or f"Command exited with {completed.returncode}."
                return ValidationResult(
                    ok=False,
                    command=command,
                    exit_code=completed.returncode,
                    summary=f"Validation failed: {first_line}",
                    output=_compact_output(combined_output),
                    changed_files=changed_files,
                )
        return ValidationResult(
            ok=True,
            command=normalized[-1],
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=changed_files,
        )

    def validate_session(
        self,
        *,
        task_id: str,
        learning_source: str = "validate",
        apply_validation_feedback_fn: Callable[[SessionState, ValidationResult], None],
        record_auto_learning_fn: Callable[..., None],
    ) -> dict[str, Any]:
        session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._repo_root
        self._save_session(session)
        canonical_views = self._canonical_views(session)
        normalized_commands = self._sessions.normalize_validation_commands(session.validation_commands)
        reviewer_acceptance = self._reviewer_acceptance_checks(canonical_views)
        reviewer_gate = self._reviewer_gate_summary(canonical_views)
        candidate_commands = reviewer_acceptance or normalized_commands
        runnable_commands = [
            command
            for command in candidate_commands
            if _validation_command_looks_runnable(command, self._repo_root)
        ]
        validation = self.run_validation_commands(runnable_commands or candidate_commands[:1] or session.validation_commands)
        apply_validation_feedback_fn(session, validation)
        record_auto_learning_fn(session=session, source=learning_source, validation=validation)
        path = self._save_session(session)
        result = {
            "session_path": str(path),
            "validation": dict(validation.__dict__),
            "canonical_views": self._canonical_views(session),
            "reviewer_gate": reviewer_gate,
        }
        return self._attach_controller_action_bar(
            result,
            task_id=task_id,
            canonical_views=result.get("canonical_views"),
        )

    def workflow_next(
        self,
        *,
        task_id: str,
        validate_session_fn: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._repo_root
        path = self._save_session(session)
        canonical_views = self._canonical_views(session)
        planner = canonical_views.get("planner", {})
        strategy = canonical_views.get("strategy", {})
        reviewer_gate = self._reviewer_gate_summary(canonical_views)
        next_action = planner.get("next_action") or "Inspect the task surfaces before deciding the next step."
        pending_validations = planner.get("pending_validations") or []
        selected_validation_paths = (canonical_views.get("strategy") or {}).get("validation_paths") or []
        task_family = str(strategy.get("task_family") or "")
        family_prior = self._load_family_prior(self._repo_root, self._project_scope, task_family)
        recommendation = str(family_prior.get("seed_recommendation") or "") if family_prior and not family_prior.get("seed_ready") else ""
        if session.validation_commands or pending_validations or selected_validation_paths:
            validated = validate_session_fn(task_id=task_id)
            validated["shell_view"] = "next"
            validated["workflow_next"] = {
                "action": "validate",
                "reason": next_action,
                "recommendation": recommendation,
            }
            validated["reviewer_gate"] = reviewer_gate
            return self._attach_controller_action_bar(validated, task_id=task_id)
        return self._attach_controller_action_bar({
            "shell_view": "next",
            "task_id": task_id,
            "session_path": str(path),
            "canonical_views": canonical_views,
            "workflow_next": {
                "action": "show",
                "reason": next_action,
                "recommendation": recommendation,
            },
            "reviewer_gate": reviewer_gate,
        }, task_id=task_id, canonical_views=canonical_views)

    def workflow_fix(
        self,
        *,
        task_id: str,
        validate_session_fn: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        session = load_session(self._repo_root, task_id, project_scope=self._project_scope)
        if session is None:
            raise FileNotFoundError(f"No session found for task_id={task_id}")
        session.repo_root = self._repo_root
        path = self._save_session(session)
        canonical_views = self._canonical_views(session)
        planner = canonical_views.get("planner", {})
        strategy = canonical_views.get("strategy", {})
        reviewer_gate = self._reviewer_gate_summary(canonical_views)
        next_action = planner.get("next_action") or "Inspect the task surfaces before deciding the next step."
        pending_validations = planner.get("pending_validations") or []
        selected_validation_paths = (canonical_views.get("strategy") or {}).get("validation_paths") or []
        task_family = str(strategy.get("task_family") or "")
        family_prior = self._load_family_prior(self._repo_root, self._project_scope, task_family)
        recommendation = str(family_prior.get("seed_recommendation") or "") if family_prior and not family_prior.get("seed_ready") else ""
        if session.validation_commands or pending_validations or selected_validation_paths:
            validated = validate_session_fn(task_id=task_id, learning_source="workflow_closure")
            validated["shell_view"] = "fix"
            validated["workflow_next"] = {
                "action": "validate",
                "reason": next_action,
                "recommendation": recommendation,
            }
            validated["reviewer_gate"] = reviewer_gate
            return self._attach_controller_action_bar(validated, task_id=task_id)
        return self._attach_controller_action_bar({
            "shell_view": "fix",
            "task_id": task_id,
            "session_path": str(path),
            "canonical_views": canonical_views,
            "workflow_next": {
                "action": "show",
                "reason": next_action,
                "recommendation": recommendation,
            },
            "reviewer_gate": reviewer_gate,
        }, task_id=task_id, canonical_views=canonical_views)
