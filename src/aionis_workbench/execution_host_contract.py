from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

DEFAULT_EXECUTION_HOST_NAME = "deepagents_local_shell"
DEFAULT_EXECUTION_RUNTIME = "deepagents"
DEFAULT_EXECUTION_BACKEND = "LocalShellBackend"
DEFAULT_EXECUTION_HOST_RUNTIME = "deepagents"


@runtime_checkable
class ExecutionHostAdapter(Protocol):
    def describe(self) -> dict[str, Any]: ...

    def supports_live_tasks(self) -> bool: ...

    def live_app_planner_timeout_seconds(self) -> float: ...

    def live_app_planner_max_completion_tokens(self) -> int: ...

    def live_app_evaluator_timeout_seconds(self) -> float: ...

    def live_app_evaluator_max_completion_tokens(self) -> int: ...

    def live_app_negotiator_timeout_seconds(self) -> float: ...

    def live_app_negotiator_max_completion_tokens(self) -> int: ...

    def live_app_revisor_timeout_seconds(self) -> float: ...

    def live_app_revisor_max_completion_tokens(self) -> int: ...

    def live_app_generator_timeout_seconds(self) -> float: ...

    def live_app_delivery_timeout_seconds(self) -> float: ...

    def live_app_delivery_model_timeout_seconds(self) -> float: ...

    def live_app_generator_max_completion_tokens(self) -> int: ...

    def probe_live_model_auth(self) -> dict[str, Any]: ...

    def plan_app_live(self, *, prompt: str) -> dict[str, Any]: ...

    def evaluate_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        evaluator_criteria: list[dict[str, Any]],
        latest_execution_attempt: dict[str, Any] | None = None,
        execution_focus: str = "",
        summary: str = "",
        blocker_notes: list[str] | None = None,
        requested_status: str = "",
        criteria_scores: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def negotiate_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any] | None = None,
        planned_sprints: list[dict[str, Any]] | None = None,
        objections: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def revise_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any] | None = None,
        latest_negotiation_round: dict[str, Any] | None = None,
        revision_notes: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def replan_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any] | None = None,
        latest_revision: dict[str, Any] | None = None,
        latest_execution_attempt: dict[str, Any] | None = None,
        execution_focus: str = "",
        note: str = "",
    ) -> dict[str, Any]: ...

    def generate_app_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_revision: dict[str, Any] | None = None,
        latest_evaluation: dict[str, Any] | None = None,
        latest_negotiation_round: dict[str, Any] | None = None,
        execution_focus: str = "",
        execution_summary: str = "",
        changed_target_hints: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def build_agent(
        self,
        *,
        system_parts: list[str | None],
        memory_sources: list[str],
        timeout_pressure: bool,
        root_dir: str | None = None,
        model_timeout_seconds_override: float | None = None,
        use_builtin_subagents: bool = True,
    ) -> Any: ...

    def build_delivery_agent(
        self,
        *,
        system_parts: list[str | None],
        memory_sources: list[str],
        root_dir: str | None = None,
        model_timeout_seconds_override: float | None = None,
    ) -> Any: ...

    def invoke(self, agent: Any, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> Any: ...

    def invoke_delivery_task(
        self,
        *,
        system_parts: list[str],
        memory_sources: list[str],
        root_dir: str,
        task: str,
        timeout_seconds: float | None = None,
        trace_path: str = "",
    ) -> str: ...
