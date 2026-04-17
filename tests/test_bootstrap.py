from __future__ import annotations

import json
import sys
import types
from pathlib import Path
import subprocess

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv)

langchain_agents = types.ModuleType("langchain.agents")
langchain_agents.create_agent = lambda *args, **kwargs: None
sys.modules.setdefault("langchain.agents", langchain_agents)

langchain_agents_middleware = types.ModuleType("langchain.agents.middleware")
langchain_agents_middleware.TodoListMiddleware = type("TodoListMiddleware", (), {})
langchain_agents_middleware.wrap_model_call = lambda *args, **kwargs: (lambda fn: fn)
langchain_agents_middleware.wrap_tool_call = lambda *args, **kwargs: (lambda fn: fn)
sys.modules.setdefault("langchain.agents.middleware", langchain_agents_middleware)

langchain_agents_middleware_types = types.ModuleType("langchain.agents.middleware.types")
langchain_agents_middleware_types.ModelResponse = type("ModelResponse", (), {})
sys.modules.setdefault("langchain.agents.middleware.types", langchain_agents_middleware_types)

langchain_anthropic_middleware = types.ModuleType("langchain_anthropic.middleware")
langchain_anthropic_middleware.AnthropicPromptCachingMiddleware = type(
    "AnthropicPromptCachingMiddleware", (), {}
)
sys.modules.setdefault("langchain_anthropic.middleware", langchain_anthropic_middleware)

langchain_openai = types.ModuleType("langchain_openai")
langchain_openai.ChatOpenAI = type("ChatOpenAI", (), {})
sys.modules.setdefault("langchain_openai", langchain_openai)

langchain_core_messages = types.ModuleType("langchain_core.messages")
langchain_core_messages.AIMessage = type("AIMessage", (), {"tool_calls": [], "usage_metadata": None})
langchain_core_messages.BaseMessage = type("BaseMessage", (), {})
langchain_core_messages.ToolMessage = type("ToolMessage", (), {"status": "success", "content": "", "name": None})
sys.modules.setdefault("langchain_core.messages", langchain_core_messages)

from aionis_workbench.runtime import AionisWorkbench, ValidationResult
from aionis_workbench.execution_packet import InstrumentationSummary
from aionis_workbench.session import (
    ArtifactReference,
    CollaborationPattern,
    DelegationPacket,
    DelegationReturn,
)
from aionis_workbench.consolidation_state import (
    consolidation_state_path,
    consolidation_summary_path,
    save_consolidation_summary,
)
from aionis_workbench.dream_state import save_dream_promotions
from aionis_workbench.session import auto_learning_path, save_auto_learning_snapshot, save_session


def _seed_python_repo(repo_root: Path) -> None:
    (repo_root / "src").mkdir()
    (repo_root / "tests").mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (repo_root / "src" / "demo.py").write_text("def add(a, b):\n    return a + b\n")
    (repo_root / "tests" / "test_demo.py").write_text("from demo import add\n")


