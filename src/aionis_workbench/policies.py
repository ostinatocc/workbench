from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field

from .context_layers import CONTEXT_LAYER_ORDER, assemble_context_layers
from .roles import default_delegation_packets
from .session import (
    CollaborationPattern,
    DelegationReturn,
    SessionState,
    add_forgetting_entry,
    compact_forgetting_backlog,
    forgetting_state_map,
)
from .tracing import TraceStep, extract_target_files, normalize_target_paths


@dataclass
class StrategySelection:
    target_files: list[str]
    selected_working_set: list[str]
    validation_commands: list[str]
    memory_lines: list[str]
    artifact_limit: int = 6
    memory_source_limit: int = 14
    task_family: str = ""
    family_scope: str = "broader_similarity"
    family_candidate_count: int = 0
    preferred_artifacts: list[str] = field(default_factory=list)
    role_sequence: list[str] = field(default_factory=list)
    strategy_profile: str = "broad_discovery"
    validation_style: str = "targeted_then_expand"
    trust_signal: str = "broader_similarity"
    selected_pattern_summaries: list[str] = field(default_factory=list)
    specialist_recommendation: str = ""


def _strip_repo_root_prefix(command: str, repo_root: str) -> str:
    cleaned = command.strip()
    repo_root_path = str(Path(repo_root).expanduser().resolve())
    prefixes = (
        f"cd {repo_root_path} && ",
        f'cd "{repo_root_path}" && ',
        f"cd '{repo_root_path}' && ",
    )
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):].strip()
    cleaned = re.sub(r"""^cd\s+(?:"[^"]+"|'[^']+'|[^\s]+)\s*&&\s*""", "", cleaned)
    return cleaned


def _normalize_insight_text(insight: str, repo_root: str) -> str:
    if insight.startswith("Prior insight: "):
        normalized = _normalize_insight_text(insight[len("Prior insight: "):], repo_root)
        return "Prior insight: " + normalized
    for prefix in ("Validation path: ", "Session validation path: "):
        if insight.startswith(prefix):
            return prefix + _strip_repo_root_prefix(insight[len(prefix):], repo_root)
    if insight.startswith("High-signal target files: "):
        return _normalize_file_list_insight(insight, repo_root, prefix="High-signal target files: ")
    if insight.startswith("Recent working sets: "):
        return _normalize_file_list_insight(insight, repo_root, prefix="Recent working sets: ")
    return insight


def _is_file_like(path_value: str) -> bool:
    name = Path(path_value).name
    if Path(path_value).suffix:
        return True
    if name in {"Dockerfile", "Makefile", "pyproject.toml", "tox.ini", "README.md", "package.json"}:
        return True
    if name.startswith("test_"):
        return True
    return False


def _normalize_file_list_insight(insight: str, repo_root: str, *, prefix: str) -> str:
    raw = insight[len(prefix):]
    parts = [value.strip() for value in raw.split(",") if value.strip()]
    normalized = normalize_target_paths(parts, repo_root=repo_root, limit=8)
    file_like = [value for value in normalized if _is_file_like(value)]
    chosen = file_like or normalized
    if not chosen:
        return prefix.rstrip()
    return prefix + ", ".join(chosen[:8])


def _dedupe_latest_by_prefix(items: list[str], prefixes: tuple[str, ...]) -> list[str]:
    kept: list[str] = []
    seen_prefixes: set[str] = set()

    for item in reversed(items):
        matched_prefix = next((prefix for prefix in prefixes if item.startswith(prefix)), None)
        if matched_prefix is None:
            if item not in kept:
                kept.append(item)
            continue
        if matched_prefix in seen_prefixes:
            continue
        seen_prefixes.add(matched_prefix)
        kept.append(item)

    kept.reverse()
    return kept


