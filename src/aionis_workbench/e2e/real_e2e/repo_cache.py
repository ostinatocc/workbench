from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from aionis_workbench.e2e.real_e2e.manifest import RealRepoSpec


def _workbench_root() -> Path:
    return Path(__file__).resolve().parents[4]


def real_e2e_cache_root(cache_root: str | Path | None = None) -> Path:
    if cache_root is not None:
        return Path(cache_root)
    return _workbench_root() / ".real-e2e-cache"


def repo_checkout_path(repo_entry: RealRepoSpec, cache_root: str | Path | None = None) -> Path:
    return real_e2e_cache_root(cache_root) / "repos" / repo_entry.id / "repo"


def repo_metadata_path(repo_entry: RealRepoSpec, cache_root: str | Path | None = None) -> Path:
    return real_e2e_cache_root(cache_root) / "repos" / repo_entry.id / "metadata.json"


def _run_git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _clone_repo(repo_entry: RealRepoSpec, checkout_path: Path) -> None:
    checkout_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git("clone", repo_entry.repo_url, str(checkout_path), cwd=checkout_path.parent)


def _fetch_repo(checkout_path: Path) -> None:
    _run_git("fetch", "--all", "--tags", "--prune", cwd=checkout_path)


def _repo_is_dirty(checkout_path: Path) -> bool:
    tracked = _run_git("status", "--short", cwd=checkout_path)
    if tracked.strip():
        return True
    untracked = _run_git("ls-files", "--others", "--exclude-standard", cwd=checkout_path)
    return bool(untracked.strip())


def _write_metadata(repo_entry: RealRepoSpec, resolved_head: str, metadata_path: Path) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "repo_url": repo_entry.repo_url,
        "commit_sha": repo_entry.commit_sha,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "resolved_head": resolved_head,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def ensure_repo_cached(repo_entry: RealRepoSpec, cache_root: str | Path | None = None) -> Path:
    checkout_path = repo_checkout_path(repo_entry, cache_root=cache_root)
    metadata_path = repo_metadata_path(repo_entry, cache_root=cache_root)
    if not checkout_path.exists():
        _clone_repo(repo_entry, checkout_path)
    elif _repo_is_dirty(checkout_path):
        shutil.rmtree(checkout_path)
        _clone_repo(repo_entry, checkout_path)
    _fetch_repo(checkout_path)
    _run_git("checkout", "--detach", repo_entry.commit_sha, cwd=checkout_path)
    resolved_head = _run_git("rev-parse", "HEAD", cwd=checkout_path)
    _write_metadata(repo_entry, resolved_head, metadata_path)
    return checkout_path
