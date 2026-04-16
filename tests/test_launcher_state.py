from __future__ import annotations

from aionis_workbench.launcher_state import launcher_paths


def test_launcher_paths_use_home_aionis_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = launcher_paths()

    assert paths.root == tmp_path / ".aionis"
    assert paths.config == tmp_path / ".aionis" / "config.json"
    assert paths.runtime_dir == tmp_path / ".aionis" / "runtime"
    assert paths.runtime_pid == tmp_path / ".aionis" / "runtime" / "pid"
    assert paths.runtime_stdout == tmp_path / ".aionis" / "runtime" / "stdout.log"
    assert paths.runtime_stderr == tmp_path / ".aionis" / "runtime" / "stderr.log"
    assert paths.workbench_dir == tmp_path / ".aionis" / "workbench"
    assert paths.last_repo_root == tmp_path / ".aionis" / "workbench" / "last_repo_root"
    assert paths.live_profile == tmp_path / ".aionis" / "workbench" / "live_profile.json"