def _dedupe_latest_by_prefix_with_overflow(items: list[str], prefixes: tuple[str, ...]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    overflow: list[str] = []
    seen_prefixes: set[str] = set()

    for item in reversed(items):
        matched_prefix = next((prefix for prefix in prefixes if item.startswith(prefix)), None)
        if matched_prefix is None:
            if item not in kept:
                kept.append(item)
            continue
        if matched_prefix in seen_prefixes:
            overflow.append(item)
            continue
        seen_prefixes.add(matched_prefix)
        kept.append(item)

    kept.reverse()
    overflow.reverse()
    return kept, overflow


def _filter_relevant_changed_files(session: SessionState, changed_files: list[str] | None) -> list[str]:
    if not changed_files:
        return []

    normalized_target_files = {
        value
        for value in session.target_files
        if isinstance(value, str) and value.strip() and "." in Path(value).name
    }
    normalized_changed_files = [value for value in changed_files if isinstance(value, str) and value.strip()]

    relevant = [value for value in normalized_changed_files if value in normalized_target_files]
    if relevant:
        return _unique_preserve_order(relevant, limit=8)

    target_dirs = {
        str(Path(value).parent)
        for value in normalized_target_files
        if str(Path(value).parent) not in ("", ".")
    }
    relevant = [
        value
        for value in normalized_changed_files
        if str(Path(value).parent) in target_dirs
    ]
    if relevant:
        return _unique_preserve_order(relevant, limit=8)

    return _unique_preserve_order(normalized_changed_files, limit=8)


def build_memory_prompts(session: SessionState) -> list[str]:
    prompts: list[str] = []
    planner_packet = session.planner_packet
    continuity = session.continuity_snapshot or {}
    context_layers = session.context_layers_snapshot or assemble_context_layers(session=session)
    if continuity:
        lines = [
            *(["Project: " + str(continuity.get("project_scope"))] if continuity.get("project_scope") else []),
            *(["Working set: " + ", ".join(continuity.get("session_working_set", [])[:6])] if isinstance(continuity.get("session_working_set"), list) and continuity.get("session_working_set") else []),
            *(["Validation paths: " + "; ".join(continuity.get("session_validation_paths", [])[:2])] if isinstance(continuity.get("session_validation_paths"), list) and continuity.get("session_validation_paths") else []),
            *(["Workflow mode: " + str(continuity.get("workflow_mode"))] if continuity.get("workflow_mode") else []),
            *(["Task family: " + str(continuity.get("task_family"))] if continuity.get("task_family") else []),
            *(["Family scope: " + str(continuity.get("selected_family_scope"))] if continuity.get("selected_family_scope") else []),
            *(["Strategy profile: " + str(continuity.get("strategy_profile"))] if continuity.get("strategy_profile") else []),
            *(["Validation style: " + str(continuity.get("validation_style"))] if continuity.get("validation_style") else []),
            *(["Selected role sequence: " + " -> ".join(continuity.get("selected_role_sequence", [])[:3])] if isinstance(continuity.get("selected_role_sequence"), list) and continuity.get("selected_role_sequence") else []),
            *(["Planner next action: " + str(continuity.get("planner_next_action"))] if continuity.get("planner_next_action") else []),
            *(["Selected patterns: " + "; ".join(continuity.get("selected_pattern_summaries", [])[:2])] if isinstance(continuity.get("selected_pattern_summaries"), list) and continuity.get("selected_pattern_summaries") else []),
            *(["Trusted patterns: " + "; ".join(continuity.get("trusted_pattern_summaries", [])[:2])] if isinstance(continuity.get("trusted_pattern_summaries"), list) and continuity.get("trusted_pattern_summaries") else []),
            *(["Preferred artifacts: " + "; ".join(continuity.get("preferred_artifact_refs", [])[:3])] if isinstance(continuity.get("preferred_artifact_refs"), list) and continuity.get("preferred_artifact_refs") else []),
            *(["Specialist handoff chain: " + " | ".join(continuity.get("specialist_handoff_chain", [])[:3])] if isinstance(continuity.get("specialist_handoff_chain"), list) and continuity.get("specialist_handoff_chain") else []),
            *(["Specialist next actions: " + " | ".join(continuity.get("specialist_next_actions", [])[:3])] if isinstance(continuity.get("specialist_next_actions"), list) and continuity.get("specialist_next_actions") else []),
            *(["Verifier blockers: " + "; ".join(continuity.get("verifier_blockers", [])[:2])] if isinstance(continuity.get("verifier_blockers"), list) and continuity.get("verifier_blockers") else []),
            *(["Verifier validation intent: " + "; ".join(continuity.get("verifier_validation_intent", [])[:2])] if isinstance(continuity.get("verifier_validation_intent"), list) and continuity.get("verifier_validation_intent") else []),
        ]
        prompts.append("Continuity snapshot:\n" + "\n".join(f"- {line}" for line in lines if line))
    if planner_packet:
        lines = [
            f"Stage: {planner_packet.current_stage}",
            f"Active role: {planner_packet.active_role}",
            f"Task: {planner_packet.task_brief}",
            *(["Next action: " + planner_packet.next_action] if planner_packet.next_action else []),
            *(["Target files: " + ", ".join(planner_packet.target_files[:6])] if planner_packet.target_files else []),
            *(["Trusted patterns: " + "; ".join(planner_packet.trusted_pattern_summaries[:3])] if planner_packet.trusted_pattern_summaries else []),
            *(["Preferred artifacts: " + "; ".join(planner_packet.preferred_artifact_refs[:3])] if planner_packet.preferred_artifact_refs else []),
            *(["Pending validations: " + "; ".join(planner_packet.pending_validations[:2])] if planner_packet.pending_validations else []),
            *(["Unresolved blockers: " + "; ".join(planner_packet.unresolved_blockers[:2])] if planner_packet.unresolved_blockers else []),
        ]
        prompts.append("Planner packet:\n" + "\n".join(f"- {line}" for line in lines if line))
    if session.strategy_summary:
        lines = [
            f"Trust signal: {session.strategy_summary.trust_signal}",
            f"Strategy profile: {session.strategy_summary.strategy_profile}",
            f"Validation style: {session.strategy_summary.validation_style}",
            *(["Working set: " + ", ".join(session.strategy_summary.selected_working_set[:6])] if session.strategy_summary.selected_working_set else []),
            *(["Validation paths: " + "; ".join(session.strategy_summary.selected_validation_paths[:2])] if session.strategy_summary.selected_validation_paths else []),
            *(["Role sequence: " + " -> ".join(session.strategy_summary.selected_role_sequence)] if session.strategy_summary.selected_role_sequence else []),
            *(["Selected patterns: " + "; ".join(session.strategy_summary.selected_pattern_summaries[:3])] if session.strategy_summary.selected_pattern_summaries else []),
            *(["Preferred artifacts: " + "; ".join(session.strategy_summary.preferred_artifact_refs[:3])] if session.strategy_summary.preferred_artifact_refs else []),
            f"Artifact budget: {session.strategy_summary.artifact_budget}",
            f"Memory source limit: {session.strategy_summary.memory_source_limit}",
            *(["Why: " + session.strategy_summary.explanation] if session.strategy_summary.explanation else []),
        ]
        prompts.append("Strategy summary:\n" + "\n".join(f"- {line}" for line in lines if line))
    if session.workflow_signal_summary:
        lines = [
            f"Workflow mode: {session.workflow_signal_summary.workflow_mode}",
            f"Workflow stage: {session.workflow_signal_summary.stage}",
            *(["Workflow role sequence: " + " -> ".join(session.workflow_signal_summary.role_sequence)] if session.workflow_signal_summary.role_sequence else []),
        ]
        prompts.append("Workflow signal summary:\n" + "\n".join(f"- {line}" for line in lines if line))
    if session.pattern_signal_summary:
        lines = [
            f"Dominant affinity: {session.pattern_signal_summary.dominant_affinity}",
            f"Trusted patterns: {session.pattern_signal_summary.trusted_pattern_count}",
            f"Contested patterns: {session.pattern_signal_summary.contested_pattern_count}",
            *(["Pattern summaries: " + "; ".join(session.pattern_signal_summary.trusted_patterns[:3])] if session.pattern_signal_summary.trusted_patterns else []),
        ]
        prompts.append("Pattern signal summary:\n" + "\n".join(f"- {line}" for line in lines if line))
    if session.maintenance_summary:
        lines = [
            f"Promoted insights: {session.maintenance_summary.promoted_insight_count}",
            f"Forgetting backlog: {session.maintenance_summary.forgetting_backlog_count}",
            f"Suppressed: {session.maintenance_summary.suppressed_count}",
            f"Evicted: {session.maintenance_summary.evicted_count}",
            *(["Recommended maintenance: " + session.maintenance_summary.recommended_action] if session.maintenance_summary.recommended_action else []),
        ]
        prompts.append("Maintenance summary:\n" + "\n".join(f"- {line}" for line in lines if line))
    packet = session.execution_packet
    if packet and not planner_packet:
        lines = [
            f"Stage: {packet.current_stage}",
            f"Active role: {packet.active_role}",
            f"Task: {packet.task_brief}",
            *(["Next action: " + packet.next_action] if packet.next_action else []),
            *(["Target files: " + ", ".join(packet.target_files[:6])] if packet.target_files else []),
            *(["Constraints: " + "; ".join(packet.hard_constraints[:3])] if packet.hard_constraints else []),
            *(["Accepted facts: " + "; ".join(packet.accepted_facts[:3])] if packet.accepted_facts else []),
            *(["Pending validations: " + "; ".join(packet.pending_validations[:2])] if packet.pending_validations else []),
            *(["Unresolved blockers: " + "; ".join(packet.unresolved_blockers[:2])] if packet.unresolved_blockers else []),
            *(["Artifact refs: " + "; ".join(packet.artifact_refs[:3])] if packet.artifact_refs else []),
        ]
        prompts.append("Execution packet:\n" + "\n".join(f"- {line}" for line in lines if line))
    rollback_artifact = next(
        (item for item in session.artifacts if item.kind == "rollback_hint_artifact"),
        None,
    )
    if rollback_artifact:
        lines = [rollback_artifact.summary]
        suspicious_file = rollback_artifact.metadata.get("suspicious_file")
        if isinstance(suspicious_file, str) and suspicious_file.strip():
            lines.append("Suspicious file: " + suspicious_file.strip())
        command = rollback_artifact.metadata.get("command")
        if isinstance(command, str) and command.strip():
            lines.append("Rollback command: " + command.strip())
        lines.append("Reference: " + rollback_artifact.path)
        prompts.append("Rollback hint:\n" + "\n".join(f"- {line}" for line in lines))
    correction_artifact = next(
        (item for item in session.artifacts if item.kind == "correction_packet_artifact"),
        None,
    )
    if correction_artifact:
        lines = [correction_artifact.summary]
        failure_name = correction_artifact.metadata.get("failure_name")
        if isinstance(failure_name, str) and failure_name.strip():
            lines.append("Primary failing test: " + failure_name.strip())
        command = correction_artifact.metadata.get("command")
        if isinstance(command, str) and command.strip():
            lines.append("Correction command: " + command.strip())
        lines.append("Reference: " + correction_artifact.path)
        prompts.append("Correction packet:\n" + "\n".join(f"- {line}" for line in lines))
    for layer_name in CONTEXT_LAYER_ORDER:
        values = context_layers.get(layer_name) or []
        if not values:
            continue
        prompts.append(
            f"Context layer: {layer_name}\n" + "\n".join(f"- {item}" for item in values)
        )
    return prompts


def normalize_session_memory(session: SessionState) -> None:
    session.shared_memory = list(
        dict.fromkeys(_normalize_insight_text(item, session.repo_root) for item in session.shared_memory if item)
    )
    normalized_promoted = list(
        dict.fromkeys(_normalize_insight_text(item, session.repo_root) for item in session.promoted_insights if item)
    )
    promoted_kept, promoted_overflow = _dedupe_latest_by_prefix_with_overflow(
        normalized_promoted,
        (
            "High-signal target files: ",
            "Validation path: ",
            "Latest execution outcome: ",
            "Validation passed: ",
            "Validation failed command: ",
        ),
    )
    session.promoted_insights = promoted_kept[:12]
    if promoted_overflow:
        for item in promoted_overflow[:12]:
            add_forgetting_entry(session, value=item, reason="superseded_insight")

    session.collaboration_patterns = _dedupe_collaboration_patterns(
        [
            CollaborationPattern(
                kind=item.kind.strip(),
                role=item.role.strip(),
                summary=item.summary.strip()[:240],
                reuse_hint=item.reuse_hint.strip()[:240],
                confidence=item.confidence,
                evidence=_unique_preserve_order(item.evidence[:4], limit=4),
                task_signature=(item.task_signature or "").strip()[:256],
                task_family=(item.task_family or "").strip()[:128],
                error_family=(item.error_family or "").strip()[:128],
                affinity_level=(item.affinity_level or "broader_similarity").strip()[:64] or "broader_similarity",
            )
            for item in session.collaboration_patterns
            if item.summary.strip()
        ]
    )

    shared_kept, shared_overflow = _dedupe_latest_by_prefix_with_overflow(
        session.shared_memory,
        (
            "Session working set: ",
            "Session validation path: ",
            "High-signal target files: ",
            "Validation path: ",
            "Latest execution outcome: ",
            "Validation passed: ",
            "Validation failed command: ",
            "Ingested changed files: ",
            "Reusable collaboration pattern: ",
        ),
    )
    session.shared_memory = shared_kept[:16]
    if shared_overflow:
        for item in shared_overflow[:12]:
            add_forgetting_entry(session, value=item, reason="superseded_shared_memory")
    compact_forgetting_backlog(session)


def reproject_shared_memory(session: SessionState) -> None:
    continuity = session.continuity_snapshot or {}
    rebuilt: list[str] = []
    if isinstance(continuity.get("kickoff"), dict):
        kickoff = continuity["kickoff"]
        tool = kickoff.get("tool")
        file_path = kickoff.get("file")
        next_action = kickoff.get("next_action")
        if isinstance(tool, str) and tool.strip():
            rebuilt.append("Kickoff tool: " + tool.strip())
        if isinstance(file_path, str) and file_path.strip():
            rebuilt.append("Kickoff file: " + file_path.strip())
        if isinstance(next_action, str) and next_action.strip():
            rebuilt.append("Kickoff next action: " + next_action.strip()[:220])
    if isinstance(continuity.get("recovered_handoff"), str) and continuity.get("recovered_handoff"):
        rebuilt.append("Recovered handoff: " + continuity["recovered_handoff"][:240])
    if isinstance(continuity.get("project_identity"), str) and continuity.get("project_identity"):
        rebuilt.append("Project identity: " + continuity["project_identity"].strip())
    if isinstance(continuity.get("project_scope"), str) and continuity.get("project_scope"):
        rebuilt.append("Project scope: " + continuity["project_scope"].strip())
    if isinstance(continuity.get("session_working_set"), list) and continuity.get("session_working_set"):
        rebuilt.append("Session working set: " + ", ".join(continuity["session_working_set"][:8]))
    if isinstance(continuity.get("session_validation_paths"), list) and continuity.get("session_validation_paths"):
        rebuilt.append("Session validation path: " + "; ".join(continuity["session_validation_paths"][:4]))
    if isinstance(continuity.get("recent_working_sets"), list) and continuity.get("recent_working_sets"):
        rebuilt.append("Recent working sets: " + ", ".join(continuity["recent_working_sets"][:6]))
    for item in session.shared_memory:
        if not isinstance(item, str) or not item.strip():
            continue
        if item.startswith("Ingested "):
            rebuilt.append(item.strip())
    session.shared_memory = list(dict.fromkeys(rebuilt))[:16]


def seed_shared_memory(
    *,
    session: SessionState,
    kickoff: dict | None = None,
    handoff_context: str | None = None,
    prior_sessions: list[SessionState] | None = None,
) -> None:
    seeded: list[str] = []
    continuity = session.continuity_snapshot or {}
    kickoff_snapshot = continuity.get("kickoff")
    if isinstance(kickoff_snapshot, dict):
        tool = kickoff_snapshot.get("tool")
        file_path = kickoff_snapshot.get("file")
        next_action = kickoff_snapshot.get("next_action")
        if isinstance(tool, str) and tool.strip():
            seeded.append("Kickoff tool: " + tool.strip())
        if isinstance(file_path, str) and file_path.strip():
            seeded.append("Kickoff file: " + file_path.strip())
        if isinstance(next_action, str) and next_action.strip():
            seeded.append("Kickoff next action: " + next_action.strip()[:220])
    elif isinstance(kickoff, dict):
        first_action = kickoff.get("first_action") or {}
        if isinstance(first_action.get("selected_tool"), str) and first_action["selected_tool"].strip():
            seeded.append(f"Kickoff tool: {first_action['selected_tool'].strip()}")
        if isinstance(first_action.get("file_path"), str) and first_action["file_path"].strip():
            seeded.append(f"Kickoff file: {first_action['file_path'].strip()}")
        if isinstance(first_action.get("next_action"), str) and first_action["next_action"].strip():
            seeded.append(f"Kickoff next action: {first_action['next_action'].strip()}")
    recovered_handoff = continuity.get("recovered_handoff")
    if isinstance(recovered_handoff, str) and recovered_handoff.strip():
        seeded.append("Recovered handoff: " + recovered_handoff.strip()[:240])
    elif isinstance(handoff_context, str) and handoff_context.strip():
        seeded.append("Recovered handoff: " + handoff_context.strip().splitlines()[0][:240])
    project_identity = continuity.get("project_identity") or session.project_identity
    if isinstance(project_identity, str) and project_identity.strip():
        seeded.append("Project identity: " + project_identity.strip())
    project_scope = continuity.get("project_scope") or session.project_scope
    if isinstance(project_scope, str) and project_scope.strip():
        seeded.append("Project scope: " + project_scope.strip())
    if isinstance(continuity.get("session_working_set"), list) and continuity.get("session_working_set"):
        seeded.append("Session working set: " + ", ".join(continuity["session_working_set"][:8]))
    elif session.target_files:
        seeded.append("Session working set: " + ", ".join(session.target_files[:8]))
    if isinstance(continuity.get("session_validation_paths"), list) and continuity.get("session_validation_paths"):
        seeded.append("Session validation path: " + "; ".join(continuity["session_validation_paths"][:4]))
    elif session.validation_commands:
        seeded.append("Session validation path: " + "; ".join(session.validation_commands[:4]))
    if prior_sessions:
        reused_files: list[str] = []
        for prior in prior_sessions[:3]:
            if not prior.promoted_insights and not prior.delegation_returns and not prior.collaboration_patterns:
                continue
            reused_files.extend(prior.target_files[:2])
        if reused_files:
            unique_files = list(dict.fromkeys(reused_files))[:6]
            seeded.append("Recent working sets: " + ", ".join(unique_files))
    else:
        for value in continuity.get("recent_working_sets", [])[:6] if isinstance(continuity.get("recent_working_sets"), list) else []:
            if isinstance(value, str) and value.strip():
                seeded.append("Recent working sets: " + value.strip()[:220])
                break

    for item in seeded:
        if item not in session.shared_memory:
            session.shared_memory.append(item)
    session.shared_memory = session.shared_memory[:16]


def seed_continuity_snapshot(
    *,
    session: SessionState,
    kickoff: dict | None = None,
    handoff_context: str | None = None,
    prior_sessions: list[SessionState] | None = None,
) -> dict[str, object]:
    snapshot: dict[str, object] = dict(session.continuity_snapshot or {})
    if isinstance((session.continuity_snapshot or {}).get("bootstrap"), dict):
        snapshot["bootstrap"] = dict((session.continuity_snapshot or {}).get("bootstrap") or {})
    if isinstance((session.continuity_snapshot or {}).get("learning"), dict):
        snapshot["learning"] = dict((session.continuity_snapshot or {}).get("learning") or {})
    if isinstance((session.continuity_snapshot or {}).get("passive_observation"), dict):
        snapshot["passive_observation"] = dict((session.continuity_snapshot or {}).get("passive_observation") or {})
    snapshot["project_identity"] = session.project_identity or snapshot.get("project_identity") or ""
    snapshot["project_scope"] = session.project_scope or snapshot.get("project_scope") or ""
    snapshot["session_working_set"] = session.target_files[:8]
    snapshot["session_validation_paths"] = session.validation_commands[:4]
    if session.goal:
        snapshot["task_goal"] = session.goal
    if session.selected_strategy_profile:
        snapshot["strategy_profile"] = session.selected_strategy_profile
    if session.selected_validation_style:
        snapshot["validation_style"] = session.selected_validation_style
    if session.selected_task_family:
        snapshot["task_family"] = session.selected_task_family
    if session.selected_family_scope:
        snapshot["selected_family_scope"] = session.selected_family_scope
    if session.selected_family_candidate_count:
        snapshot["family_candidate_count"] = session.selected_family_candidate_count
    if session.selected_role_sequence:
        snapshot["selected_role_sequence"] = session.selected_role_sequence[:3]
    if session.selected_pattern_summaries:
        snapshot["selected_pattern_summaries"] = session.selected_pattern_summaries[:4]
    if session.selected_trust_signal:
        snapshot["selected_trust_signal"] = session.selected_trust_signal
    if isinstance(kickoff, dict):
        first_action = kickoff.get("first_action") or {}
        kickoff_snapshot: dict[str, str] = {}
        if isinstance(first_action.get("selected_tool"), str) and first_action["selected_tool"].strip():
            kickoff_snapshot["tool"] = first_action["selected_tool"].strip()
        if isinstance(first_action.get("file_path"), str) and first_action["file_path"].strip():
            kickoff_snapshot["file"] = first_action["file_path"].strip()
        if isinstance(first_action.get("next_action"), str) and first_action["next_action"].strip():
            kickoff_snapshot["next_action"] = first_action["next_action"].strip()
        if kickoff_snapshot:
            snapshot["kickoff"] = kickoff_snapshot
    if isinstance(handoff_context, str) and handoff_context.strip():
        snapshot["recovered_handoff"] = handoff_context.strip().splitlines()[0][:240]
    if prior_sessions:
        prior_strategy_working_sets: list[str] = []
        prior_strategy_validations: list[str] = []
        prior_planner_actions: list[str] = []
        prior_collaboration_patterns: list[str] = []
        prior_artifact_refs: list[str] = []
        recent_working_sets: list[str] = []
        trusted_pattern_summaries: list[str] = list(snapshot.get("trusted_pattern_summaries", [])[:4]) if isinstance(snapshot.get("trusted_pattern_summaries"), list) else []
        for prior in prior_sessions[:3]:
            prior_snapshot = prior.continuity_snapshot or {}
            implementer_return = next(
                (item for item in prior.delegation_returns if getattr(item, "role", "") == "implementer"),
                None,
            )
            if implementer_return:
                prior_strategy_working_sets.extend(implementer_return.working_set[:2])
                prior_artifact_refs.extend(implementer_return.artifact_refs[:2])
            if prior.routing_signal_summary:
                prior_strategy_working_sets.extend(prior.routing_signal_summary.implementer_effective_scope[:2])
                prior_artifact_refs.extend(prior.routing_signal_summary.implementer_artifact_scope[:2])
            if prior.strategy_summary:
                prior_strategy_working_sets.extend(prior.strategy_summary.selected_working_set[:2])
                prior_strategy_validations.extend(prior.strategy_summary.selected_validation_paths[:2])
            if prior.planner_packet and prior.planner_packet.next_action:
                prior_planner_actions.append(prior.planner_packet.next_action[:220])
            if isinstance(prior_snapshot.get("prior_collaboration_patterns"), list):
                prior_collaboration_patterns.extend(
                    value.strip()[:220]
                    for value in prior_snapshot.get("prior_collaboration_patterns", [])[:2]
                    if isinstance(value, str) and value.strip()
                )
            elif prior.collaboration_patterns:
                prior_collaboration_patterns.extend(
                    f"{pattern.role}/{pattern.kind}: {pattern.summary}"[:220]
                    for pattern in prior.collaboration_patterns[:2]
                )
            preferred_refs = prior_snapshot.get("preferred_artifact_refs")
            if isinstance(preferred_refs, list):
                prior_artifact_refs.extend(
                    value.strip()[:220]
                    for value in preferred_refs[:2]
                    if isinstance(value, str) and value.strip()
                )
            else:
                prior_artifact_refs.extend(artifact.path for artifact in prior.artifacts[:2])
            recent_working_sets.extend(prior.target_files[:2])
            if prior.pattern_signal_summary and prior.pattern_signal_summary.trusted_patterns:
                trusted_pattern_summaries.extend(prior.pattern_signal_summary.trusted_patterns[:1])
        if prior_strategy_working_sets:
            snapshot["prior_strategy_working_sets"] = list(dict.fromkeys(prior_strategy_working_sets))[:4]
        if prior_strategy_validations:
            snapshot["prior_strategy_validations"] = list(dict.fromkeys(prior_strategy_validations))[:4]
        if prior_planner_actions:
            snapshot["prior_planner_actions"] = list(dict.fromkeys(prior_planner_actions))[:4]
        if prior_collaboration_patterns:
            snapshot["prior_collaboration_patterns"] = list(dict.fromkeys(prior_collaboration_patterns))[:4]
        if prior_artifact_refs:
            snapshot["prior_artifact_refs"] = list(dict.fromkeys(prior_artifact_refs))[:6]
        if recent_working_sets:
            snapshot["recent_working_sets"] = list(dict.fromkeys(recent_working_sets))[:6]
        if trusted_pattern_summaries:
            snapshot["trusted_pattern_summaries"] = list(dict.fromkeys(trusted_pattern_summaries))[:4]
    return snapshot


def build_continuity_snapshot(session: SessionState) -> dict[str, object]:
    prior_snapshot = dict(session.continuity_snapshot or {})
    snapshot: dict[str, object] = {
        "project_identity": session.project_identity or prior_snapshot.get("project_identity") or "",
        "project_scope": session.project_scope or prior_snapshot.get("project_scope") or "",
        "session_working_set": session.target_files[:8],
        "session_validation_paths": session.validation_commands[:4],
    }
    if prior_snapshot.get("app_delivery_mode") is not None:
        snapshot["app_delivery_mode"] = bool(prior_snapshot.get("app_delivery_mode"))
    if isinstance(prior_snapshot.get("bootstrap"), dict):
        snapshot["bootstrap"] = dict(prior_snapshot.get("bootstrap") or {})
    if isinstance(prior_snapshot.get("learning"), dict):
        snapshot["learning"] = dict(prior_snapshot.get("learning") or {})
    if isinstance(prior_snapshot.get("passive_observation"), dict):
        snapshot["passive_observation"] = dict(prior_snapshot.get("passive_observation") or {})
    if isinstance(prior_snapshot.get("doc_workflow"), dict):
        snapshot["doc_workflow"] = dict(prior_snapshot.get("doc_workflow") or {})
    if session.planner_packet and session.planner_packet.next_action:
        snapshot["planner_next_action"] = session.planner_packet.next_action
    elif prior_snapshot.get("planner_next_action"):
        snapshot["planner_next_action"] = prior_snapshot["planner_next_action"]
    if session.strategy_summary:
        if session.strategy_summary.selected_role_sequence:
            snapshot["selected_role_sequence"] = session.strategy_summary.selected_role_sequence[:3]
        if session.strategy_summary.preferred_artifact_refs:
            snapshot["preferred_artifact_refs"] = session.strategy_summary.preferred_artifact_refs[:6]
        if session.strategy_summary.strategy_profile:
            snapshot["strategy_profile"] = session.strategy_summary.strategy_profile
        if session.strategy_summary.validation_style:
            snapshot["validation_style"] = session.strategy_summary.validation_style
        if session.strategy_summary.selected_pattern_summaries:
            snapshot["selected_pattern_summaries"] = session.strategy_summary.selected_pattern_summaries[:4]
        if session.strategy_summary.trust_signal:
            snapshot["selected_trust_signal"] = session.strategy_summary.trust_signal
        if session.strategy_summary.task_family:
            snapshot["task_family"] = session.strategy_summary.task_family
        if session.strategy_summary.family_scope:
            snapshot["selected_family_scope"] = session.strategy_summary.family_scope
        if session.strategy_summary.family_candidate_count:
            snapshot["family_candidate_count"] = session.strategy_summary.family_candidate_count
    else:
        if isinstance(prior_snapshot.get("selected_role_sequence"), list):
            snapshot["selected_role_sequence"] = prior_snapshot["selected_role_sequence"][:3]
        if isinstance(prior_snapshot.get("preferred_artifact_refs"), list):
            snapshot["preferred_artifact_refs"] = prior_snapshot["preferred_artifact_refs"][:6]
        if prior_snapshot.get("strategy_profile"):
            snapshot["strategy_profile"] = prior_snapshot["strategy_profile"]
        if prior_snapshot.get("validation_style"):
            snapshot["validation_style"] = prior_snapshot["validation_style"]
        if isinstance(prior_snapshot.get("selected_pattern_summaries"), list):
            snapshot["selected_pattern_summaries"] = prior_snapshot["selected_pattern_summaries"][:4]
        if prior_snapshot.get("specialist_recommendation"):
            snapshot["specialist_recommendation"] = str(prior_snapshot["specialist_recommendation"])[:240]
        if prior_snapshot.get("selected_trust_signal"):
            snapshot["selected_trust_signal"] = prior_snapshot["selected_trust_signal"]
        if prior_snapshot.get("task_family"):
            snapshot["task_family"] = prior_snapshot["task_family"]
        if prior_snapshot.get("selected_family_scope"):
            snapshot["selected_family_scope"] = prior_snapshot["selected_family_scope"]
        if prior_snapshot.get("family_candidate_count"):
            snapshot["family_candidate_count"] = prior_snapshot["family_candidate_count"]
    if session.strategy_summary and session.strategy_summary.specialist_recommendation:
        snapshot["specialist_recommendation"] = session.strategy_summary.specialist_recommendation[:240]
    if session.workflow_signal_summary:
        snapshot["workflow_mode"] = session.workflow_signal_summary.workflow_mode
    elif prior_snapshot.get("workflow_mode"):
        snapshot["workflow_mode"] = prior_snapshot["workflow_mode"]
    if session.routing_signal_summary:
        if session.routing_signal_summary.implementer_effective_scope:
            snapshot["implementer_effective_scope"] = session.routing_signal_summary.implementer_effective_scope[:8]
        if session.routing_signal_summary.implementer_artifact_scope:
            snapshot["implementer_artifact_scope"] = session.routing_signal_summary.implementer_artifact_scope[:6]
        if session.routing_signal_summary.implementer_scope_source:
            snapshot["implementer_scope_source"] = session.routing_signal_summary.implementer_scope_source
        if session.routing_signal_summary.implementer_scope_narrowed:
            snapshot["implementer_scope_narrowed"] = True
        if session.routing_signal_summary.specialist_handoff_chain:
            snapshot["specialist_handoff_chain"] = session.routing_signal_summary.specialist_handoff_chain[:6]
        if session.routing_signal_summary.specialist_next_actions:
            snapshot["specialist_next_actions"] = session.routing_signal_summary.specialist_next_actions[:6]
        if session.routing_signal_summary.verifier_blockers:
            snapshot["verifier_blockers"] = session.routing_signal_summary.verifier_blockers[:4]
        if session.routing_signal_summary.verifier_validation_intent:
            snapshot["verifier_validation_intent"] = session.routing_signal_summary.verifier_validation_intent[:4]
    else:
        if isinstance(prior_snapshot.get("implementer_effective_scope"), list):
            snapshot["implementer_effective_scope"] = prior_snapshot["implementer_effective_scope"][:8]
        if isinstance(prior_snapshot.get("implementer_artifact_scope"), list):
            snapshot["implementer_artifact_scope"] = prior_snapshot["implementer_artifact_scope"][:6]
        if prior_snapshot.get("implementer_scope_source"):
            snapshot["implementer_scope_source"] = str(prior_snapshot["implementer_scope_source"])
        if prior_snapshot.get("implementer_scope_narrowed") is True:
            snapshot["implementer_scope_narrowed"] = True
        if isinstance(prior_snapshot.get("specialist_handoff_chain"), list):
            snapshot["specialist_handoff_chain"] = prior_snapshot["specialist_handoff_chain"][:6]
        if isinstance(prior_snapshot.get("specialist_next_actions"), list):
            snapshot["specialist_next_actions"] = prior_snapshot["specialist_next_actions"][:6]
        if isinstance(prior_snapshot.get("verifier_blockers"), list):
            snapshot["verifier_blockers"] = prior_snapshot["verifier_blockers"][:4]
        if isinstance(prior_snapshot.get("verifier_validation_intent"), list):
            snapshot["verifier_validation_intent"] = prior_snapshot["verifier_validation_intent"][:4]
    if session.pattern_signal_summary and session.pattern_signal_summary.trusted_patterns:
        snapshot["trusted_pattern_summaries"] = session.pattern_signal_summary.trusted_patterns[:4]
    elif isinstance(prior_snapshot.get("trusted_pattern_summaries"), list):
        snapshot["trusted_pattern_summaries"] = prior_snapshot["trusted_pattern_summaries"][:4]
    if session.goal:
        snapshot["task_goal"] = session.goal
    elif prior_snapshot.get("task_goal"):
        snapshot["task_goal"] = prior_snapshot["task_goal"]
    kickoff: dict[str, str] = {}
    prior_strategy_working_sets: list[str] = []
    prior_strategy_validations: list[str] = []
    prior_planner_actions: list[str] = []
    prior_collaboration_patterns: list[str] = []
    prior_artifact_refs: list[str] = []
    recent_working_sets: list[str] = []
    continuity_notes: list[str] = []
    for item in session.shared_memory[:16]:
        if not isinstance(item, str) or not item.strip():
            continue
        if item.startswith("Kickoff tool: "):
            kickoff["tool"] = item[len("Kickoff tool: ") :].strip()
        elif item.startswith("Kickoff file: "):
            kickoff["file"] = item[len("Kickoff file: ") :].strip()
        elif item.startswith("Kickoff next action: "):
            kickoff["next_action"] = item[len("Kickoff next action: ") :].strip()
        elif item.startswith("Recovered handoff: "):
            snapshot["recovered_handoff"] = item[len("Recovered handoff: ") :].strip()
        elif item.startswith("Prior strategy working set: "):
            prior_strategy_working_sets.append(item[len("Prior strategy working set: ") :].strip())
        elif item.startswith("Prior strategy validation: "):
            prior_strategy_validations.append(item[len("Prior strategy validation: ") :].strip())
        elif item.startswith("Prior planner next action: "):
            prior_planner_actions.append(item[len("Prior planner next action: ") :].strip())
        elif item.startswith("Prior collaboration pattern: "):
            prior_collaboration_patterns.append(item[len("Prior collaboration pattern: ") :].strip())
        elif item.startswith("Prior artifact reference: "):
            prior_artifact_refs.append(item[len("Prior artifact reference: ") :].strip())
        elif item.startswith("Recent working sets: "):
            recent_working_sets.extend(
                value.strip()
                for value in item[len("Recent working sets: ") :].split(",")
                if value.strip()
            )
        elif item.startswith("Ingested "):
            continuity_notes.append(item.strip())
    if isinstance(prior_snapshot.get("kickoff"), dict):
        kickoff = {**prior_snapshot.get("kickoff", {}), **kickoff}
    if isinstance(prior_snapshot.get("recovered_handoff"), str) and prior_snapshot.get("recovered_handoff"):
        snapshot["recovered_handoff"] = prior_snapshot["recovered_handoff"]
    if isinstance(prior_snapshot.get("prior_strategy_working_sets"), list):
        prior_strategy_working_sets = list(prior_snapshot["prior_strategy_working_sets"][:4]) + prior_strategy_working_sets
    if isinstance(prior_snapshot.get("prior_strategy_validations"), list):
        prior_strategy_validations = list(prior_snapshot["prior_strategy_validations"][:4]) + prior_strategy_validations
    if isinstance(prior_snapshot.get("prior_planner_actions"), list):
        prior_planner_actions = list(prior_snapshot["prior_planner_actions"][:4]) + prior_planner_actions
    if isinstance(prior_snapshot.get("prior_collaboration_patterns"), list):
        prior_collaboration_patterns = list(prior_snapshot["prior_collaboration_patterns"][:4]) + prior_collaboration_patterns
    if isinstance(prior_snapshot.get("prior_artifact_refs"), list):
        prior_artifact_refs = list(prior_snapshot["prior_artifact_refs"][:6]) + prior_artifact_refs
    if session.routing_signal_summary:
        prior_strategy_working_sets = session.routing_signal_summary.implementer_effective_scope[:4] + prior_strategy_working_sets
        prior_artifact_refs = session.routing_signal_summary.implementer_artifact_scope[:6] + prior_artifact_refs
    selected_pattern_artifact_refs = _extract_artifact_refs_from_text(
        list(session.strategy_summary.selected_pattern_summaries[:4]) if session.strategy_summary else []
    )
    trusted_pattern_artifact_refs = _extract_artifact_refs_from_text(
        list(session.pattern_signal_summary.trusted_patterns[:4]) if session.pattern_signal_summary else []
    )
    if selected_pattern_artifact_refs or trusted_pattern_artifact_refs:
        prior_artifact_refs = selected_pattern_artifact_refs + trusted_pattern_artifact_refs + prior_artifact_refs
    if isinstance(prior_snapshot.get("recent_working_sets"), list):
        recent_working_sets = list(prior_snapshot["recent_working_sets"][:6]) + recent_working_sets
    if isinstance(prior_snapshot.get("continuity_notes"), list):
        continuity_notes = list(prior_snapshot["continuity_notes"][:4]) + continuity_notes
    if kickoff:
        snapshot["kickoff"] = kickoff
    if prior_strategy_working_sets:
        snapshot["prior_strategy_working_sets"] = list(dict.fromkeys(prior_strategy_working_sets))[:4]
    if prior_strategy_validations:
        snapshot["prior_strategy_validations"] = list(dict.fromkeys(prior_strategy_validations))[:4]
    if prior_planner_actions:
        snapshot["prior_planner_actions"] = list(dict.fromkeys(prior_planner_actions))[:4]
    if prior_collaboration_patterns:
        snapshot["prior_collaboration_patterns"] = list(dict.fromkeys(prior_collaboration_patterns))[:4]
    if prior_artifact_refs:
        snapshot["prior_artifact_refs"] = list(dict.fromkeys(prior_artifact_refs))[:6]
    if recent_working_sets:
        snapshot["recent_working_sets"] = list(dict.fromkeys(recent_working_sets))[:6]
    if continuity_notes:
        snapshot["continuity_notes"] = list(dict.fromkeys(continuity_notes))[:4]
    return snapshot


def build_delegation_prompt(session: SessionState) -> str | None:
    if not session.delegation_packets and not session.planner_packet and not session.execution_packet:
        return None
    continuity = session.continuity_snapshot or {}
    recent_returns = {item.role: item for item in session.delegation_returns[:6]}
    artifact_by_role = {}
    for item in session.artifacts[:6]:
        artifact_by_role.setdefault(item.role, item)
    correction_artifact = next(
        (item for item in session.artifacts if item.kind == "correction_packet_artifact"),
        None,
    )
    rollback_artifact = next(
        (item for item in session.artifacts if item.kind == "rollback_hint_artifact"),
        None,
    )
    lines = ["Delegation packets:"]
    if continuity:
        if continuity.get("project_scope"):
            lines.append("Continuity project: " + str(continuity["project_scope"]))
        if isinstance(continuity.get("session_working_set"), list) and continuity.get("session_working_set"):
            lines.append("Continuity working set: " + ", ".join(continuity["session_working_set"][:6]))
        if isinstance(continuity.get("session_validation_paths"), list) and continuity.get("session_validation_paths"):
            lines.append("Continuity validation paths: " + "; ".join(continuity["session_validation_paths"][:2]))
        if continuity.get("planner_next_action"):
            lines.append("Continuity next action: " + str(continuity["planner_next_action"]))
        if continuity.get("workflow_mode"):
            lines.append("Continuity workflow mode: " + str(continuity["workflow_mode"]))
        if continuity.get("task_family"):
            lines.append("Continuity task family: " + str(continuity["task_family"]))
        if continuity.get("selected_family_scope"):
            lines.append("Continuity family scope: " + str(continuity["selected_family_scope"]))
        if continuity.get("strategy_profile"):
            lines.append("Continuity strategy profile: " + str(continuity["strategy_profile"]))
        if continuity.get("validation_style"):
            lines.append("Continuity validation style: " + str(continuity["validation_style"]))
        if isinstance(continuity.get("selected_role_sequence"), list) and continuity.get("selected_role_sequence"):
            lines.append("Continuity role sequence: " + " -> ".join(continuity["selected_role_sequence"][:3]))
        if isinstance(continuity.get("selected_pattern_summaries"), list) and continuity.get("selected_pattern_summaries"):
            lines.append("Continuity selected patterns: " + "; ".join(continuity["selected_pattern_summaries"][:3]))
        if isinstance(continuity.get("preferred_artifact_refs"), list) and continuity.get("preferred_artifact_refs"):
            lines.append("Continuity preferred artifacts: " + "; ".join(continuity["preferred_artifact_refs"][:3]))
        if isinstance(continuity.get("recovered_handoff"), str) and continuity.get("recovered_handoff"):
            lines.append("Continuity recovered handoff: " + continuity["recovered_handoff"][:220])
        kickoff = continuity.get("kickoff")
        if isinstance(kickoff, dict):
            next_action = kickoff.get("next_action")
            file_path = kickoff.get("file")
            tool = kickoff.get("tool")
            if isinstance(tool, str) and tool.strip():
                lines.append("Continuity kickoff tool: " + tool.strip())
            if isinstance(file_path, str) and file_path.strip():
                lines.append("Continuity kickoff file: " + file_path.strip())
            if isinstance(next_action, str) and next_action.strip():
                lines.append("Continuity kickoff next action: " + next_action.strip()[:220])
    if session.planner_packet:
        planner = session.planner_packet
        lines.append(f"Planner stage: {planner.current_stage}")
        lines.append(f"Planner active role: {planner.active_role}")
        if planner.next_action:
            lines.append("Planner next action: " + planner.next_action)
        if planner.target_files:
            lines.append("Planner target files: " + ", ".join(planner.target_files[:6]))
        if planner.pending_validations:
            lines.append("Planner pending validations: " + "; ".join(planner.pending_validations[:2]))
        if planner.unresolved_blockers:
            lines.append("Planner blockers: " + "; ".join(planner.unresolved_blockers[:2]))
        if planner.preferred_artifact_refs:
            lines.append("Planner preferred artifacts: " + "; ".join(planner.preferred_artifact_refs[:3]))
    if session.strategy_summary:
        lines.append("Strategy trust signal: " + session.strategy_summary.trust_signal)
        if session.strategy_summary.task_family:
            lines.append("Strategy task family: " + session.strategy_summary.task_family)
        if session.strategy_summary.family_scope:
            lines.append("Strategy family scope: " + session.strategy_summary.family_scope)
        if session.strategy_summary.family_candidate_count:
            lines.append("Strategy family candidates: " + str(session.strategy_summary.family_candidate_count))
        lines.append("Strategy profile: " + session.strategy_summary.strategy_profile)
        lines.append("Strategy validation style: " + session.strategy_summary.validation_style)
        if session.strategy_summary.selected_pattern_summaries:
            lines.append("Strategy selected patterns: " + "; ".join(session.strategy_summary.selected_pattern_summaries[:3]))
        if session.strategy_summary.explanation:
            lines.append("Strategy explanation: " + session.strategy_summary.explanation)
    if session.workflow_signal_summary:
        lines.append("Workflow mode: " + session.workflow_signal_summary.workflow_mode)
        if session.workflow_signal_summary.role_sequence:
            lines.append("Workflow role sequence: " + " -> ".join(session.workflow_signal_summary.role_sequence))
    if session.pattern_signal_summary:
        lines.append("Pattern affinity: " + session.pattern_signal_summary.dominant_affinity)
    if session.execution_packet and not session.planner_packet:
        packet = session.execution_packet
        lines.append(f"Execution stage: {packet.current_stage}")
        lines.append(f"Active role: {packet.active_role}")
        if packet.next_action:
            lines.append("Packet next action: " + packet.next_action)
        if packet.accepted_facts:
            lines.append("Accepted facts: " + "; ".join(packet.accepted_facts[:3]))
        if packet.pending_validations:
            lines.append("Pending validations: " + "; ".join(packet.pending_validations[:2]))
    if rollback_artifact:
        lines.append("Primary rollback hint: " + rollback_artifact.summary)
        suspicious_file = rollback_artifact.metadata.get("suspicious_file")
        if isinstance(suspicious_file, str) and suspicious_file.strip():
            lines.append("Rollback suspicious file: " + suspicious_file.strip())
        command = rollback_artifact.metadata.get("command")
        if isinstance(command, str) and command.strip():
            lines.append("Rollback command: " + command.strip())
        lines.append("Rollback artifact reference: " + rollback_artifact.path)
    if correction_artifact:
        lines.append("Primary correction packet: " + correction_artifact.summary)
        failure_name = correction_artifact.metadata.get("failure_name")
        if isinstance(failure_name, str) and failure_name.strip():
            lines.append("Primary failing test: " + failure_name.strip())
        command = correction_artifact.metadata.get("command")
        if isinstance(command, str) and command.strip():
            lines.append("Primary correction command: " + command.strip())
        lines.append("Correction artifact reference: " + correction_artifact.path)
    for packet in session.delegation_packets:
        lines.append(f"[{packet.role}] {packet.mission}")
        if packet.working_set:
            lines.append("Working set: " + ", ".join(packet.working_set[:8]))
        if packet.acceptance_checks:
            lines.append("Checks: " + "; ".join(packet.acceptance_checks[:4]))
        if packet.preferred_artifact_refs:
            lines.append("Routed artifacts: " + "; ".join(packet.preferred_artifact_refs[:3]))
        if packet.inherited_evidence:
            lines.append("Inherited evidence: " + "; ".join(packet.inherited_evidence[:3]))
        if packet.routing_reason:
            lines.append("Routing reason: " + packet.routing_reason)
        if packet.output_contract:
            lines.append("Return: " + packet.output_contract)
        prior_return = recent_returns.get(packet.role)
        if prior_return:
            lines.append(f"Last return: {prior_return.summary}")
            if prior_return.handoff_target:
                lines.append("Last handoff target: " + prior_return.handoff_target)
            if prior_return.next_action:
                lines.append("Last next action: " + prior_return.next_action)
            if prior_return.validation_intent:
                lines.append("Last validation intent: " + "; ".join(prior_return.validation_intent[:3]))
            if prior_return.blockers:
                lines.append("Last blockers: " + "; ".join(prior_return.blockers[:3]))
            if prior_return.evidence:
                lines.append("Last evidence: " + "; ".join(prior_return.evidence[:3]))
        prior_artifact = artifact_by_role.get(packet.role)
        if prior_artifact:
            lines.append(f"Artifact reference: {prior_artifact.path}")
    return "\n".join(lines)


def refresh_delegation_packets(session: SessionState) -> None:
    strategy_validation_paths = (
        session.strategy_summary.selected_validation_paths[:4]
        if session.strategy_summary and session.strategy_summary.selected_validation_paths
        else []
    )
    packets = default_delegation_packets(
        task=session.goal,
        target_files=session.target_files,
        validation_commands=strategy_validation_paths or session.validation_commands,
    )
    latest_returns = {item.role: item for item in session.delegation_returns[:6]}
    strategy_working_set = (
        session.strategy_summary.selected_working_set[:8]
        if session.strategy_summary and session.strategy_summary.selected_working_set
        else []
    )
    for packet in packets:
        if packet.role == "implementer":
            implementer_return = latest_returns.get("implementer")
            if implementer_return and implementer_return.working_set:
                packet.working_set = implementer_return.working_set[:8]
            elif strategy_working_set:
                packet.working_set = strategy_working_set[:8]
        refs, evidence, reason = _artifact_routing_for_role(session, packet.role)
        packet.preferred_artifact_refs = refs
        packet.inherited_evidence = evidence
        packet.routing_reason = reason
    session.delegation_packets = packets


def _is_arc_session(session: SessionState) -> bool:
    continuity = session.continuity_snapshot or {}
    if isinstance(continuity.get("arc_bridge"), dict):
        return True
    task_family = (
        session.selected_task_family
        or (session.strategy_summary.task_family if session.strategy_summary else "")
        or str(continuity.get("task_family") or "")
    )
    if isinstance(task_family, str) and task_family.endswith("-arc"):
        return True
    return any(isinstance(path, str) and path.startswith("arc_games/") for path in session.target_files)


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return ""


def _unique_preserve_order(values: list[str], *, limit: int) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))[:limit]


