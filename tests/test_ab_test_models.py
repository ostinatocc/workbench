from __future__ import annotations

from aionis_workbench.ab_test_models import (
    BenchmarkComparison,
    BenchmarkRun,
    BenchmarkScenarioResult,
)


def test_benchmark_scenario_result_requires_scenario_and_arm() -> None:
    assert BenchmarkScenarioResult.from_dict({"scenario_id": "scenario-1"}) is None

    result = BenchmarkScenarioResult.from_dict(
        {
            "scenario_id": "scenario-1",
            "arm": "aionis",
            "provider_id": "zai_glm51_coding",
            "model": "glm-5.1",
            "ended_in": "advance",
            "total_duration_seconds": 142.5,
            "retry_count": 1,
            "replan_depth": 2,
            "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            "final_execution_gate": "ready",
            "gate_flow": "needs_qa->ready@qa:passed",
            "policy_stage": "second_replan",
            "advance_reached": True,
            "escalated": False,
            "notes": ["Reached sprint-2 after second-cycle replan."],
        }
    )

    assert result is not None
    assert result.arm == "aionis"
    assert result.replan_depth == 2
    assert result.advance_reached is True


def test_benchmark_comparison_round_trips_nested_results() -> None:
    comparison = BenchmarkComparison.from_dict(
        {
            "scenario_id": "scenario-1",
            "baseline": {
                "scenario_id": "scenario-1",
                "arm": "baseline",
                "ended_in": "escalate",
                "retry_count": 1,
                "replan_depth": 0,
                "escalated": True,
            },
            "aionis": {
                "scenario_id": "scenario-1",
                "arm": "aionis",
                "ended_in": "advance",
                "retry_count": 1,
                "replan_depth": 2,
                "advance_reached": True,
            },
            "duration_delta_seconds": -31.7,
            "retry_delta": 0,
            "replan_delta": 2,
            "convergence_delta": "aionis reached ready@qa:passed after second replan",
            "winner": "aionis",
            "summary": "Aionis converged; baseline escalated.",
        }
    )

    assert comparison is not None
    assert BenchmarkComparison.from_dict(comparison.to_dict()) == comparison


def test_benchmark_run_round_trips_results_and_comparisons() -> None:
    run = BenchmarkRun.from_dict(
        {
            "benchmark_id": "ab-2026-04-05-1",
            "scenario_family": "persistence_and_hydration",
            "provider_id": "zai_glm51_coding",
            "model": "glm-5.1",
            "results": [
                {
                    "scenario_id": "scenario-1",
                    "arm": "baseline",
                    "ended_in": "escalate",
                },
                {
                    "scenario_id": "scenario-1",
                    "arm": "aionis",
                    "ended_in": "advance",
                    "advance_reached": True,
                },
            ],
            "comparisons": [
                {
                    "scenario_id": "scenario-1",
                    "baseline": {
                        "scenario_id": "scenario-1",
                        "arm": "baseline",
                        "ended_in": "escalate",
                    },
                    "aionis": {
                        "scenario_id": "scenario-1",
                        "arm": "aionis",
                        "ended_in": "advance",
                    },
                    "winner": "aionis",
                }
            ],
        }
    )

    assert run is not None
    assert len(run.results) == 2
    assert len(run.comparisons) == 1
    assert BenchmarkRun.from_dict(run.to_dict()) == run
