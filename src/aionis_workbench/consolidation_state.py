from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_scope_slug(project_scope: str) -> str:
    return project_scope.replace(":", "_").replace("/", "_")


def consolidation_summary_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "consolidation.json"


def project_consolidation_summary_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "consolidation.json"
    )


def consolidation_lock_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "consolidation.lock"


def consolidation_state_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "consolidation_state.json"


def project_consolidation_lock_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "consolidation.lock"
    )


def project_consolidation_state_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "consolidation_state.json"
    )


def load_consolidation_summary(
    *,
    repo_root: str,
    project_scope: str,
) -> dict[str, Any]:
    candidates = [
        project_consolidation_summary_path(project_scope),
        consolidation_summary_path(repo_root),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def consolidation_lock_active(*, repo_root: str, project_scope: str) -> bool:
    candidates = [
        project_consolidation_lock_path(project_scope),
        consolidation_lock_path(repo_root),
    ]
    return any(path.exists() for path in candidates)


@dataclass
class ConsolidationLock:
    started_at: str
    lock_paths: list[Path]


def acquire_consolidation_lock(*, repo_root: str, project_scope: str) -> ConsolidationLock:
    started_at = datetime.now(timezone.utc).isoformat()
    payload = {"started_at": started_at, "project_scope": project_scope}
    lock_paths = [
        consolidation_lock_path(repo_root),
        project_consolidation_lock_path(project_scope),
    ]
    created: list[Path] = []
    try:
        for path in lock_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            created.append(path)
    except FileExistsError as exc:
        for path in created:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise RuntimeError(f"consolidation already running for {project_scope}") from exc
    return ConsolidationLock(started_at=started_at, lock_paths=created)


def release_consolidation_lock(lock: ConsolidationLock | None) -> None:
    if lock is None:
        return
    for path in lock.lock_paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def save_consolidation_summary(
    *,
    repo_root: str,
    project_scope: str,
    payload: dict[str, object],
) -> tuple[Path, Path]:
    local_path = consolidation_summary_path(repo_root)
    project_path = project_consolidation_summary_path(project_scope)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(serialized)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(serialized)
    return local_path, project_path


def load_consolidation_state(
    *,
    repo_root: str,
    project_scope: str,
) -> dict[str, Any]:
    candidates = [
        project_consolidation_state_path(project_scope),
        consolidation_state_path(repo_root),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def save_consolidation_state(
    *,
    repo_root: str,
    project_scope: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    local_path = consolidation_state_path(repo_root)
    project_path = project_consolidation_state_path(project_scope)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(serialized)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(serialized)
    return local_path, project_path
