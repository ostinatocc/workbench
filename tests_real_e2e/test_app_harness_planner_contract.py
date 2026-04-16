from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import run_app_harness_planner_contract_scenario


def test_app_harness_planner_contract_real_scenario(tmp_path) -> None:
    repo_entry = next(
        item for item in load_real_repo_manifest() if "app-harness-planner-contract" in item.scenario_tags
    )

    result = run_app_harness_planner_contract_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-home",
    )

    assert result.status == "passed"
    assert result.details["product_title"] == "Visual Dependency Explorer"
    assert result.details["product_app_type"] == "desktop_like_web_app"
    assert result.details["feature_groups"] == [
        "core_workflow",
        "supporting_workflows",
        "system_foundations",
    ]
    assert result.details["product_stack"] == ["React", "Vite", "SQLite"]
    assert result.details["active_sprint_id"] == "sprint-2-replan-1"
    assert result.details["active_sprint_approved"] is False
    assert result.details["planner_proposed_sprint"] == "deterministic"
    assert result.details["next_planned_sprint_ids"] == []
    assert result.details["next_planned_sprint_goal"] == ""
    assert result.details["planning_rationale_count"] == 4
    assert result.details["top_planning_rationale"] == (
        "Start by making the core workflow tangible: visual dependency explorer."
    )
    assert result.details["latest_qa_status"] == ""
    assert result.details["latest_qa_evaluator_mode"] == ""
    assert result.details["latest_qa_failing_criteria"] == []
    assert result.details["latest_negotiation_action"] == ""
    assert result.details["latest_negotiation_objections"] == []
    assert result.details["latest_revision_id"] == ""
    assert result.details["latest_revision_planner_mode"] == ""
    assert result.details["latest_revision_baseline_status"] == ""
    assert result.details["latest_revision_outcome_status"] == ""
    assert result.details["latest_revision_improvement_status"] == ""
    assert result.details["latest_execution_attempt_id"] == ""
    assert result.details["latest_execution_mode"] == ""
    assert result.details["latest_execution_target_kind"] == ""
    assert result.details["latest_execution_summary"] == ""
    assert result.details["latest_execution_status"] == ""
    assert result.details["latest_execution_success"] is False
    assert result.details["execution_history_count"] == 2
    assert result.details["current_sprint_execution_count"] == 0
    assert result.details["replan_depth"] == 1
    assert result.details["replan_root_sprint_id"] == "sprint-2"
    assert result.details["retry_count"] == 0
    assert result.details["retry_remaining"] == 1
    assert result.details["retry_budget"] == 1
    assert result.details["evaluator_criteria_count"] == 3
    assert result.details["loop_status"] == "sprint_replanned"
