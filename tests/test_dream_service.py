from __future__ import annotations

from test_bootstrap import _seed_python_repo

from aionis_workbench.recovery_service import ValidationResult
from aionis_workbench.runtime import AionisWorkbench
from aionis_workbench.dream_state import load_dream_candidates, load_dream_promotions


def test_extract_samples_reads_successful_session_learning(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="dream-sample-1",
        task="Keep the current demo loop healthy.",
        target_files=["src/demo.py", "tests/test_demo.py"],
        validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        apply_strategy=False,
    )
    session.selected_task_family = "task:demo"
    session.selected_strategy_profile = "family_reuse_loop"
    session.selected_validation_style = "targeted_first"
    session.selected_role_sequence = ["investigator", "implementer", "verifier"]
    validation = ValidationResult(
        ok=True,
        command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        exit_code=0,
        summary="Validation commands passed.",
        output="",
        changed_files=["tests/test_demo.py", "src/demo.py"],
    )

    workbench._record_auto_learning(session=session, source="validate", validation=validation)
    workbench._apply_validation_feedback(session, validation)
    session.continuity_snapshot = dict(session.continuity_snapshot or {})
    session.continuity_snapshot["doc_workflow"] = {
        "latest_action": "resume",
        "status": "completed",
        "doc_input": "flows/demo-workflow.aionis.md",
        "source_doc_id": "demo-workflow-1",
        "handoff_anchor": "dream-doc-anchor",
        "selected_tool": "read",
        "event_source": "vscode_extension",
        "recorded_at": "2026-04-03T12:00:00Z",
        "history": [{"action": "resume", "status": "completed", "doc_input": "flows/demo-workflow.aionis.md"}],
    }
    workbench._save_session(session)

    samples = workbench._surface._dream.extract_samples(limit=12)

    assert samples[0].task_id == "dream-sample-1"
    assert samples[0].task_family == "task:demo"
    assert samples[0].strategy_profile == "family_reuse_loop"
    assert samples[0].validation_style == "targeted_first"
    assert samples[0].validation_command == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
    assert samples[0].working_set[:2] == ["tests/test_demo.py", "src/demo.py"]
    assert samples[0].observed_changed_files == ["tests/test_demo.py", "src/demo.py"]
    assert samples[0].source == "validate"
    assert samples[0].doc_input == "flows/demo-workflow.aionis.md"
    assert samples[0].source_doc_id == "demo-workflow-1"
    assert samples[0].doc_action == "resume"
    assert samples[0].selected_tool == "read"
    assert samples[0].event_source == "vscode_extension"
    assert samples[0].recorded_at == "2026-04-03T12:00:00Z"


