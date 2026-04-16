from __future__ import annotations


def classify_execution_failure_reason(reason: str) -> str:
    normalized = (reason or "").strip().lower()
    if not normalized:
        return ""
    if (
        "provider_first_turn_stall" in normalized
        or "first-response timeout" in normalized
        or "first model/tool step" in normalized
    ):
        return "provider_first_turn_stall"
    if "trace-progress timeout" in normalized or "stopped making trace progress" in normalized:
        return "execution_trace_stall"
    if (
        "429" in normalized
        or "rate limit" in normalized
        or "temporarily overloaded" in normalized
        or "connection error" in normalized
        or "connect error" in normalized
        or "connection reset" in normalized
    ):
        return "provider_transient_error"
    return "execution_failure"
