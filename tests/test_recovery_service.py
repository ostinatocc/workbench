from __future__ import annotations

import json
from pathlib import Path

from aionis_workbench.execution_packet import ExecutionPacket
from aionis_workbench.recovery_service import RecoveryService, ValidationResult
from aionis_workbench.session import ArtifactReference, SessionState


def _make_service(
    tmp_path: Path,
    *,
    observed_files: list[str] | None = None,
) -> RecoveryService:
    return RecoveryService(
        repo_root=str(tmp_path),
        trace_summary_fn=lambda _steps: {"steps_observed": 0},
        extract_target_files_fn=lambda *_args, **_kwargs: observed_files or [],
        run_validation_commands_fn=lambda _commands: ValidationResult(
            ok=True,
            command="pytest -q",
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=[],
        ),
        model_timeout_type=TimeoutError,
    )


def _make_session(tmp_path: Path) -> SessionState:
    return SessionState(
        task_id="recovery-task",
        goal="Fix validation failure",
        repo_root=str(tmp_path),
        project_identity="aionis-test",
        project_scope="project:test/recovery",
        target_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["pytest tests/test_demo.py -q"],
    )


def _write_artifact(tmp_path: Path, *, task_id: str, name: str, payload: dict[str, object]) -> str:
    artifact_dir = tmp_path / ".aionis-workbench" / "artifacts" / task_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / name
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    return str(artifact_path.relative_to(tmp_path))


def test_apply_validation_feedback_marks_successful_sessions_validated(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    session = _make_session(tmp_path)
    validation = ValidationResult(
        ok=True,
        command="pytest tests/test_demo.py -q",
        exit_code=0,
        summary="Validation commands passed.",
        output="",
        changed_files=["src/demo.py"],
    )

    service.apply_validation_feedback(session, validation)

    assert session.status == "validated"
    assert session.last_validation_result["ok"] is True
    assert "Validation passed: pytest tests/test_demo.py -q" in session.promoted_insights
    assert session.working_memory[0] == "Validation commands passed."


def test_apply_validation_feedback_marks_failed_sessions_needs_attention(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    session = _make_session(tmp_path)
    validation = ValidationResult(
        ok=False,
        command="pytest tests/test_demo.py -q",
        exit_code=1,
        summary="Test failure remains.",
        output="E assert 1 == 2",
        changed_files=["src/demo.py"],
    )

    service.apply_validation_feedback(session, validation)

    assert session.status == "needs_attention"
    assert session.last_validation_result["ok"] is False
    assert session.working_memory[0] == "Validation failed command: pytest tests/test_demo.py -q"
    assert "Test failure remains." in session.working_memory
    assert "Validation signal: E assert 1 == 2" in session.working_memory


def test_build_correction_packet_uses_latest_validation_failure(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    session = _make_session(tmp_path)
    session.last_trace_summary = {"steps_observed": 4}
    session.last_validation_result = {
        "ok": False,
        "command": "pytest tests/test_demo.py -q",
        "summary": "Validation failed.",
        "output": "FAILED tests/test_demo.py::test_example - AssertionError: expected 2",
        "changed_files": ["src/demo.py"],
    }

    packet = service.build_correction_packet(session)

    assert packet is not None
    assert packet["kind"] == "correction_packet_artifact"
    assert packet["command"] == "pytest tests/test_demo.py -q"
    assert packet["failure_name"] == "tests/test_demo.py::test_example"
    assert packet["working_set"] == ["src/demo.py"]
    assert "Primary failing test: tests/test_demo.py::test_example." in packet["summary"]


def test_apply_narrow_scope_guard_blocks_scope_drift(tmp_path: Path) -> None:
    observed_files = ["src/demo.py", "src/unexpected.py"]
    service = _make_service(tmp_path, observed_files=observed_files)
    session = _make_session(tmp_path)
    correction_path = _write_artifact(
        tmp_path,
        task_id=session.task_id,
        name="correction.json",
        payload={
            "kind": "correction_packet_artifact",
            "working_set": ["src/demo.py"],
        },
    )
    session.artifacts.append(
        ArtifactReference(
            artifact_id=f"{session.task_id}:correction",
            kind="correction_packet_artifact",
            role="orchestrator",
            summary="Correction packet",
            path=correction_path,
            metadata={},
        )
    )
    validation = ValidationResult(
        ok=True,
        command="pytest tests/test_demo.py -q",
        exit_code=0,
        summary="Validation commands passed.",
        output="",
        changed_files=["src/demo.py"],
    )

    guarded = service.apply_narrow_scope_guard(session=session, trace_steps=[], validation=validation)

    assert guarded.ok is False
    assert guarded.summary == "Scope drift detected: touched files outside the correction packet working set."
    assert "Observed out-of-scope files: src/unexpected.py" in guarded.output
    assert guarded.changed_files == ["src/demo.py", "src/unexpected.py"]


def test_apply_regression_expansion_guard_detects_new_failures(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    session = _make_session(tmp_path)
    session.execution_packet = ExecutionPacket(
        accepted_facts=["Baseline failing test is tests/test_demo.py::test_example"]
    )
    validation = ValidationResult(
        ok=False,
        command="pytest tests/test_demo.py -q",
        exit_code=1,
        summary="Tests still failing.",
        output="\n".join(
            [
                "FAILED tests/test_demo.py::test_example - AssertionError: expected 2",
                "FAILED tests/test_demo.py::test_regression - AssertionError: expected 3",
            ]
        ),
        changed_files=["src/demo.py"],
    )

    guarded = service.apply_regression_expansion_guard(session=session, validation=validation)

    assert guarded.ok is False
    assert guarded.summary == "Regression expansion detected: the failing set broadened beyond the baseline correction target."
    assert "Baseline failing test: tests/test_demo.py::test_example" in guarded.output
    assert "tests/test_demo.py::test_regression" in guarded.output
