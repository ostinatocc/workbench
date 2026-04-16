from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from .delivery_results import DeliveryExecutionResult
from .delivery_families import (
    delivery_family_workspace_validation_commands,
    infer_delivery_family_from_workspace,
)
from .delivery_workspace import DeliveryWorkspaceAdapter
from .failure_classification import classify_execution_failure_reason
from .recovery_service import ValidationResult
from .session import SessionState
from .tracing import TraceRecorder, extract_target_files
from .utils import stringify_result
from .workflow_surface_service import _compact_output, _first_signal_line, _validation_command_looks_runnable


class DeliveryExecutor:
    def __init__(
        self,
        *,
        execution_host: Any,
        trace: TraceRecorder,
        workspace: DeliveryWorkspaceAdapter,
        run_validation_commands_fn: Callable[[list[str]], ValidationResult],
    ) -> None:
        self._execution_host = execution_host
        self._trace = trace
        self._workspace = workspace
        self._run_validation_commands = run_validation_commands_fn

    def reset_task_workspace(self, *, task_id: str) -> Path:
        return self._workspace.reset_task_workspace(task_id=task_id)

    def task_workspace_root(self, *, task_id: str) -> Path:
        return self._workspace.task_workspace_root(task_id=task_id)

    def _task_title(self, session: SessionState) -> str:
        state = session.app_harness_state
        if state and state.product_spec and state.product_spec.title:
            return state.product_spec.title
        return session.task_id or "Aionis Delivery App"

    def _default_workspace_validation_commands(self, *, workspace_root: Path) -> list[str]:
        family_id = infer_delivery_family_from_workspace(workspace_root)
        return delivery_family_workspace_validation_commands(
            family_id,
            workspace_root=workspace_root,
        )

    def _trace_path(self, *, workspace_root: Path) -> Path:
        return workspace_root / ".aionis-delivery-trace.json"

    def _load_trace_snapshot(self, *, trace_path: Path) -> dict[str, Any]:
        if not trace_path.exists():
            return {}
        try:
            payload = json.loads(trace_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _latest_trace_build_result(self, *, trace_path: Path) -> tuple[str, bool | None]:
        payload = self._load_trace_snapshot(trace_path=trace_path)
        steps = payload.get("steps")
        if not isinstance(steps, list):
            return "", None
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            if str(step.get("tool_name") or "").strip() != "execute":
                continue
            tool_input = step.get("tool_input")
            tool_input = tool_input if isinstance(tool_input, dict) else {}
            command = str(tool_input.get("command") or "").strip()
            if "build" not in command:
                continue
            status = str(step.get("status") or "").strip()
            return command, status == "success"
        return "", None

    def _run_workspace_validation_commands(self, *, workspace_root: Path, commands: list[str]) -> ValidationResult:
        normalized = [command.strip() for command in commands if isinstance(command, str) and command.strip()]
        runnable = [
            command
            for command in normalized
            if _validation_command_looks_runnable(command, str(workspace_root))
        ]
        default_commands = self._default_workspace_validation_commands(workspace_root=workspace_root)
        commands_to_run = runnable or default_commands
        if runnable and default_commands:
            if len(runnable) < len(default_commands) and all(command in default_commands for command in runnable):
                commands_to_run = default_commands
        if not commands_to_run:
            return ValidationResult(
                ok=True,
                command=None,
                exit_code=None,
                summary="No runnable validation commands were configured for the task workspace.",
                output="",
                changed_files=[],
            )
        env = os.environ.copy()
        env["PWD"] = str(workspace_root)
        changed_files = sorted(self._workspace.snapshot_workspace_state(workspace_root=workspace_root).keys())
        for command in commands_to_run:
            completed = subprocess.run(
                command,
                cwd=workspace_root,
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
            command=commands_to_run[-1],
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=changed_files,
        )

    def bootstrap_app_generate(
        self,
        *,
        session: SessionState,
        delivery_family: str = "",
        validation_commands: list[str],
        execution_summary: str,
        changed_target_hints: list[str],
        install_and_build: bool = False,
    ) -> DeliveryExecutionResult:
        if delivery_family:
            workspace_root = self._workspace.bootstrap_delivery_family_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
                family_id=delivery_family,
            )
        else:
            workspace_root = self._workspace.ensure_react_app_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        trace_path = self._trace_path(workspace_root=workspace_root)
        artifact_paths = self._workspace.infer_artifact_paths(
            changed_files=list(changed_target_hints or []),
            workspace_root=workspace_root,
        )
        preview_command = self._workspace.infer_preview_command(
            artifact_paths=artifact_paths,
            workspace_root=workspace_root,
        )
        validation = self._run_workspace_validation_commands(
            workspace_root=workspace_root,
            commands=validation_commands,
        ) if install_and_build or validation_commands else ValidationResult(
            ok=True,
            command=None,
            exit_code=None,
            summary="Task workspace scaffolded. Install dependencies before previewing the app.",
            output="",
            changed_files=sorted(self._workspace.snapshot_workspace_state(workspace_root=workspace_root).keys()),
        )
        return DeliveryExecutionResult(
            execution_summary=execution_summary or "Scaffolded the bounded task workspace for the current sprint.",
            changed_target_hints=list(changed_target_hints or []),
            changed_files=sorted(self._workspace.snapshot_workspace_state(workspace_root=workspace_root).keys())[:8],
            artifact_root=str(workspace_root),
            artifact_paths=artifact_paths,
            artifact_kind=self._workspace.infer_artifact_kind(artifact_paths=artifact_paths),
            preview_command=preview_command,
            trace_path=str(trace_path),
            validation_command=validation.command or "",
            validation_summary=validation.summary or "",
            validation_ok=validation.ok,
        )

    def execute_app_generate(
        self,
        *,
        session: SessionState,
        delivery_family: str = "",
        system_parts: list[str],
        task: str,
        memory_sources: list[str],
        validation_commands: list[str],
        execution_summary: str,
        changed_target_hints: list[str],
    ) -> DeliveryExecutionResult:
        workspace_root = self._workspace.ensure_empty_task_workspace(task_id=session.task_id)
        web_bootstrap_targets = {
            "package.json",
            "vite.config.ts",
            "tsconfig.json",
            "index.html",
            "src/main.tsx",
            "src/App.tsx",
            "src/styles.css",
        }
        vue_web_bootstrap_targets = {
            "package.json",
            "vite.config.ts",
            "tsconfig.json",
            "index.html",
            "src/main.ts",
            "src/App.vue",
            "src/styles.css",
        }
        svelte_web_bootstrap_targets = {
            "package.json",
            "vite.config.ts",
            "tsconfig.json",
            "svelte.config.js",
            "index.html",
            "src/main.ts",
            "src/App.svelte",
            "src/app.css",
        }
        nextjs_web_bootstrap_targets = {
            "package.json",
            "next.config.mjs",
            "tsconfig.json",
            "next-env.d.ts",
            "app/layout.tsx",
            "app/page.tsx",
            "app/globals.css",
        }
        python_api_bootstrap_targets = {"requirements.txt", "main.py"}
        node_api_bootstrap_targets = {"package.json", "main.js"}
        if delivery_family:
            missing_family_shell = (
                delivery_family == "react_vite_web" and not (workspace_root / "package.json").exists()
            ) or (
                delivery_family == "nextjs_web" and not (workspace_root / "app" / "page.tsx").exists()
            ) or (
                delivery_family == "vue_vite_web" and not (workspace_root / "src" / "App.vue").exists()
            ) or (
                delivery_family == "svelte_vite_web" and not (workspace_root / "src" / "App.svelte").exists()
            ) or (
                delivery_family == "python_fastapi_api" and not (workspace_root / "main.py").exists()
            ) or (
                delivery_family == "node_express_api" and not (workspace_root / "main.js").exists()
            )
            if missing_family_shell:
                workspace_root = self._workspace.bootstrap_delivery_family_workspace(
                    task_id=session.task_id,
                    title=self._task_title(session),
                    family_id=delivery_family,
                )
        elif not (workspace_root / "package.json").exists() and web_bootstrap_targets.intersection(memory_sources):
            workspace_root = self._workspace.bootstrap_empty_web_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        elif not (workspace_root / "src" / "App.vue").exists() and vue_web_bootstrap_targets.intersection(memory_sources):
            workspace_root = self._workspace.bootstrap_empty_vue_web_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        elif not (workspace_root / "src" / "App.svelte").exists() and svelte_web_bootstrap_targets.intersection(memory_sources):
            workspace_root = self._workspace.bootstrap_empty_svelte_web_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        elif not (workspace_root / "app" / "page.tsx").exists() and nextjs_web_bootstrap_targets.intersection(memory_sources):
            workspace_root = self._workspace.bootstrap_empty_nextjs_web_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        elif not (workspace_root / "main.py").exists() and python_api_bootstrap_targets.intersection(memory_sources):
            workspace_root = self._workspace.bootstrap_empty_python_api_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        elif not (workspace_root / "main.js").exists() and node_api_bootstrap_targets.intersection(memory_sources):
            workspace_root = self._workspace.bootstrap_empty_node_api_workspace(
                task_id=session.task_id,
                title=self._task_title(session),
            )
        trace_path = self._trace_path(workspace_root=workspace_root)
        before = self._workspace.snapshot_workspace_state(workspace_root=workspace_root)
        try:
            invoke_timeout_seconds = getattr(
                self._execution_host,
                "live_app_delivery_timeout_seconds",
                lambda: 900.0,
            )()
            if hasattr(self._execution_host, "invoke_delivery_task"):
                result = self._execution_host.invoke_delivery_task(
                    system_parts=system_parts,
                    memory_sources=memory_sources,
                    root_dir=str(workspace_root),
                    task=task,
                    timeout_seconds=invoke_timeout_seconds,
                    trace_path=str(trace_path),
                )
            else:
                agent = self._execution_host.build_agent(
                    system_parts=system_parts,
                    memory_sources=memory_sources,
                    timeout_pressure=False,
                    root_dir=str(workspace_root),
                    model_timeout_seconds_override=invoke_timeout_seconds,
                    use_builtin_subagents=False,
                )
                result = self._execution_host.invoke(
                    agent,
                    {"messages": [{"role": "user", "content": task}]},
                    timeout_seconds=invoke_timeout_seconds,
                )
        except Exception as exc:
            after = self._workspace.snapshot_workspace_state(workspace_root=workspace_root)
            changed_files = self._workspace.changed_workspace_files(before=before, after=after)
            failure_reason = str(exc).strip()
            failure_class = classify_execution_failure_reason(failure_reason)
            _latest_build_command, build_ok = self._latest_trace_build_result(trace_path=trace_path)
            artifact_paths = self._workspace.infer_artifact_paths(
                changed_files=changed_files,
                workspace_root=workspace_root,
            )
            if build_ok is not True and failure_class in {"provider_transient_error", "provider_first_turn_stall"}:
                artifact_paths = [path for path in artifact_paths if path != "dist/index.html"]
            artifact_kind = self._workspace.infer_artifact_kind(artifact_paths=artifact_paths)
            preview_command = self._workspace.infer_preview_command(
                artifact_paths=artifact_paths,
                workspace_root=workspace_root,
            )
            validation_command = ""
            validation_summary = ""
            validation_ok: bool | None = None
            allow_recovery_validation = not (
                failure_class in {"provider_transient_error", "provider_first_turn_stall"}
                and build_ok is not True
                and not changed_files
            )
            if (artifact_paths or changed_files) and allow_recovery_validation:
                validation = self._run_workspace_validation_commands(
                    workspace_root=workspace_root,
                    commands=validation_commands,
                )
                validation_command = validation.command or ""
                validation_summary = validation.summary or ""
                validation_ok = validation.ok
                if validation.ok:
                    after = self._workspace.snapshot_workspace_state(workspace_root=workspace_root)
                    changed_files = self._workspace.changed_workspace_files(before=before, after=after)
                    artifact_paths = self._workspace.infer_artifact_paths(
                        changed_files=changed_files,
                        workspace_root=workspace_root,
                    )
                    if build_ok is not True and failure_class in {"provider_transient_error", "provider_first_turn_stall"}:
                        artifact_paths = [path for path in artifact_paths if path != "dist/index.html"]
                    artifact_kind = self._workspace.infer_artifact_kind(artifact_paths=artifact_paths)
                    preview_command = self._workspace.infer_preview_command(
                        artifact_paths=artifact_paths,
                        workspace_root=workspace_root,
                    )
                    failure_reason = ""
            return DeliveryExecutionResult(
                execution_summary=execution_summary,
                changed_target_hints=list(changed_target_hints),
                changed_files=changed_files,
                artifact_root=str(workspace_root),
                artifact_paths=artifact_paths,
                artifact_kind=artifact_kind,
                preview_command=preview_command,
                trace_path=str(trace_path),
                validation_command=validation_command,
                validation_summary=validation_summary,
                validation_ok=validation_ok,
                failure_reason=failure_reason,
                raw_result_preview=validation_summary or str(exc).strip(),
            )
        preview = stringify_result(result)
        after = self._workspace.snapshot_workspace_state(workspace_root=workspace_root)
        changed_files = self._workspace.changed_workspace_files(before=before, after=after)
        if not changed_files:
            changed_files = extract_target_files(self._trace.export(), repo_root=str(workspace_root))
        validation = self._run_workspace_validation_commands(
            workspace_root=workspace_root,
            commands=validation_commands,
        )
        artifact_paths = self._workspace.infer_artifact_paths(
            changed_files=changed_files,
            workspace_root=workspace_root,
        )
        artifact_kind = self._workspace.infer_artifact_kind(artifact_paths=artifact_paths)
        preview_command = self._workspace.infer_preview_command(
            artifact_paths=artifact_paths,
            workspace_root=workspace_root,
        )
        return DeliveryExecutionResult(
            execution_summary=preview or execution_summary,
            changed_target_hints=list(changed_target_hints) or changed_files[:4],
            changed_files=changed_files,
            artifact_root=str(workspace_root),
            artifact_paths=artifact_paths,
            artifact_kind=artifact_kind,
            preview_command=preview_command,
            trace_path=str(trace_path),
            validation_command=validation.command or "",
            validation_summary=validation.summary or "",
            validation_ok=validation.ok,
            raw_result_preview=preview,
        )

    def recover_app_generate(
        self,
        *,
        session: SessionState,
        validation_commands: list[str],
        execution_summary: str,
        changed_target_hints: list[str],
    ) -> DeliveryExecutionResult | None:
        workspace_root = self.task_workspace_root(task_id=session.task_id)
        if not workspace_root.exists():
            return None
        trace_path = self._trace_path(workspace_root=workspace_root)
        snapshot = self._workspace.snapshot_workspace_state(workspace_root=workspace_root)
        if not snapshot and not trace_path.exists():
            return None
        changed_files = sorted(snapshot.keys())[:8]
        validation_command, build_ok = self._latest_trace_build_result(trace_path=trace_path)
        artifact_paths = self._workspace.infer_artifact_paths(
            changed_files=changed_files,
            workspace_root=workspace_root,
        )
        if build_ok is not True:
            artifact_paths = [path for path in artifact_paths if path != "dist/index.html"]
        artifact_kind = self._workspace.infer_artifact_kind(artifact_paths=artifact_paths)
        preview_command = self._workspace.infer_preview_command(
            artifact_paths=artifact_paths,
            workspace_root=workspace_root,
        )
        validation_summary = ""
        validation_ok: bool | None = None
        failure_reason = ""
        if build_ok is True:
            validation_summary = "Validation commands passed."
            validation_ok = True
        elif build_ok is False:
            validation_summary = "Validation failed: latest build command did not complete successfully."
            validation_ok = False
            failure_reason = validation_summary
        else:
            validation = self._run_workspace_validation_commands(
                workspace_root=workspace_root,
                commands=validation_commands,
            )
            validation_command = validation.command or ""
            validation_summary = validation.summary or ""
            validation_ok = validation.ok
            failure_reason = "" if validation.ok else validation.summary or ""
        if not artifact_paths:
            return None
        return DeliveryExecutionResult(
            execution_summary=execution_summary,
            changed_target_hints=list(changed_target_hints or []),
            changed_files=changed_files,
            artifact_root=str(workspace_root),
            artifact_paths=artifact_paths,
            artifact_kind=artifact_kind,
            preview_command=preview_command,
            trace_path=str(trace_path),
            validation_command=validation_command or "",
            validation_summary=validation_summary,
            validation_ok=validation_ok,
            failure_reason=failure_reason,
        )
