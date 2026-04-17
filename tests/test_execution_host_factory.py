from __future__ import annotations

from dataclasses import replace

import pytest

from aionis_workbench.config import WorkbenchConfig
from aionis_workbench.execution_host_factory import build_execution_host
from aionis_workbench.tracing import TraceRecorder


def _base_config(tmp_path) -> WorkbenchConfig:
    return WorkbenchConfig(
        execution_host_runtime="openai_agents",
        model="gpt-5",
        system_prompt=None,
        provider="offline",
        api_key=None,
        base_url=None,
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


def test_build_execution_host_uses_openai_agents_by_default(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeHost:
        def __init__(self, *, config, trace) -> None:
            captured["config"] = config
            captured["trace"] = trace

    monkeypatch.setattr("aionis_workbench.execution_host_factory.OpenAIAgentsExecutionHost", _FakeHost)

    config = _base_config(tmp_path)
    trace = TraceRecorder()
    host = build_execution_host(config=config, trace=trace)

    assert isinstance(host, _FakeHost)
    assert captured["config"] is config
    assert captured["trace"] is trace


def test_build_execution_host_rejects_unknown_runtime(tmp_path) -> None:
    config = replace(_base_config(tmp_path), execution_host_runtime="unsupported_host")

    with pytest.raises(ValueError, match="Unsupported WORKBENCH_EXECUTION_HOST"):
        build_execution_host(config=config, trace=TraceRecorder())
