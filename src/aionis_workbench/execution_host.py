from __future__ import annotations

import json
import multiprocessing
import queue
import re
import signal
import time
from pathlib import Path
from typing import Any

import httpx
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_openai import ChatOpenAI

from .config import WorkbenchConfig
from .roles import builtin_subagents
from .tracing import (
    DeliveryComplete,
    TraceRecorder,
    create_delivery_completion_middleware,
    create_delivery_shell_guard_middleware,
    create_model_trace_middleware,
    create_tool_trace_middleware,
    write_json_atomically,
)


class ModelInvokeTimeout(TimeoutError):
    pass


def _timeout_signal_handler(signum, frame):  # type: ignore[no-untyped-def]
    raise ModelInvokeTimeout("Workbench model invocation exceeded the configured timeout.")


def _delivery_invoke_worker(  # type: ignore[no-untyped-def]
    config: WorkbenchConfig,
    system_parts: list[str],
    memory_sources: list[str],
    root_dir: str,
    task: str,
    delivery_timeout_seconds: float,
    model_timeout_seconds: float,
    trace_path: str,
    result_queue,
):
    trace = TraceRecorder(snapshot_path=trace_path)
    host = DeepagentsExecutionHost(config=config, trace=trace)
    try:
        agent = host.build_delivery_agent(
            system_parts=system_parts,
            memory_sources=memory_sources,
            root_dir=root_dir,
            model_timeout_seconds_override=model_timeout_seconds,
        )
        result = host.invoke(
            agent,
            {"messages": [{"role": "user", "content": task}]},
            timeout_seconds=delivery_timeout_seconds,
        )
        result_queue.put({"ok": True, "result": host._response_text(result), "trace_path": trace_path})
    except DeliveryComplete as done:
        result_queue.put({"ok": True, "result": done.message, "trace_path": trace_path})
    except Exception as exc:  # pragma: no cover - exercised through parent process behavior
        result_queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc).strip() or type(exc).__name__,
                "trace_path": trace_path,
            }
        )


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
    TraceRecorder(snapshot_path=trace_path).reset()
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


