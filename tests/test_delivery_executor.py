from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from aionis_workbench.delivery_executor import DeliveryExecutor
from aionis_workbench.delivery_workspace import DeliveryWorkspaceAdapter
from aionis_workbench.execution_host import _delivery_artifact_ready
from aionis_workbench.execution_host import ModelInvokeTimeout
from aionis_workbench.execution_host import _delivery_retry_backoff_seconds
from aionis_workbench.execution_host import _reset_delivery_trace
from aionis_workbench.execution_host import _should_retry_transient_delivery_error
from aionis_workbench.execution_host import _trace_shows_successful_build
from aionis_workbench.openai_agents_execution_host import OpenAIAgentsExecutionHost
from aionis_workbench.recovery_service import ValidationResult
from aionis_workbench.session import SessionState
from aionis_workbench.tracing import (
    DeliveryComplete,
    TraceRecorder,
    create_delivery_shell_guard_middleware,
    create_tool_trace_middleware,
    sanitize_delivery_execute_command,
    should_complete_delivery_after_tool,
)


def _bootstrap_minimal_react_vite_app(root_dir: str) -> None:
    root = Path(root_dir)
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    files = {
        root / "package.json": json.dumps(
            {
                "name": "delivery-test-app",
                "private": True,
                "version": "0.0.0",
                "type": "module",
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {
                    "react": "^18.3.1",
                    "react-dom": "^18.3.1",
                },
                "devDependencies": {
                    "@types/react": "^18.3.3",
                    "@types/react-dom": "^18.3.0",
                    "@vitejs/plugin-react": "^4.3.1",
                    "typescript": "^5.6.2",
                    "vite": "^5.4.8",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        root / "tsconfig.json": json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2020",
                    "module": "ESNext",
                    "moduleResolution": "Node",
                    "jsx": "react-jsx",
                    "strict": True,
                    "noEmit": True,
                },
                "include": ["src"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        root / "vite.config.ts": (
            'import { defineConfig } from "vite";\n'
            'import react from "@vitejs/plugin-react";\n\n'
            "export default defineConfig({ plugins: [react()] });\n"
        ),
        root / "index.html": (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="UTF-8" />\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            "    <title>Delivery Test</title>\n"
            "  </head>\n"
            "  <body>\n"
            '    <div id="root"></div>\n'
            '    <script type="module" src="/src/main.tsx"></script>\n'
            "  </body>\n"
            "</html>\n"
        ),
        src / "main.tsx": (
            'import React from "react";\n'
            'import ReactDOM from "react-dom/client";\n'
            'import App from "./App";\n'
            'import "./styles.css";\n\n'
            'ReactDOM.createRoot(document.getElementById("root")!).render(\n'
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            ");\n"
        ),
        src / "App.tsx": (
            'export default function App() {\n'
            '  return <main className="app">Bootstrap shell</main>;\n'
            "}\n"
        ),
        src / "styles.css": ".app { color: #111; }\n",
    }
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")


class _FakeExecutionHost:
    def __init__(self) -> None:
        self.build_calls: list[dict[str, object]] = []
        self.root_dir: str = ""

    def build_agent(
        self,
        *,
        system_parts,
        memory_sources,
        timeout_pressure,
        root_dir=None,
        model_timeout_seconds_override=None,
        use_builtin_subagents=True,
    ):
        self.root_dir = str(root_dir or "")
        self.build_calls.append(
            {
                "system_parts": list(system_parts),
                "memory_sources": list(memory_sources),
                "timeout_pressure": timeout_pressure,
                "root_dir": self.root_dir,
                "model_timeout_seconds_override": model_timeout_seconds_override,
                "use_builtin_subagents": use_builtin_subagents,
            }
        )
        return object()

    def invoke(self, agent, payload, *, timeout_seconds=None):
        assert agent is not None
        assert payload["messages"][0]["role"] == "user"
        if self.root_dir:
            _bootstrap_minimal_react_vite_app(self.root_dir)
            app_file = Path(self.root_dir) / "src" / "App.tsx"
            app_file.write_text(
                app_file.read_text(encoding="utf-8") + "\nexport const implemented = true;\n",
                encoding="utf-8",
            )
        return "Implemented the first runnable app shell."


class _FakeDirectDeliveryHost(_FakeExecutionHost):
    def __init__(self) -> None:
        super().__init__()
        self.delivery_calls: list[dict[str, object]] = []
        self.preexisting_files: list[str] = []

    def invoke_delivery_task(
        self,
        *,
        system_parts,
        memory_sources,
        root_dir,
        task,
        timeout_seconds=None,
        trace_path="",
    ):
        self.delivery_calls.append(
            {
                "system_parts": list(system_parts),
                "memory_sources": list(memory_sources),
                "root_dir": str(root_dir),
                "task": task,
                "timeout_seconds": timeout_seconds,
                "trace_path": trace_path,
            }
        )
        self.preexisting_files = sorted(
            path.relative_to(root_dir).as_posix()
            for path in Path(root_dir).rglob("*")
            if path.is_file()
        )
        _bootstrap_minimal_react_vite_app(str(root_dir))
        app_file = Path(root_dir) / "src" / "App.tsx"
        app_file.write_text(
            app_file.read_text(encoding="utf-8") + "\nexport const implemented = true;\n",
            encoding="utf-8",
        )
        return "Implemented the first runnable app shell."


def test_delivery_executor_runs_bounded_attempt_and_collects_workspace_evidence(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeExecutionHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0],
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-executor-1",
        goal="Ship a real app shell.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        system_parts=["Do real file edits."],
        task="Implement the first app shell.",
        memory_sources=["src/App.tsx"],
        validation_commands=["npm test"],
        execution_summary="Implement the first app shell.",
        changed_target_hints=["src/App.tsx"],
    )

    assert host.build_calls[0]["memory_sources"] == ["src/App.tsx"]
    assert host.build_calls[0]["root_dir"] == str(
        tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-executor-1"
    )
    assert host.build_calls[0]["model_timeout_seconds_override"] == 900.0
    assert host.build_calls[0]["use_builtin_subagents"] is False
    assert result.execution_summary == "Implemented the first runnable app shell."
    assert result.changed_files == ["src/App.tsx"]
    assert result.artifact_kind == "workspace_app"
    assert result.artifact_paths[:3] == ["index.html", "package.json", "src/main.tsx"]
    assert result.preview_command == (
        f"cd {tmp_path / '.aionis-workbench' / 'delivery-workspaces' / 'delivery-executor-1'} "
        "&& npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173"
    )
    assert result.trace_path.endswith("/.aionis-delivery-trace.json")
    assert result.validation_command == "npm test"
    assert result.validation_ok is False
    assert "npm error" in result.validation_summary.lower() or "validation failed" in result.validation_summary.lower()


def test_delivery_executor_prefers_direct_delivery_invocation_when_available(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0],
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-direct-1",
        goal="Ship a real app shell.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        system_parts=["Do real file edits."],
        task="Implement the first app shell.",
        memory_sources=["src/App.tsx"],
        validation_commands=["npm test"],
        execution_summary="Implement the first app shell.",
        changed_target_hints=["src/App.tsx"],
    )

    assert host.delivery_calls[0]["memory_sources"] == ["src/App.tsx"]
    assert host.delivery_calls[0]["task"] == "Implement the first app shell."
    assert host.build_calls == []
    assert host.preexisting_files == [
        "index.html",
        "package.json",
        "src/App.tsx",
        "src/main.tsx",
        "src/styles.css",
        "tsconfig.json",
        "vite.config.ts",
    ]
    assert result.changed_files == ["src/App.tsx"]
    assert result.artifact_root.endswith("/delivery-direct-1")


def test_delivery_executor_bootstraps_python_api_family_when_targets_require_it(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0],
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-python-api-1",
        goal="Ship a runnable FastAPI service.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        system_parts=["Do real file edits."],
        task="Implement the first runnable FastAPI service.",
        memory_sources=["requirements.txt", "main.py"],
        validation_commands=["python3 -m py_compile main.py"],
        execution_summary="Implement the first runnable FastAPI service.",
        changed_target_hints=["main.py"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-python-api-1"
    assert host.delivery_calls[0]["memory_sources"] == ["requirements.txt", "main.py"]
    assert "main.py" in host.preexisting_files
    assert "requirements.txt" in host.preexisting_files
    assert result.artifact_kind == "python_api_workspace"
    assert result.preview_command == (
        f"cd {workspace_root} && python3 -m pip install -r requirements.txt && "
        "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
    )


def test_delivery_executor_bootstraps_node_api_family_when_targets_require_it(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0],
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-node-api-1",
        goal="Ship a runnable Express service.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="node_express_api",
        system_parts=["Do real file edits."],
        task="Implement the first runnable Express service.",
        memory_sources=["package.json", "main.js"],
        validation_commands=["node --check main.js"],
        execution_summary="Implement the first runnable Express service.",
        changed_target_hints=["main.js"],
    )

    assert host.delivery_calls[0]["memory_sources"] == ["package.json", "main.js"]
    assert "main.js" in host.preexisting_files
    assert "package.json" in host.preexisting_files
    assert result.artifact_kind == "node_api_workspace"
    assert result.preview_command.endswith("npm run dev")


def test_delivery_executor_bootstraps_task_workspace_without_live_model(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    executor = DeliveryExecutor(
        execution_host=_FakeExecutionHost(),
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-bootstrap-1",
        goal="Bootstrap the first dependency explorer workspace.",
        repo_root=str(tmp_path),
    )

    result = executor.bootstrap_app_generate(
        session=session,
        validation_commands=[],
        execution_summary="Scaffold the first dependency explorer workspace.",
        changed_target_hints=["src/App.tsx"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-bootstrap-1"
    assert workspace_root.exists()
    assert (workspace_root / "src" / "App.tsx").exists()
    assert result.artifact_root == str(workspace_root)
    assert result.artifact_kind == "workspace_app"
    assert result.preview_command == (
        f"cd {workspace_root} && npm install --no-fund --no-audit "
        "&& npm run dev -- --host 0.0.0.0 --port 4173"
    )
    assert result.validation_summary == "Task workspace scaffolded. Install dependencies before previewing the app."


def test_delivery_executor_preserves_workspace_evidence_when_agent_invocation_fails(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    class _FailingHost(_FakeExecutionHost):
        def invoke(self, agent, payload, *, timeout_seconds=None):
            raise TimeoutError("Request timed out.")

        def live_app_delivery_timeout_seconds(self) -> float:
            return 180.0

    executor = DeliveryExecutor(
        execution_host=_FailingHost(),
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-timeout-1",
        goal="Keep the workspace exportable even after a timeout.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        system_parts=["Do real file edits."],
        task="Implement the first app shell.",
        memory_sources=["src/App.tsx"],
        validation_commands=[],
        execution_summary="Implement the first app shell.",
        changed_target_hints=["src/App.tsx"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-timeout-1"
    assert result.failure_reason == "Request timed out."
    assert result.artifact_root == str(workspace_root)
    assert result.artifact_kind == "workspace_app"
    assert result.preview_command == (
        f"cd {workspace_root} && npm install --no-fund --no-audit "
        "&& npm run dev -- --host 0.0.0.0 --port 4173"
    )
    assert result.trace_path == str(workspace_root / ".aionis-delivery-trace.json")
    assert workspace_root.exists()
    assert (workspace_root / "src" / "App.tsx").exists()


def test_delivery_executor_upgrades_build_only_web_validation_to_install_and_build(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-web-validation-upgrade-1",
        goal="Ship the first web shell.",
        repo_root=str(tmp_path),
    )

    recorded: list[str] = []

    def _fake_workspace_validation(*, workspace_root: Path, commands: list[str]) -> ValidationResult:
        recorded.extend(commands)
        return ValidationResult(
            ok=True,
            command=commands[-1] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        )

    executor._run_workspace_validation_commands = _fake_workspace_validation  # type: ignore[attr-defined]

    result = executor.execute_app_generate(
        session=session,
        delivery_family="vue_vite_web",
        system_parts=["Do real file edits."],
        task="Implement the first Vue app shell.",
        memory_sources=["package.json", "vite.config.ts", "tsconfig.json", "index.html", "src/main.ts", "src/App.vue", "src/styles.css"],
        validation_commands=["npm run build"],
        execution_summary="Implement the first Vue app shell.",
        changed_target_hints=["src/App.vue", "src/styles.css"],
    )

    assert recorded == ["npm install --no-fund --no-audit", "npm run build"]
    assert result.validation_command == "npm run build"


def test_delivery_executor_validates_bootstrapped_node_api_after_timeout(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    class _FailingHost(_FakeExecutionHost):
        def invoke(self, agent, payload, *, timeout_seconds=None):
            raise TimeoutError("Request timed out.")

        def live_app_delivery_timeout_seconds(self) -> float:
            return 180.0

    executor = DeliveryExecutor(
        execution_host=_FailingHost(),
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    executor._run_workspace_validation_commands = (  # type: ignore[attr-defined]
        lambda *, workspace_root, commands: ValidationResult(
            ok=True,
            command=commands[-1] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        )
    )
    session = SessionState(
        task_id="delivery-node-timeout-1",
        goal="Keep a valid Node API artifact even after a timeout.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="node_express_api",
        system_parts=["Do real file edits."],
        task="Implement the first Node API shell.",
        memory_sources=["package.json", "main.js"],
        validation_commands=["node --check main.js"],
        execution_summary="Implement the first Node API shell.",
        changed_target_hints=["package.json", "main.js"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-node-timeout-1"
    assert result.artifact_root == str(workspace_root)
    assert result.artifact_kind == "node_api_workspace"
    assert result.preview_command == f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev"
    assert result.validation_command.startswith("node -e ")
    assert result.validation_summary == "Validation commands passed."
    assert result.validation_ok is True
    assert result.failure_reason == ""
    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "main.js").exists()


def test_delivery_executor_refreshes_web_artifact_after_timeout_validation(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    class _FailingHost(_FakeExecutionHost):
        def invoke(self, agent, payload, *, timeout_seconds=None):
            raise TimeoutError("Request timed out.")

        def live_app_delivery_timeout_seconds(self) -> float:
            return 180.0

    def _validate_and_build(commands: list[str]) -> ValidationResult:
        workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-web-timeout-1"
        dist_root = workspace_root / "dist"
        dist_root.mkdir(parents=True, exist_ok=True)
        (dist_root / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
        return ValidationResult(
            ok=True,
            command=commands[-1] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        )

    executor = DeliveryExecutor(
        execution_host=_FailingHost(),
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=_validate_and_build,
    )
    executor._run_workspace_validation_commands = (  # type: ignore[attr-defined]
        lambda *, workspace_root, commands: _validate_and_build(commands)
    )
    session = SessionState(
        task_id="delivery-web-timeout-1",
        goal="Keep a valid web artifact even after a timeout.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="svelte_vite_web",
        system_parts=["Do real file edits."],
        task="Implement the first Svelte app shell.",
        memory_sources=["package.json", "vite.config.ts", "tsconfig.json", "svelte.config.js", "index.html", "src/main.ts", "src/App.svelte", "src/app.css"],
        validation_commands=["npm run build"],
        execution_summary="Implement the first Svelte app shell.",
        changed_target_hints=["src/App.svelte", "src/app.css"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-web-timeout-1"
    assert result.artifact_root == str(workspace_root)
    assert result.artifact_kind == "vite_dist"
    assert result.artifact_paths[0] == "dist/index.html"
    assert result.preview_command == f"python3 -m http.server 4173 --directory {workspace_root / 'dist'}"
    assert result.validation_command == "npm run build"
    assert result.validation_summary == "Validation commands passed."
    assert result.validation_ok is True
    assert result.failure_reason == ""


def test_delivery_executor_bootstraps_vue_web_family_when_targets_require_it(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-vue-direct-1",
        goal="Ship the first Vue app shell.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="vue_vite_web",
        system_parts=["Do real file edits."],
        task="Implement the first Vue app shell.",
        memory_sources=["package.json", "vite.config.ts", "tsconfig.json", "index.html", "src/main.ts", "src/App.vue", "src/styles.css"],
        validation_commands=["npm run build"],
        execution_summary="Implement the first Vue app shell.",
        changed_target_hints=["src/App.vue", "src/styles.css"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-vue-direct-1"
    assert "src/App.vue" in host.preexisting_files
    assert "src/main.ts" in host.preexisting_files
    assert result.artifact_root == str(workspace_root)
    assert "package.json" in result.artifact_paths


def test_delivery_executor_bootstraps_svelte_web_family_when_targets_require_it(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-svelte-direct-1",
        goal="Ship the first Svelte app shell.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="svelte_vite_web",
        system_parts=["Do real file edits."],
        task="Implement the first Svelte app shell.",
        memory_sources=["package.json", "vite.config.ts", "tsconfig.json", "svelte.config.js", "index.html", "src/main.ts", "src/App.svelte", "src/app.css"],
        validation_commands=["npm run build"],
        execution_summary="Implement the first Svelte app shell.",
        changed_target_hints=["src/App.svelte", "src/app.css"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-svelte-direct-1"
    assert "src/App.svelte" in host.preexisting_files
    assert "src/main.ts" in host.preexisting_files
    assert result.artifact_root == str(workspace_root)
    assert "package.json" in result.artifact_paths


def test_delivery_executor_bootstraps_nextjs_web_family_when_targets_require_it(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    host = _FakeDirectDeliveryHost()
    executor = DeliveryExecutor(
        execution_host=host,
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=True,
            command=commands[0] if commands else None,
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="delivery-nextjs-direct-1",
        goal="Ship the first Next.js app shell.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="nextjs_web",
        system_parts=["Do real file edits."],
        task="Implement the first Next.js app shell.",
        memory_sources=["package.json", "next.config.mjs", "tsconfig.json", "next-env.d.ts", "app/layout.tsx", "app/page.tsx", "app/globals.css"],
        validation_commands=["npm run build"],
        execution_summary="Implement the first Next.js app shell.",
        changed_target_hints=["app/page.tsx", "app/globals.css"],
    )

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "delivery-nextjs-direct-1"
    assert "app/page.tsx" in host.preexisting_files
    assert "app/layout.tsx" in host.preexisting_files
    assert result.artifact_root == str(workspace_root)
    assert "package.json" in result.artifact_paths


def test_delivery_completion_middleware_short_circuits_after_build_when_dist_exists(tmp_path) -> None:
    workspace_root = tmp_path / "workspace"
    dist_root = workspace_root / "dist"
    dist_root.mkdir(parents=True, exist_ok=True)
    (dist_root / "index.html").write_text("<html></html>", encoding="utf-8")

    assert should_complete_delivery_after_tool(
        tool_name="execute",
        tool_input={"command": "npm run build", "timeout": 60},
        result=SimpleNamespace(status="success"),
        workspace_root=str(workspace_root),
    )


def test_delivery_artifact_ready_requires_dist_and_successful_build_trace(tmp_path) -> None:
    trace_path = tmp_path / ".aionis-delivery-trace.json"
    recorder = TraceRecorder(snapshot_path=str(trace_path))
    recorder.record(
        tool_name="execute",
        tool_call_id="call-build",
        tool_input={"command": "npm run build"},
        status="success",
        result=SimpleNamespace(status="success"),
    )

    assert not _delivery_artifact_ready(root_dir=str(tmp_path), trace_path=str(trace_path))

    dist_entry = tmp_path / "dist" / "index.html"
    dist_entry.parent.mkdir(parents=True, exist_ok=True)
    dist_entry.write_text("<!doctype html>", encoding="utf-8")

    assert _delivery_artifact_ready(root_dir=str(tmp_path), trace_path=str(trace_path))


def test_reset_delivery_trace_clears_previous_snapshot(tmp_path) -> None:
    trace_path = tmp_path / ".aionis-delivery-trace.json"
    trace_path.write_text(
        '{"step_count": 3, "steps": [{"tool_name": "execute"}], "failure_reason": "old failure"}\n',
        encoding="utf-8",
    )

    _reset_delivery_trace(str(trace_path))

    payload = trace_path.read_text(encoding="utf-8")
    assert '"step_count": 0' in payload
    assert '"steps": []' in payload
    assert "old failure" not in payload


def test_append_trace_failure_writes_parseable_snapshot(tmp_path) -> None:
    trace_path = tmp_path / ".aionis-delivery-trace.json"
    recorder = TraceRecorder(snapshot_path=str(trace_path))
    recorder.record(
        tool_name="execute",
        tool_call_id="call-build-1",
        tool_input={"command": "npm run build"},
        status="success",
        result=SimpleNamespace(status="success"),
    )

    from aionis_workbench.execution_host import _append_trace_failure

    _append_trace_failure(str(trace_path), failure_reason="provider overloaded")

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["step_count"] == 1
    assert payload["failure_reason"] == "provider overloaded"
    assert payload["steps"][0]["tool_name"] == "execute"


def test_trace_shows_successful_build_uses_latest_build_result(tmp_path) -> None:
    trace_path = tmp_path / ".aionis-delivery-trace.json"
    recorder = TraceRecorder(snapshot_path=str(trace_path))
    recorder.record(
        tool_name="execute",
        tool_call_id="call-build-1",
        tool_input={"command": "npm run build"},
        status="success",
        result=SimpleNamespace(status="success"),
    )
    recorder.record(
        tool_name="execute",
        tool_call_id="call-build-2",
        tool_input={"command": "npm install && npm run build"},
        status="error",
        result=SimpleNamespace(status="error"),
        error="build failed",
    )

    assert not _trace_shows_successful_build(str(trace_path))


def test_tool_trace_records_delivery_complete_as_success() -> None:
    recorder = TraceRecorder()
    middleware = create_tool_trace_middleware(recorder)
    request = SimpleNamespace(
        tool_call={
            "name": "execute",
            "id": "call-build",
            "args": {"command": "npm install && npm run build"},
        }
    )

    try:
        if callable(middleware):
            middleware(
                request,
                lambda _request: (_ for _ in ()).throw(DeliveryComplete("Build completed and delivery artifact is ready.")),
            )
        else:
            middleware.wrap_tool_call(
                request,
                lambda _request: (_ for _ in ()).throw(DeliveryComplete("Build completed and delivery artifact is ready.")),
            )
    except DeliveryComplete:
        pass
    else:
        raise AssertionError("expected DeliveryComplete to be re-raised")

    steps = recorder.export()
    assert len(steps) == 1
    assert steps[0].tool_name == "execute"
    assert steps[0].status == "success"
    assert steps[0].error is None


def test_tool_trace_middleware_exposes_langchain_tool_hook() -> None:
    recorder = TraceRecorder()
    middleware = create_tool_trace_middleware(recorder)

    assert hasattr(middleware, "wrap_tool_call")
    assert hasattr(middleware, "awrap_tool_call")
    assert hasattr(middleware, "before_agent")
    assert hasattr(middleware, "abefore_agent")
    assert callable(getattr(middleware, "wrap_tool_call"))


def test_sanitize_delivery_execute_command_strips_root_reset_prefix() -> None:
    assert sanitize_delivery_execute_command("cd / && npm run build") == "npm run build"
    assert sanitize_delivery_execute_command("cd /; npm install --no-fund --no-audit") == "npm install --no-fund --no-audit"
    assert sanitize_delivery_execute_command("cd /src && npm install --no-fund --no-audit") == "npm install --no-fund --no-audit"
    assert sanitize_delivery_execute_command("cd /app; npm run dev") == "npm run dev"
    assert sanitize_delivery_execute_command("npm run build") == "npm run build"


def test_delivery_shell_guard_rewrites_execute_command_before_tool_execution() -> None:
    middleware = create_delivery_shell_guard_middleware()
    request = SimpleNamespace(
        tool_call={
            "name": "execute",
            "id": "call-build",
            "args": {"command": "cd /src && npm run build"},
        }
    )

    captured_commands: list[str] = []

    def _handler(patched_request):
        captured_commands.append(patched_request.tool_call["args"]["command"])
        return SimpleNamespace(status="success")

    if callable(middleware):
        middleware(request, _handler)
    else:
        middleware.wrap_tool_call(request, _handler)

    assert captured_commands == ["npm run build"]


def test_should_retry_transient_delivery_error_for_overload_and_connection_signals() -> None:
    assert _should_retry_transient_delivery_error(
        error_type="RuntimeError",
        error_message="Error code: 429 - {'error': {'code': '1305', 'message': 'The service may be temporarily overloaded, please try again later'}}",
    )
    assert _should_retry_transient_delivery_error(
        error_type="RuntimeError",
        error_message="Connection error.",
    )
    assert not _should_retry_transient_delivery_error(
        error_type="ModelInvokeTimeout",
        error_message="Error code: 429 - temporarily overloaded",
    )
    assert not _should_retry_transient_delivery_error(
        error_type="RuntimeError",
        error_message="Build failed with TypeScript errors.",
    )
    assert _delivery_retry_backoff_seconds(1) == 2.0
    assert _delivery_retry_backoff_seconds(2) == 4.0


def test_invoke_delivery_task_retries_once_after_transient_429(tmp_path, monkeypatch) -> None:
    class _FakeQueue:
        def __init__(self) -> None:
            self.payload = None
            self._used = False

        def get_nowait(self):
            if self._used or self.payload is None:
                raise __import__("queue").Empty
            self._used = True
            return self.payload

    class _FakeProcess:
        def __init__(self, payload, result_queue) -> None:
            self._payload = payload
            self._queue = result_queue
            self.exitcode = 0
            self._alive = False

        def start(self):
            self._queue.payload = self._payload
            self._alive = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False

    class _FakeContext:
        def __init__(self, payloads) -> None:
            self._payloads = list(payloads)

        def Queue(self):
            return _FakeQueue()

        def Process(self, target, args):
            result_queue = args[-1]
            payload = self._payloads.pop(0)
            return _FakeProcess(payload, result_queue)

    payloads = [
        {
            "ok": False,
            "error_type": "RuntimeError",
            "error": "Error code: 429 - {'error': {'code': '1305', 'message': 'The service may be temporarily overloaded, please try again later'}}",
            "trace_path": str(tmp_path / ".aionis-delivery-trace.json"),
        },
        {
            "ok": True,
            "result": "Build completed and delivery artifact is ready.",
            "trace_path": str(tmp_path / ".aionis-delivery-trace.json"),
        },
    ]
    fake_context = _FakeContext(payloads)
    sleep_calls: list[float] = []

    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.multiprocessing.get_context", lambda _mode: fake_context)
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.sleep", lambda seconds: sleep_calls.append(seconds))

    from aionis_workbench.config import WorkbenchConfig

    host = OpenAIAgentsExecutionHost(
        config=WorkbenchConfig(
            execution_host_runtime="openai_agents",
            model="glm-5.1",
            system_prompt=None,
            provider="openai",
            api_key="test-key",
            base_url="https://example.invalid",
            max_completion_tokens=8192,
            model_timeout_seconds=45.0,
            model_max_retries=1,
            repo_root=str(tmp_path),
            project_identity="local/test",
            project_scope="project:local/test",
            auto_consolidation_enabled=False,
            auto_consolidation_min_hours=24.0,
            auto_consolidation_min_new_sessions=5,
            auto_consolidation_scan_throttle_minutes=10.0,
        ),
        trace=TraceRecorder(),
    )

    result = host.invoke_delivery_task(
        system_parts=["Do real file edits."],
        memory_sources=["src/App.tsx"],
        root_dir=str(tmp_path),
        task="Build the page.",
        timeout_seconds=30.0,
        trace_path=str(tmp_path / ".aionis-delivery-trace.json"),
    )

    assert result == "Build completed and delivery artifact is ready."
    assert sleep_calls == [2.0]


def test_invoke_delivery_task_caps_per_model_timeout_separately_from_delivery_timeout(tmp_path, monkeypatch) -> None:
    captured_args: list[tuple] = []

    class _FakeQueue:
        def __init__(self) -> None:
            self.payload = None
            self._used = False

        def get_nowait(self):
            if self._used or self.payload is None:
                raise __import__("queue").Empty
            self._used = True
            return self.payload

    class _FakeProcess:
        def __init__(self, payload, result_queue) -> None:
            self._payload = payload
            self._queue = result_queue
            self.exitcode = 0
            self._alive = False

        def start(self):
            self._queue.payload = self._payload
            self._alive = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False

    class _FakeContext:
        def Queue(self):
            return _FakeQueue()

        def Process(self, target, args):
            captured_args.append(args)
            result_queue = args[-1]
            payload = {
                "ok": True,
                "result": "Build completed and delivery artifact is ready.",
                "trace_path": str(tmp_path / ".aionis-delivery-trace.json"),
            }
            return _FakeProcess(payload, result_queue)

    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.multiprocessing.get_context", lambda _mode: _FakeContext())

    from aionis_workbench.config import WorkbenchConfig

    host = OpenAIAgentsExecutionHost(
        config=WorkbenchConfig(
            execution_host_runtime="openai_agents",
            model="glm-5.1",
            system_prompt=None,
            provider="openai",
            api_key="test-key",
            base_url="https://example.invalid",
            max_completion_tokens=8192,
            model_timeout_seconds=420.0,
            model_max_retries=1,
            repo_root=str(tmp_path),
            project_identity="local/test",
            project_scope="project:local/test",
            auto_consolidation_enabled=False,
            auto_consolidation_min_hours=24.0,
            auto_consolidation_min_new_sessions=5,
            auto_consolidation_scan_throttle_minutes=10.0,
        ),
        trace=TraceRecorder(),
    )

    result = host.invoke_delivery_task(
        system_parts=["Do real file edits."],
        memory_sources=["src/App.tsx"],
        root_dir=str(tmp_path),
        task="Build the page.",
        timeout_seconds=900.0,
        trace_path=str(tmp_path / ".aionis-delivery-trace.json"),
    )

    assert result == "Build completed and delivery artifact is ready."
    assert len(captured_args) == 1
    assert captured_args[0][5] == 900.0
    assert captured_args[0][6] == 90.0


def test_invoke_delivery_task_reports_retry_exhaustion_for_transient_overload(tmp_path, monkeypatch) -> None:
    class _FakeQueue:
        def __init__(self) -> None:
            self.payload = None
            self._used = False

        def get_nowait(self):
            if self._used or self.payload is None:
                raise __import__("queue").Empty
            self._used = True
            return self.payload

    class _FakeProcess:
        def __init__(self, payload, result_queue) -> None:
            self._payload = payload
            self._queue = result_queue
            self.exitcode = 0
            self._alive = False

        def start(self):
            self._queue.payload = self._payload
            self._alive = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False

    class _FakeContext:
        def __init__(self, payloads) -> None:
            self._payloads = list(payloads)

        def Queue(self):
            return _FakeQueue()

        def Process(self, target, args):
            result_queue = args[-1]
            payload = self._payloads.pop(0)
            return _FakeProcess(payload, result_queue)

    error = "Error code: 429 - {'error': {'code': '1305', 'message': 'The service may be temporarily overloaded, please try again later'}}"
    payloads = [
        {"ok": False, "error_type": "RuntimeError", "error": error, "trace_path": str(tmp_path / ".aionis-delivery-trace.json")},
        {"ok": False, "error_type": "RuntimeError", "error": error, "trace_path": str(tmp_path / ".aionis-delivery-trace.json")},
        {"ok": False, "error_type": "RuntimeError", "error": error, "trace_path": str(tmp_path / ".aionis-delivery-trace.json")},
    ]
    fake_context = _FakeContext(payloads)
    sleep_calls: list[float] = []

    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.multiprocessing.get_context", lambda _mode: fake_context)
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.sleep", lambda seconds: sleep_calls.append(seconds))

    from aionis_workbench.config import WorkbenchConfig

    host = OpenAIAgentsExecutionHost(
        config=WorkbenchConfig(
            execution_host_runtime="openai_agents",
            model="glm-5.1",
            system_prompt=None,
            provider="openai",
            api_key="test-key",
            base_url="https://example.invalid",
            max_completion_tokens=8192,
            model_timeout_seconds=45.0,
            model_max_retries=1,
            repo_root=str(tmp_path),
            project_identity="local/test",
            project_scope="project:local/test",
            auto_consolidation_enabled=False,
            auto_consolidation_min_hours=24.0,
            auto_consolidation_min_new_sessions=5,
            auto_consolidation_scan_throttle_minutes=10.0,
        ),
        trace=TraceRecorder(),
    )

    try:
        host.invoke_delivery_task(
            system_parts=["Do real file edits."],
            memory_sources=["src/App.tsx"],
            root_dir=str(tmp_path),
            task="Build the page.",
            timeout_seconds=30.0,
            trace_path=str(tmp_path / ".aionis-delivery-trace.json"),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError after retry exhaustion")

    assert "Delivery failed after 3/3 transient attempts." in message
    assert sleep_calls == [2.0, 4.0]
    payload = json.loads((tmp_path / ".aionis-delivery-trace.json").read_text(encoding="utf-8"))
    assert payload["delivery_attempts"] == 3
    assert payload["delivery_max_attempts"] == 3
    assert len(payload["delivery_retry_events"]) == 3


def test_invoke_delivery_task_retries_and_fails_fast_when_no_first_trace_step_arrives(tmp_path, monkeypatch) -> None:
    class _FakeQueue:
        def get_nowait(self):
            raise __import__("queue").Empty

    class _FakeProcess:
        def __init__(self) -> None:
            self.exitcode = None
            self._alive = True

        def start(self):
            self._alive = True

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False
            self.exitcode = -15

    class _FakeContext:
        def Queue(self):
            return _FakeQueue()

        def Process(self, target, args):
            return _FakeProcess()

    fake_context = _FakeContext()
    sleep_calls: list[float] = []

    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.multiprocessing.get_context", lambda _mode: fake_context)
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._delivery_first_response_timeout_seconds",
        lambda **_kwargs: 1.0,
    )

    monotonic_values = iter(
        [
            0.0, 0.0, 1.1, 1.1,  # attempt 1
            2.0, 2.0, 3.1, 3.1,  # attempt 2
            4.0, 4.0, 5.1, 5.1,  # attempt 3
        ]
    )
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.monotonic", lambda: next(monotonic_values, 999.0))

    from aionis_workbench.config import WorkbenchConfig

    host = OpenAIAgentsExecutionHost(
        config=WorkbenchConfig(
            execution_host_runtime="openai_agents",
            model="glm-5.1",
            system_prompt=None,
            provider="openai",
            api_key="test-key",
            base_url="https://example.invalid",
            max_completion_tokens=8192,
            model_timeout_seconds=45.0,
            model_max_retries=1,
            repo_root=str(tmp_path),
            project_identity="local/test",
            project_scope="project:local/test",
            auto_consolidation_enabled=False,
            auto_consolidation_min_hours=24.0,
            auto_consolidation_min_new_sessions=5,
            auto_consolidation_scan_throttle_minutes=10.0,
        ),
        trace=TraceRecorder(),
    )

    try:
        host.invoke_delivery_task(
            system_parts=["Do real file edits."],
            memory_sources=["src/App.tsx"],
            root_dir=str(tmp_path),
            task="Build the page.",
            timeout_seconds=30.0,
            trace_path=str(tmp_path / ".aionis-delivery-trace.json"),
        )
    except ModelInvokeTimeout as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ModelInvokeTimeout after repeated first-response timeouts")

    assert "Delivery failed after 3/3 first-response timeouts." in message
    assert "provider_first_turn_stall:" in message
    assert sleep_calls == [2.0, 4.0]
    payload = json.loads((tmp_path / ".aionis-delivery-trace.json").read_text(encoding="utf-8"))
    assert payload["delivery_attempts"] == 3
    assert payload["delivery_max_attempts"] == 3
    assert payload["delivery_retry_events"][-1]["error_type"] == "ProviderFirstTurnStall"


def test_invoke_delivery_task_retries_and_fails_fast_when_trace_progress_stalls(tmp_path, monkeypatch) -> None:
    class _FakeQueue:
        def get_nowait(self):
            raise __import__("queue").Empty

    class _FakeProcess:
        def __init__(self) -> None:
            self.exitcode = None
            self._alive = True

        def start(self):
            self._alive = True

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False
            self.exitcode = -15

    class _FakeContext:
        def Queue(self):
            return _FakeQueue()

        def Process(self, target, args):
            return _FakeProcess()

    fake_context = _FakeContext()
    sleep_calls: list[float] = []

    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.multiprocessing.get_context", lambda _mode: fake_context)
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._delivery_progress_timeout_seconds",
        lambda **_kwargs: 1.0,
    )
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host._trace_has_steps", lambda _trace_path: True)
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host._trace_step_count", lambda _trace_path: 5)

    monotonic_values = iter(
        [
            0.0, 0.0, 0.2, 0.2, 1.3,  # attempt 1
            2.0, 2.0, 2.2, 2.2, 3.3,  # attempt 2
            4.0, 4.0, 4.2, 4.2, 5.3,  # attempt 3
        ]
    )
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.monotonic", lambda: next(monotonic_values, 999.0))

    from aionis_workbench.config import WorkbenchConfig

    host = OpenAIAgentsExecutionHost(
        config=WorkbenchConfig(
            execution_host_runtime="openai_agents",
            model="glm-5.1",
            system_prompt=None,
            provider="openai",
            api_key="test-key",
            base_url="https://example.invalid",
            max_completion_tokens=8192,
            model_timeout_seconds=45.0,
            model_max_retries=1,
            repo_root=str(tmp_path),
            project_identity="local/test",
            project_scope="project:local/test",
            auto_consolidation_enabled=False,
            auto_consolidation_min_hours=24.0,
            auto_consolidation_min_new_sessions=5,
            auto_consolidation_scan_throttle_minutes=10.0,
        ),
        trace=TraceRecorder(),
    )

    try:
        host.invoke_delivery_task(
            system_parts=["Do real file edits."],
            memory_sources=["src/App.tsx"],
            root_dir=str(tmp_path),
            task="Build the dashboard.",
            timeout_seconds=30.0,
            trace_path=str(tmp_path / ".aionis-delivery-trace.json"),
        )
    except ModelInvokeTimeout as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ModelInvokeTimeout after repeated trace-progress timeouts")

    assert "Delivery failed after 3/3 trace-progress timeouts." in message
    assert sleep_calls == [2.0, 4.0]
    payload = json.loads((tmp_path / ".aionis-delivery-trace.json").read_text(encoding="utf-8"))
    assert payload["delivery_attempts"] == 3
    assert payload["delivery_max_attempts"] == 3
    assert payload["delivery_retry_events"][-1]["error_type"] == "TraceProgressTimeout"


def test_recover_app_generate_does_not_promote_stale_dist_without_successful_build(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    workspace_root = workspace.ensure_react_app_workspace(
        task_id="recover-stale-dist-1",
        title="Recover Stale Dist",
    )
    (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
    (workspace_root / "dist" / "index.html").write_text(
        "<!doctype html><html><body>stale build</body></html>",
        encoding="utf-8",
    )
    (workspace_root / ".aionis-delivery-trace.json").write_text(
        json.dumps(
            {
                "step_count": 1,
                "steps": [
                    {
                        "step_index": 1,
                        "tool_name": "workbench.model",
                        "tool_input": {"model": "z-ai/glm-5.1"},
                        "status": "error",
                        "output_signature": {"result_type": "NoneType", "chars": 0},
                        "error": "Connection error.",
                    }
                ],
                "failure_reason": "Connection error.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    executor = DeliveryExecutor(
        execution_host=_FakeExecutionHost(),
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=lambda commands: ValidationResult(
            ok=False,
            command=commands[-1] if commands else "",
            exit_code=1,
            summary="Validation failed: react app surface too sparse",
            output="",
            changed_files=[],
        ),
    )
    session = SessionState(
        task_id="recover-stale-dist-1",
        goal="Recover after a failed delivery attempt.",
        repo_root=str(tmp_path),
    )

    result = executor.recover_app_generate(
        session=session,
        validation_commands=["npm run build"],
        execution_summary="Recover a bounded attempt.",
        changed_target_hints=["src/App.tsx"],
    )

    assert result is not None
    assert result.artifact_kind == "workspace_app"
    assert "dist/index.html" not in result.artifact_paths


def test_execute_app_generate_does_not_promote_stale_dist_after_provider_transient_error(tmp_path) -> None:
    workspace = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    workspace_root = workspace.ensure_react_app_workspace(
        task_id="provider-transient-stale-dist-1",
        title="Provider Transient Stale Dist",
    )
    (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
    (workspace_root / "dist" / "index.html").write_text(
        "<!doctype html><html><body>stale build</body></html>",
        encoding="utf-8",
    )

    class _TransientFailingHost(_FakeExecutionHost):
        def invoke_delivery_task(self, **kwargs):
            trace_path = Path(str(kwargs.get("trace_path") or ""))
            if trace_path:
                trace_path.write_text(
                    json.dumps(
                        {
                            "step_count": 1,
                            "steps": [
                                {
                                    "step_index": 1,
                                    "tool_name": "workbench.model",
                                    "tool_input": {"model": "z-ai/glm-5.1"},
                                    "status": "error",
                                    "output_signature": {"result_type": "NoneType", "chars": 0},
                                    "error": "Connection error.",
                                }
                            ],
                            "failure_reason": "Delivery failed after 3/3 transient attempts. Last error: Connection error.",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            raise RuntimeError("Delivery failed after 3/3 transient attempts. Last error: Connection error.")

    validation_called = {"called": False}

    def _unexpected_validation(commands: list[str]) -> ValidationResult:
        validation_called["called"] = True
        return ValidationResult(
            ok=True,
            command=commands[-1] if commands else "",
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        )

    executor = DeliveryExecutor(
        execution_host=_TransientFailingHost(),
        trace=TraceRecorder(),
        workspace=workspace,
        run_validation_commands_fn=_unexpected_validation,
    )
    session = SessionState(
        task_id="provider-transient-stale-dist-1",
        goal="Handle provider transient errors without promoting stale dist.",
        repo_root=str(tmp_path),
    )

    result = executor.execute_app_generate(
        session=session,
        delivery_family="react_vite_web",
        system_parts=["Do real file edits."],
        task="Build the page.",
        memory_sources=["package.json", "index.html", "src/App.tsx", "src/styles.css"],
        validation_commands=["npm run build"],
        execution_summary="Build the page.",
        changed_target_hints=["src/App.tsx"],
    )

    assert validation_called["called"] is False
    assert result.artifact_kind == "workspace_app"
    assert "dist/index.html" not in result.artifact_paths
