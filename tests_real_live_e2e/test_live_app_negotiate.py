from __future__ import annotations

import pytest

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import (
    probe_live_run_resume_readiness,
    run_live_app_negotiate_scenario,
)


def test_live_app_negotiate_real_scenario(tmp_path) -> None:
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

    result = run_live_app_negotiate_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-live-home",
    )

    assert result.status == "passed"
    assert result.details["planner_mode"] == "live"
    assert result.details["recommended_action"] == "revise_current_sprint"
    assert result.details["planner_response"]
    assert result.details["provider_id"]
    assert result.details["model"]
    assert result.details["timeout_seconds"] > 0
    assert result.details["max_completion_tokens"] > 0
    assert result.details["ready_duration_seconds"] >= 0
    assert result.details["app_negotiate_duration_seconds"] >= 0
    assert result.details["total_duration_seconds"] >= result.details["app_negotiate_duration_seconds"]
