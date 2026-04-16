from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RealRepoSpec:
    id: str
    repo_url: str
    commit_sha: str
    language: str
    default_branch: str
    scenario_tags: tuple[str, ...]
    validation_commands: tuple[str, ...]
    doc_paths: tuple[str, ...]
    expected_runtime_mode: str


def _workbench_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_real_repo_manifest_path() -> Path:
    return _workbench_root() / "e2e" / "real_repos" / "manifest.json"


def _require_text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"real repo manifest entry is missing required field: {key}")
    return value.strip()


def _require_non_empty_list(entry: dict[str, Any], key: str) -> tuple[str, ...]:
    value = entry.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"real repo manifest entry is missing required list: {key}")
    items = tuple(str(item).strip() for item in value if str(item).strip())
    if not items:
        raise ValueError(f"real repo manifest entry has an empty required list: {key}")
    return items


def _optional_list(entry: dict[str, Any], key: str) -> tuple[str, ...]:
    value = entry.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"real repo manifest entry has invalid list field: {key}")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _parse_repo(entry: dict[str, Any]) -> RealRepoSpec:
    return RealRepoSpec(
        id=_require_text(entry, "id"),
        repo_url=_require_text(entry, "repo_url"),
        commit_sha=_require_text(entry, "commit_sha"),
        language=_require_text(entry, "language"),
        default_branch=_require_text(entry, "default_branch"),
        scenario_tags=_require_non_empty_list(entry, "scenario_tags"),
        validation_commands=_optional_list(entry, "validation_commands"),
        doc_paths=_optional_list(entry, "doc_paths"),
        expected_runtime_mode=_require_text(entry, "expected_runtime_mode"),
    )


def load_real_repo_manifest(path: str | Path | None = None) -> list[RealRepoSpec]:
    manifest_path = Path(path) if path is not None else default_real_repo_manifest_path()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    repo_entries = payload.get("repos")
    if not isinstance(repo_entries, list) or not repo_entries:
        raise ValueError("real repo manifest must define a non-empty repos list")
    return [_parse_repo(entry) for entry in repo_entries]
