from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
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
    config = replace(_base_config(tmp_path), provider="offline", api_key="test-key", base_url=None)
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
        use_builtin_subagents=False,
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


def test_openai_agents_execution_host_invoke_runs_builtin_specialists_and_returns_structured_payload(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    (tmp_path / "README.md").write_text("seed file\n", encoding="utf-8")

    captures: list[dict[str, object]] = []

    class _FakeAgent:
        def __init__(self, *, name, instructions, model, tools) -> None:
            self.name = name
            self.instructions = instructions
            self.model = model
            self.tools = tools

    class _FakeRunner:
        @staticmethod
        def run_sync(agent, user_input):
            captures.append(
                {
                    "name": str(agent.name),
                    "instructions": str(agent.instructions),
                    "user_input": str(user_input),
                    "tools": sorted(tool.__name__ for tool in agent.tools),
                }
            )
            if "investigator" in str(agent.name).lower():
                return SimpleNamespace(final_output="Localized the failure in src/demo.py\nRoot cause: export mismatch")
            if "implementer" in str(agent.name).lower():
                tools = {tool.__name__: tool for tool in agent.tools}
                tools["write_file"]("src/demo.py", "implemented\n")
                return SimpleNamespace(final_output="Applied the narrow fix in src/demo.py\nTouched files: src/demo.py")
            return SimpleNamespace(final_output="Validation passed.\nCommand: python3 -m pytest -q")

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
        use_builtin_subagents=True,
    )
    output = host.invoke(
        prepared,
        {
            "messages": [{"role": "user", "content": "Repair the export path."}],
            "delegation_packets": [
                {
                    "role": "investigator",
                    "mission": "Localize the failure.",
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -m pytest -q"],
                    "output_contract": "Return diagnosis and scope.",
                },
                {
                    "role": "implementer",
                    "mission": "Apply the narrow fix.",
                    "working_set": ["src", "README.md"],
                    "acceptance_checks": ["python3 -m pytest -q"],
                    "output_contract": "Return touched files.",
                    "preferred_artifact_refs": [".aionis-workbench/artifacts/investigator.json"],
                    "inherited_evidence": ["Investigator summary: export mismatch in src/demo.py"],
                    "routing_reason": "Implementer inherits the narrow diagnosis before editing.",
                },
                {
                    "role": "verifier",
                    "mission": "Validate the fix.",
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -m pytest -q"],
                    "output_contract": "Return validation result.",
                },
            ],
        },
    )

    assert isinstance(output, dict)
    assert output["role_sequence"] == ["investigator", "implementer", "verifier"]
    assert [item["role"] for item in output["delegation_returns"]] == ["investigator", "implementer", "verifier"]
    assert output["delegation_returns"][0]["working_set"] == ["src/demo.py"]
    assert output["delegation_returns"][1]["working_set"] == ["src/demo.py"]
    assert output["delegation_returns"][2]["acceptance_checks"] == ["python3 -m pytest -q"]
    assert output["delegation_returns"][0]["handoff_target"] == "implementer"
    assert output["delegation_returns"][1]["handoff_target"] == "verifier"
    assert output["delegation_returns"][2]["handoff_target"] == "orchestrator"
    assert output["delegation_returns"][1]["next_action"].startswith("Hand off to verifier")
    assert output["delegation_returns"][2]["validation_intent"] == ["python3 -m pytest -q"]
    assert output["delegation_returns"][0]["handoff_text"].startswith("investigator summary:")
    assert "Next role: implementer" in output["delegation_returns"][0]["handoff_text"]
    assert "Validation intent: python3 -m pytest -q" in output["delegation_returns"][2]["handoff_text"]
    assert output["delegation_returns"][1]["artifact_refs"] == [".aionis-workbench/artifacts/investigator.json"]
    assert "[investigator] Localized the failure in src/demo.py" in output["final_output"]
    assert (tmp_path / "src" / "demo.py").read_text(encoding="utf-8") == "implemented\n"
    assert len(captures) == 3
    assert "Previous specialist handoffs:" in captures[1]["instructions"]
    assert "Effective edit scope: src/demo.py" in captures[1]["instructions"]
    assert "Routed artifacts: .aionis-workbench/artifacts/investigator.json" in captures[1]["instructions"]
    assert "Routing reason: Implementer inherits the narrow diagnosis before editing." in captures[1]["instructions"]
    assert captures[0]["tools"] == ["exec_command", "list_files", "read_file"]
    assert captures[1]["tools"] == ["exec_command", "list_files", "read_file", "write_file"]
    assert captures[2]["tools"] == ["exec_command", "list_files", "read_file"]
    trace_steps = host._trace.export()
    assert [step.tool_name for step in trace_steps].count("workbench.model") == 3
    assert [step.tool_name for step in trace_steps].count("write_file") == 1


