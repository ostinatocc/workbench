from __future__ import annotations

from aionis_workbench.app_harness_models import (
    AppHarnessState,
    EvaluatorCriterion,
    ProductSpec,
    SprintContract,
    SprintExecutionAttempt,
    SprintEvaluation,
    SprintNegotiationRound,
    SprintRevision,
)


def test_evaluator_criterion_from_dict_accepts_stable_shape() -> None:
    criterion = EvaluatorCriterion.from_dict(
        {
            "name": "functionality",
            "description": "Core flows should work end-to-end.",
            "threshold": 0.8,
            "weight": 1.5,
        }
    )

    assert criterion is not None
    assert criterion.name == "functionality"
    assert criterion.threshold == 0.8
    assert criterion.weight == 1.5


def test_sprint_contract_from_dict_requires_id_and_goal() -> None:
    assert SprintContract.from_dict({"sprint_id": "s1"}) is None

    contract = SprintContract.from_dict(
        {
            "sprint_id": "sprint-1",
            "goal": "Ship the playable editor shell.",
            "scope": ["editor frame", "left rail", "test seed data"],
            "acceptance_checks": ["pytest tests/test_editor.py -q"],
            "done_definition": ["editor loads", "seed project renders"],
            "proposed_by": "planner",
            "approved": True,
        }
    )

    assert contract is not None
    assert contract.sprint_id == "sprint-1"
    assert contract.approved is True
    assert contract.scope == ["editor frame", "left rail", "test seed data"]


def test_product_spec_round_trips_nested_lists() -> None:
    spec = ProductSpec.from_dict(
        {
            "prompt": "Build a retro game maker.",
            "title": "Retro Game Maker",
            "app_type": "full_stack_app",
            "stack": ["React", "Vite", "FastAPI", "SQLite"],
            "features": ["sprite editor", "level editor", "test mode"],
            "design_direction": "retro toolchain with high information density",
            "sprint_ids": ["sprint-1", "sprint-2"],
        }
    )

    assert spec is not None
    assert ProductSpec.from_dict(spec.to_dict()) == spec


def test_app_harness_state_round_trips_nested_objects() -> None:
    state = AppHarnessState.from_dict(
        {
            "product_spec": {
                "prompt": "Build a retro game maker.",
                "title": "Retro Game Maker",
                "stack": ["React", "FastAPI"],
                "features": ["sprite editor"],
                "feature_groups": {"core_workflow": ["sprite editor"]},
                "feature_rationale": {"core_workflow": "This is the primary path."},
            },
            "evaluator_criteria": [
                {"name": "functionality", "threshold": 0.8},
                {"name": "design_quality", "threshold": 0.7},
            ],
            "active_sprint_contract": {
                "sprint_id": "sprint-1",
                "goal": "Ship the editor shell.",
                "acceptance_checks": ["pytest tests/test_editor.py -q"],
            },
            "planned_sprint_contracts": [
                {
                    "sprint_id": "sprint-2",
                    "goal": "Harden supporting workflows.",
                    "scope": ["persistence", "quality pass"],
                    "proposed_by": "planner",
                }
            ],
            "planning_rationale": ["Start by proving the editor shell."],
            "sprint_negotiation_notes": ["Do not approve sprint-2 until sprint-1 is stable."],
            "latest_negotiation_round": {
                "sprint_id": "sprint-1",
                "evaluator_mode": "contract_driven",
                "evaluator_status": "failed",
                "objections": ["Resolve failing criterion: functionality."],
                "planner_response": ["Keep sprint-1 narrow until the evaluator objections are cleared."],
                "recommended_action": "revise_current_sprint",
            },
            "negotiation_history": [
                {
                    "sprint_id": "sprint-1",
                    "evaluator_mode": "contract_driven",
                    "evaluator_status": "failed",
                    "objections": ["Resolve failing criterion: functionality."],
                    "planner_response": ["Keep sprint-1 narrow until the evaluator objections are cleared."],
                    "recommended_action": "revise_current_sprint",
                }
            ],
            "sprint_history": [
                {
                    "sprint_id": "sprint-0",
                    "goal": "Bootstrap the app shell.",
                }
            ],
            "latest_sprint_evaluation": {
                "sprint_id": "sprint-1",
                "status": "failed",
                "summary": "Editor loads but the canvas interaction is broken.",
                "evaluator_mode": "contract_driven",
                "criteria_scores": {"functionality": 0.55, "design_quality": 0.78},
                "passing_criteria": ["design_quality"],
                "failing_criteria": ["functionality"],
                "blocker_notes": ["canvas input does not update entity positions"],
            },
            "last_execution_gate_from": "needs_qa",
            "last_execution_gate_to": "qa_failed",
            "last_execution_gate_transition": "needs_qa->qa_failed",
            "last_policy_action": "qa:failed",
            "loop_status": "needs_revision",
        }
    )

    assert state is not None
    assert state.product_spec is not None
    assert state.active_sprint_contract is not None
    assert state.latest_sprint_evaluation is not None
    assert AppHarnessState.from_dict(state.to_dict()) == state


