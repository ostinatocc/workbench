from __future__ import annotations

import json

import httpx
import pytest

from aionis_workbench.aionis_bridge import AionisWorkbenchBridge, BridgeDefaults
from aionis_workbench.runtime_contracts import RuntimeContractError


def _bridge_with_transport(handler) -> AionisWorkbenchBridge:
    bridge = AionisWorkbenchBridge(
        base_url="http://testserver",
        defaults=BridgeDefaults(
            tenant_id="tenant-test",
            scope="project:test/runtime-contracts",
            actor="aionis-workbench",
        ),
    )
    bridge._client.close()
    bridge._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
        timeout=60.0,
        trust_env=False,
    )
    return bridge


def test_start_task_accepts_valid_kickoff_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memory/kickoff/recommendation"
        return httpx.Response(
            200,
            json={
                "kickoff_recommendation": {
                    "selected_tool": "read",
                    "file_path": "src/demo.py",
                    "next_action": "Inspect src/demo.py before editing.",
                    "history_applied": True,
                    "source_kind": "pattern_match",
                }
            },
        )

    bridge = _bridge_with_transport(handler)

    result = bridge.start_task(task_id="task-1", text="Fix demo", context={"repo_root": "/tmp/demo"})

    assert result["task_id"] == "task-1"
    assert result["first_action"]["selected_tool"] == "read"
    assert result["first_action"]["file_path"] == "src/demo.py"
    assert result["first_action"]["next_action"] == "Inspect src/demo.py before editing."


def test_start_task_rejects_missing_kickoff_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memory/kickoff/recommendation"
        return httpx.Response(
            200,
            json={
                "kickoff_recommendation": {
                    "selected_tool": "read",
                    "file_path": "src/demo.py",
                }
            },
        )

    bridge = _bridge_with_transport(handler)

    with pytest.raises(RuntimeContractError, match="kickoff_recommendation.next_action"):
        bridge.start_task(task_id="task-1", text="Fix demo", context={"repo_root": "/tmp/demo"})


def test_inspect_task_context_accepts_operator_projection_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memory/planning/context"
        return httpx.Response(
            200,
            json={
                "planning_summary": {
                    "planner_explanation": "Use the learned export repair route.",
                },
                "operator_projection": {
                    "delegation_learning": {
                        "learning_summary": {
                            "task_family": "task:repair_export",
                            "matched_records": 2,
                            "truncated": False,
                            "route_role_counts": {"patch": 2},
                            "recommendation_count": 3,
                        },
                        "learning_recommendations": [],
                    }
                },
                "layered_context": {},
            },
        )

    bridge = _bridge_with_transport(handler)
    result = bridge.inspect_task_context(task_id="task-ctx-1", text="Fix demo", context={"repo_root": "/tmp/demo"})

    assert result["task_id"] == "task-ctx-1"
    assert result["planning_context"]["planning_summary"]["planner_explanation"] == "Use the learned export repair route."
    assert result["delegation_learning"]["learning_summary"]["task_family"] == "task:repair_export"


def test_plan_task_start_combines_context_inspect_and_kickoff() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/memory/planning/context":
            return httpx.Response(
                200,
                json={
                    "planning_summary": {
                        "planner_explanation": "Use the learned export repair route.",
                    },
                    "operator_projection": {
                        "delegation_learning": {
                            "learning_summary": {
                                "task_family": "task:repair_export",
                                "matched_records": 2,
                                "truncated": False,
                                "route_role_counts": {"patch": 2},
                                "recommendation_count": 3,
                            },
                            "learning_recommendations": [],
                        }
                    },
                    "layered_context": {},
                },
            )
        assert request.url.path == "/v1/memory/kickoff/recommendation"
        return httpx.Response(
            200,
            json={
                "kickoff_recommendation": {
                    "selected_tool": "edit",
                    "file_path": "src/demo.py",
                    "next_action": "Patch src/demo.py before rerunning tests.",
                    "history_applied": True,
                    "source_kind": "experience_intelligence",
                }
            },
        )

    bridge = _bridge_with_transport(handler)
    result = bridge.plan_task_start(task_id="task-plan-1", text="Fix demo", context={"repo_root": "/tmp/demo"})

    assert result["task_id"] == "task-plan-1"
    assert result["first_action"]["selected_tool"] == "edit"
    assert result["decision"]["startup_mode"] == "learned_kickoff"
    assert result["decision"]["planner_explanation"] == "Use the learned export repair route."
    assert result["decision"]["task_family"] == "task:repair_export"
    assert result["decision"]["matched_records"] == 2
    assert result["decision"]["recommendation_count"] == 3
    assert calls == [
        "/v1/memory/planning/context",
        "/v1/memory/kickoff/recommendation",
    ]


