from __future__ import annotations

from pathlib import Path
from typing import Any

from .aionisdoc_bridge import AionisdocBridge


class AionisdocService:
    def __init__(
        self,
        *,
        repo_root: str,
        bridge: AionisdocBridge,
    ) -> None:
        self._repo_root = str(Path(repo_root).expanduser().resolve())
        self._bridge = bridge

    def compile(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.compile(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_compile",
            doc_action="compile",
            doc_input=input_path,
            result_key="compile_result",
            result=result,
        )

    def run(self, *, input_path: str, registry_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.run(input_path=input_path, registry_path=registry_path, **kwargs)
        payload = self._payload(
            shell_view="doc_run",
            doc_action="run",
            doc_input=input_path,
            result_key="run_result",
            result=result,
        )
        payload["doc_registry"] = registry_path
        return payload

    def execute(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.execute(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_execute",
            doc_action="execute",
            doc_input=input_path,
            result_key="execute_result",
            result=result,
        )

    def build_runtime_handoff(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.build_runtime_handoff(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_runtime_handoff",
            doc_action="runtime_handoff",
            doc_input=input_path,
            result_key="runtime_handoff",
            result=result,
        )

    def build_handoff_store_request(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.build_handoff_store_request(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_handoff_store",
            doc_action="handoff_store",
            doc_input=input_path,
            result_key="handoff_store_request",
            result=result,
        )

    def publish(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.publish(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_publish",
            doc_action="publish",
            doc_input=input_path,
            result_key="publish_result",
            result=result,
        )

    def recover(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.recover(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_recover",
            doc_action="recover",
            doc_input=input_path,
            result_key="recover_result",
            result=result,
        )

    def resume(self, *, input_path: str, **kwargs: Any) -> dict[str, Any]:
        result = self._bridge.resume(input_path=input_path, **kwargs)
        return self._payload(
            shell_view="doc_resume",
            doc_action="resume",
            doc_input=input_path,
            result_key="resume_result",
            result=result,
        )

    def _payload(
        self,
        *,
        shell_view: str,
        doc_action: str,
        doc_input: str,
        result_key: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "shell_view": shell_view,
            "doc_action": doc_action,
            "doc_input": doc_input,
            "repo_root": self._repo_root,
            "status": self._status_from_result(result),
            result_key: result,
        }

    @staticmethod
    def _status_from_result(result: dict[str, Any]) -> str:
        explicit_status = str(result.get("status") or "").strip()
        if explicit_status:
            return explicit_status
        summary = result.get("summary")
        if isinstance(summary, dict) and bool(summary.get("has_errors")):
            return "failed"
        diagnostics = result.get("diagnostics")
        if isinstance(diagnostics, list):
            for diagnostic in diagnostics:
                if isinstance(diagnostic, dict) and str(diagnostic.get("severity") or "").strip().lower() == "error":
                    return "failed"
        return "ok"
