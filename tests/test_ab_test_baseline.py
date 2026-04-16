from __future__ import annotations

from aionis_workbench.ab_test_baseline import normalize_baseline_result


def test_normalize_baseline_result_infers_advance_shape() -> None:
    result = normalize_baseline_result(
        scenario_id="scenario-1",
        provider_id="zai_glm51_coding",
        model="glm-5.1",
        thin_loop_result={
            "advance_reached": True,
            "total_duration_seconds": 98.2,
            "retry_count": 1,
            "notes": ["Thin loop reached the follow-up sprint."],
        },
    )

    assert result.arm == "baseline"
    assert result.ended_in == "advance"
    assert result.final_execution_gate == "ready"
    assert result.gate_flow == "needs_qa->ready@qa:passed"


def test_normalize_baseline_result_preserves_explicit_failure_shape() -> None:
    result = normalize_baseline_result(
        scenario_id="scenario-2",
        provider_id="openrouter_default",
        model="openai/gpt-5.4",
        thin_loop_result={
            "ended_in": "escalate",
            "escalated": True,
            "retry_count": 1,
            "gate_flow": "needs_qa->qa_failed@qa:failed",
            "latest_convergence_signal": "baseline:needs_qa->qa_failed@qa:failed",
        },
    )

    assert result.ended_in == "escalate"
    assert result.escalated is True
    assert result.latest_convergence_signal == "baseline:needs_qa->qa_failed@qa:failed"
    assert result.replan_depth == 0