def _prioritize_candidates(existing: list[str], prioritized: list[str], *, limit: int) -> list[str]:
    prioritized_values = [value for value in prioritized if isinstance(value, str) and value.strip()]
    existing_values = [value for value in existing if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys([*prioritized_values, *existing_values]))[:limit]


def _preferred_artifact_paths(session: SessionState) -> list[str]:
    paths: list[str] = []
    if session.strategy_summary and session.strategy_summary.preferred_artifact_refs:
        paths.extend(
            value.strip()
            for value in session.strategy_summary.preferred_artifact_refs
            if isinstance(value, str) and value.strip()
        )
    continuity = session.continuity_snapshot or {}
    preferred = continuity.get("preferred_artifact_refs")
    if isinstance(preferred, list):
        paths.extend(value.strip() for value in preferred if isinstance(value, str) and value.strip())
    paths.extend(artifact.path for artifact in session.artifacts if artifact.path)
    return _unique_preserve_order(paths, limit=8)


def _artifact_routing_for_role(session: SessionState, role: str) -> tuple[list[str], list[str], str]:
    preferred_paths = _preferred_artifact_paths(session)
    continuity = session.continuity_snapshot or {}
    artifact_by_path = {artifact.path: artifact for artifact in session.artifacts if artifact.path}
    role_artifacts = [artifact.path for artifact in session.artifacts if artifact.role == role and artifact.path]
    investigator_artifacts = [artifact.path for artifact in session.artifacts if artifact.role == "investigator" and artifact.path]
    implementer_artifacts = [artifact.path for artifact in session.artifacts if artifact.role == "implementer" and artifact.path]
    control_artifacts = [
        artifact.path
        for artifact in session.artifacts
        if artifact.kind in {"correction_packet_artifact", "rollback_hint_artifact", "validation_result", "timeout_artifact"}
        and artifact.path
    ]
    recent_returns = {item.role: item for item in session.delegation_returns[:6]}
    selected_patterns = session.selected_pattern_summaries[:4]
    arc_bridge = continuity.get("arc_bridge") if isinstance(continuity, dict) else {}
    arc_bridge = arc_bridge if isinstance(arc_bridge, dict) else {}
    arc_session = _is_arc_session(session)

    refs: list[str] = []
    evidence: list[str] = []
    reason = "Route the narrowest relevant artifacts into the next role."
    arc_top_actions = ""
    action_distribution = arc_bridge.get("action_distribution")
    if isinstance(action_distribution, dict) and action_distribution:
        arc_top_actions = ", ".join(
            f"{name}={count}"
            for name, count in sorted(
                ((str(name).strip(), int(count)) for name, count in action_distribution.items() if str(name).strip()),
                key=lambda item: (-item[1], item[0]),
            )[:4]
        )
    blocked_actions = ""
    blocked_counts = arc_bridge.get("blocked_action_counts")
    if isinstance(blocked_counts, dict) and blocked_counts:
        blocked_actions = ", ".join(
            f"{name}={count}"
            for name, count in sorted(
                ((str(name).strip(), int(count)) for name, count in blocked_counts.items() if str(name).strip()),
                key=lambda item: (-item[1], item[0]),
            )[:3]
        )

    if role == "investigator":
        refs.extend(path for path in preferred_paths if getattr(artifact_by_path.get(path), "role", "") == "investigator")
        refs.extend(role_artifacts)
        evidence.extend(selected_patterns[:2])
        if session.planner_packet and session.planner_packet.next_action:
            evidence.append("Planner next action: " + session.planner_packet.next_action)
        reason = "Start from prior investigation artifacts and trusted patterns before widening repo inspection."
        if arc_session:
            if arc_top_actions:
                evidence.append("ARC dominant actions: " + arc_top_actions)
            reason = "Start from the ARC step digest, dominant action chain, and trusted patterns before widening to another same-family run."
    elif role == "implementer":
        refs.extend(investigator_artifacts[:2])
        refs.extend(path for path in preferred_paths if getattr(artifact_by_path.get(path), "role", "") in {"investigator", "implementer"})
        refs.extend(role_artifacts)
        refs.extend(control_artifacts[:2])
        investigator_return = recent_returns.get("investigator")
        if investigator_return:
            evidence.append("Investigator summary: " + investigator_return.summary)
            evidence.extend("Investigator evidence: " + item for item in investigator_return.evidence[:2])
        evidence.extend(selected_patterns[:2])
        reason = "Implementer inherits investigator findings plus correction artifacts before editing."
        if arc_session:
            if arc_top_actions:
                evidence.append("ARC dominant actions: " + arc_top_actions)
            reason = "Implementer should follow the ARC action-chain evidence and local plan hints before changing the next candidate action loop."
    elif role == "verifier":
        refs.extend(implementer_artifacts[:2])
        refs.extend(path for path in preferred_paths if getattr(artifact_by_path.get(path), "role", "") in {"implementer", "verifier"})
        refs.extend(role_artifacts)
        refs.extend(control_artifacts[:3])
        implementer_return = recent_returns.get("implementer")
        if implementer_return:
            evidence.append("Implementer summary: " + implementer_return.summary)
            evidence.extend("Implementer evidence: " + item for item in implementer_return.evidence[:2])
        evidence.extend("Validation path: " + item for item in session.validation_commands[:2])
        reason = "Verifier inherits implementer artifacts and targeted validation evidence before broader checks."
        if arc_session:
            if blocked_actions:
                evidence.append("ARC blocked actions: " + blocked_actions)
            scorecard_url = str(arc_bridge.get("scorecard_url") or "").strip()
            if scorecard_url:
                evidence.append("ARC scorecard: " + scorecard_url)
            reason = "Verifier should compare scorecard outcome, blocked actions, and recent action chain before declaring the ARC run stalled or reusable."
    else:
        refs.extend(preferred_paths[:3])
        evidence.extend(selected_patterns[:2])

    return (
        _unique_preserve_order(refs, limit=5),
        _unique_preserve_order(evidence, limit=5),
        reason,
    )


