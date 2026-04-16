from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from .launcher_state import launcher_paths
from .runtime_bridge_host import _runtime_health_status

RUNTIME_STARTUP_HEALTH_WAIT_SECONDS = float(os.environ.get("AIONIS_RUNTIME_STARTUP_HEALTH_WAIT_SECONDS", "35.0"))
RUNTIME_STARTUP_HEALTH_PROBE_TIMEOUT_SECONDS = float(
    os.environ.get("AIONIS_RUNTIME_STARTUP_HEALTH_PROBE_TIMEOUT_SECONDS", "5.0")
)
RUNTIME_STARTUP_HEALTH_POLL_INTERVAL_SECONDS = 0.25


def _default_workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_runtime_root(workspace_root: Path) -> Path:
    explicit_candidates: list[Path] = []
    for env_name in ("AIONIS_RUNTIME_ROOT", "AIONIS_CORE_DIR"):
        raw = os.environ.get(env_name)
        if raw:
            explicit_candidates.append(Path(raw).expanduser())

    for candidate in explicit_candidates:
        if (candidate / "package.json").exists():
            return candidate
    if explicit_candidates:
        return explicit_candidates[0]

    implicit_candidates = [
        workspace_root / "runtime-mainline",
        workspace_root.parent / "runtime-mainline",
        workspace_root.parent / "AionisCore",
        workspace_root.parent / "AionisRuntime",
    ]
    for candidate in implicit_candidates:
        if (candidate / "package.json").exists():
            return candidate

    return workspace_root / "runtime-mainline"


def _candidate_runtime_base_urls() -> list[str]:
    explicit = os.environ.get("AIONIS_BASE_URL")
    if explicit:
        return [explicit.rstrip("/")]
    return [
        "http://127.0.0.1:3101",
        "http://127.0.0.1:3001",
    ]


