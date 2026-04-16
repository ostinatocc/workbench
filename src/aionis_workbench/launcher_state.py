from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LauncherPaths:
    root: Path
    config: Path
    runtime_dir: Path
    runtime_pid: Path
    runtime_stdout: Path
    runtime_stderr: Path
    workbench_dir: Path
    last_repo_root: Path
    live_profile: Path


def launcher_paths(home: Path | None = None) -> LauncherPaths:
    home_root = Path(home) if home is not None else Path.home()
    root = home_root / ".aionis"
    runtime_dir = root / "runtime"
    workbench_dir = root / "workbench"
    return LauncherPaths(
        root=root,
        config=root / "config.json",
        runtime_dir=runtime_dir,
        runtime_pid=runtime_dir / "pid",
        runtime_stdout=runtime_dir / "stdout.log",
        runtime_stderr=runtime_dir / "stderr.log",
        workbench_dir=workbench_dir,
        last_repo_root=workbench_dir / "last_repo_root",
        live_profile=workbench_dir / "live_profile.json",
    )
