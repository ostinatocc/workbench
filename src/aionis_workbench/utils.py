from __future__ import annotations

import json
from typing import Any


def stringify_result(result: Any) -> str:
    """Convert an agent execution result to a string summary.

    Shared by orchestrator and delivery executor to avoid divergent
    stringify implementations.
    """
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        final_output = result.get("final_output")
        if isinstance(final_output, str) and final_output.strip():
            return final_output.strip()
        messages = result.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                content = getattr(message, "content", None)
                if isinstance(content, str) and content.strip():
                    return content.strip()
        todos = result.get("todos")
        if isinstance(todos, list) and todos:
            completed = [
                todo for todo in todos
                if isinstance(todo, dict) and todo.get("status") == "completed"
            ]
            if completed:
                latest = completed[-1].get("content")
                if isinstance(latest, str) and latest.strip():
                    return latest.strip()
            # Fall back to most recent todo with any content
            for item in reversed(todos):
                if isinstance(item, dict):
                    content = str(item.get("content") or "").strip()
                    if content:
                        return content
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except TypeError:
            return str(result).strip()
    return str(result).strip()