def _default_runtime_base_url() -> str:
    explicit = os.environ.get("AIONIS_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    return "http://127.0.0.1:3101"


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class RuntimeManager:
    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        home: str | Path | None = None,
        npm_executable: str = "npm",
    ) -> None:
        self._workspace_root = Path(workspace_root) if workspace_root is not None else _default_workspace_root()
        self._runtime_root = _resolve_runtime_root(self._workspace_root)
        self._paths = launcher_paths(Path(home) if home is not None else None)
        self._npm_executable = npm_executable

    def _runtime_exists(self) -> bool:
        return (self._runtime_root / "package.json").exists()

    def _read_pid(self) -> int | None:
        if not self._paths.runtime_pid.exists():
            return None
        raw = self._paths.runtime_pid.read_text().strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _resolved_health(self, *, timeout_seconds: float | None = None) -> tuple[str, str | None, str]:
        def _probe(candidate: str) -> tuple[str, str | None]:
            if timeout_seconds is None:
                return _runtime_health_status(candidate)
            return _runtime_health_status(candidate, timeout_seconds=timeout_seconds)

        candidates = [candidate.rstrip("/") for candidate in _candidate_runtime_base_urls()]
        last_status = "offline"
        last_reason: str | None = "runtime_base_url_missing"
        last_candidate = _default_runtime_base_url().rstrip("/")
        for candidate in candidates:
            status, reason = _probe(candidate)
            if status == "available":
                return status, reason, candidate
            last_status, last_reason, last_candidate = status, reason, candidate
        default_base_url = _default_runtime_base_url().rstrip("/")
        if default_base_url in candidates:
            return last_status, last_reason, last_candidate
        status, reason = _probe(default_base_url)
        return status, reason, default_base_url

    def _status_payload(
        self,
        *,
        mode: str,
        health_status: str,
        health_reason: str | None,
        base_url: str,
        pid: int | None,
        action: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": mode,
            "runtime_root": str(self._runtime_root),
            "base_url": base_url,
            "health_status": health_status,
            "health_reason": health_reason,
            "pid": pid,
            "pid_path": str(self._paths.runtime_pid),
            "stdout_path": str(self._paths.runtime_stdout),
            "stderr_path": str(self._paths.runtime_stderr),
            "command": [self._npm_executable, "run", "-s", "lite:start"],
        }
        if action:
            payload["action"] = action
        return payload

    def status(self) -> dict[str, object]:
        if not self._runtime_exists():
            return self._status_payload(
                mode="missing",
                health_status="offline",
                health_reason="runtime_workspace_missing",
                base_url=_default_runtime_base_url(),
                pid=None,
            )

        pid = self._read_pid()
        pid_alive = pid is not None and _pid_is_alive(pid)
        health_status, health_reason, base_url = self._resolved_health()
        if health_status == "available" or pid_alive:
            return self._status_payload(
                mode="running",
                health_status=health_status,
                health_reason=health_reason,
                base_url=base_url,
                pid=pid,
            )
        return self._status_payload(
            mode="stopped",
            health_status=health_status,
            health_reason=health_reason,
            base_url=base_url,
            pid=pid,
        )

    def start(self) -> dict[str, object]:
        current = self.status()
        if current["mode"] == "missing":
            current["action"] = "missing_workspace"
            return current
        if current["mode"] == "running" and current["health_status"] == "available":
            current["action"] = "reused_existing_runtime"
            return current
        if shutil.which(self._npm_executable) is None:
            return self._status_payload(
                mode="stopped",
                health_status="offline",
                health_reason="npm_missing",
                base_url=str(current["base_url"]),
                pid=None,
                action="missing_npm",
            )

        self._paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        port = urlparse(str(current["base_url"])).port or 3101
        env.setdefault("PORT", str(port))
        stdout = self._paths.runtime_stdout.open("ab")
        stderr = self._paths.runtime_stderr.open("ab")
        process = subprocess.Popen(
            [self._npm_executable, "run", "-s", "lite:start"],
            cwd=str(self._runtime_root),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        self._paths.runtime_pid.write_text(str(process.pid))

        deadline = time.monotonic() + RUNTIME_STARTUP_HEALTH_WAIT_SECONDS
        while time.monotonic() < deadline:
            health_status, health_reason, base_url = self._resolved_health(
                timeout_seconds=RUNTIME_STARTUP_HEALTH_PROBE_TIMEOUT_SECONDS
            )
            if health_status == "available":
                return self._status_payload(
                    mode="running",
                    health_status=health_status,
                    health_reason=health_reason,
                    base_url=base_url,
                    pid=process.pid,
                    action="started_runtime",
                )
            if process.poll() is not None:
                return self._status_payload(
                    mode="stopped",
                    health_status="degraded",
                    health_reason=f"runtime_process_exited_{process.returncode}",
                    base_url=str(current["base_url"]),
                    pid=process.pid,
                    action="runtime_exit_before_healthy",
                )
            time.sleep(RUNTIME_STARTUP_HEALTH_POLL_INTERVAL_SECONDS)

        return self._status_payload(
            mode="running" if process.poll() is None else "stopped",
            health_status="degraded",
            health_reason="runtime_health_unreachable",
            base_url=str(current["base_url"]),
            pid=process.pid,
            action="started_runtime_health_pending",
        )

    def stop(self) -> dict[str, object]:
        current = self.status()
        pid = self._read_pid()
        if pid is None:
            current["action"] = "no_managed_runtime"
            return current
        if not _pid_is_alive(pid):
            try:
                self._paths.runtime_pid.unlink()
            except FileNotFoundError:
                pass
            current["action"] = "cleared_stale_pid"
            current["pid"] = None
            return current

        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not _pid_is_alive(pid):
                try:
                    self._paths.runtime_pid.unlink()
                except FileNotFoundError:
                    pass
                return self._status_payload(
                    mode="stopped",
                    health_status="degraded",
                    health_reason="runtime_stopped",
                    base_url=str(current["base_url"]),
                    pid=None,
                    action="stopped_runtime",
                )
            time.sleep(0.1)

        return self._status_payload(
            mode="running",
            health_status=str(current["health_status"]),
            health_reason="runtime_stop_timeout",
            base_url=str(current["base_url"]),
            pid=pid,
            action="stop_timeout",
        )
