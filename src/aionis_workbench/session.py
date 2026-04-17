from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .app_harness_models import AppHarnessState
from .execution_packet import (
    ExecutionPacket,
    ExecutionPacketSummary,
    InstrumentationSummary,
    MaintenanceSummary,
    PatternSignalSummary,
    PlannerPacket,
    RoutingSignalSummary,
    StrategySummary,
    WorkflowSignalSummary,
)
from .reviewer_contracts import ReviewPackSummary


@dataclass
class DelegationPacket:
    role: str
    mission: str
    working_set: list[str] = field(default_factory=list)
    acceptance_checks: list[str] = field(default_factory=list)
    output_contract: str = ""
    preferred_artifact_refs: list[str] = field(default_factory=list)
    inherited_evidence: list[str] = field(default_factory=list)
    routing_reason: str = ""


@dataclass
class DelegationReturn:
    role: str
    status: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    working_set: list[str] = field(default_factory=list)
    acceptance_checks: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    handoff_text: str = ""


@dataclass
class CollaborationPattern:
    kind: str
    role: str
    summary: str
    reuse_hint: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    task_signature: str = ""
    task_family: str = ""
    error_family: str = ""
    affinity_level: str = "broader_similarity"


@dataclass
class ArtifactReference:
    artifact_id: str
    kind: str
    role: str
    summary: str
    path: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ForgetEntry:
    value: str
    reason: str
    state: str = "backlog"
    hits: int = 1


@dataclass
class SessionState:
    task_id: str
    goal: str
    repo_root: str
    project_identity: str = ""
    project_scope: str = ""
    status: str = "pending"
    target_files: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    shared_memory: list[str] = field(default_factory=list)
    working_memory: list[str] = field(default_factory=list)
    promoted_insights: list[str] = field(default_factory=list)
    forgetting_backlog: list[ForgetEntry] = field(default_factory=list)
    delegation_packets: list[DelegationPacket] = field(default_factory=list)
    delegation_returns: list[DelegationReturn] = field(default_factory=list)
    collaboration_patterns: list[CollaborationPattern] = field(default_factory=list)
    artifacts: list[ArtifactReference] = field(default_factory=list)
    selected_strategy_profile: str = "broad_discovery"
    selected_validation_style: str = "targeted_then_expand"
    selected_artifact_budget: int = 6
    selected_memory_source_limit: int = 14
    selected_trust_signal: str = "broader_similarity"
    selected_task_family: str = ""
    selected_family_scope: str = "broader_similarity"
    selected_family_candidate_count: int = 0
    selected_role_sequence: list[str] = field(default_factory=list)
    selected_pattern_summaries: list[str] = field(default_factory=list)
    execution_packet: ExecutionPacket | None = None
    execution_packet_summary: ExecutionPacketSummary | None = None
    continuity_review_pack: ReviewPackSummary | None = None
    evolution_review_pack: ReviewPackSummary | None = None
    app_harness_state: AppHarnessState | None = None
    planner_packet: PlannerPacket | None = None
    strategy_summary: StrategySummary | None = None
    pattern_signal_summary: PatternSignalSummary | None = None
    workflow_signal_summary: WorkflowSignalSummary | None = None
    routing_signal_summary: RoutingSignalSummary | None = None
    maintenance_summary: MaintenanceSummary | None = None
    instrumentation_summary: InstrumentationSummary | None = None
    continuity_snapshot: dict[str, object] = field(default_factory=dict)
    context_layers_snapshot: dict[str, list[str]] = field(default_factory=dict)
    last_trace_summary: dict[str, int] = field(default_factory=dict)
    last_validation_result: dict[str, object] = field(default_factory=dict)
    last_result_preview: str = ""
    aionis_replay_run_id: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def session_signal_score(session: SessionState) -> int:
    score = 0
    if session.target_files:
        score += 2
    if session.validation_commands:
        score += 2
    if session.promoted_insights:
        score += 4
    if session.delegation_returns:
        score += 4
    if session.collaboration_patterns:
        score += 5
    if session.artifacts:
        score += 4
    if session.continuity_snapshot:
        score += 3
    if any(
        isinstance(item, str) and item.startswith("Validation passed: ")
        for item in session.promoted_insights
    ):
        score += 3
    if any(
        isinstance(item, str) and item.startswith("Validation failed command: ")
        for item in session.promoted_insights
    ):
        score += 1
    if session.last_trace_summary.get("ingested"):
        score += 1
    if not session.promoted_insights and not session.delegation_returns:
        score -= 3
    score -= sum(1 for item in session.forgetting_backlog if item.state == "evicted")
    return score