def test_extract_samples_skips_sessions_without_learning_snapshot(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    session = workbench._initial_session(
        task_id="dream-sample-2",
        task="Inspect a repo without learning.",
        target_files=["src/demo.py"],
        validation_commands=[],
        apply_strategy=False,
    )
    workbench._save_session(session)

    samples = workbench._surface._dream.extract_samples(limit=12)

    assert samples == []


def test_distill_candidates_groups_samples_by_family_and_strategy() -> None:
    workbench_samples = [
        workbench_sample("demo-1"),
        workbench_sample("demo-2"),
        workbench_sample("demo-3", source="manual_ingest"),
    ]
    from aionis_workbench.dream_service import DreamService

    service = DreamService(repo_root="/tmp/repo", project_scope="project:test/demo")
    candidates = service.distill_candidates(workbench_samples)

    assert candidates[0].task_family == "task:demo"
    assert candidates[0].strategy_profile == "family_reuse_loop"
    assert candidates[0].validation_style == "targeted_first"
    assert candidates[0].sample_count == 3
    assert candidates[0].recent_success_count == 3
    assert candidates[0].dominant_working_set == ["src/demo.py", "tests/test_demo.py"]
    assert candidates[0].avg_artifact_hit_rate == 0.8
    assert candidates[0].avg_pattern_hit_count == 2.0
    assert candidates[0].source_weight > 0.7
    assert candidates[0].dominant_source_doc_id == "demo-workflow-1"
    assert candidates[0].dominant_doc_input == "flows/demo-workflow.aionis.md"
    assert candidates[0].dominant_doc_action == "resume"
    assert candidates[0].dominant_selected_tool == "read"
    assert candidates[0].dominant_event_source == "vscode_extension"
    assert candidates[0].latest_recorded_at == "2026-04-03T12:00:00Z"
    assert candidates[0].doc_sample_count == 3
    assert candidates[0].editor_sync_count == 3
    assert candidates[0].dominant_reviewer_standard == "strict_review"
    assert candidates[0].dominant_reviewer_outputs == ["patch", "tests"]
    assert candidates[0].dominant_reviewer_checks == ["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"]
    assert candidates[0].dominant_reviewer_pack_source == "continuity"
    assert candidates[0].dominant_reviewer_selected_tool == "read"
    assert candidates[0].dominant_reviewer_resume_anchor == "resume:src/demo.py"
    assert candidates[0].reviewer_sample_count == 3
    assert candidates[0].reviewer_ready_count == 3


def test_verify_candidate_marks_seed_ready_when_heldout_checks_pass() -> None:
    from aionis_workbench.dream_service import DreamService

    service = DreamService(repo_root="/tmp/repo", project_scope="project:test/demo")
    candidate = service.distill_candidates(
        [
            workbench_sample("demo-1"),
            workbench_sample("demo-2"),
            workbench_sample("demo-3", source="manual_ingest"),
        ]
    )[0]

    verification = service.verify_candidate(
        candidate,
        [
            workbench_sample("demo-4"),
            workbench_sample("demo-5"),
        ],
    )

    assert verification.verification_status == "passed"
    assert verification.coverage_count == 3
    assert verification.heldout_count == 2
    assert verification.heldout_match_rate >= 0.67
    assert verification.regression_risk <= 0.2


def test_promote_candidates_marks_only_verified_candidates_seed_ready() -> None:
    from aionis_workbench.dream_service import DreamService

    service = DreamService(repo_root="/tmp/repo", project_scope="project:test/demo")
    candidate = service.distill_candidates(
        [
            workbench_sample("demo-1"),
            workbench_sample("demo-2"),
            workbench_sample("demo-3", source="manual_ingest"),
        ]
    )[0]
    verification = service.verify_candidate(candidate, [workbench_sample("demo-4")])

    promotions = service.promote_candidates([candidate], [verification])

    assert promotions[0].promotion_status == "seed_ready"
    assert promotions[0].task_family == "task:demo"
    assert promotions[0].strategy_profile == "family_reuse_loop"
    assert promotions[0].confidence >= 0.6
    assert "passed held-out verification" in promotions[0].promotion_reason
    assert promotions[0].dominant_source_doc_id == "demo-workflow-1"
    assert promotions[0].dominant_doc_input == "flows/demo-workflow.aionis.md"
    assert promotions[0].dominant_doc_action == "resume"
    assert promotions[0].dominant_selected_tool == "read"
    assert promotions[0].dominant_event_source == "vscode_extension"
    assert promotions[0].editor_sync_count >= 1
    assert promotions[0].dominant_reviewer_standard == "strict_review"
    assert promotions[0].dominant_reviewer_pack_source == "continuity"
    assert promotions[0].reviewer_sample_count >= 1
    assert promotions[0].reviewer_ready_count >= 1


def test_promote_candidates_leaves_underverified_candidate_in_trial() -> None:
    from aionis_workbench.dream_service import DreamService

    service = DreamService(repo_root="/tmp/repo", project_scope="project:test/demo")
    candidate = service.distill_candidates(
        [
            workbench_sample("demo-1"),
            workbench_sample("demo-2"),
        ]
    )[0]
    verification = service.verify_candidate(candidate, [])

    promotions = service.promote_candidates([candidate], [verification])

    assert promotions[0].promotion_status == "trial"
    assert "enter trial" in promotions[0].promotion_reason


def test_distill_candidates_keeps_incompatible_reviewer_contracts_separate() -> None:
    from aionis_workbench.dream_service import DreamService

    service = DreamService(repo_root="/tmp/repo", project_scope="project:test/demo")
    candidates = service.distill_candidates(
        [
            workbench_sample("demo-1", event_source="vscode_extension"),
            workbench_sample(
                "demo-2",
                event_source="cursor_extension",
                selected_tool="edit",
                doc_action="publish",
                reviewer_standard="gated_review",
                reviewer_required_outputs=["patch"],
                reviewer_acceptance_checks=["pytest gated -q"],
                reviewer_pack_source="evolution",
            ),
            workbench_sample(
                "demo-3",
                event_source="cursor_extension",
                selected_tool="edit",
                doc_action="publish",
                reviewer_standard="gated_review",
                reviewer_required_outputs=["patch"],
                reviewer_acceptance_checks=["pytest gated -q"],
                reviewer_pack_source="evolution",
            ),
        ]
    )

    strict_read = next(
        item
        for item in candidates
        if item.dominant_reviewer_standard == "strict_review"
        and item.dominant_reviewer_pack_source == "continuity"
    )
    gated_edit = next(
        item
        for item in candidates
        if item.dominant_reviewer_standard == "gated_review"
    )

    assert strict_read.sample_count == 1
    assert gated_edit.sample_count == 2
    assert len(candidates) >= 2


def test_repeatedly_evicted_guidance_degrades_prior_status() -> None:
    from aionis_workbench.dream_service import DreamService

    service = DreamService(repo_root="/tmp/repo", project_scope="project:test/demo")
    candidate = service.distill_candidates(
        [
            workbench_sample("demo-1", evicted=1, stale=1),
            workbench_sample("demo-2", evicted=1, stale=1),
            workbench_sample("demo-3"),
        ]
    )[0]
    verification = service.verify_candidate(candidate, [workbench_sample("demo-4")])

    promotions = service.promote_candidates([candidate], [verification])

    assert promotions[0].promotion_status == "deprecated"
    assert "suppressed or evicted" in promotions[0].promotion_reason


def test_run_cycle_persists_candidates_and_promotions(tmp_path, monkeypatch) -> None:
    _seed_python_repo(tmp_path)
    monkeypatch.setenv("AIONIS_BASE_URL", "http://127.0.0.1:3101")

    workbench = AionisWorkbench(repo_root=str(tmp_path))
    for idx in range(1, 5):
        session = workbench._initial_session(
            task_id=f"dream-cycle-{idx}",
            task="Keep the demo loop narrow and validated.",
            target_files=["src/demo.py", "tests/test_demo.py"],
            validation_commands=["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
            apply_strategy=False,
        )
        session.selected_task_family = "task:demo"
        session.selected_strategy_profile = "family_reuse_loop"
        session.selected_validation_style = "targeted_first"
        validation = ValidationResult(
            ok=True,
            command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
            exit_code=0,
            summary="Validation commands passed.",
            output="",
            changed_files=["tests/test_demo.py", "src/demo.py"],
        )
        workbench._record_auto_learning(session=session, source="validate", validation=validation)
        workbench._apply_validation_feedback(session, validation)
        session.continuity_snapshot = dict(session.continuity_snapshot or {})
        session.continuity_snapshot["doc_workflow"] = {
            "latest_action": "resume",
            "status": "completed",
            "doc_input": "flows/demo-workflow.aionis.md",
            "source_doc_id": "demo-workflow-1",
            "handoff_anchor": "dream-cycle-anchor",
            "selected_tool": "read",
            "history": [{"action": "resume", "status": "completed", "doc_input": "flows/demo-workflow.aionis.md"}],
        }
        workbench._save_session(session)

    payload = workbench._surface._dream.run_cycle(limit=12)
    candidate_state = load_dream_candidates(repo_root=str(tmp_path), project_scope=workbench._config.project_scope)
    promotion_state = load_dream_promotions(repo_root=str(tmp_path), project_scope=workbench._config.project_scope)

    assert payload["summary"]["samples_reviewed"] == 4
    assert payload["summary"]["seed_ready_count"] >= 1
    assert candidate_state["summary"]["candidates_generated"] >= 1
    assert promotion_state["summary"]["promotions_generated"] >= 1
    assert promotion_state["promotions"][0]["promotion_status"] in {"seed_ready", "trial"}
    assert candidate_state["candidates"][0]["dominant_source_doc_id"] == "demo-workflow-1"
    assert promotion_state["promotions"][0]["dominant_source_doc_id"] == "demo-workflow-1"


def workbench_sample(
    task_id: str,
    *,
    source: str = "validate",
    doc_input: str = "flows/demo-workflow.aionis.md",
    source_doc_id: str = "demo-workflow-1",
    doc_action: str = "resume",
    selected_tool: str = "read",
    event_source: str = "vscode_extension",
    recorded_at: str = "2026-04-03T12:00:00Z",
    suppressed: int = 0,
    evicted: int = 0,
    stale: int = 0,
    reviewer_standard: str = "strict_review",
    reviewer_required_outputs: list[str] | None = None,
    reviewer_acceptance_checks: list[str] | None = None,
    reviewer_pack_source: str = "continuity",
    reviewer_ready_required: bool = True,
    reviewer_rollback_required: bool = False,
):
    from aionis_workbench.dream_models import DreamSample

    return DreamSample(
        task_id=task_id,
        project_identity="tests/demo",
        project_scope="project:test/demo",
        task_family="task:demo",
        source=source,
        strategy_profile="family_reuse_loop",
        validation_style="targeted_first",
        validation_command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        working_set=["src/demo.py", "tests/test_demo.py"],
        observed_changed_files=["tests/test_demo.py", "src/demo.py"] if source == "validate" else [],
        artifact_refs=[],
        doc_input=doc_input,
        source_doc_id=source_doc_id,
        doc_action=doc_action,
        handoff_anchor="demo-doc-anchor",
        selected_tool=selected_tool,
        event_source=event_source,
        recorded_at=recorded_at,
        reviewer_standard=reviewer_standard,
        reviewer_required_outputs=reviewer_required_outputs or ["patch", "tests"],
        reviewer_acceptance_checks=reviewer_acceptance_checks or ["PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"],
        reviewer_pack_source=reviewer_pack_source,
        reviewer_selected_tool="read",
        reviewer_resume_anchor="resume:src/demo.py",
        reviewer_ready_required=reviewer_ready_required,
        reviewer_rollback_required=reviewer_rollback_required,
        instrumentation_status="strong_match",
        artifact_hit_rate=0.8,
        pattern_hit_count=2,
        suppressed_forgetting_count=suppressed,
        evicted_forgetting_count=evicted,
        stale_guidance_count=stale,
    )
