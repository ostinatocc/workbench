from __future__ import annotations

from typing import Any

from .ab_test_models import BenchmarkScenarioResult


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _bool(value: object) -> bool:
    return value is True


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _aionis_ended_in(app_harness: dict[str, Any]) -> str:
    loop_status = _string(app_harness.get("loop_status"))
    recommended_next_action = _string(app_harness.get("recommended_next_action"))
    last_policy_action = _string(app_harness.get("last_policy_action"))
    if last_policy_action == "advance":
        return "advance"
    if _bool(app_harness.get("next_sprint_ready")) or recommended_next_action == "advance_to_next_sprint":
        return "advance"
    if loop_status == "escalated" or recommended_next_action == "replan_or_escalate":
        return "escalate"
    if loop_status in {"sprint_replanned", "negotiation_pending"} or recommended_next_action == "replan_current_sprint":
        return "replan"
    return "stalled"


def benchmark_result_from_aionis_payload(
    *,
    scenario_id: str,
    payload: dict[str, Any],
    provider_id: str = "",
    model: str = "",
) -> BenchmarkScenarioResult:
    canonical_views = payload.get("canonical_views") if isinstance(payload.get("canonical_views"), dict) else {}
    app_harness = canonical_views.get("app_harness") if isinstance(canonical_views.get("app_harness"), dict) else {}
    live_profile = payload.get("live_profile") if isinstance(payload.get("live_profile"), dict) else {}
    effective_provider_id = _string(provider_id) or _string(payload.get("provider_id")) or _string(live_profile.get("provider_id"))
    effective_model = _string(model) or _string(payload.get("model")) or _string(live_profile.get("model"))
    ended_in = _aionis_ended_in(app_harness)
    notes = []
    latest_evaluation = app_harness.get("latest_sprint_evaluation")
    if isinstance(latest_evaluation, dict):
        evaluation_summary = _string(latest_evaluation.get("summary"))
        if evaluation_summary:
            notes.append(evaluation_summary)
    latest_execution_attempt = app_harness.get("latest_execution_attempt")
    if isinstance(latest_execution_attempt, dict):
        execution_summary = _string(latest_execution_attempt.get("execution_summary"))
        if execution_summary:
            notes.append(execution_summary)
    return BenchmarkScenarioResult(
        scenario_id=scenario_id,
        arm="aionis",
        provider_id=effective_provider_id,
        model=effective_model,
        ended_in=ended_in,
        total_duration_seconds=_float(payload.get("latest_total_duration_seconds") or live_profile.get("latest_total_duration_seconds")),
        retry_count=_int(app_harness.get("retry_count")),
        replan_depth=_int(app_harness.get("replan_depth")),
        latest_convergence_signal=_string(payload.get("latest_convergence_signal") or live_profile.get("latest_convergence_signal")),
        final_execution_gate=_string(app_harness.get("execution_gate")),
        gate_flow=_string(app_harness.get("last_execution_gate_transition")),
        policy_stage=_string(app_harness.get("policy_stage")),
        advance_reached=_bool(app_harness.get("next_sprint_ready")) or ended_in == "advance",
        escalated=_bool(app_harness.get("loop_status") == "escalated") or ended_in == "escalate",
        notes=notes + _string_list(payload.get("benchmark_notes")),
    )
