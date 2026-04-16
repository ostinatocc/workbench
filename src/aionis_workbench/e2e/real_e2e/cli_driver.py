from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AionisCliRunResult:
    command: tuple[str, ...]
    cwd: str
    stdout: str
    stderr: str
    exit_code: int


def _workbench_root() -> Path:
    return Path(__file__).resolve().parents[4]


def aionis_binary_path() -> Path:
    return _workbench_root() / ".venv" / "bin" / "aionis"


def run_aionis(
    args: list[str],
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> AionisCliRunResult:
    command = [str(aionis_binary_path()), *args]
    run_cwd = Path(cwd) if cwd is not None else _workbench_root()
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        command,
        cwd=run_cwd,
        env=run_env,
        capture_output=True,
        text=True,
    )
    return AionisCliRunResult(
        command=tuple(command),
        cwd=str(run_cwd),
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )
