from __future__ import annotations

from types import SimpleNamespace

from aionis_workbench.runtime_manager import RuntimeManager


def test_runtime_manager_reports_missing_runtime_command(tmp_path) -> None:
    manager = RuntimeManager(workspace_root=tmp_path, home=tmp_path)

    status = manager.status()

    assert status["mode"] == "missing"
    assert status["health_status"] == "offline"
    assert status["health_reason"] == "runtime_workspace_missing"


def test_runtime_manager_reports_stopped_when_runtime_exists_but_is_unhealthy(
    tmp_path, monkeypatch
) -> None:
    runtime_root = tmp_path / "runtime-mainline"
    runtime_root.mkdir()
    (runtime_root / "package.json").write_text("{}")

    monkeypatch.setattr(
        "aionis_workbench.runtime_manager._runtime_health_status",
        lambda base_url: ("degraded", "runtime_health_unreachable"),
    )

    manager = RuntimeManager(workspace_root=tmp_path, home=tmp_path)
    status = manager.status()

    assert status["mode"] == "stopped"
    assert status["health_status"] == "degraded"
    assert status["health_reason"] == "runtime_health_unreachable"
    assert status["runtime_root"] == str(runtime_root)


def test_runtime_manager_start_returns_missing_when_runtime_workspace_is_absent(tmp_path) -> None:
    manager = RuntimeManager(workspace_root=tmp_path, home=tmp_path)

    status = manager.start()

    assert status["mode"] == "missing"
    assert status["action"] == "missing_workspace"


def test_runtime_manager_start_waits_for_delayed_runtime_health(tmp_path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime-mainline"
    runtime_root.mkdir()
    (runtime_root / "package.json").write_text("{}")

    health_calls: list[float | None] = []
    health_states = iter(
        [
            ("degraded", "runtime_health_unreachable"),
            ("degraded", "runtime_health_unreachable"),
            ("available", None),
        ]
    )

    def fake_health_status(base_url: str, *, timeout_seconds: float = 2.0):
        health_calls.append(timeout_seconds)
        return next(health_states)

    clock = {"now": 0.0}

    def fake_monotonic() -> float:
        clock["now"] += 0.5
        return clock["now"]

    monkeypatch.setattr("aionis_workbench.runtime_manager._runtime_health_status", fake_health_status)
    monkeypatch.setattr(
        "aionis_workbench.runtime_manager._candidate_runtime_base_urls",
        lambda: ["http://127.0.0.1:4101"],
    )
    monkeypatch.setattr(
        "aionis_workbench.runtime_manager._default_runtime_base_url",
        lambda: "http://127.0.0.1:4101",
    )
    monkeypatch.setattr("aionis_workbench.runtime_manager.shutil.which", lambda executable: "/usr/bin/npm")
    monkeypatch.setattr(
        "aionis_workbench.runtime_manager.subprocess.Popen",
        lambda *args, **kwargs: SimpleNamespace(pid=4321, poll=lambda: None),
    )
    monkeypatch.setattr("aionis_workbench.runtime_manager.time.sleep", lambda seconds: None)
    monkeypatch.setattr("aionis_workbench.runtime_manager.time.monotonic", fake_monotonic)

    manager = RuntimeManager(workspace_root=tmp_path, home=tmp_path)
    status = manager.start()

    assert status["mode"] == "running"
    assert status["health_status"] == "available"
    assert status["action"] == "started_runtime"
    assert health_calls[0] == 2.0
    assert health_calls[1:] == [5.0, 5.0]


def test_runtime_manager_resolves_sibling_aionis_core_checkout(tmp_path) -> None:
    workbench_root = tmp_path / "workbench"
    workbench_root.mkdir()
    runtime_root = tmp_path / "AionisCore"
    runtime_root.mkdir()
    (runtime_root / "package.json").write_text("{}")

    manager = RuntimeManager(workspace_root=workbench_root, home=tmp_path)

    assert manager._runtime_root == runtime_root
