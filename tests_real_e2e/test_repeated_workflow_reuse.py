from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import run_repeated_workflow_reuse_scenario


def test_repeated_workflow_reuse_real_scenario(tmp_path) -> None:
    repo_entry = next(item for item in load_real_repo_manifest() if "repeated-workflow-reuse" in item.scenario_tags)

    result = run_repeated_workflow_reuse_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-home",
    )

    assert result.status == "passed"
    assert result.details["consolidate_shell_view"] == "consolidate"
    assert result.details["doc_seed_ready"] is True
    assert int(result.details["doc_sample_count"] or 0) >= 3
    assert result.details["dominant_event_source"] == "cursor_extension"
    assert int(result.details["editor_sync_count"] or 0) >= 3
    assert int(result.details["dashboard_doc_prior_ready_count"] or 0) >= 1
    assert int(result.details["dashboard_doc_editor_sync_event_count"] or 0) >= 3
    assert (
        result.details["dashboard_proof_summary"]
        == "recent families already have seed-ready priors, and editor-driven doc reuse is live"
    )
