from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from test_bootstrap import _seed_python_repo

from aionis_workbench.config import load_workbench_config
from aionis_workbench.app_harness_models import (
    AppHarnessState,
    EvaluatorCriterion,
    ProductSpec,
    SprintContract,
    SprintExecutionAttempt,
    SprintEvaluation,
    SprintNegotiationRound,
)
from aionis_workbench.app_artifact_export import export_latest_app_artifact
from aionis_workbench.app_harness_service import AppHarnessService
from aionis_workbench.delivery_families import (
    REACT_VITE_WEB,
    delivery_family_targets,
    delivery_family_validation_commands,
)
from aionis_workbench.delivery_results import DeliveryExecutionResult
from aionis_workbench.execution_packet import (
    ExecutionPacket,
    ExecutionPacketSummary,
    InstrumentationSummary,
    RoutingSignalSummary,
    StrategySummary,
)
from aionis_workbench.live_profile import save_live_profile_snapshot
from aionis_workbench.reviewer_contracts import ReviewPackSummary, ResumeAnchor, ReviewerContract
from aionis_workbench.orchestrator import OrchestrationResult
from aionis_workbench.recovery_service import ValidationResult
from aionis_workbench.runtime import AionisWorkbench, WorkbenchRunResult, _build_app_delivery_contract
from aionis_workbench.session import DelegationReturn, SessionState, auto_learning_path, load_session, save_session


def _prepare_workbench(tmp_path: Path, monkeypatch, *, label: str) -> AionisWorkbench:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/{label}-{str(tmp_path).replace('/', '_')}")
    return AionisWorkbench(repo_root=str(tmp_path))


def _prepare_openai_agents_workbench(tmp_path: Path, monkeypatch, *, label: str) -> AionisWorkbench:
    monkeypatch.setenv("WORKBENCH_EXECUTION_HOST", "openai_agents")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("WORKBENCH_MODEL", "gpt-5")
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    workbench = _prepare_workbench(tmp_path, monkeypatch, label=label)
    assert workbench._execution_host.describe()["execution_runtime"] == "openai_agents"
    assert workbench._execution_host.supports_live_tasks() is True
    return workbench


