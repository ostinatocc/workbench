from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import run_launcher_runtime_cycle_scenario


def test_launcher_runtime_cycle_real_scenario(tmp_path) -> None:
    repo_entry = next(item for item in load_real_repo_manifest() if "launcher-runtime-cycle" in item.scenario_tags)

    result = run_launcher_runtime_cycle_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-home",
    )

    assert result.status == "passed"
    assert result.details["status_before"]["mode"] == "stopped"
    assert result.details["start_summary"]["mode"] == "running"
    assert result.details["start_summary"]["health"] == "available"
    assert result.details["status_after"]["mode"] == "running"
    assert result.details["status_after"]["health"] == "available"
    assert result.details["stop_action"] in {"stopped_runtime", "forced_stop_runtime", "no_managed_runtime", "cleared_stale_pid"}
    assert result.details["final_status_mode"] == "stopped"
