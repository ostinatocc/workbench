from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _legacy_aionis_workspace_root() -> Path:
    return (Path.home() / "Desktop" / "Aionis").resolve()


def _workbench_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_optional_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    return Path(value).expanduser().resolve()


def _package_root_from_workspace_root(workspace_root: str | Path) -> Path:
    return Path(workspace_root).expanduser().resolve() / "packages" / "aionis-doc"


def _looks_like_aionisdoc_package_root(path: Path) -> bool:
    return (path / "package.json").exists()


def _iter_repo_search_anchors(workspace_root: Path | None) -> list[Path]:
    anchors: list[Path] = []
    seen: set[Path] = set()
    for base in (workspace_root, _workbench_repo_root()):
        if base is None:
            continue
        resolved = base.expanduser().resolve()
        for candidate in [resolved, *list(resolved.parents)[:4]]:
            if candidate in seen:
                continue
            seen.add(candidate)
            anchors.append(candidate)
    return anchors


def resolve_aionisdoc_package_root(
    *,
    workspace_root: str | Path | None = None,
    aionis_workspace_root: str | Path | None = None,
    aionis_package_root: str | Path | None = None,
) -> Path:
    explicit_package_root = _resolve_optional_path(aionis_package_root) or _resolve_optional_path(
        os.environ.get("AIONISDOC_PACKAGE_ROOT")
    )
    if explicit_package_root is not None:
        return explicit_package_root

    explicit_workspace_root = _resolve_optional_path(aionis_workspace_root) or _resolve_optional_path(
        os.environ.get("AIONISDOC_WORKSPACE_ROOT")
    )
    if explicit_workspace_root is not None:
        return _package_root_from_workspace_root(explicit_workspace_root)

    resolved_workspace_root = _resolve_optional_path(workspace_root)
    for anchor in _iter_repo_search_anchors(resolved_workspace_root):
        for repo_name in ("AionisCore", "AionisRuntime", "runtime-mainline"):
            candidate = anchor / repo_name / "packages" / "aionis-doc"
            if _looks_like_aionisdoc_package_root(candidate):
                return candidate

    return _package_root_from_workspace_root(_legacy_aionis_workspace_root())


def resolve_aionisdoc_fixture_source(
    fixture_name: str = "valid-workflow.aionis.md",
    *,
    workspace_root: str | Path | None = None,
    aionis_workspace_root: str | Path | None = None,
    aionis_package_root: str | Path | None = None,
) -> Path:
    return (
        resolve_aionisdoc_package_root(
            workspace_root=workspace_root,
            aionis_workspace_root=aionis_workspace_root,
            aionis_package_root=aionis_package_root,
        )
        / "fixtures"
        / fixture_name
    )


class AionisdocBridgeError(RuntimeError):
    pass


class AionisdocInvocationError(AionisdocBridgeError):
    pass


class AionisdocJsonError(AionisdocBridgeError):
    pass


