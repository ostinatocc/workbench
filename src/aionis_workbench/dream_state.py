from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _project_scope_slug(project_scope: str) -> str:
    return project_scope.replace(":", "_").replace("/", "_")


def dream_candidates_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "dream_candidates.json"


def project_dream_candidates_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "dream_candidates.json"
    )


def load_dream_candidates(
    *,
    repo_root: str,
    project_scope: str | None = None,
) -> dict[str, Any]:
    candidates: list[Path] = []
    if project_scope:
        candidates.append(project_dream_candidates_path(project_scope))
    candidates.append(dream_candidates_path(repo_root))
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


def save_dream_candidates(
    *,
    repo_root: str,
    project_scope: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    local_path = dream_candidates_path(repo_root)
    project_path = project_dream_candidates_path(project_scope)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(serialized)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(serialized)
    return local_path, project_path


def dream_promotions_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "dream_promotions.json"


def project_dream_promotions_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "dream_promotions.json"
    )


def load_dream_promotions(
    *,
    repo_root: str,
    project_scope: str | None = None,
) -> dict[str, Any]:
    candidates: list[Path] = []
    if project_scope:
        candidates.append(project_dream_promotions_path(project_scope))
    candidates.append(dream_promotions_path(repo_root))
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


def save_dream_promotions(
    *,
    repo_root: str,
    project_scope: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    local_path = dream_promotions_path(repo_root)
    project_path = project_dream_promotions_path(project_scope)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(serialized)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(serialized)
    return local_path, project_path
