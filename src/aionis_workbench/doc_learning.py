from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .session import SessionState, load_recent_sessions


_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".aionis-workbench",
    "dist",
    "build",
    ".pytest_cache",
    "coverage",
}


def _session_task_family(session: SessionState) -> str:
    if session.selected_task_family:
        return session.selected_task_family
    continuity = session.continuity_snapshot or {}
    return str(continuity.get("task_family") or "").strip()


def build_doc_learning_record(session: SessionState) -> dict[str, Any] | None:
    continuity = session.continuity_snapshot or {}
    doc_workflow = continuity.get("doc_workflow")
    if not isinstance(doc_workflow, dict) or not doc_workflow:
        return None
    history = [
        {
            "action": str(item.get("action") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "doc_input": str(item.get("doc_input") or "").strip(),
            "handoff_anchor": str(item.get("handoff_anchor") or "").strip(),
            "handoff_kind": str(item.get("handoff_kind") or "").strip(),
            "selected_tool": str(item.get("selected_tool") or "").strip(),
            "event_source": str(item.get("event_source") or "").strip(),
            "event_origin": str(item.get("event_origin") or "").strip(),
            "recorded_at": str(item.get("recorded_at") or "").strip(),
        }
        for item in (doc_workflow.get("history") or [])
        if isinstance(item, dict)
    ]
    history = [item for item in history if item["action"]][:6]
    artifact_refs = [
        str(item).strip()
        for item in (doc_workflow.get("artifact_refs") or [])
        if isinstance(item, str) and str(item).strip()
    ][:8]
    preferred_artifact_refs = [
        str(item).strip()
        for item in (continuity.get("preferred_artifact_refs") or [])
        if isinstance(item, str) and str(item).strip()
    ][:8]
    latest_action = str(doc_workflow.get("latest_action") or "").strip()
    latest_status = str(doc_workflow.get("status") or "").strip() or "unknown"
    source_doc_id = str(doc_workflow.get("source_doc_id") or "").strip()
    source_doc_version = str(doc_workflow.get("source_doc_version") or "").strip()
    handoff_anchor = str(doc_workflow.get("handoff_anchor") or "").strip()
    handoff_kind = str(doc_workflow.get("handoff_kind") or "").strip()
    selected_tool = str(doc_workflow.get("selected_tool") or "").strip()
    doc_input = str(doc_workflow.get("doc_input") or "").strip()
    event_source = str(doc_workflow.get("event_source") or "").strip()
    event_origin = str(doc_workflow.get("event_origin") or "").strip()
    recorded_at = str(doc_workflow.get("recorded_at") or "").strip()
    task_family = _session_task_family(session)
    summary_parts = [
        f"action={latest_action or 'unknown'}",
        f"status={latest_status}",
    ]
    if source_doc_id:
        summary_parts.append(f"doc={source_doc_id}")
    if handoff_anchor:
        summary_parts.append(f"anchor={handoff_anchor}")
    if selected_tool:
        summary_parts.append(f"tool={selected_tool}")
    if event_source:
        summary_parts.append(f"sync={event_source}")
    return {
        "task_id": session.task_id,
        "task_family": task_family,
        "latest_action": latest_action,
        "latest_status": latest_status,
        "doc_input": doc_input,
        "source_doc_id": source_doc_id,
        "source_doc_version": source_doc_version,
        "handoff_anchor": handoff_anchor,
        "handoff_kind": handoff_kind,
        "selected_tool": selected_tool,
        "event_source": event_source,
        "event_origin": event_origin,
        "recorded_at": recorded_at,
        "artifact_refs": artifact_refs,
        "preferred_artifact_refs": preferred_artifact_refs,
        "history": history,
        "history_count": len(history),
        "artifact_count": len(artifact_refs),
        "summary": " ".join(summary_parts),
    }


def _normalize_doc_input(doc_input: str, *, repo_root: str) -> str:
    cleaned = str(doc_input or "").strip()
    if not cleaned:
        return ""
    repo_path = Path(repo_root).expanduser().resolve()
    candidate = Path(cleaned).expanduser()
    try:
        resolved = candidate.resolve() if candidate.is_absolute() else (repo_path / candidate).resolve()
    except OSError:
        resolved = candidate if candidate.is_absolute() else (repo_path / candidate)
    try:
        return resolved.relative_to(repo_path).as_posix()
    except ValueError:
        return cleaned


def _discover_doc_paths(repo_root: str, *, limit: int) -> list[str]:
    repo_path = Path(repo_root).expanduser().resolve()
    discovered: list[str] = []
    for current_root, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
        base = Path(current_root)
        for filename in sorted(filenames):
            if not filename.endswith(".aionis.md"):
                continue
            path = (base / filename).relative_to(repo_path).as_posix()
            discovered.append(path)
            if len(discovered) >= limit:
                return discovered
    return discovered


def list_doc_learning_records(
    *,
    repo_root: str,
    project_scope: str,
    limit: int = 24,
    recent_session_limit: int = 64,
) -> list[dict[str, Any]]:
    doc_paths = _discover_doc_paths(repo_root, limit=limit)
    recent = load_recent_sessions(
        repo_root,
        project_scope=project_scope,
        exclude_task_id=None,
        limit=recent_session_limit,
    )
    evidence_index: dict[str, list[dict[str, Any]]] = {}
    for session in recent:
        record = build_doc_learning_record(session)
        if not record:
            continue
        normalized = _normalize_doc_input(str(record.get("doc_input") or ""), repo_root=repo_root)
        if normalized:
            evidence_index.setdefault(normalized, []).append(record)
        basename = Path(normalized or str(record.get("doc_input") or "")).name
        if basename and basename != normalized:
            evidence_index.setdefault(basename, []).append(record)

    rows: list[dict[str, Any]] = []
    for path in doc_paths[:limit]:
        evidence = (evidence_index.get(path) or evidence_index.get(Path(path).name) or [])
        latest = evidence[0] if evidence else {}
        latest = latest if isinstance(latest, dict) else {}
        rows.append(
            {
                "path": path,
                "has_evidence": bool(evidence),
                "evidence_count": len(evidence),
                "latest_task_id": str(latest.get("task_id") or "").strip() or None,
                "latest_action": str(latest.get("latest_action") or "").strip() or None,
                "latest_status": str(latest.get("latest_status") or "").strip() or None,
                "source_doc_id": str(latest.get("source_doc_id") or "").strip() or None,
                "handoff_anchor": str(latest.get("handoff_anchor") or "").strip() or None,
                "summary": str(latest.get("summary") or "").strip() or None,
            }
        )
    return rows


def inspect_doc_target(
    *,
    repo_root: str,
    project_scope: str,
    target: str,
    limit: int = 8,
    recent_session_limit: int = 64,
) -> dict[str, Any]:
    cleaned = str(target or "").strip()
    normalized = _normalize_doc_input(cleaned, repo_root=repo_root)
    repo_path = Path(repo_root).expanduser().resolve()
    target_path = Path(cleaned).expanduser()
    if target_path.is_absolute():
        resolved = target_path
    else:
        resolved = repo_path / normalized if normalized else repo_path / cleaned

    if cleaned.endswith(".json"):
        payload: dict[str, Any] = {}
        if resolved.exists():
            try:
                loaded = json.loads(resolved.read_text())
                payload = loaded if isinstance(loaded, dict) else {}
            except (OSError, json.JSONDecodeError):
                payload = {}
        return {
            "inspect_kind": "artifact",
            "target": cleaned,
            "resolved_target": normalized or cleaned,
            "exists": resolved.exists(),
            "artifact_summary": {
                "kind": str(payload.get("kind") or "").strip() or None,
                "doc_action": str(payload.get("doc_action") or "").strip() or None,
                "status": str(payload.get("status") or "").strip() or None,
                "source_doc_id": str(payload.get("source_doc_id") or "").strip() or None,
                "handoff_anchor": str(payload.get("handoff_anchor") or payload.get("anchor") or "").strip() or None,
            },
            "artifact_payload": payload,
        }

    recent = load_recent_sessions(
        repo_root,
        project_scope=project_scope,
        exclude_task_id=None,
        limit=recent_session_limit,
    )
    matches: list[dict[str, Any]] = []
    target_name = Path(normalized or cleaned).name
    for session in recent:
        record = build_doc_learning_record(session)
        if not record:
            continue
        record_input = _normalize_doc_input(str(record.get("doc_input") or ""), repo_root=repo_root)
        if record_input == normalized or Path(record_input).name == target_name:
            matches.append(record)
    return {
        "inspect_kind": "workflow",
        "target": cleaned,
        "resolved_target": normalized or cleaned,
        "exists": resolved.exists(),
        "evidence_count": len(matches),
        "latest_record": matches[0] if matches else None,
        "recent_records": matches[:limit],
    }
