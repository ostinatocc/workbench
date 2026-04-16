from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StatusLineInput:
    project_identity: str
    project_scope: str
    task_id: str | None
    task_family: str | None
    strategy_profile: str | None
    validation_style: str | None
    instrumentation_status: str | None
    family_trend: str | None
    consolidation_status: str | None
    host_summary: str | None
    controller_status: str | None
    controller_allowed_actions: list[str]
    controller_blocked_actions: list[str]
    controller_transition: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _family_trend_for(task_family: str | None, dashboard_payload: dict[str, Any] | None) -> str | None:
    if not task_family or not isinstance(dashboard_payload, dict):
        return None
    for row in dashboard_payload.get("family_rows", []):
        if row.get("task_family") == task_family:
            return row.get("trend_status")
    return None


def _controller_summary_for(canonical_views: dict[str, Any] | None) -> tuple[str | None, list[str], list[str], str | None]:
    controller = ((canonical_views or {}).get("controller") or {}) if isinstance(canonical_views, dict) else {}
    if not isinstance(controller, dict):
        return (None, [], [], None)
    allowed_actions = [
        item.strip()
        for item in (controller.get("allowed_actions") or [])
        if isinstance(item, str) and item.strip()
    ]
    blocked_actions = [
        item.strip()
        for item in (controller.get("blocked_actions") or [])
        if isinstance(item, str) and item.strip()
    ]
    status = str(controller.get("status") or "").strip() or None
    transition = str(controller.get("last_transition_kind") or "").strip() or None
    return (status, allowed_actions[:4], blocked_actions[:3], transition)


def build_statusline_input(
    *,
    project_identity: str,
    project_scope: str,
    task_id: str | None,
    canonical_views: dict[str, Any] | None,
    dashboard_payload: dict[str, Any] | None = None,
    background_payload: dict[str, Any] | None = None,
    host_payload: dict[str, Any] | None = None,
) -> StatusLineInput:
    canonical_views = canonical_views or {}
    strategy = canonical_views.get("strategy", {}) or {}
    instrumentation = canonical_views.get("instrumentation", {}) or {}
    task_family = strategy.get("task_family") or instrumentation.get("task_family")
    contract = (host_payload or {}).get("contract") or {}
    product_shell = contract.get("product_shell", {}) or {}
    learning_engine = contract.get("learning_engine", {}) or {}
    execution_host = contract.get("execution_host", {}) or {}
    host_parts = [
        product_shell.get("name"),
        learning_engine.get("name"),
        execution_host.get("name"),
    ]
    controller_status, controller_allowed_actions, controller_blocked_actions, controller_transition = _controller_summary_for(
        canonical_views
    )
    return StatusLineInput(
        project_identity=project_identity,
        project_scope=project_scope,
        task_id=task_id,
        task_family=task_family,
        strategy_profile=strategy.get("strategy_profile"),
        validation_style=strategy.get("validation_style"),
        instrumentation_status=instrumentation.get("status"),
        family_trend=_family_trend_for(task_family, dashboard_payload),
        consolidation_status=(background_payload or {}).get("status_line"),
        host_summary="/".join(str(part) for part in host_parts if part) or None,
        controller_status=controller_status,
        controller_allowed_actions=controller_allowed_actions,
        controller_blocked_actions=controller_blocked_actions,
        controller_transition=controller_transition,
    )


def render_statusline(status: StatusLineInput) -> str:
    controller_segment = None
    if status.controller_status:
        allowed = ",".join(status.controller_allowed_actions[:3]) or "none"
        controller_segment = f"controller:{status.controller_status}[{allowed}]"
    parts = [
        status.project_scope,
        f"task:{status.task_id}" if status.task_id else None,
        status.task_family,
        status.strategy_profile,
        status.validation_style,
        status.instrumentation_status,
        controller_segment,
        (
            "blocked:" + ",".join(status.controller_blocked_actions[:2])
            if status.controller_blocked_actions
            else None
        ),
        f"transition:{status.controller_transition}" if status.controller_transition else None,
        f"trend:{status.family_trend}" if status.family_trend else None,
        f"consolidate:{status.consolidation_status}" if status.consolidation_status else None,
        f"hosts:{status.host_summary}" if status.host_summary else None,
    ]
    return " | ".join(part for part in parts if part)
