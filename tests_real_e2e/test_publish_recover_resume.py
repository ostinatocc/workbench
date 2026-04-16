from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest
from aionis_workbench.e2e.real_e2e.scenario_runner import run_publish_recover_resume_scenario


def test_publish_recover_resume_real_scenario(tmp_path) -> None:
    repo_entry = next(item for item in load_real_repo_manifest() if "publish-recover-resume" in item.scenario_tags)

    result = run_publish_recover_resume_scenario(
        repo_entry,
        cache_root=tmp_path / ".real-e2e-cache",
        launcher_home=tmp_path / ".aionis-home",
    )

    assert result.status == "passed"
    assert result.details["publish_shell_view"] == "doc_publish"
    assert result.details["recover_shell_view"] == "doc_recover"
    assert result.details["resume_shell_view"] == "doc_resume"
    assert result.details["session_doc_latest_action"] == "resume"
    assert result.details["resume_selected_tool"] == "read"
    assert result.details["session_doc_selected_tool"] == "read"
    assert result.details["session_doc_event_source"] == "cursor_extension"
    assert result.details["history_actions"][:3] == ["resume", "recover", "publish"]
    assert result.details["session_doc_handoff_anchor"]
    assert "doc_publish_result" in result.details["artifact_kinds"]
    assert "doc_recover_result" in result.details["artifact_kinds"]
    assert "doc_resume_result" in result.details["artifact_kinds"]
