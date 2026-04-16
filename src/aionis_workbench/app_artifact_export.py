from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .delivery_families import (
    delivery_family_development_command,
    delivery_family_export_entrypoint,
    delivery_family_preview_command,
    infer_delivery_family_from_artifact_paths,
)
from .delivery_workspace import DeliveryWorkspaceAdapter
from .session import SessionState


def _latest_exportable_attempt(session: SessionState):
    state = session.app_harness_state
    if state is None:
        return None
    attempt = state.latest_execution_attempt
    if attempt is not None:
        return attempt
    for item in reversed(state.execution_history):
        if str(item.artifact_root or "").strip() or str(item.artifact_path or "").strip():
            return item
    return None


def export_latest_app_artifact(
    *,
    session: SessionState,
    output_dir: str,
) -> dict[str, Any]:
    attempt = _latest_exportable_attempt(session)
    if attempt is None:
        raise ValueError("no execution attempt is available to export")
    artifact_root_value = str(attempt.artifact_root or "").strip()
    artifact_root = Path(artifact_root_value).expanduser() if artifact_root_value else None
    artifact_path_value = str(attempt.artifact_path or "").strip()
    if (artifact_root is None or not artifact_root.exists()) and artifact_path_value:
        resolved_artifact_path = (Path(session.repo_root) / artifact_path_value).expanduser()
        if resolved_artifact_path.exists():
            artifact_root = (
                resolved_artifact_path.parent
                if resolved_artifact_path.is_file()
                else resolved_artifact_path
            )
    if (artifact_root is None or not artifact_root.exists()) and session.task_id:
        fallback_workspace_root = Path(session.repo_root) / ".aionis-workbench" / "delivery-workspaces" / session.task_id
        if fallback_workspace_root.exists():
            artifact_root = fallback_workspace_root
    if artifact_root is None or not artifact_root.exists():
        raise ValueError("latest execution attempt does not have an exportable artifact root")

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        artifact_root,
        destination,
        ignore=shutil.ignore_patterns("node_modules", ".DS_Store"),
    )

    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(destination),
        collect_changed_files_fn=lambda: [],
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=list(attempt.changed_files),
        workspace_root=destination,
    )
    family_id = infer_delivery_family_from_artifact_paths(artifact_paths)
    entrypoint = delivery_family_export_entrypoint(
        family_id,
        destination=destination,
        artifact_path=str(attempt.artifact_path or ""),
    )
    preview_command = delivery_family_preview_command(
        family_id,
        destination=destination,
    ) or adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=destination,
    )
    development_command = delivery_family_development_command(
        family_id,
        destination=destination,
    )
    readme_path = destination / "README.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Exported App Artifact",
                "",
                f"- task_id: `{session.task_id}`",
                f"- sprint_id: `{attempt.sprint_id}`",
                f"- attempt_id: `{attempt.attempt_id}`",
                f"- execution_mode: `{attempt.execution_mode}`",
                f"- source_root: `{artifact_root}`",
                f"- entrypoint: `{entrypoint}`",
                f"- preview_command: `{preview_command or 'none'}`",
                f"- development_command: `{development_command or 'none'}`",
                f"- validation_command: `{attempt.validation_command or 'none'}`",
                f"- validation_summary: `{attempt.validation_summary or 'none'}`",
                "",
                "Changed files:",
                *([f"- `{item}`" for item in attempt.changed_files] or ["- none"]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "task_id": session.task_id,
        "attempt_id": attempt.attempt_id,
        "artifact_root": str(artifact_root),
        "export_root": str(destination),
        "entrypoint": str(entrypoint),
        "preview_command": preview_command,
        "development_command": development_command,
        "validation_command": attempt.validation_command,
        "validation_summary": attempt.validation_summary,
        "changed_files": attempt.changed_files[:8],
        "shell_view": "app_export",
    }
