from __future__ import annotations

import os
import socket
import signal
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aionis_workbench.runtime_manager import RuntimeManager


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _runtime_base_url(base_url: str) -> Iterator[None]:
    previous = os.environ.get("AIONIS_BASE_URL")
    os.environ["AIONIS_BASE_URL"] = base_url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AIONIS_BASE_URL", None)
        else:
            os.environ["AIONIS_BASE_URL"] = previous


class RealRuntimeEnv:
    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        home: str | Path | None = None,
        base_url: str | None = None,
    ) -> None:
        self.base_url = base_url or f"http://127.0.0.1:{_find_free_port()}"
        self._manager = RuntimeManager(workspace_root=workspace_root, home=home)

    def status(self) -> dict[str, object]:
        with _runtime_base_url(self.base_url):
            return self._manager.status()

    def start(self) -> dict[str, object]:
        with _runtime_base_url(self.base_url):
            return self._manager.start()

    def stop(self) -> dict[str, object]:
        with _runtime_base_url(self.base_url):
            payload = self._manager.stop()
            if payload.get("action") != "stop_timeout":
                return payload
            pid = payload.get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    if self._manager.status().get("pid") is None:
                        break
                    time.sleep(0.1)
                try:
                    self._manager._paths.runtime_pid.unlink()
                except FileNotFoundError:
                    pass
                payload = self._manager.status()
                payload["action"] = "forced_stop_runtime"
                payload["pid"] = None
            return payload

    def is_healthy(self) -> bool:
        return self.status().get("health_status") == "available"
