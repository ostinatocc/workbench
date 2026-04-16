from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from aionis_workbench.config import WorkbenchConfig
from aionis_workbench.openai_agents_execution_host import (
    OpenAIAgentsExecutionHost,
    OpenAIAgentsModelInvokeTimeout,
    OpenAIAgentsPreparedAgent,
)
from aionis_workbench.tracing import TraceRecorder


def _base_config(tmp_path) -> WorkbenchConfig:
    return WorkbenchConfig(
        execution_host_runtime="openai_agents",
        model="gpt-5",
        system_prompt=None,
        provider="openai",
        api_key="test-key",
        base_url="https://api.openai.com/v1",
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
    )


def test_openai_agents_execution_host_describe_reports_missing_dependency(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: False,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())

    payload = host.describe()

    assert payload["name"] == "openai_agents_local_shell"
    assert payload["execution_runtime"] == "openai_agents"
    assert payload["backend"] == "Agent+Runner"
    assert payload["supports_live_tasks"] is False
    assert payload["health_reason"] == "execution_host_dependency_missing"
    assert host.supports_live_tasks() is False


def test_openai_agents_execution_host_describe_reports_ready_when_dependency_and_credentials_exist(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())

    payload = host.describe()

    assert payload["supports_live_tasks"] is True
    assert payload["health_status"] == "available"
    assert payload["health_reason"] is None
    assert host.supports_live_tasks() is True


def test_openai_agents_execution_host_rejects_unsupported_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    config = replace(_base_config(tmp_path), provider="offline", api_key=None, base_url=None)
    host = OpenAIAgentsExecutionHost(config=config, trace=TraceRecorder())

    payload = host.describe()

    assert payload["supports_live_tasks"] is False
    assert payload["health_reason"] == "execution_host_provider_unsupported"


def test_openai_agents_execution_host_probe_requires_dependency_and_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: False,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())

    with pytest.raises(ValueError, match="auth probe requires"):
        host.probe_live_model_auth()


def test_openai_agents_execution_host_probe_retries_after_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.time.sleep", lambda _seconds: None)
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    calls = {"count": 0}

    def _fake_run_json_agent(*, system_prompt: str, user_input: str, timeout_seconds: float, agent_name: str):
        calls["count"] += 1
        assert timeout_seconds == 20.0
        if calls["count"] == 1:
            raise OpenAIAgentsModelInvokeTimeout("OpenAI Agents SDK model invocation exceeded the configured timeout.")
        return {"ok": True}

    monkeypatch.setattr(host, "_run_json_agent", _fake_run_json_agent)

    payload = host.probe_live_model_auth()

    assert payload == {"ok": True}
    assert calls["count"] == 2


def test_openai_agents_execution_host_build_agent_returns_prepared_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())

    prepared = host.build_agent(
        system_parts=["system", "memory"],
        memory_sources=["src/app.py"],
        timeout_pressure=False,
        root_dir=str(tmp_path),
        use_builtin_subagents=True,
    )

    assert isinstance(prepared, OpenAIAgentsPreparedAgent)
    assert prepared.root_dir == str(tmp_path)
    assert prepared.memory_sources == ["src/app.py"]
    assert prepared.use_builtin_subagents is True


