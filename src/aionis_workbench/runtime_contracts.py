from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class RuntimeContractError(ValueError):
    def __init__(self, endpoint: str, detail: str) -> None:
        super().__init__(f"{endpoint} contract error: {detail}")
        self.endpoint = endpoint
        self.detail = detail


def _require_dict(value: Any, *, endpoint: str, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeContractError(endpoint, f"{field} must be an object")
    return value


def _require_string(value: Any, *, endpoint: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeContractError(endpoint, f"{field} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


@dataclass(frozen=True)
class KickoffRecommendationContract:
    selected_tool: str | None
    file_path: str | None
    next_action: str | None
    history_applied: bool | None
    source_kind: str | None


@dataclass(frozen=True)
class KickoffResponseContract:
    payload: dict[str, Any]
    recommendation: KickoffRecommendationContract


@dataclass(frozen=True)
class HandoffResponseContract:
    payload: dict[str, Any]
    handoff: dict[str, Any]


@dataclass(frozen=True)
class ReplayRunStartContract:
    payload: dict[str, Any]
    run_id: str
    status: str


@dataclass(frozen=True)
class ReplayStepBeforeContract:
    payload: dict[str, Any]
    step_id: str


@dataclass(frozen=True)
class ReplayRunEndContract:
    payload: dict[str, Any]
    run_id: str
    status: str


@dataclass(frozen=True)
class ReviewPackResponseContract:
    payload: dict[str, Any]
    pack: dict[str, Any]


@dataclass(frozen=True)
class PlanningContextResponseContract:
    payload: dict[str, Any]
    operator_projection: dict[str, Any] | None
    delegation_learning: dict[str, Any] | None


@dataclass(frozen=True)
class SessionCreateResponseContract:
    payload: dict[str, Any]
    session_id: str


def parse_kickoff_response(payload: Any) -> KickoffResponseContract:
    endpoint = "/v1/memory/kickoff/recommendation"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    kickoff_raw = _require_dict(root.get("kickoff_recommendation"), endpoint=endpoint, field="kickoff_recommendation")
    selected_tool = _optional_string(kickoff_raw.get("selected_tool"))
    next_action = _optional_string(kickoff_raw.get("next_action"))
    if selected_tool and not next_action:
        raise RuntimeContractError(endpoint, "kickoff_recommendation.next_action must be present when selected_tool is set")
    return KickoffResponseContract(
        payload=root,
        recommendation=KickoffRecommendationContract(
            selected_tool=selected_tool,
            file_path=_optional_string(kickoff_raw.get("file_path")),
            next_action=next_action,
            history_applied=kickoff_raw.get("history_applied") if isinstance(kickoff_raw.get("history_applied"), bool) else None,
            source_kind=_optional_string(kickoff_raw.get("source_kind")),
        ),
    )


def parse_handoff_recover_response(payload: Any) -> HandoffResponseContract:
    endpoint = "/v1/handoff/recover"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    handoff = _require_dict(root.get("handoff"), endpoint=endpoint, field="handoff")
    return HandoffResponseContract(payload=root, handoff=handoff)


def parse_handoff_store_response(payload: Any) -> HandoffResponseContract:
    endpoint = "/v1/handoff/store"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    handoff = _require_dict(root.get("handoff"), endpoint=endpoint, field="handoff")
    return HandoffResponseContract(payload=root, handoff=handoff)


def parse_replay_run_start_response(payload: Any) -> ReplayRunStartContract:
    endpoint = "/v1/memory/replay/run/start"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    run_id = _require_string(root.get("run_id"), endpoint=endpoint, field="run_id")
    status = _require_string(root.get("status"), endpoint=endpoint, field="status")
    return ReplayRunStartContract(payload=root, run_id=run_id, status=status)


def parse_replay_step_before_response(payload: Any) -> ReplayStepBeforeContract:
    endpoint = "/v1/memory/replay/step/before"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    step_id = _require_string(root.get("step_id"), endpoint=endpoint, field="step_id")
    return ReplayStepBeforeContract(payload=root, step_id=step_id)


def parse_replay_run_end_response(payload: Any) -> ReplayRunEndContract:
    endpoint = "/v1/memory/replay/run/end"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    run_id = _require_string(root.get("run_id"), endpoint=endpoint, field="run_id")
    status = _require_string(root.get("status"), endpoint=endpoint, field="status")
    return ReplayRunEndContract(payload=root, run_id=run_id, status=status)


def parse_continuity_review_pack_response(payload: Any) -> ReviewPackResponseContract:
    endpoint = "/v1/memory/continuity/review-pack"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    pack = _require_dict(root.get("continuity_review_pack"), endpoint=endpoint, field="continuity_review_pack")
    return ReviewPackResponseContract(payload=root, pack=pack)


def parse_evolution_review_pack_response(payload: Any) -> ReviewPackResponseContract:
    endpoint = "/v1/memory/evolution/review-pack"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    pack = _require_dict(root.get("evolution_review_pack"), endpoint=endpoint, field="evolution_review_pack")
    return ReviewPackResponseContract(payload=root, pack=pack)


def parse_planning_context_response(payload: Any) -> PlanningContextResponseContract:
    endpoint = "/v1/memory/planning/context"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    operator_projection_raw = root.get("operator_projection")
    operator_projection = None
    if operator_projection_raw is not None:
        operator_projection = _require_dict(operator_projection_raw, endpoint=endpoint, field="operator_projection")
    layered_context_raw = root.get("layered_context")
    layered_context = None
    if layered_context_raw is not None:
        layered_context = _require_dict(layered_context_raw, endpoint=endpoint, field="layered_context")
    delegation_learning = None
    if operator_projection and operator_projection.get("delegation_learning") is not None:
        delegation_learning = _require_dict(
            operator_projection.get("delegation_learning"),
            endpoint=endpoint,
            field="operator_projection.delegation_learning",
        )
    elif layered_context and layered_context.get("delegation_learning") is not None:
        delegation_learning = _require_dict(
            layered_context.get("delegation_learning"),
            endpoint=endpoint,
            field="layered_context.delegation_learning",
        )
        operator_projection = {
            "delegation_learning": delegation_learning,
        }
    return PlanningContextResponseContract(
        payload=root,
        operator_projection=operator_projection,
        delegation_learning=delegation_learning,
    )


def parse_session_create_response(payload: Any, *, fallback_session_id: str | None = None) -> SessionCreateResponseContract:
    endpoint = "/v1/memory/sessions"
    root = _require_dict(payload, endpoint=endpoint, field="response")
    session_id = _optional_string(root.get("session_id"))
    if session_id is None:
        nested_session = root.get("session")
        if nested_session is not None:
            nested_root = _require_dict(nested_session, endpoint=endpoint, field="session")
            session_id = _optional_string(nested_root.get("session_id"))
    if session_id is None:
        session_id = _optional_string(fallback_session_id)
    if session_id is None:
        raise RuntimeContractError(endpoint, "session_id must be present in response or fallback input")
    return SessionCreateResponseContract(payload=root, session_id=session_id)
