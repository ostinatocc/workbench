from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import run_editor_to_dream_scenario


def test_editor_to_dream_real_scenario(tmp_path) -> None:
    repo_entry = next(item for item in load_real_repo_manifest() if "editor-to-dream" in item.scenario_tags)

    result = run_editor_to_dream_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-home",
    )

    assert result.status == "passed"
    assert result.details["dream_shell_view"] == "dream"
    assert int(result.details["dream_promotion_count"] or 0) >= 1
    assert result.details["promotion_status"] in {"trial", "seed_ready"}
    assert result.details["dominant_doc_action"] == "compile"
    assert result.details["dominant_event_source"] == "cursor_extension"
    assert int(result.details["editor_sync_count"] or 0) >= 3
    assert result.details["session_doc_event_source"] == "cursor_extension"
    assert result.details["session_doc_latest_action"] == "compile"
