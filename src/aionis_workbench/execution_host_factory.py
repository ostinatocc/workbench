from __future__ import annotations

from .config import WorkbenchConfig
from .execution_host import DeepagentsExecutionHost
from .execution_host_contract import DEFAULT_EXECUTION_HOST_RUNTIME, ExecutionHostAdapter
from .openai_agents_execution_host import OpenAIAgentsExecutionHost
from .tracing import TraceRecorder


def build_execution_host(*, config: WorkbenchConfig, trace: TraceRecorder) -> ExecutionHostAdapter:
    runtime = (config.execution_host_runtime or DEFAULT_EXECUTION_HOST_RUNTIME).strip().lower()
    if runtime == DEFAULT_EXECUTION_HOST_RUNTIME:
        return DeepagentsExecutionHost(config=config, trace=trace)
    if runtime == "openai_agents":
        return OpenAIAgentsExecutionHost(config=config, trace=trace)
    raise ValueError(
        f"Unsupported WORKBENCH_EXECUTION_HOST={config.execution_host_runtime!r}. "
        f"Supported values: {DEFAULT_EXECUTION_HOST_RUNTIME!r}, 'openai_agents'."
    )