def _normalize_trace_command(command: str, repo_root: str) -> str:
    cleaned = command.strip()
    repo_root_path = str(Path(repo_root).expanduser().resolve())
    for prefix in (
        repo_root_path + "/",
        repo_root_path,
    ):
        cleaned = cleaned.replace(prefix, "")
    cleaned = cleaned.replace("sh /.aionis-workbench/", "sh .aionis-workbench/")
    cleaned = re.sub(r"PYTHONPATH=/src(?=\s|$)", "PYTHONPATH=src", cleaned)
    cleaned = re.sub(r"(^|\s)/((?:src|tests)/)", r"\1\2", cleaned)
    return cleaned.strip()


def _build_delegation_returns(
    *,
    session: SessionState,
    trace_steps: list[TraceStep],
    content: str,
    validation_ok: bool | None,
    validation_command: str | None,
    validation_summary: str | None,
    changed_files: list[str] | None,
) -> list[DelegationReturn]:
    relevant_changed_files = _filter_relevant_changed_files(session, changed_files)
    files = _unique_preserve_order([*session.target_files, *relevant_changed_files], limit=8)
    executed_commands = []
    for step in trace_steps:
        if step.tool_name == "execute" and isinstance(step.tool_input, dict):
            command = step.tool_input.get("command")
            if isinstance(command, str) and command.strip():
                executed_commands.append(_normalize_trace_command(command, session.repo_root))
    executed_commands = _unique_preserve_order(executed_commands, limit=4)

    investigator_summary = (
        f"Narrowed the working surface to {', '.join(files[:4])}."
        if files
        else "Narrowed the working surface for the current task."
    )
    implementer_summary = (
        f"Changed files now center on {', '.join(files[:4])}."
        if files
        else "Prepared a narrow implementation path."
    )
    verifier_parts = []
    if validation_ok is True:
        verifier_parts.append("Targeted validation passed.")
    elif validation_ok is False:
        verifier_parts.append(validation_summary or "Targeted validation failed.")
    if validation_command:
        verifier_parts.append(f"Command: {validation_command}")
    verifier_summary = " ".join(verifier_parts) if verifier_parts else "Validation has not run yet."

    content_line = _first_nonempty_line(content)
    investigator_handoff_target = "implementer"
    implementer_handoff_target = "verifier"
    verifier_handoff_target = "orchestrator"
    investigator_next_action = (
        f"Hand off to implementer and keep the implementation inside {', '.join(files[:3])}."
        if files
        else "Hand off to implementer and keep the implementation scope narrow."
    )
    implementer_next_action = (
        f"Hand off to verifier and run targeted validation: {validation_command or session.validation_commands[0]}"
        if (validation_command or session.validation_commands)
        else "Hand off to verifier and validate the patch against the delegated checks."
    )
    verifier_blockers = [validation_summary] if validation_ok is False and validation_summary else []
    verifier_validation_intent = _unique_preserve_order(
        [
            *(session.validation_commands[:4]),
            *([validation_command] if validation_command else []),
        ],
        limit=4,
    )
    verifier_next_action = (
        "Report the validated fix back to the orchestrator and keep the task ready for completion."
        if validation_ok is not False
        else (
            f"Revise the fix and rerun the verifier path: {verifier_validation_intent[0]}"
            if verifier_validation_intent
            else "Revise the fix and rerun the targeted verifier path."
        )
    )
    returns = [
        DelegationReturn(
            role="investigator",
            status="success",
            summary=investigator_summary,
            evidence=_unique_preserve_order(
                [
                    *([f"Working set: {', '.join(files[:4])}"] if files else []),
                    *([f"Outcome: {content_line}"] if content_line else []),
                ],
                limit=4,
            ),
            working_set=files[:8],
            acceptance_checks=session.validation_commands[:4],
            handoff_target=investigator_handoff_target,
            next_action=investigator_next_action,
            validation_intent=session.validation_commands[:4],
            handoff_text="\n".join(
                [
                    f"investigator summary: {investigator_summary}",
                    f"Next role: {investigator_handoff_target}",
                    f"Next action: {investigator_next_action}",
                    *([f"Working set: {', '.join(files[:8])}"] if files else []),
                    *([f"Validation intent: {'; '.join(session.validation_commands[:4])}"] if session.validation_commands else []),
                ]
            ),
        ),
        DelegationReturn(
            role="implementer",
            status="success",
            summary=implementer_summary,
            evidence=_unique_preserve_order(
                [
                    *([f"Changed files: {', '.join((changed_files or files)[:4])}"] if (changed_files or files) else []),
                    *([f"Changed files: {', '.join(relevant_changed_files[:4])}"] if relevant_changed_files else []),
                    *([f"Outcome: {content_line}"] if content_line else []),
                ],
                limit=4,
            ),
            working_set=(relevant_changed_files or files)[:8],
            acceptance_checks=session.validation_commands[:4],
            handoff_target=implementer_handoff_target,
            next_action=implementer_next_action,
            validation_intent=verifier_validation_intent,
            handoff_text="\n".join(
                [
                    f"implementer summary: {implementer_summary}",
                    f"Next role: {implementer_handoff_target}",
                    f"Next action: {implementer_next_action}",
                    *(
                        [f"Working set: {', '.join((relevant_changed_files or files)[:8])}"]
                        if (relevant_changed_files or files)
                        else []
                    ),
                    *([f"Validation intent: {'; '.join(verifier_validation_intent[:3])}"] if verifier_validation_intent else []),
                ]
            ),
        ),
        DelegationReturn(
            role="verifier",
            status="success" if validation_ok is not False else "error",
            summary=verifier_summary,
            evidence=_unique_preserve_order(
                [
                    *([f"Validation summary: {validation_summary}"] if validation_summary else []),
                    *(f"Executed: {command}" for command in executed_commands),
                ],
                limit=4,
            ),
            working_set=files[:8],
            acceptance_checks=verifier_validation_intent,
            handoff_target=verifier_handoff_target,
            next_action=verifier_next_action,
            blockers=verifier_blockers,
            validation_intent=verifier_validation_intent,
            handoff_text="\n".join(
                [
                    f"verifier summary: {verifier_summary}",
                    f"Next role: {verifier_handoff_target}",
                    f"Next action: {verifier_next_action}",
                    *([f"Working set: {', '.join(files[:8])}"] if files else []),
                    *([f"Validation intent: {'; '.join(verifier_validation_intent[:3])}"] if verifier_validation_intent else []),
                    *([f"Blockers: {'; '.join(verifier_blockers[:3])}"] if verifier_blockers else []),
                ]
            ),
        ),
    ]
    return returns


