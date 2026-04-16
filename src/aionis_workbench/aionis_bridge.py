from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from .runtime_contracts import (
    parse_continuity_review_pack_response,
    parse_evolution_review_pack_response,
    parse_handoff_recover_response,
    parse_handoff_store_response,
    parse_kickoff_response,
    parse_planning_context_response,
    parse_replay_run_end_response,
    parse_replay_run_start_response,
    parse_replay_step_before_response,
    parse_session_create_response,
)
from .tracing import TraceStep


@dataclass(frozen=True)
class BridgeDefaults:
    tenant_id: str
    scope: str
    actor: str


def _task_session_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _build_task_session_transition(*, transition_kind: str, status: str, detail: str | None = None) -> dict[str, Any]:
    return {
        "summary_version": "host_bridge_task_session_transition_v1",
        "transition_kind": transition_kind,
        "status": status,
        "at": _task_session_now(),
        "detail": detail,
    }


def _build_task_session_transition_guards(status: str) -> list[dict[str, Any]]:
    guards = {
        "list_events": {"allowed": True, "reason": None},
        "inspect_context": {"allowed": True, "reason": None},
        "record_event": {
            "allowed": status in {"active", "resumed"},
            "reason": (
                "task session is paused; resume before recording more events"
                if status == "paused"
                else "task session is completed and is now read-only"
                if status == "completed"
                else None
            ),
        },
        "plan_start": {
            "allowed": status in {"active", "resumed"},
            "reason": (
                "task session is paused; resume before planning the next start"
                if status == "paused"
                else "task session is completed and cannot plan a new start"
                if status == "completed"
                else None
            ),
        },
        "pause": {
            "allowed": status in {"active", "resumed"},
            "reason": (
                "task session is already paused"
                if status == "paused"
                else "task session is completed and cannot pause again"
                if status == "completed"
                else None
            ),
        },
        "resume": {
            "allowed": status == "paused",
            "reason": (
                "task session is completed and cannot resume"
                if status == "completed"
                else "task session must be paused before it can resume"
            ),
        },
        "complete": {
            "allowed": status in {"active", "resumed"},
            "reason": (
                "task session is paused; resume before marking it complete"
                if status == "paused"
                else "task session is already completed"
                if status == "completed"
                else None
            ),
        },
    }
    ordered_actions = ["list_events", "inspect_context", "record_event", "plan_start", "pause", "resume", "complete"]
    return [
        {
            "summary_version": "host_bridge_task_session_transition_guard_v1",
            "action": action,
            "allowed": guards[action]["allowed"],
            "reason": guards[action]["reason"],
        }
        for action in ordered_actions
    ]


def _with_task_session_controls(state: dict[str, Any]) -> dict[str, Any]:
    guards = _build_task_session_transition_guards(str(state.get("status") or "active"))
    return {
        **state,
        "allowed_actions": [entry["action"] for entry in guards if entry["allowed"]],
        "transition_guards": guards,
    }


def _build_initial_task_session_state(*, task_id: str, session_id: str) -> dict[str, Any]:
    transition = _build_task_session_transition(
        transition_kind="session_opened",
        status="active",
        detail="host task session opened",
    )
    return _with_task_session_controls(
        {
            "summary_version": "host_bridge_task_session_state_v1",
            "task_id": task_id,
            "session_id": session_id,
            "status": "active",
            "transition_count": 1,
            "last_transition": transition,
            "transitions": [transition],
            "last_startup_mode": None,
            "last_handoff_anchor": None,
            "last_event_text": None,
        }
    )


def _advance_task_session_state(
    *,
    state: dict[str, Any],
    transition_kind: str,
    status: str,
    detail: str | None = None,
    startup_mode: str | None = None,
    handoff_anchor: str | None = None,
    event_text: str | None = None,
) -> dict[str, Any]:
    transition = _build_task_session_transition(
        transition_kind=transition_kind,
        status=status,
        detail=detail,
    )
    return _with_task_session_controls(
        {
            **state,
            "status": status,
            "transition_count": int(state.get("transition_count") or 0) + 1,
            "last_transition": transition,
            "transitions": [*(state.get("transitions") or []), transition],
            "last_startup_mode": startup_mode if startup_mode is not None else state.get("last_startup_mode"),
            "last_handoff_anchor": handoff_anchor if handoff_anchor is not None else state.get("last_handoff_anchor"),
            "last_event_text": event_text if event_text is not None else state.get("last_event_text"),
        }
    )


