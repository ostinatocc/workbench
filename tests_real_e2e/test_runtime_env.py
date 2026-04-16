from __future__ import annotations

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