def add_forgetting_entry(
    session: SessionState,
    *,
    value: str,
    reason: str,
) -> None:
    cleaned = value.strip()
    if not cleaned:
        return
    for entry in session.forgetting_backlog:
        if entry.value == cleaned:
            entry.hits += 1
            entry.reason = reason
            if entry.hits >= 3:
                entry.state = "evicted"
            elif entry.hits >= 2:
                entry.state = "suppressed"
            else:
                entry.state = "backlog"
            return
    session.forgetting_backlog.append(ForgetEntry(value=cleaned, reason=reason))


def forgetting_state_map(session: SessionState) -> dict[str, ForgetEntry]:
    return {item.value: item for item in session.forgetting_backlog if item.value}


def forgetting_signal_summary(
    session: SessionState,
    *,
    linked_values: list[str] | None = None,
) -> dict[str, int]:
    linked = [item.strip() for item in (linked_values or []) if isinstance(item, str) and item.strip()]
    suppressed_count = 0
    evicted_count = 0
    linked_suppressed_count = 0
    linked_evicted_count = 0
    for entry in session.forgetting_backlog:
        if entry.state == "suppressed":
            suppressed_count += 1
        elif entry.state == "evicted":
            evicted_count += 1
        else:
            continue
        if linked and any(value in entry.value or entry.value in value for value in linked):
            if entry.state == "suppressed":
                linked_suppressed_count += 1
            elif entry.state == "evicted":
                linked_evicted_count += 1
    return {
        "suppressed_count": suppressed_count,
        "evicted_count": evicted_count,
        "linked_suppressed_count": linked_suppressed_count,
        "linked_evicted_count": linked_evicted_count,
        "linked_stale_count": linked_suppressed_count + linked_evicted_count,
    }


def compact_forgetting_backlog(session: SessionState, *, limit: int = 24) -> None:
    deduped: dict[str, ForgetEntry] = {}
    for item in session.forgetting_backlog:
        if not item.value:
            continue
        prior = deduped.get(item.value)
        if prior is None or item.hits >= prior.hits:
            deduped[item.value] = item
    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            {"evicted": 3, "suppressed": 2, "backlog": 1}.get(item.state, 0),
            item.hits,
            item.value,
        ),
        reverse=True,
    )
    session.forgetting_backlog = ranked[:limit]


