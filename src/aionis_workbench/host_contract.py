from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import AionisConfig, WorkbenchConfig


@dataclass(frozen=True)
class ProductShellHost:
    name: str
    entrypoint: str
    mode: str
    health_status: str
    default_workflow: list[str]
    task_navigation: list[str]
    inspection_commands: list[str]


@dataclass(frozen=True)
class LearningEngineHost:
    name: str
    health_status: str
    cold_start_bootstrap: bool
    auto_learning: bool
    passive_observation: bool
    consolidation: bool
    family_prior_strengthening: bool
    seed_influence_mode: str
    canonical_surfaces: list[str]


@dataclass(frozen=True)
class ExecutionHost:
    name: str
    execution_runtime: str
    backend: str
    model_provider: str
    model_available: bool
    supports_live_tasks: bool
    mode: str
    health_status: str
    health_reason: str | None
    degraded_reason: str | None


@dataclass(frozen=True)
class RuntimeHost:
    name: str
    base_url: str
    tenant_id: str
    scope: str
    actor: str
    bridge_configured: bool
    replay_mode: str
    health_status: str
    health_reason: str | None
    degraded_reason: str | None


@dataclass(frozen=True)
class UnifiedHostContract:
    product_shell: ProductShellHost
    learning_engine: LearningEngineHost
    execution_host: ExecutionHost
    runtime_host: RuntimeHost

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_unified_host_contract(
    *,
    workbench_config: WorkbenchConfig,
    aionis_config: AionisConfig,
    execution_host_description: dict[str, object] | None = None,
    runtime_host_description: dict[str, object] | None = None,
) -> UnifiedHostContract:
    execution_host_description = execution_host_description or {}
    runtime_host_description = runtime_host_description or {}
    return UnifiedHostContract(
        product_shell=ProductShellHost(
            name="aionis_cli",
            entrypoint="aionis",
            mode="shell_first",
            health_status="available",
            default_workflow=["/plan", "/work", "/review", "/next", "/fix"],
            task_navigation=["/tasks", "/latest", "/pick", "/use", "/clear"],
            inspection_commands=["/show", "/family", "/dashboard", "/background", "/hosts"],
        ),
        learning_engine=LearningEngineHost(
            name="workbench_engine",
            health_status="available",
            cold_start_bootstrap=True,
            auto_learning=True,
            passive_observation=True,
            consolidation=True,
            family_prior_strengthening=True,
            seed_influence_mode="fallback_and_boost",
            canonical_surfaces=[
                "execution_packet",
                "planner_packet",
                "strategy_summary",
                "workflow_signal_summary",
                "routing_signal_summary",
                "maintenance_summary",
                "continuity_snapshot",
                "context_layers_snapshot",
            ],
        ),
        execution_host=ExecutionHost(
            name=str(execution_host_description.get("name") or "deepagents_local_shell"),
            execution_runtime=str(execution_host_description.get("execution_runtime") or "deepagents"),
            backend=str(execution_host_description.get("backend") or "LocalShellBackend"),
            model_provider=str(execution_host_description.get("model_provider") or workbench_config.provider),
            model_available=bool(execution_host_description.get("model_available", bool(workbench_config.api_key))),
            supports_live_tasks=bool(
                execution_host_description.get(
                    "supports_live_tasks",
                    workbench_config.provider in {"openrouter", "openai"},
                )
            ),
            mode=str(execution_host_description.get("mode") or "inspect_only"),
            health_status=str(execution_host_description.get("health_status") or "offline"),
            health_reason=(
                str(execution_host_description["health_reason"])
                if execution_host_description.get("health_reason") is not None
                else None
            ),
            degraded_reason=(
                str(execution_host_description["degraded_reason"])
                if execution_host_description.get("degraded_reason") is not None
                else None
            ),
        ),
        runtime_host=RuntimeHost(
            name=str(runtime_host_description.get("name") or "aionis_runtime_host"),
            base_url=str(runtime_host_description.get("base_url") or aionis_config.base_url),
            tenant_id=str(runtime_host_description.get("tenant_id") or aionis_config.tenant_id),
            scope=str(runtime_host_description.get("scope") or aionis_config.scope),
            actor=str(runtime_host_description.get("actor") or aionis_config.actor),
            bridge_configured=bool(runtime_host_description.get("bridge_configured", True)),
            replay_mode=str(runtime_host_description.get("replay_mode") or "configured"),
            health_status=str(runtime_host_description.get("health_status") or "degraded"),
            health_reason=(
                str(runtime_host_description["health_reason"])
                if runtime_host_description.get("health_reason") is not None
                else None
            ),
            degraded_reason=(
                str(runtime_host_description["degraded_reason"])
                if runtime_host_description.get("degraded_reason") is not None
                else None
            ),
        ),
    )
