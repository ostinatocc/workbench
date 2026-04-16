from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .launcher_state import launcher_paths


@dataclass(frozen=True)
class LiveTimingPhase:
    name: str
    duration_seconds: float


@dataclass
class LiveTimingRecord:
    task_id: str
    phases: list[LiveTimingPhase] = field(default_factory=list)

    def add_phase(self, name: str, duration_seconds: float) -> None:
        self.phases.append(
            LiveTimingPhase(
                name=str(name).strip(),
                duration_seconds=round(max(float(duration_seconds), 0.0), 3),
            )
        )

    @property
    def total_duration_seconds(self) -> float:
        return round(sum(phase.duration_seconds for phase in self.phases), 3)

    def summary(self) -> str:
        phase_summary = " ".join(
            f"{phase.name}={phase.duration_seconds:.3f}s" for phase in self.phases if phase.name
        ).strip()
        if not phase_summary:
            return f"task={self.task_id} total={self.total_duration_seconds:.3f}s"
        return f"task={self.task_id} {phase_summary} total={self.total_duration_seconds:.3f}s"


def infer_live_mode(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    mode = str(source.get("AIONIS_LIVE_MODE") or "").strip()
    return mode or "targeted_fix"


def _candidate_live_profile_paths(*, home: Path | None = None, repo_root: str | Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if home is not None:
        candidates.append(launcher_paths(home).live_profile)
    if repo_root is not None:
        repo_home = Path(repo_root) / ".real-live-home"
        candidates.append(launcher_paths(repo_home).live_profile)
    candidates.append(launcher_paths().live_profile)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for item in candidates:
        resolved = item.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(item)
    return deduped


def resolve_live_profile_snapshot_path(
    *,
    home: Path | None = None,
    repo_root: str | Path | None = None,
) -> Path:
    for candidate in _candidate_live_profile_paths(home=home, repo_root=repo_root):
        if candidate.exists():
            return candidate
    return _candidate_live_profile_paths(home=home, repo_root=repo_root)[0]


def load_live_profile_snapshot(
    home: Path | None = None,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_live_profile_snapshot_path(home=home, repo_root=repo_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_live_profile_snapshot(payload: dict[str, Any], home: Path | None = None) -> Path:
    path = launcher_paths(home).live_profile
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