def test_shell_status_uses_bootstrap_when_no_sessions(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.shell_status()

    assert payload["task_id"] is None
    assert payload["dashboard_summary"]["status"] == "empty"
    assert payload["status_line"]["task_family"] == "task:cold-start"
    assert payload["status_line"]["strategy_profile"] == "bootstrap_first_loop"
    assert payload["status_line"]["instrumentation_status"] == "cold_start"
    assert "task:cold-start" in payload["text"]


def test_doctor_reports_inspect_only_when_hosts_are_not_live_ready(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.doctor()

    assert payload["shell_view"] == "doctor"
    assert payload["mode"] == "inspect-only"
    assert payload["live_ready"] is False
    assert payload["live_ready_summary"] == "inspect-only: missing credentials + runtime"
    assert payload["capability_state"] == "inspect_only_missing_credentials_and_runtime"
    assert payload["capabilities"]["can_run_live_tasks"] is False
    assert "can inspect, validate, and ingest" in payload["capability_summary"]
    assert payload["setup_checklist"][0]["name"] == "bootstrap_initialized"
    assert payload["setup_checklist"][0]["command_hint"].startswith("aionis init --repo-root ")
    runtime_check = next(item for item in payload["setup_checklist"] if item["name"] == "runtime_available")
    assert runtime_check["command_hint"] == "curl -fsS http://127.0.0.1:3101/health"
    check_names = {item["name"]: item for item in payload["checks"]}
    assert check_names["repo_root"]["status"] == "available"
    assert check_names["bootstrap"]["status"] == "missing"
    assert any("inspect-only" in item for item in payload["recommendations"])


def test_doctor_summary_returns_compact_surface(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.doctor(summary=True)

    assert payload["shell_view"] == "doctor_summary"
    assert payload["mode"] == "inspect-only"
    assert payload["live_ready_summary"] == "inspect-only: missing credentials + runtime"
    assert payload["recovery_summary"] == "configure model credentials and restore runtime availability before retrying live execution"
    assert payload["pending_checklist_count"] >= 1


def test_doctor_one_line_returns_compact_line(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.doctor(one_line=True)

    assert payload["shell_view"] == "doctor_one_line"
    assert payload["summary_line"].startswith("doctor-summary: inspect-only: missing credentials + runtime")


def test_doctor_check_returns_named_runtime_check(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.doctor(check="runtime_host")

    assert payload["shell_view"] == "doctor_check"
    assert payload["check_name"] == "runtime_host"
    assert payload["found"] is True
    assert payload["source"] == "checks"


def test_setup_surfaces_pending_checklist_and_next_steps(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.setup()

    assert payload["shell_view"] == "setup"
    assert payload["mode"] == "inspect-only"
    assert payload["live_ready_summary"] == "inspect-only: missing credentials + runtime"
    assert payload["pending_count"] >= 1
    assert payload["pending_items"][0]["name"] == "bootstrap_initialized"
    assert payload["next_steps"][0].startswith("aionis init --repo-root ")


def test_setup_pending_only_hides_completed_items(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.setup(pending_only=True)

    assert payload["pending_only"] is True
    assert payload["completed_items"] == []
    assert payload["pending_items"][0]["name"] == "bootstrap_initialized"


def test_setup_summary_returns_compact_surface(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.setup(summary=True)

    assert payload["shell_view"] == "setup_summary"
    assert payload["recovery_summary"] == "configure model credentials and restore runtime availability before retrying live execution"
    assert payload["pending_count"] >= 1
    assert payload["next_step"].startswith("aionis init --repo-root ")


def test_setup_one_line_returns_compact_line(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.setup(one_line=True)

    assert payload["shell_view"] == "setup_one_line"
    assert payload["summary_line"].startswith("setup-summary: inspect-only: missing credentials + runtime")


def test_setup_check_returns_named_check(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.setup(check="bootstrap_initialized")

    assert payload["shell_view"] == "setup_check"
    assert payload["check_name"] == "bootstrap_initialized"
    assert payload["found"] is True


def test_initial_session_seeds_bootstrap_hints_for_empty_project(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-bootstrap-1",
        task="Set up the first narrow CLI task.",
        target_files=[],
        validation_commands=[],
        apply_strategy=False,
    )

    assert session.target_files
    assert session.validation_commands == ["PYTHONPATH=src python3 -m pytest -q"]
    assert session.continuity_snapshot["bootstrap"]["bootstrap_working_set"]
    assert session.continuity_snapshot["bootstrap"]["status"] == "bootstrap_ready"


def test_initialize_project_persists_bootstrap_and_imports_history(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "demo@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Demo User"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "Add initial parser tests"], check=True, capture_output=True)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.initialize_project()

    assert payload["initialized"] is True
    assert Path(payload["bootstrap_path"]).exists()
    assert payload["bootstrap_snapshot"]["history_status"] == "imported"
    assert payload["bootstrap_snapshot"]["recent_commit_subjects"][0] == "Add initial parser tests"
    assert payload["bootstrap_snapshot"]["bootstrap_focus"][:2] == ["src/demo.py", "tests/test_demo.py"]
    assert payload["bootstrap_snapshot"]["bootstrap_first_step"].startswith("Start with src/demo.py, tests/test_demo.py")
    assert payload["bootstrap_snapshot"]["bootstrap_validation_step"].startswith("Run PYTHONPATH=src python3 -m pytest -q")
    assert payload["setup"]["mode"] == "inspect-only"
    assert payload["setup"]["live_ready"] is False
    assert payload["setup"]["next_steps"]


def test_auto_learning_marks_successful_validation(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-learning-1",
        task="Add the first narrow test loop.",
        target_files=[],
        validation_commands=[],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    validation = ValidationResult(
        ok=True,
        command="PYTHONPATH=src python3 -m pytest -q",
        exit_code=0,
        summary="Validation commands passed.",
        output="",
        changed_files=["tests/test_demo.py", "src/demo.py"],
    )

    workbench._record_auto_learning(session=session, source="validate", validation=validation)
    workbench._apply_validation_feedback(session, validation)
    workbench._save_session(session)

    assert session.continuity_snapshot["learning"]["auto_absorbed"] is True
    assert session.continuity_snapshot["learning"]["source"] == "validate"
    assert session.continuity_snapshot["passive_observation"]["recorded"] is True
    assert session.continuity_snapshot["passive_observation"]["changed_files"]
    assert session.target_files[:2] == ["tests/test_demo.py", "src/demo.py"]
    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest -q"
    assert session.maintenance_summary.auto_learning_status == "auto_absorbed"
    assert session.maintenance_summary.last_learning_source == "validate"
    assert session.maintenance_summary.passive_observation_status == "recorded"
    assert session.maintenance_summary.observed_changed_file_count >= 1
    assert any(item.startswith("Auto-learned success path via validate.") for item in session.promoted_insights)
    assert any(item.startswith("Observed changed files via validate:") for item in session.promoted_insights)
    persisted = auto_learning_path(str(tmp_path))
    assert persisted.exists()
    payload = json.loads(persisted.read_text())
    assert payload["recent_samples"][0]["task_id"] == "demo-learning-1"
    assert payload["recent_samples"][0]["source"] == "validate"
    assert payload["recent_samples"][0]["task_family"] == "task:testing"
    assert payload["recent_samples"][0]["observed_changed_files"]


def test_passive_validate_promotes_new_default_validation_path(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-learning-2",
        task="Refine the current validation path.",
        target_files=["src/legacy.py"],
        validation_commands=["python3 -m pytest tests/test_legacy.py -q"],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    validation = ValidationResult(
        ok=True,
        command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        exit_code=0,
        summary="Validation commands passed.",
        output="",
        changed_files=["tests/test_demo.py", "src/demo.py"],
    )

    workbench._record_auto_learning(session=session, source="validate", validation=validation)
    workbench._apply_validation_feedback(session, validation)
    workbench._save_session(session)

    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    assert session.target_files[:2] == ["tests/test_demo.py", "src/demo.py"]
    inspected = workbench.inspect_session(task_id="demo-learning-2")
    strategy = inspected["canonical_views"]["strategy"]
    assert strategy["working_set"][:2] == ["tests/test_demo.py", "src/demo.py"]
    assert strategy["validation_paths"][0] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"


def test_collect_changed_files_uses_git_status_and_untracked_files(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "demo@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Demo User"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "initial"], check=True, capture_output=True)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    (tmp_path / "src" / "demo.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "tests" / "test_extra.py").write_text("def test_extra():\n    assert True\n")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    changed = workbench._collect_changed_files()

    assert "src/demo.py" in changed
    assert "tests/test_extra.py" in changed


def test_workflow_fix_marks_workflow_closure_learning(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-fix-1",
        task="Close the first validation loop.",
        target_files=[],
        validation_commands=["python3 -c \"print('ok')\""],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    workbench._save_session(session)

    payload = workbench.workflow_fix(task_id="demo-fix-1")

    assert payload["shell_view"] == "fix"
    assert payload["validation"]["ok"] is True
    assert payload["controller_action_bar"] == {
        "task_id": "demo-fix-1",
        "status": "completed",
        "recommended_command": "/show demo-fix-1",
        "allowed_commands": ["/show demo-fix-1", "/session demo-fix-1"],
    }
    reloaded = workbench.inspect_session(task_id="demo-fix-1")
    maintenance = reloaded["canonical_views"]["maintenance"]
    assert maintenance["auto_learning_status"] == "auto_absorbed"
    assert maintenance["last_learning_source"] == "workflow_closure"


def test_workflow_next_surfaces_controller_action_bar(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-next-1",
        task="Plan the next narrow validation loop.",
        target_files=[],
        validation_commands=["python3 -c \"print('ok')\""],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    workbench._save_session(session)

    payload = workbench.workflow_next(task_id="demo-next-1")

    assert payload["shell_view"] == "next"
    assert payload["validation"]["ok"] is True
    assert payload["controller_action_bar"] == {
        "task_id": "demo-next-1",
        "status": "completed",
        "recommended_command": "/show demo-next-1",
        "allowed_commands": ["/show demo-next-1", "/session demo-next-1"],
    }


def test_ingest_marks_manual_learning_without_auto_learning_store(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.ingest(
        task_id="demo-ingest-1",
        task="Record a validated manual testing task.",
        summary="Recorded the validated manual task.",
        target_files=["tests/test_demo.py", "src/demo.py"],
        changed_files=["tests/test_demo.py", "src/demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        validation_ok=True,
        validation_summary="Validation commands passed.",
    )

    assert payload.runner == "ingest"
    inspected = workbench.inspect_session(task_id="demo-ingest-1")
    maintenance = inspected["canonical_views"]["maintenance"]
    assert maintenance["auto_learning_status"] == "recorded"
    assert maintenance["last_learning_source"] == "manual_ingest"
    session_payload = inspected["canonical_surface"]["continuity_snapshot"]
    assert session_payload["learning"]["auto_absorbed"] is False
    assert session_payload["learning"]["source"] == "manual_ingest"
    assert not auto_learning_path(str(tmp_path)).exists()


def test_initialize_project_loads_recent_auto_learning_into_bootstrap(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    save_auto_learning_snapshot(
        repo_root=str(tmp_path),
        project_scope="project:demo/bootstrap",
        payload={
            "project_identity": "demo/bootstrap",
            "project_scope": "project:demo/bootstrap",
            "recent_samples": [
                {
                    "task_id": "demo-learned-1",
                    "source": "validate",
                    "task_family": "task:testing",
                    "strategy_profile": "family_reuse_loop",
                    "validation_command": "PYTHONPATH=src python3 -m pytest -q",
                    "working_set": ["tests/test_demo.py", "src/demo.py"],
                    "role_sequence": ["investigator", "implementer", "verifier"],
                    "artifact_refs": [],
                }
            ],
        },
    )

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    object.__setattr__(workbench._config, "project_identity", "demo/bootstrap")
    object.__setattr__(workbench._config, "project_scope", "project:demo/bootstrap")
    payload = workbench.initialize_project()

    assert payload["bootstrap_snapshot"]["recent_auto_learning"][0]["task_id"] == "demo-learned-1"


def test_initialize_project_loads_consolidated_family_priors_into_bootstrap(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    summary_path = consolidation_summary_path(str(tmp_path))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "family_rows": [
                    {
                        "task_family": "task:termui",
                        "status": "strong_family",
                        "confidence": 0.91,
                        "sample_count": 3,
                        "recent_success_count": 2,
                        "dominant_strategy_profile": "interactive_reuse_loop",
                        "dominant_validation_style": "targeted_first",
                        "dominant_validation_command": "PYTHONPATH=src python3 -m pytest tests/test_termui.py -q",
                        "dominant_working_set": ["src/demo.py", "tests/test_demo.py"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    payload = workbench.initialize_project()

    priors = payload["bootstrap_snapshot"]["recent_family_priors"]
    assert priors[0]["task_family"] == "task:termui"
    assert priors[0]["dominant_strategy_profile"] == "interactive_reuse_loop"
    assert priors[0]["confidence"] == 0.91
    assert priors[0]["seed_ready"] is True
    assert priors[0]["seed_gate"] == "ready"
    assert payload["bootstrap_snapshot"]["bootstrap_reuse_summary"].startswith("recent prior: task:termui via interactive_reuse_loop")
    assert "Loaded family priors:" in payload["bootstrap_snapshot"]["notes"][-1]


def test_initial_session_uses_consolidated_family_prior_validation_seed(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    summary_path = consolidation_summary_path(str(tmp_path))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "family_rows": [
                    {
                        "task_family": "task:demo",
                        "status": "strong_family",
                        "confidence": 0.88,
                        "sample_count": 3,
                        "recent_success_count": 2,
                        "dominant_strategy_profile": "family_reuse_loop",
                        "dominant_validation_style": "targeted_first",
                        "dominant_validation_command": "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
                        "dominant_working_set": ["tests/test_demo.py", "src/demo.py"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-prior-seed-1",
        task="Keep the demo test loop narrow.",
        target_files=["tests/test_demo.py"],
        validation_commands=[],
        apply_strategy=True,
    )

    assert session.selected_task_family == "task:demo"
    assert session.selected_trust_signal == "broader_similarity"
    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"


def test_initial_session_boosts_working_set_from_consolidated_prior_when_trust_is_weak(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    summary_path = consolidation_summary_path(str(tmp_path))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "family_rows": [
                    {
                        "task_family": "task:demo",
                        "status": "strong_family",
                        "confidence": 0.82,
                        "sample_count": 3,
                        "recent_success_count": 2,
                        "dominant_strategy_profile": "family_reuse_loop",
                        "dominant_validation_style": "targeted_first",
                        "dominant_validation_command": "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
                        "dominant_working_set": ["src/special_demo.py", "tests/test_special_demo.py"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-prior-seed-2",
        task="Preserve the current demo loop.",
        target_files=[],
        validation_commands=[],
        apply_strategy=True,
    )

    assert session.selected_task_family.startswith("task:demo")
    assert session.selected_trust_signal == "broader_similarity"
    assert session.target_files[:2] == ["src/special_demo.py", "tests/test_special_demo.py"]
    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"


def test_initial_session_does_not_use_low_confidence_family_prior_seed(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    summary_path = consolidation_summary_path(str(tmp_path))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "family_rows": [
                    {
                        "task_family": "task:demo",
                        "status": "mixed_family",
                        "confidence": 0.42,
                        "sample_count": 1,
                        "recent_success_count": 0,
                        "dominant_strategy_profile": "family_reuse_loop",
                        "dominant_validation_style": "targeted_first",
                        "dominant_validation_command": "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
                        "dominant_working_set": ["src/special_demo.py", "tests/test_special_demo.py"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-prior-seed-3",
        task="Preserve the current demo loop.",
        target_files=[],
        validation_commands=[],
        apply_strategy=True,
    )

    assert session.selected_task_family == "task:demo"
    assert session.selected_trust_signal == "broader_similarity"
    assert session.target_files[:2] != ["src/special_demo.py", "tests/test_special_demo.py"]
    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest -q"


def test_initial_session_prefers_seed_ready_dream_prior_over_consolidation_seed(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    workbench = AionisWorkbench(repo_root=str(tmp_path))
    summary_path = consolidation_summary_path(str(tmp_path))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "family_rows": [
                    {
                        "task_family": "task:demo",
                        "status": "mixed_family",
                        "confidence": 0.42,
                        "sample_count": 1,
                        "recent_success_count": 0,
                        "dominant_strategy_profile": "family_reuse_loop",
                        "dominant_validation_style": "targeted_first",
                        "dominant_validation_command": "PYTHONPATH=src python3 -m pytest -q",
                        "dominant_working_set": ["src/fallback_demo.py", "tests/test_fallback_demo.py"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    save_dream_promotions(
        repo_root=str(tmp_path),
        project_scope=workbench._config.project_scope,
        payload={
            "summary": {"seed_ready_count": 1},
            "promotions": [
                {
                    "prior_id": "task-demo::family-reuse-loop",
                    "task_family": "task:demo",
                    "strategy_profile": "family_reuse_loop",
                    "validation_style": "targeted_first",
                    "dominant_validation_command": "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
                    "dominant_working_set": ["src/demo.py", "tests/test_demo.py"],
                    "promotion_status": "seed_ready",
                    "promotion_reason": "candidate passed held-out verification and met seed thresholds",
                    "confidence": 0.91,
                    "sample_count": 4,
                    "recent_success_count": 3,
                    "verification_summary": "candidate held across the held-out family slice",
                    "promoted_at": "2026-04-03T00:00:00+00:00",
                }
            ],
        },
    )

    session = workbench._initial_session(
        task_id="demo-prior-seed-4",
        task="Keep the demo loop stable.",
        target_files=[],
        validation_commands=[],
        apply_strategy=True,
    )

    assert session.selected_task_family == "task:demo"
    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    assert session.target_files[:2] == ["src/demo.py", "tests/test_demo.py"]


def test_initial_session_uses_promoted_prior_after_manual_consolidate(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    validation_command = "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    for idx, source in enumerate(
        ["workflow_closure", "manual_ingest", "validate"],
        start=1,
    ):
        session = workbench._initial_session(
            task_id=f"demo-promoted-prior-{idx}",
            task="Keep the demo loop narrow.",
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
                "demo-promoted-prior-1",
                "demo-promoted-prior-2",
                "demo-promoted-prior-3",
            ],
            routed_other_family_task_ids=[],
        )
        save_session(session)

    payload = workbench.consolidate(limit=12, family_limit=4)
    session = workbench._initial_session(
        task_id="demo-promoted-prior-seeded",
        task="Preserve the current demo loop.",
        target_files=[],
        validation_commands=[],
        apply_strategy=True,
    )

    assert payload["dream_summary"]["seed_ready_count"] >= 1
    assert session.selected_task_family == "task:demo"
    assert session.validation_commands[0] == validation_command
    assert session.target_files[:2] == ["src/demo.py", "tests/test_demo.py"]


def test_initial_session_reuses_effective_edit_scope_for_implementer_packets(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    validation_command = "python3 -c \"print('ok')\""
    prior = workbench._initial_session(
        task_id="demo-effective-scope-prior",
        task="Repair the demo export path.",
        target_files=["src", "README.md"],
        validation_commands=[validation_command],
        apply_strategy=False,
    )
    prior.status = "validated"
    prior.selected_task_family = "task:repair-demo"
    prior.selected_trust_signal = "same_task_family"
    prior.selected_family_scope = "same_task_family"
    prior.selected_strategy_profile = "family_reuse_loop"
    prior.selected_validation_style = "targeted_first"
    prior.selected_role_sequence = ["investigator", "implementer", "verifier"]
    prior.delegation_packets = [
        DelegationPacket(role="investigator", mission="Inspect the narrow demo failure.", working_set=["src/demo.py"]),
        DelegationPacket(
            role="implementer",
            mission="Patch the demo export path.",
            working_set=["src", "README.md"],
            preferred_artifact_refs=[".aionis-workbench/artifacts/investigator.json"],
            routing_reason="Implementer inherits the narrow diagnosis before editing.",
        ),
        DelegationPacket(
            role="verifier",
            mission="Re-run the narrow validation loop.",
            working_set=["src/demo.py"],
            acceptance_checks=[validation_command],
        ),
    ]
    prior.delegation_returns = [
        DelegationReturn(
            role="investigator",
            status="success",
            summary="Narrowed src/demo.py",
            evidence=["Root cause isolated to the export path."],
            working_set=["src/demo.py"],
            handoff_text="investigator summary: narrowed src/demo.py",
        ),
        DelegationReturn(
            role="implementer",
            status="success",
            summary="Patched src/demo.py",
            evidence=["Touched src/demo.py."],
            working_set=["src/demo.py"],
            artifact_refs=[".aionis-workbench/artifacts/investigator.json"],
            handoff_text="implementer summary: patched src/demo.py",
        ),
        DelegationReturn(
            role="verifier",
            status="success",
            summary="Validation passed.",
            evidence=[f"Command: {validation_command}"],
            working_set=["src/demo.py"],
            acceptance_checks=[validation_command],
            handoff_text="verifier summary: validation passed",
        ),
    ]
    prior.collaboration_patterns = [
        CollaborationPattern(
            kind="effective_edit_scope_strategy",
            role="implementer",
            summary="Start implementation from src/demo.py before widening back to the packet scope.",
            reuse_hint="src/demo.py",
            confidence=0.88,
            task_family="task:repair-demo",
        ),
        CollaborationPattern(
            kind="artifact_scope_strategy",
            role="implementer",
            summary="Anchor implementer context to the investigator artifact first.",
            reuse_hint=".aionis-workbench/artifacts/investigator.json",
            confidence=0.82,
            task_family="task:repair-demo",
        ),
    ]
    prior.artifacts = [
        ArtifactReference(
            artifact_id="artifact-investigator-1",
            kind="analysis_note",
            role="investigator",
            summary="Investigator narrowed the export mismatch to src/demo.py.",
            path=".aionis-workbench/artifacts/investigator.json",
        )
    ]
    save_session(prior)

    session = workbench._initial_session(
        task_id="demo-effective-scope-next",
        task="Repair the demo export path.",
        target_files=["src", "README.md"],
        validation_commands=[validation_command],
        apply_strategy=True,
    )

    implementer_packet = next(packet for packet in session.delegation_packets if packet.role == "implementer")

    assert session.strategy_summary is not None
    assert session.strategy_summary.selected_working_set == ["src/demo.py"]
    assert any("effective_edit_scope_strategy" in item for item in session.selected_pattern_summaries)
    assert any("artifact_scope_strategy" in item for item in session.selected_pattern_summaries)
    assert implementer_packet.working_set == ["src/demo.py"]
    assert implementer_packet.preferred_artifact_refs == [".aionis-workbench/artifacts/investigator.json"]
    assert session.continuity_snapshot["prior_strategy_working_sets"][0] == "src/demo.py"
    assert ".aionis-workbench/artifacts/investigator.json" in session.continuity_snapshot["prior_artifact_refs"]


def test_manual_consolidation_summarizes_recent_project_learning(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session_one = workbench._initial_session(
        task_id="demo-consolidate-1",
        task="Strengthen interactive family priors.",
        target_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session_one.selected_task_family = "task:testing"
    session_one.selected_trust_signal = "same_task_family"
    session_one.selected_strategy_profile = "family_reuse_loop"
    session_one.continuity_snapshot = {
        "learning": {
            "auto_absorbed": False,
            "source": "manual_ingest",
            "task_family": "task:testing",
        },
        "prior_artifact_refs": ["a.json", "a.json", "b.json"],
        "prior_collaboration_patterns": ["pattern-one", "pattern-one"],
    }
    session_one.collaboration_patterns = [
        CollaborationPattern(
            kind="artifact_routing_strategy",
            role="implementer",
            summary="Reuse the same routed artifact pair.",
            reuse_hint="Reuse the same routed artifact pair.",
            task_family="task:testing",
            affinity_level="same_task_family",
        )
    ]
    save_session(session_one)

    session_two = workbench._initial_session(
        task_id="demo-consolidate-2",
        task="Preserve the same narrow testing loop.",
        target_files=["tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session_two.selected_task_family = "task:testing"
    session_two.selected_trust_signal = "broader_similarity"
    session_two.selected_strategy_profile = "family_reuse_loop"
    session_two.continuity_snapshot = {
        "learning": {
            "auto_absorbed": True,
            "source": "workflow_closure",
            "task_family": "task:testing",
        },
        "passive_observation": {
            "recorded": True,
            "source": "validate",
            "changed_files": ["tests/test_demo.py"],
        },
        "prior_artifact_refs": ["a.json", "c.json", "c.json"],
    }
    session_two.collaboration_patterns = [
        CollaborationPattern(
            kind="artifact_routing_strategy",
            role="implementer",
            summary="Reuse the same routed artifact pair.",
            reuse_hint="Reuse the same routed artifact pair.",
            task_family="task:testing",
            affinity_level="same_task_family",
        )
    ]
    save_session(session_two)

    payload = workbench.consolidate(limit=12, family_limit=4)

    assert payload["shell_view"] == "consolidate"
    assert payload["sessions_reviewed"] == 2
    assert payload["families_reviewed"] == 1
    assert payload["patterns_merged"] >= 1
    assert payload["patterns_suppressed"] >= 1
    assert payload["continuity_cleaned"] >= 2
    assert Path(payload["consolidation_path"]).exists()
    assert consolidation_summary_path(str(tmp_path)).exists()
    assert payload["family_rows"][0]["task_family"] == "task:testing"
    assert payload["family_rows"][0]["session_count"] == 2
    assert payload["family_rows"][0]["sample_count"] == 2
    assert payload["family_rows"][0]["recent_success_count"] == 0
    assert payload["family_rows"][0]["manual_ingest_count"] == 1
    assert payload["family_rows"][0]["workflow_closure_count"] == 1
    assert payload["family_rows"][0]["passive_observation_count"] == 1
    assert payload["family_rows"][0]["confidence"] >= 0.2
    assert payload["family_rows"][0]["seed_ready"] is False
    assert payload["family_rows"][0]["seed_gate"] in {"confidence", "recent_success"}
    assert payload["family_rows"][0]["dominant_strategy_profile"] == "family_reuse_loop"
    assert payload["family_rows"][0]["dominant_validation_command"] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    assert "src/demo.py" in payload["family_rows"][0]["dominant_working_set"]


def test_auto_consolidation_runs_after_backfill_when_gates_pass(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/demo-auto-consolidate-pass-{str(tmp_path).replace('/', '_')}")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE", "true")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_MIN_HOURS", "0")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_MIN_NEW_SESSIONS", "1")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_SCAN_THROTTLE_MINUTES", "0")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-auto-consolidate-1",
        task="Keep the current testing family healthy.",
        target_files=["tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    save_session(session)

    payload = workbench.backfill(task_id="demo-auto-consolidate-1")

    assert payload["auto_consolidation"]["status"] == "completed"
    assert payload["auto_consolidation"]["trigger"] == "backfill"
    assert Path(payload["auto_consolidation"]["consolidation_path"]).exists()
    assert consolidation_summary_path(str(tmp_path)).exists()
    assert consolidation_state_path(str(tmp_path)).exists()


def test_auto_consolidation_respects_session_gate_and_scan_throttle(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/demo-auto-consolidate-throttle-{str(tmp_path).replace('/', '_')}")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE", "true")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_MIN_HOURS", "0")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_MIN_NEW_SESSIONS", "3")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_SCAN_THROTTLE_MINUTES", "60")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-auto-consolidate-2",
        task="Hold off consolidation until enough sessions accumulate.",
        target_files=["tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    save_session(session)

    first = workbench.backfill(task_id="demo-auto-consolidate-2")
    second = workbench.backfill(task_id="demo-auto-consolidate-2")

    assert first["auto_consolidation"]["status"] == "skipped"
    assert first["auto_consolidation"]["reason"] == "session_gate"
    assert first["auto_consolidation"]["new_session_count"] == 1
    assert second["auto_consolidation"]["status"] == "skipped"
    assert second["auto_consolidation"]["reason"] == "scan_throttle"


def test_shell_status_surfaces_background_consolidation_state(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")
    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"tests/demo-background-status-{str(tmp_path).replace('/', '_')}")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE", "true")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_MIN_HOURS", "0")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_MIN_NEW_SESSIONS", "1")
    monkeypatch.setenv("AIONIS_AUTO_CONSOLIDATE_SCAN_THROTTLE_MINUTES", "0")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-background-1",
        task="Keep the testing family healthy.",
        target_files=["tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    save_session(session)
    workbench.backfill(task_id="demo-background-1")

    payload = workbench.shell_status(task_id="demo-background-1")

    assert payload["background"]["status"] == "completed"
    assert payload["background"]["summary"]["sessions_reviewed"] >= 1
    assert payload["status_line"]["consolidation_status"] == "completed"
    assert "consolidate:completed" in payload["text"]


def test_dashboard_surfaces_consolidated_prior_seed_state(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="demo-dashboard-1",
        task="Keep the testing family healthy.",
        target_files=["tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.selected_task_family = "task:testing"
    session.selected_strategy_profile = "family_reuse_loop"
    save_session(session)

    save_consolidation_summary(
        repo_root=str(tmp_path),
        project_scope=workbench._config.project_scope,
        payload={
            "family_rows": [
                {
                    "task_family": "task:demo",
                    "status": "strong_family",
                    "confidence": 0.83,
                    "sample_count": 3,
                    "recent_success_count": 2,
                    "seed_ready": True,
                    "seed_gate": "ready",
                    "seed_reason": "strong prior from 3 samples, confidence 0.83, recent_success=2",
                    "seed_recommendation": "reuse this prior as a seed fallback when live family trust is weak",
                }
            ]
        },
    )

    payload = workbench.dashboard(limit=12, family_limit=4)

    assert payload["dashboard_summary"]["prior_seed_ready_count"] == 1
    assert payload["dashboard_summary"]["prior_seed_blocked_count"] == 0
    assert payload["dashboard_summary"]["blocked_family_recommendations"] == []
    assert payload["family_rows"][0]["task_family"] == "task:demo"
    assert payload["family_rows"][0]["prior_seed_ready"] is True
    assert payload["family_rows"][0]["prior_seed_gate"] == "ready"
    assert payload["family_rows"][0]["prior_seed_recommendation"] == "reuse this prior as a seed fallback when live family trust is weak"
