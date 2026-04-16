from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DeliveryExecutionResult:
    execution_summary: str = ""
    changed_target_hints: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    artifact_root: str = ""
    artifact_paths: list[str] = field(default_factory=list)
    artifact_kind: str = ""
    preview_command: str = ""
    trace_path: str = ""
    validation_command: str = ""
    validation_summary: str = ""
    validation_ok: bool | None = None
    failure_reason: str = ""
    raw_result_preview: str = ""
