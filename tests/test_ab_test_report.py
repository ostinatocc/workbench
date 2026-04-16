from __future__ import annotations

from aionis_workbench.ab_test_models import BenchmarkRun, BenchmarkScenarioResult
from aionis_workbench.ab_test_report import (
    build_benchmark_comparison,
    render_benchmark_run_markdown,
    render_comparison_summary,
)


def test_build_benchmark_comparison_prefers_aionis_when_it_advances_and_baseline_escalates() -> None:
    baseline = BenchmarkScenarioResult(
        scenario_id="scenario-1",
        arm="baseline",
        ended_in="escalate",
        total_duration_seconds=120.0,
        retry_count=1,
        replan_depth=0,
        latest_convergence_signal="baseline:needs_qa->qa_failed@qa:failed",
        final_execution_gate="qa_failed",
        gate_flow="needs_qa->qa_failed@qa:failed",
        policy_stage="thin_loop",
        advance_reached=False,
        escalated=True,
    )
    aionis = BenchmarkScenarioResult(
        scenario_id="scenario-1",
        arm="aionis",
        ended_in="advance",
        total_duration_seconds=150.0,
        retry_count=1,
        replan_depth=1,
        latest_convergence_signal="aionis:needs_qa->ready@qa:passed",
        final_execution_gate="ready",
        gate_flow="needs_qa->ready@qa:passed",
        policy_stage="replanned",
        advance_reached=True,
        escalated=False,
    )

    comparison = build_benchmark_comparison(
        scenario_id="scenario-1",
        baseline=baseline,
        aionis=aionis,
    )

    assert comparison.winner == "aionis"
    assert comparison.retry_delta == 0
    assert comparison.replan_delta == 1
    assert comparison.duration_delta_seconds == 30.0
    assert "baseline=baseline:needs_qa->qa_failed@qa:failed" in comparison.convergence_delta
    assert comparison.summary == "Aionis converged to advance; baseline escalated before reaching the next sprint."


def test_render_comparison_summary_handles_tie() -> None:
    baseline = BenchmarkScenarioResult(
        scenario_id="scenario-2",
        arm="baseline",
        ended_in="stalled",
        total_duration_seconds=100.0,
    )
    aionis = BenchmarkScenarioResult(
        scenario_id="scenario-2",
        arm="aionis",
        ended_in="stalled",
        total_duration_seconds=100.0,
    )
    comparison = build_benchmark_comparison(
        scenario_id="scenario-2",
        baseline=baseline,
        aionis=aionis,
    )

    assert comparison.winner == "tie"
    assert render_comparison_summary(comparison) == "Both arms finished with comparable endings in this scenario."


def test_render_benchmark_run_markdown_includes_table_and_conclusions() -> None:
    comparison = build_benchmark_comparison(
        scenario_id="persistence-and-hydration",
        baseline=BenchmarkScenarioResult(
            scenario_id="persistence-and-hydration",
            arm="baseline",
            ended_in="escalate",
            total_duration_seconds=120.0,
            retry_count=1,
            latest_convergence_signal="baseline:needs_qa->qa_failed@qa:failed",
            final_execution_gate="qa_failed",
            gate_flow="needs_qa->qa_failed@qa:failed",
            escalated=True,
        ),
        aionis=BenchmarkScenarioResult(
            scenario_id="persistence-and-hydration",
            arm="aionis",
            ended_in="advance",
            total_duration_seconds=150.0,
            retry_count=1,
            replan_depth=1,
            latest_convergence_signal="live-app-retry-compare:needs_qa->ready@qa:passed",
            final_execution_gate="ready",
            gate_flow="needs_qa->ready@qa:passed",
            policy_stage="replanned",
            advance_reached=True,
        ),
    )
    run = BenchmarkRun(
        benchmark_id="ab-phase-1",
        scenario_family="app-harness",
        provider_id="zai_glm51_coding",
        model="glm-5.1",
        comparisons=[comparison],
    )

    markdown = render_benchmark_run_markdown(run)

    assert "# Benchmark Run: ab-phase-1" in markdown
    assert "| Scenario | Winner | Baseline | Aionis | Duration Δ (s) | Retry Δ | Replan Δ | Convergence |" in markdown
    assert "| persistence-and-hydration | aionis | escalate | advance | 30.00 | 0 | 1 |" in markdown
    assert "## Conclusions" in markdown
    assert "`persistence-and-hydration`: Aionis converged to advance; baseline escalated before reaching the next sprint." in markdown