def _pattern_key(pattern: CollaborationPattern) -> tuple[str, str, str, str, str]:
    return (
        pattern.kind,
        pattern.role,
        pattern.reuse_hint.strip(),
        pattern.task_signature.strip() or pattern.task_family.strip(),
        pattern.error_family.strip(),
    )


def _dedupe_collaboration_patterns(
    patterns: list[CollaborationPattern],
    *,
    limit: int = 9,
) -> list[CollaborationPattern]:
    deduped: dict[tuple[str, str, str, str, str], CollaborationPattern] = {}
    for pattern in patterns:
        key = _pattern_key(pattern)
        prior = deduped.get(key)
        if prior is None or pattern.confidence >= prior.confidence:
            deduped[key] = pattern
    ranked = sorted(
        deduped.values(),
        key=lambda item: (item.confidence, len(item.evidence), item.summary),
        reverse=True,
    )
    return ranked[:limit]


def _build_collaboration_patterns(
    *,
    session: SessionState,
    delegation_returns: list[DelegationReturn],
    validation_ok: bool | None,
    validation_command: str | None,
) -> list[CollaborationPattern]:
    patterns: list[CollaborationPattern] = []
    task_signature, task_family, error_family = _session_task_metadata(session)
    artifact_by_role = {}
    packet_by_role = {item.role: item for item in session.delegation_packets}
    for artifact in session.artifacts:
        artifact_by_role.setdefault(artifact.role, artifact)
    successful_roles: list[str] = []

    for item in delegation_returns:
        if item.status != "success":
            continue
        successful_roles.append(item.role)

        if item.role == "investigator" and item.working_set:
            working_set = ", ".join(item.working_set[:4])
            patterns.append(
                CollaborationPattern(
                    kind="working_set_strategy",
                    role=item.role,
                    summary=f"Use {working_set} as the first-pass working surface for similar tasks.",
                    reuse_hint=working_set,
                    confidence=0.76,
                    evidence=item.evidence[:3],
                    task_signature=task_signature,
                    task_family=task_family,
                    error_family=error_family,
                )
            )
        elif item.role == "implementer" and item.working_set:
            focus = ", ".join(item.working_set[:4])
            patterns.append(
                CollaborationPattern(
                    kind="implementation_scope",
                    role=item.role,
                    summary=f"Keep implementation scope narrow around {focus}.",
                    reuse_hint=focus,
                    confidence=0.71,
                    evidence=item.evidence[:3],
                    task_signature=task_signature,
                    task_family=task_family,
                    error_family=error_family,
                )
            )
            source_packet = packet_by_role.get(item.role)
            packet_scope = list(source_packet.working_set[:8]) if source_packet else []
            if packet_scope and packet_scope[:4] != item.working_set[:4]:
                patterns.append(
                    CollaborationPattern(
                        kind="effective_edit_scope_strategy",
                        role=item.role,
                        summary=f"Start implementation from the narrowed scope {focus} before widening back to the original packet.",
                        reuse_hint=",".join(item.working_set[:6]),
                        confidence=0.8,
                        evidence=_unique_preserve_order(
                            [
                                f"Original packet scope: {', '.join(packet_scope[:4])}",
                                *item.evidence[:2],
                            ],
                            limit=4,
                        ),
                        task_signature=task_signature,
                        task_family=task_family,
                        error_family=error_family,
                    )
                )
            if item.artifact_refs:
                patterns.append(
                    CollaborationPattern(
                        kind="artifact_scope_strategy",
                        role=item.role,
                        summary=f"Anchor implementer context to {', '.join(item.artifact_refs[:2])} before widening repo reads.",
                        reuse_hint=",".join(item.artifact_refs[:4]),
                        confidence=0.76,
                        evidence=_unique_preserve_order(item.evidence[:3], limit=3),
                        task_signature=task_signature,
                        task_family=task_family,
                        error_family=error_family,
                    )
                )
        elif item.role == "verifier" and validation_ok is True:
            checks = item.acceptance_checks[:2]
            command = validation_command or (checks[0] if checks else "")
            if command:
                patterns.append(
                    CollaborationPattern(
                        kind="validation_strategy",
                        role=item.role,
                        summary=f"Default to targeted validation with: {command}",
                        reuse_hint=command,
                        confidence=0.84,
                        evidence=item.evidence[:3],
                        task_signature=task_signature,
                        task_family=task_family,
                        error_family=error_family,
                    )
                )
        artifact = artifact_by_role.get(item.role)
        if artifact:
            patterns.append(
                CollaborationPattern(
                    kind="artifact_reference_strategy",
                    role=item.role,
                    summary=f"Prefer the {item.role} artifact as the primary context object before falling back to long summaries.",
                    reuse_hint=f"{item.role}:{artifact.kind}",
                    confidence=0.68 if validation_ok is True else 0.6,
                    evidence=[
                        f"Artifact reference: {artifact.path}",
                        *item.evidence[:2],
                    ],
                    task_signature=task_signature,
                    task_family=task_family,
                    error_family=error_family,
                )
            )

    ordered_roles = [role for role in ("investigator", "implementer", "verifier") if role in successful_roles]
    if validation_ok is True and len(ordered_roles) == 3:
        patterns.append(
            CollaborationPattern(
                kind="role_sequence_strategy",
                role="orchestrator",
                summary="Keep the collaboration loop ordered as investigator -> implementer -> verifier, and keep each handoff narrow.",
                reuse_hint="investigator,implementer,verifier",
                confidence=0.82,
                evidence=[
                    *(["Validation command: " + validation_command] if validation_command else []),
                    "Successful collaboration loop completed with narrow validation.",
                ],
                task_signature=task_signature,
                task_family=task_family,
                error_family=error_family,
            )
        )

    for packet in session.delegation_packets:
        routed_refs = [value for value in packet.preferred_artifact_refs[:3] if isinstance(value, str) and value.strip()]
        if not routed_refs:
            continue
        confidence = 0.78 if validation_ok is True else 0.64
        patterns.append(
            CollaborationPattern(
                kind="artifact_routing_strategy",
                role=packet.role,
                summary=(
                    f"Route {packet.role} through {', '.join(routed_refs[:2])} before widening context."
                )[:240],
                reuse_hint=",".join(routed_refs[:3]),
                confidence=confidence,
                evidence=_unique_preserve_order(
                    [
                        *(["Routing reason: " + packet.routing_reason] if packet.routing_reason else []),
                        *(packet.inherited_evidence[:2] if packet.inherited_evidence else []),
                    ],
                    limit=4,
                ),
                task_signature=task_signature,
                task_family=task_family,
                error_family=error_family,
            )
        )

    existing = list(session.collaboration_patterns)
    return _dedupe_collaboration_patterns([*patterns, *existing])


