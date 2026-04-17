from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class AionisConfig:
    base_url: str
    tenant_id: str
    scope: str
    actor: str


@dataclass(frozen=True)
class WorkbenchConfig:
    execution_host_runtime: str
    model: str
    system_prompt: str | None
    provider: str
    api_key: str | None
    base_url: str | None
    max_completion_tokens: int | None
    model_timeout_seconds: float | None
    model_max_retries: int
    repo_root: str
    project_identity: str
    project_scope: str
    auto_consolidation_enabled: bool
    auto_consolidation_min_hours: float
    auto_consolidation_min_new_sessions: int
    auto_consolidation_scan_throttle_minutes: float


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_healthy_runtime(base_url: str) -> bool:
    try:
        with urlopen(base_url.rstrip("/") + "/health", timeout=2.0) as response:
            return 200 <= response.status < 300
    except (OSError, URLError, ValueError):
        return False


def resolve_aionis_base_url() -> str:
    explicit = os.environ.get("AIONIS_BASE_URL")
    if explicit:
        return explicit.rstrip("/")

    candidates = (
        "http://127.0.0.1:3101",
        "http://127.0.0.1:3001",
    )
    for candidate in candidates:
        if _is_healthy_runtime(candidate):
            return candidate

    return "http://127.0.0.1:3101"


def _parse_repo_identity_from_remote(remote_url: str) -> str | None:
    cleaned = remote_url.strip()
    patterns = (
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$",
        r"gitlab\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return None


def _read_origin_url(repo_root: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", repo_root, "config", "--get", "remote.origin.url"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return ""


def _resolve_canonical_remote_url(repo_root: str, *, max_depth: int = 3) -> str:
    current_root = str(Path(repo_root).expanduser().resolve())
    visited: set[str] = set()

    for _ in range(max_depth):
        if current_root in visited:
            break
        visited.add(current_root)
        remote_url = _read_origin_url(current_root)
        if not remote_url:
            return ""
        parsed = _parse_repo_identity_from_remote(remote_url)
        if parsed:
            return remote_url
        remote_path = Path(remote_url).expanduser()
        if remote_path.exists() and (remote_path / ".git").exists():
            current_root = str(remote_path.resolve())
            continue
        return remote_url

    return ""


def resolve_project_identity(repo_root: str) -> str:
    explicit = os.environ.get("WORKBENCH_PROJECT_IDENTITY")
    if explicit:
        return explicit.strip()

    remote_url = _resolve_canonical_remote_url(repo_root)

    if remote_url:
        parsed = _parse_repo_identity_from_remote(remote_url)
        if parsed:
            return parsed

    return f"local/{Path(repo_root).name}"


def resolve_project_scope(repo_root: str) -> str:
    explicit_scope = os.environ.get("AIONIS_SCOPE")
    if explicit_scope:
        return explicit_scope.strip()
    project_identity = resolve_project_identity(repo_root)
    return f"project:{project_identity}"


def load_aionis_config(project_scope: str) -> AionisConfig:
    return AionisConfig(
        base_url=resolve_aionis_base_url(),
        tenant_id=os.environ.get("AIONIS_TENANT_ID", "default"),
        scope=project_scope,
        actor=os.environ.get("AIONIS_ACTOR", "aionis-workbench"),
    )


def resolve_repo_root(repo_root_override: str | None = None) -> str:
    repo_root_value = repo_root_override or os.environ.get("WORKBENCH_REPO_ROOT")

    if not repo_root_value:
        cwd = Path.cwd().resolve()
        if (
            (cwd / "src" / "aionis_workbench").exists()
            and (cwd / "pyproject.toml").exists()
        ) or (cwd / ".aionis-workbench").exists():
            repo_root_value = str(cwd)

    if not repo_root_value:
        raise ValueError("Workbench repo root is required. Pass --repo-root or set WORKBENCH_REPO_ROOT.")

    return str(Path(repo_root_value).expanduser().resolve())


def load_workbench_config(repo_root_override: str | None = None) -> WorkbenchConfig:
    repo_root = resolve_repo_root(repo_root_override)
    project_identity = resolve_project_identity(repo_root)
    project_scope = resolve_project_scope(repo_root)
    model_timeout_seconds = float(os.environ.get("WORKBENCH_MODEL_TIMEOUT_SECONDS", "45"))
    model_max_retries = int(os.environ.get("WORKBENCH_MODEL_MAX_RETRIES", "1"))
    auto_consolidation_enabled = _env_flag("AIONIS_AUTO_CONSOLIDATE", False)
    auto_consolidation_min_hours = float(os.environ.get("AIONIS_AUTO_CONSOLIDATE_MIN_HOURS", "24"))
    auto_consolidation_min_new_sessions = int(os.environ.get("AIONIS_AUTO_CONSOLIDATE_MIN_NEW_SESSIONS", "5"))
    auto_consolidation_scan_throttle_minutes = float(os.environ.get("AIONIS_AUTO_CONSOLIDATE_SCAN_THROTTLE_MINUTES", "10"))
    # Resolve provider-specific settings; shared fields are set once below.
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openrouter_api_key:
        provider = "openrouter"
        model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-5.4")
        api_key: str | None = openrouter_api_key
        base_url: str | None = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    elif openai_api_key:
        provider = "openai"
        model = os.environ.get("WORKBENCH_MODEL", "gpt-5")
        api_key = openai_api_key
        base_url = os.environ.get("OPENAI_BASE_URL")
    else:
        provider = "offline"
        model = os.environ.get("WORKBENCH_MODEL", "gpt-5")
        api_key = None
        base_url = None

    return WorkbenchConfig(
        execution_host_runtime=os.environ.get("WORKBENCH_EXECUTION_HOST", "openai_agents").strip().lower(),
        model=model,
        system_prompt=os.environ.get("WORKBENCH_SYSTEM_PROMPT"),
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        max_completion_tokens=int(os.environ.get("WORKBENCH_MAX_COMPLETION_TOKENS", "8192")),
        model_timeout_seconds=model_timeout_seconds,
        model_max_retries=model_max_retries,
        repo_root=repo_root,
        project_identity=project_identity,
        project_scope=project_scope,
        auto_consolidation_enabled=auto_consolidation_enabled,
        auto_consolidation_min_hours=auto_consolidation_min_hours,
        auto_consolidation_min_new_sessions=auto_consolidation_min_new_sessions,
        auto_consolidation_scan_throttle_minutes=auto_consolidation_scan_throttle_minutes,
    )