class DeepagentsExecutionHost:
    def __init__(self, *, config: WorkbenchConfig, trace: TraceRecorder) -> None:
        self._config = config
        self._trace = trace

    def describe(self) -> dict[str, Any]:
        supports_live_tasks = self._config.provider in {"openrouter", "openai"} and bool(self._config.api_key)
        health_status = "available" if supports_live_tasks else "offline"
        health_reason = None if supports_live_tasks else "model_credentials_missing"
        return {
            "name": "deepagents_local_shell",
            "execution_runtime": "deepagents",
            "backend": "LocalShellBackend",
            "model_provider": self._config.provider,
            "model_available": bool(self._config.api_key),
            "supports_live_tasks": supports_live_tasks,
            "mode": "live_enabled" if supports_live_tasks else "inspect_only",
            "health_status": health_status,
            "health_reason": health_reason,
            "degraded_reason": health_reason,
        }

    def _build_model(
        self,
        *,
        timeout_pressure: bool = False,
        timeout_seconds_override: float | None = None,
        max_completion_tokens_override: int | None = None,
        max_retries_override: int | None = None,
        model_kwargs_override: dict[str, Any] | None = None,
    ):
        if self._config.provider in {"openrouter", "openai"}:
            timeout_seconds = timeout_seconds_override or self._config.model_timeout_seconds or 45.0
            max_completion_tokens = max_completion_tokens_override
            if max_completion_tokens is None:
                max_completion_tokens = self._config.max_completion_tokens
            if timeout_pressure:
                if max_completion_tokens is None:
                    max_completion_tokens = 768
                else:
                    max_completion_tokens = min(max_completion_tokens, 768)
            max_retries = self._config.model_max_retries if max_retries_override is None else max_retries_override
            client_timeout = httpx.Timeout(
                timeout_seconds,
                connect=min(timeout_seconds, 10.0),
                read=timeout_seconds,
                write=timeout_seconds,
                pool=timeout_seconds,
            )
            return ChatOpenAI(
                model=self._config.model,
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                max_completion_tokens=max_completion_tokens,
                timeout=timeout_seconds,
                http_client=httpx.Client(timeout=client_timeout, trust_env=False),
                max_retries=max_retries,
                model_kwargs=model_kwargs_override or {},
            )
        raise ValueError(
            "Workbench model credentials are missing. Set OPENROUTER_API_KEY for the OpenRouter path "
            "or OPENAI_API_KEY for the OpenAI-compatible path before running model-backed workbench commands."
        )

    def supports_live_tasks(self) -> bool:
        return self._config.provider in {"openrouter", "openai"} and bool(self._config.api_key)

    def live_app_planner_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 45.0)

    def live_app_planner_max_completion_tokens(self) -> int:
        return 160

    def live_app_evaluator_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 45.0)

    def live_app_evaluator_max_completion_tokens(self) -> int:
        return 180

    def live_app_negotiator_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 45.0)

    def live_app_negotiator_max_completion_tokens(self) -> int:
        return 180

    def live_app_revisor_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 45.0)

    def live_app_revisor_max_completion_tokens(self) -> int:
        return 180

    def live_app_generator_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 45.0)

    def live_app_delivery_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 900.0)

    def live_app_delivery_model_timeout_seconds(self) -> float:
        configured = max(self._config.model_timeout_seconds or 45.0, 45.0)
        return min(configured, 90.0)

    def live_app_generator_max_completion_tokens(self) -> int:
        return 220

    def probe_live_model_auth(self) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live auth probe requires a live model provider with configured credentials")
        response = self._invoke_model(
            [
                (
                    "system",
                    "Return JSON only. Produce exactly {\"ok\": true}. Do not include markdown fences or extra text.",
                ),
                ("human", "Return the JSON object now."),
            ],
            timeout_seconds_override=min(self._config.model_timeout_seconds or 45.0, 10.0),
            max_completion_tokens_override=24,
            max_retries_override=0,
        )
        payload = self._extract_json_payload(self._response_text(response))
        if payload.get("ok") is not True:
            raise ValueError("live auth probe did not return ok=true")
        return payload

    def _invoke_model(
        self,
        messages: list[tuple[str, str]],
        *,
        timeout_seconds_override: float | None = None,
        max_completion_tokens_override: int | None = None,
        max_retries_override: int | None = None,
        model_kwargs_override: dict[str, Any] | None = None,
    ):
        timeout_seconds = timeout_seconds_override or self._config.model_timeout_seconds or 45.0
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout_signal_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            model = self._build_model(
                timeout_pressure=True,
                timeout_seconds_override=timeout_seconds,
                max_completion_tokens_override=max_completion_tokens_override,
                max_retries_override=max_retries_override,
                model_kwargs_override=model_kwargs_override,
            )
            return model.invoke(messages)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _response_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            return "\n".join(parts)
        content = getattr(value, "content", None)
        if content is not None and content is not value:
            return self._response_text(content)
        return str(value)

    def _extract_json_payload(self, text: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        raw = fenced.group(1) if fenced else text
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("live planner response must be a JSON object")
        return payload

    def plan_app_live(self, *, prompt: str) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live planner requires a live model provider with configured credentials")
        system = (
            "You are a product planner for long-running application development. "
            "Return JSON only. "
            "Produce a compact planning object with keys: "
            "title, design_direction, planning_rationale, sprint_1. "
            "Keep title under 5 words, design_direction under 12 words, planning_rationale to exactly 2 items. "
            "sprint_1 must be an object with goal, scope, acceptance_checks, done_definition. "
            "Keep scope to at most 3 items, acceptance_checks to at most 1 item, done_definition to at most 2 items. "
            "Favor concrete, reviewable scope over broad ambition. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        response = self._invoke_model(
            [
                ("system", system),
                ("human", f"Project request: {prompt}\nReturn only the JSON object."),
            ],
            timeout_seconds_override=self.live_app_planner_timeout_seconds(),
            max_completion_tokens_override=self.live_app_planner_max_completion_tokens(),
            max_retries_override=0,
        )
        return self._extract_json_payload(self._response_text(response))

    def evaluate_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        evaluator_criteria: list[dict[str, Any]],
        latest_execution_attempt: dict[str, Any] | None = None,
        execution_focus: str = "",
        summary: str = "",
        blocker_notes: list[str] | None = None,
        requested_status: str = "auto",
        criteria_scores: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live evaluator requires a live model provider with configured credentials")
        system = (
            "You are an app sprint evaluator for a long-running application development harness. "
            "Return JSON only. "
            "Produce an object with keys: status, summary, passing_criteria, failing_criteria, blocker_notes, criteria_scores. "
            "status must be one of passed or failed. "
            "passing_criteria and failing_criteria must contain only criterion names from the provided evaluator criteria. "
            "criteria_scores must be an object mapping criterion names to scores between 0.0 and 1.0. "
            "Keep summary to one sentence. "
            "If blocker_notes are present or a criterion falls below its threshold, bias toward failed. "
            "If execution_focus is present, treat it as the highest-signal summary of the most recent bounded execution attempt. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        response = self._invoke_model(
            [
                ("system", system),
                (
                    "human",
                    json.dumps(
                        {
                            "product_spec": product_spec,
                            "sprint_contract": sprint_contract,
                            "evaluator_criteria": evaluator_criteria,
                            "latest_execution_attempt": dict(latest_execution_attempt or {}),
                            "execution_focus": execution_focus,
                            "requested_status": requested_status,
                            "summary": summary,
                            "blocker_notes": list(blocker_notes or []),
                            "criteria_scores": dict(criteria_scores or {}),
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            timeout_seconds_override=self.live_app_evaluator_timeout_seconds(),
            max_completion_tokens_override=self.live_app_evaluator_max_completion_tokens(),
            max_retries_override=0,
        )
        return self._extract_json_payload(self._response_text(response))

    def negotiate_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any],
        planned_sprints: list[dict[str, Any]],
        objections: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live negotiator requires a live model provider with configured credentials")
        system = (
            "You are a planner revising a sprint proposal after evaluator feedback in a long-running application development harness. "
            "Return JSON only. "
            "Produce an object with keys: recommended_action, planner_response, sprint_negotiation_notes. "
            "recommended_action must be revise_current_sprint or advance_to_next_sprint. "
            "planner_response must be a list of 1 to 3 short, concrete revision notes. "
            "sprint_negotiation_notes must be a list of 1 to 3 short notes that an evaluator should use in the next negotiation round. "
            "If there are failing criteria or blocker notes, bias toward revise_current_sprint. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        response = self._invoke_model(
            [
                ("system", system),
                (
                    "human",
                    json.dumps(
                        {
                            "product_spec": product_spec,
                            "sprint_contract": sprint_contract,
                            "latest_evaluation": latest_evaluation,
                            "planned_sprints": planned_sprints,
                            "objections": list(objections or []),
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            timeout_seconds_override=self.live_app_negotiator_timeout_seconds(),
            max_completion_tokens_override=self.live_app_negotiator_max_completion_tokens(),
            max_retries_override=0,
        )
        return self._extract_json_payload(self._response_text(response))

    def revise_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any],
        latest_negotiation_round: dict[str, Any],
        revision_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live revisor requires a live model provider with configured credentials")
        system = (
            "You are revising the current sprint after planner/evaluator negotiation in a long-running application development harness. "
            "Return JSON only. "
            "Produce an object with keys: revision_summary, must_fix, must_keep. "
            "revision_summary must be one short sentence. "
            "must_fix must be a list of 1 to 4 concrete revision targets. "
            "must_keep must be a list of 1 to 4 constraints or checks that must survive the revision. "
            "Bias must_fix toward failing criteria, blocker notes, and negotiation objections. "
            "Bias must_keep toward acceptance checks, done-definition items, and already passing criteria. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        response = self._invoke_model(
            [
                ("system", system),
                (
                    "human",
                    json.dumps(
                        {
                            "product_spec": product_spec,
                            "sprint_contract": sprint_contract,
                            "latest_evaluation": latest_evaluation,
                            "latest_negotiation_round": latest_negotiation_round,
                            "revision_notes": list(revision_notes or []),
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            timeout_seconds_override=self.live_app_revisor_timeout_seconds(),
            max_completion_tokens_override=self.live_app_revisor_max_completion_tokens(),
            max_retries_override=0,
        )
        return self._extract_json_payload(self._response_text(response))

    def replan_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any] | None = None,
        latest_revision: dict[str, Any] | None = None,
        latest_execution_attempt: dict[str, Any] | None = None,
        execution_focus: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live replanner requires a live model provider with configured credentials")
        system = (
            "You are replanning the current sprint after escalation or retry-budget exhaustion in a long-running application development harness. "
            "Return JSON only. "
            "Produce an object with keys: goal, scope, acceptance_checks, done_definition, replan_note. "
            "goal must be one short sentence for the replanned sprint. "
            "scope must be a list of 1 to 4 compact work items. "
            "acceptance_checks must be a list of 0 to 2 checks. "
            "done_definition must be a list of 1 to 3 clear completion statements. "
            "replan_note must be one short sentence explaining why the sprint was narrowed or redirected. "
            "Bias the replanned sprint toward the latest failing criteria, latest revision must_fix items, and latest execution attempt target hints. "
            "If execution_focus is present, treat it as the highest-signal summary of what the previous execution attempt actually changed or tried to change. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        response = self._invoke_model(
            [
                ("system", system),
                (
                    "human",
                    json.dumps(
                        {
                            "product_spec": product_spec,
                            "sprint_contract": sprint_contract,
                            "latest_evaluation": dict(latest_evaluation or {}),
                            "latest_revision": dict(latest_revision or {}),
                            "latest_execution_attempt": dict(latest_execution_attempt or {}),
                            "execution_focus": execution_focus,
                            "note": note,
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            timeout_seconds_override=self.live_app_planner_timeout_seconds(),
            max_completion_tokens_override=self.live_app_planner_max_completion_tokens(),
            max_retries_override=0,
        )
        return self._extract_json_payload(self._response_text(response))

    def generate_app_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_revision: dict[str, Any] | None = None,
        latest_evaluation: dict[str, Any] | None = None,
        latest_negotiation_round: dict[str, Any] | None = None,
        execution_focus: str = "",
        execution_summary: str = "",
        changed_target_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError("live generator requires a live model provider with configured credentials")
        system = (
            "You are producing a bounded implementation-attempt artifact for a long-running application development harness. "
            "Return JSON only. "
            "Produce an object with keys: execution_summary, changed_target_hints. "
            "execution_summary must be one short sentence describing the immediate implementation attempt. "
            "changed_target_hints must be a list of 1 to 4 compact targets such as files, modules, workflows, or checks. "
            "Bias the attempt toward the latest revision when one exists. "
            "Bias targets toward must_fix items, sprint scope, and one relevant acceptance check. "
            "If execution_focus is present, use it to keep the new attempt aligned with the most recent concrete implementation direction. "
            "Do not claim the code is fully implemented; describe only the bounded execution attempt. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        response = self._invoke_model(
            [
                ("system", system),
                (
                    "human",
                    json.dumps(
                        {
                            "product_spec": product_spec,
                            "sprint_contract": sprint_contract,
                            "latest_revision": dict(latest_revision or {}),
                            "latest_evaluation": dict(latest_evaluation or {}),
                            "latest_negotiation_round": dict(latest_negotiation_round or {}),
                            "execution_focus": execution_focus,
                            "execution_summary": execution_summary,
                            "changed_target_hints": list(changed_target_hints or []),
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            timeout_seconds_override=self.live_app_generator_timeout_seconds(),
            max_completion_tokens_override=self.live_app_generator_max_completion_tokens(),
            max_retries_override=0,
        )
        return self._extract_json_payload(self._response_text(response))

    def build_agent(
        self,
        *,
        system_parts: list[str | None],
        memory_sources: list[str],
        timeout_pressure: bool,
        root_dir: str | None = None,
        model_timeout_seconds_override: float | None = None,
        use_builtin_subagents: bool = True,
    ):
        self._trace.reset()
        backend = LocalShellBackend(
            root_dir=root_dir or self._config.repo_root,
            virtual_mode=True,
            inherit_env=True,
        )
        if timeout_pressure:
            return self._build_direct_agent(
                system_parts=system_parts,
                backend=backend,
                memory_sources=memory_sources,
                model_timeout_seconds_override=model_timeout_seconds_override,
            )
        return create_deep_agent(
            model=self._build_model(
                timeout_pressure=timeout_pressure,
                timeout_seconds_override=model_timeout_seconds_override,
            ),
            system_prompt="\n\n".join(part for part in system_parts if part),
            backend=backend,
            middleware=[
                create_model_trace_middleware(self._trace),
                create_tool_trace_middleware(self._trace),
            ],
            subagents=[] if timeout_pressure or not use_builtin_subagents else builtin_subagents(),
            memory=memory_sources,
            name="aionis-workbench",
        )

    def _build_direct_agent(
        self,
        *,
        system_parts: list[str | None],
        backend: LocalShellBackend,
        memory_sources: list[str],
        model_timeout_seconds_override: float | None = None,
    ):
        model = self._build_model(
            timeout_pressure=True,
            timeout_seconds_override=model_timeout_seconds_override,
        )
        middleware = [
            TodoListMiddleware(),
            MemoryMiddleware(backend=backend, sources=memory_sources),
            FilesystemMiddleware(backend=backend),
            create_summarization_middleware(model, backend),
            AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
            PatchToolCallsMiddleware(),
            create_delivery_shell_guard_middleware(),
            create_model_trace_middleware(self._trace),
            create_tool_trace_middleware(self._trace),
        ]
        return create_agent(
            model,
            system_prompt="\n\n".join(part for part in system_parts if part),
            middleware=middleware,
            name="aionis-workbench-direct",
        )

    def build_delivery_agent(
        self,
        *,
        system_parts: list[str | None],
        memory_sources: list[str],
        root_dir: str | None = None,
        model_timeout_seconds_override: float | None = None,
    ):
        model = self._build_model(
            timeout_pressure=False,
            timeout_seconds_override=model_timeout_seconds_override,
            max_retries_override=0,
        )
        backend = LocalShellBackend(
            root_dir=root_dir or self._config.repo_root,
            virtual_mode=True,
            inherit_env=True,
        )
        middleware: list[Any] = []
        if memory_sources:
            middleware.append(MemoryMiddleware(backend=backend, sources=memory_sources))
        middleware.extend(
            [
                FilesystemMiddleware(backend=backend),
                AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
                PatchToolCallsMiddleware(),
                create_delivery_shell_guard_middleware(),
                create_model_trace_middleware(self._trace),
                create_tool_trace_middleware(self._trace),
                create_delivery_completion_middleware(workspace_root=root_dir or self._config.repo_root),
            ]
        )
        return create_agent(
            model,
            system_prompt="\n\n".join(part for part in system_parts if part),
            middleware=middleware,
            name="aionis-workbench-delivery",
        ).with_config({"recursion_limit": 128, "metadata": {"ls_integration": "deepagents-delivery"}})

    def invoke(self, agent, payload: dict[str, Any], *, timeout_seconds: float | None = None):
        timeout_seconds = timeout_seconds or self._config.model_timeout_seconds or 45.0
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout_signal_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            return agent.invoke(payload)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def invoke_delivery_task(
        self,
        *,
        system_parts: list[str],
        memory_sources: list[str],
        root_dir: str,
        task: str,
        timeout_seconds: float | None = None,
        trace_path: str = "",
    ) -> str:
        timeout = timeout_seconds or self.live_app_delivery_timeout_seconds()
        model_timeout = self.live_app_delivery_model_timeout_seconds()
        max_attempts = 3
        for attempt_number in range(1, max_attempts + 1):
            _reset_delivery_trace(trace_path, preserve_retry_metadata=attempt_number > 1)
            ctx = multiprocessing.get_context("spawn")
            result_queue = ctx.Queue()
            process = ctx.Process(
                target=_delivery_invoke_worker,
                args=(
                    self._config,
                    list(system_parts),
                    list(memory_sources),
                    root_dir,
                    task,
                    float(timeout),
                    float(model_timeout),
                    trace_path,
                    result_queue,
                ),
            )
            process.daemon = True
            process.start()
            start_time = time.monotonic()
            deadline = start_time + float(timeout)
            first_response_deadline = start_time + _delivery_first_response_timeout_seconds(
                model_timeout_seconds=float(model_timeout),
                delivery_timeout_seconds=float(timeout),
            )
            progress_timeout = _delivery_progress_timeout_seconds(
                model_timeout_seconds=float(model_timeout),
                delivery_timeout_seconds=float(timeout),
            )
            first_response_timed_out = False
            progress_timed_out = False
            last_step_count = 0
            last_progress_time = start_time
            while process.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                process.join(min(1.0, remaining))
                if _delivery_artifact_ready(root_dir=root_dir, trace_path=trace_path):
                    process.terminate()
                    process.join(5.0)
                    _cleanup_delivery_runtime(process, result_queue)
                    return "Build completed and delivery artifact is ready."
                current_step_count = _trace_step_count(trace_path)
                if current_step_count > last_step_count:
                    last_step_count = current_step_count
                    last_progress_time = time.monotonic()
                if not _trace_has_steps(trace_path) and time.monotonic() >= first_response_deadline:
                    process.terminate()
                    process.join(5.0)
                    error_type = "ProviderFirstTurnStall"
                    error_message = (
                        "provider_first_turn_stall: Delivery agent did not produce a first model/tool step within "
                        f"{int(_delivery_first_response_timeout_seconds(model_timeout_seconds=float(model_timeout), delivery_timeout_seconds=float(timeout)))} seconds."
                    )
                    if attempt_number < max_attempts:
                        _update_trace_retry_state(
                            trace_path,
                            attempt_number=attempt_number,
                            max_attempts=max_attempts,
                            error_type=error_type,
                            error_message=error_message,
                        )
                        _cleanup_delivery_runtime(process, result_queue)
                        time.sleep(_delivery_retry_backoff_seconds(attempt_number))
                        first_response_timed_out = True
                        break
                    _update_trace_retry_state(
                        trace_path,
                        attempt_number=attempt_number,
                        max_attempts=max_attempts,
                        error_type=error_type,
                        error_message=error_message,
                    )
                    error_message = (
                        f"Delivery failed after {attempt_number}/{max_attempts} first-response timeouts. "
                        f"Last error: {error_message}"
                    )
                    _append_trace_failure(trace_path, failure_reason=error_message)
                    _cleanup_delivery_runtime(process, result_queue)
                    raise ModelInvokeTimeout(error_message)
                if last_step_count > 0 and time.monotonic() - last_progress_time >= progress_timeout:
                    process.terminate()
                    process.join(5.0)
                    error_type = "TraceProgressTimeout"
                    error_message = (
                        "Delivery agent stopped making trace progress for "
                        f"{int(progress_timeout)} seconds after reaching step {last_step_count}."
                    )
                    if attempt_number < max_attempts:
                        _update_trace_retry_state(
                            trace_path,
                            attempt_number=attempt_number,
                            max_attempts=max_attempts,
                            error_type=error_type,
                            error_message=error_message,
                        )
                        _cleanup_delivery_runtime(process, result_queue)
                        time.sleep(_delivery_retry_backoff_seconds(attempt_number))
                        progress_timed_out = True
                        break
                    _update_trace_retry_state(
                        trace_path,
                        attempt_number=attempt_number,
                        max_attempts=max_attempts,
                        error_type=error_type,
                        error_message=error_message,
                    )
                    error_message = (
                        f"Delivery failed after {attempt_number}/{max_attempts} trace-progress timeouts. "
                        f"Last error: {error_message}"
                    )
                    _append_trace_failure(trace_path, failure_reason=error_message)
                    _cleanup_delivery_runtime(process, result_queue)
                    raise ModelInvokeTimeout(error_message)
            if first_response_timed_out or progress_timed_out:
                continue
            if process.is_alive():
                process.terminate()
                process.join(5.0)
                _append_trace_failure(trace_path, failure_reason=f"Delivery agent exceeded {int(timeout)} seconds.")
                _cleanup_delivery_runtime(process, result_queue)
                raise ModelInvokeTimeout(f"Delivery agent exceeded {int(timeout)} seconds.")
            try:
                payload = result_queue.get_nowait()
            except queue.Empty:
                if process.exitcode not in (0, None):
                    _append_trace_failure(trace_path, failure_reason=f"Delivery agent exited with code {process.exitcode}.")
                    _cleanup_delivery_runtime(process, result_queue)
                    raise RuntimeError(f"Delivery agent exited with code {process.exitcode}.")
                _append_trace_failure(trace_path, failure_reason="Delivery agent finished without returning a result.")
                _cleanup_delivery_runtime(process, result_queue)
                raise RuntimeError("Delivery agent finished without returning a result.")
            if payload.get("ok") is True:
                result = str(payload.get("result") or "").strip()
                _cleanup_delivery_runtime(process, result_queue)
                return result
            error_type = str(payload.get("error_type") or "").strip()
            error_message = str(payload.get("error") or "Delivery agent failed.").strip()
            if (
                attempt_number < max_attempts
                and _should_retry_transient_delivery_error(error_type=error_type, error_message=error_message)
            ):
                _update_trace_retry_state(
                    trace_path,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                    error_type=error_type,
                    error_message=error_message,
                )
                _cleanup_delivery_runtime(process, result_queue)
                time.sleep(_delivery_retry_backoff_seconds(attempt_number))
                continue
            if _should_retry_transient_delivery_error(error_type=error_type, error_message=error_message):
                _update_trace_retry_state(
                    trace_path,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                    error_type=error_type,
                    error_message=error_message,
                )
                error_message = (
                    f"Delivery failed after {attempt_number}/{max_attempts} transient attempts. "
                    f"Last error: {error_message}"
                )
            _append_trace_failure(trace_path, failure_reason=error_message)
            _cleanup_delivery_runtime(process, result_queue)
            if error_type == "ModelInvokeTimeout":
                raise ModelInvokeTimeout(error_message)
            raise RuntimeError(error_message)
        raise RuntimeError("Delivery agent exhausted retry attempts without returning a result.")