def test_openai_agents_execution_host_uses_dynamic_handoff_graph_for_verifier_retry(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    (tmp_path / "README.md").write_text("seed file\n", encoding="utf-8")

    captures: list[dict[str, object]] = []
    role_runs = {"investigator": 0, "implementer": 0, "verifier": 0}

    class _FakeAgent:
        def __init__(self, *, name, instructions, model, tools) -> None:
            self.name = name
            self.instructions = instructions
            self.model = model
            self.tools = tools

    class _FakeRunner:
        @staticmethod
        def run_sync(agent, user_input):
            role = str(agent.name).split()[-1].lower()
            role_runs[role] += 1
            captures.append(
                {
                    "name": str(agent.name),
                    "instructions": str(agent.instructions),
                    "user_input": str(user_input),
                    "tools": sorted(tool.__name__ for tool in agent.tools),
                }
            )
            tools = {tool.__name__: tool for tool in agent.tools}
            if role == "investigator":
                return SimpleNamespace(final_output="Localized the failure in src/demo.py\nRoot cause: export mismatch")
            if role == "implementer" and role_runs[role] == 1:
                tools["write_file"]("src/demo.py", "tentative\n")
                return SimpleNamespace(final_output="Applied a tentative fix in src/demo.py\nTouched files: src/demo.py")
            if role == "implementer":
                tools["write_file"]("src/demo.py", "final\n")
                return SimpleNamespace(final_output="Refined the fix in src/demo.py\nTouched files: src/demo.py")
            if role == "verifier" and role_runs[role] == 1:
                return SimpleNamespace(
                    final_output="Validation failed.\nCommand: python3 -m pytest -q\nBlocker: export path still mismatched"
                )
            return SimpleNamespace(final_output="Validation passed.\nCommand: python3 -m pytest -q")

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
        use_builtin_subagents=True,
    )
    output = host.invoke(
        prepared,
        {
            "messages": [{"role": "user", "content": "Repair the export path."}],
            "delegation_packets": [
                {
                    "role": "investigator",
                    "mission": "Localize the failure.",
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -m pytest -q"],
                    "output_contract": "Return diagnosis and scope.",
                },
                {
                    "role": "implementer",
                    "mission": "Apply the narrow fix.",
                    "working_set": ["src", "README.md"],
                    "acceptance_checks": ["python3 -m pytest -q"],
                    "output_contract": "Return touched files.",
                },
                {
                    "role": "verifier",
                    "mission": "Validate the fix.",
                    "working_set": ["src/demo.py"],
                    "acceptance_checks": ["python3 -m pytest -q"],
                    "output_contract": "Return validation result.",
                },
            ],
        },
    )

    assert output["role_sequence"] == ["investigator", "implementer", "verifier", "implementer", "verifier"]
    assert [item["role"] for item in output["delegation_returns"]] == [
        "investigator",
        "implementer",
        "verifier",
        "implementer",
        "verifier",
    ]
    assert output["delegation_returns"][2]["status"] == "error"
    assert output["delegation_returns"][2]["handoff_target"] == "implementer"
    assert output["delegation_returns"][2]["next_action"].startswith("Hand off to implementer")
    assert output["delegation_returns"][4]["handoff_target"] == "orchestrator"
    assert len(captures) == 5
    assert "Graph hop: 4" in captures[3]["instructions"]
    assert "verifier summary: Validation failed." in captures[3]["instructions"]
    trace_steps = host._trace.export()
    assert [step.tool_name for step in trace_steps].count("workbench.model") == 5
    assert [step.tool_name for step in trace_steps].count("write_file") == 2


def test_openai_agents_execution_host_blocks_mutating_commands_for_role_shells(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )

    def _fake_function_tool(fn):
        return fn

    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    monkeypatch.setattr(
        host,
        "_import_agents_runtime",
        lambda: (object, object, _fake_function_tool, lambda *args, **kwargs: None, lambda *args, **kwargs: None),
    )

    investigator_tools = {
        tool.__name__: tool
        for tool in host._build_function_tools(
            root_dir=str(tmp_path),
            recorder=host._trace,
            delivery_mode=False,
            allowed_tool_names={"exec_command"},
            role_name="investigator",
            working_set=["src/demo.py"],
        )
    }
    verifier_tools = {
        tool.__name__: tool
        for tool in host._build_function_tools(
            root_dir=str(tmp_path),
            recorder=host._trace,
            delivery_mode=False,
            allowed_tool_names={"exec_command"},
            role_name="verifier",
            working_set=["src/demo.py"],
        )
    }
    implementer_tools = {
        tool.__name__: tool
        for tool in host._build_function_tools(
            root_dir=str(tmp_path),
            recorder=host._trace,
            delivery_mode=False,
            allowed_tool_names={"exec_command"},
            role_name="implementer",
            working_set=["src/demo.py"],
        )
    }

    with pytest.raises(ValueError, match="investigator may only run read-only commands"):
        investigator_tools["exec_command"]("touch blocked.txt")
    with pytest.raises(ValueError, match="verifier may only run read-only commands"):
        verifier_tools["exec_command"]("git apply patch.diff")
    with pytest.raises(ValueError, match="implementer may only mutate files via write_file"):
        implementer_tools["exec_command"]("touch src/demo.py")


