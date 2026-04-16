from __future__ import annotations

from aionis_workbench.live_profile import (
    LiveTimingRecord,
    load_live_profile_snapshot,
    resolve_live_profile_snapshot_path,
    save_live_profile_snapshot,
)


def test_live_timing_record_summarizes_phases() -> None:
    record = LiveTimingRecord(task_id="task-1")

    record.add_phase("ready", 1.2)
    record.add_phase("run", 12.5)

    assert record.total_duration_seconds == 13.7
    summary = record.summary()
    assert "task=task-1" in summary
    assert "ready=1.200s" in summary
    assert "run=12.500s" in summary
    assert "total=13.700s" in summary


def test_live_profile_snapshot_prefers_repo_local_snapshot(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_home = repo_root / ".real-live-home"
    save_live_profile_snapshot({"provider_id": "zai_glm51_coding", "recorded_at": "2026-04-05T00:00:00Z"}, home=repo_home)

    snapshot = load_live_profile_snapshot(repo_root=repo_root)
    path = resolve_live_profile_snapshot_path(repo_root=repo_root)

    assert snapshot["provider_id"] == "zai_glm51_coding"
    assert snapshot["recorded_at"] == "2026-04-05T00:00:00Z"
    assert path == (repo_home / ".aionis" / "workbench" / "live_profile.json")


def test_live_profile_snapshot_round_trips_recent_convergence_signals(tmp_path) -> None:
    repo_home = tmp_path / ".real-live-home"
    payload = {
        "provider_id": "zai_glm51_coding",
        "convergence_signal": "live-app-plan:needs_qa->ready@qa:passed",
        "recent_convergence_signals": [
            "live-app-advance:needs_qa->ready@qa:passed",
            "live-app-escalate:needs_qa->qa_failed@qa:failed",
        ],
    }

    save_live_profile_snapshot(payload, home=repo_home)
    snapshot = load_live_profile_snapshot(home=repo_home)

    assert snapshot["convergence_signal"] == "live-app-plan:needs_qa->ready@qa:passed"
    assert snapshot["recent_convergence_signals"] == [
        "live-app-advance:needs_qa->ready@qa:passed",
        "live-app-escalate:needs_qa->qa_failed@qa:failed",
    ]
