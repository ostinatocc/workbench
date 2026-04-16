from __future__ import annotations

from pathlib import Path

from aionis_workbench.e2e.real_e2e.runtime_env import RealRuntimeEnv


def test_real_runtime_env_can_start_confirm_health_and_stop(tmp_path) -> None:
    runtime_env = RealRuntimeEnv(home=tmp_path)

    start_payload = runtime_env.start()
    status_payload = runtime_env.status()

    assert start_payload["mode"] == "running"
    assert status_payload["health_status"] == "available"
    assert runtime_env.is_healthy()

    stop_payload = runtime_env.stop()
    assert stop_payload["action"] in {"stopped_runtime", "forced_stop_runtime", "no_managed_runtime"}


def test_real_runtime_env_start_retries_pending_health(monkeypatch, tmp_path) -> None:
    class FakeRuntimeManager:
        def __init__(self, *, workspace_root=None, home=None) -> None:
            self.workspace_root = workspace_root
            self.home = home
            self._statuses = iter(
                [
                    {"mode": "running", "health_status": "degraded", "health_reason": "runtime_health_unreachable"},
                    {"mode": "running", "health_status": "available", "health_reason": None},
                ]
            )

        def start(self) -> dict[str, object]:
            return {
                "mode": "running",
                "health_status": "degraded",
                "health_reason": "runtime_health_unreachable",
                "action": "started_runtime_health_pending",
            }

        def status(self) -> dict[str, object]:
            return next(self._statuses)

        def stop(self) -> dict[str, object]:
            return {"action": "stopped_runtime"}

    monkeypatch.setattr("aionis_workbench.e2e.real_e2e.runtime_env.RuntimeManager", FakeRuntimeManager)
    monkeypatch.setattr("aionis_workbench.e2e.real_e2e.runtime_env._find_free_port", lambda: 39001)

    runtime_env = RealRuntimeEnv(home=Path(tmp_path) / ".aionis-home")

    start_payload = runtime_env.start()

    assert start_payload["mode"] == "running"
    assert start_payload["health_status"] == "available"


def test_real_runtime_env_restarts_once_after_persistent_pending_health(monkeypatch, tmp_path) -> None:
    class FakeRuntimeManager:
        def __init__(self, *, workspace_root=None, home=None) -> None:
            self.workspace_root = workspace_root
            self.home = home
            self.start_calls = 0
            self.stop_calls = 0
            self._statuses = [
                [
                    {"mode": "running", "health_status": "degraded", "health_reason": "runtime_health_unreachable"},
                    {"mode": "running", "health_status": "degraded", "health_reason": "runtime_health_unreachable"},
                ],
                [
                    {"mode": "running", "health_status": "available", "health_reason": None},
                ],
            ]

        def start(self) -> dict[str, object]:
            self.start_calls += 1
            if self.start_calls == 1:
                return {
                    "mode": "running",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                    "action": "started_runtime_health_pending",
                }
            return {
                "mode": "running",
                "health_status": "degraded",
                "health_reason": "runtime_health_unreachable",
                "action": "restarted_runtime_health_pending",
            }

        def status(self) -> dict[str, object]:
            bucket = self._statuses[min(self.start_calls - 1, len(self._statuses) - 1)]
            if len(bucket) > 1:
                return bucket.pop(0)
            return bucket[0]

        def stop(self) -> dict[str, object]:
            self.stop_calls += 1
            return {"action": "stopped_runtime"}

    monkeypatch.setattr("aionis_workbench.e2e.real_e2e.runtime_env.RuntimeManager", FakeRuntimeManager)
    monkeypatch.setattr("aionis_workbench.e2e.real_e2e.runtime_env._find_free_port", lambda: 39002)

    runtime_env = RealRuntimeEnv(home=Path(tmp_path) / ".aionis-home")

    start_payload = runtime_env.start()

    assert start_payload["mode"] == "running"
    assert start_payload["health_status"] == "available"
    assert runtime_env._manager.start_calls == 2
    assert runtime_env._manager.stop_calls == 1
