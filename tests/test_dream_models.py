from __future__ import annotations

from aionis_workbench.dream_models import CandidateVerification, DreamSample, PromotedPrior, StrategyCandidate


def test_strategy_candidate_defaults_to_candidate_status() -> None:
    candidate = StrategyCandidate(
        candidate_id="cand-1",
        task_family="task:demo",
        strategy_profile="family_reuse_loop",
        validation_style="targeted_first",
        dominant_validation_command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        dominant_working_set=["src/demo.py", "tests/test_demo.py"],
    )

    assert candidate.status == "candidate"
    assert candidate.sample_count == 0


def test_dream_models_round_trip_dict_payloads() -> None:
    sample = DreamSample(
        task_id="demo-1",
        task_family="task:demo",
        strategy_profile="family_reuse_loop",
        validation_style="targeted_first",
        validation_command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        working_set=["src/demo.py", "tests/test_demo.py"],
        event_source="vscode_extension",
        recorded_at="2026-04-03T12:00:00Z",
    )
    verification = CandidateVerification(
        candidate_id="cand-1",
        task_family="task:demo",
        verification_status="passed",
        heldout_match_rate=1.0,
    )
    prior = PromotedPrior(
        prior_id="prior-1",
        task_family="task:demo",
        strategy_profile="family_reuse_loop",
        validation_style="targeted_first",
        dominant_validation_command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        dominant_working_set=["src/demo.py", "tests/test_demo.py"],
        promotion_status="seed_ready",
        confidence=0.82,
        dominant_event_source="vscode_extension",
        latest_recorded_at="2026-04-03T12:00:00Z",
        editor_sync_count=2,
    )

    assert DreamSample.from_dict(sample.to_dict()) == sample
    assert CandidateVerification.from_dict(verification.to_dict()) == verification
    assert PromotedPrior.from_dict(prior.to_dict()) == prior
