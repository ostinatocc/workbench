from __future__ import annotations

from typing import Any

from .session import SessionState


def _latest_verifier_result(session: SessionState) -> dict[str, str]:
    for item in reversed(session.delegation_returns):
        if item.role == "verifier":
            return {
                "status": str(item.status or "").strip(),
                "summary": str(item.summary or "").strip(),
                "blocker": str((item.blockers or [""])[0] or "").strip(),
            }
    return {"status": "", "summary": "", "blocker": ""}


def session_completion_gates(session: SessionState) -> dict[str, str]:
    validation = session.last_validation_result or {}
    validation_ok_value = validation.get("ok")
    validation_ok = validation_ok_value if isinstance(validation_ok_value, bool) else None
    verifier = _latest_verifier_result(session)
    verifier_status = verifier["status"]
    verifier_summary = verifier["summary"]
    verifier_blocker = verifier["blocker"]
    verifier_expected = bool(session.selected_role_sequence and "verifier" in session.selected_role_sequence) or bool(
        verifier_status or verifier_summary
    )

    if verifier_status and verifier_status != "success":
        detail = verifier_summary or verifier_blocker or "verifier reported unresolved issues"
        return {"complete": detail}
    if validation_ok is False:
        summary = str(validation.get("summary") or "").strip()
        return {"complete": summary or "latest validation failed; keep the task open until verifier passes"}
    if verifier_expected and not verifier_status and validation_ok is None:
        return {"complete": "verifier has not produced a completion signal yet"}
    return {}


def apply_session_controller_gates(controller: dict[str, Any] | None, session: SessionState) -> dict[str, Any] | None:
    if not isinstance(controller, dict):
        return None
    gated_actions = session_completion_gates(session)
    if not gated_actions:
        return controller

    allowed_actions = [
        str(item).strip()
        for item in (controller.get("allowed_actions") or [])
        if isinstance(item, str) and item.strip()
    ]
    blocked_actions = [
        str(item).strip()
        for item in (controller.get("blocked_actions") or [])
        if isinstance(item, str) and item.strip()
    ]
    guard_reasons = [
        item
        for item in (controller.get("guard_reasons") or [])
        if isinstance(item, dict)
        and str(item.get("action") or "").strip()
        and str(item.get("reason") or "").strip()
    ]
    guard_index = {
        str(item.get("action") or "").strip(): index
        for index, item in enumerate(guard_reasons)
    }

    for action, reason in gated_actions.items():
        allowed_actions = [item for item in allowed_actions if item != action]
        if action not in blocked_actions:
            blocked_actions.append(action)
        if action in guard_index:
            guard_reasons[guard_index[action]] = {"action": action, "reason": reason}
        else:
            guard_reasons.append({"action": action, "reason": reason})

    return {
        **controller,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions[:6],
        "guard_reasons": guard_reasons[:6],
    }
