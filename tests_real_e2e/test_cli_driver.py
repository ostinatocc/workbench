from __future__ import annotations

from pathlib import Path

from aionis_workbench.e2e.real_e2e.cli_driver import run_aionis


def test_run_aionis_status() -> None:
    result = run_aionis(["status"])

    assert result.exit_code == 0
    assert "launcher-status:" in result.stdout


def test_run_aionis_captures_stdout_stderr_and_exit_code() -> None:
    result = run_aionis(["status"])

    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)
    assert isinstance(result.exit_code, int)


def test_run_aionis_targets_specific_cwd(tmp_path: Path) -> None:
    result = run_aionis(["status"], cwd=tmp_path)

    assert result.exit_code == 0
    assert Path(result.cwd) == tmp_path