def _parse_reuse_hint_files(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _artifact_task_ids_from_reuse_hint(value: str) -> list[str]:
    task_ids: list[str] = []
    for item in _parse_reuse_hint_files(value):
        match = re.search(r"/artifacts/([^/]+)/", item)
        if not match:
            continue
        task_id = match.group(1).strip()
        if task_id and task_id not in task_ids:
            task_ids.append(task_id)
    return task_ids


def _artifact_task_id_from_path(path: str) -> str:
    match = re.search(r"/artifacts/([^/]+)/", path)
    if not match:
        return ""
    return match.group(1).strip()


def _split_signal_words(value: str, *, limit: int = 8) -> list[str]:
    words = [
        token
        for part in re.split(r"[\s,.;:()[\]{}\"'`/]+", value.lower())
        if (token := re.sub(r"[^a-z0-9_-]", "", part)) and len(token) > 2
    ]
    return words[:limit]


def _normalize_family_label(value: str | None, prefix: str) -> str:
    if not value:
        return ""
    tokens = _split_signal_words(value, limit=6)
    if not tokens:
        return ""
    return f"{prefix}:{'-'.join(tokens[:6])}"[:128]


def _module_family_tokens(target_files: list[str]) -> list[str]:
    ignored = {"src", "tests", "click", "test", "impl", "json", "python"}
    counts: dict[str, int] = {}
    preferred_files = [
        value for value in target_files if str(Path(value)).startswith("src/")
    ] or list(target_files)
    for value in preferred_files:
        path = Path(value)
        parts = list(path.parts[:-1])
        if path.name:
            parts.append(path.stem)
        for part in parts:
            normalized = re.sub(r"[^a-z0-9_\\-]", "", part.lower())
            if normalized.startswith("test_"):
                normalized = normalized[len("test_") :]
            for token in re.split(r"[_\\-]+", normalized):
                if not token or token in ignored or len(token) <= 2:
                    continue
                counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (item[1], len(item[0]), item[0]), reverse=True)
    tokens = [token for token, _ in ranked[:4]]
    if len(tokens) > 1 and "core" in tokens:
        tokens = [token for token in tokens if token != "core"]
    return tokens[:3]


def _extract_artifact_refs_from_text(values: list[str]) -> list[str]:
    refs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        refs.extend(re.findall(r"\.aionis-workbench/artifacts/[^\s,;]+?\.json", value))
    return list(dict.fromkeys(refs))


def _extract_failure_name(session: SessionState) -> str:
    for artifact in session.artifacts:
        failure_name = artifact.metadata.get("failure_name")
        if isinstance(failure_name, str) and failure_name.strip():
            return failure_name.strip()
    summary = session.last_validation_result.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return ""


def _derive_task_signature(
    *,
    task_text: str = "",
    target_files: list[str] | None = None,
    validation_summary: str = "",
    failure_name: str = "",
) -> str:
    cue = task_text.strip() or failure_name.strip() or validation_summary.strip()
    if not cue and target_files:
        cue = " ".join(target_files[:3])
    return _normalize_family_label(cue, "tasksig")


def _derive_task_family(
    *,
    task_text: str = "",
    target_files: list[str] | None = None,
    validation_summary: str = "",
) -> str:
    stopwords = {
        "make",
        "fix",
        "keep",
        "uses",
        "using",
        "use",
        "with",
        "through",
        "correctly",
        "similar",
        "tasks",
        "task",
        "click",
        "around",
        "default",
    }
    module_tokens = _module_family_tokens(target_files or [])
    if module_tokens:
        return f"task:{'-'.join(module_tokens[:3])}"[:128]
    tokens = [
        token
        for token in _split_signal_words(task_text or validation_summary, limit=4)
        if token not in stopwords
    ]
    if tokens:
        return f"task:{'-'.join(tokens[:4])}"[:128]
    return _normalize_family_label(task_text or validation_summary, "task")


def _derive_error_family(
    *,
    validation_summary: str = "",
    failure_name: str = "",
    artifact_summaries: list[str] | None = None,
) -> str:
    source = " ".join(
        [
            failure_name.strip(),
            validation_summary.strip(),
            *[(item or "").strip() for item in (artifact_summaries or [])[:4]],
        ]
    ).strip()
    lowered = source.lower()
    if "timeout" in lowered:
        return "error:timeout"
    if "regression expansion" in lowered:
        return "error:regression-expansion"
    if "scope drift" in lowered:
        return "error:scope-drift"
    if "syntax error" in lowered:
        return "error:syntax-error"
    if failure_name:
        return _normalize_family_label(re.sub(r"\[.*?\]", "", failure_name), "error")
    return _normalize_family_label(source, "error")


def _session_task_metadata(session: SessionState) -> tuple[str, str, str]:
    summary_value = session.last_validation_result.get("summary")
    validation_summary = summary_value if isinstance(summary_value, str) else ""
    failure_name = _extract_failure_name(session)
    artifact_summaries = [item.summary for item in session.artifacts]
    return (
        _derive_task_signature(
            task_text=session.goal,
            target_files=session.target_files,
            validation_summary=validation_summary,
            failure_name=failure_name,
        ),
        _derive_task_family(
            task_text=session.goal,
            target_files=session.target_files,
            validation_summary=validation_summary,
        ),
        _derive_error_family(
            validation_summary=validation_summary,
            failure_name=failure_name,
            artifact_summaries=artifact_summaries,
        ),
    )


def _resolve_pattern_task_metadata(
    pattern: CollaborationPattern,
    session: SessionState,
) -> tuple[str, str, str]:
    task_signature, task_family, error_family = _session_task_metadata(session)
    return (
        pattern.task_signature or task_signature,
        pattern.task_family or task_family,
        pattern.error_family or error_family,
    )


def _path_affinity(target_files: list[str], candidate_files: list[str]) -> float:
    if not target_files or not candidate_files:
        return 0.0

    target_paths = [Path(value) for value in target_files if value]
    candidate_paths = [Path(value) for value in candidate_files if value]
    score = 0.0

    for target in target_paths:
        for candidate in candidate_paths:
            if target == candidate:
                score = max(score, 1.0)
            elif target.parent == candidate.parent and str(target.parent) not in ("", "."):
                score = max(score, 0.7)

    return score


def _module_stem_tokens(path_value: str) -> set[str]:
    path = Path(path_value)
    stem = path.stem
    if stem.startswith("test_"):
        stem = stem[len("test_") :]
    tokens = [item for item in re.split(r"[_\\-]+", stem) if item]
    return {item.lower() for item in tokens if len(item) > 2}


def _module_affinity(target_files: list[str], candidate_files: list[str]) -> float:
    if not target_files or not candidate_files:
        return 0.0

    target_paths = [Path(value) for value in target_files if value]
    candidate_paths = [Path(value) for value in candidate_files if value]
    score = 0.0

    for target in target_paths:
        for candidate in candidate_paths:
            if target == candidate:
                score = max(score, 1.0)
                continue

            target_tokens = _module_stem_tokens(str(target))
            candidate_tokens = _module_stem_tokens(str(candidate))
            if target_tokens and candidate_tokens:
                overlap = target_tokens & candidate_tokens
                if overlap:
                    score = max(score, 0.82)
                    continue

            if target.parent == candidate.parent and str(target.parent) not in ("", "."):
                score = max(score, 0.7)
                continue

            if target.parts[:2] == candidate.parts[:2] and len(target.parts) >= 2 and len(candidate.parts) >= 2:
                score = max(score, 0.4)

    return score


def _has_timeout_artifact(session: SessionState) -> bool:
    return any(item.kind == "timeout_artifact" for item in session.artifacts)


def _resolve_pattern_affinity(
    *,
    pattern: CollaborationPattern,
    session: SessionState,
    current_task_signature: str,
    current_task_family: str,
    current_error_family: str,
) -> tuple[str, float]:
    stored_task_signature, stored_task_family, stored_error_family = _resolve_pattern_task_metadata(pattern, session)
    if current_task_signature and stored_task_signature and current_task_signature == stored_task_signature:
        return "exact_task_signature", 3.0
    if current_task_family and stored_task_family and current_task_family == stored_task_family:
        return "same_task_family", 2.0
    if current_error_family and stored_error_family and current_error_family == stored_error_family:
        return "same_error_family", 1.0
    return "broader_similarity", 0.0


def _affinity_rank(level: str) -> int:
    return {
        "exact_task_signature": 3,
        "same_task_family": 2,
        "same_error_family": 1,
        "broader_similarity": 0,
    }.get((level or "broader_similarity").strip(), 0)


def _session_affinity_level(
    *,
    current_task_signature: str,
    current_task_family: str,
    current_error_family: str,
    prior: SessionState,
) -> str:
    prior_task_signature, prior_task_family, prior_error_family = _session_task_metadata(prior)
    if current_task_signature and prior_task_signature and current_task_signature == prior_task_signature:
        return "exact_task_signature"
    if current_task_family and prior_task_family and current_task_family == prior_task_family:
        return "same_task_family"
    if current_error_family and prior_error_family and current_error_family == prior_error_family:
        return "same_error_family"
    return "broader_similarity"


def _select_family_scoped_prior_sessions(
    *,
    ranked_prior_sessions: list[SessionState],
    current_task_signature: str,
    current_task_family: str,
    current_error_family: str,
) -> tuple[str, list[SessionState]]:
    exact = [
        prior
        for prior in ranked_prior_sessions
        if _session_affinity_level(
            current_task_signature=current_task_signature,
            current_task_family=current_task_family,
            current_error_family=current_error_family,
            prior=prior,
        )
        == "exact_task_signature"
    ]
    if exact:
        return "exact_task_signature", exact

    same_family = [
        prior
        for prior in ranked_prior_sessions
        if _session_affinity_level(
            current_task_signature=current_task_signature,
            current_task_family=current_task_family,
            current_error_family=current_error_family,
            prior=prior,
        )
        == "same_task_family"
    ]
    if same_family:
        return "same_task_family", same_family

    same_error = [
        prior
        for prior in ranked_prior_sessions
        if _session_affinity_level(
            current_task_signature=current_task_signature,
            current_task_family=current_task_family,
            current_error_family=current_error_family,
            prior=prior,
        )
        == "same_error_family"
    ]
    if same_error:
        return "same_error_family", same_error

    return "broader_similarity", ranked_prior_sessions


