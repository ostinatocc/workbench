from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from aionis_workbench.e2e.real_e2e.manifest import RealRepoSpec


_GIT_NETWORK_RETRYABLE_MARKERS = (
    "error in the http2 framing layer",
    "ssl_error_syscall",
    "the remote end hung up unexpectedly",
    "connection reset by peer",
    "connection timed out",
    "operation timed out",
    "empty reply from server",
    "failed to connect",
    "connection refused",
    "tlsv1 alert",
    "proxy connect aborted",
)
_GIT_RETRY_ATTEMPTS = 3


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


def _git_error_is_retryable(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _GIT_NETWORK_RETRYABLE_MARKERS)


def _run_git(*args: str, cwd: Path, retry_attempts: int = 1) -> str:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, retry_attempts + 1):
        try:
            result = subprocess.run(
                ["git", "-c", "http.version=HTTP/1.1", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as exc:
            last_error = exc
            stderr = exc.stderr or ""
            if attempt >= retry_attempts or not _git_error_is_retryable(stderr):
                raise
            time.sleep(min(2.0, 0.5 * attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("git command failed without a captured error")


def _clone_repo(repo_entry: RealRepoSpec, checkout_path: Path) -> None:
    checkout_path.parent.mkdir(parents=True, exist_ok=True)
    if checkout_path.exists():
        shutil.rmtree(checkout_path)
    try:
        _run_git(
            "clone",
            repo_entry.repo_url,
            str(checkout_path),
            cwd=checkout_path.parent,
            retry_attempts=_GIT_RETRY_ATTEMPTS,
        )
    except subprocess.CalledProcessError:
        if checkout_path.exists():
            shutil.rmtree(checkout_path)
        raise


def _fetch_repo(checkout_path: Path) -> None:
    _run_git(
        "fetch",
        "--all",
        "--tags",
        "--prune",
        cwd=checkout_path,
        retry_attempts=_GIT_RETRY_ATTEMPTS,
    )


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