def _assert_task_session_action_allowed(*, state: dict[str, Any], action: str) -> None:
    guards = state.get("transition_guards") or []
    guard = next((entry for entry in guards if entry.get("action") == action), None)
    if isinstance(guard, dict) and guard.get("allowed") is True:
        return
    reason = guard.get("reason") if isinstance(guard, dict) else "action is not allowed"
    raise RuntimeError(f"host bridge task session cannot {action.replace('_', ' ')}: {reason}")


class AionisWorkbenchTaskSession:
    def __init__(
        self,
        *,
        bridge: "AionisWorkbenchBridge",
        task_id: str,
        task_text: str,
        session_id: str,
        session: dict[str, Any],
    ) -> None:
        self._bridge = bridge
        self.task_id = task_id
        self.task_text = task_text
        self.session_id = session_id
        self.session = session
        self.state = _build_initial_task_session_state(task_id=task_id, session_id=session_id)

    def snapshot_state(self) -> dict[str, Any]:
        return deepcopy(self.state)

    def record_event(self, *, text: str | None = None, **payload: Any) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="record_event")
        event_text = text
        if not isinstance(event_text, str) or not event_text.strip():
            event_text = payload.get("event_text") or payload.get("input_text") or payload.get("text_summary")
        response = self._bridge.write_task_session_event(
            session_id=self.session_id,
            event_text=str(event_text).strip() if isinstance(event_text, str) and event_text.strip() else None,
            **payload,
        )
        self.state = _advance_task_session_state(
            state=self.state,
            transition_kind="event_recorded",
            status=str(self.state.get("status") or "active"),
            detail=str(event_text).strip() if isinstance(event_text, str) and event_text.strip() else None,
            event_text=str(event_text).strip() if isinstance(event_text, str) and event_text.strip() else None,
        )
        return response

    def list_events(self, **query: Any) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="list_events")
        return self._bridge.list_task_session_events(session_id=self.session_id, **query)

    def inspect_task_context(self, *, text: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="inspect_context")
        return self._bridge.inspect_task_context(
            task_id=self.task_id,
            text=text or self.task_text,
            context=context or {},
        )

    def plan_task_start(self, *, text: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="plan_start")
        plan = self._bridge.plan_task_start(
            task_id=self.task_id,
            text=text or self.task_text,
            context=context or {},
        )
        decision = plan.get("decision") if isinstance(plan.get("decision"), dict) else {}
        startup_mode = decision.get("startup_mode")
        self.state = _advance_task_session_state(
            state=self.state,
            transition_kind="startup_planned",
            status=str(self.state.get("status") or "active"),
            detail=startup_mode if isinstance(startup_mode, str) and startup_mode.strip() else None,
            startup_mode=startup_mode if isinstance(startup_mode, str) and startup_mode.strip() else None,
        )
        return plan

    def pause_task(self, **payload: Any) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="pause")
        pause = self._bridge.pause_task(task_id=self.task_id, **payload)
        handoff = pause.get("handoff") if isinstance(pause.get("handoff"), dict) else {}
        handoff_payload = handoff.get("handoff") if isinstance(handoff.get("handoff"), dict) else handoff
        anchor = handoff_payload.get("anchor") if isinstance(handoff_payload, dict) else None
        self.state = _advance_task_session_state(
            state=self.state,
            transition_kind="paused",
            status="paused",
            detail=payload.get("summary") if isinstance(payload.get("summary"), str) and payload.get("summary").strip() else None,
            handoff_anchor=anchor if isinstance(anchor, str) and anchor.strip() else self.task_id,
        )
        return pause

    def resume_task(self, *, repo_root: str, **payload: Any) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="resume")
        resume = self._bridge.resume_task(task_id=self.task_id, repo_root=repo_root, **payload)
        handoff = resume.get("handoff") if isinstance(resume.get("handoff"), dict) else {}
        handoff_payload = handoff.get("handoff") if isinstance(handoff.get("handoff"), dict) else handoff
        anchor = handoff_payload.get("anchor") if isinstance(handoff_payload, dict) else None
        self.state = _advance_task_session_state(
            state=self.state,
            transition_kind="resumed",
            status="resumed",
            detail="task resumed from handoff",
            handoff_anchor=anchor if isinstance(anchor, str) and anchor.strip() else self.task_id,
        )
        return resume

    def complete_task(self, **payload: Any) -> dict[str, Any]:
        _assert_task_session_action_allowed(state=self.state, action="complete")
        complete = self._bridge.complete_task(task_id=self.task_id, text=payload.pop("text", self.task_text), **payload)
        self.state = _advance_task_session_state(
            state=self.state,
            transition_kind="completed",
            status="completed",
            detail=payload.get("summary") if isinstance(payload.get("summary"), str) and payload.get("summary").strip() else self.task_text,
        )
        return complete