def _rank_prior_sessions_for_strategy(
    *,
    prior_sessions: list[SessionState],
    target_files: list[str],
    current_task_signature: str,
    current_task_family: str,
    current_error_family: str,
) -> list[SessionState]:
    ranked: list[tuple[float, SessionState]] = []

    for prior in prior_sessions:
        prior_task_signature, prior_task_family, prior_error_family = _session_task_metadata(prior)
        trust_score = 0.0
        if current_task_signature and prior_task_signature and current_task_signature == prior_task_signature:
            trust_score = 3.0
        elif current_task_family and prior_task_family and current_task_family == prior_task_family:
            trust_score = 2.0
        elif current_error_family and prior_error_family and current_error_family == prior_error_family:
            trust_score = 1.0

        similarity_score = max(
            _path_affinity(target_files, prior.target_files[:8]),
            _module_affinity(target_files, prior.target_files[:8]),
        )
        quality_score = 0.0
        if prior.strategy_summary:
            quality_score += 0.2
        if prior.routing_signal_summary and prior.routing_signal_summary.routed_role_count:
            quality_score += 0.2
        if prior.collaboration_patterns:
            quality_score += min(len(prior.collaboration_patterns), 6) * 0.03
        if prior.artifacts:
            quality_score += min(len(prior.artifacts), 6) * 0.02

        ranked.append((trust_score + similarity_score + quality_score, prior))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [prior for _, prior in ranked]


def _strategy_family_kind(task_family: str) -> str:
    normalized = (task_family or "").lower()
    if any(token in normalized for token in ("completion", "shell")):
        return "completion"
    if any(token in normalized for token in ("termui", "prompt", "pager", "ui")):
        return "interactive"
    if any(token in normalized for token in ("testing", "runner")):
        return "testing"
    if any(token in normalized for token in ("utils", "types")):
        return "utility"
    return "generic"


def _choose_strategy_profile(
    *,
    trust_signal: str,
    task_family: str,
    current_error_family: str,
    timeout_affinity: float,
    selected_patterns: list[CollaborationPattern],
    preferred_artifacts: list[str],
) -> tuple[str, str, list[str], int, int]:
    has_working_set = any(item.kind in {"working_set_strategy", "effective_edit_scope_strategy"} for item in selected_patterns)
    has_validation = any(item.kind == "validation_strategy" for item in selected_patterns)
    has_artifact_guidance = any(
        item.kind in {"artifact_reference_strategy", "artifact_routing_strategy", "artifact_scope_strategy"}
        for item in selected_patterns
    ) or bool(preferred_artifacts)
    recovery_error_family = current_error_family in {
        "error:timeout",
        "error:regression-expansion",
        "error:scope-drift",
        "error:syntax-error",
    }
    recovery_pressure = recovery_error_family or (
        timeout_affinity >= 0.7 and trust_signal not in {"exact_task_signature", "same_task_family"}
    )
    family_kind = _strategy_family_kind(task_family)

    if recovery_pressure:
        return (
            "guarded_recovery",
            "baseline_first",
            ["investigator", "implementer", "verifier"],
            3,
            8,
        )
    if trust_signal == "exact_task_signature" and has_validation and has_artifact_guidance:
        return (
            "artifact_guided_fast_path",
            "targeted_first",
            ["implementer", "verifier", "investigator"],
            4,
            9,
        )
    if trust_signal in {"exact_task_signature", "same_task_family"} and family_kind == "interactive":
        return (
            "interactive_reuse_loop",
            "targeted_first",
            ["implementer", "verifier", "investigator"],
            4,
            10,
        )
    if trust_signal in {"exact_task_signature", "same_task_family"} and family_kind == "completion":
        return (
            "completion_family_loop",
            "targeted_first",
            ["investigator", "implementer", "verifier"],
            5,
            10,
        )
    if trust_signal in {"same_task_family", "same_error_family"} and (has_working_set or has_validation):
        return (
            "family_reuse_loop",
            "targeted_first",
            ["investigator", "implementer", "verifier"],
            5,
            11,
        )
    return (
        "broad_discovery",
        "targeted_then_expand",
        ["investigator", "implementer", "verifier"],
        6,
        14,
    )


def _working_set_specificity(paths: list[str]) -> tuple[int, int, int]:
    normalized = [Path(value.strip()) for value in paths if isinstance(value, str) and value.strip()]
    return (
        sum(len(path.parts) for path in normalized),
        sum(1 for path in normalized if path.suffix),
        -len(normalized),
    )


def _prefer_narrower_working_set(current: list[str], candidate: list[str]) -> list[str]:
    normalized_candidate = [value.strip() for value in candidate if isinstance(value, str) and value.strip()][:8]
    if not normalized_candidate:
        return current
    normalized_current = [value.strip() for value in current if isinstance(value, str) and value.strip()][:8]
    if not normalized_current:
        return normalized_candidate
    if len(normalized_candidate) < len(normalized_current):
        return normalized_candidate
    if _working_set_specificity(normalized_candidate) > _working_set_specificity(normalized_current):
        return normalized_candidate
    return normalized_current


def _latest_delegation_return_for_role(session: SessionState, role: str) -> DelegationReturn | None:
    for item in session.delegation_returns:
        if item.role == role:
            return item
    return None


def _specialist_retry_guidance(
    session: SessionState,
) -> tuple[list[str], list[str], list[str], list[str], str]:
    routing = session.routing_signal_summary
    continuity = session.continuity_snapshot or {}
    implementer_return = _latest_delegation_return_for_role(session, "implementer")
    verifier_return = _latest_delegation_return_for_role(session, "verifier")

    scope: list[str] = []
    validation_intent: list[str] = []
    blockers: list[str] = []
    next_actions: list[str] = []
    source = ""

    if routing:
        if routing.implementer_effective_scope:
            scope = [value for value in routing.implementer_effective_scope if isinstance(value, str) and value.strip()][:8]
            source = "routing_signal_summary"
        if routing.verifier_validation_intent:
            validation_intent = [
                value for value in routing.verifier_validation_intent if isinstance(value, str) and value.strip()
            ][:4]
            source = source or "routing_signal_summary"
        if routing.verifier_blockers:
            blockers = [value for value in routing.verifier_blockers if isinstance(value, str) and value.strip()][:4]
            source = source or "routing_signal_summary"
        if routing.specialist_next_actions:
            next_actions = [value for value in routing.specialist_next_actions if isinstance(value, str) and value.strip()][:4]
            source = source or "routing_signal_summary"

    if not scope and isinstance(continuity.get("implementer_effective_scope"), list):
        scope = [value for value in continuity.get("implementer_effective_scope", []) if isinstance(value, str) and value.strip()][:8]
        source = source or "continuity_snapshot"
    if not validation_intent and isinstance(continuity.get("verifier_validation_intent"), list):
        validation_intent = [
            value for value in continuity.get("verifier_validation_intent", []) if isinstance(value, str) and value.strip()
        ][:4]
        source = source or "continuity_snapshot"
    if not blockers and isinstance(continuity.get("verifier_blockers"), list):
        blockers = [value for value in continuity.get("verifier_blockers", []) if isinstance(value, str) and value.strip()][:4]
        source = source or "continuity_snapshot"
    if not next_actions and isinstance(continuity.get("specialist_next_actions"), list):
        next_actions = [value for value in continuity.get("specialist_next_actions", []) if isinstance(value, str) and value.strip()][:4]
        source = source or "continuity_snapshot"

    if not scope and implementer_return and implementer_return.working_set:
        scope = [value for value in implementer_return.working_set if isinstance(value, str) and value.strip()][:8]
        source = source or "delegation_return"
    if not validation_intent and verifier_return and verifier_return.validation_intent:
        validation_intent = [
            value for value in verifier_return.validation_intent if isinstance(value, str) and value.strip()
        ][:4]
        source = source or "delegation_return"
    if not blockers and verifier_return and verifier_return.blockers:
        blockers = [value for value in verifier_return.blockers if isinstance(value, str) and value.strip()][:4]
        source = source or "delegation_return"
    if not next_actions:
        delegated_actions: list[str] = []
        for prior_return in (implementer_return, verifier_return):
            if prior_return and isinstance(prior_return.next_action, str) and prior_return.next_action.strip():
                delegated_actions.append(prior_return.next_action.strip())
        if delegated_actions:
            next_actions = list(dict.fromkeys(delegated_actions))[:4]
            source = source or "delegation_return"

    return (
        list(dict.fromkeys(scope))[:8],
        list(dict.fromkeys(validation_intent))[:4],
        list(dict.fromkeys(blockers))[:4],
        list(dict.fromkeys(next_actions))[:4],
        source or "none",
    )


def _specialist_retry_recommendation(
    session: SessionState,
    *,
    scope: list[str],
    validation_intent: list[str],
    blockers: list[str],
    next_actions: list[str],
) -> str:
    verifier_return = _latest_delegation_return_for_role(session, "verifier")
    implementer_return = _latest_delegation_return_for_role(session, "implementer")
    handoff_target = ""
    if verifier_return and verifier_return.status != "success":
        handoff_target = str(verifier_return.handoff_target or "").strip()
        if not handoff_target and (scope or validation_intent or blockers):
            handoff_target = "implementer"
    if not handoff_target and implementer_return:
        handoff_target = str(implementer_return.handoff_target or "").strip()

    narrowed_scope = ", ".join(value for value in scope[:3] if value)
    primary_validation = next((value for value in validation_intent if value), "")
    primary_blocker = next((value for value in blockers if value), "")

    if handoff_target and handoff_target != "orchestrator":
        recommendation = f"Follow the specialist handoff back to {handoff_target}"
        if narrowed_scope:
            recommendation += f" inside {narrowed_scope}"
        if primary_blocker:
            recommendation += f" to address {primary_blocker[:180]}"
        if primary_validation:
            recommendation += f", then rerun {primary_validation}"
        return recommendation + "."

    if next_actions:
        return next_actions[0][:240]
    if primary_validation and narrowed_scope:
        return f"Stay inside {narrowed_scope} and rerun {primary_validation}."
    if primary_validation:
        return f"Rerun {primary_validation} before broadening scope."
    if primary_blocker:
        return f"Address the verifier blocker before broadening scope: {primary_blocker[:180]}."
    return ""