def _stub_openai_agents_json_runtime(monkeypatch, workbench: AionisWorkbench, *, responses, captures: list[dict[str, str]] | None = None) -> None:
    host = workbench._execution_host

    class _FakeAgent:
        def __init__(self, *, name, instructions, model, tools=None) -> None:
            self.name = name
            self.instructions = instructions
            self.model = model
            self.tools = tools or []

    class _FakeRunner:
        @staticmethod
        def run_sync(agent, user_input):
            if captures is not None:
                captures.append(
                    {
                        "name": str(agent.name),
                        "instructions": str(agent.instructions),
                        "user_input": str(user_input),
                    }
                )
            payload_or_factory = responses[str(agent.name)]
            payload = payload_or_factory(agent, user_input) if callable(payload_or_factory) else payload_or_factory
            return SimpleNamespace(final_output=json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(host, "_configure_openai_agents_client", lambda: None)
    monkeypatch.setattr(
        host,
        "_import_agents_runtime",
        lambda: (_FakeAgent, _FakeRunner, lambda fn: fn, lambda *args, **kwargs: None, lambda *args, **kwargs: None),
    )


def test_product_runtime_does_not_load_repo_env_by_default(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=present",
                "OPENAI_BASE_URL=https://api.z.ai/api/coding/paas/v4",
                "WORKBENCH_MODEL=glm-5.1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/env-{str(tmp_path).replace('/', '_')}")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("WORKBENCH_MODEL", raising=False)

    workbench = AionisWorkbench(repo_root=str(tmp_path))

    assert workbench._config.provider == "offline"
    assert workbench._config.api_key is None
    assert os.environ.get("OPENAI_API_KEY") is None


def test_product_runtime_loads_repo_env_for_live_provider_when_explicitly_enabled(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=present",
                "OPENAI_BASE_URL=https://api.z.ai/api/coding/paas/v4",
                "WORKBENCH_MODEL=glm-5.1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/env-enabled-{str(tmp_path).replace('/', '_')}")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("WORKBENCH_MODEL", raising=False)

    try:
        workbench = AionisWorkbench(repo_root=str(tmp_path), load_env=True)

        assert workbench._config.provider == "openai"
        assert workbench._config.api_key == "present"
        assert workbench._config.base_url == "https://api.z.ai/api/coding/paas/v4"
        assert workbench._config.model == "glm-5.1"
    finally:
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("WORKBENCH_MODEL", None)


def test_product_runtime_resolves_repo_root_from_cwd(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    (tmp_path / ".aionis-workbench").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WORKBENCH_REPO_ROOT", raising=False)

    config = load_workbench_config()

    assert config.repo_root == str(tmp_path.resolve())


def test_product_runtime_app_plan_initializes_missing_session(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-plan-init")
    expected_targets = delivery_family_targets(REACT_VITE_WEB.family_id, {})
    expected_validation_commands = delivery_family_validation_commands(REACT_VITE_WEB.family_id)

    payload = workbench.app_plan(
        task_id="product-app-plan-init-1",
        prompt="Build a polished landing page for a workflow platform.",
    )

    session = load_session(str(tmp_path), "product-app-plan-init-1", project_scope=workbench._config.project_scope)
    assert session is not None
    assert session.status == "ingested"
    assert session.target_files == expected_targets
    assert session.validation_commands == expected_validation_commands
    assert session.delegation_packets == []
    assert session.artifacts == []
    assert session.shared_memory == [
        f"Project identity: {session.project_identity}",
        f"Project scope: {session.project_scope}",
        f"Session working set: {', '.join(expected_targets)}",
        f"Session validation path: {'; '.join(expected_validation_commands)}",
    ]
    assert payload["task_id"] == "product-app-plan-init-1"
    assert payload["shell_view"] == "app_plan"


def test_product_runtime_app_plan_resets_existing_session_to_clean_delivery_context(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-plan-reset")
    expected_targets = delivery_family_targets(REACT_VITE_WEB.family_id, {})
    expected_validation_commands = delivery_family_validation_commands(REACT_VITE_WEB.family_id)
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-plan-reset-1"
    workspace_root.mkdir(parents=True, exist_ok=True)
    stale_file = workspace_root / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    session = workbench._initial_session(
        task_id="product-app-plan-reset-1",
        task="Old task context.",
        target_files=["README.md"],
        validation_commands=["git status --short"],
        apply_strategy=False,
    )
    session.shared_memory = [
        "Project identity: stale/tests",
        "Recent working sets: README.md, flows/e2e-workflow.aionis.md",
        "Prior artifact reference: .aionis-workbench/artifacts/e2e-doc-test/investigator.json",
    ]
    session.selected_strategy_profile = "broad_discovery"
    session.selected_validation_style = "targeted_then_expand"
    session.selected_trust_signal = "broader_similarity"
    session.selected_task_family = "task:styles-main-app"
    session.selected_family_scope = "exact_task_signature"
    session.selected_family_candidate_count = 3
    session.app_harness_state = AppHarnessState(
        product_spec=ProductSpec(
            prompt="Old task context.",
            title="Old App",
            app_type="web_app",
            stack=["React"],
            features=["Old feature"],
            sprint_ids=["sprint-1"],
        ),
        active_sprint_contract=SprintContract(
            sprint_id="sprint-1",
            goal="Old sprint goal.",
            scope=["README.md"],
            proposed_by="planner",
            approved=False,
        ),
        latest_execution_attempt=SprintExecutionAttempt(
            attempt_id="sprint-1-attempt-1",
            sprint_id="sprint-1",
            execution_summary="Do not approve follow-up work until sprint-1 proves the old path.",
            changed_target_hints=["README.md"],
            status="recorded",
        ),
        loop_status="execution_recorded",
    )
    session.delegation_packets = [session.delegation_packets[0]] if session.delegation_packets else []
    session.artifacts = [
        session.artifacts[0]
    ] if session.artifacts else []
    session.continuity_snapshot["recent_working_sets"] = ["README.md", "flows/e2e-workflow.aionis.md"]
    workbench._save_session(session)

    workbench.app_plan(
        task_id="product-app-plan-reset-1",
        prompt="Build a modern landing page for an AI agent platform.",
    )

    reset = load_session(str(tmp_path), "product-app-plan-reset-1", project_scope=workbench._config.project_scope)
    assert reset is not None
    assert reset.target_files == expected_targets
    assert reset.validation_commands == expected_validation_commands
    assert reset.delegation_packets == []
    assert reset.artifacts == []
    assert reset.selected_strategy_profile == "delivery_first"
    assert reset.selected_validation_style == "artifact_first"
    assert reset.selected_trust_signal == "direct_app_session"
    assert reset.selected_task_family == "task:web-app-delivery"
    assert reset.selected_family_scope == "direct_task"
    assert reset.selected_family_candidate_count == 0
    assert reset.app_harness_state is not None
    assert reset.app_harness_state.latest_execution_attempt is None
    assert reset.app_harness_state.loop_status == "sprint_proposed"
    assert not stale_file.exists()
    assert reset.shared_memory == [
        f"Project identity: {reset.project_identity}",
        f"Project scope: {reset.project_scope}",
        f"Session working set: {', '.join(expected_targets)}",
        f"Session validation path: {'; '.join(expected_validation_commands)}",
    ]
    assert reset.continuity_snapshot.get("recent_working_sets") is None


def test_product_runtime_app_ship_runs_single_entry_flow(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-ship-1"

    def _fake_execute_app_generate(**kwargs):
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "package.json").write_text('{"name":"product-app-ship"}', encoding="utf-8")
        (workspace_root / "index.html").write_text("<!doctype html><html><body><div id='root'></div></body></html>", encoding="utf-8")
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text("export function App(){return <main>ship</main>}", encoding="utf-8")
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text("<!doctype html><html><body>built</body></html>", encoding="utf-8")
        return DeliveryExecutionResult(
            execution_summary="Implemented the first runnable landing page.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["package.json", "index.html", "src/App.tsx"],
            artifact_root=str(workspace_root),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_ship(
        task_id="product-app-ship-1",
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "visible-export"),
        use_live_generator=True,
    )

    session = load_session(str(tmp_path), "product-app-ship-1", project_scope=workbench._config.project_scope)
    assert session is not None
    assert payload["shell_view"] == "app_ship"
    assert payload["status"] == "completed"
    assert payload["phase"] == "complete"
    assert payload["active_sprint_id"] == "sprint-2"
    assert payload["export_root"] == str(tmp_path / "visible-export")
    assert payload["entrypoint"] == str(tmp_path / "visible-export" / "dist" / "index.html")
    assert payload["validation_summary"] == "Validation commands passed."
    assert payload["route_summary"] == "task_intake->context_scan->plan->sprint->generate->qa->export->advance"
    assert payload["controller_action_bar"] == {
        "task_id": "product-app-ship-1",
        "status": "active",
        "recommended_command": "/next product-app-ship-1",
        "allowed_commands": [
            "/next product-app-ship-1",
            "/show product-app-ship-1",
            "/session product-app-ship-1",
        ],
    }
    assert [item["phase"] for item in payload["phase_history"]] == [
        "context_scan",
        "plan",
        "sprint",
        "generate",
        "qa",
        "export",
        "advance",
    ]
    assert session.app_harness_state is not None
    assert session.app_harness_state.active_sprint_contract is not None
    assert session.app_harness_state.active_sprint_contract.sprint_id == "sprint-2"
    assert session.app_harness_state.active_sprint_contract.approved is False
    assert (tmp_path / "visible-export" / "dist" / "index.html").exists()


def test_product_runtime_ship_routes_delivery_tasks_to_app_ship(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-ship-app-route")

    def _fake_app_ship(
        *,
        task_id: str,
        prompt: str,
        output_dir: str = "",
        use_live_planner: bool = False,
        use_live_generator: bool = False,
    ) -> dict[str, object]:
        assert task_id == "product-ship-app-route-1"
        assert prompt == "Build a modern landing page for an AI agent platform."
        assert output_dir == str(tmp_path / "visible-export")
        assert use_live_planner is True
        assert use_live_generator is True
        return {
            "shell_view": "app_ship",
            "task_id": task_id,
            "status": "completed",
            "phase": "complete",
            "route_summary": "task_intake->context_scan->plan->sprint->generate->qa->export->advance",
            "context_summary": "repo=/tmp/repo | top=README.md, src/",
            "active_sprint_id": "sprint-1",
            "entrypoint": str(tmp_path / "visible-export" / "dist" / "index.html"),
            "preview_command": "npm run dev",
            "validation_summary": "Validation commands passed.",
        }

    monkeypatch.setattr(workbench, "app_ship", _fake_app_ship)

    payload = workbench.ship(
        task_id="product-ship-app-route-1",
        task="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "visible-export"),
        use_live_planner=True,
        use_live_generator=True,
    )

    assert payload["shell_view"] == "ship"
    assert payload["ship_mode"] == "app_delivery"
    assert payload["delegated_shell_view"] == "app_ship"
    assert payload["route_summary"] == "task_intake->context_scan->plan->sprint->generate->qa->export->advance"
    assert "output directory" in payload["route_reason"]
    assert "delivery task" in payload["route_reason"]
    assert "repo=" in payload["context_summary"]
    assert "src/" in payload["context_summary"]


def test_product_runtime_app_ship_overrides_simple_web_sprint_checks_with_build(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-build-only")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    captured: dict[str, object] = {}

    original_app_sprint = workbench.app_sprint

    def _capturing_app_sprint(*, acceptance_checks=None, done_definition=None, **kwargs):
        captured["acceptance_checks"] = list(acceptance_checks or [])
        captured["done_definition"] = list(done_definition or [])
        return original_app_sprint(
            acceptance_checks=acceptance_checks,
            done_definition=done_definition,
            **kwargs,
        )

    def _fake_execute_app_generate(**kwargs):
        workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-ship-build-only-1"
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "package.json").write_text('{"name":"product-app-ship-build-only"}', encoding="utf-8")
        (workspace_root / "index.html").write_text("<!doctype html><html><body><div id='root'></div></body></html>", encoding="utf-8")
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text("export function App(){return <main>ship</main>}", encoding="utf-8")
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text("<!doctype html><html><body>built</body></html>", encoding="utf-8")
        return DeliveryExecutionResult(
            execution_summary="Implemented the first runnable landing page.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["package.json", "index.html", "src/App.tsx"],
            artifact_root=str(workspace_root),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench, "app_sprint", _capturing_app_sprint)
    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_ship(
        task_id="product-app-ship-build-only-1",
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "build-only-export"),
        use_live_generator=True,
    )

    assert payload["status"] == "completed"
    assert captured["acceptance_checks"] == [
        "npm run build",
        'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
        'python3 -c "from pathlib import Path; p=Path(\'src/App.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'react app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
    ]
    assert captured["done_definition"] == [
        "The landing page is visually complete enough to demo.",
        "The app builds successfully, emits dist/index.html, and leaves a non-sparse primary page surface.",
    ]


def test_product_runtime_app_show_surfaces_last_execution_from_history_after_advance(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-show-history-fallback")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-show-history-fallback-1"

    def _fake_execute_app_generate(**kwargs):
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "package.json").write_text('{"name":"product-app-show-history-fallback"}', encoding="utf-8")
        (workspace_root / "index.html").write_text("<!doctype html><html><body><div id='root'></div></body></html>", encoding="utf-8")
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text("export function App(){return <main>ship</main>}", encoding="utf-8")
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text("<!doctype html><html><body>built</body></html>", encoding="utf-8")
        return DeliveryExecutionResult(
            execution_summary="Implemented the first runnable landing page.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["package.json", "index.html", "src/App.tsx"],
            artifact_root=str(workspace_root),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_ship(
        task_id="product-app-show-history-fallback-1",
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "show-history-export"),
        use_live_generator=True,
    )

    assert payload["status"] == "completed"
    show_payload = workbench.app_show(task_id="product-app-show-history-fallback-1")
    harness = show_payload["canonical_views"]["app_harness"]

    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert harness["latest_execution_attempt"]["attempt_id"] == "sprint-1-attempt-1"
    assert harness["latest_execution_attempt"]["artifact_kind"] == "vite_dist"
    assert harness["latest_execution_attempt"]["validation_summary"] == "Validation commands passed."
    assert harness["execution_history_count"] == 1
    assert harness["current_sprint_execution_count"] == 0


def test_product_runtime_app_ship_auto_retries_after_failed_qa(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-retry")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    call_state = {"count": 0}
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-ship-retry-1"

    def _fake_execute_app_generate(**kwargs):
        call_state["count"] += 1
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "package.json").write_text('{"name":"product-app-ship-retry"}', encoding="utf-8")
        (workspace_root / "index.html").write_text("<!doctype html><html><body><div id='root'></div></body></html>", encoding="utf-8")
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text(
            f"export function App(){{return <main>attempt-{call_state['count']}</main>}}",
            encoding="utf-8",
        )
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text(
            f"<!doctype html><html><body>attempt-{call_state['count']}</body></html>",
            encoding="utf-8",
        )
        if call_state["count"] == 1:
            return DeliveryExecutionResult(
                execution_summary="Initial landing page pass still fails validation.",
                changed_target_hints=["src/App.tsx", "src/styles.css"],
                changed_files=["package.json", "index.html", "src/App.tsx"],
                artifact_root=str(workspace_root),
                artifact_paths=["dist/index.html"],
                artifact_kind="vite_dist",
                preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
                validation_command="npm run build",
                validation_summary="Validation failed: hero hierarchy still breaks on mobile.",
                validation_ok=False,
                failure_reason="hero hierarchy still breaks on mobile",
            )
        return DeliveryExecutionResult(
            execution_summary="Retry stabilized the landing page hierarchy and interactions.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["package.json", "index.html", "src/App.tsx"],
            artifact_root=str(workspace_root),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_ship(
        task_id="product-app-ship-retry-1",
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "retry-export"),
        use_live_generator=True,
    )

    assert call_state["count"] == 2
    assert payload["status"] == "completed"
    assert payload["active_sprint_id"] == "sprint-2"
    assert payload["route_summary"] == (
        "task_intake->context_scan->plan->sprint->generate->qa->negotiate->retry->generate->qa->export->advance"
    )
    assert [item["phase"] for item in payload["phase_history"]] == [
        "context_scan",
        "plan",
        "sprint",
        "generate",
        "qa",
        "negotiate",
        "retry",
        "generate",
        "qa",
        "export",
        "advance",
    ]
    assert payload["validation_summary"] == "Validation commands passed."
    assert (tmp_path / "retry-export" / "dist" / "index.html").exists()


def test_product_runtime_app_ship_auto_replans_after_retry_budget_exhaustion(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-replan")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    call_state = {"count": 0}
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-ship-replan-1"

    def _fake_execute_app_generate(**kwargs):
        call_state["count"] += 1
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "package.json").write_text('{"name":"product-app-ship-replan"}', encoding="utf-8")
        (workspace_root / "index.html").write_text("<!doctype html><html><body><div id='root'></div></body></html>", encoding="utf-8")
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text(
            f"export function App(){{return <main>attempt-{call_state['count']}</main>}}",
            encoding="utf-8",
        )
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text(
            f"<!doctype html><html><body>attempt-{call_state['count']}</body></html>",
            encoding="utf-8",
        )
        if call_state["count"] < 3:
            return DeliveryExecutionResult(
                execution_summary=f"Attempt {call_state['count']} still fails the mobile layout gate.",
                changed_target_hints=["src/App.tsx", "src/styles.css"],
                changed_files=["package.json", "index.html", "src/App.tsx"],
                artifact_root=str(workspace_root),
                artifact_paths=["dist/index.html"],
                artifact_kind="vite_dist",
                preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
                validation_command="npm run build",
                validation_summary="Validation failed: mobile layout still collapses the hero stack.",
                validation_ok=False,
                failure_reason="mobile layout still collapses the hero stack",
            )
        return DeliveryExecutionResult(
            execution_summary="Replanned sprint stabilizes the mobile hero and clears validation.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["package.json", "index.html", "src/App.tsx"],
            artifact_root=str(workspace_root),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_ship(
        task_id="product-app-ship-replan-1",
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "replan-export"),
        use_live_generator=True,
    )

    assert call_state["count"] == 3
    assert payload["status"] == "completed"
    assert payload["active_sprint_id"] == "sprint-2"
    assert payload["route_summary"] == (
        "task_intake->context_scan->plan->sprint->generate->qa->negotiate->retry->generate->qa->escalate->replan->sprint->generate->qa->export->advance"
    )
    assert [item["phase"] for item in payload["phase_history"]] == [
        "context_scan",
        "plan",
        "sprint",
        "generate",
        "qa",
        "negotiate",
        "retry",
        "generate",
        "qa",
        "escalate",
        "replan",
        "sprint",
        "generate",
        "qa",
        "export",
        "advance",
    ]
    assert payload["validation_summary"] == "Validation commands passed."
    assert (tmp_path / "replan-export" / "dist" / "index.html").exists()


def test_product_runtime_app_ship_reconciles_workspace_artifact_when_execution_attempt_is_missing(
    tmp_path, monkeypatch
) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-reconcile")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    task_id = "product-app-ship-reconcile-1"
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / task_id

    def _fake_app_generate(*, task_id: str, sprint_id: str = "", use_live_generator: bool = False, **kwargs):
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "package.json").write_text(
            '{"name":"product-app-ship-reconcile","scripts":{"build":"node -e \\"process.exit(0)\\""}}',
            encoding="utf-8",
        )
        (workspace_root / "index.html").write_text("<!doctype html><html><body><div id='root'></div></body></html>", encoding="utf-8")
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text(
            (
                "export default function App(){return ("
                "<main><header><h1>Reconciled ship</h1><p>Autonomous delivery for app work.</p></header>"
                "<section><h2>Why it matters</h2><p>This preserved artifact now reflects the current non-sparse surface rule.</p></section>"
                "<section><h2>Ready to export</h2><p>Build output and source surface are both present.</p></section>"
                "</main>);}"
            ),
            encoding="utf-8",
        )
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text(
            "<!doctype html><html><body>reconciled build</body></html>",
            encoding="utf-8",
        )
        trace_payload = {
            "step_count": 2,
            "steps": [
                {
                    "step_index": 1,
                    "tool_name": "workbench.model",
                    "tool_call_id": None,
                    "tool_input": {"model": "z-ai/glm-5.1"},
                    "status": "success",
                    "output_signature": {"result_type": "ModelResponse"},
                    "error": None,
                },
                {
                    "step_index": 2,
                    "tool_name": "execute",
                    "tool_call_id": "call_build",
                    "tool_input": {"command": "npm run build 2>&1", "timeout": 60},
                    "status": "success",
                    "output_signature": {"result_type": "str", "chars": 24},
                    "error": None,
                },
            ],
        }
        (workspace_root / ".aionis-delivery-trace.json").write_text(
            json.dumps(trace_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        payload = workbench._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_generate"
        payload["task_id"] = task_id
        return payload

    monkeypatch.setattr(workbench, "app_generate", _fake_app_generate)

    payload = workbench.app_ship(
        task_id=task_id,
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "reconcile-export"),
        use_live_generator=True,
    )

    session = load_session(str(tmp_path), task_id, project_scope=workbench._config.project_scope)
    assert session is not None
    assert session.app_harness_state is not None
    assert session.app_harness_state.execution_history
    latest = session.app_harness_state.execution_history[-1]
    assert latest.artifact_path in {"dist/index.html", "index.html"}
    assert latest.validation_summary == "Validation commands passed."
    assert payload["status"] == "completed"
    assert payload["export_root"] == str(tmp_path / "reconcile-export")
    assert (tmp_path / "reconcile-export" / "dist" / "index.html").exists()
    export_payload = workbench.app_export(
        task_id=task_id,
        output_dir=str(tmp_path / "reconcile-export-second"),
    )
    assert export_payload["entrypoint"] == str(tmp_path / "reconcile-export-second" / "dist" / "index.html")


def test_product_runtime_app_ship_fails_fast_when_generate_records_no_execution_attempt(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-first-turn-stall")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    task_id = "product-app-ship-first-turn-stall-1"
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / task_id

    def _fake_app_generate(*, task_id: str, sprint_id: str = "", use_live_generator: bool = False, **kwargs):
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / ".aionis-delivery-trace.json").write_text(
            json.dumps(
                {
                    "step_count": 0,
                    "steps": [],
                    "failure_reason": (
                        "Delivery failed after 3/3 first-response timeouts. "
                        "Last error: provider_first_turn_stall: Delivery agent did not produce "
                        "a first model/tool step within 60 seconds."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = workbench._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_generate"
        payload["task_id"] = task_id
        return payload

    monkeypatch.setattr(workbench, "app_generate", _fake_app_generate)

    payload = workbench.app_ship(
        task_id=task_id,
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "first-turn-stall-export"),
        use_live_generator=True,
    )

    assert payload["status"] == "failed"
    assert payload["phase"] == "generate"
    assert payload["failure_class"] == "provider_first_turn_stall"
    assert "provider_first_turn_stall" in payload["failure_reason"]
    assert payload["route_summary"] == "task_intake->context_scan->plan->sprint->generate"
    assert payload["controller_action_bar"] == {
        "task_id": task_id,
        "status": "active",
        "recommended_command": f"/next {task_id}",
        "allowed_commands": [
            f"/next {task_id}",
            f"/show {task_id}",
            f"/session {task_id}",
        ],
    }


def test_product_runtime_app_ship_does_not_surface_vite_dist_after_provider_transient_error(
    tmp_path, monkeypatch
) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-provider-transient")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    task_id = "product-app-ship-provider-transient-1"
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / task_id

    def _fake_app_generate(*, task_id: str, sprint_id: str = "", use_live_generator: bool = False, **kwargs):
        workspace_root.mkdir(parents=True, exist_ok=True)
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
                    "failure_reason": "Delivery failed after 3/3 transient attempts. Last error: Connection error.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = workbench._surface.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_generate"
        payload["task_id"] = task_id
        return payload

    monkeypatch.setattr(workbench, "app_generate", _fake_app_generate)

    payload = workbench.app_ship(
        task_id=task_id,
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "provider-transient-export"),
        use_live_generator=True,
    )

    assert payload["status"] == "failed"
    assert payload["phase"] == "generate"
    assert payload["failure_class"] == "provider_transient_error"
    assert payload.get("artifact_kind") in {None, "", "workspace_app"}
    assert payload.get("artifact_path") in {None, "", "index.html"}
    assert payload.get("artifact_kind") != "vite_dist"
    assert payload.get("artifact_path") != "dist/index.html"

    show_payload = workbench.app_show(task_id=task_id)
    shown_attempt = show_payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    if shown_attempt:
        assert shown_attempt["artifact_kind"] != "vite_dist"
        assert shown_attempt["artifact_path"] != "dist/index.html"


def test_product_runtime_app_generate_does_not_surface_vite_dist_after_provider_transient_error(
    tmp_path, monkeypatch
) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-generate-provider-transient")
    session = workbench._initial_session(
        task_id="product-app-generate-provider-transient-1",
        task="Build a modern landing page for an AI agent platform.",
        target_files=[],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-generate-provider-transient-1",
        prompt="Build a modern landing page for an AI agent platform.",
        title="Modern Landing Page",
        app_type="desktop_like_web_app",
        stack=["React", "Vite", "TypeScript"],
        features=["hero", "metrics", "cta"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-generate-provider-transient-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable landing page.",
        scope=["Create the first complete landing page shell."],
        acceptance_checks=[],
        done_definition=["The task workspace contains a complete landing page."],
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_invoke_delivery_task(
        *,
        system_parts,
        memory_sources,
        root_dir,
        task,
        timeout_seconds=None,
        trace_path="",
    ):
        workspace_root = Path(root_dir)
        dist_root = workspace_root / "dist"
        dist_root.mkdir(parents=True, exist_ok=True)
        (dist_root / "index.html").write_text(
            "<!doctype html><html><body>stale build</body></html>",
            encoding="utf-8",
        )
        if trace_path:
            Path(trace_path).write_text(
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

    monkeypatch.setattr(workbench._execution_host, "invoke_delivery_task", _fake_invoke_delivery_task)

    payload = workbench.app_generate(
        task_id="product-app-generate-provider-transient-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    attempt = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert attempt["artifact_kind"] == "workspace_app"
    assert attempt["artifact_path"] == "index.html"
    assert attempt["failure_reason"] == "Delivery failed after 3/3 transient attempts. Last error: Connection error."

    show_payload = workbench.app_show(task_id="product-app-generate-provider-transient-1")
    shown_attempt = show_payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert shown_attempt["artifact_kind"] == "workspace_app"
    assert shown_attempt["artifact_path"] == "index.html"


def test_product_runtime_app_ship_can_rerun_same_task_id_after_hidden_cache_workspace(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-ship-rerun-cache")
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    task_id = "product-app-ship-rerun-cache-1"
    run_state = {"count": 0}

    def _fake_execute_app_generate(**kwargs):
        run_state["count"] += 1
        workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / task_id
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / ".vite" / "deps").mkdir(parents=True, exist_ok=True)
        (workspace_root / ".vite" / "deps" / f"chunk-{run_state['count']}.js").write_text(
            "console.log('cache')",
            encoding="utf-8",
        )
        (workspace_root / "package.json").write_text(
            '{"name":"product-app-ship-rerun-cache","scripts":{"build":"node -e \\"process.exit(0)\\""}}',
            encoding="utf-8",
        )
        (workspace_root / "index.html").write_text(
            "<!doctype html><html><body><div id='root'></div></body></html>",
            encoding="utf-8",
        )
        (workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (workspace_root / "src" / "App.tsx").write_text(
            (
                "export default function App(){return ("
                f"<main><header><h1>Run {run_state['count']}</h1></header>"
                "<section><p>Rerunnable task workspace.</p></section>"
                "<section><p>Hidden caches must not block reset.</p></section>"
                "</main>);}"
            ),
            encoding="utf-8",
        )
        (workspace_root / "dist").mkdir(parents=True, exist_ok=True)
        (workspace_root / "dist" / "index.html").write_text(
            f"<!doctype html><html><body>run-{run_state['count']}</body></html>",
            encoding="utf-8",
        )
        return DeliveryExecutionResult(
            execution_summary=f"Completed run {run_state['count']}.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["package.json", "index.html", "src/App.tsx", f".vite/deps/chunk-{run_state['count']}.js"],
            artifact_root=str(workspace_root),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    first_payload = workbench.app_ship(
        task_id=task_id,
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "rerun-export-1"),
        use_live_generator=True,
    )
    second_payload = workbench.app_ship(
        task_id=task_id,
        prompt="Build a modern landing page for an AI agent platform.",
        output_dir=str(tmp_path / "rerun-export-2"),
        use_live_generator=True,
    )

    assert run_state["count"] == 2
    assert first_payload["status"] == "completed"
    assert second_payload["status"] == "completed"
    assert (tmp_path / "rerun-export-1" / "dist" / "index.html").exists()
    assert (tmp_path / "rerun-export-2" / "dist" / "index.html").exists()


def test_product_runtime_simple_web_generate_prefers_sprint_goal_and_app_files(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-simple-web-generate-focus")
    workbench.app_plan(
        task_id="product-simple-web-generate-focus-1",
        prompt="Build a modern landing page for an AI agent platform.",
    )
    workbench.app_sprint(
        task_id="product-simple-web-generate-focus-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable landing page.",
        scope=["hero section", "feature band", "cta strip"],
        acceptance_checks=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
        ],
        done_definition=["landing page renders"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute_app_generate(**kwargs):
        assert kwargs["delivery_family"] == "react_vite_web"
        assert kwargs["execution_summary"] == "Ship the first runnable landing page."
        assert kwargs["changed_target_hints"][:5] == [
            "package.json",
            "index.html",
            "src/main.tsx",
            "src/App.tsx",
            "src/styles.css",
        ]
        return DeliveryExecutionResult(
            execution_summary="Implemented the landing page shell.",
            changed_target_hints=list(kwargs["changed_target_hints"]),
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-simple-web-generate-focus-1"),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_app",
            preview_command="npm install --no-fund --no-audit && npm run dev",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_generate(
        task_id="product-simple-web-generate-focus-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    assert payload["canonical_views"]["app_harness"]["latest_execution_attempt"]["execution_summary"] == (
        "Implemented the landing page shell."
    )


def test_product_runtime_delivery_contract_warns_against_cd_root_for_shell_commands() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Modern Landing Page",
            "prompt": "Build a modern landing page for an AI agent platform.",
            "app_type": "desktop_like_web_app",
            "stack": ["React", "Vite"],
            "features": ["hero", "pricing"],
        },
        sprint_contract={
            "goal": "Ship the first runnable landing page.",
            "scope": ["hero section", "feature band"],
            "acceptance_checks": [
                "npm run build",
                'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
                'python3 -c "from pathlib import Path; p=Path(\'src/App.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'react app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
            ],
            "done_definition": ["landing page renders"],
        },
        revision={},
        execution_summary="Ship the first runnable landing page.",
        changed_target_hints=["src/App.tsx", "src/styles.css", "index.html"],
        selected_targets=["package.json", "vite.config.ts", "tsconfig.json", "index.html", "src/main.tsx", "src/App.tsx", "src/styles.css"],
        validation_commands=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'src/App.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'react app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "Never prefix shell commands with `cd /`" in combined
    assert "For shell commands, run `npm run build` directly from the current workspace." in combined


def test_product_runtime_delivery_contract_sets_simple_web_quality_bar() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Modern Landing Page",
            "prompt": "Build a modern landing page for an AI agent platform.",
            "app_type": "desktop_like_web_app",
            "stack": ["React", "Vite"],
            "features": ["hero", "pricing"],
        },
        sprint_contract={
            "goal": "Ship the first runnable landing page.",
            "scope": ["hero section", "feature band"],
            "acceptance_checks": ["npm run build"],
            "done_definition": ["landing page renders"],
        },
        revision={},
        execution_summary="Ship the first runnable landing page.",
        changed_target_hints=["src/App.tsx", "src/styles.css", "index.html"],
        selected_targets=["package.json", "vite.config.ts", "tsconfig.json", "index.html", "src/main.tsx", "src/App.tsx", "src/styles.css"],
        validation_commands=["npm run build"],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "Minimum page quality bar: deliver a complete, presentation-ready page rather than a sparse shell." in combined
    assert "Bootstrap the app from scratch inside the current workspace before refining the UI." in combined
    assert "Create the minimal React/Vite project files yourself when they are missing" in combined
    assert "establish the project shell and core delivery files together: package.json, index.html, src/main.tsx, src/App.tsx, and src/styles.css." in combined
    assert "After reading package.json, index.html, src/App.tsx, and src/styles.css, stop discovery and move directly into write_file/edit_file calls." in combined
    assert "In the second model response at the latest, begin writing the page implementation instead of continuing analysis." in combined
    assert "run npm install --no-fund --no-audit and npm run build before requesting more model turns" in combined
    assert "include a clear navigation/header, a strong hero section, at least two supporting content sections, and a CTA or footer area." in combined
    assert "Responsive behavior is required" in combined


def test_product_runtime_delivery_contract_sets_vue_web_quality_bar() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Modern Vue Landing Page",
            "prompt": "Build a modern Vue landing page for an AI agent platform.",
            "app_type": "desktop_like_web_app",
            "stack": ["Vue", "Vite"],
            "features": ["hero", "pricing"],
        },
        sprint_contract={
            "goal": "Ship the first runnable Vue landing page.",
            "scope": ["hero section", "feature band"],
            "acceptance_checks": [
                "npm run build",
                'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
                'python3 -c "from pathlib import Path; p=Path(\'src/App.vue\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'vue app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
            ],
            "done_definition": ["landing page renders"],
        },
        revision={},
        execution_summary="Ship the first runnable Vue landing page.",
        changed_target_hints=["src/App.vue", "src/styles.css", "index.html"],
        selected_targets=["package.json", "vite.config.ts", "tsconfig.json", "index.html", "src/main.ts", "src/App.vue", "src/styles.css"],
        validation_commands=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'src/App.vue\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'vue app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "This is a simple Vue web delivery task." in combined
    assert "Create the minimal Vue/Vite project files yourself when they are missing" in combined
    assert "src/main.ts, src/App.vue, and src/styles.css." in combined
    assert "After reading package.json, index.html, src/App.vue, and src/styles.css" in combined
    assert "Minimum page quality bar" in combined


def test_product_runtime_delivery_contract_sets_svelte_web_quality_bar() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Modern Svelte Landing Page",
            "prompt": "Build a modern Svelte landing page for an AI agent platform.",
            "app_type": "desktop_like_web_app",
            "stack": ["Svelte", "Vite"],
            "features": ["hero", "pricing"],
        },
        sprint_contract={
            "goal": "Ship the first runnable Svelte landing page.",
            "scope": ["hero section", "feature band"],
            "acceptance_checks": [
                "npm run build",
                'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
                'python3 -c "from pathlib import Path; p=Path(\'src/App.svelte\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'svelte app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
            ],
            "done_definition": ["landing page renders"],
        },
        revision={},
        execution_summary="Ship the first runnable Svelte landing page.",
        changed_target_hints=["src/App.svelte", "src/app.css", "index.html"],
        selected_targets=["package.json", "vite.config.ts", "tsconfig.json", "svelte.config.js", "index.html", "src/main.ts", "src/App.svelte", "src/app.css"],
        validation_commands=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'src/App.svelte\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'svelte app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "This is a simple Svelte web delivery task." in combined
    assert "Create the minimal Svelte/Vite project files yourself when they are missing" in combined
    assert "src/main.ts, src/App.svelte, and src/app.css." in combined
    assert "After reading package.json, index.html, src/App.svelte, and src/app.css" in combined
    assert "Minimum page quality bar" in combined


def test_product_runtime_delivery_contract_sets_nextjs_web_quality_bar() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Modern Next Dashboard",
            "prompt": "Build a modern Next.js dashboard for an AI agent platform.",
            "app_type": "desktop_like_web_app",
            "stack": ["Next.js", "React"],
            "features": ["hero", "analytics"],
        },
        sprint_contract={
            "goal": "Ship the first runnable Next.js dashboard.",
            "scope": ["hero section", "analytics band"],
            "acceptance_checks": [
                "npm run build",
                'python3 -c "from pathlib import Path; p=Path(\'.next/BUILD_ID\'); print(\'next build ok\' if p.exists() else \'missing .next/BUILD_ID\'); raise SystemExit(0 if p.exists() else 1)"',
                'python3 -c "from pathlib import Path; p=Path(\'app/page.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'next page surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
            ],
            "done_definition": ["dashboard renders"],
        },
        revision={},
        execution_summary="Ship the first runnable Next.js dashboard.",
        changed_target_hints=["app/page.tsx", "app/globals.css"],
        selected_targets=["package.json", "next.config.mjs", "tsconfig.json", "next-env.d.ts", "app/layout.tsx", "app/page.tsx", "app/globals.css"],
        validation_commands=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'.next/BUILD_ID\'); print(\'next build ok\' if p.exists() else \'missing .next/BUILD_ID\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'app/page.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'next page surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "This is a Next.js web delivery task." in combined
    assert "Create the minimal Next.js project files yourself when they are missing" in combined
    assert "package.json, app/layout.tsx, app/page.tsx, and app/globals.css." in combined
    assert "After reading package.json, app/page.tsx, and app/globals.css" in combined
    assert "Minimum page quality bar" in combined


def test_product_runtime_delivery_contract_sets_python_api_quality_bar() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Agent Platform API",
            "prompt": "Build a FastAPI backend service with a health endpoint and a features endpoint for an AI agent platform.",
            "app_type": "full_stack_app",
            "stack": ["React", "Vite", "FastAPI", "SQLite"],
            "features": ["health endpoint", "features endpoint"],
        },
        sprint_contract={
            "goal": "Ship the first runnable backend service.",
            "scope": ["health endpoint", "features endpoint"],
            "acceptance_checks": [
                "python3 -m py_compile main.py",
                "python3 -c \"from pathlib import Path; s=Path('requirements.txt').read_text(encoding='utf-8').lower(); required=('fastapi', 'uvicorn'); missing=[item for item in required if item not in s]; print('python api manifest ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
                "python3 -c \"from pathlib import Path; s=Path('main.py').read_text(encoding='utf-8'); required=('FastAPI(', 'app =', '/health', '/features'); missing=[item for item in required if item not in s]; print('python api structure ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
            ],
            "done_definition": ["api compiles"],
        },
        revision={},
        execution_summary="Ship the first runnable backend service.",
        changed_target_hints=["requirements.txt", "main.py"],
        selected_targets=["requirements.txt", "main.py"],
        validation_commands=[
            "python3 -m py_compile main.py",
            "python3 -c \"from pathlib import Path; s=Path('requirements.txt').read_text(encoding='utf-8').lower(); required=('fastapi', 'uvicorn'); missing=[item for item in required if item not in s]; print('python api manifest ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
            "python3 -c \"from pathlib import Path; s=Path('main.py').read_text(encoding='utf-8'); required=('FastAPI(', 'app =', '/health', '/features'); missing=[item for item in required if item not in s]; print('python api structure ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
        ],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "This is a Python API delivery task." in combined
    assert "Create the minimal FastAPI project files yourself when they are missing, including requirements.txt and main.py." in combined
    assert "verify requirements.txt includes FastAPI and Uvicorn" in combined
    assert "run syntax validation" in combined
    assert "Minimum API quality bar" in combined


def test_product_runtime_delivery_contract_sets_node_api_quality_bar() -> None:
    system_parts, task = _build_app_delivery_contract(
        product_spec={
            "title": "Agent Platform Node API",
            "prompt": "Build an Express backend service with a health endpoint and a features endpoint for an AI agent platform.",
            "app_type": "api_service",
            "stack": ["Node", "Express"],
            "features": ["health endpoint", "features endpoint"],
        },
        sprint_contract={
            "goal": "Ship the first runnable backend service.",
            "scope": ["health endpoint", "features endpoint"],
            "acceptance_checks": [
                "node --check main.js",
                "node -e \"const fs=require('fs'); const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); const deps={...(pkg.dependencies||{}), ...(pkg.devDependencies||{})}; const scripts=pkg.scripts||{}; const missing=[]; if(!('express' in deps)) missing.push('express dependency'); if(!(scripts.dev || scripts.start)) missing.push('dev/start script'); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api manifest ok')}\"",
                "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
            ],
            "done_definition": ["api compiles"],
        },
        revision={},
        execution_summary="Ship the first runnable backend service.",
        changed_target_hints=["package.json", "main.js"],
        selected_targets=["package.json", "main.js"],
        validation_commands=[
            "node --check main.js",
            "node -e \"const fs=require('fs'); const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); const deps={...(pkg.dependencies||{}), ...(pkg.devDependencies||{})}; const scripts=pkg.scripts||{}; const missing=[]; if(!('express' in deps)) missing.push('express dependency'); if(!(scripts.dev || scripts.start)) missing.push('dev/start script'); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api manifest ok')}\"",
            "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
        ],
    )

    combined = "\n".join(system_parts) + "\n" + task

    assert "This is a Node API delivery task." in combined
    assert "Create the minimal Node/Express project files yourself when they are missing, including package.json and main.js." in combined
    assert "verify package.json declares the Express dependency and a dev/start script" in combined
    assert "run syntax validation" in combined
    assert "Minimum API quality bar" in combined


def test_product_runtime_node_api_prompt_markers_override_conflicting_stack() -> None:
    system_parts, _task = _build_app_delivery_contract(
        product_spec={
            "title": "Conflicting Backend Spec",
            "prompt": "Build an Express backend service with a health endpoint and a features endpoint.",
            "app_type": "full_stack_app",
            "stack": ["FastAPI", "SQLite"],
            "features": ["health endpoint", "features endpoint"],
        },
        sprint_contract={
            "goal": "Ship the first runnable backend service.",
            "scope": ["health endpoint", "features endpoint"],
            "acceptance_checks": [
                "node --check main.js",
                "node -e \"const fs=require('fs'); const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); const deps={...(pkg.dependencies||{}), ...(pkg.devDependencies||{})}; const scripts=pkg.scripts||{}; const missing=[]; if(!('express' in deps)) missing.push('express dependency'); if(!(scripts.dev || scripts.start)) missing.push('dev/start script'); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api manifest ok')}\"",
                "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
            ],
            "done_definition": ["api compiles"],
        },
        revision={},
        execution_summary="Ship the first runnable backend service.",
        changed_target_hints=["package.json", "main.js"],
        selected_targets=["package.json", "main.js"],
        validation_commands=[
            "node --check main.js",
            "node -e \"const fs=require('fs'); const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); const deps={...(pkg.dependencies||{}), ...(pkg.devDependencies||{})}; const scripts=pkg.scripts||{}; const missing=[]; if(!('express' in deps)) missing.push('express dependency'); if(!(scripts.dev || scripts.start)) missing.push('dev/start script'); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api manifest ok')}\"",
            "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
        ],
    )

    combined = "\n".join(system_parts)
    assert "This is a Node API delivery task." in combined


def test_product_runtime_python_api_generate_prefers_service_targets_and_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-python-api-generate-focus")
    workbench.app_plan(
        task_id="product-python-api-generate-focus-1",
        prompt="Build a FastAPI backend service with a health endpoint and a features endpoint for an AI agent platform.",
        app_type="full_stack_app",
        stack=["React", "Vite", "FastAPI", "SQLite"],
    )
    workbench.app_sprint(
        task_id="product-python-api-generate-focus-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable backend service.",
        scope=["health endpoint", "features endpoint"],
        acceptance_checks=[
            "python3 -m py_compile main.py",
            "python3 -c \"from pathlib import Path; s=Path('requirements.txt').read_text(encoding='utf-8').lower(); required=('fastapi', 'uvicorn'); missing=[item for item in required if item not in s]; print('python api manifest ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
            "python3 -c \"from pathlib import Path; s=Path('main.py').read_text(encoding='utf-8'); required=('FastAPI(', 'app =', '/health', '/features'); missing=[item for item in required if item not in s]; print('python api structure ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
        ],
        done_definition=["api compiles"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute_app_generate(**kwargs):
        assert kwargs["delivery_family"] == "python_fastapi_api"
        assert kwargs["execution_summary"] == "Ship the first runnable backend service."
        assert kwargs["changed_target_hints"][:2] == ["requirements.txt", "main.py"]
        assert kwargs["memory_sources"][:2] == ["requirements.txt", "main.py"]
        assert kwargs["validation_commands"][0] == "python3 -m py_compile main.py"
        assert len(kwargs["validation_commands"]) == 3
        assert "fastapi" in kwargs["validation_commands"][1].lower()
        assert "/features" in kwargs["validation_commands"][2]
        return DeliveryExecutionResult(
            execution_summary="Implemented the backend service shell.",
            changed_target_hints=list(kwargs["changed_target_hints"]),
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-python-api-generate-focus-1"),
            artifact_paths=["requirements.txt", "main.py"],
            artifact_kind="python_api_workspace",
            preview_command="python3 -m uvicorn main:app --host 0.0.0.0 --port 4173",
            validation_command="python3 -c \"from pathlib import Path; s=Path('main.py').read_text(encoding='utf-8'); required=('FastAPI(', 'app =', '/health', '/features'); missing=[item for item in required if item not in s]; print('python api structure ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_generate(
        task_id="product-python-api-generate-focus-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    latest = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert latest["artifact_kind"] == "python_api_workspace"
    assert latest["validation_command"].startswith("python3 -c ")


def test_product_runtime_vue_web_generate_prefers_service_targets_and_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-vue-web-generate-focus")
    workbench.app_plan(
        task_id="product-vue-web-generate-focus-1",
        prompt="Build a modern Vue landing page for an AI agent platform.",
        app_type="desktop_like_web_app",
        stack=["Vue", "Vite"],
    )
    workbench.app_sprint(
        task_id="product-vue-web-generate-focus-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable Vue landing page.",
        scope=["hero section", "feature band"],
        acceptance_checks=["npm run build"],
        done_definition=["landing page renders"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute_app_generate(**kwargs):
        assert kwargs["delivery_family"] == "vue_vite_web"
        assert kwargs["execution_summary"] == "Ship the first runnable Vue landing page."
        assert kwargs["changed_target_hints"][:5] == [
            "package.json",
            "index.html",
            "src/main.ts",
            "src/App.vue",
            "src/styles.css",
        ]
        assert kwargs["memory_sources"][:5] == kwargs["changed_target_hints"][:5]
        assert kwargs["validation_commands"] == [
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'src/App.vue\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'vue app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ]
        return DeliveryExecutionResult(
            execution_summary="Implemented the Vue landing page shell.",
            changed_target_hints=list(kwargs["changed_target_hints"]),
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-vue-web-generate-focus-1"),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_app",
            preview_command="npm install --no-fund --no-audit && npm run dev",
            validation_command='python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_generate(
        task_id="product-vue-web-generate-focus-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    latest = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert latest["validation_command"].startswith('python3 -c ')


def test_product_runtime_svelte_web_generate_prefers_service_targets_and_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-svelte-web-generate-focus")
    workbench.app_plan(
        task_id="product-svelte-web-generate-focus-1",
        prompt="Build a modern Svelte landing page for an AI agent platform.",
        app_type="desktop_like_web_app",
        stack=["Svelte", "Vite"],
    )
    workbench.app_sprint(
        task_id="product-svelte-web-generate-focus-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable Svelte landing page.",
        scope=["hero section", "feature band"],
        acceptance_checks=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
        ],
        done_definition=["landing page renders"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute_app_generate(**kwargs):
        assert kwargs["delivery_family"] == "svelte_vite_web"
        assert kwargs["execution_summary"] == "Ship the first runnable Svelte landing page."
        assert kwargs["changed_target_hints"][:5] == [
            "package.json",
            "index.html",
            "src/main.ts",
            "src/App.svelte",
            "src/app.css",
        ]
        assert kwargs["memory_sources"][:5] == kwargs["changed_target_hints"][:5]
        assert kwargs["validation_commands"] == [
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'src/App.svelte\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'svelte app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ]
        return DeliveryExecutionResult(
            execution_summary="Implemented the Svelte landing page shell.",
            changed_target_hints=list(kwargs["changed_target_hints"]),
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-svelte-web-generate-focus-1"),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_app",
            preview_command="npm install --no-fund --no-audit && npm run dev",
            validation_command='python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_generate(
        task_id="product-svelte-web-generate-focus-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    latest = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert latest["validation_command"].startswith('python3 -c ')


def test_product_runtime_nextjs_web_generate_prefers_service_targets_and_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-nextjs-web-generate-focus")
    workbench.app_plan(
        task_id="product-nextjs-web-generate-focus-1",
        prompt="Build a modern Next.js dashboard for an AI agent platform.",
        app_type="desktop_like_web_app",
        stack=["Next.js", "React"],
    )
    workbench.app_sprint(
        task_id="product-nextjs-web-generate-focus-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable Next.js dashboard.",
        scope=["hero section", "analytics band"],
        acceptance_checks=[
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'.next/BUILD_ID\'); print(\'next build ok\' if p.exists() else \'missing .next/BUILD_ID\'); raise SystemExit(0 if p.exists() else 1)"',
        ],
        done_definition=["dashboard renders"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute_app_generate(**kwargs):
        assert kwargs["delivery_family"] == "nextjs_web"
        assert kwargs["execution_summary"] == "Ship the first runnable Next.js dashboard."
        assert kwargs["changed_target_hints"][:4] == [
            "package.json",
            "app/layout.tsx",
            "app/page.tsx",
            "app/globals.css",
        ]
        assert kwargs["memory_sources"][:4] == kwargs["changed_target_hints"][:4]
        assert len(kwargs["memory_sources"]) == 4
        assert kwargs["validation_commands"] == [
            "npm run build",
            'python3 -c "from pathlib import Path; p=Path(\'.next/BUILD_ID\'); print(\'next build ok\' if p.exists() else \'missing .next/BUILD_ID\'); raise SystemExit(0 if p.exists() else 1)"',
            'python3 -c "from pathlib import Path; p=Path(\'app/page.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'next page surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
        ]
        return DeliveryExecutionResult(
            execution_summary="Implemented the Next.js dashboard shell.",
            changed_target_hints=list(kwargs["changed_target_hints"]),
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-nextjs-web-generate-focus-1"),
            artifact_paths=["package.json", "app/page.tsx"],
            artifact_kind="nextjs_workspace",
            preview_command="npm run dev",
            validation_command='python3 -c "from pathlib import Path; p=Path(\'.next/BUILD_ID\'); print(\'next build ok\' if p.exists() else \'missing .next/BUILD_ID\'); raise SystemExit(0 if p.exists() else 1)"',
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_generate(
        task_id="product-nextjs-web-generate-focus-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    latest = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert latest["artifact_kind"] == "nextjs_workspace"
    assert latest["validation_command"].startswith('python3 -c ')


def test_product_runtime_node_api_generate_prefers_service_targets_and_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-node-api-generate-focus")
    workbench.app_plan(
        task_id="product-node-api-generate-focus-1",
        prompt="Build an Express backend service with a health endpoint and a features endpoint for an AI agent platform.",
        app_type="api_service",
        stack=["Node", "Express"],
    )
    workbench.app_sprint(
        task_id="product-node-api-generate-focus-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable backend service.",
        scope=["health endpoint", "features endpoint"],
        acceptance_checks=[
            "node --check main.js",
            "node -e \"const fs=require('fs'); const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); const deps={...(pkg.dependencies||{}), ...(pkg.devDependencies||{})}; const scripts=pkg.scripts||{}; const missing=[]; if(!('express' in deps)) missing.push('express dependency'); if(!(scripts.dev || scripts.start)) missing.push('dev/start script'); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api manifest ok')}\"",
            "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
        ],
        done_definition=["api compiles"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute_app_generate(**kwargs):
        assert kwargs["delivery_family"] == "node_express_api"
        assert kwargs["execution_summary"] == "Ship the first runnable backend service."
        assert kwargs["changed_target_hints"][:2] == ["package.json", "main.js"]
        assert kwargs["memory_sources"][:2] == ["package.json", "main.js"]
        assert kwargs["validation_commands"][0] == "node --check main.js"
        assert len(kwargs["validation_commands"]) == 3
        assert "express dependency" in kwargs["validation_commands"][1]
        assert "/features" in kwargs["validation_commands"][2]
        return DeliveryExecutionResult(
            execution_summary="Implemented the backend service shell.",
            changed_target_hints=list(kwargs["changed_target_hints"]),
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-node-api-generate-focus-1"),
            artifact_paths=["package.json", "main.js"],
            artifact_kind="node_api_workspace",
            preview_command="npm run dev",
            validation_command="node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    payload = workbench.app_generate(
        task_id="product-node-api-generate-focus-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    latest = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert latest["artifact_kind"] == "node_api_workspace"
    assert latest["validation_command"].startswith("node -e ")


def test_product_runtime_app_plan_defaults_node_api_evaluator_criteria(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-node-api-default-criteria")
    payload = workbench.app_plan(
        task_id="product-node-api-default-criteria-1",
        prompt="Build an Express backend service with a health endpoint and a features endpoint for an AI agent platform.",
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["product_spec"]["app_type"] == "api_service"
    assert harness["product_spec"]["stack"] == ["Node", "Express"]
    assert harness["active_sprint_contract"]["acceptance_checks"][0] == "node --check main.js"
    assert len(harness["active_sprint_contract"]["acceptance_checks"]) == 3
    assert harness["active_sprint_contract"]["done_definition"] == [
        "The API service exposes a runnable Express app entrypoint.",
        "The service passes syntax, dependency-manifest, and route-structure validation.",
    ]
    assert harness["evaluator_criteria_count"] == 2


def test_product_runtime_app_plan_defaults_vue_web_evaluator_criteria(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-vue-web-default-criteria")
    payload = workbench.app_plan(
        task_id="product-vue-web-default-criteria-1",
        prompt="Build a modern Vue landing page for an AI agent platform.",
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["product_spec"]["app_type"] == "desktop_like_web_app"
    assert harness["product_spec"]["stack"] == ["Vue", "Vite", "SQLite"]
    assert harness["active_sprint_contract"]["acceptance_checks"][0] == "npm run build"
    assert len(harness["active_sprint_contract"]["acceptance_checks"]) == 3
    assert harness["evaluator_criteria_count"] == 3


def test_product_runtime_app_plan_defaults_svelte_web_evaluator_criteria(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-svelte-web-default-criteria")
    payload = workbench.app_plan(
        task_id="product-svelte-web-default-criteria-1",
        prompt="Build a modern Svelte landing page for an AI agent platform.",
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["product_spec"]["app_type"] == "desktop_like_web_app"
    assert harness["product_spec"]["stack"] == ["Svelte", "Vite", "SQLite"]
    assert harness["active_sprint_contract"]["acceptance_checks"][0] == "npm run build"
    assert len(harness["active_sprint_contract"]["acceptance_checks"]) == 3
    assert harness["evaluator_criteria_count"] == 3


def test_product_runtime_app_plan_defaults_nextjs_web_evaluator_criteria(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-nextjs-web-default-criteria")
    payload = workbench.app_plan(
        task_id="product-nextjs-web-default-criteria-1",
        prompt="Build a modern Next.js dashboard for an AI agent platform.",
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["product_spec"]["app_type"] == "desktop_like_web_app"
    assert harness["product_spec"]["stack"] == ["Next.js", "React", "SQLite"]
    assert harness["active_sprint_contract"]["acceptance_checks"][0] == "npm run build"
    assert len(harness["active_sprint_contract"]["acceptance_checks"]) == 3
    assert harness["evaluator_criteria_count"] == 3


def test_product_cold_start_flow_surfaces_bootstrap_and_status(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-cold-start")

    initialized = workbench.initialize_project()
    status = workbench.shell_status()

    assert initialized["initialized"] is True
    assert Path(initialized["bootstrap_path"]).exists()
    assert initialized["bootstrap_snapshot"]["bootstrap_focus"]
    assert initialized["bootstrap_snapshot"]["bootstrap_first_step"]
    assert initialized["setup"]["mode"] == "inspect-only"
    assert initialized["setup"]["live_ready"] is False
    assert status["task_id"] is None
    assert status["dashboard_summary"]["status"] == "empty"
    assert status["status_line"]["task_family"] == "task:cold-start"
    assert status["status_line"]["strategy_profile"] == "bootstrap_first_loop"
    assert "task:cold-start" in status["text"]


def test_product_run_success_surface_wraps_orchestrated_result(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-run-success")
    session = workbench._initial_session(
        task_id="product-run-1",
        task="Apply a narrow demo fix.",
        target_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["python3 -c \"print('ok')\""],
        apply_strategy=False,
    )
    session.status = "completed"
    session.selected_task_family = "task:demo"
    session.last_result_preview = "Implemented the narrow demo fix."
    session.last_validation_result = {
        "ok": True,
        "command": "python3 -c \"print('ok')\"",
        "exit_code": 0,
        "summary": "Validation commands passed.",
        "output": "",
        "changed_files": ["src/demo.py", "tests/test_demo.py"],
    }
    session_path = workbench._save_session(session)

    def _stub_run(**_: object) -> OrchestrationResult:
        return OrchestrationResult(
            task_id="product-run-1",
            runner="run",
            content="Implemented the narrow demo fix.",
            session=session,
            session_path=session_path,
            aionis={
                "complete": {"status": "ok"},
                "validation": {"ok": True},
                "task_session_state": {
                    "status": "completed",
                    "allowed_actions": ["inspect_context"],
                    "transition_guards": [],
                },
            },
        )

    monkeypatch.setattr(workbench._orchestrator, "run", _stub_run)

    payload = workbench.run(
        task_id="product-run-1",
        task="Apply a narrow demo fix.",
        target_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["python3 -c \"print('ok')\""],
    )

    assert payload.runner == "run"
    assert payload.content == "Implemented the narrow demo fix."
    assert payload.session["status"] == "completed"
    assert payload.canonical_views["task_state"]["validation_ok"] is True
    assert payload.canonical_views["task_state"]["status"] == "completed"
    assert payload.controller_action_bar == {
        "task_id": "product-run-1",
        "status": "completed",
        "recommended_command": "/show product-run-1",
        "allowed_commands": ["/show product-run-1"],
    }
    assert payload.aionis["complete"]["status"] == "ok"


def test_product_run_persists_structured_host_delegation_returns(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-run-multi-agent")

    class _FakeTaskSession:
        def __init__(self) -> None:
            self._state = {"status": "active", "allowed_actions": ["inspect_context", "pause", "complete"], "transition_guards": []}

        def snapshot_state(self) -> dict[str, object]:
            return dict(self._state)

        def plan_task_start(self, **_: object) -> dict[str, object]:
            return {
                "first_action": {"selected_tool": "edit", "next_action": "Start with a narrow investigation."},
                "decision": {"planner_explanation": "Use the learned repair loop.", "task_family": "task:repair_demo"},
                "task_context": {
                    "delegation_learning": {
                        "learning_summary": {
                            "task_family": "task:repair_demo",
                            "matched_records": 2,
                            "recommendation_count": 1,
                        }
                    }
                },
            }

        def complete_task(self, **_: object) -> dict[str, object]:
            self._state = {"status": "completed", "allowed_actions": ["inspect_context"], "transition_guards": []}
            return {"status": "ok", "replay_run_id": "replay-run-1"}

    monkeypatch.setattr(
        workbench._orchestrator._runtime_host,
        "open_task_session",
        lambda **_: _FakeTaskSession(),
    )
    monkeypatch.setattr(workbench._orchestrator._execution_host, "build_agent", lambda **_: object())
    monkeypatch.setattr(
        workbench._orchestrator._execution_host,
        "invoke",
        lambda *_args, **_kwargs: {
            "final_output": "[investigator] Narrowed src/demo.py\n[implementer] Patched src/demo.py\n[verifier] Validation passed.",
            "role_sequence": ["investigator", "implementer", "verifier"],
            "delegation_returns": [
                {
                    "role": "investigator",
                    "status": "success",
                    "summary": "Narrowed src/demo.py",
                    "evidence": ["Root cause isolated to export handling."],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "handoff_target": "implementer",
                    "next_action": "Hand off to implementer and keep the implementation inside src/demo.py.",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
                {
                    "role": "implementer",
                    "status": "success",
                    "summary": "Patched src/demo.py",
                    "evidence": ["Touched src/demo.py."],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "artifact_refs": [".aionis-workbench/artifacts/investigator.json"],
                    "handoff_target": "verifier",
                    "next_action": "Hand off to verifier and run targeted validation: python3 -c \"print('ok')\"",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
                {
                    "role": "verifier",
                    "status": "success",
                    "summary": "Validation passed.",
                    "evidence": ["Command: python3 -c \"print('ok')\""],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "handoff_target": "orchestrator",
                    "next_action": "Report the validated fix back to the orchestrator and keep the task ready for completion.",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
            ],
        },
    )

    payload = workbench.run(
        task_id="product-run-multi-agent-1",
        task="Repair the demo export path.",
        target_files=["src", "README.md"],
        validation_commands=["python3 -c \"print('ok')\""],
    )

    assert payload.session["selected_role_sequence"] == ["investigator", "implementer", "verifier"]
    assert [item["role"] for item in payload.session["delegation_returns"]] == ["investigator", "implementer", "verifier"]
    assert payload.session["delegation_returns"][0]["summary"] == "Narrowed src/demo.py"
    assert payload.session["delegation_returns"][2]["summary"] == "Validation passed."
    assert payload.session["delegation_returns"][0]["handoff_text"].startswith("investigator summary:")
    assert payload.session["delegation_returns"][0]["handoff_target"] == "implementer"
    assert payload.session["delegation_returns"][1]["next_action"].startswith("Hand off to verifier")
    assert payload.session["delegation_returns"][2]["validation_intent"] == ['python3 -c "print(\'ok\')"']
    implementer_packet = next(item for item in payload.session["delegation_packets"] if item["role"] == "implementer")
    assert implementer_packet["working_set"] == ["src/demo.py"]
    assert any(item.endswith("/investigator.json") for item in implementer_packet["preferred_artifact_refs"])
    collaboration_kinds = {item["kind"] for item in payload.session["collaboration_patterns"]}
    assert "effective_edit_scope_strategy" in collaboration_kinds
    assert {"artifact_scope_strategy", "artifact_routing_strategy"} & collaboration_kinds
    assert payload.canonical_views["task_state"]["status"] == "completed"
    assert payload.canonical_views["controller"]["status"] == "completed"
    assert payload.canonical_views["routing"]["summary"]["implementer_effective_scope"] == ["src/demo.py"]
    assert payload.canonical_views["routing"]["summary"]["implementer_artifact_scope"] == [
        ".aionis-workbench/artifacts/investigator.json"
    ]
    assert payload.canonical_views["routing"]["summary"]["implementer_scope_narrowed"] is True
    assert payload.canonical_views["routing"]["summary"]["implementer_scope_source"] == "investigator_narrowed"
    assert payload.canonical_views["routing"]["summary"]["specialist_handoff_chain"] == [
        "investigator->implementer",
        "implementer->verifier",
        "verifier->orchestrator",
    ]
    assert payload.canonical_views["routing"]["summary"]["specialist_next_actions"][1].startswith(
        "implementer: Hand off to verifier"
    )
    assert payload.canonical_views["routing"]["summary"]["verifier_validation_intent"] == ['python3 -c "print(\'ok\')"']
    assert payload.session["continuity_snapshot"]["implementer_effective_scope"] == ["src/demo.py"]
    assert any(
        item.endswith("/investigator.json")
        for item in payload.session["continuity_snapshot"]["implementer_artifact_scope"]
    )
    assert payload.session["continuity_snapshot"]["implementer_scope_source"] == "investigator_narrowed"
    assert payload.session["continuity_snapshot"]["specialist_handoff_chain"] == [
        "investigator->implementer",
        "implementer->verifier",
        "verifier->orchestrator",
    ]
    assert payload.session["continuity_snapshot"]["verifier_validation_intent"] == ['python3 -c "print(\'ok\')"']


def test_product_run_blocks_completion_when_verifier_reports_failure(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-run-verifier-gate")

    session = workbench._initial_session(
        task_id="product-run-verifier-gate-1",
        task="Repair the demo export path.",
        target_files=["src/demo.py"],
        validation_commands=["python3 -m pytest -q"],
        apply_strategy=False,
    )
    session.status = "running"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    session.delegation_returns = [
        DelegationReturn(role="investigator", status="success", summary="Narrowed src/demo.py", handoff_text="investigator summary: narrowed"),
        DelegationReturn(role="implementer", status="success", summary="Patched src/demo.py", handoff_text="implementer summary: patched"),
        DelegationReturn(role="verifier", status="error", summary="Validation failed on the targeted check.", handoff_text="verifier summary: failed"),
    ]
    session.last_validation_result = {
        "ok": False,
        "command": "python3 -m pytest -q",
        "exit_code": 1,
        "summary": "Validation failed on the targeted check.",
        "output": "FAILED tests/test_demo.py",
        "changed_files": ["src/demo.py"],
    }
    session_path = workbench._save_session(session)

    def _stub_run(**_: object) -> OrchestrationResult:
        return OrchestrationResult(
            task_id="product-run-verifier-gate-1",
            runner="run",
            content="Validation failed on the targeted check.",
            session=session,
            session_path=session_path,
            aionis={
                "task_session_state": {
                    "status": "active",
                    "allowed_actions": ["inspect_context", "plan_start", "pause", "complete"],
                    "transition_guards": [],
                },
            },
        )

    monkeypatch.setattr(workbench._orchestrator, "run", _stub_run)

    payload = workbench.run(
        task_id="product-run-verifier-gate-1",
        task="Repair the demo export path.",
        target_files=["src/demo.py"],
        validation_commands=["python3 -m pytest -q"],
    )

    controller = payload.canonical_views["controller"]
    assert controller["status"] == "active"
    assert controller["allowed_actions"] == ["inspect_context", "plan_start", "pause"]
    assert "complete" in controller["blocked_actions"]
    assert {
        "action": "complete",
        "reason": "Validation failed on the targeted check.",
    } in controller["guard_reasons"]
    assert payload.controller_action_bar == {
        "task_id": "product-run-verifier-gate-1",
        "status": "active",
        "recommended_command": "/next product-run-verifier-gate-1",
        "allowed_commands": [
            "/next product-run-verifier-gate-1",
            "/show product-run-verifier-gate-1",
        ],
    }


def test_product_session_surfaces_block_completion_when_verifier_reports_failure(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-session-verifier-gate")
    session = workbench._initial_session(
        task_id="product-session-verifier-gate-1",
        task="Repair the demo export path.",
        target_files=["src/demo.py"],
        validation_commands=["python3 -m pytest -q"],
        apply_strategy=False,
    )
    session.status = "running"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    session.delegation_returns = [
        DelegationReturn(role="verifier", status="error", summary="Validation failed on the targeted check.", handoff_text="verifier summary: failed"),
    ]
    session.last_validation_result = {
        "ok": False,
        "command": "python3 -m pytest -q",
        "exit_code": 1,
        "summary": "Validation failed on the targeted check.",
        "output": "FAILED tests/test_demo.py",
        "changed_files": ["src/demo.py"],
    }
    workbench._save_session(session)

    inspected = workbench.inspect_session(task_id="product-session-verifier-gate-1")
    evaluated = workbench.evaluate_session(task_id="product-session-verifier-gate-1")
    status = workbench.shell_status(task_id="product-session-verifier-gate-1")

    expected_bar = {
        "task_id": "product-session-verifier-gate-1",
        "status": "active",
        "recommended_command": "/next product-session-verifier-gate-1",
        "allowed_commands": [
            "/next product-session-verifier-gate-1",
            "/show product-session-verifier-gate-1",
            "/session product-session-verifier-gate-1",
        ],
    }

    for payload in (inspected, evaluated, status):
        controller = payload["canonical_views"]["controller"] if "canonical_views" in payload else payload["controller"]
        assert controller["allowed_actions"] == ["list_events", "inspect_context", "record_event", "plan_start", "pause"]
        assert "complete" in controller["blocked_actions"]
        assert {
            "action": "complete",
            "reason": "Validation failed on the targeted check.",
        } in controller["guard_reasons"]

    assert inspected["controller_action_bar"] == expected_bar
    assert evaluated["controller_action_bar"] == expected_bar
    assert status["controller_action_bar"] == expected_bar


def test_product_inspect_session_uses_specialist_handoff_for_execution_packet_next_action(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-session-specialist-next-action")
    retry_command = "python3 -m pytest tests/test_demo.py -q"
    session = workbench._initial_session(
        task_id="product-session-specialist-next-action-1",
        task="Repair the demo export path.",
        target_files=["src", "README.md"],
        validation_commands=["python3 -m pytest -q"],
        apply_strategy=False,
    )
    session.status = "running"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    session.strategy_summary = StrategySummary(
        selected_working_set=["src/demo.py"],
        selected_validation_paths=[retry_command],
        specialist_recommendation=(
            "Follow the specialist handoff back to implementer inside src/demo.py, "
            f"then rerun {retry_command}."
        ),
    )
    session.routing_signal_summary = RoutingSignalSummary(
        implementer_effective_scope=["src/demo.py"],
        verifier_blockers=["Blocker: export path still mismatched"],
        verifier_validation_intent=[retry_command],
    )
    session.delegation_returns = [
        DelegationReturn(
            role="implementer",
            status="success",
            summary="Patched src/demo.py",
            working_set=["src/demo.py"],
            next_action=f"Hand off to verifier and run targeted validation: {retry_command}",
        ),
        DelegationReturn(
            role="verifier",
            status="error",
            summary="Validation failed on the targeted check.",
            blockers=["Blocker: export path still mismatched"],
            validation_intent=[retry_command],
            handoff_target="implementer",
            next_action=f"Hand off to implementer and rerun the narrow fix loop before validating again: {retry_command}",
        ),
    ]
    session.last_validation_result = {
        "ok": False,
        "command": retry_command,
        "exit_code": 1,
        "summary": "Validation failed on the targeted check.",
        "output": "FAILED tests/test_demo.py",
        "changed_files": ["src/demo.py"],
    }
    save_session(session)

    payload = workbench.inspect_session(task_id="product-session-specialist-next-action-1")

    assert payload["canonical_surface"]["execution_packet"]["next_action"] == (
        "Follow verifier handoff to implementer inside src/demo.py to address "
        "Blocker: export path still mismatched, then rerun python3 -m pytest tests/test_demo.py -q."
    )
    assert payload["canonical_views"]["strategy"]["specialist_recommendation"].startswith(
        "Follow the specialist handoff back to implementer inside src/demo.py"
    )


def test_product_run_preserves_specialist_retry_handoff_graph(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-run-handoff-graph")

    class _FakeTaskSession:
        def __init__(self) -> None:
            self._state = {
                "status": "active",
                "allowed_actions": ["record_event", "pause", "plan_start", "complete", "inspect_context"],
                "transition_guards": [],
            }

        def snapshot_state(self) -> dict[str, object]:
            return dict(self._state)

        def inspect_task_context(self, **_: object) -> dict[str, object]:
            return {"operator_projection": None, "delegation_learning": None, "planning_context": {}}

        def plan_task_start(self, **_: object) -> dict[str, object]:
            return {
                "first_action": {"selected_tool": "edit", "next_action": "Start with a narrow investigation."},
                "decision": {"planner_explanation": "Use the learned repair loop.", "task_family": "task:repair_demo"},
                "task_context": {},
            }

        def complete_task(self, **_: object) -> dict[str, object]:
            self._state = {"status": "completed", "allowed_actions": ["inspect_context"], "transition_guards": []}
            return {"status": "ok", "replay_run_id": "replay-run-graph-1"}

    monkeypatch.setattr(
        workbench._orchestrator._runtime_host,
        "open_task_session",
        lambda **_: _FakeTaskSession(),
    )
    monkeypatch.setattr(workbench._orchestrator._execution_host, "build_agent", lambda **_: object())
    monkeypatch.setattr(
        workbench._orchestrator._execution_host,
        "invoke",
        lambda *_args, **_kwargs: {
            "final_output": "[investigator] Narrowed src/demo.py\n[implementer] Tentative patch\n[verifier] Validation failed.\n[implementer] Refined patch\n[verifier] Validation passed.",
            "role_sequence": ["investigator", "implementer", "verifier", "implementer", "verifier"],
            "delegation_returns": [
                {
                    "role": "investigator",
                    "status": "success",
                    "summary": "Narrowed src/demo.py",
                    "evidence": ["Root cause isolated to export handling."],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "handoff_target": "implementer",
                    "next_action": "Hand off to implementer and keep the implementation inside src/demo.py.",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
                {
                    "role": "implementer",
                    "status": "success",
                    "summary": "Applied a tentative fix in src/demo.py",
                    "evidence": ["Touched src/demo.py."],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "artifact_refs": [".aionis-workbench/artifacts/investigator.json"],
                    "handoff_target": "verifier",
                    "next_action": "Hand off to verifier and run targeted validation: python3 -c \"print('ok')\"",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
                {
                    "role": "verifier",
                    "status": "error",
                    "summary": "Validation failed.",
                    "evidence": ["Command: python3 -c \"print('ok')\"", "Blocker: export path still mismatched"],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "handoff_target": "implementer",
                    "next_action": "Hand off to implementer and rerun the narrow fix loop before validating again: python3 -c \"print('ok')\"",
                    "blockers": ["Blocker: export path still mismatched"],
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
                {
                    "role": "implementer",
                    "status": "success",
                    "summary": "Refined the fix in src/demo.py",
                    "evidence": ["Adjusted export handling in src/demo.py."],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "artifact_refs": [".aionis-workbench/artifacts/investigator.json"],
                    "handoff_target": "verifier",
                    "next_action": "Hand off to verifier and run targeted validation: python3 -c \"print('ok')\"",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
                {
                    "role": "verifier",
                    "status": "success",
                    "summary": "Validation passed.",
                    "evidence": ["Command: python3 -c \"print('ok')\""],
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -c \"print('ok')\""],
                    "handoff_target": "orchestrator",
                    "next_action": "Report the validated fix back to the orchestrator and keep the task ready for completion.",
                    "validation_intent": ["python3 -c \"print('ok')\""],
                },
            ],
        },
    )

    payload = workbench.run(
        task_id="product-run-handoff-graph-1",
        task="Repair the demo export path.",
        target_files=["src", "README.md"],
        validation_commands=["python3 -c \"print('ok')\""],
    )

    assert [item["role"] for item in payload.session["delegation_returns"]] == [
        "investigator",
        "implementer",
        "verifier",
        "implementer",
        "verifier",
    ]
    assert payload.canonical_views["routing"]["summary"]["specialist_handoff_chain"] == [
        "investigator->implementer",
        "implementer->verifier",
        "verifier->implementer",
        "implementer->verifier",
        "verifier->orchestrator",
    ]
    assert payload.session["continuity_snapshot"]["specialist_handoff_chain"] == [
        "investigator->implementer",
        "implementer->verifier",
        "verifier->implementer",
        "implementer->verifier",
        "verifier->orchestrator",
    ]
    assert payload.canonical_views["task_state"]["status"] == "completed"
    assert payload.canonical_views["controller"]["status"] == "completed"


def test_product_runtime_ship_routes_existing_project_tasks_to_run(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-ship-run-route")

    def _fake_run(
        *,
        task_id: str,
        task: str,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
    ) -> WorkbenchRunResult:
        assert task_id == "product-ship-run-route-1"
        assert task == "Fix the failing demo validation."
        assert target_files == ["src/demo.py"]
        assert validation_commands == ["python3 -m pytest tests/test_demo.py -q"]
        return WorkbenchRunResult(
            task_id=task_id,
            runner="run",
            content="Implemented the narrow demo fix.",
            session_path=str(tmp_path / ".aionis-workbench" / "sessions" / "product-ship-run-route-1.json"),
            session={"status": "completed"},
            canonical_surface={"task": task},
            canonical_views={
                "task_state": {"status": "completed", "validation_ok": True},
                "planner": {"next_action": "none"},
                "instrumentation": {"status": "ready"},
            },
            controller_action_bar={
                "task_id": task_id,
                "status": "completed",
                "recommended_command": f"/show {task_id}",
                "allowed_commands": [f"/show {task_id}"],
            },
            aionis={"complete": {"status": "ok"}},
            trace_summary={"events": 0},
        )

    monkeypatch.setattr(workbench, "run", _fake_run)

    payload = workbench.ship(
        task_id="product-ship-run-route-1",
        task="Fix the failing demo validation.",
        target_files=["src/demo.py"],
        validation_commands=["python3 -m pytest tests/test_demo.py -q"],
    )

    assert payload["shell_view"] == "ship"
    assert payload["ship_mode"] == "project_workflow"
    assert payload["delegated_shell_view"] == "run"
    assert payload["route_summary"] == "task_intake->context_scan->route->run"
    assert "target files" in payload["route_reason"]
    assert payload["controller_action_bar"]["recommended_command"] == "/show product-ship-run-route-1"
    assert "existing-project task" in payload["route_reason"]
    assert payload["runner"] == "run"
    assert payload["canonical_views"]["task_state"]["validation_ok"] is True


def test_product_resume_hydrates_runtime_review_packs(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-runtime-review-packs")
    session = workbench._initial_session(
        task_id="product-runtime-review-1",
        task="Resume a paused task and hydrate runtime reviewer packs.",
        target_files=["src/demo.py"],
        validation_commands=["true"],
        apply_strategy=False,
    )
    session.status = "paused"
    workbench._save_session(session)

    class _FakeTaskSession:
        def __init__(self) -> None:
            self._state = {"status": "active", "allowed_actions": ["resume"], "transition_guards": []}

        def snapshot_state(self) -> dict[str, object]:
            return dict(self._state)

        def resume_task(self, *, repo_root: str, **_: object) -> dict[str, object]:
            assert repo_root == str(tmp_path)
            self._state = {"status": "resumed", "allowed_actions": ["inspect_context", "pause", "complete"], "transition_guards": []}
            return {
                "handoff": {
                    "handoff": {
                        "summary": "Resume task",
                        "handoff_text": "Continue from the latest fix attempt.",
                        "execution_ready_handoff": {
                            "next_action": "Re-run the narrow validation command.",
                            "repo_root": str(tmp_path),
                            "target_files": ["src/demo.py"],
                        },
                    }
                }
            }

        def inspect_task_context(self, **_: object) -> dict[str, object]:
            return {
                "planning_context": {
                    "planning_summary": {
                        "planner_explanation": "Resume through the learned narrow repair route.",
                    }
                },
                "delegation_learning": {
                    "learning_summary": {
                        "task_family": "task:repair_demo",
                        "matched_records": 2,
                        "recommendation_count": 1,
                    }
                },
            }

        def complete_task(self, **_: object) -> dict[str, object]:
            self._state = {"status": "completed", "allowed_actions": ["inspect_context"], "transition_guards": []}
            return {"status": "ok"}

    monkeypatch.setattr(
        workbench._orchestrator._runtime_host,
        "open_task_session",
        lambda **_: _FakeTaskSession(),
    )
    monkeypatch.setattr(
        workbench._orchestrator._runtime_host,
        "continuity_review_pack",
        lambda **_: {
            "payload": {
                "continuity_review_pack": {
                    "pack_version": "continuity_review_pack_v1",
                    "review_contract": {
                        "target_files": ["src/demo.py"],
                        "next_action": "Verify the patch against the reviewer contract.",
                        "acceptance_checks": ["true"],
                        "rollback_required": False,
                    },
                    "latest_handoff": {"anchor": "resume:src/demo.py", "file_path": "src/demo.py"},
                    "recovered_handoff": {"anchor": "resume:src/demo.py", "file_path": "src/demo.py"},
                }
            }
        },
    )
    monkeypatch.setattr(
        workbench._orchestrator._runtime_host,
        "evolution_review_pack",
        lambda **_: {
            "payload": {
                "evolution_review_pack": {
                    "pack_version": "evolution_review_pack_v1",
                    "review_contract": {
                        "selected_tool": "edit",
                        "file_path": "src/demo.py",
                        "target_files": ["src/demo.py"],
                        "next_action": "Patch src/demo.py and rerun tests.",
                    },
                    "stable_workflow": {"anchor_id": "workflow-anchor-1"},
                }
            }
        },
    )
    monkeypatch.setattr(workbench._orchestrator._execution_host, "build_agent", lambda **_: object())
    monkeypatch.setattr(
        workbench._orchestrator._execution_host,
        "invoke",
        lambda *_args, **_kwargs: "Resumed successfully with runtime reviewer packs.",
    )

    payload = workbench.resume(task_id="product-runtime-review-1")

    assert payload.session["continuity_review_pack"]["pack_version"] == "continuity_review_pack_v1"
    assert payload.session["evolution_review_pack"]["pack_version"] == "evolution_review_pack_v1"
    assert payload.canonical_views["review_packs"]["continuity"]["pack_version"] == "continuity_review_pack_v1"
    assert payload.canonical_views["review_packs"]["evolution"]["selected_tool"] == "edit"
    assert payload.canonical_views["controller"]["status"] == "completed"
    assert payload.canonical_views["controller"]["allowed_actions"] == ["inspect_context"]
    assert payload.controller_action_bar == {
        "task_id": "product-runtime-review-1",
        "status": "completed",
        "recommended_command": "/show product-runtime-review-1",
        "allowed_commands": ["/show product-runtime-review-1"],
    }
    assert payload.aionis["task_session_state"]["status"] == "completed"
    assert payload.aionis["task_context"]["delegation_learning"]["learning_summary"]["task_family"] == "task:repair_demo"


def test_product_resume_explicit_validation_command_overrides_failed_chain(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-resume-validation-override")
    session = workbench._initial_session(
        task_id="product-resume-override-1",
        task="Resume a previously paused task with a new validation command.",
        target_files=["src/demo.py"],
        validation_commands=["false"],
        apply_strategy=False,
    )
    session.status = "paused"
    workbench._save_session(session)

    class _FakeTaskSession:
        def __init__(self) -> None:
            self._state = {"status": "active", "allowed_actions": ["resume"], "transition_guards": []}

        def snapshot_state(self) -> dict[str, object]:
            return dict(self._state)

        def resume_task(self, **_: object) -> dict[str, object]:
            self._state = {"status": "resumed", "allowed_actions": ["inspect_context", "pause", "complete"], "transition_guards": []}
            return {}

        def inspect_task_context(self, **_: object) -> dict[str, object]:
            return {
                "planning_context": {
                    "planning_summary": {
                        "planner_explanation": "Resume with the replacement validation command.",
                    }
                },
                "delegation_learning": {
                    "learning_summary": {
                        "task_family": "task:validation_override",
                        "matched_records": 1,
                        "recommendation_count": 1,
                    }
                },
            }

        def complete_task(self, **_: object) -> dict[str, object]:
            self._state = {"status": "completed", "allowed_actions": ["inspect_context"], "transition_guards": []}
            return {"status": "ok"}

    monkeypatch.setattr(
        workbench._orchestrator._runtime_host,
        "open_task_session",
        lambda **_: _FakeTaskSession(),
    )
    monkeypatch.setattr(workbench._orchestrator._execution_host, "build_agent", lambda **_: object())
    monkeypatch.setattr(
        workbench._orchestrator._execution_host,
        "invoke",
        lambda *_args, **_kwargs: "Resumed successfully with the replacement validation command.",
    )

    payload = workbench.resume(
        task_id="product-resume-override-1",
        validation_commands=["true"],
    )

    assert payload.runner == "resume"
    assert payload.session["status"] == "completed"
    assert payload.session["validation_commands"] == ["true"]
    assert payload.canonical_views["controller"]["status"] == "completed"
    assert payload.aionis["validation"]["ok"] is True
    assert payload.aionis["validation"]["command"] == "true"
    assert payload.aionis["task_session_state"]["status"] == "completed"
    assert payload.canonical_views["task_state"]["validation_ok"] is True
    assert payload.controller_action_bar == {
        "task_id": "product-resume-override-1",
        "status": "completed",
        "recommended_command": "/show product-resume-override-1",
        "allowed_commands": ["/show product-resume-override-1"],
    }


def test_product_validate_success_persists_auto_learning(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-validate")
    session = workbench._initial_session(
        task_id="product-validate-1",
        task="Close one narrow validation loop.",
        target_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["python3 -c \"print('ok')\""],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    workbench._save_session(session)

    payload = workbench.validate_session(task_id="product-validate-1")
    inspected = workbench.inspect_session(task_id="product-validate-1")
    status = workbench.shell_status(task_id="product-validate-1")
    learning_payload = json.loads(auto_learning_path(str(tmp_path)).read_text())

    assert payload["validation"]["ok"] is True
    assert payload["controller_action_bar"] == {
        "task_id": "product-validate-1",
        "status": "completed",
        "recommended_command": "/show product-validate-1",
        "allowed_commands": ["/show product-validate-1", "/session product-validate-1"],
    }
    assert inspected["canonical_views"]["maintenance"]["auto_learning_status"] == "auto_absorbed"
    assert inspected["canonical_views"]["maintenance"]["last_learning_source"] == "validate"
    assert learning_payload["recent_samples"][0]["task_id"] == "product-validate-1"
    assert learning_payload["recent_samples"][0]["source"] == "validate"
    assert status["task_id"] == "product-validate-1"
    assert status["dashboard_summary"]["status"] == "ready"


def test_product_validate_prefers_reviewer_acceptance_checks(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-reviewer-gate")
    session = workbench._initial_session(
        task_id="product-reviewer-gate-1",
        task="Validate only against the reviewer contract acceptance check.",
        target_files=["src/demo.py"],
        validation_commands=["false"],
        apply_strategy=False,
    )
    session.status = "paused"
    session.continuity_review_pack = ReviewPackSummary(
        pack_version="continuity_review_pack_v1",
        source="continuity",
        review_contract=ReviewerContract(
            standard="strict_review",
            required_outputs=["patch", "tests"],
            acceptance_checks=["true"],
            rollback_required=False,
        ),
        selected_tool="read",
        file_path="src/demo.py",
        target_files=["src/demo.py"],
        next_action="Verify the patch against the reviewer contract.",
        recovered_handoff={"anchor": "resume:src/demo.py"},
    )
    save_session(session)

    payload = workbench.validate_session(task_id="product-reviewer-gate-1")

    assert payload["validation"]["ok"] is True
    assert payload["validation"]["command"] == "true"
    assert payload["controller_action_bar"] == {
        "task_id": "product-reviewer-gate-1",
        "status": "completed",
        "recommended_command": "/show product-reviewer-gate-1",
        "allowed_commands": ["/show product-reviewer-gate-1", "/session product-reviewer-gate-1"],
    }
    assert payload["reviewer_gate"]["gated_validation"] is True
    assert payload["reviewer_gate"]["acceptance_checks"] == ["true"]


def test_product_shell_status_projects_controller_actions(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-controller-status")
    session = workbench._initial_session(
        task_id="product-controller-status-1",
        task="Resume the paused session using controller-visible actions.",
        target_files=["src/demo.py"],
        validation_commands=["true"],
        apply_strategy=False,
    )
    session.status = "paused"
    save_session(session)

    status = workbench.shell_status(task_id="product-controller-status-1")
    inspected = workbench.inspect_session(task_id="product-controller-status-1")
    evaluated = workbench.evaluate_session(task_id="product-controller-status-1")

    assert status["controller"]["status"] == "paused"
    assert status["controller"]["projection_source"] == "session_status"
    assert status["controller_action_bar"]["status"] == "paused"
    assert status["controller_action_bar"]["recommended_command"] == "/resume product-controller-status-1"
    assert status["controller_action_bar"]["allowed_commands"] == [
        "/resume product-controller-status-1",
        "/show product-controller-status-1",
        "/session product-controller-status-1",
    ]
    assert inspected["controller_action_bar"] == status["controller_action_bar"]
    assert evaluated["controller_action_bar"] == status["controller_action_bar"]
    assert status["status_line"]["controller_status"] == "paused"
    assert status["status_line"]["controller_allowed_actions"] == ["list_events", "inspect_context", "resume"]
    assert status["status_line"]["controller_blocked_actions"][:2] == ["record_event", "plan_start"]
    assert "controller:paused[list_events,inspect_context,resume]" in status["text"]
    assert "blocked:record_event,plan_start" in status["text"]


def test_product_controller_action_bar_stays_consistent_across_task_scoped_surfaces(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-cross-surface")
    session = workbench._initial_session(
        task_id="product-cross-surface-1",
        task="Keep controller guidance consistent across app and doc surfaces.",
        target_files=["flows/workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)
    (tmp_path / "flows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "flows" / "workflow.aionis.md").write_text("# workflow\n", encoding="utf-8")

    plan_payload = workbench.app_plan(
        task_id="product-cross-surface-1",
        prompt="Build a compact planning shell.",
    )
    doc_event_payload = workbench.doc_event(
        task_id="product-cross-surface-1",
        event={
            "event_version": "aionisdoc_workbench_event_v1",
            "event_source": "cursor_extension",
            "task_id": "product-cross-surface-1",
            "doc_action": "publish",
            "doc_input": "flows/workflow.aionis.md",
            "status": "completed",
            "payload": {
                "shell_view": "doc_publish",
                "doc_action": "publish",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
                "publish_result": {
                    "publish_result_version": "aionis_doc_publish_result_v1",
                    "source_doc_id": "workflow-cross-1",
                    "request": {"anchor": "cross-anchor", "handoff_kind": "doc_runtime_handoff"},
                    "response": {"handoff_anchor": "cross-anchor", "handoff_kind": "doc_runtime_handoff"},
                },
            },
        },
    )

    expected = {
        "task_id": "product-cross-surface-1",
        "status": "active",
        "recommended_command": "/next product-cross-surface-1",
        "allowed_commands": [
            "/next product-cross-surface-1",
            "/show product-cross-surface-1",
            "/session product-cross-surface-1",
        ],
    }

    status = workbench.shell_status(task_id="product-cross-surface-1")
    inspected = workbench.inspect_session(task_id="product-cross-surface-1")
    evaluated = workbench.evaluate_session(task_id="product-cross-surface-1")
    app_show = workbench.app_show(task_id="product-cross-surface-1")
    doc_inspect = workbench.doc_inspect(target="flows/workflow.aionis.md", limit=8)
    doc_list = workbench.doc_list(limit=8)
    workflow_row = next(item for item in doc_list["docs"] if item["path"] == "flows/workflow.aionis.md")

    assert plan_payload["controller_action_bar"] == expected
    assert doc_event_payload["controller_action_bar"] == expected
    assert status["controller_action_bar"] == expected
    assert inspected["controller_action_bar"] == expected
    assert evaluated["controller_action_bar"] == expected
    assert app_show["controller_action_bar"] == expected
    assert doc_inspect["controller_action_bar"] == expected
    assert workflow_row["controller_action_bar"] == expected


def test_product_paused_controller_action_bar_stays_consistent_across_task_scoped_surfaces(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-cross-paused")
    session = workbench._initial_session(
        task_id="product-cross-paused-1",
        task="Keep paused controller guidance consistent across app and doc surfaces.",
        target_files=["flows/workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    session.status = "paused"
    workbench._save_session(session)
    (tmp_path / "flows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "flows" / "workflow.aionis.md").write_text("# workflow\n", encoding="utf-8")

    doc_event_payload = workbench.doc_event(
        task_id="product-cross-paused-1",
        event={
            "event_version": "aionisdoc_workbench_event_v1",
            "event_source": "cursor_extension",
            "task_id": "product-cross-paused-1",
            "doc_action": "publish",
            "doc_input": "flows/workflow.aionis.md",
            "status": "completed",
            "payload": {
                "shell_view": "doc_publish",
                "doc_action": "publish",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
                "publish_result": {
                    "publish_result_version": "aionis_doc_publish_result_v1",
                    "source_doc_id": "workflow-cross-paused-1",
                    "request": {"anchor": "cross-paused-anchor", "handoff_kind": "doc_runtime_handoff"},
                    "response": {"handoff_anchor": "cross-paused-anchor", "handoff_kind": "doc_runtime_handoff"},
                },
            },
        },
    )

    expected = {
        "task_id": "product-cross-paused-1",
        "status": "paused",
        "recommended_command": "/resume product-cross-paused-1",
        "allowed_commands": [
            "/resume product-cross-paused-1",
            "/show product-cross-paused-1",
            "/session product-cross-paused-1",
        ],
    }

    status = workbench.shell_status(task_id="product-cross-paused-1")
    inspected = workbench.inspect_session(task_id="product-cross-paused-1")
    evaluated = workbench.evaluate_session(task_id="product-cross-paused-1")
    app_show = workbench.app_show(task_id="product-cross-paused-1")
    doc_inspect = workbench.doc_inspect(target="flows/workflow.aionis.md", limit=8)
    doc_list = workbench.doc_list(limit=8)
    workflow_row = next(item for item in doc_list["docs"] if item["path"] == "flows/workflow.aionis.md")

    assert doc_event_payload["controller_action_bar"] == expected
    assert status["controller_action_bar"] == expected
    assert inspected["controller_action_bar"] == expected
    assert evaluated["controller_action_bar"] == expected
    assert app_show["controller_action_bar"] == expected
    assert doc_inspect["controller_action_bar"] == expected
    assert workflow_row["controller_action_bar"] == expected


def test_product_completed_controller_action_bar_stays_consistent_across_task_scoped_surfaces(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-cross-completed")
    session = workbench._initial_session(
        task_id="product-cross-completed-1",
        task="Keep completed controller guidance consistent across app and doc surfaces.",
        target_files=["flows/workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    session.status = "completed"
    workbench._save_session(session)
    (tmp_path / "flows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "flows" / "workflow.aionis.md").write_text("# workflow\n", encoding="utf-8")

    doc_event_payload = workbench.doc_event(
        task_id="product-cross-completed-1",
        event={
            "event_version": "aionisdoc_workbench_event_v1",
            "event_source": "cursor_extension",
            "task_id": "product-cross-completed-1",
            "doc_action": "publish",
            "doc_input": "flows/workflow.aionis.md",
            "status": "completed",
            "payload": {
                "shell_view": "doc_publish",
                "doc_action": "publish",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
                "publish_result": {
                    "publish_result_version": "aionis_doc_publish_result_v1",
                    "source_doc_id": "workflow-cross-completed-1",
                    "request": {"anchor": "cross-completed-anchor", "handoff_kind": "doc_runtime_handoff"},
                    "response": {"handoff_anchor": "cross-completed-anchor", "handoff_kind": "doc_runtime_handoff"},
                },
            },
        },
    )

    expected = {
        "task_id": "product-cross-completed-1",
        "status": "completed",
        "recommended_command": "/show product-cross-completed-1",
        "allowed_commands": [
            "/show product-cross-completed-1",
            "/session product-cross-completed-1",
        ],
    }

    status = workbench.shell_status(task_id="product-cross-completed-1")
    inspected = workbench.inspect_session(task_id="product-cross-completed-1")
    evaluated = workbench.evaluate_session(task_id="product-cross-completed-1")
    app_show = workbench.app_show(task_id="product-cross-completed-1")
    doc_inspect = workbench.doc_inspect(target="flows/workflow.aionis.md", limit=8)
    doc_list = workbench.doc_list(limit=8)
    workflow_row = next(item for item in doc_list["docs"] if item["path"] == "flows/workflow.aionis.md")

    assert doc_event_payload["controller_action_bar"] == expected
    assert status["controller_action_bar"] == expected
    assert inspected["controller_action_bar"] == expected
    assert evaluated["controller_action_bar"] == expected
    assert app_show["controller_action_bar"] == expected
    assert doc_inspect["controller_action_bar"] == expected
    assert workflow_row["controller_action_bar"] == expected


def test_product_ingest_external_work_surfaces_recorded_learning(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-ingest")

    payload = workbench.ingest(
        task_id="product-ingest-1",
        task="Record a validated external testing task.",
        summary="Recorded a validated external task into project continuity.",
        target_files=["src/demo.py", "tests/test_demo.py"],
        changed_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        validation_ok=True,
        validation_summary="Validation commands passed.",
    )
    inspected = workbench.inspect_session(task_id="product-ingest-1")
    evaluated = workbench.evaluate_session(task_id="product-ingest-1")
    status = workbench.shell_status(task_id="product-ingest-1")

    assert payload.runner == "ingest"
    assert inspected["canonical_views"]["maintenance"]["auto_learning_status"] == "recorded"
    assert inspected["canonical_views"]["maintenance"]["last_learning_source"] == "manual_ingest"
    assert inspected["canonical_views"]["continuity"]["learning"]["source"] == "manual_ingest"
    assert evaluated["evaluation"]["status"] in {"ready", "in_progress"}
    assert status["task_id"] == "product-ingest-1"
    assert status["dashboard_summary"]["status"] == "ready"


def test_product_backfill_restores_legacy_session_surfaces(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-backfill")
    legacy = workbench._initial_session(
        task_id="product-backfill-1",
        task="Restore a legacy validated session.",
        target_files=["src/demo.py"],
        validation_commands=["python3 -c \"print('ok')\""],
        apply_strategy=False,
    )
    legacy.project_identity = ""
    legacy.project_scope = ""
    legacy.status = "running"
    legacy.execution_packet = None
    legacy.execution_packet_summary = None
    legacy.planner_packet = None
    legacy.strategy_summary = None
    legacy.pattern_signal_summary = None
    legacy.workflow_signal_summary = None
    legacy.routing_signal_summary = None
    legacy.maintenance_summary = None
    legacy.instrumentation_summary = None
    legacy.continuity_snapshot = {}
    legacy.context_layers_snapshot = {}
    legacy.last_validation_result = {
        "ok": True,
        "command": "python3 -c \"print('ok')\"",
        "exit_code": 0,
        "summary": "Validation commands passed.",
        "output": "",
        "changed_files": ["src/demo.py"],
    }
    save_session(legacy)

    payload = workbench.backfill(task_id="product-backfill-1")

    assert payload["session"]["project_scope"] == workbench._config.project_scope
    assert payload["session"]["project_identity"] == workbench._config.project_identity
    assert payload["session"]["status"] == "validated"
    assert payload["canonical_surface"]["execution_packet"] is not None
    assert payload["canonical_views"]["task_state"]["validation_ok"] is True
    assert payload["canonical_views"]["strategy"]["task_family"]
    assert payload["controller_action_bar"] == {
        "task_id": "product-backfill-1",
        "status": "completed",
        "recommended_command": "/show product-backfill-1",
        "allowed_commands": ["/show product-backfill-1", "/session product-backfill-1"],
    }
    assert payload["evaluation"]["status"] in {"ready", "in_progress"}


def test_product_session_persists_reviewer_substrate(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-reviewer-persistence")
    session = workbench._initial_session(
        task_id="product-reviewer-1",
        task="Persist reviewer substrate across save and load.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    session.execution_packet = ExecutionPacket.from_dict(
        {
            "packet_version": 1,
            "current_stage": "review",
            "active_role": "review",
            "task_brief": session.goal,
            "target_files": ["src/demo.py"],
            "next_action": "Verify the patch against the reviewer contract.",
            "pending_validations": ["pytest -q"],
            "review_contract": {
                "standard": "strict",
                "required_outputs": ["patch", "tests"],
                "acceptance_checks": ["pytest -q"],
                "rollback_required": True,
            },
            "reviewer_ready_required": True,
            "resume_anchor": {
                "anchor": "resume:src/demo.py",
                "file_path": "src/demo.py",
                "repo_root": str(tmp_path),
            },
        }
    )
    session.execution_packet_summary = ExecutionPacketSummary.from_dict(
        {
            "packet_version": 1,
            "current_stage": "review",
            "active_role": "review",
            "task_brief": session.goal,
            "review_contract_present": True,
            "reviewer_ready_required": True,
            "resume_anchor_present": True,
        }
    )
    session.continuity_review_pack = ReviewPackSummary(
        pack_version="continuity_review_pack_v1",
        source="continuity",
        review_contract=ReviewerContract(
            standard="strict",
            required_outputs=["patch", "tests"],
            acceptance_checks=["pytest -q"],
            rollback_required=True,
        ),
        target_files=["src/demo.py"],
        next_action="Verify the patch against the reviewer contract.",
        recovered_handoff={"anchor": "resume:src/demo.py"},
        latest_handoff={"anchor": "resume:src/demo.py"},
    )
    session.evolution_review_pack = ReviewPackSummary(
        pack_version="evolution_review_pack_v1",
        source="evolution",
        review_contract=ReviewerContract(
            standard="strict",
            required_outputs=["patch"],
            acceptance_checks=["pytest -q"],
            rollback_required=False,
        ),
        selected_tool="edit",
        file_path="src/demo.py",
        target_files=["src/demo.py"],
        next_action="Patch src/demo.py and rerun tests.",
        stable_workflow={"anchor_id": "workflow-anchor-1"},
    )
    save_session(session)

    loaded = load_session(str(tmp_path), "product-reviewer-1", project_scope=workbench._config.project_scope)

    assert loaded is not None
    assert loaded.execution_packet is not None
    assert loaded.execution_packet.review_contract is not None
    assert loaded.execution_packet.review_contract.standard == "strict"
    assert loaded.execution_packet.reviewer_ready_required is True
    assert loaded.execution_packet.resume_anchor == ResumeAnchor(
        anchor="resume:src/demo.py",
        file_path="src/demo.py",
        symbol=None,
        repo_root=str(tmp_path),
    )
    assert loaded.execution_packet_summary is not None
    assert loaded.execution_packet_summary.review_contract_present is True
    assert loaded.continuity_review_pack is not None
    assert loaded.continuity_review_pack.pack_version == "continuity_review_pack_v1"
    assert loaded.continuity_review_pack.review_contract is not None
    assert loaded.continuity_review_pack.review_contract.rollback_required is True
    assert loaded.evolution_review_pack is not None
    assert loaded.evolution_review_pack.selected_tool == "edit"


def test_product_session_persists_app_harness_state(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-harness-persistence")
    session = workbench._initial_session(
        task_id="product-app-harness-1",
        task="Persist long-running app harness state across save and load.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    session.app_harness_state = AppHarnessState(
        product_spec=ProductSpec(
            prompt="Build a retro game maker.",
            title="Retro Game Maker",
            app_type="full_stack_app",
            stack=["React", "Vite", "FastAPI", "SQLite"],
            features=["sprite editor", "level editor", "test mode"],
            design_direction="retro toolchain with high information density",
            sprint_ids=["sprint-1"],
        ),
        evaluator_criteria=[
            EvaluatorCriterion(name="functionality", description="Core flows should work.", threshold=0.8, weight=1.0),
            EvaluatorCriterion(name="design_quality", description="The app should feel cohesive.", threshold=0.7, weight=1.0),
        ],
        active_sprint_contract=SprintContract(
            sprint_id="sprint-1",
            goal="Ship the playable editor shell.",
            scope=["editor frame", "seed project"],
            acceptance_checks=["pytest tests/test_editor.py -q"],
            done_definition=["editor loads", "seed project renders"],
            proposed_by="planner",
            approved=True,
        ),
        sprint_history=[
            SprintContract(
                sprint_id="sprint-0",
                goal="Bootstrap the app shell.",
            )
        ],
        latest_sprint_evaluation=SprintEvaluation(
            sprint_id="sprint-1",
            status="failed",
            summary="Editor loads but the play mode wiring is broken.",
            criteria_scores={"functionality": 0.55, "design_quality": 0.78},
            blocker_notes=["play mode does not respond to keyboard input"],
        ),
        latest_negotiation_round=SprintNegotiationRound(
            sprint_id="sprint-1",
            evaluator_mode="contract_driven",
            evaluator_status="failed",
            objections=["Resolve failing criterion: functionality."],
            planner_response=["Keep sprint-1 narrow until the evaluator objections are cleared."],
            recommended_action="revise_current_sprint",
        ),
        loop_status="needs_revision",
    )
    save_session(session)

    loaded = load_session(str(tmp_path), "product-app-harness-1", project_scope=workbench._config.project_scope)

    assert loaded is not None
    assert loaded.app_harness_state is not None
    assert loaded.app_harness_state.product_spec is not None
    assert loaded.app_harness_state.product_spec.title == "Retro Game Maker"
    assert loaded.app_harness_state.active_sprint_contract is not None
    assert loaded.app_harness_state.active_sprint_contract.sprint_id == "sprint-1"
    assert loaded.app_harness_state.latest_sprint_evaluation is not None
    assert loaded.app_harness_state.latest_sprint_evaluation.status == "failed"
    assert loaded.app_harness_state.latest_negotiation_round is not None
    assert loaded.app_harness_state.latest_negotiation_round.recommended_action == "revise_current_sprint"
    assert loaded.app_harness_state.loop_status == "needs_revision"


def test_product_app_harness_service_builds_plan_sprint_and_evaluation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-harness-service")
    session = workbench._initial_session(
        task_id="product-app-service-1",
        task="Set up the app harness state for a long-running app build.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()

    plan_summary = service.plan_app(
        session,
        prompt="Build a collaborative pixel-art level editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI", "SQLite"],
        features=["canvas editor", "palette presets", "shareable levels"],
        design_direction="editor-first, dense but friendly",
        evaluator_criteria=[
            EvaluatorCriterion(name="functionality", threshold=0.85),
            EvaluatorCriterion(name="design_quality", threshold=0.7),
        ],
    )
    sprint_summary = service.set_sprint_contract(
        session,
        sprint_id="sprint-1",
        goal="Ship the editor shell and the seeded canvas.",
        scope=["shell", "canvas", "palette"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads", "canvas renders", "palette selectable"],
        proposed_by="planner",
        approved=True,
    )
    evaluation_summary = service.record_sprint_evaluation(
        session,
        sprint_id="sprint-1",
        status="failed",
        summary="The shell loads but the palette selection does not persist.",
        criteria_scores={"functionality": 0.61, "design_quality": 0.79},
        blocker_notes=["palette selection resets on refresh"],
    )

    assert plan_summary["product_spec"]["title"] == "Pixel Forge"
    assert plan_summary["product_spec"]["feature_groups"] == [
        "core_workflow",
        "supporting_workflows",
        "system_foundations",
    ]
    assert plan_summary["evaluator_criteria_count"] == 2
    assert plan_summary["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert plan_summary["active_sprint_contract"]["approved"] is False
    assert plan_summary["planned_sprint_contracts"][0]["sprint_id"] == "sprint-2"
    assert plan_summary["planned_sprint_contracts"][0]["proposed_by"] == "planner"
    assert plan_summary["loop_status"] == "sprint_proposed"
    assert sprint_summary["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert sprint_summary["active_sprint_contract"]["approved"] is True
    assert evaluation_summary["latest_sprint_evaluation"]["status"] == "failed"
    assert evaluation_summary["loop_status"] == "needs_revision"
    assert session.app_harness_state is not None
    assert session.app_harness_state.product_spec is not None
    assert session.app_harness_state.product_spec.sprint_ids == ["sprint-1", "sprint-2"]
    assert session.app_harness_state.active_sprint_contract is not None
    assert session.app_harness_state.active_sprint_contract.proposed_by == "planner"
    assert session.app_harness_state.latest_sprint_evaluation is not None
    assert session.app_harness_state.latest_sprint_evaluation.blocker_notes == [
        "palette selection resets on refresh"
    ]


def test_product_app_harness_service_negotiates_current_sprint(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-harness-negotiate")
    session = workbench._initial_session(
        task_id="product-app-negotiate-1",
        task="Negotiate the current sprint after evaluator objections.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()
    service.plan_app(
        session,
        prompt="Build a collaborative pixel-art level editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI", "SQLite"],
        features=["canvas editor", "palette presets", "shareable levels"],
        evaluator_criteria=[
            EvaluatorCriterion(name="functionality", threshold=0.85),
            EvaluatorCriterion(name="design_quality", threshold=0.7),
        ],
    )
    service.set_sprint_contract(
        session,
        sprint_id="sprint-1",
        goal="Ship the editor shell and the seeded canvas.",
        scope=["shell", "canvas", "palette"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads", "canvas renders", "palette selectable"],
        proposed_by="planner",
        approved=True,
    )
    service.record_sprint_evaluation(
        session,
        sprint_id="sprint-1",
        status="failed",
        criteria_scores={"functionality": 0.61, "design_quality": 0.79},
        blocker_notes=["palette selection resets on refresh"],
    )

    negotiation_summary = service.negotiate_sprint(session, sprint_id="sprint-1")

    assert negotiation_summary["latest_negotiation_round"]["sprint_id"] == "sprint-1"
    assert negotiation_summary["latest_negotiation_round"]["recommended_action"] == "revise_current_sprint"
    assert negotiation_summary["latest_negotiation_round"]["objections"] == [
        "Resolve failing criterion: functionality.",
        "palette selection resets on refresh",
    ]
    assert negotiation_summary["latest_negotiation_round"]["planner_mode"] == "deterministic"
    assert negotiation_summary["negotiation_history_count"] == 1
    assert negotiation_summary["loop_status"] == "negotiation_pending"


def test_product_app_harness_service_infers_product_spec_from_prompt_only(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-harness-autoplan")
    session = workbench._initial_session(
        task_id="product-app-service-autoplan-1",
        task="Infer a product spec from a high-level app prompt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()

    plan_summary = service.plan_app(
        session,
        prompt="Build a visual dependency explorer for async task orchestration.",
    )

    assert plan_summary["product_spec"]["title"] == "Visual Dependency Explorer"
    assert plan_summary["product_spec"]["app_type"] == "desktop_like_web_app"
    assert plan_summary["product_spec"]["feature_count"] == 3
    assert plan_summary["product_spec"]["stack"] == ["React", "Vite", "SQLite"]
    assert plan_summary["product_spec"]["feature_groups"] == [
        "core_workflow",
        "supporting_workflows",
        "system_foundations",
    ]
    assert plan_summary["evaluator_criteria_count"] == 3
    assert plan_summary["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert plan_summary["active_sprint_contract"]["approved"] is False
    assert plan_summary["planned_sprint_contracts"][0]["sprint_id"] == "sprint-2"
    assert plan_summary["loop_status"] == "sprint_proposed"
    assert session.app_harness_state is not None
    assert session.app_harness_state.product_spec is not None
    assert session.app_harness_state.active_sprint_contract is not None
    assert session.app_harness_state.active_sprint_contract.goal == (
        "Ship the first usable visual dependency explorer workflow."
    )
    assert session.app_harness_state.product_spec.design_direction == (
        "high-signal workspace with clear navigation and compact panels"
    )
    assert [criterion.name for criterion in session.app_harness_state.evaluator_criteria] == [
        "functionality",
        "design_quality",
        "code_quality",
    ]
    assert session.app_harness_state.product_spec.feature_groups == {
        "core_workflow": ["visual dependency explorer"],
        "supporting_workflows": ["async task orchestration"],
        "system_foundations": ["project workspace"],
    }
    assert session.app_harness_state.product_spec.feature_rationale == {
        "core_workflow": "This is the primary user-visible path the first sprint should make tangible.",
        "supporting_workflows": "These flows reinforce the core path and should be stabilized right after the first usable shell.",
        "system_foundations": "These foundations keep state, navigation, and persistence coherent as the app grows.",
    }
    assert session.app_harness_state.planned_sprint_contracts[0].sprint_id == "sprint-2"
    assert session.app_harness_state.planned_sprint_contracts[0].goal == (
        "Stabilize async task orchestration and project workspace around the visual dependency explorer release path."
    )
    assert session.app_harness_state.planned_sprint_contracts[0].scope == [
        "async task orchestration",
        "project workspace",
        "quality pass",
    ]
    assert session.app_harness_state.planning_rationale == [
        "Start by making the core workflow tangible: visual dependency explorer.",
        "Keep the second sprint focused on supporting workflows: async task orchestration.",
        "Treat foundational work as stability infrastructure: project workspace.",
        "Bias toward a dense workspace shell before polishing secondary interactions.",
    ]
    assert session.app_harness_state.sprint_negotiation_notes == [
        "Do not approve follow-up work until sprint-1 proves the visual dependency explorer path.",
        "Evaluator should challenge whether async task orchestration, project workspace genuinely depends on sprint-1 being stable.",
        "Sprint negotiation should keep acceptance checks explicit: npm run build.",
    ]


def test_product_app_harness_service_derives_bounded_revision(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-harness-retry")
    session = workbench._initial_session(
        task_id="product-app-service-retry-1",
        task="Derive a bounded revision attempt from the latest negotiation round.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()
    service.plan_app(
        session,
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        evaluator_criteria=[
            EvaluatorCriterion(name="functionality", threshold=0.8),
            EvaluatorCriterion(name="design_quality", threshold=0.7),
        ],
    )
    service.set_sprint_contract(
        session,
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    service.record_sprint_evaluation(
        session,
        sprint_id="sprint-1",
        status="failed",
        criteria_scores={"functionality": 0.61, "design_quality": 0.79},
        blocker_notes=["palette resets on refresh"],
    )
    service.negotiate_sprint(
        session,
        sprint_id="sprint-1",
        evaluator_objections=["timeline entries reset on refresh"],
    )

    retry_summary = service.apply_revision_attempt(
        session,
        sprint_id="sprint-1",
        explicit_notes=["Focus on palette persistence before widening the scope."],
    )

    latest_revision = retry_summary["latest_revision"]
    assert latest_revision["revision_id"] == "sprint-1-revision-1"
    assert latest_revision["planner_mode"] == "deterministic"
    assert latest_revision["source_negotiation_action"] == "revise_current_sprint"
    assert latest_revision["must_fix"] == [
        "Resolve failing criterion: functionality.",
        "palette resets on refresh",
        "timeline entries reset on refresh",
    ]
    assert latest_revision["must_keep"] == [
        "pytest tests/test_editor.py -q",
        "editor loads",
        "design_quality",
    ]
    assert retry_summary["retry_budget"] == 1
    assert retry_summary["retry_count"] == 1
    assert retry_summary["revision_history_count"] == 1
    assert retry_summary["loop_status"] == "revision_recorded"


def test_product_inspect_session_exposes_app_harness_canonical_view(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-harness-inspect")
    session = workbench._initial_session(
        task_id="product-app-inspect-1",
        task="Inspect app harness state through canonical views.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()
    service.plan_app(
        session,
        prompt="Build a visual storyboarding tool for narrative games.",
        title="Storyboard Forge",
        app_type="desktop_like_web_app",
        stack=["React", "Vite", "SQLite"],
        features=["scene timeline", "panel editor", "character notes"],
        evaluator_criteria=[EvaluatorCriterion(name="functionality", threshold=0.8)],
    )
    service.set_sprint_contract(
        session,
        sprint_id="sprint-1",
        goal="Ship the timeline shell and panel editor.",
        scope=["timeline", "panel editor"],
        acceptance_checks=["pytest tests/test_storyboard.py -q"],
        approved=True,
    )
    service.record_sprint_evaluation(
        session,
        sprint_id="sprint-1",
        status="passed",
        summary="The timeline shell and panel editor are stable.",
    )
    save_session(session)

    payload = workbench.inspect_session(task_id="product-app-inspect-1")
    harness = payload["canonical_views"]["app_harness"]

    assert harness["product_spec"]["title"] == "Storyboard Forge"
    assert harness["product_spec"]["feature_count"] == 3
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert harness["latest_sprint_evaluation"]["status"] == "passed"
    assert harness["evaluator_criteria_count"] == 1
    assert harness["policy_stage"] == "base"
    assert harness["execution_outcome_ready"] is False
    assert harness["execution_gate"] == "no_execution"
    assert harness["loop_status"] == "ready_for_next_sprint"


def test_product_runtime_app_plan_sprint_and_qa_round_trip(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-flow")
    session = workbench._initial_session(
        task_id="product-app-runtime-1",
        task="Drive the app harness through plan, sprint, and qa updates.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    plan_payload = workbench.app_plan(
        task_id="product-app-runtime-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        design_direction="dense creative tooling",
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    sprint_payload = workbench.app_sprint(
        task_id="product-app-runtime-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-1",
        sprint_id="sprint-1",
        status="failed",
        summary="Palette persistence still fails.",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    negotiate_payload = workbench.app_negotiate(
        task_id="product-app-runtime-1",
        sprint_id="sprint-1",
    )
    inspect_payload = workbench.inspect_session(task_id="product-app-runtime-1")

    assert plan_payload["shell_view"] == "app_plan"
    assert sprint_payload["shell_view"] == "app_sprint"
    assert qa_payload["shell_view"] == "app_qa"
    assert negotiate_payload["shell_view"] == "app_negotiate"
    harness = inspect_payload["canonical_views"]["app_harness"]
    assert harness["product_spec"]["title"] == "Pixel Forge"
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert harness["active_sprint_contract"]["approved"] is True
    assert harness["latest_sprint_evaluation"]["status"] == "failed"
    assert harness["latest_sprint_evaluation"]["summary"] == "Palette persistence still fails."
    assert harness["latest_sprint_evaluation"]["evaluator_mode"] == "contract_driven"
    assert harness["latest_sprint_evaluation"]["failing_criteria"] == ["functionality"]
    assert harness["latest_negotiation_round"]["recommended_action"] == "revise_current_sprint"
    assert harness["evaluator_criteria_count"] == 2
    assert harness["loop_status"] == "negotiation_pending"


def test_product_runtime_app_retry_records_revision_attempt(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-retry")
    session = workbench._initial_session(
        task_id="product-app-runtime-retry-1",
        task="Record one bounded revision attempt after negotiation.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-retry-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-retry-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-retry-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-retry-1",
        sprint_id="sprint-1",
    )

    retry_payload = workbench.app_retry(
        task_id="product-app-runtime-retry-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )

    assert retry_payload["shell_view"] == "app_retry"
    harness = retry_payload["canonical_views"]["app_harness"]
    assert harness["latest_revision"]["revision_id"] == "sprint-1-revision-1"
    assert harness["latest_revision"]["planner_mode"] == "deterministic"
    assert harness["retry_budget"] == 1
    assert harness["retry_count"] == 1
    assert harness["revision_history_count"] == 1
    assert harness["loop_status"] == "revision_recorded"


def test_product_runtime_app_qa_compares_revision_outcome(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-retry-compare")
    session = workbench._initial_session(
        task_id="product-app-runtime-retry-compare-1",
        task="Compare evaluator results before and after one bounded revision attempt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-retry-compare-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-retry-compare-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-retry-compare-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-retry-compare-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-retry-compare-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-retry-compare-1",
        sprint_id="sprint-1",
        status="passed",
        scores=["functionality=0.89", "design_quality=0.82"],
        summary="Palette persistence is stable and the editor shell clears the evaluator bar.",
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["status"] == "passed"
    assert harness["loop_status"] == "ready_for_next_sprint"
    assert harness["next_sprint_ready"] is True
    assert harness["next_sprint_candidate_id"] == "sprint-2"
    assert harness["retry_available"] is False
    assert harness["retry_remaining"] == 0
    assert harness["recommended_next_action"] == "advance_to_next_sprint"
    assert harness["latest_revision"]["baseline_status"] == "failed"
    assert harness["latest_revision"]["baseline_failing_criteria"] == ["functionality"]
    assert harness["latest_revision"]["outcome_status"] == "passed"
    assert harness["latest_revision"]["outcome_failing_criteria"] == []
    assert harness["latest_revision"]["outcome_summary"] == (
        "Palette persistence is stable and the editor shell clears the evaluator bar."
    )
    assert harness["latest_revision"]["improvement_status"] == "improved"


def test_product_runtime_app_qa_failed_after_retry_exposes_retry_policy(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-retry-policy")
    session = workbench._initial_session(
        task_id="product-app-runtime-retry-policy-1",
        task="Keep a retry open when the revised sprint still fails.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-retry-policy-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    loaded = load_session(
        task_id="product-app-runtime-retry-policy-1",
        project_scope=workbench._config.project_scope,
        repo_root=workbench._config.repo_root,
    )
    assert loaded is not None
    assert loaded.app_harness_state is not None
    loaded.app_harness_state.retry_budget = 2
    save_session(loaded)

    workbench.app_sprint(
        task_id="product-app-runtime-retry-policy-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-retry-policy-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-retry-policy-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-retry-policy-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on persistence before broadening scope."],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-retry-policy-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        summary="Timeline persistence improved, but functionality still fails the evaluator bar.",
        blocker_notes=["timeline entries still drift after refresh"],
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_revision"]["baseline_status"] == "failed"
    assert harness["latest_revision"]["outcome_status"] == "failed"
    assert harness["latest_revision"]["improvement_status"] == "unchanged"
    assert harness["loop_status"] == "retry_available"
    assert harness["retry_available"] is True
    assert harness["retry_remaining"] == 1
    assert harness["next_sprint_ready"] is False
    assert harness["next_sprint_candidate_id"] == ""
    assert harness["recommended_next_action"] == "retry_current_sprint"


def test_product_runtime_app_advance_promotes_next_sprint(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-advance")
    session = workbench._initial_session(
        task_id="product-app-runtime-advance-1",
        task="Advance to sprint-2 once sprint-1 passes after retry.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-advance-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-advance-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-advance-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-advance-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-advance-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )
    workbench.app_qa(
        task_id="product-app-runtime-advance-1",
        sprint_id="sprint-1",
        status="passed",
        scores=["functionality=0.89", "design_quality=0.82"],
        summary="Palette persistence is stable and the editor shell clears the evaluator bar.",
    )

    advance_payload = workbench.app_advance(
        task_id="product-app-runtime-advance-1",
        sprint_id="sprint-2",
    )

    harness = advance_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert harness["planned_sprint_contracts"] == []
    assert harness["latest_sprint_evaluation"]["status"] == ""
    assert harness["latest_revision"]["revision_id"] == ""
    assert harness["loop_status"] == "in_sprint"


def test_product_runtime_app_advance_requires_latest_execution_outcome_to_be_qa_passed(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-advance-execution-gate")
    session = workbench._initial_session(
        task_id="product-app-runtime-advance-execution-gate-1",
        task="Do not advance if the latest execution attempt has not settled successfully.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-advance-execution-gate-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-advance-execution-gate-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    loaded = load_session(
        task_id="product-app-runtime-advance-execution-gate-1",
        project_scope=workbench._config.project_scope,
        repo_root=workbench._config.repo_root,
    )
    assert loaded is not None
    assert loaded.app_harness_state is not None
    loaded.app_harness_state.latest_sprint_evaluation = SprintEvaluation(
        sprint_id="sprint-1",
        status="passed",
        summary="Evaluator says the sprint is ready.",
        evaluator_mode="contract_driven",
    )
    loaded.app_harness_state.latest_execution_attempt = SprintExecutionAttempt(
        attempt_id="sprint-1-attempt-1",
        sprint_id="sprint-1",
        execution_target_kind="revision",
        execution_mode="deterministic",
        execution_summary="Latest execution attempt still needs QA confirmation.",
        status="recorded",
        success=False,
    )
    loaded.app_harness_state.execution_history = [loaded.app_harness_state.latest_execution_attempt]
    save_session(loaded)

    advance_payload = workbench.app_advance(
        task_id="product-app-runtime-advance-execution-gate-1",
        sprint_id="sprint-2",
    )

    harness = advance_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert harness["policy_stage"] == "base"
    assert harness["execution_outcome_ready"] is False
    assert harness["execution_gate"] == "needs_qa"
    assert harness["execution_focus"] == "Latest execution attempt still needs QA confirmation."
    assert harness["recommended_next_action"] == "evaluate_current_execution"
    assert harness["loop_status"] == "execution_recorded"


def test_product_runtime_app_escalate_marks_loop_escalated(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-escalate")
    session = workbench._initial_session(
        task_id="product-app-runtime-escalate-1",
        task="Escalate the sprint once retry budget is exhausted.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-escalate-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-escalate-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    loaded = load_session(
        task_id="product-app-runtime-escalate-1",
        project_scope=workbench._config.project_scope,
        repo_root=workbench._config.repo_root,
    )
    assert loaded is not None
    assert loaded.app_harness_state is not None
    loaded.app_harness_state.retry_budget = 1
    save_session(loaded)
    workbench.app_qa(
        task_id="product-app-runtime-escalate-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-escalate-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-escalate-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )
    workbench.app_qa(
        task_id="product-app-runtime-escalate-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        summary="Timeline persistence improved, but functionality still fails the evaluator bar.",
        blocker_notes=["timeline entries still drift after refresh"],
    )

    escalate_payload = workbench.app_escalate(
        task_id="product-app-runtime-escalate-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )

    harness = escalate_payload["canonical_views"]["app_harness"]
    assert harness["loop_status"] == "escalated"
    assert harness["last_execution_gate_transition"] == "no_execution->no_execution"
    assert harness["last_policy_action"] == "escalate"
    assert harness["recommended_next_action"] == "replan_or_escalate"
    assert harness["sprint_negotiation_notes"][-1] == "retry budget exhausted"


def test_product_runtime_app_replan_creates_replanned_sprint(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-replan")
    session = workbench._initial_session(
        task_id="product-app-runtime-replan-1",
        task="Replan the sprint after escalation.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-replan-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    loaded = load_session(
        task_id="product-app-runtime-replan-1",
        project_scope=workbench._config.project_scope,
        repo_root=workbench._config.repo_root,
    )
    assert loaded is not None
    assert loaded.app_harness_state is not None
    loaded.app_harness_state.retry_budget = 1
    save_session(loaded)
    workbench.app_qa(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        execution_summary="Patch palette persistence in src/editor.tsx before retrying the evaluator.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        summary="Timeline persistence improved, but functionality still fails the evaluator bar.",
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )

    replan_payload = workbench.app_replan(
        task_id="product-app-runtime-replan-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )

    harness = replan_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1"
    assert harness["active_sprint_contract"]["approved"] is False
    assert harness["retry_count"] == 0
    assert harness["retry_remaining"] == 1
    assert harness["last_execution_gate_transition"] == "no_execution->no_execution"
    assert harness["last_policy_action"] == "replan"
    assert harness["latest_sprint_evaluation"]["status"] == ""
    assert harness["latest_revision"]["revision_id"] == ""
    assert harness["loop_status"] == "sprint_replanned"
    assert harness["recommended_next_action"] == "run_current_sprint"
    assert "narrow the sprint around persistence" in harness["sprint_negotiation_notes"][0]
    assert "Previous execution outcome: Patch palette persistence in src/editor.tsx before retrying the evaluator." in harness["sprint_negotiation_notes"][0]
    assert "src/editor.tsx" in harness["active_sprint_contract"]["scope"]


def test_product_runtime_app_replan_uses_live_planner_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-replan")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-replan-1",
        task="Use a live planner slice to replan the sprint after escalation.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-replan-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        execution_summary="Patch palette persistence in src/editor.tsx before retrying the evaluator.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        summary="Timeline persistence improved, but functionality still fails the evaluator bar.",
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )

    def _fake_live_replanner(**kwargs):
        assert kwargs.get("execution_focus") == (
            "Patch palette persistence in src/editor.tsx before retrying the evaluator."
        )
        return {
            "goal": "Replanned sprint focused on persistence hardening.",
            "scope": ["src/editor.tsx", "refresh stability"],
            "acceptance_checks": ["pytest tests/test_editor.py -q"],
            "done_definition": ["refresh path stays stable", "editor shell remains coherent"],
            "replan_note": "Narrow the sprint around persistence hardening after the failed execution attempt.",
        }

    monkeypatch.setattr(workbench._execution_host, "replan_sprint_live", _fake_live_replanner)

    payload = workbench.app_replan(
        task_id="product-app-runtime-live-replan-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
        use_live_planner=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1"
    assert harness["active_sprint_contract"]["goal"] == "Replanned sprint focused on persistence hardening."
    assert harness["active_sprint_contract"]["scope"] == ["src/editor.tsx", "refresh stability"]
    assert harness["active_sprint_contract"]["acceptance_checks"] == ["pytest tests/test_editor.py -q"]
    assert harness["active_sprint_contract"]["done_definition"] == [
        "refresh path stays stable",
        "editor shell remains coherent",
    ]
    assert payload["app_replanner_timeout_seconds"] > 0
    assert payload["app_replanner_max_completion_tokens"] > 0


def test_product_runtime_replanned_sprint_pass_unlocks_advance(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-replanned-advance")
    session = workbench._initial_session(
        task_id="product-app-runtime-replanned-advance-1",
        task="Advance after a replanned sprint passes QA with a settled execution outcome.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-replanned-advance-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Stabilize palette persistence and refresh flow on the replanned sprint.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-1-replan-1",
        status="passed",
        scores=["functionality=0.88", "design_quality=0.84"],
        summary="The replanned sprint stabilizes refresh flow and clears the evaluator bar.",
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1"
    assert harness["latest_execution_attempt"]["status"] == "qa_passed"
    assert harness["last_execution_gate_transition"] == "needs_qa->ready"
    assert harness["last_policy_action"] == "qa:passed"
    assert harness["loop_status"] == "ready_for_next_sprint"
    assert harness["next_sprint_ready"] is True
    assert harness["next_sprint_candidate_id"] == "sprint-2"
    assert harness["recommended_next_action"] == "advance_to_next_sprint"

    advance_payload = workbench.app_advance(
        task_id="product-app-runtime-replanned-advance-1",
        sprint_id="sprint-2",
    )

    advance_harness = advance_payload["canonical_views"]["app_harness"]
    assert advance_harness["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert advance_harness["last_execution_gate_transition"] == "ready->no_execution"
    assert advance_harness["last_policy_action"] == "advance"
    assert advance_harness["loop_status"] == "in_sprint"


def test_product_runtime_replanned_sprint_failed_execution_routes_back_to_negotiation_and_retry(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-replanned-retry")
    session = workbench._initial_session(
        task_id="product-app-runtime-replanned-retry-1",
        task="Allow a replanned sprint to re-enter negotiation and bounded retry after a failed execution attempt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-replanned-retry-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Patch the refresh path for the replanned sprint before re-running QA.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.74", "design_quality=0.82"],
        summary="The replanned sprint still fails functionality on refresh.",
        blocker_notes=["refresh path still loses palette state"],
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1"
    assert harness["latest_execution_attempt"]["status"] == "qa_failed"
    assert harness["current_sprint_execution_count"] == 1
    assert harness["loop_status"] == "needs_revision"
    assert harness["retry_available"] is False
    assert harness["recommended_next_action"] == "negotiate_current_sprint"

    workbench.app_negotiate(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1-replan-1",
        objections=["refresh path still loses palette state"],
    )
    retry_payload = workbench.app_retry(
        task_id="product-app-runtime-replanned-retry-1",
        sprint_id="sprint-1-replan-1",
        revision_notes=["Narrow the replanned sprint to palette hydration and refresh stability."],
    )

    retry_harness = retry_payload["canonical_views"]["app_harness"]
    assert retry_harness["latest_revision"]["sprint_id"] == "sprint-1-replan-1"
    assert retry_harness["retry_count"] == 1
    assert retry_harness["retry_remaining"] == 0
    assert retry_harness["last_execution_gate_transition"] == "needs_qa->qa_failed"
    assert retry_harness["last_policy_action"] == "qa:failed"
    assert retry_harness["loop_status"] == "revision_recorded"


def test_product_runtime_second_replan_tracks_depth_and_resets_retry_window(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-second-replan")
    session = workbench._initial_session(
        task_id="product-app-runtime-second-replan-1",
        task="Track second replan depth and reset the bounded retry window.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-second-replan-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Patch the refresh path for the replanned sprint before re-running QA.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.74", "design_quality=0.82"],
        summary="The replanned sprint still fails functionality on refresh.",
        blocker_notes=["refresh path still loses palette state"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        objections=["refresh path still loses palette state"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        revision_notes=["Narrow the replanned sprint to palette hydration and refresh stability."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Try a second bounded persistence patch on the replanned sprint.",
        changed_target_hints=["src/editor.tsx", "src/state/hydration.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.75", "design_quality=0.83"],
        summary="The replanned sprint still fails after the bounded retry.",
        blocker_notes=["palette hydration still diverges after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        note="replanned retry budget exhausted",
    )

    replan_payload = workbench.app_replan(
        task_id="product-app-runtime-second-replan-1",
        sprint_id="sprint-1-replan-1",
        note="narrow again around hydration and persistence",
    )

    harness = replan_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1-replan-1"
    assert harness["replan_depth"] == 2
    assert harness["replan_root_sprint_id"] == "sprint-1"
    assert harness["retry_count"] == 0
    assert harness["retry_remaining"] == 1
    assert harness["loop_status"] == "sprint_replanned"
    assert harness["recommended_next_action"] == "run_current_sprint"


def _prepare_second_replan_transition_state(workbench: AionisWorkbench, *, task_id: str) -> None:
    workbench.app_plan(
        task_id=task_id,
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id=task_id,
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id=task_id,
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id=task_id,
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id=task_id,
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id=task_id,
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id=task_id,
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id=task_id,
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )
    workbench.app_replan(
        task_id=task_id,
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )
    workbench.app_generate(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        execution_summary="Patch the refresh path for the replanned sprint before re-running QA.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.74", "design_quality=0.82"],
        summary="The replanned sprint still fails functionality on refresh.",
        blocker_notes=["refresh path still loses palette state"],
    )
    workbench.app_negotiate(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        objections=["refresh path still loses palette state"],
    )
    workbench.app_retry(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        revision_notes=["Narrow the replanned sprint to palette hydration and refresh stability."],
    )
    workbench.app_generate(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        execution_summary="Try a second bounded persistence patch on the replanned sprint.",
        changed_target_hints=["src/editor.tsx", "src/state/hydration.ts"],
    )
    workbench.app_qa(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.75", "design_quality=0.83"],
        summary="The replanned sprint still fails after the bounded retry.",
        blocker_notes=["palette hydration still diverges after refresh"],
    )
    workbench.app_escalate(
        task_id=task_id,
        sprint_id="sprint-1-replan-1",
        note="replanned retry budget exhausted",
    )


def test_product_runtime_second_replan_uses_live_planner_with_execution_focus(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-second-replan-live")
    session = workbench._initial_session(
        task_id="product-app-runtime-second-replan-live-1",
        task="Use a live replanner on the second replan transition with execution focus.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    _prepare_second_replan_transition_state(
        workbench,
        task_id="product-app-runtime-second-replan-live-1",
    )

    def _fake_second_live_replanner(**kwargs):
        assert kwargs.get("execution_focus") == "Try a second bounded persistence patch on the replanned sprint."
        return {
            "goal": "Second replanned sprint focused on the final hydration edge.",
            "scope": ["src/state/hydration.ts", "src/state/persistence.ts"],
            "acceptance_checks": ["pytest tests/test_editor.py -q"],
            "done_definition": ["hydration edge stays stable", "persistence remains coherent"],
            "replan_note": "Narrow the sprint one more time around the final hydration edge.",
        }

    monkeypatch.setattr(workbench._execution_host, "replan_sprint_live", _fake_second_live_replanner)

    payload = workbench.app_replan(
        task_id="product-app-runtime-second-replan-live-1",
        sprint_id="sprint-1-replan-1",
        note="narrow again around hydration and persistence",
        use_live_planner=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1-replan-1"
    assert harness["active_sprint_contract"]["goal"] == "Second replanned sprint focused on the final hydration edge."
    assert payload["app_replanner_timeout_seconds"] > 0
    assert payload["app_replanner_max_completion_tokens"] > 0


def test_product_runtime_second_replanned_generate_uses_live_generator_with_execution_focus(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-second-replanned-live-generate")
    session = workbench._initial_session(
        task_id="product-app-runtime-second-replanned-live-generate-1",
        task="Use a live generator on the second replanned sprint with carried execution focus.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    _prepare_second_replan_transition_state(
        workbench,
        task_id="product-app-runtime-second-replanned-live-generate-1",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replanned-live-generate-1",
        sprint_id="sprint-1-replan-1",
        note="narrow again around hydration and persistence",
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)
    monkeypatch.setattr(
        workbench._delivery,
        "execute_app_generate",
        lambda **kwargs: (
            (
                lambda execution_summary: (
                    (_ for _ in ()).throw(AssertionError("missing second replan execution focus"))
                    if "narrow again around hydration and persistence Previous execution outcome: Try a second bounded persistence patch on the replanned sprint." not in execution_summary
                    else DeliveryExecutionResult(
                        execution_summary="Patch the final hydration edge on the second replanned sprint.",
                        changed_target_hints=[
                            "src/state/hydration.ts",
                            "src/state/persistence.ts",
                            "pytest tests/test_editor.py -q",
                        ],
                        changed_files=["src/state/hydration.ts", "src/state/persistence.ts"],
                        artifact_paths=["index.html", "src/state/hydration.ts"],
                        artifact_kind="workspace_app",
                        preview_command="npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
                        validation_command="pytest tests/test_editor.py -q",
                        validation_summary="Validation commands passed.",
                        validation_ok=True,
                    )
                )
            )(str(kwargs.get("execution_summary") or ""))
        ),
    )

    payload = workbench.app_generate(
        task_id="product-app-runtime-second-replanned-live-generate-1",
        sprint_id="sprint-1-replan-1-replan-1",
        use_live_generator=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["latest_execution_attempt"]["execution_mode"] == "live"
    assert harness["latest_execution_attempt"]["sprint_id"] == "sprint-1-replan-1-replan-1"
    assert harness["latest_execution_attempt"]["execution_summary"] == (
        "Patch the final hydration edge on the second replanned sprint."
    )


def test_product_runtime_second_replan_pass_unlocks_advance(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-second-replan-advance")
    session = workbench._initial_session(
        task_id="product-app-runtime-second-replan-advance-1",
        task="Advance after a second replanned sprint passes QA with a settled execution outcome.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-second-replan-advance-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Patch the refresh path for the replanned sprint before re-running QA.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.74", "design_quality=0.82"],
        summary="The replanned sprint still fails functionality on refresh.",
        blocker_notes=["refresh path still loses palette state"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        objections=["refresh path still loses palette state"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        revision_notes=["Narrow the replanned sprint to palette hydration and refresh stability."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Try a second bounded persistence patch on the replanned sprint.",
        changed_target_hints=["src/editor.tsx", "src/state/hydration.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.75", "design_quality=0.83"],
        summary="The replanned sprint still fails after the bounded retry.",
        blocker_notes=["palette hydration still diverges after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        note="replanned retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1",
        note="narrow again around hydration and persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1-replan-1",
        execution_summary="Stabilize the final hydration edge on the second replanned sprint.",
        changed_target_hints=["src/state/hydration.ts", "src/state/persistence.ts"],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-1-replan-1-replan-1",
        status="passed",
        scores=["functionality=0.89", "design_quality=0.84"],
        summary="The second replanned sprint closes the last hydration edge and clears the evaluator bar.",
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1-replan-1"
    assert harness["latest_execution_attempt"]["status"] == "qa_passed"
    assert harness["last_execution_gate_transition"] == "needs_qa->ready"
    assert harness["last_policy_action"] == "qa:passed"
    assert harness["replan_depth"] == 2
    assert harness["replan_root_sprint_id"] == "sprint-1"
    assert harness["loop_status"] == "ready_for_next_sprint"
    assert harness["recommended_next_action"] == "advance_to_next_sprint"
    assert harness["next_sprint_candidate_id"] == "sprint-2"

    advance_payload = workbench.app_advance(
        task_id="product-app-runtime-second-replan-advance-1",
        sprint_id="sprint-2",
    )

    advance_harness = advance_payload["canonical_views"]["app_harness"]
    assert advance_harness["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert advance_harness["last_execution_gate_transition"] == "ready->no_execution"
    assert advance_harness["last_policy_action"] == "advance"
    assert advance_harness["loop_status"] == "in_sprint"


def test_product_runtime_second_replan_failed_execution_routes_back_to_negotiation_and_retry(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-second-replan-retry")
    session = workbench._initial_session(
        task_id="product-app-runtime-second-replan-retry-1",
        task="Allow a second replanned sprint to re-enter negotiation and bounded retry after a failed execution attempt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-second-replan-retry-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Patch the refresh path for the replanned sprint before re-running QA.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.74", "design_quality=0.82"],
        summary="The replanned sprint still fails functionality on refresh.",
        blocker_notes=["refresh path still loses palette state"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        objections=["refresh path still loses palette state"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        revision_notes=["Narrow the replanned sprint to palette hydration and refresh stability."],
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        execution_summary="Try a second bounded persistence patch on the replanned sprint.",
        changed_target_hints=["src/editor.tsx", "src/state/hydration.ts"],
    )
    workbench.app_qa(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        status="failed",
        scores=["functionality=0.75", "design_quality=0.83"],
        summary="The replanned sprint still fails after the bounded retry.",
        blocker_notes=["palette hydration still diverges after refresh"],
    )
    workbench.app_escalate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        note="replanned retry budget exhausted",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1",
        note="narrow again around hydration and persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1-replan-1",
        execution_summary="Patch the final hydration edge on the second replanned sprint before re-running QA.",
        changed_target_hints=["src/state/hydration.ts", "src/state/persistence.ts"],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1-replan-1",
        status="failed",
        scores=["functionality=0.76", "design_quality=0.84"],
        summary="The second replanned sprint still fails on the last hydration edge.",
        blocker_notes=["the last hydration edge still diverges after refresh"],
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1-replan-1"
    assert harness["latest_execution_attempt"]["status"] == "qa_failed"
    assert harness["last_execution_gate_transition"] == "needs_qa->qa_failed"
    assert harness["last_policy_action"] == "qa:failed"
    assert harness["replan_depth"] == 2
    assert harness["replan_root_sprint_id"] == "sprint-1"
    assert harness["loop_status"] == "needs_revision"
    assert harness["recommended_next_action"] == "negotiate_current_sprint"

    workbench.app_negotiate(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1-replan-1",
        objections=["the last hydration edge still diverges after refresh"],
    )
    retry_payload = workbench.app_retry(
        task_id="product-app-runtime-second-replan-retry-1",
        sprint_id="sprint-1-replan-1-replan-1",
        revision_notes=["Narrow the second replanned sprint to the last hydration edge."],
    )

    retry_harness = retry_payload["canonical_views"]["app_harness"]
    assert retry_harness["latest_revision"]["sprint_id"] == "sprint-1-replan-1-replan-1"
    assert retry_harness["replan_depth"] == 2
    assert retry_harness["replan_root_sprint_id"] == "sprint-1"
    assert retry_harness["retry_count"] == 1
    assert retry_harness["retry_remaining"] == 0
    assert retry_harness["loop_status"] == "revision_recorded"


def test_product_app_service_set_sprint_contract_resets_sprint_scoped_loop_state(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-set-sprint-reset")
    session = workbench._initial_session(
        task_id="product-app-set-sprint-reset-1",
        task="Reset sprint-scoped loop state when switching the active sprint.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()
    service.plan_app(
        session,
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        evaluator_criteria=[EvaluatorCriterion(name="functionality", threshold=0.8)],
    )
    service.set_sprint_contract(
        session,
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    service.record_sprint_evaluation(
        session,
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )
    service.negotiate_sprint(
        session,
        sprint_id="sprint-1",
        evaluator_objections=["timeline entries reset on refresh"],
    )
    service.apply_revision_attempt(
        session,
        sprint_id="sprint-1",
        explicit_notes=["Focus on palette persistence first."],
    )
    service.record_execution_attempt(
        session,
        sprint_id="sprint-1",
        execution_summary="Apply the palette persistence fix.",
    )

    sprint_summary = service.set_sprint_contract(
        session,
        sprint_id="sprint-2",
        goal="Stabilize supporting workflows.",
        scope=["palette", "export"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["supporting workflows are stable"],
        proposed_by="planner",
        approved=False,
    )

    assert sprint_summary["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert sprint_summary["latest_sprint_evaluation"]["sprint_id"] == ""
    assert sprint_summary["latest_negotiation_round"]["sprint_id"] == ""
    assert sprint_summary["latest_revision"]["revision_id"] == ""
    assert sprint_summary["latest_execution_attempt"]["attempt_id"] == ""
    assert sprint_summary["retry_count"] == 0
    assert sprint_summary["loop_status"] == "in_sprint"


def test_product_runtime_app_advance_resets_retry_and_execution_state(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-advance-reset")
    session = workbench._initial_session(
        task_id="product-app-advance-reset-1",
        task="Reset retry and execution state when advancing to the next sprint.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-advance-reset-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before widening the scope."],
    )
    workbench.app_generate(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
    )
    workbench.app_qa(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-1",
        status="passed",
        scores=["functionality=0.89", "design_quality=0.82"],
        summary="Palette persistence is stable and the editor shell clears the evaluator bar.",
    )

    advance_payload = workbench.app_advance(
        task_id="product-app-advance-reset-1",
        sprint_id="sprint-2",
    )

    harness = advance_payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert harness["retry_count"] == 0
    assert harness["retry_remaining"] == 1
    assert harness["latest_sprint_evaluation"]["sprint_id"] == ""
    assert harness["latest_revision"]["revision_id"] == ""
    assert harness["latest_execution_attempt"]["attempt_id"] == ""
    assert harness["loop_status"] == "in_sprint"


def test_product_app_service_ignores_historical_sprint_evaluation_when_new_sprint_is_active(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-historical-qa-ignored")
    session = workbench._initial_session(
        task_id="product-app-historical-qa-ignored-1",
        task="Keep historical sprint QA from overwriting the active sprint state.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    service = AppHarnessService()
    service.plan_app(
        session,
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        evaluator_criteria=[EvaluatorCriterion(name="functionality", threshold=0.8)],
    )
    service.set_sprint_contract(
        session,
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    service.set_sprint_contract(
        session,
        sprint_id="sprint-2",
        goal="Stabilize supporting workflows.",
        scope=["palette", "export"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["supporting workflows are stable"],
        proposed_by="planner",
        approved=False,
    )

    summary = service.record_sprint_evaluation(
        session,
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["old sprint should not rewrite the current loop"],
    )

    assert summary["active_sprint_contract"]["sprint_id"] == "sprint-2"
    assert summary["latest_sprint_evaluation"]["sprint_id"] == ""
    assert summary["latest_execution_attempt"]["attempt_id"] == ""
    assert summary["loop_status"] == "in_sprint"


def test_product_runtime_app_generate_records_execution_attempt(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-generate")
    session = workbench._initial_session(
        task_id="product-app-runtime-generate-1",
        task="Record one bounded generator execution attempt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-generate-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-generate-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-generate-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-generate-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-generate-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )

    generate_payload = workbench.app_generate(
        task_id="product-app-runtime-generate-1",
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence fix before re-running QA.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )

    harness = generate_payload["canonical_views"]["app_harness"]
    assert harness["latest_execution_attempt"]["attempt_id"] == "sprint-1-attempt-1"
    assert harness["latest_execution_attempt"]["sprint_id"] == "sprint-1"
    assert harness["latest_execution_attempt"]["revision_id"] == "sprint-1-revision-1"
    assert harness["latest_execution_attempt"]["execution_target_kind"] == "revision"
    assert harness["latest_execution_attempt"]["execution_mode"] == "deterministic"
    assert harness["latest_execution_attempt"]["changed_target_hints"] == ["src/editor.tsx", "src/state/store.ts"]
    assert harness["latest_execution_attempt"]["execution_summary"] == "Apply the narrowed persistence fix before re-running QA."
    assert harness["latest_execution_attempt"]["artifact_kind"] == "static_html_demo"
    assert harness["latest_execution_attempt"]["artifact_path"].endswith("/index.html")
    assert (tmp_path / harness["latest_execution_attempt"]["artifact_path"]).exists()
    artifact_html = (tmp_path / harness["latest_execution_attempt"]["artifact_path"]).read_text(encoding="utf-8")
    assert "Filter nodes, files, or checks" in artifact_html
    assert "localStorage" in artifact_html
    assert harness["latest_execution_attempt"]["status"] == "recorded"
    assert harness["latest_execution_attempt"]["success"] is False
    assert harness["execution_history_count"] == 1
    assert harness["loop_status"] == "execution_recorded"


def test_product_runtime_app_generate_derives_deterministic_summary_and_targets(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-generate-derived")
    session = workbench._initial_session(
        task_id="product-app-runtime-generate-derived-1",
        task="Derive a bounded deterministic generator summary from the current revision.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-generate-derived-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-generate-derived-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-generate-derived-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-generate-derived-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-generate-derived-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )

    generate_payload = workbench.app_generate(
        task_id="product-app-runtime-generate-derived-1",
        sprint_id="sprint-1",
    )

    harness = generate_payload["canonical_views"]["app_harness"]
    assert harness["latest_execution_attempt"]["execution_target_kind"] == "revision"
    assert harness["latest_execution_attempt"]["execution_mode"] == "deterministic"
    assert harness["latest_execution_attempt"]["changed_target_hints"] == [
        "Resolve failing criterion: functionality.",
        "Resolve failing criterion: design_quality.",
        "shell",
        "canvas",
    ]
    assert harness["latest_execution_attempt"]["execution_summary"] == (
        "Execute the bounded revision for sprint-1: Resolve failing criterion: functionality, Resolve failing criterion: design_quality."
    )


def test_product_inspect_session_exposes_app_harness_execution_attempt(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-inspect-execution")
    session = workbench._initial_session(
        task_id="product-app-inspect-execution-1",
        task="Inspect app harness execution attempt state.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    session.app_harness_state = AppHarnessState(
        product_spec=ProductSpec(prompt="Build a visual pixel-art editor.", title="Pixel Forge"),
        active_sprint_contract=SprintContract(sprint_id="sprint-1", goal="Ship the editor shell."),
        latest_execution_attempt=SprintExecutionAttempt(
            attempt_id="sprint-1-attempt-1",
            sprint_id="sprint-1",
            revision_id="sprint-1-revision-1",
            execution_target_kind="revision",
            execution_mode="deterministic",
            changed_target_hints=["src/editor.tsx"],
            execution_summary="Apply persistence fixes to the editor state path.",
            artifact_kind="static_html_demo",
            artifact_path=".aionis-workbench/artifacts/product-app-inspect-execution-1/sprint-1-attempt-1/index.html",
            preview_command="python3 -m http.server 4173 --directory /tmp/demo",
            status="recorded",
            success=True,
        ),
        execution_history=[
            SprintExecutionAttempt(
                attempt_id="sprint-1-attempt-1",
                sprint_id="sprint-1",
                revision_id="sprint-1-revision-1",
                execution_target_kind="revision",
                execution_mode="deterministic",
                changed_target_hints=["src/editor.tsx"],
                execution_summary="Apply persistence fixes to the editor state path.",
                artifact_kind="static_html_demo",
                artifact_path=".aionis-workbench/artifacts/product-app-inspect-execution-1/sprint-1-attempt-1/index.html",
                preview_command="python3 -m http.server 4173 --directory /tmp/demo",
                status="recorded",
                success=True,
            )
        ],
        loop_status="execution_recorded",
    )
    save_session(session)

    payload = workbench.inspect_session(task_id="product-app-inspect-execution-1")
    harness = payload["canonical_views"]["app_harness"]
    assert harness["latest_execution_attempt"]["attempt_id"] == "sprint-1-attempt-1"
    assert harness["latest_execution_attempt"]["execution_target_kind"] == "revision"
    assert harness["latest_execution_attempt"]["execution_summary"] == "Apply persistence fixes to the editor state path."
    assert harness["latest_execution_attempt"]["artifact_kind"] == "static_html_demo"
    assert harness["latest_execution_attempt"]["artifact_path"].endswith("/index.html")
    assert harness["execution_history_count"] == 1
    assert harness["current_sprint_execution_count"] == 1
    assert harness["policy_stage"] == "base"
    assert harness["execution_outcome_ready"] is False
    assert harness["execution_gate"] == "needs_qa"
    assert harness["execution_focus"] == "Apply persistence fixes to the editor state path."


def test_product_app_harness_current_sprint_execution_count_excludes_previous_sprints(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-current-execution-count")
    session = workbench._initial_session(
        task_id="product-app-current-execution-count-1",
        task="Keep per-sprint execution count distinct from total history.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    session.app_harness_state = AppHarnessState(
        active_sprint_contract=SprintContract(sprint_id="sprint-2", goal="Ship sprint 2."),
        latest_execution_attempt=SprintExecutionAttempt(
            attempt_id="sprint-2-attempt-1",
            sprint_id="sprint-2",
            execution_target_kind="sprint",
            execution_mode="deterministic",
            execution_summary="Apply the current sprint changes.",
            status="recorded",
            success=False,
        ),
        execution_history=[
            SprintExecutionAttempt(
                attempt_id="sprint-1-attempt-1",
                sprint_id="sprint-1",
                execution_target_kind="sprint",
                execution_mode="deterministic",
                execution_summary="Apply the previous sprint changes.",
                status="qa_passed",
                success=True,
            ),
            SprintExecutionAttempt(
                attempt_id="sprint-2-attempt-1",
                sprint_id="sprint-2",
                execution_target_kind="sprint",
                execution_mode="deterministic",
                execution_summary="Apply the current sprint changes.",
                status="recorded",
                success=False,
            ),
        ],
        loop_status="execution_recorded",
    )
    save_session(session)

    payload = workbench.inspect_session(task_id="product-app-current-execution-count-1")
    harness = payload["canonical_views"]["app_harness"]
    assert harness["execution_history_count"] == 2
    assert harness["current_sprint_execution_count"] == 1


def test_product_runtime_app_generate_uses_live_generator_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-generate")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-generate-1",
        task="Use a live generator slice to record one bounded implementation attempt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-generate-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-generate-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-live-generate-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-live-generate-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-app-runtime-live-generate-1",
        sprint_id="sprint-1",
        revision_notes=["keep the shell narrow"],
    )

    def _fake_execute_app_generate(**kwargs):
        assert str(kwargs.get("execution_summary") or "").strip()
        assert isinstance(kwargs.get("changed_target_hints"), list)
        assert "src/App.tsx" in (kwargs.get("memory_sources") or [])
        return DeliveryExecutionResult(
            execution_summary="Apply the bounded persistence revision before the next evaluator pass.",
            changed_target_hints=[
                "src/editor.tsx",
                "src/state/store.ts",
                "pytest tests/test_editor.py -q",
            ],
            artifact_root=str(tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-runtime-live-generate-1"),
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_app",
            preview_command="npm run dev",
            validation_command="pytest tests/test_editor.py -q",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute_app_generate)

    generate_payload = workbench.app_generate(
        task_id="product-app-runtime-live-generate-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    harness = generate_payload["canonical_views"]["app_harness"]
    assert generate_payload["app_generator_timeout_seconds"] == 45
    assert generate_payload["app_generator_max_completion_tokens"] == 220
    assert harness["latest_execution_attempt"]["execution_mode"] == "live"


def test_product_runtime_app_generate_persists_real_delivery_evidence_when_live_ready(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-delivery-evidence")
    session = workbench._initial_session(
        task_id="product-app-runtime-delivery-evidence-1",
        task="Use live generate to produce a real bounded delivery attempt.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-delivery-evidence-1",
        prompt="Build a stateful visual dependency explorer.",
    )
    workbench.app_retry(
        task_id="product-app-runtime-delivery-evidence-1",
        sprint_id="sprint-1",
        revision_notes=["Keep the first attempt narrow around state persistence."],
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)
    monkeypatch.setattr(
        workbench._delivery,
        "execute_app_generate",
        lambda **kwargs: (
            (
                lambda execution_summary: (
                    (_ for _ in ()).throw(AssertionError("missing derived execution focus"))
                    if not execution_summary.strip()
                    else DeliveryExecutionResult(
                        execution_summary="Implemented the first runnable dependency explorer shell.",
                        changed_target_hints=["src/App.tsx", "src/state/store.ts"],
                        changed_files=["index.html", "src/App.tsx", "src/state/store.ts"],
                        artifact_paths=["index.html", "package.json"],
                        artifact_kind="workspace_app",
                        preview_command="npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
                        validation_command="npm test",
                        validation_summary="Validation commands passed.",
                        validation_ok=True,
                    )
                )
            )(str(kwargs.get("execution_summary") or ""))
        ),
    )

    payload = workbench.app_generate(
        task_id="product-app-runtime-delivery-evidence-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    attempt = harness["latest_execution_attempt"]
    assert attempt["execution_mode"] == "live"
    assert attempt["artifact_kind"] == "workspace_app"
    assert attempt["artifact_path"] == "index.html"
    assert attempt["preview_command"] == "npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173"
    assert attempt["validation_command"] == "npm test"
    assert attempt["validation_summary"] == "Validation commands passed."
    assert attempt["changed_files"] == ["index.html", "src/App.tsx", "src/state/store.ts"]
    assert attempt["execution_target_kind"] == "revision"
    assert attempt["changed_target_hints"] == ["src/App.tsx", "src/state/store.ts"]
    assert attempt["execution_summary"] == "Implemented the first runnable dependency explorer shell."


def test_product_runtime_app_generate_runs_delivery_executor_inside_task_workspace(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-task-workspace")
    session = workbench._initial_session(
        task_id="product-app-runtime-task-workspace-1",
        task="Build the first real dependency explorer slice.",
        target_files=["src/App.tsx"],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-task-workspace-1",
        prompt="Build a stateful visual dependency explorer.",
        title="Dependency Explorer",
        app_type="desktop_like_web_app",
        stack=["React", "TypeScript"],
        features=["graph", "detail panel", "timeline"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-task-workspace-1",
        sprint_id="sprint-1",
        goal="Ship the first bounded explorer shell.",
        scope=["Create the first runnable explorer layout."],
        acceptance_checks=["echo workspace-validation-ok"],
        done_definition=["The task workspace contains a runnable React shell."],
    )

    root_dirs: list[str] = []

    def _invoke_delivery_task(
        *,
        system_parts,
        memory_sources,
        root_dir,
        task,
        timeout_seconds=None,
        trace_path="",
    ):
        root_dirs.append(str(root_dir or ""))
        assert task
        app_file = Path(root_dirs[-1]) / "src" / "App.tsx"
        app_file.write_text(
            app_file.read_text(encoding="utf-8") + "\nexport const runtimeIntegrated = true;\n",
            encoding="utf-8",
        )
        return "Implemented the first real dependency explorer shell in the task workspace."

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)
    monkeypatch.setattr(workbench._execution_host, "invoke_delivery_task", _invoke_delivery_task)

    payload = workbench.app_generate(
        task_id="product-app-runtime-task-workspace-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    workspace_root = (
        tmp_path
        / ".aionis-workbench"
        / "delivery-workspaces"
        / "product-app-runtime-task-workspace-1"
    )
    attempt = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert root_dirs == [str(workspace_root)]
    assert workspace_root.exists()
    assert (workspace_root / "src" / "App.tsx").exists()
    assert attempt["artifact_kind"] == "vite_dist"
    assert attempt["artifact_path"] == "dist/index.html"
    assert attempt["preview_command"] == f"python3 -m http.server 4173 --directory {workspace_root / 'dist'}"
    assert attempt["validation_command"].startswith('python3 -c ')
    assert attempt["validation_summary"] == "Validation failed: react app surface too sparse"
    assert attempt["changed_files"] == ["src/App.tsx"]
    assert attempt["artifact_root"] == str(workspace_root)


def test_product_runtime_app_generate_uses_delivery_first_contract_for_simple_web_tasks(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-delivery-contract")
    session = workbench._initial_session(
        task_id="product-app-runtime-delivery-contract-1",
        task="Build a simple web app artifact for a stateful dependency explorer.",
        target_files=["src/App.tsx"],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-delivery-contract-1",
        prompt="Build a stateful visual dependency explorer.",
        title="Dependency Explorer",
        app_type="desktop_like_web_app",
        stack=["React", "Vite", "TypeScript"],
        features=["graph", "detail panel", "timeline"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-delivery-contract-1",
        sprint_id="sprint-1",
        goal="Ship the first bounded explorer shell.",
        scope=["Create the first runnable explorer layout."],
        acceptance_checks=["npm run build"],
        done_definition=["The task workspace contains a runnable React shell."],
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute(**kwargs):
        captured["system_parts"] = list(kwargs.get("system_parts") or [])
        captured["task"] = str(kwargs.get("task") or "")
        return DeliveryExecutionResult(
            execution_summary="Implemented the first runnable dependency explorer shell.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["src/App.tsx", "src/styles.css"],
            artifact_paths=["index.html", "src/App.tsx"],
            artifact_kind="workspace_app",
            preview_command="npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute)

    workbench.app_generate(
        task_id="product-app-runtime-delivery-contract-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    system_prompt = "\n".join(str(item) for item in captured["system_parts"])
    delivery_task = str(captured["task"])
    assert "Leave behind a runnable artifact and keep the task workspace in a buildable state." in system_prompt
    assert "Prioritize visible UI, working interactions, and a clean build" in system_prompt
    assert "Product prompt: Build a stateful visual dependency explorer." in delivery_task
    assert "Sprint scope:\n- Create the first runnable explorer layout." in delivery_task
    assert "Done definition:\n- The task workspace contains a runnable React shell." in delivery_task
    assert "Acceptance checks:\n- npm run build" in delivery_task


def test_product_runtime_simple_web_generate_skips_live_summary_phase(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-direct-delivery")
    session = workbench._initial_session(
        task_id="product-app-runtime-direct-delivery-1",
        task="Build a simple delivery-first web artifact.",
        target_files=["src/App.tsx"],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-direct-delivery-1",
        prompt="Build a stateful visual dependency explorer.",
        title="Dependency Explorer",
        app_type="desktop_like_web_app",
        stack=["React", "Vite", "TypeScript"],
        features=["graph", "detail panel", "timeline"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-direct-delivery-1",
        sprint_id="sprint-1",
        goal="Ship the first bounded explorer shell.",
        scope=["Create the first runnable explorer layout."],
        acceptance_checks=["npm run build"],
        done_definition=["The task workspace contains a runnable React shell."],
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)
    monkeypatch.setattr(
        workbench._delivery,
        "execute_app_generate",
        lambda **_: DeliveryExecutionResult(
            execution_summary="Implemented the first runnable dependency explorer shell.",
            changed_target_hints=["src/App.tsx"],
            changed_files=["src/App.tsx"],
            artifact_paths=["index.html", "src/App.tsx"],
            artifact_kind="workspace_app",
            preview_command="npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        ),
    )

    payload = workbench.app_generate(
        task_id="product-app-runtime-direct-delivery-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    attempt = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert attempt["execution_mode"] == "live"
    assert attempt["execution_summary"] == "Implemented the first runnable dependency explorer shell."


def test_product_runtime_simple_web_generate_defaults_targets_and_build_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-simple-web-defaults")
    session = workbench._initial_session(
        task_id="product-app-runtime-simple-web-defaults-1",
        task="Build a simple visual explorer shell.",
        target_files=[],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-simple-web-defaults-1",
        prompt="Build a stateful visual dependency explorer.",
        title="Dependency Explorer",
        app_type="desktop_like_web_app",
        stack=["React", "Vite", "TypeScript"],
        features=["graph", "detail panel", "timeline"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-simple-web-defaults-1",
        sprint_id="sprint-1",
        goal="Ship the first bounded explorer shell.",
        scope=["Create the first runnable explorer layout."],
        acceptance_checks=[],
        done_definition=["The task workspace contains a runnable React shell."],
    )

    captured: dict[str, object] = {}
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute(**kwargs):
        captured["memory_sources"] = list(kwargs.get("memory_sources") or [])
        captured["validation_commands"] = list(kwargs.get("validation_commands") or [])
        return DeliveryExecutionResult(
            execution_summary="Implemented the first runnable dependency explorer shell.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["src/App.tsx", "src/styles.css"],
            artifact_paths=["index.html", "src/App.tsx"],
            artifact_kind="workspace_app",
            preview_command="npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute)

    workbench.app_generate(
        task_id="product-app-runtime-simple-web-defaults-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    assert captured["validation_commands"] == [
        "npm run build",
        'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
        'python3 -c "from pathlib import Path; p=Path(\'src/App.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'react app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
    ]


def test_product_runtime_simple_web_generate_overrides_generic_sprint_checks_with_build(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-simple-web-build-only")
    session = workbench._initial_session(
        task_id="product-app-runtime-simple-web-build-only-1",
        task="Build a modern landing page for an AI agent platform.",
        target_files=[],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-simple-web-build-only-1",
        prompt="Build a modern landing page for an AI agent platform.",
        title="Modern Landing Page",
        app_type="desktop_like_web_app",
        stack=["React", "Vite", "TypeScript"],
        features=["hero", "metrics", "cta"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-simple-web-build-only-1",
        sprint_id="sprint-1",
        goal="Ship the first runnable landing page.",
        scope=["Create the first complete landing page shell."],
        acceptance_checks=["npm test", "pytest -q"],
        done_definition=["The task workspace contains a complete landing page."],
    )

    captured: dict[str, object] = {}
    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)

    def _fake_execute(**kwargs):
        captured["validation_commands"] = list(kwargs.get("validation_commands") or [])
        captured["memory_sources"] = list(kwargs.get("memory_sources") or [])
        return DeliveryExecutionResult(
            execution_summary="Implemented the first runnable landing page.",
            changed_target_hints=["src/App.tsx", "src/styles.css"],
            changed_files=["src/App.tsx", "src/styles.css"],
            artifact_paths=["dist/index.html"],
            artifact_kind="vite_dist",
            preview_command="npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
            validation_command="npm run build",
            validation_summary="Validation commands passed.",
            validation_ok=True,
        )

    monkeypatch.setattr(workbench._delivery, "execute_app_generate", _fake_execute)

    workbench.app_generate(
        task_id="product-app-runtime-simple-web-build-only-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    assert captured["validation_commands"] == [
        "npm run build",
        'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); print(\'vite dist ok\' if p.exists() else \'missing dist/index.html\'); raise SystemExit(0 if p.exists() else 1)"',
        'python3 -c "from pathlib import Path; p=Path(\'src/App.tsx\'); s=p.read_text(encoding=\'utf-8\') if p.exists() else \'\'; markers=(\'<main\', \'<section\', \'<header\', \'<nav\', \'<aside\', \'<footer\', \'<article\', \'<div\'); text=s.lower(); hits=sum(1 for marker in markers if marker in text); label=\'react app surface\'; ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; print(f\'{label} ok\' if ok else f\'{label} too sparse\'); raise SystemExit(0 if ok else 1)"',
    ]
    assert captured["memory_sources"][:5] == [
        "package.json",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/styles.css",
    ]


def test_product_runtime_app_generate_offline_live_flag_bootstraps_task_workspace(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-offline-bootstrap")
    session = workbench._initial_session(
        task_id="product-app-runtime-offline-bootstrap-1",
        task="Bootstrap the first dependency explorer workspace without live credentials.",
        target_files=["src/App.tsx"],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-offline-bootstrap-1",
        prompt="Build a stateful visual dependency explorer.",
        title="Dependency Explorer",
        app_type="desktop_like_web_app",
        stack=["React", "TypeScript"],
        features=["graph", "detail panel", "timeline"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-offline-bootstrap-1",
        sprint_id="sprint-1",
        goal="Ship the first bounded explorer shell.",
        scope=["Create the first runnable explorer layout."],
        acceptance_checks=[],
        done_definition=["The task workspace contains a runnable React shell."],
    )

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: False)
    monkeypatch.setattr(
        workbench._delivery,
        "_run_workspace_validation_commands",
        lambda *, workspace_root, commands: ValidationResult(
            ok=True,
            command="npm run build",
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=sorted(workbench._delivery._workspace.snapshot_workspace_state(workspace_root=workspace_root).keys()),
        ),
    )
    payload = workbench.app_generate(
        task_id="product-app-runtime-offline-bootstrap-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    workspace_root = (
        tmp_path
        / ".aionis-workbench"
        / "delivery-workspaces"
        / "product-app-runtime-offline-bootstrap-1"
    )
    attempt = payload["canonical_views"]["app_harness"]["latest_execution_attempt"]
    assert workspace_root.exists()
    assert attempt["artifact_root"] == str(workspace_root)
    assert attempt["artifact_kind"] == "workspace_app"
    assert attempt["artifact_path"] == "index.html"
    assert attempt["preview_command"] == (
        f"cd {workspace_root} && npm install --no-fund --no-audit "
        "&& npm run dev -- --host 0.0.0.0 --port 4173"
    )
    assert attempt["validation_command"] == "npm run build"
    assert attempt["validation_summary"] == "Validation commands passed."


def test_product_runtime_app_export_copies_latest_task_workspace_artifact(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-export")
    session = workbench._initial_session(
        task_id="product-app-runtime-export-1",
        task="Build the first real dependency explorer slice.",
        target_files=["src/App.tsx"],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-export-1",
        prompt="Build a stateful visual dependency explorer.",
        title="Dependency Explorer",
        app_type="desktop_like_web_app",
        stack=["React", "TypeScript"],
        features=["graph", "detail panel", "timeline"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-export-1",
        sprint_id="sprint-1",
        goal="Ship the first bounded explorer shell.",
        scope=["Create the first runnable explorer layout."],
        acceptance_checks=["echo workspace-validation-ok"],
        done_definition=["The task workspace contains a runnable React shell."],
    )

    root_dirs: list[str] = []

    def _invoke_delivery_task(
        *,
        system_parts,
        memory_sources,
        root_dir,
        task,
        timeout_seconds=None,
        trace_path="",
    ):
        root_dirs.append(str(root_dir or ""))
        app_file = Path(root_dirs[-1]) / "src" / "App.tsx"
        app_file.write_text(
            app_file.read_text(encoding="utf-8") + "\nexport const exported = true;\n",
            encoding="utf-8",
        )
        return "Implemented the first real dependency explorer shell in the task workspace."

    monkeypatch.setattr(workbench._execution_host, "supports_live_tasks", lambda: True)
    monkeypatch.setattr(workbench._execution_host, "invoke_delivery_task", _invoke_delivery_task)

    workbench.app_generate(
        task_id="product-app-runtime-export-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    export_dir = tmp_path / "visible-export"
    payload = workbench.app_export(
        task_id="product-app-runtime-export-1",
        output_dir=str(export_dir),
    )

    assert payload["shell_view"] == "app_export"
    assert payload["controller_action_bar"] == {
        "task_id": "product-app-runtime-export-1",
        "status": "active",
        "recommended_command": "/next product-app-runtime-export-1",
        "allowed_commands": [
            "/next product-app-runtime-export-1",
            "/show product-app-runtime-export-1",
            "/session product-app-runtime-export-1",
        ],
    }
    assert payload["export_root"] == str(export_dir)
    assert payload["entrypoint"] == str(export_dir / "dist" / "index.html")
    assert payload["preview_command"] == f"python3 -m http.server 4173 --directory {export_dir / 'dist'}"
    assert payload["development_command"] == f"cd {export_dir} && npm install && npm run dev -- --host 0.0.0.0 --port 4173"
    assert (export_dir / "src" / "App.tsx").exists()
    assert "exported = true" in (export_dir / "src" / "App.tsx").read_text(encoding="utf-8")
    assert (export_dir / "README.md").exists()


def test_product_runtime_app_export_falls_back_to_task_workspace_when_artifact_root_is_empty(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-export-fallback")
    session = workbench._initial_session(
        task_id="product-app-runtime-export-fallback-1",
        task="Export the current task workspace even after a failed live attempt.",
        target_files=["src/App.tsx"],
        validation_commands=[],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-export-fallback-1",
        prompt="Build a modern landing page for an AI agent platform.",
    )
    workspace_root = tmp_path / ".aionis-workbench" / "delivery-workspaces" / "product-app-runtime-export-fallback-1"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "index.html").write_text("<!doctype html><html><body>fallback</body></html>", encoding="utf-8")
    workbench.app_generate(
        task_id="product-app-runtime-export-fallback-1",
        sprint_id="sprint-1",
        execution_summary="Attempt the first landing page shell.",
        changed_target_hints=["src/App.tsx"],
        use_live_generator=False,
    )
    session = workbench._load_required_session(task_id="product-app-runtime-export-fallback-1")
    session.app_harness_state.latest_execution_attempt.artifact_root = ""
    session.app_harness_state.latest_execution_attempt.artifact_path = "index.html"
    workbench._save_session(session)

    export_dir = tmp_path / "fallback-export"
    payload = workbench.app_export(
        task_id="product-app-runtime-export-fallback-1",
        output_dir=str(export_dir),
    )

    assert payload["export_root"] == str(export_dir)
    assert (export_dir / "index.html").exists()


def test_product_app_export_uses_static_demo_artifact_path_when_artifact_root_is_empty(tmp_path) -> None:
    artifact_dir = (
        tmp_path
        / ".aionis-workbench"
        / "artifacts"
        / "artifact-export-static-demo-1"
        / "sprint-1-attempt-1"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "index.html").write_text(
        "<!doctype html><html><body>static demo</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("repo root should not be exported\n", encoding="utf-8")

    session = SessionState(
        task_id="artifact-export-static-demo-1",
        goal="Export a static demo artifact.",
        repo_root=str(tmp_path),
        app_harness_state=AppHarnessState(
            latest_execution_attempt=SprintExecutionAttempt(
                attempt_id="sprint-1-attempt-1",
                sprint_id="sprint-1",
                execution_target_kind="sprint",
                execution_mode="deterministic",
                execution_summary="Deterministic demo artifact.",
                changed_target_hints=["landing page"],
                changed_files=[],
                artifact_root="",
                artifact_kind="static_html_demo",
                artifact_path=".aionis-workbench/artifacts/artifact-export-static-demo-1/sprint-1-attempt-1/index.html",
                preview_command=f"python3 -m http.server 4173 --directory {artifact_dir}",
                validation_command="",
                validation_summary="",
                success=True,
                status="qa_passed",
            )
        ),
    )

    export_dir = tmp_path / "static-demo-export"
    payload = export_latest_app_artifact(session=session, output_dir=str(export_dir))

    assert payload["export_root"] == str(export_dir)
    assert payload["entrypoint"] == str(export_dir / "index.html")
    assert (export_dir / "index.html").exists()
    assert (export_dir / "README.md").exists()
    assert not (export_dir / ".aionis-workbench").exists()


def test_product_app_export_prefers_built_dist_and_skips_node_modules(tmp_path) -> None:
    workspace_root = tmp_path / "artifact-root"
    (workspace_root / "src").mkdir(parents=True)
    (workspace_root / "dist").mkdir(parents=True)
    (workspace_root / "node_modules" / ".bin").mkdir(parents=True)
    (workspace_root / "index.html").write_text("<!doctype html><html><body>source</body></html>", encoding="utf-8")
    (workspace_root / "dist" / "index.html").write_text("<!doctype html><html><body>built</body></html>", encoding="utf-8")
    (workspace_root / "package.json").write_text(
        json.dumps({"name": "artifact-root", "scripts": {"dev": "vite", "build": "vite build"}}),
        encoding="utf-8",
    )
    (workspace_root / "src" / "App.tsx").write_text("export default function App() { return null; }\n", encoding="utf-8")
    (workspace_root / "node_modules" / ".bin" / "vite").write_text("broken", encoding="utf-8")

    session = SessionState(
        task_id="artifact-export-built-1",
        goal="Export a built app artifact.",
        repo_root=str(tmp_path),
        app_harness_state=AppHarnessState(
            latest_execution_attempt=SprintExecutionAttempt(
                attempt_id="sprint-1-attempt-1",
                sprint_id="sprint-1",
                execution_target_kind="sprint",
                execution_mode="live",
                execution_summary="Built the dependency explorer export.",
                changed_target_hints=["src/App.tsx"],
                changed_files=["src/App.tsx"],
                artifact_root=str(workspace_root),
                artifact_kind="workspace_app",
                artifact_path="index.html",
                preview_command=f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173",
                validation_command="npm run build",
                validation_summary="Validation commands passed.",
            )
        ),
    )

    export_dir = tmp_path / "visible-export-built"
    payload = export_latest_app_artifact(session=session, output_dir=str(export_dir))

    assert payload["entrypoint"] == str(export_dir / "dist" / "index.html")
    assert payload["preview_command"] == f"python3 -m http.server 4173 --directory {export_dir / 'dist'}"
    assert payload["development_command"] == f"cd {export_dir} && npm install && npm run dev -- --host 0.0.0.0 --port 4173"
    assert not (export_dir / "node_modules").exists()


def test_product_app_export_uses_python_api_entrypoint_and_development_command(tmp_path) -> None:
    workspace_root = tmp_path / "python-api-root"
    workspace_root.mkdir(parents=True)
    (workspace_root / "requirements.txt").write_text("fastapi==0.116.1\nuvicorn==0.35.0\n", encoding="utf-8")
    (workspace_root / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

    session = SessionState(
        task_id="artifact-export-python-api-1",
        goal="Export a Python API artifact.",
        repo_root=str(tmp_path),
        app_harness_state=AppHarnessState(
            latest_execution_attempt=SprintExecutionAttempt(
                attempt_id="sprint-1-attempt-1",
                sprint_id="sprint-1",
                execution_target_kind="sprint",
                execution_mode="live",
                execution_summary="Built the API service export.",
                changed_target_hints=["main.py"],
                changed_files=["main.py"],
                artifact_root=str(workspace_root),
                artifact_kind="python_api_workspace",
                artifact_path="main.py",
                preview_command="python3 -m uvicorn main:app --host 0.0.0.0 --port 4173",
                validation_command="python3 -m py_compile main.py",
                validation_summary="Validation commands passed.",
            )
        ),
    )

    export_dir = tmp_path / "visible-export-python-api"
    payload = export_latest_app_artifact(session=session, output_dir=str(export_dir))

    assert payload["entrypoint"] == str(export_dir / "main.py")
    assert payload["preview_command"] == (
        "python3 -m pip install -r requirements.txt && "
        "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
    )
    assert payload["development_command"] == (
        f"cd {export_dir} && python3 -m pip install -r requirements.txt && "
        "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
    )


def test_product_app_export_uses_node_api_entrypoint_and_development_command(tmp_path) -> None:
    workspace_root = tmp_path / "node-api-root"
    workspace_root.mkdir(parents=True)
    (workspace_root / "package.json").write_text(
        json.dumps(
            {
                "name": "node-api-root",
                "private": True,
                "version": "0.0.0",
                "type": "module",
                "scripts": {"dev": "node main.js", "start": "node main.js"},
                "dependencies": {"express": "^4.21.2"},
            }
        ),
        encoding="utf-8",
    )
    (workspace_root / "main.js").write_text("import express from 'express';\nconst app = express();\n", encoding="utf-8")

    session = SessionState(
        task_id="artifact-export-node-api-1",
        goal="Export a Node API artifact.",
        repo_root=str(tmp_path),
        app_harness_state=AppHarnessState(
            latest_execution_attempt=SprintExecutionAttempt(
                attempt_id="sprint-1-attempt-1",
                sprint_id="sprint-1",
                execution_target_kind="sprint",
                execution_mode="live",
                execution_summary="Built the Node API service export.",
                changed_target_hints=["main.js"],
                changed_files=["main.js"],
                artifact_root=str(workspace_root),
                artifact_kind="node_api_workspace",
                artifact_path="main.js",
                preview_command="npm run dev",
                validation_command="node --check main.js",
                validation_summary="Validation commands passed.",
            )
        ),
    )

    export_dir = tmp_path / "visible-export-node-api"
    payload = export_latest_app_artifact(session=session, output_dir=str(export_dir))

    assert payload["entrypoint"] == str(export_dir / "main.js")
    assert payload["preview_command"] == "npm install --no-fund --no-audit && npm run dev"
    assert payload["development_command"] == f"cd {export_dir} && npm install --no-fund --no-audit && npm run dev"


def test_product_runtime_app_qa_can_auto_derive_status_and_summary(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-auto-qa")
    session = workbench._initial_session(
        task_id="product-app-runtime-auto-qa-1",
        task="Let contract-driven app qa derive the evaluator result.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-auto-qa-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-auto-qa-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-auto-qa-1",
        sprint_id="sprint-1",
        blocker_notes=["palette resets on refresh"],
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["status"] == "failed"
    assert harness["latest_sprint_evaluation"]["evaluator_mode"] == "contract_driven"
    assert harness["latest_sprint_evaluation"]["failing_criteria"] == ["functionality", "design_quality"]
    assert harness["latest_sprint_evaluation"]["summary"] == (
        "Ship the editor shell. still fails functionality, design_quality; palette resets on refresh"
    )
    assert harness["loop_status"] == "needs_revision"


def test_product_runtime_app_qa_auto_uses_latest_execution_attempt_context(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-auto-qa-execution")
    session = workbench._initial_session(
        task_id="product-app-runtime-auto-qa-execution-1",
        task="Let contract-driven app qa consume the latest execution attempt context.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-auto-qa-execution-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-auto-qa-execution-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_generate(
        task_id="product-app-runtime-auto-qa-execution-1",
        sprint_id="sprint-1",
        execution_summary="Apply the bounded shell persistence fix.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-auto-qa-execution-1",
        sprint_id="sprint-1",
        blocker_notes=["palette resets on refresh"],
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["summary"] == (
        "Ship the editor shell. after Apply the bounded shell persistence fix. still fails functionality, design_quality; palette resets on refresh"
    )
    assert harness["latest_execution_attempt"]["status"] == "qa_failed"
    assert harness["latest_execution_attempt"]["success"] is False
    assert harness["latest_sprint_evaluation"]["criteria_scores"]["functionality"] > 0.6
    assert harness["latest_sprint_evaluation"]["criteria_scores"]["design_quality"] > 0.6


def test_product_runtime_app_plan_infers_product_spec_from_prompt_only(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-autoplan")
    session = workbench._initial_session(
        task_id="product-app-runtime-autoplan-1",
        task="Infer app harness planning defaults from prompt-only input.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    plan_payload = workbench.app_plan(
        task_id="product-app-runtime-autoplan-1",
        prompt="Build a visual dependency explorer for async task orchestration.",
    )
    inspect_payload = workbench.inspect_session(task_id="product-app-runtime-autoplan-1")

    assert plan_payload["shell_view"] == "app_plan"
    harness = inspect_payload["canonical_views"]["app_harness"]
    assert harness["product_spec"]["title"] == "Visual Dependency Explorer"
    assert harness["product_spec"]["app_type"] == "desktop_like_web_app"
    assert harness["product_spec"]["stack"] == ["React", "Vite", "SQLite"]
    assert harness["product_spec"]["feature_groups"] == [
        "core_workflow",
        "supporting_workflows",
        "system_foundations",
    ]
    assert harness["product_spec"]["feature_count"] == 3
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1"
    assert harness["active_sprint_contract"]["approved"] is False
    assert harness["planned_sprint_contracts"][0]["sprint_id"] == "sprint-2"
    assert len(harness["planning_rationale"]) == 4
    assert len(harness["sprint_negotiation_notes"]) == 3
    assert harness["evaluator_criteria_count"] == 3
    assert harness["loop_status"] == "sprint_proposed"


def test_product_runtime_app_plan_uses_live_planner_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-planner")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-1",
        task="Use a live planner slice to produce the initial app harness artifacts.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    monkeypatch.setattr(
        workbench._execution_host,
        "plan_app_live",
        lambda *, prompt: {
            "title": "Atlas Board",
            "app_type": "desktop_like_web_app",
            "stack": ["React", "Vite", "SQLite"],
            "features": ["dependency board", "async lane", "project workspace"],
            "design_direction": "dense operator board with clear lanes and high-signal panels",
            "planning_rationale": [
                "Lead with the dependency board so the product intent is legible immediately.",
                "Keep async lane work in the initial release path because it validates orchestration depth.",
            ],
            "sprint_1": {
                "goal": "Ship the first usable dependency board workflow.",
                "scope": ["dependency board", "async lane", "navigation shell"],
                "acceptance_checks": ["npm test"],
                "done_definition": [
                    "dependency board is interactive",
                    "async lane explains orchestration state",
                    "navigation shell is coherent",
                ],
            },
        },
    )

    plan_payload = workbench.app_plan(
        task_id="product-app-runtime-live-1",
        prompt="Build a visual dependency explorer for async task orchestration.",
        use_live_planner=True,
    )
    inspect_payload = workbench.inspect_session(task_id="product-app-runtime-live-1")

    assert plan_payload["planner_mode"] == "live"
    assert plan_payload["app_planner_timeout_seconds"] == workbench._execution_host.live_app_planner_timeout_seconds()
    assert (
        plan_payload["app_planner_max_completion_tokens"]
        == workbench._execution_host.live_app_planner_max_completion_tokens()
    )
    harness = inspect_payload["canonical_views"]["app_harness"]
    assert harness["planner_mode"] == "live"
    assert harness["product_spec"]["title"] == "Atlas Board"
    assert harness["product_spec"]["feature_groups"] == [
        "core_workflow",
        "supporting_workflows",
        "system_foundations",
    ]
    assert harness["active_sprint_contract"]["goal"] == "Ship the first usable dependency board workflow."
    assert harness["active_sprint_contract"]["proposed_by"] == "live_planner"
    assert harness["planned_sprint_contracts"][0]["sprint_id"] == "sprint-2"
    assert harness["planning_rationale"][0] == (
        "Lead with the dependency board so the product intent is legible immediately."
    )
    assert len(harness["sprint_negotiation_notes"]) == 3


def test_product_runtime_app_qa_uses_live_evaluator_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-evaluator")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-eval-1",
        task="Use a live evaluator slice to score the active sprint.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-eval-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-eval-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(
        workbench._execution_host,
        "evaluate_sprint_live",
        lambda **_: {
            "status": "failed",
            "summary": "The shell is usable, but palette persistence still fails the evaluator bar.",
            "passing_criteria": ["design_quality"],
            "failing_criteria": ["functionality"],
            "blocker_notes": ["palette resets on refresh"],
            "criteria_scores": {"functionality": 0.61, "design_quality": 0.79},
        },
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-live-eval-1",
        sprint_id="sprint-1",
        use_live_evaluator=True,
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert qa_payload["app_evaluator_timeout_seconds"] == 45
    assert qa_payload["app_evaluator_max_completion_tokens"] == 180
    assert harness["latest_sprint_evaluation"]["status"] == "failed"
    assert harness["latest_sprint_evaluation"]["evaluator_mode"] == "live"
    assert harness["latest_sprint_evaluation"]["passing_criteria"] == ["design_quality"]
    assert harness["latest_sprint_evaluation"]["failing_criteria"] == ["functionality"]


def test_product_runtime_app_qa_passes_latest_execution_attempt_to_live_evaluator(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-evaluator-execution")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-eval-execution-1",
        task="Pass the latest execution attempt into the live evaluator slice.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-eval-execution-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-eval-execution-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_generate(
        task_id="product-app-runtime-live-eval-execution-1",
        sprint_id="sprint-1",
        execution_summary="Apply the bounded shell persistence fix.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )

    def _fake_live_evaluator(**kwargs):
        latest_execution_attempt = kwargs.get("latest_execution_attempt") or {}
        assert latest_execution_attempt["attempt_id"] == "sprint-1-attempt-1"
        assert latest_execution_attempt["execution_summary"] == "Apply the bounded shell persistence fix."
        assert latest_execution_attempt["changed_target_hints"] == ["src/editor.tsx", "src/state/store.ts"]
        assert latest_execution_attempt["status"] == "recorded"
        assert latest_execution_attempt["success"] is None
        assert kwargs.get("execution_focus") == "Apply the bounded shell persistence fix."
        return {
            "status": "failed",
            "summary": "The shell is usable, but palette persistence still fails the evaluator bar.",
            "passing_criteria": ["design_quality"],
            "failing_criteria": ["functionality"],
            "blocker_notes": ["palette resets on refresh"],
            "criteria_scores": {"functionality": 0.61, "design_quality": 0.79},
        }

    monkeypatch.setattr(workbench._execution_host, "evaluate_sprint_live", _fake_live_evaluator)

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-live-eval-execution-1",
        sprint_id="sprint-1",
        use_live_evaluator=True,
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["evaluator_mode"] == "live"
    assert harness["latest_sprint_evaluation"]["summary"] == (
        "The shell is usable, but palette persistence still fails the evaluator bar."
    )
    assert harness["latest_execution_attempt"]["status"] == "qa_failed"
    assert harness["latest_execution_attempt"]["success"] is False


def test_product_runtime_second_replanned_app_qa_passes_execution_focus_to_live_evaluator(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-second-replanned-live-eval")
    session = workbench._initial_session(
        task_id="product-app-runtime-second-replanned-live-eval-1",
        task="Pass second-cycle execution focus into the live evaluator slice.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    _prepare_second_replan_transition_state(
        workbench,
        task_id="product-app-runtime-second-replanned-live-eval-1",
    )
    workbench.app_replan(
        task_id="product-app-runtime-second-replanned-live-eval-1",
        sprint_id="sprint-1-replan-1",
        note="narrow again around hydration and persistence",
    )
    workbench.app_generate(
        task_id="product-app-runtime-second-replanned-live-eval-1",
        sprint_id="sprint-1-replan-1-replan-1",
        execution_summary="Patch the final hydration edge on the second replanned sprint.",
        changed_target_hints=["src/state/hydration.ts", "src/state/persistence.ts"],
    )

    def _fake_second_live_evaluator(**kwargs):
        latest_execution_attempt = kwargs.get("latest_execution_attempt") or {}
        assert latest_execution_attempt["sprint_id"] == "sprint-1-replan-1-replan-1"
        assert latest_execution_attempt["execution_summary"] == (
            "Patch the final hydration edge on the second replanned sprint."
        )
        assert kwargs.get("execution_focus") == "Patch the final hydration edge on the second replanned sprint."
        return {
            "status": "passed",
            "summary": "The second replanned sprint closes the last hydration edge and clears the evaluator bar.",
            "passing_criteria": ["functionality", "design_quality"],
            "failing_criteria": [],
            "blocker_notes": [],
            "criteria_scores": {"functionality": 0.89, "design_quality": 0.84},
        }

    monkeypatch.setattr(workbench._execution_host, "evaluate_sprint_live", _fake_second_live_evaluator)

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-second-replanned-live-eval-1",
        sprint_id="sprint-1-replan-1-replan-1",
        use_live_evaluator=True,
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["evaluator_mode"] == "live"
    assert harness["latest_sprint_evaluation"]["status"] == "passed"
    assert harness["latest_execution_attempt"]["status"] == "qa_passed"


def test_product_runtime_app_qa_normalizes_string_blocker_notes_from_live_evaluator(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-evaluator-blocker-normalize")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-eval-blocker-normalize-1",
        task="Normalize string blocker notes from the live evaluator.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-eval-blocker-normalize-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-eval-blocker-normalize-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )

    monkeypatch.setattr(
        workbench._execution_host,
        "evaluate_sprint_live",
        lambda **_: {
            "status": "failed",
            "summary": "The shell is usable, but palette persistence still fails the evaluator bar.",
            "passing_criteria": "design_quality",
            "failing_criteria": "functionality",
            "blocker_notes": "Execution path still loses palette state after refresh.",
            "criteria_scores": {"functionality": 0.61, "design_quality": 0.79},
        },
    )

    qa_payload = workbench.app_qa(
        task_id="product-app-runtime-live-eval-blocker-normalize-1",
        sprint_id="sprint-1",
        use_live_evaluator=True,
    )

    harness = qa_payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["passing_criteria"] == ["design_quality"]
    assert harness["latest_sprint_evaluation"]["failing_criteria"] == ["functionality"]
    assert harness["latest_sprint_evaluation"]["blocker_notes"] == [
        "Execution path still loses palette state after refresh."
    ]


def test_product_runtime_live_profile_prefers_repo_local_snapshot_metadata(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-live-profile-repo-local")
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    repo_home = tmp_path / ".real-live-home"
    save_live_profile_snapshot(
        {
            "provider_id": "zai_glm51_coding",
            "model": "glm-5.1",
            "timeout_seconds": 15,
            "max_completion_tokens": 256,
            "live_mode": "targeted_fix",
            "recorded_at": "2026-04-05T00:00:00Z",
            "scenario_id": "live-app-plan",
            "timing_summary": "task=task-1 ready=1.000s total=1.000s",
            "execution_focus": "Patch the persistence edge before retrying the evaluator.",
            "execution_gate": "ready",
            "execution_gate_transition": "needs_qa->ready",
            "execution_outcome_ready": True,
            "last_policy_action": "qa:passed",
        },
        home=repo_home,
    )

    payload = workbench.live_profile()

    assert payload["provider_id"] == "zai_glm51_coding"
    assert payload["provider_label"] == "Z.AI GLM-5.1 Coding"
    assert payload["model"] == "glm-5.1"
    assert payload["timeout_seconds"] == 15
    assert payload["latest_recorded_at"] == "2026-04-05T00:00:00Z"
    assert payload["latest_execution_focus"] == "Patch the persistence edge before retrying the evaluator."
    assert payload["latest_execution_gate"] == "ready"
    assert payload["latest_execution_gate_transition"] == "needs_qa->ready"
    assert payload["latest_execution_outcome_ready"] is True
    assert payload["latest_last_policy_action"] == "qa:passed"
    assert payload["latest_convergence_signal"] == "live-app-plan:needs_qa->ready@qa:passed"
    assert payload["recent_convergence_signals"] == ["live-app-plan:needs_qa->ready@qa:passed"]
    assert payload["latest_profile_path"].endswith("/.real-live-home/.aionis/workbench/live_profile.json")


def test_product_runtime_live_profile_uses_configured_openrouter_model_when_snapshot_is_missing(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    (tmp_path / ".aionis-workbench").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENROUTER_API_KEY=present",
                "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1",
                "OPENROUTER_MODEL=z-ai/glm-5.1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/live-profile-openrouter-{str(tmp_path).replace('/', '_')}")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("WORKBENCH_MODEL", raising=False)
    monkeypatch.delenv("AIONIS_PROVIDER_PROFILE", raising=False)

    workbench = AionisWorkbench(repo_root=str(tmp_path), load_env=True)

    payload = workbench.live_profile()

    assert payload["provider_id"] == "openrouter_default"
    assert payload["model"] == "z-ai/glm-5.1"
    assert payload["timeout_seconds"] == 45


def test_product_runtime_ab_test_compare_summarizes_current_task_against_baseline(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-ab-test-compare")
    session = workbench._initial_session(
        task_id="product-ab-1",
        task="Recover a persistence bug and compare against a thin loop baseline.",
        target_files=["src/editor.tsx"],
        validation_commands=["true"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-ab-1",
        prompt="Recover a persistence bug and keep the sprint narrow.",
        title="Stateful Editor",
        app_type="full_stack_app",
        stack=["React"],
        features=["persistence"],
        criteria=["functionality:0.8"],
    )
    workbench.app_sprint(
        task_id="product-ab-1",
        sprint_id="sprint-1",
        goal="Fix persistence without widening the sprint.",
        scope=["persistence"],
        acceptance_checks=["pytest -q"],
        done_definition=["persistence restored"],
        approved=True,
    )
    workbench.app_generate(
        task_id="product-ab-1",
        sprint_id="sprint-1",
        execution_summary="Apply the second bounded persistence patch.",
        changed_target_hints=["src/editor.tsx"],
    )
    workbench.app_qa(
        task_id="product-ab-1",
        sprint_id="sprint-1",
        status="passed",
        summary="Second replanned sprint passed QA and can advance.",
    )

    repo_home = tmp_path / ".real-live-home"
    save_live_profile_snapshot(
        {
            "provider_id": "zai_glm51_coding",
            "model": "glm-5.1",
            "scenario_id": "live-app-second-replan-generate-qa-advance",
            "execution_gate_transition": "needs_qa->ready",
            "last_policy_action": "qa:passed",
            "total_duration_seconds": 381.92,
        },
        home=repo_home,
    )

    payload = workbench.ab_test_compare(
        task_id="product-ab-1",
        scenario_id="scenario-1",
        baseline_ended_in="escalate",
        baseline_duration_seconds=120.5,
        baseline_retry_count=1,
        baseline_convergence_signal="baseline:needs_qa->qa_failed@qa:failed",
        baseline_final_execution_gate="qa_failed",
        baseline_gate_flow="needs_qa->qa_failed@qa:failed",
        baseline_escalated=True,
    )

    assert payload["shell_view"] == "ab_test_compare"
    assert payload["comparison"]["winner"] == "aionis"
    assert payload["baseline"]["ended_in"] == "escalate"
    assert payload["aionis"]["latest_convergence_signal"] == "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed"


def test_product_runtime_app_negotiate_uses_live_planner_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-negotiate")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-negotiate-1",
        task="Use a live planner slice to revise the sprint after evaluator objections.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-negotiate-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-negotiate-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-live-negotiate-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )

    monkeypatch.setattr(
        workbench._execution_host,
        "negotiate_sprint_live",
        lambda **_: {
            "recommended_action": "revise_current_sprint",
            "planner_response": [
                "Revise sprint-1 around palette persistence before expanding the surface area.",
                "Keep sprint-1 tied to the existing acceptance check until refresh behavior is stable.",
            ],
            "sprint_negotiation_notes": [
                "Evaluator should re-check palette persistence before approving follow-up scope.",
                "Do not approve sprint-2 until the editor shell survives refresh.",
            ],
        },
    )

    negotiate_payload = workbench.app_negotiate(
        task_id="product-app-runtime-live-negotiate-1",
        sprint_id="sprint-1",
        use_live_planner=True,
    )

    harness = negotiate_payload["canonical_views"]["app_harness"]
    assert negotiate_payload["app_negotiator_timeout_seconds"] == 45
    assert negotiate_payload["app_negotiator_max_completion_tokens"] == 180
    assert harness["latest_negotiation_round"]["planner_mode"] == "live"
    assert harness["latest_negotiation_round"]["recommended_action"] == "revise_current_sprint"
    assert harness["latest_negotiation_round"]["planner_response"] == [
        "Revise sprint-1 around palette persistence before expanding the surface area.",
        "Keep sprint-1 tied to the existing acceptance check until refresh behavior is stable.",
    ]
    assert harness["sprint_negotiation_notes"] == [
        "Evaluator should re-check palette persistence before approving follow-up scope.",
        "Do not approve sprint-2 until the editor shell survives refresh.",
    ]


def test_product_runtime_app_retry_uses_live_planner_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-app-runtime-live-retry")
    session = workbench._initial_session(
        task_id="product-app-runtime-live-retry-1",
        task="Use a live planner slice to derive one bounded sprint revision.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)

    workbench.app_plan(
        task_id="product-app-runtime-live-retry-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-app-runtime-live-retry-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-app-runtime-live-retry-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-app-runtime-live-retry-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )

    monkeypatch.setattr(
        workbench._execution_host,
        "revise_sprint_live",
        lambda **_: {
            "revision_summary": "Tighten sprint-1 around palette persistence before broadening the surface.",
            "must_fix": [
                "Resolve failing criterion: functionality.",
                "timeline entries reset on refresh",
                "palette resets on refresh",
            ],
            "must_keep": [
                "pytest tests/test_editor.py -q",
                "editor loads",
                "design_quality",
            ],
        },
    )

    retry_payload = workbench.app_retry(
        task_id="product-app-runtime-live-retry-1",
        sprint_id="sprint-1",
        revision_notes=["keep the shell narrow"],
        use_live_planner=True,
    )

    harness = retry_payload["canonical_views"]["app_harness"]
    assert retry_payload["app_revisor_timeout_seconds"] == 45
    assert retry_payload["app_revisor_max_completion_tokens"] == 180
    assert harness["latest_revision"]["planner_mode"] == "live"
    assert harness["latest_revision"]["revision_id"] == "sprint-1-revision-1"
    assert harness["latest_revision"]["revision_summary"] == (
        "Tighten sprint-1 around palette persistence before broadening the surface."
    )
    assert harness["latest_revision"]["must_fix"] == [
        "Resolve failing criterion: functionality.",
        "timeline entries reset on refresh",
        "palette resets on refresh",
    ]
    assert harness["latest_revision"]["must_keep"] == [
        "pytest tests/test_editor.py -q",
        "editor loads",
        "design_quality",
    ]
    assert harness["retry_count"] == 1
    assert harness["loop_status"] == "revision_recorded"


def test_product_runtime_app_plan_uses_openai_agents_host_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_openai_agents_workbench(tmp_path, monkeypatch, label="product-openai-agents-live-planner")
    session = workbench._initial_session(
        task_id="product-openai-agents-live-planner-1",
        task="Use the openai-agents execution host to produce the initial app plan.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    captures: list[dict[str, str]] = []
    _stub_openai_agents_json_runtime(
        monkeypatch,
        workbench,
        responses={
            "Workbench live planner": {
                "title": "Atlas Board",
                "app_type": "desktop_like_web_app",
                "stack": ["React", "Vite", "SQLite"],
                "features": ["dependency board", "async lane", "project workspace"],
                "design_direction": "dense operator board with clear lanes",
                "planning_rationale": [
                    "Lead with the dependency board so the product intent is legible immediately.",
                    "Keep async lane work in the initial release path because it validates orchestration depth.",
                ],
                "sprint_1": {
                    "goal": "Ship the first usable dependency board workflow.",
                    "scope": ["dependency board", "async lane", "navigation shell"],
                    "acceptance_checks": ["npm test"],
                    "done_definition": [
                        "dependency board is interactive",
                        "async lane explains orchestration state",
                    ],
                },
            }
        },
        captures=captures,
    )

    payload = workbench.app_plan(
        task_id="product-openai-agents-live-planner-1",
        prompt="Build a visual dependency explorer for async task orchestration.",
        use_live_planner=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert payload["planner_mode"] == "live"
    assert harness["planner_mode"] == "live"
    assert harness["product_spec"]["title"] == "Atlas Board"
    assert harness["active_sprint_contract"]["proposed_by"] == "live_planner"
    assert captures[0]["name"] == "Workbench live planner"
    assert "Project request: Build a visual dependency explorer for async task orchestration." in captures[0]["user_input"]


def test_product_runtime_app_qa_uses_openai_agents_host_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_openai_agents_workbench(tmp_path, monkeypatch, label="product-openai-agents-live-evaluator")
    session = workbench._initial_session(
        task_id="product-openai-agents-live-evaluator-1",
        task="Use the openai-agents execution host to score the active sprint.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    workbench.app_plan(
        task_id="product-openai-agents-live-evaluator-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-openai-agents-live-evaluator-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    captures: list[dict[str, str]] = []

    def _fake_evaluator(_agent, user_input):
        payload = json.loads(user_input)
        assert payload["requested_status"] == "auto"
        assert payload["sprint_contract"]["sprint_id"] == "sprint-1"
        return {
            "status": "failed",
            "summary": "The shell is usable, but palette persistence still fails the evaluator bar.",
            "passing_criteria": ["design_quality"],
            "failing_criteria": ["functionality"],
            "blocker_notes": ["palette resets on refresh"],
            "criteria_scores": {"functionality": 0.61, "design_quality": 0.79},
        }

    _stub_openai_agents_json_runtime(
        monkeypatch,
        workbench,
        responses={"Workbench live evaluator": _fake_evaluator},
        captures=captures,
    )

    payload = workbench.app_qa(
        task_id="product-openai-agents-live-evaluator-1",
        sprint_id="sprint-1",
        use_live_evaluator=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["latest_sprint_evaluation"]["evaluator_mode"] == "live"
    assert harness["latest_sprint_evaluation"]["status"] == "failed"
    assert harness["latest_sprint_evaluation"]["failing_criteria"] == ["functionality"]
    assert captures[0]["name"] == "Workbench live evaluator"


def test_product_runtime_app_negotiate_uses_openai_agents_host_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_openai_agents_workbench(tmp_path, monkeypatch, label="product-openai-agents-live-negotiate")
    session = workbench._initial_session(
        task_id="product-openai-agents-live-negotiate-1",
        task="Use the openai-agents execution host to negotiate the current sprint.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    workbench.app_plan(
        task_id="product-openai-agents-live-negotiate-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-openai-agents-live-negotiate-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-openai-agents-live-negotiate-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )

    def _fake_negotiator(_agent, user_input):
        payload = json.loads(user_input)
        assert payload["sprint_contract"]["sprint_id"] == "sprint-1"
        assert payload["objections"] == ["timeline entries reset on refresh"]
        return {
            "recommended_action": "revise_current_sprint",
            "planner_response": [
                "Revise sprint-1 around palette persistence before expanding the surface area.",
                "Keep sprint-1 tied to the existing acceptance check until refresh behavior is stable.",
            ],
            "sprint_negotiation_notes": [
                "Evaluator should re-check palette persistence before approving follow-up scope.",
                "Do not approve sprint-2 until the editor shell survives refresh.",
            ],
        }

    _stub_openai_agents_json_runtime(
        monkeypatch,
        workbench,
        responses={"Workbench live negotiator": _fake_negotiator},
    )

    payload = workbench.app_negotiate(
        task_id="product-openai-agents-live-negotiate-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
        use_live_planner=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["latest_negotiation_round"]["planner_mode"] == "live"
    assert harness["latest_negotiation_round"]["recommended_action"] == "revise_current_sprint"
    assert harness["sprint_negotiation_notes"][0] == (
        "Evaluator should re-check palette persistence before approving follow-up scope."
    )


def test_product_runtime_app_retry_uses_openai_agents_host_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_openai_agents_workbench(tmp_path, monkeypatch, label="product-openai-agents-live-retry")
    session = workbench._initial_session(
        task_id="product-openai-agents-live-retry-1",
        task="Use the openai-agents execution host to derive one bounded sprint revision.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    workbench.app_plan(
        task_id="product-openai-agents-live-retry-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-openai-agents-live-retry-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-openai-agents-live-retry-1",
        sprint_id="sprint-1",
        status="failed",
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-openai-agents-live-retry-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )

    def _fake_revisor(_agent, user_input):
        payload = json.loads(user_input)
        assert payload["latest_negotiation_round"]["recommended_action"] == "revise_current_sprint"
        assert payload["revision_notes"] == ["keep the shell narrow"]
        return {
            "revision_summary": "Tighten sprint-1 around palette persistence before broadening the surface.",
            "must_fix": [
                "Resolve failing criterion: functionality.",
                "timeline entries reset on refresh",
                "palette resets on refresh",
            ],
            "must_keep": [
                "pytest tests/test_editor.py -q",
                "editor loads",
                "design_quality",
            ],
        }

    _stub_openai_agents_json_runtime(
        monkeypatch,
        workbench,
        responses={"Workbench live revisor": _fake_revisor},
    )

    payload = workbench.app_retry(
        task_id="product-openai-agents-live-retry-1",
        sprint_id="sprint-1",
        revision_notes=["keep the shell narrow"],
        use_live_planner=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["latest_revision"]["planner_mode"] == "live"
    assert harness["latest_revision"]["revision_summary"] == (
        "Tighten sprint-1 around palette persistence before broadening the surface."
    )
    assert harness["retry_count"] == 1


def test_product_runtime_app_replan_uses_openai_agents_host_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_openai_agents_workbench(tmp_path, monkeypatch, label="product-openai-agents-live-replan")
    session = workbench._initial_session(
        task_id="product-openai-agents-live-replan-1",
        task="Use the openai-agents execution host to replan the sprint after escalation.",
        target_files=["src/demo.py"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    workbench.app_plan(
        task_id="product-openai-agents-live-replan-1",
        prompt="Build a visual pixel-art editor.",
        title="Pixel Forge",
        app_type="full_stack_app",
        stack=["React", "FastAPI"],
        features=["canvas", "palette"],
        criteria=["functionality:0.8", "design_quality:0.7"],
    )
    workbench.app_sprint(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        goal="Ship the editor shell.",
        scope=["shell", "canvas"],
        acceptance_checks=["pytest tests/test_editor.py -q"],
        done_definition=["editor loads"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.61", "design_quality=0.79"],
        blocker_notes=["palette resets on refresh"],
    )
    workbench.app_negotiate(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        revision_notes=["Focus on palette persistence before broadening the scope."],
    )
    workbench.app_generate(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        execution_summary="Patch palette persistence in src/editor.tsx before retrying the evaluator.",
        changed_target_hints=["src/editor.tsx", "src/state/store.ts"],
    )
    workbench.app_qa(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.73", "design_quality=0.81"],
        summary="Timeline persistence improved, but functionality still fails the evaluator bar.",
        blocker_notes=["timeline entries still drift after refresh"],
    )
    workbench.app_escalate(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        note="retry budget exhausted",
    )

    def _fake_replanner(_agent, user_input):
        payload = json.loads(user_input)
        assert payload["execution_focus"] == "Patch palette persistence in src/editor.tsx before retrying the evaluator."
        assert payload["latest_execution_attempt"]["changed_target_hints"] == ["src/editor.tsx", "src/state/store.ts"]
        return {
            "goal": "Replanned sprint focused on persistence hardening.",
            "scope": ["src/editor.tsx", "refresh stability"],
            "acceptance_checks": ["pytest tests/test_editor.py -q"],
            "done_definition": ["refresh path stays stable", "editor shell remains coherent"],
            "replan_note": "Narrow the sprint around persistence hardening after the failed execution attempt.",
        }

    _stub_openai_agents_json_runtime(
        monkeypatch,
        workbench,
        responses={"Workbench live replanner": _fake_replanner},
    )

    payload = workbench.app_replan(
        task_id="product-openai-agents-live-replan-1",
        sprint_id="sprint-1",
        note="narrow the sprint around persistence",
        use_live_planner=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    assert harness["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1"
    assert harness["active_sprint_contract"]["goal"] == "Replanned sprint focused on persistence hardening."
    assert harness["active_sprint_contract"]["scope"] == ["src/editor.tsx", "refresh stability"]


def test_product_runtime_app_generate_uses_openai_agents_delivery_host_when_requested(tmp_path, monkeypatch) -> None:
    workbench = _prepare_openai_agents_workbench(tmp_path, monkeypatch, label="product-openai-agents-live-generate")
    session = workbench._initial_session(
        task_id="product-openai-agents-live-generate-1",
        task="Use the openai-agents execution host to run one bounded delivery attempt.",
        target_files=["notes/plan.md"],
        validation_commands=["pytest -q"],
        apply_strategy=False,
    )
    save_session(session)
    workbench.app_plan(
        task_id="product-openai-agents-live-generate-1",
        prompt="Coordinate bounded hydration hardening pipeline.",
        title="Hydration Pipeline",
        app_type="internal_tool",
        stack=["SQLite"],
        features=["hydration audit", "persistence checklist"],
        criteria=["functionality:0.8", "code_quality:0.6"],
    )
    workbench.app_sprint(
        task_id="product-openai-agents-live-generate-1",
        sprint_id="sprint-1",
        goal="Produce one bounded delivery artifact for hydration hardening.",
        scope=["dist/index.html", "notes/implementation.txt"],
        acceptance_checks=["python3 scripts/check_dist.py"],
        done_definition=["delivery artifact exists"],
        proposed_by="planner",
        approved=True,
    )
    session = load_session(
        str(tmp_path),
        "product-openai-agents-live-generate-1",
        project_scope=workbench._config.project_scope,
    )
    assert session is not None and session.app_harness_state is not None and session.app_harness_state.active_sprint_contract is not None
    session.app_harness_state.active_sprint_contract.acceptance_checks = ["python3 scripts/check_dist.py"]
    save_session(session)
    captures: list[dict[str, str]] = []
    host = workbench._execution_host

    monkeypatch.setattr("aionis_workbench.runtime._delivery_bootstrap_family", lambda _spec: "")
    monkeypatch.setattr(
        workbench._delivery,
        "_run_workspace_validation_commands",
        lambda **_: ValidationResult(
            ok=True,
            command="python3 scripts/check_dist.py",
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=["dist/index.html", "notes/implementation.txt"],
        ),
    )
    monkeypatch.setattr(
        host,
        "invoke_delivery_task",
        lambda **kwargs: (
            captures.append(
                {
                    "task": str(kwargs["task"]),
                    "root_dir": str(kwargs["root_dir"]),
                    "trace_path": str(kwargs.get("trace_path") or ""),
                }
            ),
            Path(str(kwargs["root_dir"]) or ".").joinpath("dist").mkdir(parents=True, exist_ok=True),
            Path(str(kwargs["root_dir"]) or ".").joinpath("dist/index.html").write_text(
                "<html>hydration ok</html>",
                encoding="utf-8",
            ),
            Path(str(kwargs["root_dir"]) or ".").joinpath("src").mkdir(parents=True, exist_ok=True),
            Path(str(kwargs["root_dir"]) or ".").joinpath("src/App.tsx").write_text(
                """
export function App() {
  return (
    <main>
      <header>
        <h1>Hydration Pipeline</h1>
        <p>Bounded persistence hardening run.</p>
      </header>
      <section>
        <h2>Current Lane</h2>
        <div>Hydration audit and persistence verification.</div>
      </section>
      <section>
        <h2>Checks</h2>
        <div>Delivery artifact exists and bounded notes are recorded.</div>
      </section>
      <footer>
        <div>Ready for the next constrained retry.</div>
      </footer>
    </main>
  );
}
""".strip()
                + "\n",
                encoding="utf-8",
            ),
            Path(str(kwargs["root_dir"]) or ".").joinpath("scripts").mkdir(parents=True, exist_ok=True),
            Path(str(kwargs["root_dir"]) or ".").joinpath("scripts/check_dist.py").write_text(
                """
from pathlib import Path

raise SystemExit(0 if Path("dist/index.html").exists() else 1)
""".strip()
                + "\n",
                encoding="utf-8",
            ),
            Path(str(kwargs["root_dir"]) or ".").joinpath("notes").mkdir(parents=True, exist_ok=True),
            Path(str(kwargs["root_dir"]) or ".").joinpath("notes/implementation.txt").write_text(
                "bounded hydration hardening attempt\n",
                encoding="utf-8",
            ),
            "Build completed and delivery artifact is ready.",
        )[-1],
    )

    payload = workbench.app_generate(
        task_id="product-openai-agents-live-generate-1",
        sprint_id="sprint-1",
        use_live_generator=True,
    )

    harness = payload["canonical_views"]["app_harness"]
    latest_attempt = harness["latest_execution_attempt"]
    assert latest_attempt["execution_mode"] == "live"
    assert latest_attempt["artifact_path"] in {"dist/index.html", "index.html"}
    assert latest_attempt["validation_summary"] == "Validation commands passed."
    assert latest_attempt["failure_reason"] == ""
    assert host.describe()["execution_runtime"] == "openai_agents"
    assert "Produce one bounded delivery artifact for hydration hardening." in captures[0]["task"]


def test_product_inspect_session_derives_reviewer_surface_from_failed_validation(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-reviewer-surface")
    session = workbench._initial_session(
        task_id="product-reviewer-surface-1",
        task="Repair the focused demo regression.",
        target_files=["src/demo.py"],
        validation_commands=["pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.status = "paused"
    session.last_validation_result = {
        "ok": False,
        "command": "pytest tests/test_demo.py -q",
        "exit_code": 1,
        "summary": "Validation failed: tests/test_demo.py::test_render",
        "output": "Baseline failing test: tests/test_demo.py::test_render",
    }
    save_session(session)

    payload = workbench.inspect_session(task_id="product-reviewer-surface-1")

    reviewer = payload["canonical_views"]["reviewer"]
    packet = payload["canonical_surface"]["execution_packet"]
    summary = payload["canonical_surface"]["execution_packet_summary"]

    assert reviewer["standard"] == "strict_review"
    assert reviewer["ready_required"] is True
    assert reviewer["acceptance_checks"] == ["pytest tests/test_demo.py -q"]
    assert reviewer["resume_anchor"] == "resume:src/demo.py"
    assert packet["review_contract"].standard == "strict_review"
    assert packet["reviewer_ready_required"] is True
    assert packet["resume_anchor"].anchor == "resume:src/demo.py"
    assert summary["review_contract_present"] is True
    assert summary["resume_anchor_present"] is True
    assert payload["canonical_views"]["review_packs"]["continuity"]["pack_version"] is None


def test_product_inspect_session_surfaces_review_pack_summaries(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-review-pack-summary")
    session = workbench._initial_session(
        task_id="product-review-pack-summary-1",
        task="Expose continuity and evolution review packs in canonical views.",
        target_files=["src/demo.py"],
        validation_commands=["pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.continuity_review_pack = ReviewPackSummary(
        pack_version="continuity_review_pack_v1",
        source="continuity",
        review_contract=ReviewerContract(
            standard="strict_review",
            required_outputs=["patch", "tests"],
            acceptance_checks=["pytest tests/test_demo.py -q"],
            rollback_required=False,
        ),
        selected_tool="read",
        file_path="src/demo.py",
        target_files=["src/demo.py"],
        next_action="Verify the patch against the reviewer contract.",
    )
    session.evolution_review_pack = ReviewPackSummary(
        pack_version="evolution_review_pack_v1",
        source="evolution",
        review_contract=ReviewerContract(
            standard="strict_review",
            required_outputs=["patch"],
            acceptance_checks=["pytest tests/test_demo.py -q"],
            rollback_required=False,
        ),
        selected_tool="edit",
        file_path="src/demo.py",
        target_files=["src/demo.py"],
        next_action="Patch the focused file and rerun tests.",
    )
    save_session(session)

    payload = workbench.inspect_session(task_id="product-review-pack-summary-1")

    assert payload["canonical_views"]["review_packs"]["continuity"]["pack_version"] == "continuity_review_pack_v1"
    assert payload["canonical_views"]["review_packs"]["continuity"]["selected_tool"] == "read"
    assert payload["canonical_views"]["review_packs"]["evolution"]["pack_version"] == "evolution_review_pack_v1"
    assert payload["canonical_views"]["review_packs"]["evolution"]["selected_tool"] == "edit"


def test_product_consolidation_promotes_seed_ready_family_prior(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-family-prior")
    validation_command = "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    task_family = "task:demo"
    for task_id, source in [
        ("product-family-1", "workflow_closure"),
        ("product-family-2", "manual_ingest"),
    ]:
        session = workbench._initial_session(
            task_id=task_id,
            task="Keep the testing family healthy.",
            target_files=["src/demo.py", "tests/test_demo.py"],
            validation_commands=[validation_command],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = task_family
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.promoted_insights = [f"Validation passed: {validation_command}"]
        session.last_validation_result = {
            "ok": True,
            "command": validation_command,
            "exit_code": 0,
            "summary": "Validation commands passed.",
            "output": "",
            "changed_files": ["src/demo.py", "tests/test_demo.py"],
        }
        session.continuity_snapshot = {
            "learning": {
                "auto_absorbed": source != "manual_ingest",
                "source": source,
                "task_family": task_family,
                "strategy_profile": "family_reuse_loop",
                "validation_command": validation_command,
                "validation_summary": "Validation commands passed.",
                "working_set": ["src/demo.py", "tests/test_demo.py"],
                "role_sequence": ["investigator", "implementer", "verifier"],
                "artifact_refs": [],
            },
            "doc_workflow": {
                "latest_action": "resume",
                "status": "completed",
                "doc_input": "flows/demo-workflow.aionis.md",
                "source_doc_id": "demo-workflow-1",
                "handoff_anchor": "product-dream-anchor",
                "selected_tool": "read",
                "history": [{"action": "resume", "status": "completed", "doc_input": "flows/demo-workflow.aionis.md"}],
            },
        }
        session.instrumentation_summary = InstrumentationSummary(
            task_family=task_family,
            family_scope="same_task_family",
            family_hit=True,
            family_reason="Family-scoped strategy matched task:demo.",
            selected_pattern_hit_count=1,
            selected_pattern_miss_count=0,
            routed_artifact_known_count=2,
            routed_artifact_same_family_count=2,
            routed_artifact_other_family_count=0,
            routed_artifact_unknown_count=0,
            routed_artifact_hit_rate=1.0,
            routed_same_family_task_ids=["product-family-1", "product-family-2"],
            routed_other_family_task_ids=[],
        )
        save_session(session)

    consolidated = workbench.consolidate(limit=12, family_limit=4)
    dashboard = workbench.dashboard(limit=12, family_limit=4)

    assert consolidated["family_rows"][0]["task_family"] == task_family
    assert consolidated["family_rows"][0]["seed_ready"] is True


def test_consolidation_surfaces_family_reviewer_prior(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-reviewer-prior")
    validation_command = "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    for task_id in ["product-reviewer-prior-1", "product-reviewer-prior-2"]:
        session = workbench._initial_session(
            task_id=task_id,
            task="Keep reviewer-backed demo work reusable.",
            target_files=["src/demo.py", "tests/test_demo.py"],
            validation_commands=[validation_command],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = "task:demo"
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.last_validation_result = {
            "ok": True,
            "command": validation_command,
            "exit_code": 0,
            "summary": "Validation commands passed.",
            "output": "",
            "changed_files": ["src/demo.py", "tests/test_demo.py"],
        }
        session.execution_packet = ExecutionPacket.from_dict(
            {
                "packet_version": 1,
                "current_stage": "review",
                "active_role": "review",
                "task_brief": session.goal,
                "target_files": ["src/demo.py", "tests/test_demo.py"],
                "next_action": "Verify the patch against the reviewer contract.",
                "pending_validations": [validation_command],
                "review_contract": {
                    "standard": "strict_review",
                    "required_outputs": ["patch", "tests"],
                    "acceptance_checks": [validation_command],
                    "rollback_required": False,
                },
                "reviewer_ready_required": True,
                "resume_anchor": {
                    "anchor": "resume:src/demo.py",
                    "file_path": "src/demo.py",
                    "repo_root": str(tmp_path),
                },
            }
        )
        session.continuity_review_pack = ReviewPackSummary(
            pack_version="continuity_review_pack_v1",
            source="continuity",
            review_contract=ReviewerContract(
                standard="strict_review",
                required_outputs=["patch", "tests"],
                acceptance_checks=[validation_command],
                rollback_required=False,
            ),
            selected_tool="read",
            file_path="src/demo.py",
            target_files=["src/demo.py", "tests/test_demo.py"],
            next_action="Verify the patch against the reviewer contract.",
        )
        save_session(session)

    consolidated = workbench.consolidate(limit=12, family_limit=4)

    family_row = consolidated["family_rows"][0]
    reviewer_prior = family_row["family_reviewer_prior"]

    assert family_row["task_family"] == "task:demo"
    assert family_row["reviewer_sample_count"] == 2
    assert family_row["reviewer_seed_ready"] is True
    assert reviewer_prior["dominant_standard"] == "strict_review"
    assert reviewer_prior["dominant_required_outputs"] == ["patch", "tests"]
    assert reviewer_prior["dominant_acceptance_checks"] == [validation_command]
    assert reviewer_prior["dominant_pack_source"] == "continuity"
    assert reviewer_prior["dominant_selected_tool"] == "read"
    assert reviewer_prior["dominant_resume_anchor"] == "resume:src/demo.py"
    assert reviewer_prior["ready_required_count"] == 2


def test_consolidation_does_not_seed_ready_incompatible_family_reviewer_contracts(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-reviewer-prior-mismatch")
    commands = [
        "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        "PYTHONPATH=src python3 -m pytest tests/test_demo_alt.py -q",
    ]
    for idx, validation_command in enumerate(commands, start=1):
        session = workbench._initial_session(
            task_id=f"product-reviewer-prior-mismatch-{idx}",
            task="Keep reviewer-backed demo work reusable.",
            target_files=["src/demo.py", "tests/test_demo.py"],
            validation_commands=[validation_command],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = "task:demo"
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.last_validation_result = {
            "ok": True,
            "command": validation_command,
            "exit_code": 0,
            "summary": "Validation commands passed.",
            "output": "",
            "changed_files": ["src/demo.py", "tests/test_demo.py"],
        }
        session.execution_packet = ExecutionPacket.from_dict(
            {
                "packet_version": 1,
                "current_stage": "review",
                "active_role": "review",
                "task_brief": session.goal,
                "target_files": ["src/demo.py", "tests/test_demo.py"],
                "next_action": "Verify the patch against the reviewer contract.",
                "pending_validations": [validation_command],
                "review_contract": {
                    "standard": "strict_review",
                    "required_outputs": ["patch", "tests"],
                    "acceptance_checks": [validation_command],
                    "rollback_required": False,
                },
                "reviewer_ready_required": True,
                "resume_anchor": {
                    "anchor": "resume:src/demo.py",
                    "file_path": "src/demo.py",
                    "repo_root": str(tmp_path),
                },
            }
        )
        session.continuity_review_pack = ReviewPackSummary(
            pack_version="continuity_review_pack_v1",
            source="continuity",
            review_contract=ReviewerContract(
                standard="strict_review",
                required_outputs=["patch", "tests"],
                acceptance_checks=[validation_command],
                rollback_required=False,
            ),
            selected_tool="read",
            file_path="src/demo.py",
            target_files=["src/demo.py", "tests/test_demo.py"],
            next_action="Verify the patch against the reviewer contract.",
        )
        save_session(session)

    consolidated = workbench.consolidate(limit=12, family_limit=4)

    family_row = consolidated["family_rows"][0]
    reviewer_prior = family_row["family_reviewer_prior"]

    assert family_row["task_family"] == "task:demo"
    assert family_row["reviewer_sample_count"] == 2
    assert family_row["reviewer_seed_ready"] is False
    assert reviewer_prior["seed_ready"] is False
    assert reviewer_prior["dominant_acceptance_checks"] in [[commands[0]], [commands[1]]]
    assert "needs at least one more sample" in reviewer_prior["seed_reason"]


def test_product_doc_publish_infers_repo_root_and_file_path(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-publish-defaults")
    internal_workflow = tmp_path / "flows" / "internal-workflow.aionis.md"
    internal_workflow.parent.mkdir(parents=True, exist_ok=True)
    internal_workflow.write_text("# internal\n", encoding="utf-8")
    external_workflow = tmp_path.parent / f"{tmp_path.name}-external-workflow.aionis.md"
    external_workflow.write_text("# external\n", encoding="utf-8")
    calls: list[tuple[str, dict[str, object]]] = []

    def _stub_publish(*, input_path: str, **kwargs: object) -> dict[str, object]:
        calls.append((input_path, dict(kwargs)))
        return {
            "source_doc_id": "workflow-001",
            "source_doc_version": "1.0",
            "response": {
                "handoff_anchor": "doc-defaults-anchor",
                "handoff_kind": "task_handoff",
            },
        }

    monkeypatch.setattr(workbench._aionisdoc, "publish", _stub_publish)

    workbench.doc_publish(input_path=str(internal_workflow), task_id="doc-defaults-1")
    workbench.doc_publish(input_path=str(external_workflow), task_id="doc-defaults-2")

    assert calls[0][1]["repo_root"] == str(tmp_path)
    assert calls[0][1]["file_path"] == "flows/internal-workflow.aionis.md"
    assert calls[1][1]["repo_root"] == str(tmp_path)
    assert calls[1][1]["file_path"] == f"flows/{external_workflow.name}"


def test_workbench_exposes_doc_compile_surface(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-compile")

    def _stub_compile(*, input_path: str, **_: object) -> dict[str, object]:
        assert input_path == "workflow.aionis.md"
        return {
            "shell_view": "doc_compile",
            "doc_action": "compile",
            "doc_input": input_path,
            "status": "ok",
            "compile_result": {"compile_result_version": "aionis_doc_compile_result_v1"},
        }

    monkeypatch.setattr(workbench._aionisdoc, "compile", _stub_compile)

    payload = workbench.doc_compile(input_path="workflow.aionis.md")

    assert payload["shell_view"] == "doc_compile"
    assert payload["status"] == "ok"
    assert payload["compile_result"]["compile_result_version"] == "aionis_doc_compile_result_v1"


def test_workbench_exposes_doc_run_publish_recover_resume_surfaces(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-surfaces")

    monkeypatch.setattr(
        workbench._aionisdoc,
        "run",
        lambda *, input_path, registry_path, **_: {
            "shell_view": "doc_run",
            "doc_action": "run",
            "doc_input": input_path,
            "doc_registry": registry_path,
            "status": "succeeded",
            "run_result": {"status": "succeeded"},
        },
    )
    monkeypatch.setattr(
        workbench._aionisdoc,
        "publish",
        lambda *, input_path, **_: {
            "shell_view": "doc_publish",
            "doc_action": "publish",
            "doc_input": input_path,
            "status": "published",
            "publish_result": {"status": "published"},
        },
    )
    monkeypatch.setattr(
        workbench._aionisdoc,
        "recover",
        lambda *, input_path, **_: {
            "shell_view": "doc_recover",
            "doc_action": "recover",
            "doc_input": input_path,
            "status": "recovered",
            "recover_result": {"status": "recovered"},
        },
    )
    monkeypatch.setattr(
        workbench._aionisdoc,
        "resume",
        lambda *, input_path, **_: {
            "shell_view": "doc_resume",
            "doc_action": "resume",
            "doc_input": input_path,
            "status": "completed",
            "resume_result": {"status": "completed"},
        },
    )

    run_payload = workbench.doc_run(input_path="workflow.aionis.md", registry_path="module-registry.json")
    publish_payload = workbench.doc_publish(input_path="workflow.aionis.md")
    recover_payload = workbench.doc_recover(input_path="publish-result.json")
    resume_payload = workbench.doc_resume(input_path="recover-result.json")

    assert run_payload["shell_view"] == "doc_run"
    assert run_payload["doc_registry"] == "module-registry.json"
    assert publish_payload["shell_view"] == "doc_publish"
    assert recover_payload["shell_view"] == "doc_recover"
    assert resume_payload["shell_view"] == "doc_resume"


def test_doc_publish_result_is_recorded_as_session_artifact(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-artifact")
    session = workbench._initial_session(
        task_id="product-doc-1",
        task="Record an Aionisdoc publish result into the current session.",
        target_files=["workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)

    def _stub_publish(*, input_path: str, **_: object) -> dict[str, object]:
        assert input_path == "workflow.aionis.md"
        return {
            "shell_view": "doc_publish",
            "doc_action": "publish",
            "doc_input": input_path,
            "status": "published",
            "publish_result": {
                "publish_result_version": "aionis_doc_publish_result_v1",
                "input_kind": "source",
                "source_doc_id": "workflow-001",
                "source_doc_version": "1.0",
                "request": {
                    "anchor": "product-doc-anchor",
                    "handoff_kind": "task_handoff",
                },
                "response": {
                    "status": 200,
                    "commit_id": "commit-1",
                    "handoff_anchor": "product-doc-anchor",
                    "handoff_kind": "task_handoff",
                },
            },
        }

    monkeypatch.setattr(workbench._aionisdoc, "publish", _stub_publish)

    payload = workbench.doc_publish(
        input_path="workflow.aionis.md",
        task_id="product-doc-1",
        event_source="vscode_extension",
        event_origin="editor_extension",
        recorded_at="2026-04-03T12:00:00Z",
    )
    inspected = workbench.inspect_session(task_id="product-doc-1")
    artifacts = inspected["session"]["artifacts"]
    continuity = inspected["canonical_views"]["continuity"]
    doc_learning = inspected["doc_learning"]

    assert payload["status"] == "published"
    assert payload["task_id"] == "product-doc-1"
    assert payload["recorded_artifacts"]
    assert any(item["kind"] == "doc_publish_result" for item in artifacts)
    assert any(item["kind"] == "doc_runtime_handoff" for item in artifacts)
    assert continuity["doc_workflow"]["latest_action"] == "publish"
    assert continuity["doc_workflow"]["handoff_anchor"] == "product-doc-anchor"
    assert continuity["doc_workflow"]["source_doc_id"] == "workflow-001"
    assert continuity["preferred_artifact_refs"]
    assert doc_learning["latest_action"] == "publish"
    assert doc_learning["task_family"]
    assert doc_learning["handoff_anchor"] == "product-doc-anchor"
    assert doc_learning["source_doc_id"] == "workflow-001"
    assert doc_learning["event_source"] == "vscode_extension"
    assert doc_learning["event_origin"] == "editor_extension"
    assert doc_learning["recorded_at"] == "2026-04-03T12:00:00Z"
    assert payload["controller_action_bar"] == {
        "task_id": "product-doc-1",
        "status": "active",
        "recommended_command": "/next product-doc-1",
        "allowed_commands": [
            "/next product-doc-1",
            "/show product-doc-1",
            "/session product-doc-1",
        ],
    }


def test_doc_editor_event_is_recorded_without_rerunning_aionisdoc(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-editor-event")
    session = workbench._initial_session(
        task_id="product-doc-editor-1",
        task="Attach an editor-originated doc publish event to the current task.",
        target_files=["workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)

    payload = workbench.doc_event(
        task_id="product-doc-editor-1",
        event={
            "event_version": "aionisdoc_workbench_event_v1",
            "event_source": "cursor_extension",
            "task_id": "product-doc-editor-1",
            "doc_action": "publish",
            "doc_input": "workflow.aionis.md",
            "status": "completed",
            "payload": {
                "shell_view": "doc_publish",
                "doc_action": "publish",
                "doc_input": "workflow.aionis.md",
                "status": "completed",
                "publish_result": {
                    "publish_result_version": "aionis_doc_publish_result_v1",
                    "source_doc_id": "workflow-editor-1",
                    "source_doc_version": "1.1",
                    "request": {"anchor": "editor-doc-anchor", "handoff_kind": "doc_runtime_handoff"},
                    "response": {"handoff_anchor": "editor-doc-anchor", "handoff_kind": "doc_runtime_handoff"},
                },
            },
        },
    )

    inspected = workbench.inspect_session(task_id="product-doc-editor-1")
    artifacts = inspected["session"]["artifacts"]
    continuity = inspected["canonical_views"]["continuity"]
    doc_learning = inspected["doc_learning"]

    assert payload["event_origin"] == "editor_extension"
    assert any(item["kind"] == "doc_publish_result" for item in artifacts)
    assert any(item["kind"] == "doc_runtime_handoff" for item in artifacts)
    assert continuity["doc_workflow"]["latest_action"] == "publish"
    assert continuity["doc_workflow"]["handoff_anchor"] == "editor-doc-anchor"
    assert continuity["doc_workflow"]["source_doc_id"] == "workflow-editor-1"
    assert continuity["doc_workflow"]["event_source"] == "cursor_extension"
    assert continuity["doc_workflow"]["event_origin"] == "editor_extension"
    assert doc_learning["latest_action"] == "publish"
    assert doc_learning["source_doc_id"] == "workflow-editor-1"
    assert doc_learning["handoff_anchor"] == "editor-doc-anchor"
    assert doc_learning["event_source"] == "cursor_extension"
    assert doc_learning["event_origin"] == "editor_extension"
    assert payload["controller_action_bar"] == {
        "task_id": "product-doc-editor-1",
        "status": "active",
        "recommended_command": "/next product-doc-editor-1",
        "allowed_commands": [
            "/next product-doc-editor-1",
            "/show product-doc-editor-1",
            "/session product-doc-editor-1",
        ],
    }


def test_product_doc_inspect_surfaces_controller_action_bar(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-inspect")
    session = workbench._initial_session(
        task_id="product-doc-inspect-1",
        task="Inspect a doc workflow and surface controller guidance.",
        target_files=["flows/workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)
    (tmp_path / "flows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "flows" / "workflow.aionis.md").write_text("# workflow\n", encoding="utf-8")

    workbench.doc_event(
        task_id="product-doc-inspect-1",
        event={
            "event_version": "aionisdoc_workbench_event_v1",
            "event_source": "cursor_extension",
            "task_id": "product-doc-inspect-1",
            "doc_action": "publish",
            "doc_input": "flows/workflow.aionis.md",
            "status": "completed",
            "payload": {
                "shell_view": "doc_publish",
                "doc_action": "publish",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
                "publish_result": {
                    "publish_result_version": "aionis_doc_publish_result_v1",
                    "source_doc_id": "workflow-inspect-1",
                    "request": {"anchor": "doc-inspect-anchor", "handoff_kind": "doc_runtime_handoff"},
                    "response": {"handoff_anchor": "doc-inspect-anchor", "handoff_kind": "doc_runtime_handoff"},
                },
            },
        },
    )

    payload = workbench.doc_inspect(target="flows/workflow.aionis.md", limit=8)

    assert payload["inspect_kind"] == "workflow"
    assert payload["latest_record"]["task_id"] == "product-doc-inspect-1"
    assert payload["controller_action_bar"] == {
        "task_id": "product-doc-inspect-1",
        "status": "active",
        "recommended_command": "/next product-doc-inspect-1",
        "allowed_commands": [
            "/next product-doc-inspect-1",
            "/show product-doc-inspect-1",
            "/session product-doc-inspect-1",
        ],
    }


def test_product_doc_list_surfaces_row_controller_actions(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-list")
    session = workbench._initial_session(
        task_id="product-doc-list-1",
        task="List doc workflows with row-level controller guidance.",
        target_files=["flows/workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)
    (tmp_path / "flows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "flows" / "workflow.aionis.md").write_text("# workflow\n", encoding="utf-8")

    workbench.doc_event(
        task_id="product-doc-list-1",
        event={
            "event_version": "aionisdoc_workbench_event_v1",
            "event_source": "cursor_extension",
            "task_id": "product-doc-list-1",
            "doc_action": "resume",
            "doc_input": "flows/workflow.aionis.md",
            "status": "completed",
            "payload": {
                "shell_view": "doc_resume",
                "doc_action": "resume",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
            },
        },
    )

    payload = workbench.doc_list(limit=8)

    assert payload["doc_count"] >= 1
    workflow_row = next(item for item in payload["docs"] if item["path"] == "flows/workflow.aionis.md")
    assert workflow_row["latest_task_id"] == "product-doc-list-1"
    assert workflow_row["controller_action_bar"] == {
        "task_id": "product-doc-list-1",
        "status": "active",
        "recommended_command": "/next product-doc-list-1",
        "allowed_commands": [
            "/next product-doc-list-1",
            "/show product-doc-list-1",
            "/session product-doc-list-1",
        ],
    }


def test_doc_publish_recover_resume_flow_persists_workflow_history(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-doc-flow")
    session = workbench._initial_session(
        task_id="product-doc-flow-1",
        task="Keep a doc workflow resumable through publish, recover, and resume.",
        target_files=["workflow.aionis.md"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)

    monkeypatch.setattr(
        workbench._aionisdoc,
        "publish",
        lambda *, input_path, **_: {
            "shell_view": "doc_publish",
            "doc_action": "publish",
            "doc_input": input_path,
            "status": "published",
            "publish_result": {
                "publish_result_version": "aionis_doc_publish_result_v1",
                "source_doc_id": "workflow-002",
                "source_doc_version": "2.0",
                "request": {
                    "anchor": "product-doc-flow-anchor",
                    "handoff_kind": "task_handoff",
                },
                "response": {
                    "status": 200,
                    "handoff_anchor": "product-doc-flow-anchor",
                    "handoff_kind": "task_handoff",
                },
            },
        },
    )
    monkeypatch.setattr(
        workbench._aionisdoc,
        "recover",
        lambda *, input_path, **_: {
            "shell_view": "doc_recover",
            "doc_action": "recover",
            "doc_input": input_path,
            "status": "recovered",
            "recover_result": {
                "recover_result_version": "aionis_doc_recover_result_v1",
                "recover_request": {
                    "anchor": "product-doc-flow-anchor",
                    "handoff_kind": "task_handoff",
                },
                "recover_response": {
                    "status": 200,
                    "data": {
                        "anchor": "product-doc-flow-anchor",
                        "handoff_kind": "task_handoff",
                    },
                },
            },
        },
    )
    monkeypatch.setattr(
        workbench._aionisdoc,
        "resume",
        lambda *, input_path, **_: {
            "shell_view": "doc_resume",
            "doc_action": "resume",
            "doc_input": input_path,
            "status": "completed",
            "resume_result": {
                "resume_result_version": "aionis_doc_resume_result_v1",
                "recover_result": {
                    "recover_request": {
                        "anchor": "product-doc-flow-anchor",
                        "handoff_kind": "task_handoff",
                    },
                    "recover_response": {
                        "status": 200,
                        "data": {
                            "anchor": "product-doc-flow-anchor",
                            "handoff_kind": "task_handoff",
                        },
                    },
                },
                "resume_summary": {
                    "selected_tool": "read",
                },
            },
        },
    )

    publish_payload = workbench.doc_publish(input_path="workflow.aionis.md", task_id="product-doc-flow-1")
    recover_payload = workbench.doc_recover(input_path="publish-result.json", task_id="product-doc-flow-1")
    resume_payload = workbench.doc_resume(input_path="recover-result.json", task_id="product-doc-flow-1")
    inspected = workbench.inspect_session(task_id="product-doc-flow-1")
    continuity = inspected["canonical_views"]["continuity"]
    doc_learning = inspected["doc_learning"]
    artifacts = inspected["session"]["artifacts"]

    assert publish_payload["recorded_artifacts"]
    assert recover_payload["recorded_artifacts"]
    assert resume_payload["recorded_artifacts"]
    assert continuity["doc_workflow"]["latest_action"] == "resume"
    assert continuity["doc_workflow"]["handoff_anchor"] == "product-doc-flow-anchor"
    assert continuity["doc_workflow"]["selected_tool"] == "read"
    assert [item["action"] for item in continuity["doc_workflow"]["history"][:3]] == ["resume", "recover", "publish"]
    assert len([item for item in artifacts if item["kind"] == "doc_runtime_handoff"]) >= 3
    assert continuity["preferred_artifact_refs"]
    assert doc_learning["latest_action"] == "resume"
    assert doc_learning["selected_tool"] == "read"
    assert [item["action"] for item in doc_learning["history"][:3]] == ["resume", "recover", "publish"]


def test_promoted_prior_is_used_after_dream_promotion(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-dream-promotion")
    validation_command = "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    task_family = "task:demo"
    for idx, source in enumerate(
        ["workflow_closure", "manual_ingest", "validate"],
        start=1,
    ):
        session = workbench._initial_session(
            task_id=f"product-dream-{idx}",
            task="Keep the demo family tight and repeatable.",
            target_files=["src/demo.py", "tests/test_demo.py"],
            validation_commands=[validation_command],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = task_family
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.promoted_insights = [f"Validation passed: {validation_command}"]
        session.last_validation_result = {
            "ok": True,
            "command": validation_command,
            "exit_code": 0,
            "summary": "Validation commands passed.",
            "output": "",
            "changed_files": ["src/demo.py", "tests/test_demo.py"],
        }
        session.continuity_snapshot = {
            "learning": {
                "auto_absorbed": source != "manual_ingest",
                "source": source,
                "task_family": task_family,
                "strategy_profile": "family_reuse_loop",
                "validation_style": "targeted_first",
                "validation_command": validation_command,
                "validation_summary": "Validation commands passed.",
                "working_set": ["src/demo.py", "tests/test_demo.py"],
                "role_sequence": ["investigator", "implementer", "verifier"],
                "artifact_refs": [],
            },
            "doc_workflow": {
                "latest_action": "resume",
                "status": "completed",
                "doc_input": "flows/demo-workflow.aionis.md",
                "source_doc_id": "demo-workflow-1",
                "handoff_anchor": "product-dream-anchor",
                "selected_tool": "read",
                "history": [{"action": "resume", "status": "completed", "doc_input": "flows/demo-workflow.aionis.md"}],
            },
        }
        session.instrumentation_summary = InstrumentationSummary(
            task_family=task_family,
            family_scope="same_task_family",
            family_hit=True,
            family_reason="Family-scoped strategy matched task:demo.",
            selected_pattern_hit_count=1,
            selected_pattern_miss_count=0,
            routed_artifact_known_count=2,
            routed_artifact_same_family_count=2,
            routed_artifact_other_family_count=0,
            routed_artifact_unknown_count=0,
            routed_artifact_hit_rate=1.0,
            routed_same_family_task_ids=["product-dream-1", "product-dream-2", "product-dream-3"],
            routed_other_family_task_ids=[],
        )
        save_session(session)

    consolidated = workbench.consolidate(limit=12, family_limit=4)
    seeded = workbench._initial_session(
        task_id="product-dream-seeded-1",
        task="Keep the current demo loop stable.",
        target_files=[],
        validation_commands=[],
        apply_strategy=True,
        )

    assert consolidated["dream_summary"]["seed_ready_count"] >= 1
    assert seeded.selected_task_family == "task:demo"
    assert seeded.validation_commands[0] == validation_command
    assert seeded.target_files[:2] == ["src/demo.py", "tests/test_demo.py"]
    dream_payload = workbench.dream(limit=12, family_limit=4, status_filter="seed_ready")
    assert dream_payload["dream_promotions"][0]["dominant_source_doc_id"] == "demo-workflow-1"
    assert dream_payload["dream_promotions"][0]["dominant_doc_input"] == "flows/demo-workflow.aionis.md"


def test_consolidation_surfaces_family_doc_prior(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-family-doc-prior")
    task_family = "task:docs"
    for task_id, latest_action, selected_tool in [
        ("product-doc-prior-1", "publish", ""),
        ("product-doc-prior-2", "resume", "read"),
    ]:
        session = workbench._initial_session(
            task_id=task_id,
            task="Keep the doc workflow family reusable.",
            target_files=["flows/workflow.aionis.md"],
            validation_commands=[],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = task_family
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.continuity_snapshot = {
            "task_family": task_family,
            "doc_workflow": {
                "latest_action": latest_action,
                "status": "completed",
                "doc_input": "flows/workflow.aionis.md",
                "source_doc_id": "workflow-doc-1",
                "handoff_anchor": "doc-prior-anchor",
                "selected_tool": selected_tool,
                "event_source": "vscode_extension",
                "recorded_at": f"2026-04-03T12:0{1 if latest_action == 'publish' else 2}:00Z",
                "artifact_refs": [],
                "history": [{"action": latest_action, "status": "completed", "doc_input": "flows/workflow.aionis.md"}],
            }
        }
        save_session(session)

    consolidated = workbench.consolidate(limit=12, family_limit=4)
    family_row = next(item for item in consolidated["family_rows"] if item["task_family"] == task_family)
    doc_prior = family_row["family_doc_prior"]

    assert doc_prior["dominant_source_doc_id"] == "workflow-doc-1"
    assert doc_prior["dominant_doc_input"] == "flows/workflow.aionis.md"
    assert doc_prior["sample_count"] == 2
    assert doc_prior["dominant_event_source"] == "vscode_extension"
    assert doc_prior["editor_sync_count"] == 2
    assert family_row["doc_sample_count"] == 2
    assert family_row["doc_seed_ready"] is True

    dashboard = workbench.dashboard(limit=12, family_limit=4)
    assert dashboard["dashboard_summary"]["doc_prior_ready_count"] >= 1
    assert dashboard["dashboard_summary"]["doc_prior_blocked_count"] == 0
    assert dashboard["dashboard_summary"]["doc_editor_sync_family_count"] >= 1
    assert dashboard["dashboard_summary"]["doc_editor_sync_event_count"] >= 2
    dashboard_family_row = next(item for item in dashboard["family_rows"] if item["task_family"] == task_family)
    assert dashboard_family_row["prior_doc_source_doc_id"] == "workflow-doc-1"
    assert dashboard_family_row["prior_doc_sample_count"] == 2
    assert dashboard_family_row["prior_doc_seed_ready"] is True
    assert dashboard_family_row["prior_doc_event_source"] == "vscode_extension"


def test_dashboard_proof_summary_highlights_editor_driven_doc_reuse(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-dashboard-editor-proof")
    task_family = "task:docs"
    for idx in range(1, 3):
        session = workbench._initial_session(
            task_id=f"product-dashboard-editor-proof-{idx}",
            task="Prove editor-driven doc reuse is live.",
            target_files=["flows/workflow.aionis.md"],
            validation_commands=[],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = task_family
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.continuity_snapshot = {
            "task_family": task_family,
            "doc_workflow": {
                "latest_action": "resume",
                "status": "completed",
                "doc_input": "flows/workflow.aionis.md",
                "source_doc_id": "workflow-doc-proof",
                "handoff_anchor": "doc-proof-anchor",
                "selected_tool": "read",
                "event_source": "vscode_extension",
                "recorded_at": f"2026-04-03T12:0{idx}:00Z",
                "artifact_refs": [],
                "history": [{"action": "resume", "status": "completed", "doc_input": "flows/workflow.aionis.md"}],
            },
        }
        save_session(session)

    workbench.consolidate(limit=12, family_limit=4)
    dashboard = workbench.dashboard(limit=12, family_limit=4)

    assert dashboard["dashboard_summary"]["doc_prior_ready_count"] >= 1
    assert dashboard["dashboard_summary"]["doc_editor_sync_event_count"] >= 2
    assert dashboard["dashboard_summary"]["proof_summary"] == "recent families already have seed-ready priors, and editor-driven doc reuse is live"


def test_dream_surface_can_filter_to_seed_ready_promotions(tmp_path, monkeypatch) -> None:
    workbench = _prepare_workbench(tmp_path, monkeypatch, label="product-dream-filter")
    validation_command = "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    for idx, source in enumerate(
        ["workflow_closure", "manual_ingest", "validate"],
        start=1,
    ):
        session = workbench._initial_session(
            task_id=f"product-dream-filter-{idx}",
            task="Keep the demo family reusable.",
            target_files=["src/demo.py", "tests/test_demo.py"],
            validation_commands=[validation_command],
            apply_strategy=False,
        )
        session.status = "validated"
        session.selected_task_family = "task:demo"
        session.selected_trust_signal = "same_task_family"
        session.selected_family_scope = "same_task_family"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        session.promoted_insights = [f"Validation passed: {validation_command}"]
        session.last_validation_result = {
            "ok": True,
            "command": validation_command,
            "exit_code": 0,
            "summary": "Validation commands passed.",
            "output": "",
            "changed_files": ["src/demo.py", "tests/test_demo.py"],
        }
        session.continuity_snapshot = {
            "learning": {
                "auto_absorbed": source != "manual_ingest",
                "source": source,
                "task_family": "task:demo",
                "strategy_profile": "family_reuse_loop",
                "validation_style": "targeted_first",
                "validation_command": validation_command,
                "validation_summary": "Validation commands passed.",
                "working_set": ["src/demo.py", "tests/test_demo.py"],
                "role_sequence": ["investigator", "implementer", "verifier"],
                "artifact_refs": [],
            }
        }
        session.instrumentation_summary = InstrumentationSummary(
            task_family="task:demo",
            family_scope="same_task_family",
            family_hit=True,
            family_reason="Family-scoped strategy matched task:demo.",
            selected_pattern_hit_count=1,
            selected_pattern_miss_count=0,
            routed_artifact_known_count=2,
            routed_artifact_same_family_count=2,
            routed_artifact_other_family_count=0,
            routed_artifact_unknown_count=0,
            routed_artifact_hit_rate=1.0,
            routed_same_family_task_ids=[
                "product-dream-filter-1",
                "product-dream-filter-2",
                "product-dream-filter-3",
            ],
            routed_other_family_task_ids=[],
        )
        save_session(session)

    payload = workbench.dream(limit=12, family_limit=4, status_filter="seed_ready")

    assert payload["shell_view"] == "dream"
    assert payload["dream_status_filter"] == "seed_ready"
    assert payload["dream_promotion_count"] >= 1
    assert payload["dream_candidate_count"] == 0
    assert all(item["promotion_status"] == "seed_ready" for item in payload["dream_promotions"])
