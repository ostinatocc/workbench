from __future__ import annotations

import json
import subprocess
from pathlib import Path

from aionis_workbench.e2e.real_e2e.manifest import RealRepoSpec
from aionis_workbench.e2e.real_e2e.repo_cache import (
    ensure_repo_cached,
    repo_checkout_path,
    repo_metadata_path,
)


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _create_source_repo(tmp_path: Path) -> tuple[str, str]:
    repo = tmp_path / "source-repo"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    _git("config", "user.name", "Aionis E2E", cwd=repo)
    _git("config", "user.email", "e2e@example.com", cwd=repo)
    (repo / "README.md").write_text("# real repo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-m", "initial", cwd=repo)
    first_commit = _git("rev-parse", "HEAD", cwd=repo)
    (repo / "README.md").write_text("# real repo\n\nsecond\n", encoding="utf-8")
    _git("commit", "-am", "second", cwd=repo)
    second_commit = _git("rev-parse", "HEAD", cwd=repo)
    return str(repo), first_commit or second_commit


def _repo_entry(repo_url: str, commit_sha: str) -> RealRepoSpec:
    return RealRepoSpec(
        id="local-real-repo",
        repo_url=repo_url,
        commit_sha=commit_sha,
        language="markdown",
        default_branch="main",
        scenario_tags=("editor-to-dream",),
        validation_commands=(),
        doc_paths=("README.md",),
        expected_runtime_mode="inspect-only",
    )


def test_repo_cache_clones_into_expected_path(tmp_path: Path) -> None:
    repo_url, commit_sha = _create_source_repo(tmp_path)
    entry = _repo_entry(repo_url, commit_sha)
    cache_root = tmp_path / ".real-e2e-cache"

    checkout_path = ensure_repo_cached(entry, cache_root=cache_root)

    assert checkout_path == repo_checkout_path(entry, cache_root=cache_root)
    assert checkout_path.exists()
    assert (checkout_path / ".git").exists()


def test_repo_cache_reuses_existing_clone(tmp_path: Path) -> None:
    repo_url, commit_sha = _create_source_repo(tmp_path)
    entry = _repo_entry(repo_url, commit_sha)
    cache_root = tmp_path / ".real-e2e-cache"

    checkout_path = ensure_repo_cached(entry, cache_root=cache_root)
    second_checkout_path = ensure_repo_cached(entry, cache_root=cache_root)

    assert second_checkout_path == checkout_path
    assert (second_checkout_path / ".git").exists()


def test_repo_cache_checks_out_requested_commit(tmp_path: Path) -> None:
    repo_url, commit_sha = _create_source_repo(tmp_path)
    entry = _repo_entry(repo_url, commit_sha)
    cache_root = tmp_path / ".real-e2e-cache"

    checkout_path = ensure_repo_cached(entry, cache_root=cache_root)
    resolved_head = _git("rev-parse", "HEAD", cwd=checkout_path)
    metadata = json.loads(repo_metadata_path(entry, cache_root=cache_root).read_text(encoding="utf-8"))

    assert resolved_head == commit_sha
    assert metadata["repo_url"] == repo_url
    assert metadata["commit_sha"] == commit_sha
    assert metadata["resolved_head"] == commit_sha
    assert metadata["fetched_at"]


def test_repo_cache_reclones_dirty_checkout(tmp_path: Path) -> None:
    repo_url, commit_sha = _create_source_repo(tmp_path)
    entry = _repo_entry(repo_url, commit_sha)
    cache_root = tmp_path / ".real-e2e-cache"

    checkout_path = ensure_repo_cached(entry, cache_root=cache_root)
    (checkout_path / "README.md").write_text("# dirty checkout\n", encoding="utf-8")
    (checkout_path / ".reuse-marker").write_text("remove me", encoding="utf-8")

    second_checkout_path = ensure_repo_cached(entry, cache_root=cache_root)

    assert second_checkout_path == checkout_path
    assert (second_checkout_path / "README.md").read_text(encoding="utf-8") == "# real repo\n"
    assert not (second_checkout_path / ".reuse-marker").exists()