def select_collaboration_strategy(
    *,
    prior_sessions: list[SessionState],
    target_files: list[str],
    validation_commands: list[str],
    task_text: str = "",
    validation_summary: str = "",
    failure_name: str = "",
) -> StrategySelection:
    selected_files = list(dict.fromkeys(target_files))
    selected_commands = list(dict.fromkeys(validation_commands))
    memory_lines: list[str] = []
    artifact_limit = 6
    memory_source_limit = 14
    timeout_affinity = 0.0
    current_task_signature = _derive_task_signature(
        task_text=task_text,
        target_files=target_files,
        validation_summary=validation_summary,
        failure_name=failure_name,
    )
    current_task_family = _derive_task_family(
        task_text=task_text,
        target_files=target_files,
        validation_summary=validation_summary,
    )
    current_error_family = _derive_error_family(
        validation_summary=validation_summary,
        failure_name=failure_name,
    )

    strategy_prior_sessions = prior_sessions[:32]
    ranked_prior_sessions = _rank_prior_sessions_for_strategy(
        prior_sessions=strategy_prior_sessions,
        target_files=target_files,
        current_task_signature=current_task_signature,
        current_task_family=current_task_family,
        current_error_family=current_error_family,
    )
    family_scope, family_scoped_sessions = _select_family_scoped_prior_sessions(
        ranked_prior_sessions=ranked_prior_sessions,
        current_task_signature=current_task_signature,
        current_task_family=current_task_family,
        current_error_family=current_error_family,
    )
    candidate_sessions = family_scoped_sessions[:8] or ranked_prior_sessions[:8]
    candidate_task_ids = {prior.task_id for prior in candidate_sessions if prior.task_id}

    for prior in ranked_prior_sessions[:6]:
        if not _has_timeout_artifact(prior):
            continue
        timeout_affinity = max(
            timeout_affinity,
            max(
                _path_affinity(target_files, prior.target_files[:8]),
                _module_affinity(target_files, prior.target_files[:8]),
            ),
        )

    if timeout_affinity >= 0.7:
        artifact_limit = 3
        memory_source_limit = 8
        memory_lines.append(
            "Timeout-aware strategy: keep prior artifact references minimal and stay on the narrowest known working set before expanding scope."
        )

    ranked_patterns: list[tuple[float, CollaborationPattern, SessionState]] = []
    for prior in candidate_sessions:
        prior_files = prior.target_files[:8]
        for pattern in prior.collaboration_patterns[:7]:
            if pattern.kind == "artifact_routing_strategy" and family_scope in {
                "exact_task_signature",
                "same_task_family",
            }:
                routed_paths = _parse_reuse_hint_files(pattern.reuse_hint)
                family_paths = [
                    path for path in routed_paths if _artifact_task_id_from_path(path) in candidate_task_ids
                ]
                if routed_paths and not family_paths:
                    continue
                if family_paths and len(family_paths) != len(routed_paths):
                    pattern = CollaborationPattern(
                        **{
                            **pattern.__dict__,
                            "reuse_hint": ",".join(family_paths[:3]),
                            "summary": (
                                f"Route {pattern.role} through {', '.join(family_paths[:2])} before widening context."
                            )[:240],
                        }
                    )
            affinity_level, trust_affinity = _resolve_pattern_affinity(
                pattern=pattern,
                session=prior,
                current_task_signature=current_task_signature,
                current_task_family=current_task_family,
                current_error_family=current_error_family,
            )
            candidate_files = []
            if pattern.kind in {"working_set_strategy", "implementation_scope", "effective_edit_scope_strategy"} and pattern.reuse_hint:
                candidate_files = _parse_reuse_hint_files(pattern.reuse_hint)
            else:
                candidate_files = prior_files
            similarity_affinity = max(
                _path_affinity(target_files, candidate_files),
                _module_affinity(target_files, candidate_files),
            )
            score = pattern.confidence + trust_affinity + similarity_affinity
            if (
                target_files
                and trust_affinity == 0
                and similarity_affinity == 0
                and pattern.kind not in {"role_sequence_strategy", "artifact_reference_strategy"}
            ):
                score -= 0.25
            if pattern.kind == "artifact_reference_strategy":
                score += 0.08
            if pattern.kind == "effective_edit_scope_strategy":
                score += 0.14
            if pattern.kind == "artifact_routing_strategy":
                score += 0.16
                if affinity_level in {"exact_task_signature", "same_task_family"}:
                    score += 0.08
                routed_task_ids = _artifact_task_ids_from_reuse_hint(pattern.reuse_hint)
                if routed_task_ids and candidate_task_ids:
                    family_hits = sum(1 for task_id in routed_task_ids if task_id in candidate_task_ids)
                    non_family_hits = sum(1 for task_id in routed_task_ids if task_id not in candidate_task_ids)
                    score += family_hits * 0.18
                    score -= non_family_hits * 0.12
                    if family_scope in {"exact_task_signature", "same_task_family"} and family_hits == 0:
                        score -= 0.35
            if family_scope == "same_task_family" and affinity_level == "same_task_family":
                score += 0.25
            elif family_scope == "exact_task_signature" and affinity_level == "exact_task_signature":
                score += 0.35
            elif family_scope == "same_error_family" and affinity_level == "same_error_family":
                score += 0.18
            if pattern.kind == "role_sequence_strategy":
                score += 0.05
            pattern.affinity_level = affinity_level
            ranked_patterns.append((score, pattern, prior))

    ranked_patterns.sort(key=lambda item: (item[0], len(item[1].evidence), item[1].kind), reverse=True)
    selected_kinds: set[str] = set()
    preferred_artifacts: list[str] = []
    selected_working_set: list[str] = []
    role_sequence: list[str] = []
    selected_patterns: list[CollaborationPattern] = []
    specialist_recommendation = ""

    for score, pattern, prior in ranked_patterns:
        if score < 0.65:
            continue
        if pattern.kind in selected_kinds and pattern.kind not in {"artifact_reference_strategy", "artifact_routing_strategy", "artifact_scope_strategy"}:
            continue
        if pattern.kind in {"working_set_strategy", "implementation_scope", "effective_edit_scope_strategy"} and pattern.reuse_hint:
            parsed_files = _parse_reuse_hint_files(pattern.reuse_hint)
            selected_files = _prioritize_candidates(selected_files, parsed_files, limit=12)
            selected_working_set = _prefer_narrower_working_set(selected_working_set, parsed_files)
            memory_lines.append(
                f"Selected collaboration strategy ({pattern.affinity_level}): [{pattern.role}/{pattern.kind}] {pattern.summary}"
            )
            selected_kinds.add(pattern.kind)
            selected_patterns.append(pattern)
        elif pattern.kind == "validation_strategy" and pattern.reuse_hint:
            if pattern.reuse_hint not in selected_commands:
                selected_commands.append(pattern.reuse_hint)
            memory_lines.append(
                f"Selected validation strategy ({pattern.affinity_level}): [{pattern.role}/{pattern.kind}] {pattern.summary}"
            )
            selected_kinds.add(pattern.kind)
            selected_patterns.append(pattern)
        elif pattern.kind == "role_sequence_strategy" and pattern.reuse_hint and not role_sequence:
            role_sequence = [item.strip() for item in pattern.reuse_hint.split(",") if item.strip()]
            if role_sequence:
                memory_lines.append(
                    "Selected role sequence: " + " -> ".join(role_sequence)
                )
                selected_kinds.add(pattern.kind)
                selected_patterns.append(pattern)
        elif pattern.kind in {"artifact_reference_strategy", "artifact_routing_strategy", "artifact_scope_strategy"}:
            matched_paths: list[str] = []
            if pattern.kind == "artifact_reference_strategy":
                role, _, artifact_kind = pattern.reuse_hint.partition(":")
                artifact = next(
                    (
                        item
                        for item in prior.artifacts
                        if item.role == role and (not artifact_kind or item.kind == artifact_kind)
                    ),
                    None,
                )
                if artifact:
                    matched_paths.append(artifact.path)
            else:
                matched_paths.extend(
                    value.strip()
                    for value in pattern.reuse_hint.split(",")
                    if isinstance(value, str) and value.strip()
                )
            added = False
            for path in matched_paths:
                if path not in preferred_artifacts:
                    preferred_artifacts.append(path)
                    added = True
            if matched_paths:
                memory_lines.append(
                    f"Selected artifact strategy ({pattern.affinity_level}): [{pattern.role}/{pattern.kind}] prefer {', '.join(matched_paths[:3])}"
                )
                if added or pattern.kind == "artifact_routing_strategy":
                    selected_patterns.append(pattern)

    trust_signal = "broader_similarity"
    if selected_patterns:
        trust_signal = max(
            (pattern.affinity_level for pattern in selected_patterns),
            key=_affinity_rank,
            default="broader_similarity",
        )
    strategy_profile, validation_style, profile_role_sequence, profile_artifact_limit, profile_memory_source_limit = _choose_strategy_profile(
        trust_signal=trust_signal,
        task_family=current_task_family,
        current_error_family=current_error_family,
        timeout_affinity=timeout_affinity,
        selected_patterns=selected_patterns,
        preferred_artifacts=preferred_artifacts,
    )

    artifact_limit = min(artifact_limit, profile_artifact_limit) if timeout_affinity >= 0.7 else profile_artifact_limit
    memory_source_limit = min(memory_source_limit, profile_memory_source_limit) if timeout_affinity >= 0.7 else profile_memory_source_limit
    if (
        strategy_profile in {"interactive_reuse_loop", "artifact_guided_fast_path"}
        and profile_role_sequence
    ):
        role_sequence = profile_role_sequence
    elif not role_sequence:
        role_sequence = profile_role_sequence
    prioritized_patterns = sorted(
        selected_patterns,
        key=lambda item: (
            1 if item.kind == "artifact_routing_strategy" else 0,
            1 if item.kind == "role_sequence_strategy" else 0,
            item.confidence,
        ),
        reverse=True,
    )
    selected_pattern_summaries = list(
        dict.fromkeys(f"[{item.role}/{item.kind}] {item.summary}" for item in prioritized_patterns)
    )[:4]
    if current_task_family:
        memory_lines.append(f"Selected task family: {current_task_family}")
    memory_lines.append(f"Selected family scope: {family_scope}")
    memory_lines.append(f"Family candidate sessions: {len(candidate_sessions)}")
    memory_lines.append(f"Selected strategy profile: {strategy_profile}")
    memory_lines.append(f"Selected validation style: {validation_style}")
    if validation_summary.strip() or failure_name.strip():
        retry_scope: list[str] = []
        retry_validation_commands: list[str] = []
        retry_blockers: list[str] = []
        retry_next_actions: list[str] = []
        retry_source = ""
        for prior in candidate_sessions[:4]:
            (
                guidance_scope,
                guidance_validation,
                guidance_blockers,
                guidance_next_actions,
                guidance_source,
            ) = _specialist_retry_guidance(prior)
            if not guidance_scope and not guidance_validation and not guidance_blockers and not guidance_next_actions:
                continue
            scope_affinity = (
                max(
                    _path_affinity(target_files, guidance_scope),
                    _module_affinity(target_files, guidance_scope),
                )
                if guidance_scope
                else 0.0
            )
            if guidance_scope and (
                family_scope in {"exact_task_signature", "same_task_family", "same_error_family"}
                or scope_affinity >= 0.45
            ):
                retry_scope = _prefer_narrower_working_set(retry_scope, guidance_scope)
            if guidance_validation:
                retry_validation_commands.extend(guidance_validation)
            if guidance_blockers:
                retry_blockers.extend(guidance_blockers)
            if guidance_next_actions:
                retry_next_actions.extend(guidance_next_actions)
            if guidance_source != "none" and not retry_source:
                retry_source = guidance_source
            if not specialist_recommendation:
                specialist_recommendation = _specialist_retry_recommendation(
                    prior,
                    scope=guidance_scope,
                    validation_intent=guidance_validation,
                    blockers=guidance_blockers,
                    next_actions=guidance_next_actions,
                )
        if retry_scope:
            selected_files = _prioritize_candidates(selected_files, retry_scope, limit=12)
            selected_working_set = _prefer_narrower_working_set(selected_working_set, retry_scope)
            memory_lines.append(
                "Selected retry scope from specialist handoff"
                + (f" ({retry_source})" if retry_source else "")
                + f": {', '.join(retry_scope[:4])}"
            )
        if retry_validation_commands:
            selected_commands = _prioritize_candidates(selected_commands, retry_validation_commands, limit=8)
            memory_lines.append(
                "Selected verifier retry path"
                + (f" ({retry_source})" if retry_source else "")
                + f": {'; '.join(selected_commands[:2])}"
            )
        if retry_blockers:
            memory_lines.append("Retry blockers: " + "; ".join(list(dict.fromkeys(retry_blockers))[:2]))
        if retry_next_actions:
            memory_lines.append(
                "Specialist retry next action: " + list(dict.fromkeys(retry_next_actions))[0][:220]
            )
        if specialist_recommendation:
            memory_lines.append("Specialist graph recommendation: " + specialist_recommendation[:220])
    if role_sequence:
        memory_lines.append("Applied role sequence: " + " -> ".join(role_sequence[:3]))
    if not selected_working_set:
        selected_working_set = selected_files[:8]

    return StrategySelection(
        target_files=selected_files[:6] if timeout_affinity >= 0.7 else selected_files[:12],
        selected_working_set=selected_working_set[:8],
        validation_commands=selected_commands[:1] if validation_style == "baseline_first" else (selected_commands[:2] if validation_style == "targeted_first" else selected_commands[:8]),
        memory_lines=list(dict.fromkeys(memory_lines))[:6],
        artifact_limit=artifact_limit,
        memory_source_limit=memory_source_limit,
        task_family=current_task_family,
        family_scope=family_scope,
        family_candidate_count=len(candidate_sessions),
        preferred_artifacts=preferred_artifacts[:artifact_limit],
        role_sequence=role_sequence[:3],
        strategy_profile=strategy_profile,
        validation_style=validation_style,
        trust_signal=trust_signal,
        selected_pattern_summaries=selected_pattern_summaries,
        specialist_recommendation=specialist_recommendation[:240],
    )


def promote_insights(
    *,
    session: SessionState,
    trace_steps: list[TraceStep],
    content: str,
    delegation_returns: list[DelegationReturn] | None = None,
    validation_ok: bool | None = None,
    validation_command: str | None = None,
    validation_summary: str | None = None,
    changed_files: list[str] | None = None,
) -> None:
    new_targets = extract_target_files(trace_steps, repo_root=session.repo_root)
    if new_targets:
        session.target_files = list(dict.fromkeys([*session.target_files, *new_targets]))[:12]
    relevant_changed_files = _filter_relevant_changed_files(session, changed_files)

    promoted: list[str] = []
    if session.target_files:
        promoted.append("High-signal target files: " + ", ".join(session.target_files[:8]))
    if session.validation_commands:
        promoted.append("Validation path: " + "; ".join(session.validation_commands[:4]))
    if content.strip():
        promoted.append("Latest execution outcome: " + content.strip().splitlines()[0][:240])

    for item in promoted:
        if item not in session.promoted_insights:
            session.promoted_insights.append(item)

    if delegation_returns:
        session.delegation_returns = delegation_returns
    else:
        session.delegation_returns = _build_delegation_returns(
            session=session,
            trace_steps=trace_steps,
            content=content,
            validation_ok=validation_ok,
            validation_command=validation_command,
            validation_summary=validation_summary,
            changed_files=relevant_changed_files,
        )
    session.collaboration_patterns = _build_collaboration_patterns(
        session=session,
        delegation_returns=session.delegation_returns,
        validation_ok=validation_ok,
        validation_command=validation_command,
    )
    recent_steps = [f"{step.tool_name} [{step.status}]" for step in trace_steps[-8:]]
    session.working_memory = recent_steps[-6:]
    session.promoted_insights = _dedupe_latest_by_prefix(
        session.promoted_insights,
        (
            "High-signal target files: ",
            "Validation path: ",
            "Latest execution outcome: ",
            "Validation passed: ",
            "Validation failed command: ",
        ),
    )
    overflow = session.promoted_insights[12:]
    if overflow:
        for item in overflow:
            add_forgetting_entry(session, value=item, reason="promoted_overflow")
        session.promoted_insights = session.promoted_insights[:12]
    compact_forgetting_backlog(session)
    refresh_delegation_packets(session)


def refresh_collaboration_patterns(session: SessionState) -> None:
    validation_command = session.validation_commands[0] if session.validation_commands else None
    validation_ok_value = session.last_validation_result.get("ok")
    validation_ok = validation_ok_value if isinstance(validation_ok_value, bool) else None
    session.collaboration_patterns = _build_collaboration_patterns(
        session=session,
        delegation_returns=session.delegation_returns,
        validation_ok=validation_ok if session.delegation_returns else None,
        validation_command=validation_command,
    )


def trace_summary(trace_steps: list[TraceStep]) -> dict[str, int]:
    return {
        "steps_observed": len(trace_steps),
        "tool_steps": sum(1 for step in trace_steps if step.tool_name != "workbench.model"),
        "model_steps": sum(1 for step in trace_steps if step.tool_name == "workbench.model"),
        "successful_steps": sum(1 for step in trace_steps if step.status == "success"),
        "errored_steps": sum(1 for step in trace_steps if step.status != "success"),
    }
