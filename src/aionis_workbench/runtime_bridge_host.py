from __future__ import annotations

import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .aionis_bridge import AionisWorkbenchBridge, BridgeDefaults
from .config import AionisConfig
from .tracing import TraceStep


DEFAULT_RUNTIME_HEALTH_PROBE_TIMEOUT_SECONDS = 2.0


def _runtime_health_status(
    base_url: str,
    *,
    timeout_seconds: float = DEFAULT_RUNTIME_HEALTH_PROBE_TIMEOUT_SECONDS,
) -> tuple[str, str | None]:
    if not base_url:
        return "offline", "runtime_base_url_missing"
    try:
        with urlopen(base_url.rstrip("/") + "/health", timeout=timeout_seconds) as response:
            if 200 <= response.status < 300:
                return "available", None
            return "degraded", f"runtime_health_http_{response.status}"
    except (OSError, URLError, ValueError):
        return "degraded", "runtime_health_unreachable"


class AionisRuntimeHost:
    def __init__(self, *, config: AionisConfig) -> None:
        self._config = config
        self._health_cache: tuple[float, tuple[str, str | None]] | None = None
        self._bridge = AionisWorkbenchBridge(
            base_url=config.base_url,
            defaults=BridgeDefaults(
                tenant_id=config.tenant_id,
                scope=config.scope,
                actor=config.actor,
            ),
        )

    def _describe_health(self) -> tuple[str, str | None]:
        cached = self._health_cache
        now = time.monotonic()
        if cached and (now - cached[0]) < 5.0:
            return cached[1]
        status = _runtime_health_status(self._config.base_url)
        self._health_cache = (now, status)
        return status

    def describe(self) -> dict[str, Any]:
        health_status, health_reason = self._describe_health()
        return {
            "name": "aionis_runtime_host",
            "base_url": self._config.base_url,
            "tenant_id": self._config.tenant_id,
            "scope": self._config.scope,
            "actor": self._config.actor,
            "bridge_configured": bool(self._config.base_url),
            "replay_mode": "configured" if bool(self._config.base_url) else "disabled",
            "health_status": health_status,
            "health_reason": health_reason,
            "degraded_reason": health_reason,
        }

    def start_task(self, *, task_id: str, text: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._bridge.start_task(task_id=task_id, text=text, context=context)

    def inspect_task_context(self, *, task_id: str, text: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._bridge.inspect_task_context(task_id=task_id, text=text, context=context)

    def plan_task_start(self, *, task_id: str, text: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._bridge.plan_task_start(task_id=task_id, text=text, context=context)

    def open_task_session(
        self,
        *,
        task_id: str,
        text: str,
        session_id: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        return self._bridge.open_task_session(
            task_id=task_id,
            text=text,
            session_id=session_id,
            title=title,
            summary=summary,
            metadata=metadata,
        )

    def resume_task(self, *, task_id: str, repo_root: str) -> dict[str, Any]:
        return self._bridge.resume_task(task_id=task_id, repo_root=repo_root)

    def continuity_review_pack(
        self,
        *,
        task_id: str,
        repo_root: str,
        file_path: str | None = None,
        handoff_kind: str = "task_handoff",
    ) -> dict[str, Any]:
        return self._bridge.continuity_review_pack(
            task_id=task_id,
            repo_root=repo_root,
            file_path=file_path,
            handoff_kind=handoff_kind,
        )

    def evolution_review_pack(
        self,
        *,
        task_id: str,
        text: str,
        repo_root: str,
        target_files: list[str],
    ) -> dict[str, Any]:
        return self._bridge.evolution_review_pack(
            task_id=task_id,
            text=text,
            repo_root=repo_root,
            target_files=target_files,
        )

    def pause_task(
        self,
        *,
        task_id: str,
        summary: str,
        handoff_text: str,
        repo_root: str,
        target_files: list[str],
        next_action: str,
        execution_result_summary: dict[str, Any],
        execution_evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._bridge.pause_task(
            task_id=task_id,
            summary=summary,
            handoff_text=handoff_text,
            repo_root=repo_root,
            target_files=target_files,
            next_action=next_action,
            execution_result_summary=execution_result_summary,
            execution_evidence=execution_evidence,
        )

    def complete_task(
        self,
        *,
        task_id: str,
        text: str,
        summary: str,
        output: str,
        tool_steps: list[TraceStep],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self._bridge.complete_task(
            task_id=task_id,
            text=text,
            summary=summary,
            output=output,
            tool_steps=tool_steps,
            metadata=metadata,
        )

    def record_task(
        self,
        *,
        task_id: str,
        text: str,
        summary: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self._bridge.record_task(
            task_id=task_id,
            text=text,
            summary=summary,
            metadata=metadata,
        )
