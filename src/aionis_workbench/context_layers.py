from __future__ import annotations

from dataclasses import dataclass, field

from .session import SessionState, forgetting_state_map

CONTEXT_LAYER_ORDER = [
    "facts",
    "episodes",
    "rules",
    "static",
    "decisions",
    "tools",
    "citations",
]


@dataclass
class ContextForgettingPolicy:
    exclude_evicted: bool = True
    suppress_without_exact_task_match: bool = True


@dataclass
class ContextLayerBudget:
    char_budget_total: int = 5200
    char_budget_by_layer: dict[str, int] = field(
        default_factory=lambda: {
            "facts": 900,
            "episodes": 1100,
            "rules": 800,
            "static": 600,
            "decisions": 800,
            "tools": 500,
            "citations": 500,
        }
    )
    max_items_by_layer: dict[str, int] = field(
        default_factory=lambda: {
            "facts": 10,
            "episodes": 10,
            "rules": 8,
            "static": 6,
            "decisions": 8,
            "tools": 6,
            "citations": 8,
        }
    )
    forgetting_policy: ContextForgettingPolicy = field(default_factory=ContextForgettingPolicy)


def _dedupe_preserve(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if isinstance(item, str) and item.strip()))


def _fit_layer_items(items: list[str], *, item_limit: int, char_budget: int) -> list[str]:
    selected: list[str] = []
    consumed = 0
    for item in _dedupe_preserve(items):
        if len(selected) >= item_limit:
            break
        next_cost = len(item) + (1 if selected else 0)
        if selected and consumed + next_cost > char_budget:
            break
        if not selected and len(item) > char_budget:
            selected.append(item[: max(0, char_budget - 3)].rstrip() + "...")
            break
        selected.append(item)
        consumed += next_cost
    return selected


def assemble_context_layers(
    session: SessionState,
    *,
    budget: ContextLayerBudget | None = None,
) -> dict[str, list[str]]:
    config = budget or ContextLayerBudget()
    forgetting = forgetting_state_map(session)
    exact_task_match = (
        bool(session.strategy_summary)
        and session.strategy_summary.trust_signal == "exact_task_signature"
    )

    def allow(value: str) -> bool:
        entry = forgetting.get(value)
        if entry is None:
            return True
        if config.forgetting_policy.exclude_evicted and entry.state == "evicted":
            return False
        if (
            config.forgetting_policy.suppress_without_exact_task_match
            and entry.state == "suppressed"
            and not exact_task_match
        ):
            return False
        return True

    packet = session.execution_packet
    continuity = session.continuity_snapshot or {}
    layers: dict[str, list[str]] = {name: [] for name in CONTEXT_LAYER_ORDER}

    layers["facts"].extend(
        item for item in session.promoted_insights[:12] if allow(item)
    )
    if packet:
        layers["facts"].extend(packet.accepted_facts[:6])

    layers["episodes"].extend(
        f"[{item.role}] {item.status}: {item.summary}"
        for item in session.delegation_returns[:8]
    )
    layers["episodes"].extend(session.working_memory[:6])

    if packet:
        layers["rules"].extend(packet.hard_constraints[:6])
        layers["rules"].extend(packet.rollback_notes[:4])
    if any(item.kind == "timeout_artifact" for item in session.artifacts):
        layers["rules"].append(
            "timeout-aware recovery: reduce artifact load, stay on the narrowest working set, and validate with the first exact command"
        )
    kickoff = continuity.get("kickoff")
    if isinstance(kickoff, dict):
        tool = kickoff.get("tool")
        file_path = kickoff.get("file")
        next_action = kickoff.get("next_action")
        if isinstance(tool, str) and tool.strip():
            layers["rules"].append("Kickoff tool: " + tool.strip())
        if isinstance(file_path, str) and file_path.strip():
            layers["rules"].append("Kickoff file: " + file_path.strip())
        if isinstance(next_action, str) and next_action.strip():
            layers["rules"].append("Kickoff next action: " + next_action.strip())

    layers["static"].extend(
        [
            f"Project identity: {continuity.get('project_identity') or session.project_identity}" if (continuity.get("project_identity") or session.project_identity) else "",
            f"Project scope: {continuity.get('project_scope') or session.project_scope}" if (continuity.get("project_scope") or session.project_scope) else "",
            f"Task goal: {session.goal}" if session.goal else "",
        ]
    )
    if isinstance(continuity.get("recovered_handoff"), str) and continuity.get("recovered_handoff"):
        layers["static"].append("Recovered handoff: " + str(continuity["recovered_handoff"]))

    if session.execution_packet_summary:
        layers["decisions"].extend(
            [
                f"Stage: {session.execution_packet_summary.current_stage}",
                f"Active role: {session.execution_packet_summary.active_role}",
                f"Next action: {session.execution_packet_summary.next_action}" if session.execution_packet_summary.next_action else "",
            ]
        )
    if session.strategy_summary:
        layers["decisions"].extend(
            [
                f"Trust signal: {session.strategy_summary.trust_signal}",
                f"Strategy rationale: {session.strategy_summary.explanation}" if session.strategy_summary.explanation else "",
            ]
        )
    if session.workflow_signal_summary:
        layers["decisions"].extend(
            [
                f"Workflow mode: {session.workflow_signal_summary.workflow_mode}",
                f"Role sequence: {' -> '.join(session.workflow_signal_summary.role_sequence)}" if session.workflow_signal_summary.role_sequence else "",
            ]
        )

    if packet:
        layers["tools"].extend(packet.pending_validations[:4])
    else:
        layers["tools"].extend(session.validation_commands[:4])

    if packet:
        layers["citations"].extend(packet.artifact_refs[:6])
        layers["citations"].extend(packet.evidence_refs[:6])
    else:
        layers["citations"].extend(item.path for item in session.artifacts[:6])

    trimmed: dict[str, list[str]] = {}
    remaining_budget = config.char_budget_total
    for layer in CONTEXT_LAYER_ORDER:
        layer_budget = min(config.char_budget_by_layer.get(layer, remaining_budget), remaining_budget)
        trimmed[layer] = _fit_layer_items(
            layers[layer],
            item_limit=config.max_items_by_layer.get(layer, 8),
            char_budget=max(layer_budget, 120),
        )
        remaining_budget = max(0, remaining_budget - sum(len(item) for item in trimmed[layer]))
    return trimmed