class AionisdocBridge:
    _ENTRYPOINTS = {
        "compile": "cli.js",
        "run": "run-cli.js",
        "execute": "execute-cli.js",
        "runtime_handoff": "runtime-handoff-cli.js",
        "handoff_store": "handoff-store-cli.js",
        "publish": "publish-cli.js",
        "recover": "recover-cli.js",
        "resume": "resume-cli.js",
    }

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        aionis_workspace_root: str | Path | None = None,
        aionis_package_root: str | Path | None = None,
        node_executable: str = "node",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
        self._package_root = resolve_aionisdoc_package_root(
            workspace_root=self._workspace_root,
            aionis_workspace_root=aionis_workspace_root,
            aionis_package_root=aionis_package_root,
        )
        self._aionis_workspace_root = self._package_root.parents[1]
        self._node_executable = node_executable
        self._timeout_seconds = timeout_seconds

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def aionis_workspace_root(self) -> Path:
        return self._aionis_workspace_root

    @property
    def package_root(self) -> Path:
        return self._package_root

    @property
    def dist_root(self) -> Path:
        return self.package_root / "dist"

    def exists(self) -> bool:
        return self.dist_root.exists()

    def entrypoint_path(self, action: str) -> Path:
        entrypoint = self._ENTRYPOINTS.get(action)
        if entrypoint is None:
            raise AionisdocBridgeError(f"Unsupported Aionisdoc action: {action}")
        path = self.dist_root / entrypoint
        if not path.exists():
            raise AionisdocBridgeError(f"Aionisdoc entrypoint is missing: {path}")
        return path

    def build_compile_command(
        self,
        *,
        input_path: str,
        emit: str = "all",
        strict: bool = False,
        out_path: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [self._node_executable, str(self.entrypoint_path("compile")), input_path, "--emit", emit]
        if strict:
            command.append("--strict")
        if out_path:
            command.extend(["--out", out_path])
        if compact:
            command.append("--compact")
        return command

    def build_run_command(
        self,
        *,
        input_path: str,
        registry_path: str,
        input_kind: str = "source",
        out_path: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [
            self._node_executable,
            str(self.entrypoint_path("run")),
            input_path,
            "--input-kind",
            input_kind,
            "--registry",
            registry_path,
        ]
        if out_path:
            command.extend(["--out", out_path])
        if compact:
            command.append("--compact")
        return command

    def build_execute_command(
        self,
        *,
        input_path: str,
        input_kind: str = "source",
        out_path: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [
            self._node_executable,
            str(self.entrypoint_path("execute")),
            input_path,
            "--input-kind",
            input_kind,
        ]
        if out_path:
            command.extend(["--out", out_path])
        if compact:
            command.append("--compact")
        return command

    def build_runtime_handoff_command(
        self,
        *,
        input_path: str,
        input_kind: str = "source",
        scope: str | None = None,
        out_path: str | None = None,
        repo_root: str | None = None,
        file_path: str | None = None,
        symbol: str | None = None,
        current_stage: str | None = None,
        active_role: str | None = None,
        allow_compile_errors: bool = False,
        compact: bool = True,
    ) -> list[str]:
        command = [
            self._node_executable,
            str(self.entrypoint_path("runtime_handoff")),
            input_path,
            "--input-kind",
            input_kind,
        ]
        command.extend(self._optional_flag("--scope", scope))
        command.extend(self._optional_flag("--out", out_path))
        command.extend(self._optional_flag("--repo-root", repo_root))
        command.extend(self._optional_flag("--file-path", file_path))
        command.extend(self._optional_flag("--symbol", symbol))
        command.extend(self._optional_flag("--current-stage", current_stage))
        command.extend(self._optional_flag("--active-role", active_role))
        if allow_compile_errors:
            command.append("--allow-compile-errors")
        if compact:
            command.append("--compact")
        return command

    def build_handoff_store_command(
        self,
        *,
        input_path: str,
        scope: str | None = None,
        tenant_id: str | None = None,
        actor: str | None = None,
        memory_lane: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        out_path: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [self._node_executable, str(self.entrypoint_path("handoff_store")), input_path]
        command.extend(self._optional_flag("--scope", scope))
        command.extend(self._optional_flag("--tenant-id", tenant_id))
        command.extend(self._optional_flag("--actor", actor))
        command.extend(self._optional_flag("--memory-lane", memory_lane))
        command.extend(self._optional_flag("--title", title))
        command.extend(self._repeated_flag("--tag", tags or []))
        command.extend(self._optional_flag("--out", out_path))
        if compact:
            command.append("--compact")
        return command

    def build_publish_command(
        self,
        *,
        input_path: str,
        input_kind: str = "source",
        base_url: str | None = None,
        scope: str | None = None,
        tenant_id: str | None = None,
        actor: str | None = None,
        memory_lane: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        repo_root: str | None = None,
        file_path: str | None = None,
        symbol: str | None = None,
        current_stage: str | None = None,
        active_role: str | None = None,
        allow_compile_errors: bool = False,
        timeout_ms: int | None = None,
        api_key: str | None = None,
        auth_bearer: str | None = None,
        admin_token: str | None = None,
        request_id: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [
            self._node_executable,
            str(self.entrypoint_path("publish")),
            input_path,
            "--input-kind",
            input_kind,
        ]
        command.extend(self._optional_flag("--base-url", base_url))
        command.extend(self._optional_flag("--scope", scope))
        command.extend(self._optional_flag("--tenant-id", tenant_id))
        command.extend(self._optional_flag("--actor", actor))
        command.extend(self._optional_flag("--memory-lane", memory_lane))
        command.extend(self._optional_flag("--title", title))
        command.extend(self._repeated_flag("--tag", tags or []))
        command.extend(self._optional_flag("--repo-root", repo_root))
        command.extend(self._optional_flag("--file-path", file_path))
        command.extend(self._optional_flag("--symbol", symbol))
        command.extend(self._optional_flag("--current-stage", current_stage))
        command.extend(self._optional_flag("--active-role", active_role))
        if allow_compile_errors:
            command.append("--allow-compile-errors")
        command.extend(self._optional_flag("--timeout-ms", timeout_ms))
        command.extend(self._optional_flag("--api-key", api_key))
        command.extend(self._optional_flag("--auth-bearer", auth_bearer))
        command.extend(self._optional_flag("--admin-token", admin_token))
        command.extend(self._optional_flag("--request-id", request_id))
        if compact:
            command.append("--compact")
        return command

    def build_recover_command(
        self,
        *,
        input_path: str,
        input_kind: str = "source",
        base_url: str | None = None,
        scope: str | None = None,
        tenant_id: str | None = None,
        actor: str | None = None,
        memory_lane: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        repo_root: str | None = None,
        file_path: str | None = None,
        symbol: str | None = None,
        current_stage: str | None = None,
        active_role: str | None = None,
        handoff_kind: str | None = None,
        limit: int | None = None,
        allow_compile_errors: bool = False,
        timeout_ms: int | None = None,
        api_key: str | None = None,
        auth_bearer: str | None = None,
        admin_token: str | None = None,
        request_id: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [
            self._node_executable,
            str(self.entrypoint_path("recover")),
            input_path,
            "--input-kind",
            input_kind,
        ]
        command.extend(self._optional_flag("--base-url", base_url))
        command.extend(self._optional_flag("--scope", scope))
        command.extend(self._optional_flag("--tenant-id", tenant_id))
        command.extend(self._optional_flag("--actor", actor))
        command.extend(self._optional_flag("--memory-lane", memory_lane))
        command.extend(self._optional_flag("--title", title))
        command.extend(self._repeated_flag("--tag", tags or []))
        command.extend(self._optional_flag("--repo-root", repo_root))
        command.extend(self._optional_flag("--file-path", file_path))
        command.extend(self._optional_flag("--symbol", symbol))
        command.extend(self._optional_flag("--current-stage", current_stage))
        command.extend(self._optional_flag("--active-role", active_role))
        command.extend(self._optional_flag("--handoff-kind", handoff_kind))
        command.extend(self._optional_flag("--limit", limit))
        if allow_compile_errors:
            command.append("--allow-compile-errors")
        command.extend(self._optional_flag("--timeout-ms", timeout_ms))
        command.extend(self._optional_flag("--api-key", api_key))
        command.extend(self._optional_flag("--auth-bearer", auth_bearer))
        command.extend(self._optional_flag("--admin-token", admin_token))
        command.extend(self._optional_flag("--request-id", request_id))
        if compact:
            command.append("--compact")
        return command

    def build_resume_command(
        self,
        *,
        input_path: str,
        input_kind: str = "recover-result",
        base_url: str | None = None,
        scope: str | None = None,
        tenant_id: str | None = None,
        actor: str | None = None,
        memory_lane: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        repo_root: str | None = None,
        file_path: str | None = None,
        symbol: str | None = None,
        current_stage: str | None = None,
        active_role: str | None = None,
        handoff_kind: str | None = None,
        limit: int | None = None,
        allow_compile_errors: bool = False,
        timeout_ms: int | None = None,
        api_key: str | None = None,
        auth_bearer: str | None = None,
        admin_token: str | None = None,
        request_id: str | None = None,
        out_path: str | None = None,
        query_text: str | None = None,
        run_id: str | None = None,
        candidates: list[str] | None = None,
        strict: bool = True,
        include_shadow: bool = False,
        rules_limit: int | None = None,
        include_rules: bool = False,
        feedback_outcome: str | None = None,
        feedback_target: str | None = None,
        feedback_note: str | None = None,
        feedback_input_text: str | None = None,
        feedback_selected_tool: str | None = None,
        feedback_actor: str | None = None,
        compact: bool = True,
    ) -> list[str]:
        command = [
            self._node_executable,
            str(self.entrypoint_path("resume")),
            input_path,
            "--input-kind",
            input_kind,
        ]
        command.extend(self._optional_flag("--base-url", base_url))
        command.extend(self._optional_flag("--scope", scope))
        command.extend(self._optional_flag("--tenant-id", tenant_id))
        command.extend(self._optional_flag("--actor", actor))
        command.extend(self._optional_flag("--memory-lane", memory_lane))
        command.extend(self._optional_flag("--title", title))
        command.extend(self._repeated_flag("--tag", tags or []))
        command.extend(self._optional_flag("--repo-root", repo_root))
        command.extend(self._optional_flag("--file-path", file_path))
        command.extend(self._optional_flag("--symbol", symbol))
        command.extend(self._optional_flag("--current-stage", current_stage))
        command.extend(self._optional_flag("--active-role", active_role))
        command.extend(self._optional_flag("--handoff-kind", handoff_kind))
        command.extend(self._optional_flag("--limit", limit))
        if allow_compile_errors:
            command.append("--allow-compile-errors")
        command.extend(self._optional_flag("--timeout-ms", timeout_ms))
        command.extend(self._optional_flag("--api-key", api_key))
        command.extend(self._optional_flag("--auth-bearer", auth_bearer))
        command.extend(self._optional_flag("--admin-token", admin_token))
        command.extend(self._optional_flag("--request-id", request_id))
        command.extend(self._optional_flag("--out", out_path))
        command.extend(self._optional_flag("--query-text", query_text))
        command.extend(self._optional_flag("--run-id", run_id))
        command.extend(self._repeated_flag("--candidate", candidates or []))
        command.append("--strict" if strict else "--no-strict")
        if include_shadow:
            command.append("--include-shadow")
        if include_rules:
            command.append("--include-rules")
        command.extend(self._optional_flag("--rules-limit", rules_limit))
        command.extend(self._optional_flag("--feedback-outcome", feedback_outcome))
        command.extend(self._optional_flag("--feedback-target", feedback_target))
        command.extend(self._optional_flag("--feedback-note", feedback_note))
        command.extend(self._optional_flag("--feedback-input-text", feedback_input_text))
        command.extend(self._optional_flag("--feedback-selected-tool", feedback_selected_tool))
        command.extend(self._optional_flag("--feedback-actor", feedback_actor))
        if compact:
            command.append("--compact")
        return command

    def invoke_json(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> Any:
        working_directory = Path(cwd).resolve() if cwd is not None else self._workspace_root
        completed = subprocess.run(
            command,
            cwd=str(working_directory),
            env=env,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
            check=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if not stdout:
            raise AionisdocInvocationError(
                f"Aionisdoc command produced no JSON output (exit={completed.returncode}): "
                f"{' '.join(command)}; stderr={stderr or 'none'}"
            )
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AionisdocJsonError(
                f"Aionisdoc command produced invalid JSON (exit={completed.returncode}): "
                f"{' '.join(command)}; stderr={stderr or 'none'}"
            ) from exc

    def compile(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_compile_command(**kwargs))

    def run(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_run_command(**kwargs))

    def execute(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_execute_command(**kwargs))

    def build_runtime_handoff(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_runtime_handoff_command(**kwargs))

    def build_handoff_store_request(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_handoff_store_command(**kwargs))

    def publish(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_publish_command(**kwargs))

    def recover(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_recover_command(**kwargs))

    def resume(self, **kwargs: Any) -> Any:
        return self.invoke_json(self.build_resume_command(**kwargs))

    @staticmethod
    def _optional_flag(name: str, value: object | None) -> list[str]:
        if value is None:
            return []
        return [name, str(value)]

    @staticmethod
    def _repeated_flag(name: str, values: list[str]) -> list[str]:
        rendered: list[str] = []
        for value in values:
            rendered.extend([name, value])
        return rendered
