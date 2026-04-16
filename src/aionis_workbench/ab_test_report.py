from __future__ import annotations

from .ab_test_models import BenchmarkComparison, BenchmarkRun, BenchmarkScenarioResult


def _winner(baseline: BenchmarkScenarioResult, aionis: BenchmarkScenarioResult) -> str:
    if aionis.advance_reached and not baseline.advance_reached:
        return "aionis"
    if baseline.advance_reached and not aionis.advance_reached:
        return "baseline"
    if aionis.escalated and not baseline.escalated:
        return "baseline"
    if baseline.escalated and not aionis.escalated:
        return "aionis"
    if aionis.replan_depth < baseline.replan_depth:
        return "aionis"
    if baseline.replan_depth < aionis.replan_depth:
        return "baseline"
    if aionis.total_duration_seconds < baseline.total_duration_seconds:
        return "aionis"
    if baseline.total_duration_seconds < aionis.total_duration_seconds:
        return "baseline"
    return "tie"


def _convergence_delta(baseline: BenchmarkScenarioResult, aionis: BenchmarkScenarioResult) -> str:
    baseline_signal = baseline.latest_convergence_signal or "none"
    aionis_signal = aionis.latest_convergence_signal or "none"
    if baseline_signal == aionis_signal:
        return baseline_signal
    return f"baseline={baseline_signal} | aionis={aionis_signal}"


def render_comparison_summary(comparison: BenchmarkComparison) -> str:
    if comparison.winner == "aionis":
        if comparison.aionis.advance_reached and comparison.baseline.escalated:
            return "Aionis converged to advance; baseline escalated before reaching the next sprint."
        if comparison.aionis.advance_reached and not comparison.baseline.advance_reached:
            return "Aionis reached the next sprint while the baseline arm did not."
        return "Aionis finished with the stronger long-loop ending."
    if comparison.winner == "baseline":
        return "The baseline arm finished with the stronger ending in this scenario."
    return "Both arms finished with comparable endings in this scenario."


def build_benchmark_comparison(
    *,
    scenario_id: str,
    baseline: BenchmarkScenarioResult,
    aionis: BenchmarkScenarioResult,
) -> BenchmarkComparison:
    comparison = BenchmarkComparison(
        scenario_id=scenario_id,
        baseline=baseline,
        aionis=aionis,
        duration_delta_seconds=aionis.total_duration_seconds - baseline.total_duration_seconds,
        retry_delta=aionis.retry_count - baseline.retry_count,
        replan_delta=aionis.replan_depth - baseline.replan_depth,
        convergence_delta=_convergence_delta(baseline, aionis),
        winner=_winner(baseline, aionis),
    )
    comparison.summary = render_comparison_summary(comparison)
    return comparison


def render_benchmark_run_markdown(run: BenchmarkRun) -> str:
    lines = [
        f"# Benchmark Run: {run.benchmark_id}",
        "",
    ]
    if run.scenario_family:
        lines.append(f"- scenario family: `{run.scenario_family}`")
    if run.provider_id:
        lines.append(f"- provider: `{run.provider_id}`")
    if run.model:
        lines.append(f"- model: `{run.model}`")
    if len(lines) > 2:
        lines.append("")

    lines.extend(
        [
            "| Scenario | Winner | Baseline | Aionis | Duration Δ (s) | Retry Δ | Replan Δ | Convergence |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for comparison in run.comparisons:
        lines.append(
            "| {scenario} | {winner} | {baseline} | {aionis} | {duration:.2f} | {retry} | {replan} | {convergence} |".format(
                scenario=comparison.scenario_id,
                winner=comparison.winner or "tie",
                baseline=comparison.baseline.ended_in or "unknown",
                aionis=comparison.aionis.ended_in or "unknown",
                duration=comparison.duration_delta_seconds,
                retry=comparison.retry_delta,
                replan=comparison.replan_delta,
                convergence=comparison.convergence_delta or "none",
            )
        )

    if run.comparisons:
        lines.extend(["", "## Conclusions", ""])
        for comparison in run.comparisons:
            lines.append(f"- `{comparison.scenario_id}`: {comparison.summary}")

    return "\n".join(lines).rstrip() + "\n"