def test_openai_agents_execution_host_implementer_writes_only_inside_working_set(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )

    def _fake_function_tool(fn):
        return fn

    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    monkeypatch.setattr(
        host,
        "_import_agents_runtime",
        lambda: (object, object, _fake_function_tool, lambda *args, **kwargs: None, lambda *args, **kwargs: None),
    )

    tools = {
        tool.__name__: tool
        for tool in host._build_function_tools(
            root_dir=str(tmp_path),
            recorder=host._trace,
            delivery_mode=False,
            allowed_tool_names={"write_file"},
            role_name="implementer",
            working_set=["src/demo.py", "tests/"],
        )
    }

    tools["write_file"]("src/demo.py", "ok\n")
    tools["write_file"]("tests/output.txt", "ok\n")
    assert (tmp_path / "src" / "demo.py").read_text(encoding="utf-8") == "ok\n"
    assert (tmp_path / "tests" / "output.txt").read_text(encoding="utf-8") == "ok\n"

    with pytest.raises(ValueError, match="implementer may only write inside the delegated working set"):
        tools["write_file"]("README.md", "blocked\n")


def test_openai_agents_execution_host_implementer_reads_only_working_set_and_artifact_scope(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("demo\n", encoding="utf-8")
    (tmp_path / ".aionis-workbench" / "artifacts").mkdir(parents=True)
    (tmp_path / ".aionis-workbench" / "artifacts" / "investigator.json").write_text(
        "{\"summary\":\"artifact\"}\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("blocked\n", encoding="utf-8")

    def _fake_function_tool(fn):
        return fn

    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    monkeypatch.setattr(
        host,
        "_import_agents_runtime",
        lambda: (object, object, _fake_function_tool, lambda *args, **kwargs: None, lambda *args, **kwargs: None),
    )

    tools = {
        tool.__name__: tool
        for tool in host._build_function_tools(
            root_dir=str(tmp_path),
            recorder=host._trace,
            delivery_mode=False,
            allowed_tool_names={"read_file", "list_files"},
            role_name="implementer",
            working_set=["src/demo.py"],
            preferred_artifact_refs=[".aionis-workbench/artifacts/investigator.json"],
        )
    }

    assert tools["read_file"]("src/demo.py") == "demo\n"
    assert "\"artifact\"" in tools["read_file"](".aionis-workbench/artifacts/investigator.json")
    listed_src = json.loads(tools["list_files"]("src"))
    listed_artifacts = json.loads(tools["list_files"](".aionis-workbench/artifacts"))
    assert listed_src["items"] == ["src/demo.py"]
    assert listed_artifacts["items"] == [".aionis-workbench/artifacts/investigator.json"]

    with pytest.raises(ValueError, match="implementer may only read inside the delegated working set or routed artifact scope"):
        tools["read_file"]("README.md")
    with pytest.raises(ValueError, match="implementer may only inspect inside the delegated working set or routed artifact scope"):
        tools["list_files"](".")


def test_openai_agents_execution_host_narrows_implementer_effective_working_set_from_investigator_scope(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "aionis_workbench.openai_agents_execution_host._openai_agents_sdk_available",
        lambda: True,
    )
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())

    narrowed = host._effective_working_set_for_role(
        role="implementer",
        packet={"working_set": ["src", "README.md"]},
        prior_returns=[
            {
                "role": "investigator",
                "working_set": ["src/demo.py"],
            }
        ],
    )
    untouched = host._effective_working_set_for_role(
        role="implementer",
        packet={"working_set": ["src", "README.md"]},
        prior_returns=[
            {
                "role": "investigator",
                "working_set": ["docs/guide.md"],
            }
        ],
    )

    assert narrowed == ["src/demo.py"]
    assert untouched == ["src", "README.md"]


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
            root_dir = Path(args[3])
            trace_path = Path(args[7])
            (root_dir / "dist").mkdir(parents=True, exist_ok=True)
            (root_dir / "dist" / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            trace_path.write_text(
                json.dumps(
                    {
                        "step_count": 2,
                        "steps": [
                            {
                                "tool_name": "execute",
                                "status": "success",
                                "tool_input": {"command": "npm run build"},
                            },
                            {
                                "tool_name": "write_file",
                                "status": "success",
                                "tool_input": {"path": "src/App.tsx"},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result_queue = args[-1]
            payload = {
                "ok": True,
                "result": "Build completed and delivery artifact is ready.",
                "trace_path": str(trace_path),
            }
            return _FakeProcess(payload, result_queue)

    trace_path = tmp_path / ".aionis-delivery-trace.json"
    host = OpenAIAgentsExecutionHost(config=_base_config(tmp_path), trace=TraceRecorder())
    monkeypatch.setattr("aionis_workbench.openai_agents_execution_host.multiprocessing.get_context", lambda _mode: _FakeContext())

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