class AionisWorkbenchBridge:
    def __init__(self, base_url: str, defaults: BridgeDefaults) -> None:
        self._defaults = defaults
        self._client = httpx.Client(base_url=base_url, timeout=60.0, trust_env=False)

    def _replay_unsupported(self, *, task_id: str, reason: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "replay_run_id": "",
            "recorded": False,
            "replay_supported": False,
            "reason": reason,
        }

    def _runtime_unavailable(self, *, task_id: str, error: Exception) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "replay_run_id": "",
            "recorded": False,
            "replay_supported": False,
            "reason": "runtime_unavailable",
            "error": str(error),
        }

    def _with_defaults(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "tenant_id": payload.get("tenant_id", self._defaults.tenant_id),
            "scope": payload.get("scope", self._defaults.scope),
            "actor": payload.get("actor", self._defaults.actor),
            **payload,
        }

    def _kickoff_payload(self, *, text: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._with_defaults(
            {
                "query_text": text,
                "context": {"goal": text, **context},
                "candidates": ["read", "glob", "grep", "bash", "edit", "write", "ls", "task"],
            }
        )

    def _planning_payload(self, *, text: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._with_defaults(
            {
                "query_text": text,
                "context": {"goal": text, "operator_mode": "debug", **context},
                "tool_candidates": ["read", "glob", "grep", "bash", "edit", "write", "ls", "task"],
                "tool_strict": True,
                "include_shadow": False,
                "rules_limit": 50,
                "return_layered_context": True,
            }
        )

    def _build_startup_decision(
        self,
        *,
        started: dict[str, Any],
        task_context: dict[str, Any],
    ) -> dict[str, Any]:
        first_action = started.get("first_action")
        if not isinstance(first_action, dict):
            first_action = {}
        planning_context = task_context.get("planning_context")
        if not isinstance(planning_context, dict):
            planning_context = {}
        planning_summary = planning_context.get("planning_summary")
        if not isinstance(planning_summary, dict):
            planning_summary = {}
        delegation_learning = task_context.get("delegation_learning")
        if not isinstance(delegation_learning, dict):
            delegation_learning = {}
        learning_summary = delegation_learning.get("learning_summary")
        if not isinstance(learning_summary, dict):
            learning_summary = {}
        planner_explanation = planning_summary.get("planner_explanation")
        if not isinstance(planner_explanation, str) or not planner_explanation.strip():
            planner_explanation = None
        selected_tool = first_action.get("selected_tool")
        file_path = first_action.get("file_path")
        next_action = first_action.get("next_action")
        history_applied = first_action.get("history_applied") is True
        if isinstance(selected_tool, str) and selected_tool.strip():
            startup_mode = "learned_kickoff" if history_applied else "planner_fallback"
        else:
            startup_mode = "manual_triage"
        return {
            "startup_mode": startup_mode,
            "tool": selected_tool.strip() if isinstance(selected_tool, str) and selected_tool.strip() else None,
            "file_path": file_path.strip() if isinstance(file_path, str) and file_path.strip() else None,
            "instruction": next_action.strip() if isinstance(next_action, str) and next_action.strip() else None,
            "planner_explanation": planner_explanation,
            "task_family": learning_summary.get("task_family") if isinstance(learning_summary.get("task_family"), str) and learning_summary.get("task_family").strip() else None,
            "matched_records": int(learning_summary.get("matched_records") or 0),
            "recommendation_count": int(learning_summary.get("recommendation_count") or 0),
        }

    def start_task(self, *, task_id: str, text: str, context: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            "/v1/memory/kickoff/recommendation",
            json=self._kickoff_payload(text=text, context=context),
        )
        response.raise_for_status()
        parsed = parse_kickoff_response(response.json())
        data = parsed.payload
        kickoff = parsed.recommendation
        return {
            "task_id": task_id,
            "first_action": {
                "selected_tool": kickoff.selected_tool,
                "file_path": kickoff.file_path,
                "next_action": kickoff.next_action,
                "history_applied": kickoff.history_applied,
                "source_kind": kickoff.source_kind,
            } if kickoff.selected_tool else None,
            "task_start": data,
        }

    def create_task_session(
        self,
        *,
        task_id: str,
        text: str,
        session_id: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_session_id = (session_id or task_id).strip()
        response = self._client.post(
            "/v1/memory/sessions",
            json=self._with_defaults(
                {
                    "session_id": resolved_session_id,
                    "title": title or text,
                    "text_summary": summary or text,
                    "input_text": text,
                    "metadata": metadata or {},
                }
            ),
        )
        response.raise_for_status()
        parsed = parse_session_create_response(response.json(), fallback_session_id=resolved_session_id)
        return {
            "task_id": task_id,
            "session_id": parsed.session_id,
            "session": parsed.payload,
        }

    def write_task_session_event(
        self,
        *,
        session_id: str,
        event_text: str | None = None,
        title: str | None = None,
        text_summary: str | None = None,
        input_text: str | None = None,
        metadata: dict[str, Any] | None = None,
        execution_state_v1: dict[str, Any] | None = None,
        execution_packet_v1: dict[str, Any] | None = None,
        execution_transitions_v1: list[dict[str, Any]] | None = None,
        memory_lane: str | None = None,
        edge_weight: float | None = None,
        edge_confidence: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "metadata": metadata or {},
        }
        if isinstance(title, str) and title.strip():
            payload["title"] = title.strip()
        if isinstance(text_summary, str) and text_summary.strip():
            payload["text_summary"] = text_summary.strip()
        if isinstance(input_text, str) and input_text.strip():
            payload["input_text"] = input_text.strip()
        elif isinstance(event_text, str) and event_text.strip():
            payload["input_text"] = event_text.strip()
        if execution_state_v1 is not None:
            payload["execution_state_v1"] = execution_state_v1
        if execution_packet_v1 is not None:
            payload["execution_packet_v1"] = execution_packet_v1
        if execution_transitions_v1 is not None:
            payload["execution_transitions_v1"] = execution_transitions_v1
        if isinstance(memory_lane, str) and memory_lane.strip():
            payload["memory_lane"] = memory_lane.strip()
        if edge_weight is not None:
            payload["edge_weight"] = edge_weight
        if edge_confidence is not None:
            payload["edge_confidence"] = edge_confidence
        response = self._client.post("/v1/memory/events", json=self._with_defaults(payload))
        response.raise_for_status()
        return response.json()

    def list_task_session_events(self, *, session_id: str, **query: Any) -> dict[str, Any]:
        response = self._client.get(
            f"/v1/memory/sessions/{session_id}/events",
            params=self._with_defaults(
                {
                    "session_id": session_id,
                    **query,
                }
            ),
        )
        response.raise_for_status()
        return response.json()

    def open_task_session(
        self,
        *,
        task_id: str,
        text: str,
        session_id: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AionisWorkbenchTaskSession:
        created = self.create_task_session(
            task_id=task_id,
            text=text,
            session_id=session_id,
            title=title,
            summary=summary,
            metadata=metadata,
        )
        return AionisWorkbenchTaskSession(
            bridge=self,
            task_id=task_id,
            task_text=text,
            session_id=str(created["session_id"]),
            session=created["session"],
        )

    def inspect_task_context(self, *, task_id: str, text: str, context: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            "/v1/memory/planning/context",
            json=self._planning_payload(text=text, context=context),
        )
        response.raise_for_status()
        parsed = parse_planning_context_response(response.json())
        return {
            "task_id": task_id,
            "planning_context": parsed.payload,
            "operator_projection": parsed.operator_projection,
            "delegation_learning": parsed.delegation_learning,
        }

    def plan_task_start(self, *, task_id: str, text: str, context: dict[str, Any]) -> dict[str, Any]:
        task_context = self.inspect_task_context(task_id=task_id, text=text, context=context)
        started = self.start_task(task_id=task_id, text=text, context=context)
        return {
            "task_id": task_id,
            "decision": self._build_startup_decision(started=started, task_context=task_context),
            "first_action": started.get("first_action"),
            "task_start": started.get("task_start"),
            "task_context": task_context,
        }

    def resume_task(self, *, task_id: str, repo_root: str) -> dict[str, Any]:
        response = self._client.post(
            "/v1/handoff/recover",
            json=self._with_defaults(
                {
                    "anchor": task_id,
                    "handoff_kind": "task_handoff",
                    "include_payload": True,
                    "repo_root": repo_root,
                }
            ),
        )
        if response.status_code == 404:
            try:
                data = response.json()
            except Exception:
                data = {}
            if data.get("error") == "handoff_not_found":
                return {"task_id": task_id, "handoff": None, "missing_handoff": data}
        response.raise_for_status()
        parsed = parse_handoff_recover_response(response.json())
        return {"task_id": task_id, "handoff": parsed.payload, "missing_handoff": None}

    def continuity_review_pack(
        self,
        *,
        task_id: str,
        repo_root: str,
        file_path: str | None = None,
        handoff_kind: str = "task_handoff",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "anchor": task_id,
            "handoff_kind": handoff_kind,
            "repo_root": repo_root,
        }
        if isinstance(file_path, str) and file_path.strip():
            payload["file_path"] = file_path.strip()
        response = self._client.post(
            "/v1/memory/continuity/review-pack",
            json=self._with_defaults(payload),
        )
        response.raise_for_status()
        parsed = parse_continuity_review_pack_response(response.json())
        return {"task_id": task_id, "payload": parsed.payload, "pack": parsed.pack}

    def evolution_review_pack(
        self,
        *,
        task_id: str,
        text: str,
        repo_root: str,
        target_files: list[str],
    ) -> dict[str, Any]:
        response = self._client.post(
            "/v1/memory/evolution/review-pack",
            json=self._with_defaults(
                {
                    "query_text": text,
                    "context": {
                        "task": {"id": task_id, "brief": text},
                        "repo_root": repo_root,
                        "target_files": target_files,
                    },
                    "candidates": ["edit", "bash", "test", "read"],
                }
            ),
        )
        response.raise_for_status()
        parsed = parse_evolution_review_pack_response(response.json())
        return {"task_id": task_id, "payload": parsed.payload, "pack": parsed.pack}

    def pause_task(
        self,
        *,
        task_id: str,
        summary: str,
        handoff_text: str,
        repo_root: str,
        target_files: list[str],
        next_action: str,
        execution_result_summary: dict[str, Any],
        execution_evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = self._with_defaults(
            {
                "anchor": task_id,
                "handoff_kind": "task_handoff",
                "summary": summary,
                "handoff_text": handoff_text,
                "memory_lane": "shared",
                "repo_root": repo_root,
                "target_files": target_files,
                "next_action": next_action,
                "acceptance_checks": [],
                "execution_result_summary": execution_result_summary,
                "execution_evidence": execution_evidence,
            }
        )
        response = self._client.post("/v1/handoff/store", json=payload)
        response.raise_for_status()
        parsed = parse_handoff_store_response(response.json())
        return {"task_id": task_id, "handoff": parsed.payload}

    def complete_task(
        self,
        *,
        task_id: str,
        text: str,
        summary: str,
        output: str,
        tool_steps: list[TraceStep],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        try:
            run_start = self._client.post(
                "/v1/memory/replay/run/start",
                json=self._with_defaults(
                    {
                        "run_id": run_id,
                        "memory_lane": "shared",
                        "goal": text,
                        "metadata": metadata,
                    }
                ),
            )
        except httpx.HTTPError as exc:
            return self._runtime_unavailable(task_id=task_id, error=exc)
        if run_start.status_code == 404:
            return self._replay_unsupported(task_id=task_id, reason="replay_routes_unavailable")
        run_start.raise_for_status()
        parsed_run_start = parse_replay_run_start_response(run_start.json())
        for step in tool_steps:
            before = self._client.post(
                "/v1/memory/replay/step/before",
                json=self._with_defaults(
                    {
                        "run_id": run_id,
                        "step_index": step.step_index,
                        "tool_name": step.tool_name,
                        "tool_input": {"tool_call_id": step.tool_call_id, "args": step.tool_input},
                        "memory_lane": "private",
                    }
                ),
            )
            before.raise_for_status()
            step_id = parse_replay_step_before_response(before.json()).step_id
            after = self._client.post(
                "/v1/memory/replay/step/after",
                json=self._with_defaults(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "step_index": step.step_index,
                        "status": step.status,
                        "output_signature": step.output_signature,
                        "metadata": {
                            **metadata,
                            "tool_call_id": step.tool_call_id,
                            **({"error": step.error} if step.error else {}),
                        },
                        "memory_lane": "private",
                    }
                ),
            )
            after.raise_for_status()
        run_end = self._client.post(
            "/v1/memory/replay/run/end",
            json=self._with_defaults(
                {
                    "run_id": run_id,
                    "status": "success" if all(step.status == "success" for step in tool_steps) else "partial",
                    "summary": summary,
                    "metadata": metadata,
                    "memory_lane": "private",
                }
            ),
        )
        run_end.raise_for_status()
        parsed_run_end = parse_replay_run_end_response(run_end.json())
        return {
            "task_id": task_id,
            "replay_run_id": run_id,
            "run_start": parsed_run_start.payload,
            "run_end": parsed_run_end.payload,
        }

    def record_task(
        self,
        *,
        task_id: str,
        text: str,
        summary: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        try:
            run_start = self._client.post(
                "/v1/memory/replay/run/start",
                json=self._with_defaults(
                    {
                        "run_id": run_id,
                        "memory_lane": "shared",
                        "goal": text,
                        "metadata": metadata,
                    }
                ),
            )
        except httpx.HTTPError as exc:
            return self._runtime_unavailable(task_id=task_id, error=exc)
        if run_start.status_code == 404:
            return self._replay_unsupported(task_id=task_id, reason="replay_routes_unavailable")
        run_start.raise_for_status()
        parsed_run_start = parse_replay_run_start_response(run_start.json())
        run_end = self._client.post(
            "/v1/memory/replay/run/end",
            json=self._with_defaults(
                {
                    "run_id": run_id,
                    "status": "success",
                    "summary": summary,
                    "metadata": metadata,
                    "memory_lane": "private",
                }
            ),
        )
        run_end.raise_for_status()
        parsed_run_end = parse_replay_run_end_response(run_end.json())
        return {
            "task_id": task_id,
            "replay_run_id": run_id,
            "run_start": parsed_run_start.payload,
            "run_end": parsed_run_end.payload,
            "recorded": True,
        }