def test_open_task_session_binds_controller_lifecycle_into_python_adapter() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/v1/memory/sessions":
            return httpx.Response(200, json={"session_id": "session-1"})
        if request.url.path == "/v1/memory/events":
            return httpx.Response(200, json={"session_id": "session-1", "event_id": "event-1"})
        if request.url.path == "/v1/memory/sessions/session-1/events":
            return httpx.Response(
                200,
                json={
                    "session": {"session_id": "session-1"},
                    "events": [{"text_summary": "observed serializer failure"}],
                    "page": {"returned": 1},
                },
            )
        if request.url.path == "/v1/memory/planning/context":
            return httpx.Response(
                200,
                json={
                    "planning_summary": {
                        "planner_explanation": "Use the learned export repair route.",
                    },
                    "operator_projection": {
                        "delegation_learning": {
                            "learning_summary": {
                                "task_family": "task:repair_export",
                                "matched_records": 2,
                                "truncated": False,
                                "route_role_counts": {"patch": 2},
                                "recommendation_count": 3,
                            },
                            "learning_recommendations": [],
                        }
                    },
                    "layered_context": {},
                },
            )
        if request.url.path == "/v1/memory/kickoff/recommendation":
            return httpx.Response(
                200,
                json={
                    "kickoff_recommendation": {
                        "selected_tool": "edit",
                        "file_path": "src/demo.py",
                        "next_action": "Patch src/demo.py before rerunning tests.",
                        "history_applied": True,
                        "source_kind": "experience_intelligence",
                    }
                },
            )
        if request.url.path == "/v1/handoff/store":
            return httpx.Response(200, json={"handoff": {"anchor": "task-session-1"}})
        if request.url.path == "/v1/handoff/recover":
            return httpx.Response(200, json={"handoff": {"anchor": "task-session-1"}})
        if request.url.path == "/v1/memory/replay/run/start":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"run_id": payload["run_id"], "status": "started"})
        if request.url.path == "/v1/memory/replay/step/before":
            return httpx.Response(200, json={"step_id": "step-1"})
        if request.url.path == "/v1/memory/replay/step/after":
            return httpx.Response(200, json={"ok": True})
        assert request.url.path == "/v1/memory/replay/run/end"
        return httpx.Response(200, json={"run_id": "run-123", "status": "success"})

    bridge = _bridge_with_transport(handler)
    task_session = bridge.open_task_session(
        task_id="task-session-1",
        text="Fix demo",
        title="Fix demo session",
    )

    initial_state = task_session.snapshot_state()
    with pytest.raises(RuntimeError, match="must be paused before it can resume"):
        task_session.resume_task(repo_root="/tmp/demo")
    event = task_session.record_event(text="observed serializer failure")
    events = task_session.list_events(limit=5)
    plan = task_session.plan_task_start(context={"repo_root": "/tmp/demo"})
    pause = task_session.pause_task(
        summary="pause demo repair",
        handoff_text="resume demo repair",
        repo_root="/tmp/demo",
        target_files=["src/demo.py"],
        next_action="Patch src/demo.py",
        execution_result_summary={"validation_ok": False},
        execution_evidence=[{"kind": "validation_failure"}],
    )
    paused_state = task_session.snapshot_state()
    with pytest.raises(RuntimeError, match="paused; resume before planning the next start"):
        task_session.plan_task_start(context={"repo_root": "/tmp/demo"})
    resume = task_session.resume_task(repo_root="/tmp/demo")
    resumed_state = task_session.snapshot_state()
    complete = task_session.complete_task(
        summary="completed demo repair",
        output="patched export route",
        tool_steps=[],
        metadata={"repo_root": "/tmp/demo"},
    )
    completed_state = task_session.snapshot_state()
    with pytest.raises(RuntimeError, match="completed and is now read-only"):
        task_session.record_event(text="late event")

    assert task_session.session_id == "session-1"
    assert initial_state["status"] == "active"
    assert initial_state["allowed_actions"] == [
        "list_events",
        "inspect_context",
        "record_event",
        "plan_start",
        "pause",
        "complete",
    ]
    assert event["session_id"] == "session-1"
    assert events["events"][0]["text_summary"] == "observed serializer failure"
    assert plan["decision"]["startup_mode"] == "learned_kickoff"
    assert pause["handoff"]["handoff"]["anchor"] == "task-session-1"
    assert paused_state["allowed_actions"] == ["list_events", "inspect_context", "resume"]
    assert resume["handoff"]["handoff"]["anchor"] == "task-session-1"
    assert resumed_state["status"] == "resumed"
    assert isinstance(complete["replay_run_id"], str) and complete["replay_run_id"]
    assert completed_state["status"] == "completed"
    assert completed_state["allowed_actions"] == ["list_events", "inspect_context"]
    assert completed_state["last_startup_mode"] == "learned_kickoff"
    assert completed_state["last_handoff_anchor"] == "task-session-1"
    assert completed_state["last_event_text"] == "observed serializer failure"
    assert [entry["transition_kind"] for entry in completed_state["transitions"]] == [
        "session_opened",
        "event_recorded",
        "startup_planned",
        "paused",
        "resumed",
        "completed",
    ]


