from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ControllerActionBar:
    task_id: str
    status: str
    recommended_command: str
    allowed_commands: list[str]


def controller_allowed_commands(controller: dict[str, Any] | None, *, task_id: str) -> list[str]:
    if not isinstance(controller, dict) or not isinstance(task_id, str) or not task_id.strip():
        return []
    allowed_actions = {
        item.strip()
        for item in (controller.get("allowed_actions") or [])
        if isinstance(item, str) and item.strip()
    }
    commands: list[str] = []
    if "resume" in allowed_actions:
        commands.append(f"/resume {task_id}")
    if "plan_start" in allowed_actions:
        commands.append(f"/next {task_id}")
    if "inspect_context" in allowed_actions:
        commands.append(f"/show {task_id}")
    if "list_events" in allowed_actions:
        commands.append(f"/session {task_id}")
    return list(dict.fromkeys(commands))


def primary_controller_action(controller: dict[str, Any] | None) -> str | None:
    if not isinstance(controller, dict):
        return None
    allowed_actions = {
        str(item).strip()
        for item in (controller.get("allowed_actions") or [])
        if isinstance(item, str) and item.strip()
    }
    if "resume" in allowed_actions:
        return "resume"
    if "plan_start" in allowed_actions:
        return "next"
    if "inspect_context" in allowed_actions:
        return "show"
    if "list_events" in allowed_actions:
        return "session"
    return None


def build_controller_action_bar(
    controller: dict[str, Any] | None,
    *,
    task_id: str | None,
) -> ControllerActionBar | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    if not isinstance(controller, dict) or not controller:
        return None
    allowed_commands = controller_allowed_commands(controller, task_id=task_id)
    if not allowed_commands:
        return None
    return ControllerActionBar(
        task_id=task_id,
        status=str(controller.get("status") or "unknown").strip() or "unknown",
        recommended_command=allowed_commands[0],
        allowed_commands=allowed_commands,
    )


def controller_action_bar_payload(
    controller: dict[str, Any] | None,
    *,
    task_id: str | None,
) -> dict[str, Any] | None:
    action_bar = build_controller_action_bar(controller, task_id=task_id)
    if action_bar is None:
        return None
    return {
        "task_id": action_bar.task_id,
        "status": action_bar.status,
        "recommended_command": action_bar.recommended_command,
        "allowed_commands": list(action_bar.allowed_commands),
    }


def format_controller_action_bar(
    controller: dict[str, Any] | None,
    *,
    task_id: str | None,
    label: str = "controller_actions",
) -> str | None:
    action_bar = build_controller_action_bar(controller, task_id=task_id)
    if action_bar is None:
        return None
    allowed_preview = " | ".join(action_bar.allowed_commands[:3])
    return f"{label}: recommended={action_bar.recommended_command} allowed={allowed_preview}"


def format_controller_action_bar_payload(
    action_bar: dict[str, Any] | None,
    *,
    label: str = "controller_actions",
) -> str | None:
    if not isinstance(action_bar, dict):
        return None
    recommended_command = str(action_bar.get("recommended_command") or "").strip()
    allowed_commands = [
        str(item).strip()
        for item in (action_bar.get("allowed_commands") or [])
        if isinstance(item, str) and item.strip()
    ]
    if not recommended_command or not allowed_commands:
        return None
    return f"{label}: recommended={recommended_command} allowed={' | '.join(allowed_commands[:3])}"


def primary_action_from_action_bar(action_bar: dict[str, Any] | None) -> str | None:
    if not isinstance(action_bar, dict):
        return None
    recommended_command = str(action_bar.get("recommended_command") or "").strip()
    if not recommended_command.startswith("/"):
        return None
    parts = recommended_command[1:].split(" ", 1)
    action = parts[0].strip()
    return action or None
