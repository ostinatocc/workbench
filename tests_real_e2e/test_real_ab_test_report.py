from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.repo_cache import ensure_repo_cached
from aionis_workbench.runtime import AionisWorkbench


def test_real_ab_test_report_scenario(tmp_path, monkeypatch) -> None:
    repo_entry = next(
        item for item in load_real_repo_manifest() if "app-harness-planner-contract" in item.scenario_tags
    )
    repo_root = ensure_repo_cached(repo_entry, cache_root=tmp_path / ".real-e2e-cache")

    monkeypatch.setenv("WORKBENCH_PROJECT_IDENTITY", f"real-e2e/ab-test/{repo_entry.id}")
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(repo_root))
    task_id = f"{repo_entry.id}-ab-test-1"

    workbench.ingest(
        task_id=task_id,
        task="Establish app harness state for an A/B benchmark scenario.",
        summary="Create a persisted session for a bounded persistence-fix loop.",
        target_files=["README.md"],
        validation_commands=["git status --short"],
        validation_ok=True,
        validation_summary="git status completed.",
    )
    workbench.app_plan(
        task_id=task_id,
        prompt="Build a visual dependency explorer for async task orchestration.",
    )
    workbench.app_sprint(
        task_id=task_id,
        sprint_id="sprint-1",
        goal="Ship the graph shell and timeline panel.",
        scope=["graph shell", "timeline panel"],
        acceptance_checks=["npm test"],
        done_definition=["graph loads", "timeline renders"],
        proposed_by="planner",
        approved=True,
    )
    workbench.app_qa(
        task_id=task_id,
        sprint_id="sprint-1",
        status="failed",
        scores=["functionality=0.62", "design_quality=0.78"],
        blocker_notes=["timeline entries reset on refresh"],
    )
    workbench.app_negotiate(
        task_id=task_id,
        sprint_id="sprint-1",
        objections=["timeline entries reset on refresh"],
    )
    workbench.app_retry(
        task_id=task_id,
        sprint_id="sprint-1",
        revision_notes=["fix timeline persistence"],
    )
    workbench.app_generate(
        task_id=task_id,
        sprint_id="sprint-1",
        execution_summary="Apply the narrowed persistence patch and rerun QA.",
        changed_target_hints=["README.md"],
    )
    workbench.app_qa(
        task_id=task_id,
        sprint_id="sprint-1",
        status="passed",
        scores=["functionality=0.90", "design_quality=0.82", "code_quality=0.80"],
        summary="Timeline persistence is stable and the sprint clears the evaluator bar.",
    )

    payload = workbench.ab_test_compare(
        task_id=task_id,
        scenario_id="persistence-and-hydration",
        baseline_ended_in="escalate",
        baseline_duration_seconds=120.5,
        baseline_retry_count=1,
        baseline_convergence_signal="baseline:needs_qa->qa_failed@qa:failed",
        baseline_final_execution_gate="qa_failed",
        baseline_gate_flow="needs_qa->qa_failed@qa:failed",
        baseline_escalated=True,
    )

    assert payload["shell_view"] == "ab_test_compare"
    assert payload["scenario_id"] == "persistence-and-hydration"
    assert payload["comparison"]["winner"] == "aionis"
    assert payload["baseline"]["ended_in"] == "escalate"
    assert payload["aionis"]["ended_in"] == "advance"
    assert payload["aionis"]["final_execution_gate"] == "ready"
