from __future__ import annotations

import pytest

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import (
    probe_live_run_resume_readiness,
    run_live_app_replan_generate_qa_scenario,
)


def test_live_app_replan_generate_qa_real_scenario(tmp_path) -> None:
    repo_entry = next(item for item in load_real_repo_manifest() if "live-app-plan" in item.scenario_tags)

    readiness = probe_live_run_resume_readiness(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-live-home",
    )
    if not readiness["live_ready"]:
        reason = str(readiness.get("live_ready_summary") or readiness.get("capability_state") or "live environment blocked")
        ready_line = str(readiness.get("ready_output") or "").splitlines()
        ready_hint = ready_line[0] if ready_line else ""
        pytest.skip(f"real-live-e2e requires a live-ready environment: {reason} {ready_hint}".strip())

    result = run_live_app_replan_generate_qa_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-live-home",
    )

    assert result.status == "passed"
    assert result.details["replanned_sprint_id"].startswith("sprint-1-replan-")
    assert result.details["execution_mode"] == "live"
    assert result.details["execution_summary"]
    assert result.details["evaluator_mode"] == "live"
    assert result.details["evaluation_status"] in {"passed", "failed"}
    assert result.details["provider_id"]