def test_resume_task_accepts_valid_handoff_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/handoff/recover"
        return httpx.Response(
            200,
            json={
                "handoff": {
                    "summary": "Resume task",
                    "handoff_text": "Continue from the latest fix attempt.",
                    "prompt_safe_handoff": {"summary": "Resume task"},
                    "execution_ready_handoff": {
                        "next_action": "Re-run pytest on the narrowed file set.",
                        "repo_root": "/tmp/demo",
                        "target_files": ["src/demo.py"],
                    },
                }
            },
        )

    bridge = _bridge_with_transport(handler)

    result = bridge.resume_task(task_id="task-2", repo_root="/tmp/demo")

    assert result["task_id"] == "task-2"
    assert result["missing_handoff"] is None
    assert result["handoff"]["handoff"]["summary"] == "Resume task"


def test_resume_task_returns_missing_handoff_for_runtime_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/handoff/recover"
        return httpx.Response(404, json={"error": "handoff_not_found", "anchor": "task-2"})

    bridge = _bridge_with_transport(handler)

    result = bridge.resume_task(task_id="task-2", repo_root="/tmp/demo")

    assert result["task_id"] == "task-2"
    assert result["handoff"] is None
    assert result["missing_handoff"]["error"] == "handoff_not_found"


def test_pause_task_accepts_valid_handoff_store_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/handoff/store"
        return httpx.Response(
            200,
            json={
                "handoff": {
                    "id": "handoff-1",
                    "anchor": "task-3",
                    "summary": "Paused after validation failure.",
                    "handoff_text": "Use the failing command before widening scope.",
                }
            },
        )

    bridge = _bridge_with_transport(handler)

    result = bridge.pause_task(
        task_id="task-3",
        summary="Paused after validation failure.",
        handoff_text="Use the failing command before widening scope.",
        repo_root="/tmp/demo",
        target_files=["src/demo.py"],
        next_action="Fix src/demo.py",
        execution_result_summary={"validation_ok": False},
        execution_evidence=[{"kind": "validation_failure"}],
    )

    assert result["task_id"] == "task-3"
    assert result["handoff"]["handoff"]["id"] == "handoff-1"


def test_continuity_review_pack_accepts_valid_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memory/continuity/review-pack"
        return httpx.Response(
            200,
            json={
                "continuity_review_pack": {
                    "pack_version": "continuity_review_pack_v1",
                    "review_contract": {
                        "acceptance_checks": ["pytest -q"],
                        "rollback_required": True,
                    },
                    "latest_handoff": {"anchor": "resume:src/demo.py"},
                }
            },
        )

    bridge = _bridge_with_transport(handler)
    result = bridge.continuity_review_pack(task_id="task-5", repo_root="/tmp/demo", file_path="src/demo.py")

    assert result["task_id"] == "task-5"
    assert result["pack"]["pack_version"] == "continuity_review_pack_v1"


def test_evolution_review_pack_accepts_valid_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memory/evolution/review-pack"
        return httpx.Response(
            200,
            json={
                "evolution_review_pack": {
                    "pack_version": "evolution_review_pack_v1",
                    "review_contract": {
                        "selected_tool": "edit",
                        "file_path": "src/demo.py",
                    },
                }
            },
        )

    bridge = _bridge_with_transport(handler)
    result = bridge.evolution_review_pack(
        task_id="task-6",
        text="Fix demo",
        repo_root="/tmp/demo",
        target_files=["src/demo.py"],
    )

    assert result["task_id"] == "task-6"
    assert result["pack"]["pack_version"] == "evolution_review_pack_v1"


def test_record_task_accepts_valid_replay_payload() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/memory/replay/run/start":
            return httpx.Response(
                200,
                json={
                    "run_id": "run-123",
                    "status": "started",
                    "commit_id": "commit-start",
                },
            )
        if request.url.path == "/v1/memory/replay/run/end":
            return httpx.Response(
                200,
                json={
                    "run_id": "run-123",
                    "status": "success",
                    "commit_id": "commit-end",
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    bridge = _bridge_with_transport(handler)

    result = bridge.record_task(
        task_id="task-4",
        text="Record task",
        summary="Validated externally.",
        metadata={"host": "aionis-workbench"},
    )

    assert calls == ["/v1/memory/replay/run/start", "/v1/memory/replay/run/end"]
    assert result["task_id"] == "task-4"
    assert result["recorded"] is True
    assert result["run_start"]["run_id"] == "run-123"
    assert result["run_end"]["status"] == "success"
