from __future__ import annotations

from aionis_workbench.ab_test_runner import benchmark_result_from_aionis_payload


def test_benchmark_result_from_aionis_payload_extracts_compact_summary() -> None:
    result = benchmark_result_from_aionis_payload(
        scenario_id="scenario-1",
        payload={
            "canonical_views": {
                "app_harness": {
                    "retry_count": 1,
                    "replan_depth": 2,
                    "execution_gate": "ready",
                    "last_execution_gate_transition": "needs_qa->ready",
                    "policy_stage": "second_replan",
                    "next_sprint_ready": True,
                    "recommended_next_action": "advance_to_next_sprint",
                    "latest_sprint_evaluation": {
                        "summary": "Second replanned sprint passed QA.",
                    },
                    "latest_execution_attempt": {
                        "execution_summary": "Apply the second bounded persistence patch.",
                    },
                }
            },
            "live_profile": {
                "provider_id": "zai_glm51_coding",
                "model": "glm-5.1",
                "latest_total_duration_seconds": 381.92,
                "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            },
        },
    )

    assert result.arm == "aionis"
    assert result.provider_id == "zai_glm51_coding"
    assert result.ended_in == "advance"
    assert result.replan_depth == 2
    assert result.advance_reached is True
    assert result.notes[:2] == [
        "Second replanned sprint passed QA.",
        "Apply the second bounded persistence patch.",
    ]


def test_benchmark_result_from_aionis_payload_marks_escalation_when_loop_is_terminal() -> None:
    result = benchmark_result_from_aionis_payload(
        scenario_id="scenario-2",
        payload={
            "provider_id": "zai_glm51_coding",
            "model": "glm-5.1",
            "canonical_views": {
                "app_harness": {
                    "loop_status": "escalated",
                    "retry_count": 1,
                    "replan_depth": 1,
                    "execution_gate": "qa_failed",
                    "last_execution_gate_transition": "needs_qa->qa_failed",
                    "policy_stage": "replanned",
                    "next_sprint_ready": False,
                    "recommended_next_action": "replan_or_escalate",
                }
            },
            "latest_convergence_signal": "live-app-escalate:needs_qa->qa_failed@qa:failed",
        },
    )

    assert result.ended_in == "escalate"
    assert result.escalated is True
    assert result.final_execution_gate == "qa_failed"
    assert result.latest_convergence_signal == "live-app-escalate:needs_qa->qa_failed@qa:failed"


def test_benchmark_result_from_aionis_payload_keeps_advance_after_policy_transition() -> None:
    result = benchmark_result_from_aionis_payload(
        scenario_id="scenario-3",
        payload={
            "provider_id": "zai_glm51_coding",
            "model": "glm-5.1",
            "canonical_views": {
                "app_harness": {
                    "loop_status": "in_sprint",
                    "retry_count": 1,
                    "replan_depth": 1,
                    "execution_gate": "no_execution",
                    "last_execution_gate_transition": "ready->no_execution",
                    "policy_stage": "base",
                    "next_sprint_ready": False,
                    "recommended_next_action": "run_current_sprint",
                    "last_policy_action": "advance",
                }
            },
            "latest_convergence_signal": "live-app-replan-generate-qa-advance:ready->no_execution@advance",
        },
    )

    assert result.ended_in == "advance"
    assert result.advance_reached is True
    assert result.final_execution_gate == "no_execution"
