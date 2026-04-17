from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import queue
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig
from .execution_host import (
    ModelInvokeTimeout,
    _append_trace_failure,
    _cleanup_delivery_runtime,
    _delivery_artifact_ready,
    _delivery_first_response_timeout_seconds,
    _delivery_progress_timeout_seconds,
    _delivery_retry_backoff_seconds,
    _reset_delivery_trace,
    _should_retry_transient_delivery_error,
    _trace_has_steps,
    _trace_step_count,
    _update_trace_retry_state,
)
from .tracing import TraceRecorder
from .utils import stringify_result
from .roles import builtin_subagents

OPENAI_AGENTS_EXECUTION_HOST_NAME = "openai_agents_local_shell"
OPENAI_AGENTS_EXECUTION_RUNTIME = "openai_agents"
OPENAI_AGENTS_EXECUTION_BACKEND = "Agent+Runner"


class OpenAIAgentsModelInvokeTimeout(TimeoutError):
    pass


def _timeout_signal_handler(signum, frame):  # type: ignore[no-untyped-def]
    raise OpenAIAgentsModelInvokeTimeout("OpenAI Agents SDK model invocation exceeded the configured timeout.")


def _openai_agents_sdk_available() -> bool:
    return importlib.util.find_spec("agents") is not None


@dataclass
class OpenAIAgentsPreparedAgent:
    system_prompt: str
    root_dir: str
    memory_sources: list[str]
    timeout_pressure: bool
    use_builtin_subagents: bool
    delivery_mode: bool = False


@dataclass
class OpenAIAgentsInvokeResult:
    final_output: str
    delegation_returns: list[dict[str, Any]]
    role_sequence: list[str]


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return text.strip()


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
    host = OpenAIAgentsExecutionHost(config=config, trace=trace)
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
        artifact = Path(root_dir) / "dist" / "index.html"
        if artifact.exists():
            result_queue.put(
                {
                    "ok": True,
                    "result": "Build completed and delivery artifact is ready.",
                    "trace_path": trace_path,
                }
            )
            return
        result_queue.put({"ok": True, "result": stringify_result(result), "trace_path": trace_path})
    except Exception as exc:  # pragma: no cover - exercised via parent retry behavior
        result_queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc).strip() or type(exc).__name__,
                "trace_path": trace_path,
            }
        )


