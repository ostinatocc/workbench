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


def _baseline_ended_in(payload: dict[str, Any]) -> str:
    explicit = _string(payload.get("ended_in"))
    if explicit:
        return explicit
    if _bool(payload.get("advance_reached")):
        return "advance"
    if _bool(payload.get("escalated")):
        return "escalate"
    if _bool(payload.get("replanned")):
        return "replan"
    status = _string(payload.get("status"))
    if status in {"advance", "escalate", "replan", "stalled"}:
        return status
    return "stalled"


def normalize_baseline_result(
    *,
    scenario_id: str,
    provider_id: str,
    model: str,
    thin_loop_result: dict[str, Any],
) -> BenchmarkScenarioResult:
    ended_in = _baseline_ended_in(thin_loop_result)
    latest_convergence_signal = _string(thin_loop_result.get("latest_convergence_signal"))
    final_execution_gate = _string(thin_loop_result.get("final_execution_gate"))
    if not final_execution_gate:
        final_execution_gate = "ready" if ended_in == "advance" else "qa_failed" if ended_in == "escalate" else "none"
    gate_flow = _string(thin_loop_result.get("gate_flow"))
    if not gate_flow:
        if ended_in == "advance":
            gate_flow = "needs_qa->ready@qa:passed"
        elif ended_in == "escalate":
            gate_flow = "needs_qa->qa_failed@qa:failed"
        else:
            gate_flow = "no_execution->no_execution@thin_loop"
    return BenchmarkScenarioResult(
        scenario_id=scenario_id,
        arm="baseline",
        provider_id=provider_id,
        model=model,
        ended_in=ended_in,
        total_duration_seconds=_float(thin_loop_result.get("total_duration_seconds")),
        retry_count=_int(thin_loop_result.get("retry_count")),
        replan_depth=0,
        latest_convergence_signal=latest_convergence_signal,
        final_execution_gate=final_execution_gate,
        gate_flow=gate_flow,
        policy_stage="thin_loop",
        advance_reached=_bool(thin_loop_result.get("advance_reached")) or ended_in == "advance",
        escalated=_bool(thin_loop_result.get("escalated")) or ended_in == "escalate",
        notes=_string_list(thin_loop_result.get("notes")),
    )
