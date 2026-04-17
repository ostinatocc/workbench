from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .tracing import write_json_atomically


class ModelInvokeTimeout(TimeoutError):
    pass


def _append_trace_failure(trace_path: str, *, failure_reason: str) -> None:
    if not trace_path:
        return
    path = Path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"step_count": 0, "steps": []}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                payload.update(parsed)
        except Exception:
            pass
    payload["failure_reason"] = failure_reason.strip()
    write_json_atomically(path, payload)


def _update_trace_retry_state(
    trace_path: str,
    *,
    attempt_number: int,
    max_attempts: int,
    error_type: str,
    error_message: str,
) -> None:
    if not trace_path:
        return
    path = Path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"step_count": 0, "steps": []}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                payload.update(parsed)
        except Exception:
            pass
    retry_events = payload.get("delivery_retry_events")
    if not isinstance(retry_events, list):
        retry_events = []
    retry_events.append(
        {
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "error_type": error_type.strip(),
            "error_message": error_message.strip(),
        }
    )
    payload["delivery_attempts"] = attempt_number
    payload["delivery_max_attempts"] = max_attempts
    payload["delivery_retry_events"] = retry_events
    payload["last_error_type"] = error_type.strip()
    payload["last_error_message"] = error_message.strip()
    write_json_atomically(path, payload)


def _reset_delivery_trace(trace_path: str, *, preserve_retry_metadata: bool = False) -> None:
    if not trace_path:
        return
    path = Path(trace_path)
    preserved: dict[str, Any] = {}
    if preserve_retry_metadata and path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                for key in (
                    "delivery_attempts",
                    "delivery_max_attempts",
                    "delivery_retry_events",
                    "last_error_type",
                    "last_error_message",
                ):
                    if key in parsed:
                        preserved[key] = parsed[key]
        except Exception:
            pass
    write_json_atomically(path, {"step_count": 0, "steps": []})
    if preserved:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.update(preserved)
            write_json_atomically(path, payload)


def _trace_shows_successful_build(trace_path: str) -> bool:
    if not trace_path:
        return False
    path = Path(trace_path)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return False
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        if step.get("tool_name") != "execute":
            continue
        tool_input = step.get("tool_input") or {}
        command = str(tool_input.get("command") or "").strip().lower()
        if "npm run build" in command:
            return step.get("status") == "success"
    return False


def _delivery_artifact_ready(*, root_dir: str, trace_path: str) -> bool:
    dist_entry = Path(root_dir) / "dist" / "index.html"
    if not dist_entry.exists():
        return False
    return _trace_shows_successful_build(trace_path)


def _should_retry_transient_delivery_error(*, error_type: str, error_message: str) -> bool:
    normalized_type = (error_type or "").strip().lower()
    normalized_message = (error_message or "").strip().lower()
    if not normalized_message:
        return False
    transient_markers = (
        "429",
        "rate limit",
        "temporarily overloaded",
        "service may be temporarily overloaded",
        "connection error",
        "connect error",
        "connection reset",
        "'code': '1305'",
        '"code": "1305"',
    )
    if not any(marker in normalized_message for marker in transient_markers):
        return False
    if normalized_type in {"modelinvoketimeout", "timeout", "timeouterror"}:
        return False
    return True


def _delivery_retry_backoff_seconds(attempt_number: int) -> float:
    return min(2.0 * max(1, attempt_number), 5.0)


def _cleanup_delivery_runtime(process: Any, result_queue: Any) -> None:
    try:
        close_queue = getattr(result_queue, "close", None)
        if callable(close_queue):
            close_queue()
        join_thread = getattr(result_queue, "join_thread", None)
        if callable(join_thread):
            join_thread()
    except Exception:
        pass
    try:
        close_process = getattr(process, "close", None)
        if callable(close_process):
            close_process()
    except Exception:
        pass


def _delivery_first_response_timeout_seconds(*, model_timeout_seconds: float, delivery_timeout_seconds: float) -> float:
    return min(float(delivery_timeout_seconds), max(30.0, float(model_timeout_seconds) + 15.0))


def _delivery_progress_timeout_seconds(*, model_timeout_seconds: float, delivery_timeout_seconds: float) -> float:
    return min(float(delivery_timeout_seconds), max(45.0, float(model_timeout_seconds) + 20.0))


def _trace_has_steps(trace_path: str) -> bool:
    if not trace_path:
        return False
    path = Path(trace_path)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    steps = payload.get("steps")
    return isinstance(steps, list) and bool(steps)


def _trace_step_count(trace_path: str) -> int:
    if not trace_path:
        return 0
    path = Path(trace_path)
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return 0
    return len(steps)


__all__ = [
    "ModelInvokeTimeout",
    "_append_trace_failure",
    "_cleanup_delivery_runtime",
    "_delivery_artifact_ready",
    "_delivery_first_response_timeout_seconds",
    "_delivery_progress_timeout_seconds",
    "_delivery_retry_backoff_seconds",
    "_reset_delivery_trace",
    "_should_retry_transient_delivery_error",
    "_trace_has_steps",
    "_trace_shows_successful_build",
    "_trace_step_count",
    "_update_trace_retry_state",
]