class OpenAIAgentsExecutionHost:
    def __init__(self, *, config: WorkbenchConfig, trace: Any) -> None:
        self._config = config
        self._trace = trace

    def _dependency_ready(self) -> bool:
        return _openai_agents_sdk_available()

    def _provider_ready(self) -> bool:
        return self._config.provider in {"openai", "openrouter"}

    def _dependency_reason(self) -> str | None:
        if not self._dependency_ready():
            return "execution_host_dependency_missing"
        if not self._config.api_key:
            return "model_credentials_missing"
        if not self._provider_ready():
            return "execution_host_provider_unsupported"
        return None

    def describe(self) -> dict[str, Any]:
        health_reason = self._dependency_reason()
        supports_live_tasks = health_reason is None
        health_status = "available" if supports_live_tasks else "offline"
        return {
            "name": OPENAI_AGENTS_EXECUTION_HOST_NAME,
            "execution_runtime": OPENAI_AGENTS_EXECUTION_RUNTIME,
            "backend": OPENAI_AGENTS_EXECUTION_BACKEND,
            "model_provider": self._config.provider,
            "model_available": bool(self._config.api_key),
            "supports_live_tasks": supports_live_tasks,
            "mode": "live_enabled" if supports_live_tasks else "inspect_only",
            "health_status": health_status,
            "health_reason": health_reason,
            "degraded_reason": health_reason,
        }

    def supports_live_tasks(self) -> bool:
        return self._dependency_reason() is None

    def live_app_planner_timeout_seconds(self) -> float:
        return max(self._config.model_timeout_seconds or 45.0, 45.0)

    def live_app_planner_max_completion_tokens(self) -> int:
        return 220

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

    def _import_agents_runtime(self) -> tuple[Any, Any, Any, Any, Any]:
        from agents import Agent, Runner, function_tool, set_default_openai_client, set_tracing_disabled

        return Agent, Runner, function_tool, set_default_openai_client, set_tracing_disabled

    def _configure_openai_agents_client(self) -> None:
        if not self._config.api_key:
            raise ValueError("OpenAI Agents execution host requires configured credentials.")
        from openai import AsyncOpenAI

        _, _, _, set_default_openai_client, set_tracing_disabled = self._import_agents_runtime()
        client = AsyncOpenAI(
            api_key=self._config.api_key,
            base_url=self._config.base_url,
        )
        set_default_openai_client(client, use_for_tracing=False)
        set_tracing_disabled(True)
        return client

    def _use_explicit_chat_completions_model(self) -> bool:
        if self._config.provider == "openrouter":
            return True
        base_url = str(self._config.base_url or "").strip().rstrip("/")
        if not base_url:
            return False
        return "api.openai.com" not in base_url

    def _runner_model(self, openai_client: Any) -> Any:
        if not self._use_explicit_chat_completions_model():
            return self._config.model
        from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

        return OpenAIChatCompletionsModel(self._config.model, openai_client)

    def _record_tool_result(
        self,
        *,
        recorder: TraceRecorder,
        tool_name: str,
        tool_input: dict[str, Any],
        result: Any = None,
        error: str | None = None,
    ) -> None:
        recorder.record(
            tool_name=tool_name,
            tool_call_id=None,
            tool_input=tool_input,
            status="error" if error else "success",
            result=result,
            error=error,
        )

    def _build_function_tools(
        self,
        *,
        root_dir: str,
        recorder: TraceRecorder,
        delivery_mode: bool,
    ) -> list[Any]:
        _, _, function_tool, _, _ = self._import_agents_runtime()
        workspace_root = Path(root_dir)

        def _resolve_path(path: str) -> Path:
            candidate = (path or "").strip()
            if not candidate:
                raise ValueError("path is required")
            resolved = (workspace_root / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
            if workspace_root not in resolved.parents and resolved != workspace_root:
                raise ValueError("path escapes the configured workspace root")
            return resolved

        @function_tool
        def exec_command(command: str, cwd: str = ".") -> str:
            """Run a shell command inside the task workspace.

            Args:
                command: Shell command to execute.
                cwd: Relative working directory inside the workspace.
            """

            normalized_command = command
            if delivery_mode:
                from .tracing import sanitize_delivery_execute_command

                normalized_command = sanitize_delivery_execute_command(command)
            working_dir = _resolve_path(cwd)
            env = os.environ.copy()
            env["PWD"] = str(working_dir)
            completed = subprocess.run(
                normalized_command,
                cwd=working_dir,
                shell=True,
                capture_output=True,
                text=True,
                env=env,
            )
            output = "\n".join(
                part.strip() for part in [completed.stdout, completed.stderr] if isinstance(part, str) and part.strip()
            ).strip()
            payload = {
                "command": normalized_command,
                "cwd": str(working_dir),
                "returncode": completed.returncode,
                "output": output,
            }
            if completed.returncode != 0:
                self._record_tool_result(
                    recorder=recorder,
                    tool_name="execute",
                    tool_input={"command": normalized_command, "cwd": str(working_dir)},
                    error=json.dumps(payload, ensure_ascii=False),
                )
                raise RuntimeError(json.dumps(payload, ensure_ascii=False))
            self._record_tool_result(
                recorder=recorder,
                tool_name="execute",
                tool_input={"command": normalized_command, "cwd": str(working_dir)},
                result=payload,
            )
            return json.dumps(payload, ensure_ascii=False)

        @function_tool
        def read_file(path: str) -> str:
            """Read a UTF-8 text file from the task workspace.

            Args:
                path: Relative path to the file inside the workspace.
            """

            resolved = _resolve_path(path)
            content = resolved.read_text(encoding="utf-8")
            self._record_tool_result(
                recorder=recorder,
                tool_name="read_file",
                tool_input={"path": str(resolved)},
                result={"path": str(resolved), "chars": len(content)},
            )
            return content

        @function_tool
        def write_file(path: str, content: str) -> str:
            """Write a UTF-8 text file inside the task workspace.

            Args:
                path: Relative path to the file inside the workspace.
                content: Full replacement file content.
            """

            resolved = _resolve_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            payload = {"path": str(resolved), "chars": len(content)}
            self._record_tool_result(
                recorder=recorder,
                tool_name="write_file",
                tool_input={"path": str(resolved)},
                result=payload,
            )
            return json.dumps(payload, ensure_ascii=False)

        @function_tool
        def list_files(path: str = ".") -> str:
            """List files under a workspace directory.

            Args:
                path: Relative directory path inside the workspace.
            """

            resolved = _resolve_path(path)
            if not resolved.exists():
                raise ValueError(f"path does not exist: {path}")
            if resolved.is_file():
                items = [resolved.relative_to(workspace_root).as_posix()]
            else:
                items = sorted(
                    entry.relative_to(workspace_root).as_posix()
                    for entry in resolved.rglob("*")
                    if entry.is_file()
                )[:200]
            payload = {"path": str(resolved), "items": items}
            self._record_tool_result(
                recorder=recorder,
                tool_name="list_files",
                tool_input={"path": str(resolved)},
                result={"path": str(resolved), "count": len(items)},
            )
            return json.dumps(payload, ensure_ascii=False)

        return [exec_command, read_file, write_file, list_files]

    def _response_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, OpenAIAgentsInvokeResult):
            return value.final_output
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

    def _specialist_specs(self) -> dict[str, dict[str, str]]:
        return {item["name"]: item for item in builtin_subagents()}

    def _coerce_delegation_packets(self, payload: dict[str, Any], *, memory_sources: list[str]) -> list[dict[str, Any]]:
        raw_packets = payload.get("delegation_packets")
        packets: list[dict[str, Any]] = []
        if isinstance(raw_packets, list):
            for item in raw_packets:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip()
                if role not in self._specialist_specs():
                    continue
                packets.append(
                    {
                        "role": role,
                        "mission": str(item.get("mission") or "").strip(),
                        "working_set": [
                            str(value).strip()
                            for value in list(item.get("working_set") or [])[:8]
                            if str(value).strip()
                        ],
                        "acceptance_checks": [
                            str(value).strip()
                            for value in list(item.get("acceptance_checks") or [])[:6]
                            if str(value).strip()
                        ],
                        "output_contract": str(item.get("output_contract") or "").strip(),
                    }
                )
        if packets:
            return packets
        task = ""
        messages = payload.get("messages")
        if isinstance(messages, list):
            for item in messages:
                if isinstance(item, dict) and str(item.get("role") or "").strip() == "user":
                    task = str(item.get("content") or "").strip()
                    if task:
                        break
        defaults: list[dict[str, Any]] = []
        default_working_set = [value.strip() for value in memory_sources[:8] if isinstance(value, str) and value.strip()]
        for role in ("investigator", "implementer", "verifier"):
            if role == "investigator":
                mission = f"Inspect the repository and narrow the likely failure surface for: {task}".strip()
                output_contract = "Return a concise diagnosis, likely cause, and the narrowest working set."
            elif role == "implementer":
                mission = f"Implement the smallest correct change for: {task}".strip()
                output_contract = "Return the touched files, code-level summary, and follow-up checks."
            else:
                mission = f"Validate the attempted fix for: {task}".strip()
                output_contract = "Return exact validation commands, pass/fail result, and residual risks."
            defaults.append(
                {
                    "role": role,
                    "mission": mission,
                    "working_set": list(default_working_set),
                    "acceptance_checks": [],
                    "output_contract": output_contract,
                }
            )
        return defaults

    def _specialist_summary(self, text: str) -> tuple[str, list[str]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "No output returned.", []
        summary = lines[0][:240]
        evidence = lines[1:4] if len(lines) > 1 else [summary]
        return summary, evidence[:4]

    def _run_agent_sync(
        self,
        *,
        agent_name: str,
        instructions: str,
        model: Any,
        tools: list[Any],
        user_input: str,
        timeout_seconds: float,
    ) -> Any:
        Agent, Runner, _, _, _ = self._import_agents_runtime()
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout_signal_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            runner_agent = Agent(
                name=agent_name,
                instructions=instructions,
                model=model,
                tools=tools,
            )
            return Runner.run_sync(runner_agent, user_input)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _run_builtin_specialists(
        self,
        *,
        agent: OpenAIAgentsPreparedAgent,
        payload: dict[str, Any],
        user_input: str,
        tools: list[Any],
        timeout_budget: float,
        model: Any,
    ) -> dict[str, Any]:
        packets = self._coerce_delegation_packets(payload, memory_sources=agent.memory_sources)
        specs = self._specialist_specs()
        delegation_returns: list[dict[str, Any]] = []
        role_sequence: list[str] = []
        for packet in packets:
            role = packet["role"]
            spec = specs[role]
            prior_context: list[str] = []
            if delegation_returns:
                prior_context.append("Previous specialist handoffs:")
                for item in delegation_returns[-2:]:
                    prior_context.append(f"- {item['role']}: {item['summary']}")
            packet_context = [
                f"Role mission: {packet['mission']}",
                *([f"Working set: {', '.join(packet['working_set'][:8])}"] if packet["working_set"] else []),
                *([f"Acceptance checks: {'; '.join(packet['acceptance_checks'][:6])}"] if packet["acceptance_checks"] else []),
                *([f"Output contract: {packet['output_contract']}"] if packet["output_contract"] else []),
            ]
            instructions = "\n\n".join(
                [
                    agent.system_prompt,
                    spec["system_prompt"],
                    *prior_context,
                    *packet_context,
                    "Return a concise execution summary first, then the most relevant evidence or commands you used.",
                    "Use the available local tools directly. Keep your working set narrow and avoid broad rewrites.",
                ]
            )
            result = self._run_agent_sync(
                agent_name=f"Aionis Workbench {role}",
                instructions=instructions,
                model=model,
                tools=tools,
                user_input=user_input,
                timeout_seconds=timeout_budget,
            )
            output_text = self._response_text(getattr(result, "final_output", result)).strip()
            summary, evidence = self._specialist_summary(output_text)
            run_payload = {
                "role": role,
                "status": "success",
                "summary": summary,
                "evidence": evidence,
                "working_set": list(packet["working_set"]),
                "acceptance_checks": list(packet["acceptance_checks"]),
            }
            delegation_returns.append(run_payload)
            role_sequence.append(role)
            self._record_tool_result(
                recorder=self._trace,
                tool_name="workbench.model",
                tool_input={
                    "model": self._config.model,
                    "role": role,
                    "messages": len(payload.get("messages") or []),
                    "tools": len(tools),
                    "root_dir": agent.root_dir,
                },
                result=output_text,
            )
        final_output = "\n".join(f"[{item['role']}] {item['summary']}" for item in delegation_returns)
        return {
            "final_output": final_output.strip(),
            "delegation_returns": delegation_returns,
            "role_sequence": role_sequence,
        }

    def _extract_json_payload(self, text: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        raw = fenced.group(1) if fenced else text
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("OpenAI Agents execution host expected a JSON object response.")
        return payload

    def probe_live_model_auth(self) -> dict[str, Any]:
        if not self.supports_live_tasks():
            raise ValueError(
                "OpenAI Agents auth probe requires a supported provider, configured credentials, and installed openai-agents dependency"
            )
        timeout_seconds = min(max(self._config.model_timeout_seconds or 45.0, 15.0), 20.0)
        payload: dict[str, Any] | None = None
        last_timeout: Exception | None = None
        for attempt in range(3):
            try:
                payload = self._run_json_agent(
                    system_prompt='Return JSON only. Produce exactly {"ok": true}. Do not include markdown fences or extra text.',
                    user_input="Return the JSON object now.",
                    timeout_seconds=timeout_seconds,
                    agent_name="Workbench auth probe",
                )
                break
            except OpenAIAgentsModelInvokeTimeout as exc:
                last_timeout = exc
                if attempt >= 2:
                    raise
                time.sleep(0.25)
        if payload is None and last_timeout is not None:
            raise last_timeout
        if payload.get("ok") is not True:
            raise ValueError("openai-agents auth probe did not return ok=true")
        return payload

    def _run_json_agent(
        self,
        *,
        system_prompt: str,
        user_input: str,
        timeout_seconds: float,
        agent_name: str,
    ) -> dict[str, Any]:
        openai_client = self._configure_openai_agents_client()
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout_signal_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            agent = Agent(
                name=agent_name,
                instructions=system_prompt,
                model=self._runner_model(openai_client),
            )
            result = Runner.run_sync(agent, user_input)
            return self._extract_json_payload(self._response_text(getattr(result, "final_output", result)))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _unsupported(self, surface: str) -> None:
        raise NotImplementedError(
            f"{surface} is not implemented for WORKBENCH_EXECUTION_HOST='openai_agents' yet. "
            "Phase 2 currently provides host metadata and auth-probe wiring only."
        )

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
        return self._run_json_agent(
            system_prompt=system,
            user_input=f"Project request: {prompt}\nReturn only the JSON object.",
            timeout_seconds=self.live_app_planner_timeout_seconds(),
            agent_name="Workbench live planner",
        )

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
        requested_status: str = "",
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
            "Treat requested_status and any explicit criteria_scores as high-signal operator input. "
            "If requested_status is passed and explicit criteria_scores satisfy the thresholds, preserve that unless blocker_notes or the latest_execution_attempt directly contradict it. "
            "If blocker_notes are present or a criterion falls below its threshold, bias toward failed. "
            "If execution_focus is present, treat it as the highest-signal summary of the most recent bounded execution attempt. "
            "Do not include markdown fences or explanation outside the JSON object."
        )
        return self._run_json_agent(
            system_prompt=system,
            user_input=json.dumps(
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
            timeout_seconds=self.live_app_evaluator_timeout_seconds(),
            agent_name="Workbench live evaluator",
        )

    def negotiate_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any] | None = None,
        planned_sprints: list[dict[str, Any]] | None = None,
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
        return self._run_json_agent(
            system_prompt=system,
            user_input=json.dumps(
                {
                    "product_spec": product_spec,
                    "sprint_contract": sprint_contract,
                    "latest_evaluation": latest_evaluation,
                    "planned_sprints": planned_sprints,
                    "objections": list(objections or []),
                },
                ensure_ascii=False,
            ),
            timeout_seconds=self.live_app_negotiator_timeout_seconds(),
            agent_name="Workbench live negotiator",
        )

    def revise_sprint_live(
        self,
        *,
        product_spec: dict[str, Any],
        sprint_contract: dict[str, Any],
        latest_evaluation: dict[str, Any] | None = None,
        latest_negotiation_round: dict[str, Any] | None = None,
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
        return self._run_json_agent(
            system_prompt=system,
            user_input=json.dumps(
                {
                    "product_spec": product_spec,
                    "sprint_contract": sprint_contract,
                    "latest_evaluation": latest_evaluation,
                    "latest_negotiation_round": latest_negotiation_round,
                    "revision_notes": list(revision_notes or []),
                },
                ensure_ascii=False,
            ),
            timeout_seconds=self.live_app_revisor_timeout_seconds(),
            agent_name="Workbench live revisor",
        )

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
        return self._run_json_agent(
            system_prompt=system,
            user_input=json.dumps(
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
            timeout_seconds=self.live_app_planner_timeout_seconds(),
            agent_name="Workbench live replanner",
        )

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
        return self._run_json_agent(
            system_prompt=system,
            user_input=json.dumps(
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
            timeout_seconds=self.live_app_generator_timeout_seconds(),
            agent_name="Workbench live generator",
        )

    def build_agent(
        self,
        *,
        system_parts: list[str | None],
        memory_sources: list[str],
        timeout_pressure: bool,
        root_dir: str | None = None,
        model_timeout_seconds_override: float | None = None,
        use_builtin_subagents: bool = True,
    ) -> Any:
        if not self.supports_live_tasks():
            raise ValueError(
                "OpenAI Agents execution host requires a supported provider, configured credentials, and installed openai-agents dependency"
            )
        return OpenAIAgentsPreparedAgent(
            system_prompt="\n\n".join(part for part in system_parts if part),
            root_dir=root_dir or self._config.repo_root,
            memory_sources=list(memory_sources),
            timeout_pressure=timeout_pressure,
            use_builtin_subagents=use_builtin_subagents,
            delivery_mode=False,
        )

    def build_delivery_agent(
        self,
        *,
        system_parts: list[str | None],
        memory_sources: list[str],
        root_dir: str | None = None,
        model_timeout_seconds_override: float | None = None,
    ) -> Any:
        if not self.supports_live_tasks():
            raise ValueError(
                "OpenAI Agents execution host requires a supported provider, configured credentials, and installed openai-agents dependency"
            )
        delivery_parts = [part for part in system_parts if part]
        delivery_parts.append(
            "Delivery mode is active. Prefer bounded edits inside the task workspace, keep the working set narrow, and run the smallest validation/build step needed to produce a previewable artifact."
        )
        return OpenAIAgentsPreparedAgent(
            system_prompt="\n\n".join(delivery_parts),
            root_dir=root_dir or self._config.repo_root,
            memory_sources=list(memory_sources),
            timeout_pressure=False,
            use_builtin_subagents=False,
            delivery_mode=True,
        )

    def invoke(self, agent: Any, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> Any:
        if not isinstance(agent, OpenAIAgentsPreparedAgent):
            raise TypeError("OpenAIAgentsExecutionHost.invoke expects an OpenAIAgentsPreparedAgent")
        if not self.supports_live_tasks():
            raise ValueError(
                "OpenAI Agents execution host requires a supported provider, configured credentials, and installed openai-agents dependency"
            )
        Agent, Runner, _, _, _ = self._import_agents_runtime()
        openai_client = self._configure_openai_agents_client()
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("invoke payload must contain at least one message")
        user_parts = [
            str(item.get("content") or "").strip()
            for item in messages
            if isinstance(item, dict) and str(item.get("role") or "").strip() == "user"
        ]
        user_input = "\n\n".join(part for part in user_parts if part).strip()
        if not user_input:
            raise ValueError("invoke payload did not include a usable user message")

        self._trace.reset()
        tools = self._build_function_tools(
            root_dir=agent.root_dir,
            recorder=self._trace,
            delivery_mode=agent.delivery_mode,
        )
        instructions = agent.system_prompt
        if agent.memory_sources:
            instructions += "\n\nRelevant memory sources:\n" + "\n".join(f"- {value}" for value in agent.memory_sources[:16])
        instructions += (
            "\n\nUse the available local tools to inspect files, edit files, and run commands inside the workspace. "
            "Prefer small, direct edits over broad rewrites."
        )
        timeout_budget = timeout_seconds or self._config.model_timeout_seconds or 45.0
        runner_model = self._runner_model(openai_client)
        if agent.use_builtin_subagents:
            return self._run_builtin_specialists(
                agent=agent,
                payload=payload,
                user_input=user_input,
                tools=tools,
                timeout_budget=timeout_budget,
                model=runner_model,
            )
        result = self._run_agent_sync(
            agent_name="Aionis Workbench OpenAI Agents Host",
            instructions=instructions,
            model=runner_model,
            tools=tools,
            user_input=user_input,
            timeout_seconds=timeout_budget,
        )
        final_output = getattr(result, "final_output", result)
        self._record_tool_result(
            recorder=self._trace,
            tool_name="workbench.model",
            tool_input={
                "model": self._config.model,
                "messages": len(messages),
                "tools": len(tools),
                "root_dir": agent.root_dir,
            },
            result=final_output,
        )
        return final_output

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
            if error_type in {"ModelInvokeTimeout", "OpenAIAgentsModelInvokeTimeout"}:
                raise ModelInvokeTimeout(error_message)
            raise RuntimeError(error_message)
        raise RuntimeError("Delivery agent exhausted retry attempts without returning a result.")
