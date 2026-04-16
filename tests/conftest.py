from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _isolate_provider_environment(monkeypatch):
    monkeypatch.setenv("AIONIS_LOAD_ENV_FILES", "0")
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "OPENROUTER_MODEL",
        "WORKBENCH_MODEL",
        "AIONIS_PROVIDER_PROFILE",
        "AIONIS_RUNTIME_ROOT",
        "AIONIS_CORE_DIR",
        "AIONISDOC_PACKAGE_ROOT",
        "AIONISDOC_WORKSPACE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


@dataclass
class FakeResult:
    task_id: str = "task-123"
    session_path: str = "/tmp/session.json"
    content: str = "ok"
    runner: str = "ingest"
    session: dict[str, Any] = field(default_factory=dict)
    canonical_surface: dict[str, Any] = field(default_factory=dict)
    canonical_views: dict[str, Any] = field(default_factory=dict)
    aionis: dict[str, Any] = field(default_factory=dict)
    trace_summary: dict[str, Any] = field(default_factory=dict)


class FakeWorkbench:
    def __init__(self, repo_root: str | None = None) -> None:
        self.repo_root = repo_root
