from __future__ import annotations

import json
import os
import re
import tempfile
from inspect import isawaitable
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


class DeliveryComplete(Exception):
    def __init__(self, message: str = "Delivery artifact is ready.") -> None:
        super().__init__(message)
        self.message = message


@dataclass
class TraceStep:
    step_index: int
    tool_name: str
    tool_call_id: str | None
    tool_input: Any
    status: str
    output_signature: dict[str, Any]
    error: str | None = None


class _CallableMiddlewareAdapter:
    def __init__(self, wrapped: Any, fallback_callable: Any) -> None:
        self._wrapped = wrapped
        self._fallback_callable = fallback_callable

    def __call__(self, *args, **kwargs):
        return self._fallback_callable(*args, **kwargs)

    def _call_wrapped(self, attribute_name: str, *args, **kwargs):
        wrapped = getattr(self._wrapped, attribute_name, None)
        if callable(wrapped):
            return wrapped(*args, **kwargs)
        return None

    async def _acall_wrapped(self, attribute_name: str, *args, **kwargs):
        wrapped = getattr(self._wrapped, attribute_name, None)
        if callable(wrapped):
            result = wrapped(*args, **kwargs)
            if isawaitable(result):
                return await result
            return result
        return None

    def wrap_tool_call(self, *args, **kwargs):
        result = self._call_wrapped("wrap_tool_call", *args, **kwargs)
        if result is not None:
            return result
        return self._fallback_callable(*args, **kwargs)

    def wrap_model_call(self, *args, **kwargs):
        result = self._call_wrapped("wrap_model_call", *args, **kwargs)
        if result is not None:
            return result
        return self._fallback_callable(*args, **kwargs)

    async def awrap_tool_call(self, *args, **kwargs):
        result = await self._acall_wrapped("awrap_tool_call", *args, **kwargs)
        if result is None:
            result = self._fallback_callable(*args, **kwargs)
        if isawaitable(result):
            return await result
        return result

    async def awrap_model_call(self, *args, **kwargs):
        result = await self._acall_wrapped("awrap_model_call", *args, **kwargs)
        if result is None:
            result = self._fallback_callable(*args, **kwargs)
        if isawaitable(result):
            return await result
        return result

    def before_agent(self, *args, **kwargs):
        return self._call_wrapped("before_agent", *args, **kwargs)

    async def abefore_agent(self, *args, **kwargs):
        return await self._acall_wrapped("abefore_agent", *args, **kwargs)

    def after_agent(self, *args, **kwargs):
        return self._call_wrapped("after_agent", *args, **kwargs)

    async def aafter_agent(self, *args, **kwargs):
        return await self._acall_wrapped("aafter_agent", *args, **kwargs)

    def before_model(self, *args, **kwargs):
        return self._call_wrapped("before_model", *args, **kwargs)

    async def abefore_model(self, *args, **kwargs):
        return await self._acall_wrapped("abefore_model", *args, **kwargs)

    def after_model(self, *args, **kwargs):
        return self._call_wrapped("after_model", *args, **kwargs)

    async def aafter_model(self, *args, **kwargs):
        return await self._acall_wrapped("aafter_model", *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


def _is_langchain_middleware_object(wrapped: Any) -> bool:
    required = (
        "wrap_tool_call",
        "awrap_tool_call",
        "wrap_model_call",
        "awrap_model_call",
        "before_agent",
        "abefore_agent",
        "after_agent",
        "aafter_agent",
        "before_model",
        "abefore_model",
        "after_model",
        "aafter_model",
    )
    return all(hasattr(wrapped, name) for name in required)


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _message_char_count(message: BaseMessage) -> int:
    return len(_stringify(getattr(message, "content", "")))


def _build_output_signature(result: Any) -> dict[str, Any]:
    signature: dict[str, Any] = {"result_type": type(result).__name__}
    if isinstance(result, ModelResponse):
        messages = result.result
        signature["messages"] = len(messages)
        signature["chars"] = sum(_message_char_count(message) for message in messages)
        ai_messages = [message for message in messages if isinstance(message, AIMessage)]
        if ai_messages:
            signature["tool_calls"] = sum(len(message.tool_calls) for message in ai_messages)
            usage = ai_messages[-1].usage_metadata
            if usage:
                signature["usage"] = dict(usage)
        return signature
    if isinstance(result, AIMessage):
        signature["chars"] = _message_char_count(result)
        signature["tool_calls"] = len(result.tool_calls)
        if result.usage_metadata:
            signature["usage"] = dict(result.usage_metadata)
        return signature
    if isinstance(result, ToolMessage):
        signature["tool_message_status"] = result.status
        signature["chars"] = len(_stringify(result.content))
        if result.name:
            signature["message_name"] = result.name
        return signature
    signature["chars"] = len(_stringify(result))
    return signature


def _collect_string_paths(value: Any, paths: dict[str, int]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if normalized_key in {"path", "file_path", "cwd", "root_dir"} and isinstance(nested, str):
                candidate = nested.strip()
                if candidate.startswith("/"):
                    weight = {"file_path": 50, "path": 40, "cwd": 5, "root_dir": 1}.get(normalized_key, 0)
                    paths[candidate] = max(paths.get(candidate, 0), weight)
            _collect_string_paths(nested, paths)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_string_paths(nested, paths)


def _path_bonus(path: PurePosixPath) -> int:
    if path.suffix:
        return 20
    if path.name in {"Dockerfile", "Makefile", "README.md", "package.json", "pyproject.toml", "tox.ini"}:
        return 15
    if path.name.startswith("test_"):
        return 10
    return 0


def _normalize_target_path(candidate: str, repo_root: str | None) -> str | None:
    candidate = candidate.strip()
    if not candidate:
        return None
    path = PurePosixPath(candidate)

    if repo_root:
        root = PurePosixPath(repo_root)
        if path == root:
            return None
        if path.is_absolute():
            try:
                relative = path.relative_to(root)
            except ValueError:
                return None
            if not relative.parts:
                return None
            path = relative

    if not path.parts or path.parts == (".",):
        return None
    if path.name in {"", ".", ".."}:
        return None
    return path.as_posix()


def normalize_target_paths(
    paths: list[str],
    *,
    repo_root: str | None,
    limit: int = 8,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in paths:
        normalized_candidate = _normalize_target_path(candidate, repo_root)
        if normalized_candidate is None or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        normalized.append(normalized_candidate)
        if len(normalized) >= limit:
            break
    return normalized


def extract_target_files(
    trace_steps: list["TraceStep"],
    *,
    repo_root: str | None = None,
    limit: int = 8,
) -> list[str]:
    collected: dict[str, int] = {}
    for step in trace_steps:
        _collect_string_paths(step.tool_input, collected)
    ranked: list[tuple[int, str]] = []
    for candidate, weight in collected.items():
        path = PurePosixPath(candidate)
        if path.name in {"", ".", ".."}:
            continue
        if candidate in {"/", "/tmp", "/var", "/usr", "/bin", "/lib", "/opt"}:
            continue
        ranked.append((weight + _path_bonus(path), candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    file_like = [candidate for score, candidate in ranked if score >= 20]
    if file_like:
        return normalize_target_paths(file_like, repo_root=repo_root, limit=limit)
    return normalize_target_paths([candidate for _, candidate in ranked], repo_root=repo_root, limit=limit)


@dataclass
class TraceRecorder:
    _steps: list[TraceStep] = field(default_factory=list)
    snapshot_path: str = ""

    def reset(self) -> None:
        self._steps.clear()
        self._write_snapshot()

    def record(
        self,
        *,
        tool_name: str,
        tool_call_id: str | None,
        tool_input: Any,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        self._steps.append(
            TraceStep(
                step_index=len(self._steps) + 1,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_input=tool_input,
                status=status,
                output_signature=_build_output_signature(result),
                error=error,
            )
        )
        self._write_snapshot()

    def export(self) -> list[TraceStep]:
        return list(self._steps)

    def _write_snapshot(self) -> None:
        if not self.snapshot_path:
            return
        path = Path(self.snapshot_path)
        payload = {
            "step_count": len(self._steps),
            "steps": [asdict(step) for step in self._steps],
        }
        write_json_atomically(path, payload)


def create_tool_trace_middleware(recorder: TraceRecorder):
    def trace_tool_call(request, handler):
        tool_name = request.tool_call.get("name", "unknown_tool")
        tool_call_id = request.tool_call.get("id")
        tool_input = request.tool_call.get("args")
        try:
            result = handler(request)
        except DeliveryComplete as done:
            recorder.record(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_input=tool_input,
                status="success",
                result=done.message,
            )
            raise
        except Exception as exc:
            recorder.record(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_input=tool_input,
                status="error",
                error=str(exc),
            )
            raise
        status = "success"
        if isinstance(result, ToolMessage) and result.status == "error":
            status = "error"
        recorder.record(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_input=tool_input,
            status=status,
            result=result,
            error=_stringify(result.content) if status == "error" and isinstance(result, ToolMessage) else None,
        )
        return result

    wrapped = wrap_tool_call(name="WorkbenchToolTraceMiddleware")(trace_tool_call)
    if _is_langchain_middleware_object(wrapped):
        return wrapped
    return _CallableMiddlewareAdapter(wrapped, trace_tool_call)


def sanitize_delivery_execute_command(command: str) -> str:
    cleaned = _stringify(command).strip()
    if not cleaned:
        return cleaned
    patterns = (
        r"^\s*cd\s+/\S*\s*&&\s*",
        r"^\s*cd\s+/\S*\s*;\s*",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
    return cleaned.strip()


def create_delivery_shell_guard_middleware():
    def guard_shell_command(request, handler):
        tool_call = getattr(request, "tool_call", None)
        if isinstance(tool_call, dict) and tool_call.get("name") == "execute":
            args = tool_call.get("args")
            if isinstance(args, dict):
                command = args.get("command")
                if isinstance(command, str):
                    args["command"] = sanitize_delivery_execute_command(command)
        return handler(request)

    wrapped = wrap_tool_call(name="WorkbenchDeliveryShellGuardMiddleware")(guard_shell_command)
    if _is_langchain_middleware_object(wrapped):
        return wrapped
    return _CallableMiddlewareAdapter(wrapped, guard_shell_command)


def should_complete_delivery_after_tool(
    *,
    tool_name: str,
    tool_input: Any,
    result: Any,
    workspace_root: str,
) -> bool:
    if tool_name != "execute":
        return False
    status = getattr(result, "status", "success")
    if status == "error":
        return False
    command = _stringify((tool_input or {}).get("command")).strip().lower()
    if "npm run build" not in command:
        return False
    return (Path(workspace_root) / "dist" / "index.html").exists()


def create_delivery_completion_middleware(*, workspace_root: str):
    def complete_after_build(request, handler):
        result = handler(request)
        tool_name = request.tool_call.get("name", "unknown_tool")
        tool_input = request.tool_call.get("args") or {}
        if should_complete_delivery_after_tool(
            tool_name=tool_name,
            tool_input=tool_input,
            result=result,
            workspace_root=workspace_root,
        ):
            raise DeliveryComplete("Build completed and delivery artifact is ready.")
        return result

    wrapped = wrap_tool_call(name="WorkbenchDeliveryCompletionMiddleware")(complete_after_build)
    if _is_langchain_middleware_object(wrapped):
        return wrapped
    return _CallableMiddlewareAdapter(wrapped, complete_after_build)


def create_model_trace_middleware(recorder: TraceRecorder):
    def trace_model_call(request, handler):
        model_name = (
            getattr(request.model, "model_name", None)
            or getattr(request.model, "model", None)
            or type(request.model).__name__
        )
        model_input = {
            "model": model_name,
            "messages": len(request.messages),
            "tools": len(request.tools),
            "has_system_message": request.system_message is not None,
        }
        try:
            result = handler(request)
        except Exception as exc:
            recorder.record(
                tool_name="workbench.model",
                tool_call_id=None,
                tool_input=model_input,
                status="error",
                error=str(exc),
            )
            raise
        recorder.record(
            tool_name="workbench.model",
            tool_call_id=None,
            tool_input=model_input,
            status="success",
            result=result,
        )
        return result

    wrapped = wrap_model_call(name="WorkbenchModelTraceMiddleware")(trace_model_call)
    if _is_langchain_middleware_object(wrapped):
        return wrapped
    return _CallableMiddlewareAdapter(wrapped, trace_model_call)
