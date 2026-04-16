from __future__ import annotations

from pathlib import Path

from aionis_workbench.doc_learning import inspect_doc_target, list_doc_learning_records
from aionis_workbench.session import SessionState, save_session


def test_list_doc_learning_records_surfaces_repo_docs_with_evidence(tmp_path) -> None:
    project_scope = f"project:tests/doc-learning-{tmp_path.name}-list"
    workflow_path = tmp_path / "flows" / "workflow.aionis.md"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("# workflow\n")

    session = SessionState(
        task_id="doc-learning-1",
        goal="Track one doc workflow.",
        repo_root=str(tmp_path),
        project_identity="tests/doc-learning",
        project_scope=project_scope,
    )
    session.selected_task_family = "task:docs"
    session.continuity_snapshot = {
        "task_family": "task:docs",
        "doc_workflow": {
            "latest_action": "publish",
            "status": "published",
            "doc_input": "flows/workflow.aionis.md",
            "source_doc_id": "workflow-001",
            "handoff_anchor": "anchor-1",
            "artifact_refs": ["./.aionis-workbench/artifacts/doc-learning-1/doc-publish.json"],
            "history": [{"action": "publish", "status": "published", "doc_input": "flows/workflow.aionis.md"}],
        },
    }
    save_session(session)

    rows = list_doc_learning_records(
        repo_root=str(tmp_path),
        project_scope=project_scope,
        limit=8,
    )

    assert len(rows) == 1
    assert rows[0]["path"] == "flows/workflow.aionis.md"
    assert rows[0]["has_evidence"] is True
    assert rows[0]["latest_task_id"] == "doc-learning-1"
    assert rows[0]["latest_action"] == "publish"


def test_inspect_doc_target_handles_workflow_and_artifact(tmp_path) -> None:
    project_scope = f"project:tests/doc-learning-{tmp_path.name}-inspect"
    workflow_path = tmp_path / "flows" / "workflow.aionis.md"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("# workflow\n")

    artifact_path = tmp_path / ".aionis-workbench" / "artifacts" / "doc-learning-2" / "doc-publish.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        '{"kind":"doc_publish_result","doc_action":"publish","status":"published","source_doc_id":"workflow-002","handoff_anchor":"anchor-2"}'
    )

    session = SessionState(
        task_id="doc-learning-2",
        goal="Inspect one doc workflow.",
        repo_root=str(tmp_path),
        project_identity="tests/doc-learning",
        project_scope=project_scope,
    )
    session.selected_task_family = "task:docs"
    session.continuity_snapshot = {
        "task_family": "task:docs",
        "doc_workflow": {
            "latest_action": "resume",
            "status": "completed",
            "doc_input": "flows/workflow.aionis.md",
            "source_doc_id": "workflow-002",
            "handoff_anchor": "anchor-2",
            "selected_tool": "read",
            "artifact_refs": [".aionis-workbench/artifacts/doc-learning-2/doc-publish.json"],
            "history": [{"action": "resume", "status": "completed", "doc_input": "flows/workflow.aionis.md"}],
        },
    }
    save_session(session)

    workflow_payload = inspect_doc_target(
        repo_root=str(tmp_path),
        project_scope=project_scope,
        target="flows/workflow.aionis.md",
    )
    artifact_payload = inspect_doc_target(
        repo_root=str(tmp_path),
        project_scope=project_scope,
        target=".aionis-workbench/artifacts/doc-learning-2/doc-publish.json",
    )

    assert workflow_payload["inspect_kind"] == "workflow"
    assert workflow_payload["evidence_count"] == 1
    assert workflow_payload["latest_record"]["latest_action"] == "resume"
    assert artifact_payload["inspect_kind"] == "artifact"
    assert artifact_payload["artifact_summary"]["kind"] == "doc_publish_result"
    assert artifact_payload["artifact_summary"]["handoff_anchor"] == "anchor-2"