def test_openai_agents_execution_host_uses_explicit_chat_model_for_openrouter(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    config = replace(
        _base_config(tmp_path),
        provider="openrouter",
        model="z-ai/glm-5.1",
        base_url="https://openrouter.ai/api/v1",
    )
    host = OpenAIAgentsExecutionHost(config=config, trace=TraceRecorder())

    model = host._runner_model(object())

    assert model.__class__.__name__ == "OpenAIChatCompletionsModel"
    assert getattr(model, "model") == "z-ai/glm-5.1"


def test_openai_agents_execution_host_invoke_runs_local_tools_and_records_trace(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    (tmp_path / "README.md").write_text("seed file\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class _FakeAgent:
        def __init__(self, *, name, instructions, model, tools) -> None:
            self.name = name
            self.instructions = instructions
            self.model = model
            self.tools = tools
            captured["name"] = name
            captured["instructions"] = instructions
            captured["model"] = model
            captured["tools"] = tools

    class _FakeRunner:
        @staticmethod
        def run_sync(agent, user_input):
            captured["user_input"] = user_input
            tools = {tool.__name__: tool for tool in agent.tools}
            assert "Relevant memory sources:" in agent.instructions
            read_text = tools["read_file"]("README.md")
            tools["write_file"]("notes.txt", read_text + "changed\n")
            return SimpleNamespace(final_output="implemented via openai-agents")

    def _fake_function_tool(fn):
        return fn

    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    monkeypatch.setattr(host, "_configure_openai_agents_client", lambda: None)
    monkeypatch.setattr(
        host,
        "_import_agents_runtime",
        lambda: (_FakeAgent, _FakeRunner, _fake_function_tool, lambda *args, **kwargs: None, lambda *args, **kwargs: None),
    )

    prepared = host.build_agent(
        system_parts=["system prompt"],
        memory_sources=["README.md"],
        timeout_pressure=False,
        root_dir=str(tmp_path),
    )
    output = host.invoke(
        prepared,
        {"messages": [{"role": "user", "content": "Read the seed file and create notes.txt"}]},
    )

    assert output == "implemented via openai-agents"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "seed file\nchanged\n"
    assert captured["model"] == "gpt-5"
    assert captured["user_input"] == "Read the seed file and create notes.txt"
    trace_steps = host._trace.export()
    assert [step.tool_name for step in trace_steps] == ["read_file", "write_file", "workbench.model"]
    assert isinstance(captured["tools"], list)
    assert {tool.__name__ for tool in captured["tools"]} == {"exec_command", "read_file", "write_file", "list_files"}


def test_openai_agents_execution_host_build_delivery_agent_marks_delivery_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())

    prepared = host.build_delivery_agent(
        system_parts=["delivery system"],
        memory_sources=["src/App.tsx"],
        root_dir=str(tmp_path),
    )

    assert isinstance(prepared, OpenAIAgentsPreparedAgent)
    assert prepared.delivery_mode is True
    assert prepared.use_builtin_subagents is False
    assert "Delivery mode is active." in prepared.system_prompt


def test_openai_agents_execution_host_invoke_delivery_task_detects_ready_artifact_and_writes_trace(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    captured: dict[str, object] = {}

    class _FakeAgent:
        def __init__(self, *, name, instructions, model, tools) -> None:
            self.name = name
            self.instructions = instructions
            self.model = model
            self.tools = tools
            captured["tools"] = tools
            captured["instructions"] = instructions

    class _FakeRunner:
        @staticmethod
        def run_sync(agent, user_input):
            captured["user_input"] = user_input
            tools = {tool.__name__: tool for tool in agent.tools}
            tools["exec_command"](
                "python3 -c \"from pathlib import Path; Path('dist').mkdir(exist_ok=True); Path('dist/index.html').write_text('<html>ok</html>', encoding='utf-8')\" # build"
            )
            tools["write_file"]("src/App.tsx", "export const implemented = true;\n")
            return SimpleNamespace(final_output="delivery complete")

    def _fake_function_tool(fn):
        return fn

    trace_path = tmp_path / ".aionis-delivery-trace.json"
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    monkeypatch.setattr(host, "_configure_openai_agents_client", lambda: None)
    monkeypatch.setattr(
        host,
        "_import_agents_runtime",
        lambda: (_FakeAgent, _FakeRunner, _fake_function_tool, lambda *args, **kwargs: None, lambda *args, **kwargs: None),
    )

    result = host.invoke_delivery_task(
        system_parts=["delivery system"],
        memory_sources=["src/App.tsx"],
        root_dir=str(tmp_path),
        task="Implement the first app shell.",
        timeout_seconds=30.0,
        trace_path=str(trace_path),
    )

    assert result == "Build completed and delivery artifact is ready."
    assert (tmp_path / "dist" / "index.html").exists()
    assert trace_path.exists()
    trace_payload = trace_path.read_text(encoding="utf-8")
    assert '"tool_name": "execute"' in trace_payload
    assert '"tool_name": "write_file"' in trace_payload
    assert "Implement the first app shell." == captured["user_input"]


def test_openai_agents_execution_host_plan_app_live_uses_json_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    captured: dict[str, object] = {}

    def _fake_run_json_agent(*, system_prompt: str, user_input: str, timeout_seconds: float, agent_name: str):
        captured["system_prompt"] = system_prompt
        captured["user_input"] = user_input
        captured["timeout_seconds"] = timeout_seconds
        captured["agent_name"] = agent_name
        return {"title": "Demo", "design_direction": "Clean shell", "planning_rationale": ["a", "b"], "sprint_1": {}}

    monkeypatch.setattr(host, "_run_json_agent", _fake_run_json_agent)

    payload = host.plan_app_live(prompt="Build a focused product shell")

    assert payload["title"] == "Demo"
    assert captured["agent_name"] == "Workbench live planner"
    assert captured["timeout_seconds"] == host.live_app_planner_timeout_seconds()
    assert "Project request: Build a focused product shell" in str(captured["user_input"])


def test_openai_agents_execution_host_evaluate_sprint_live_uses_json_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    captured: dict[str, object] = {}

    def _fake_run_json_agent(*, system_prompt: str, user_input: str, timeout_seconds: float, agent_name: str):
        captured["system_prompt"] = system_prompt
        captured["user_input"] = json.loads(user_input)
        captured["timeout_seconds"] = timeout_seconds
        captured["agent_name"] = agent_name
        return {"status": "passed", "summary": "Looks good.", "passing_criteria": ["ship"], "failing_criteria": [], "blocker_notes": [], "criteria_scores": {"ship": 1.0}}

    monkeypatch.setattr(host, "_run_json_agent", _fake_run_json_agent)

    payload = host.evaluate_sprint_live(
        product_spec={"title": "Demo"},
        sprint_contract={"goal": "Ship"},
        evaluator_criteria=[{"name": "ship", "threshold": 0.8}],
        latest_execution_attempt={"execution_summary": "done"},
        execution_focus="focused execution",
        summary="summary",
        blocker_notes=["none"],
        requested_status="auto",
        criteria_scores={"ship": 0.9},
    )

    assert payload["status"] == "passed"
    assert captured["agent_name"] == "Workbench live evaluator"
    assert captured["timeout_seconds"] == host.live_app_evaluator_timeout_seconds()
    assert captured["user_input"]["execution_focus"] == "focused execution"
    assert captured["user_input"]["criteria_scores"] == {"ship": 0.9}


def test_openai_agents_execution_host_negotiate_revise_replan_generate_use_json_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    calls: list[tuple[str, dict[str, object], float]] = []

    def _fake_run_json_agent(*, system_prompt: str, user_input: str, timeout_seconds: float, agent_name: str):
        calls.append((agent_name, json.loads(user_input), timeout_seconds))
        if agent_name == "Workbench live negotiator":
            return {"recommended_action": "revise_current_sprint", "planner_response": ["tighten scope"], "sprint_negotiation_notes": ["retry"]}
        if agent_name == "Workbench live revisor":
            return {"revision_summary": "Narrowed scope.", "must_fix": ["scope"], "must_keep": ["check"]}
        if agent_name == "Workbench live replanner":
            return {"goal": "Ship narrower scope", "scope": ["one"], "acceptance_checks": ["check"], "done_definition": ["done"], "replan_note": "narrowed"}
        return {"execution_summary": "Implement narrow slice.", "changed_target_hints": ["src/App.tsx"]}

    monkeypatch.setattr(host, "_run_json_agent", _fake_run_json_agent)

    negotiate = host.negotiate_sprint_live(
        product_spec={"title": "Demo"},
        sprint_contract={"goal": "Ship"},
        latest_evaluation={"status": "failed"},
        planned_sprints=[{"goal": "Sprint 1"}],
        objections=["too broad"],
    )
    revise = host.revise_sprint_live(
        product_spec={"title": "Demo"},
        sprint_contract={"goal": "Ship"},
        latest_evaluation={"status": "failed"},
        latest_negotiation_round={"recommended_action": "revise_current_sprint"},
        revision_notes=["tighten scope"],
    )
    replan = host.replan_sprint_live(
        product_spec={"title": "Demo"},
        sprint_contract={"goal": "Ship"},
        latest_evaluation={"status": "failed"},
        latest_revision={"must_fix": ["scope"]},
        latest_execution_attempt={"changed_target_hints": ["src/App.tsx"]},
        execution_focus="worked on app shell",
        note="retry budget exhausted",
    )
    generate = host.generate_app_live(
        product_spec={"title": "Demo"},
        sprint_contract={"goal": "Ship"},
        latest_revision={"must_fix": ["scope"]},
        latest_evaluation={"status": "failed"},
        latest_negotiation_round={"recommended_action": "revise_current_sprint"},
        execution_focus="touch app shell",
        execution_summary="worked on shell",
        changed_target_hints=["src/App.tsx"],
    )

    assert negotiate["recommended_action"] == "revise_current_sprint"
    assert revise["revision_summary"] == "Narrowed scope."
    assert replan["replan_note"] == "narrowed"
    assert generate["changed_target_hints"] == ["src/App.tsx"]
    assert [name for name, _, _ in calls] == [
        "Workbench live negotiator",
        "Workbench live revisor",
        "Workbench live replanner",
        "Workbench live generator",
    ]
    assert calls[0][2] == host.live_app_negotiator_timeout_seconds()
    assert calls[1][2] == host.live_app_revisor_timeout_seconds()
    assert calls[2][2] == host.live_app_planner_timeout_seconds()
    assert calls[3][2] == host.live_app_generator_timeout_seconds()