def test_app_harness_state_returns_none_for_empty_payload() -> None:
    assert AppHarnessState.from_dict({}) is None
    assert AppHarnessState.from_dict(None) is None


def test_sprint_negotiation_round_from_dict_requires_sprint_id() -> None:
    assert SprintNegotiationRound.from_dict({"recommended_action": "revise_current_sprint"}) is None
    round_summary = SprintNegotiationRound.from_dict(
        {
            "sprint_id": "sprint-1",
            "planner_mode": "live",
            "evaluator_mode": "contract_driven",
            "evaluator_status": "failed",
            "objections": ["Resolve failing criterion: functionality."],
            "planner_response": ["Keep sprint-1 narrow until the evaluator objections are cleared."],
            "recommended_action": "revise_current_sprint",
        }
    )
    assert round_summary is not None
    assert round_summary.sprint_id == "sprint-1"
    assert round_summary.planner_mode == "live"
    assert round_summary.recommended_action == "revise_current_sprint"


def test_sprint_revision_from_dict_requires_revision_and_sprint_ids() -> None:
    assert SprintRevision.from_dict({"revision_id": "sprint-1-revision-1"}) is None
    revision = SprintRevision.from_dict(
        {
            "revision_id": "sprint-1-revision-1",
            "sprint_id": "sprint-1",
            "planner_mode": "deterministic",
            "source_negotiation_action": "revise_current_sprint",
            "must_fix": ["Resolve failing criterion: functionality."],
            "must_keep": ["npm test"],
            "revision_summary": "Keep sprint-1 narrow around the failing functionality path.",
            "revision_diff_summary": ["Fix: Resolve failing criterion: functionality.."],
        }
    )
    assert revision is not None
    assert revision.revision_id == "sprint-1-revision-1"
    assert revision.sprint_id == "sprint-1"
    assert revision.source_negotiation_action == "revise_current_sprint"


def test_sprint_execution_attempt_from_dict_requires_attempt_and_sprint_ids() -> None:
    assert SprintExecutionAttempt.from_dict({"attempt_id": "sprint-1-attempt-1"}) is None
    attempt = SprintExecutionAttempt.from_dict(
        {
            "attempt_id": "sprint-1-attempt-1",
            "sprint_id": "sprint-1",
            "revision_id": "sprint-1-revision-1",
            "execution_target_kind": "revision",
            "execution_mode": "deterministic",
            "changed_target_hints": ["src/editor.tsx", "src/state/store.ts"],
            "execution_summary": "Apply the narrowed persistence fix before re-running QA.",
            "artifact_kind": "static_html_demo",
            "artifact_path": ".aionis-workbench/artifacts/task-1/sprint-1-attempt-1/index.html",
            "preview_command": "python3 -m http.server 4173 --directory /tmp/demo",
            "status": "recorded",
            "success": True,
        }
    )
    assert attempt is not None
    assert attempt.attempt_id == "sprint-1-attempt-1"
    assert attempt.execution_target_kind == "revision"
    assert attempt.success is True
    assert attempt.artifact_kind == "static_html_demo"


def test_app_harness_state_round_trips_execution_attempts() -> None:
    state = AppHarnessState.from_dict(
        {
            "active_sprint_contract": {
                "sprint_id": "sprint-1",
                "goal": "Ship the editor shell.",
            },
            "latest_execution_attempt": {
                "attempt_id": "sprint-1-attempt-1",
                "sprint_id": "sprint-1",
                "revision_id": "sprint-1-revision-1",
                "execution_target_kind": "revision",
                "execution_mode": "live",
                "changed_target_hints": ["src/editor.tsx"],
                "execution_summary": "Apply persistence fixes to the editor state path.",
                "status": "recorded",
                "success": True,
            },
            "execution_history": [
                {
                    "attempt_id": "sprint-1-attempt-1",
                    "sprint_id": "sprint-1",
                    "execution_target_kind": "revision",
                    "execution_mode": "live",
                    "changed_target_hints": ["src/editor.tsx"],
                    "execution_summary": "Apply persistence fixes to the editor state path.",
                    "status": "recorded",
                    "success": True,
                }
            ],
            "loop_status": "execution_recorded",
        }
    )

    assert state is not None
    assert state.latest_execution_attempt is not None
    assert state.latest_execution_attempt.execution_mode == "live"
    assert len(state.execution_history) == 1
    assert AppHarnessState.from_dict(state.to_dict()) == state
