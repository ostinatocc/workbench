from __future__ import annotations

import pytest

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import (
    probe_live_run_resume_readiness,
    run_live_app_second_replan_scenario,
)


def test_live_app_second_replan_real_scenario(tmp_path) -> None:
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

    result = run_live_app_second_replan_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-live-home",
    )

    assert result.status == "passed"
    assert result.details["first_replanned_sprint_id"].startswith("sprint-1-replan-")
    assert result.details["second_replanned_sprint_id"].startswith(
        f'{result.details["first_replanned_sprint_id"]}-replan-'
    )
    assert result.details["loop_status"] == "sprint_replanned"
    assert result.details["replan_depth"] == 2
    assert result.details["replan_root_sprint_id"] == "sprint-1"
    assert result.details["retry_count"] == 0
    assert result.details["retry_remaining"] == 1
    assert result.details["provider_id"]