def session_path(repo_root: str, task_id: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "sessions" / f"{task_id}.json"


def _project_scope_slug(project_scope: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", project_scope.strip())
    return cleaned.strip("._-") or "default"


def project_session_path(project_scope: str, task_id: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "sessions"
        / f"{task_id}.json"
    )


def _load_session_file(path: Path) -> SessionState | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    packets = [DelegationPacket(**packet) for packet in data.get("delegation_packets", [])]
    data["delegation_packets"] = packets
    returns = [DelegationReturn(**item) for item in data.get("delegation_returns", [])]
    data["delegation_returns"] = returns
    patterns = [CollaborationPattern(**item) for item in data.get("collaboration_patterns", [])]
    data["collaboration_patterns"] = patterns
    artifacts = [ArtifactReference(**item) for item in data.get("artifacts", [])]
    data["artifacts"] = artifacts
    data["execution_packet"] = ExecutionPacket.from_dict(data.get("execution_packet"))
    data["execution_packet_summary"] = ExecutionPacketSummary.from_dict(data.get("execution_packet_summary"))
    data["continuity_review_pack"] = ReviewPackSummary.from_dict(data.get("continuity_review_pack"))
    data["evolution_review_pack"] = ReviewPackSummary.from_dict(data.get("evolution_review_pack"))
    data["app_harness_state"] = AppHarnessState.from_dict(data.get("app_harness_state"))
    data["planner_packet"] = PlannerPacket.from_dict(data.get("planner_packet"))
    data["strategy_summary"] = StrategySummary.from_dict(data.get("strategy_summary"))
    data["pattern_signal_summary"] = PatternSignalSummary.from_dict(data.get("pattern_signal_summary"))
    data["workflow_signal_summary"] = WorkflowSignalSummary.from_dict(data.get("workflow_signal_summary"))
    data["routing_signal_summary"] = RoutingSignalSummary.from_dict(data.get("routing_signal_summary"))
    data["maintenance_summary"] = MaintenanceSummary.from_dict(data.get("maintenance_summary"))
    data["instrumentation_summary"] = InstrumentationSummary.from_dict(data.get("instrumentation_summary"))
    forgetting_entries = []
    for item in data.get("forgetting_backlog", []):
        if isinstance(item, str):
            forgetting_entries.append(ForgetEntry(value=item, reason="legacy_backlog"))
        elif isinstance(item, dict):
            forgetting_entries.append(ForgetEntry(**item))
    data["forgetting_backlog"] = forgetting_entries
    return SessionState(**data)


def load_session(repo_root: str, task_id: str, *, project_scope: str | None = None) -> SessionState | None:
    session = _load_session_file(session_path(repo_root, task_id))
    if session is not None:
        return session
    if project_scope:
        return _load_session_file(project_session_path(project_scope, task_id))
    return None


def load_recent_sessions(
    repo_root: str,
    *,
    project_scope: str | None = None,
    exclude_task_id: str | None = None,
    limit: int = 3,
) -> list[SessionState]:
    candidate_dirs: list[Path] = []
    if project_scope:
        candidate_dirs.append(project_session_path(project_scope, "_placeholder").parent)
    candidate_dirs.append(session_path(repo_root, "_placeholder").parent)

    loaded: list[tuple[float, SessionState]] = []
    seen_task_ids: set[str] = set()
    for sessions_dir in candidate_dirs:
        if not sessions_dir.exists():
            continue
        for path in sessions_dir.glob("*.json"):
            if exclude_task_id and path.stem == exclude_task_id:
                continue
            if path.stem in seen_task_ids:
                continue
            try:
                session = _load_session_file(path)
            except Exception:
                session = None
            if session is None:
                continue
            seen_task_ids.add(path.stem)
            loaded.append((path.stat().st_mtime, session))

    loaded.sort(
        key=lambda item: (
            session_signal_score(item[1]),
            item[0],
        ),
        reverse=True,
    )
    filtered = [session for _, session in loaded if session_signal_score(session) > 0]
    if filtered:
        return filtered[:limit]
    return [session for _, session in loaded[:limit]]


def save_session(session: SessionState) -> Path:
    local_path = session_path(session.repo_root, session.task_id)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    payload = session.to_json()
    local_path.write_text(payload)
    if session.project_scope:
        project_path = project_session_path(session.project_scope, session.task_id)
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(payload)
    return local_path


def artifact_dir(repo_root: str, task_id: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "artifacts" / task_id


def bootstrap_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "bootstrap.json"


def auto_learning_path(repo_root: str) -> Path:
    return Path(repo_root) / ".aionis-workbench" / "auto_learning.json"


def project_artifact_dir(project_scope: str, task_id: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "artifacts"
        / task_id
    )


def project_bootstrap_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "bootstrap.json"
    )


def project_auto_learning_path(project_scope: str) -> Path:
    return (
        Path.home()
        / ".aionis-workbench"
        / "projects"
        / _project_scope_slug(project_scope)
        / "auto_learning.json"
    )


def load_auto_learning_snapshot(
    repo_root: str,
    *,
    project_scope: str | None = None,
) -> dict[str, object]:
    candidates: list[Path] = []
    if project_scope:
        candidates.append(project_auto_learning_path(project_scope))
    candidates.append(auto_learning_path(repo_root))
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def save_auto_learning_snapshot(
    *,
    repo_root: str,
    project_scope: str,
    payload: dict[str, object],
) -> Path:
    local_path = auto_learning_path(repo_root)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    local_path.write_text(serialized)
    if project_scope:
        project_path = project_auto_learning_path(project_scope)
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(serialized)
    return local_path


def save_artifact_payload(
    *,
    repo_root: str,
    project_scope: str,
    task_id: str,
    artifact_name: str,
    payload: dict,
) -> str:
    local_dir = artifact_dir(repo_root, task_id)
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / artifact_name
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    local_path.write_text(serialized)
    if project_scope:
        project_dir = project_artifact_dir(project_scope, task_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / artifact_name).write_text(serialized)
    rel = local_path.relative_to(Path(repo_root))
    return rel.as_posix()
