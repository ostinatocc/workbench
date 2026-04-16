from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .doc_learning import build_doc_learning_record
from .reviewer_contracts import resolve_reviewer_evidence
from .session import SessionState, load_recent_sessions


def _learning_snapshot(session: SessionState) -> dict[str, Any]:
    continuity = session.continuity_snapshot or {}
    if not isinstance(continuity, dict):
        return {}
    learning = continuity.get("learning")
    return learning if isinstance(learning, dict) else {}


def _passive_snapshot(session: SessionState) -> dict[str, Any]:
    continuity = session.continuity_snapshot or {}
    if not isinstance(continuity, dict):
        return {}
    passive = continuity.get("passive_observation")
    return passive if isinstance(passive, dict) else {}


def _task_family(session: SessionState) -> str:
    if session.selected_task_family:
        return session.selected_task_family
    if session.strategy_summary and session.strategy_summary.task_family:
        return session.strategy_summary.task_family
    learning = _learning_snapshot(session)
    if isinstance(learning, dict):
        task_family = str(learning.get("task_family") or "").strip()
        if task_family:
            return task_family
    return "task:unknown"


def _instrumentation_status(session: SessionState) -> str:
    instrumentation = session.instrumentation_summary
    if not instrumentation:
        return "weak_match"
    if (
        instrumentation.family_hit
        and instrumentation.selected_pattern_hit_count > 0
        and instrumentation.routed_artifact_hit_rate >= 0.75
    ):
        return "strong_match"
    if instrumentation.family_hit or instrumentation.selected_pattern_hit_count > 0:
        return "usable_match"
    return "weak_match"


def _dedupe_count(values: list[str]) -> int:
    ordered = [item for item in values if isinstance(item, str) and item.strip()]
    return max(0, len(ordered) - len(list(dict.fromkeys(ordered))))


def _dominant_value(values: list[str]) -> str:
    filtered = [item.strip() for item in values if isinstance(item, str) and item.strip()]
    if not filtered:
        return ""
    return Counter(filtered).most_common(1)[0][0]


def _dominant_working_set(bucket: list[SessionState]) -> list[str]:
    ranked: list[str] = []
    for session in bucket:
        for item in session.target_files[:3]:
            if isinstance(item, str) and item.strip():
                ranked.append(item.strip())
    return list(dict.fromkeys(ranked))[:4]


def _recent_success_count(bucket: list[SessionState]) -> int:
    count = 0
    for session in bucket:
        validation = session.last_validation_result or {}
        ok = validation.get("ok")
        if ok is True:
            count += 1
    return count


def _family_doc_prior(bucket: list[SessionState]) -> dict[str, Any]:
    records = [record for session in bucket if (record := build_doc_learning_record(session))]
    if not records:
        return {}
    doc_inputs = [str(item.get("doc_input") or "").strip() for item in records]
    source_doc_ids = [str(item.get("source_doc_id") or "").strip() for item in records]
    latest_actions = [str(item.get("latest_action") or "").strip() for item in records]
    selected_tools = [str(item.get("selected_tool") or "").strip() for item in records]
    handoff_anchors = [str(item.get("handoff_anchor") or "").strip() for item in records]
    event_sources = [str(item.get("event_source") or "").strip() for item in records]
    recorded_times = [str(item.get("recorded_at") or "").strip() for item in records]
    sample_count = len(records)
    dominant_doc_input = _dominant_value(doc_inputs)
    dominant_source_doc_id = _dominant_value(source_doc_ids)
    dominant_action = _dominant_value(latest_actions)
    dominant_selected_tool = _dominant_value(selected_tools)
    dominant_event_source = _dominant_value(event_sources)
    latest_recorded_at = max((item for item in recorded_times if item), default="")
    anchor_count = sum(1 for item in handoff_anchors if item)
    editor_sync_count = sum(1 for item in event_sources if item)
    confidence = round(
        min(
            1.0,
            (0.5 * min(sample_count / 2.0, 1.0))
            + (0.3 * (anchor_count / sample_count))
            + (0.2 if dominant_source_doc_id else 0.0),
        ),
        3,
    )
    seed_ready = sample_count >= 2 and bool(dominant_source_doc_id)
    if seed_ready:
        seed_reason = (
            f"doc prior is reusable across {sample_count} samples with source_doc_id={dominant_source_doc_id}"
        )
    elif sample_count < 2:
        seed_reason = "doc prior needs at least one more successful sample before it should be reused by default"
    else:
        seed_reason = "doc prior is missing a stable source_doc_id anchor"
    return {
        "sample_count": sample_count,
        "confidence": confidence,
        "dominant_doc_input": dominant_doc_input,
        "dominant_source_doc_id": dominant_source_doc_id,
        "dominant_action": dominant_action,
        "dominant_selected_tool": dominant_selected_tool,
        "dominant_event_source": dominant_event_source,
        "latest_recorded_at": latest_recorded_at,
        "handoff_anchor_count": anchor_count,
        "editor_sync_count": editor_sync_count,
        "seed_ready": seed_ready,
        "seed_reason": seed_reason,
    }


def _session_reviewer_record(session: SessionState) -> dict[str, Any]:
    merged = resolve_reviewer_evidence(
        packet=session.execution_packet,
        continuity_pack=session.continuity_review_pack,
        evolution_pack=session.evolution_review_pack,
    )
    if not merged:
        return {}
    return {
        "standard": str(merged.get("reviewer_standard") or "").strip(),
        "required_outputs": list(merged.get("reviewer_required_outputs") or []),
        "acceptance_checks": list(merged.get("reviewer_acceptance_checks") or []),
        "rollback_required": merged.get("reviewer_rollback_required") is True,
        "ready_required": merged.get("reviewer_ready_required") is True,
        "pack_source": str(merged.get("reviewer_pack_source") or "").strip(),
        "selected_tool": str(merged.get("reviewer_selected_tool") or "").strip(),
        "resume_anchor": str(merged.get("reviewer_resume_anchor") or "").strip(),
        "next_action": str(
            (session.evolution_review_pack.next_action if session.evolution_review_pack else "")
            or (session.continuity_review_pack.next_action if session.continuity_review_pack else "")
            or (session.execution_packet.next_action if session.execution_packet else "")
            or ""
        ).strip(),
    }


def _family_reviewer_prior(bucket: list[SessionState]) -> dict[str, Any]:
    records = [record for session in bucket if (record := _session_reviewer_record(session))]
    if not records:
        return {}

    def _record_signature(item: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
        return (
            str(item.get("standard") or "").strip(),
            "|".join(
                output.strip()
                for output in (item.get("required_outputs") or [])
                if isinstance(output, str) and output.strip()
            ),
            " && ".join(
                check.strip()
                for check in (item.get("acceptance_checks") or [])
                if isinstance(check, str) and check.strip()
            ),
            str(item.get("pack_source") or "").strip(),
            str(item.get("selected_tool") or "").strip(),
            str(item.get("resume_anchor") or "").strip(),
        )

    sample_count = len(records)
    signatures: dict[tuple[str, str, str, str, str, str], int] = {}
    for record in records:
        signature = _record_signature(record)
        signatures[signature] = signatures.get(signature, 0) + 1
    dominant_signature = max(
        signatures.items(),
        key=lambda item: (item[1], item[0][0], item[0][1], item[0][2], item[0][3], item[0][4], item[0][5]),
    )[0]
    dominant_record = next(record for record in records if _record_signature(record) == dominant_signature)
    dominant_standard = str(dominant_record.get("standard") or "").strip()
    dominant_pack_source = str(dominant_record.get("pack_source") or "").strip()
    dominant_selected_tool = str(dominant_record.get("selected_tool") or "").strip()
    dominant_resume_anchor = str(dominant_record.get("resume_anchor") or "").strip()
    dominant_next_action = str(dominant_record.get("next_action") or "").strip()
    dominant_required_outputs = [
        output.strip()
        for output in (dominant_record.get("required_outputs") or [])
        if isinstance(output, str) and output.strip()
    ]
    dominant_acceptance_checks = [
        check.strip()
        for check in (dominant_record.get("acceptance_checks") or [])
        if isinstance(check, str) and check.strip()
    ]
    dominant_sample_count = signatures[dominant_signature]
    ready_required_count = sum(1 for item in records if item.get("ready_required"))
    rollback_required_count = sum(1 for item in records if item.get("rollback_required"))
    confidence = round(
        min(
            1.0,
            (0.5 * min(dominant_sample_count / 2.0, 1.0))
            + (0.2 if dominant_standard else 0.0)
            + (0.15 if dominant_acceptance_checks else 0.0)
            + (0.15 if dominant_resume_anchor else 0.0),
        ),
        3,
    )
    seed_ready = dominant_sample_count >= 2 and bool(dominant_standard)
    if seed_ready:
        seed_reason = (
            f"reviewer prior is reusable across {dominant_sample_count} matching samples with standard={dominant_standard}"
        )
    elif dominant_sample_count < 2:
        seed_reason = "reviewer prior needs at least one more sample before it should gate family reuse by default"
    else:
        seed_reason = "reviewer prior is missing a stable reviewer standard"
    return {
        "sample_count": sample_count,
        "confidence": confidence,
        "dominant_standard": dominant_standard,
        "dominant_pack_source": dominant_pack_source,
        "dominant_selected_tool": dominant_selected_tool,
        "dominant_resume_anchor": dominant_resume_anchor,
        "dominant_next_action": dominant_next_action,
        "dominant_required_outputs": dominant_required_outputs,
        "dominant_acceptance_checks": dominant_acceptance_checks,
        "ready_required_count": ready_required_count,
        "rollback_required_count": rollback_required_count,
        "seed_ready": seed_ready,
        "seed_reason": seed_reason,
    }


def _source_counts(bucket: list[SessionState]) -> dict[str, int]:
    counts = {
        "manual_ingest_count": 0,
        "workflow_closure_count": 0,
        "run_resume_count": 0,
        "validate_count": 0,
        "auto_absorbed_count": 0,
        "passive_observation_count": 0,
    }
    for session in bucket:
        learning = _learning_snapshot(session)
        passive = _passive_snapshot(session)
        source = str(learning.get("source") or "").strip()
        if learning.get("auto_absorbed"):
            counts["auto_absorbed_count"] += 1
        if source == "manual_ingest":
            counts["manual_ingest_count"] += 1
        elif source == "workflow_closure":
            counts["workflow_closure_count"] += 1
        elif source in {"run", "resume"}:
            counts["run_resume_count"] += 1
        elif source == "validate":
            counts["validate_count"] += 1
        if passive.get("recorded"):
            counts["passive_observation_count"] += 1
    return counts


def _learning_source_weight(session: SessionState) -> float:
    learning = _learning_snapshot(session)
    passive = _passive_snapshot(session)
    source = str(learning.get("source") or "").strip()
    if source == "manual_ingest":
        return 1.0
    if source == "workflow_closure":
        return 0.95
    if source in {"run", "resume"}:
        return 0.85
    if source == "validate":
        return 0.7 if passive.get("recorded") else 0.65
    if passive.get("recorded"):
        return 0.45
    if learning:
        return 0.55 if learning.get("auto_absorbed") else 0.5
    return 0.2


def _average_source_weight(bucket: list[SessionState]) -> float:
    if not bucket:
        return 0.0
    total = sum(_learning_source_weight(session) for session in bucket)
    return round(total / len(bucket), 3)


def _prior_confidence(
    *,
    session_count: int,
    strong_count: int,
    usable_count: int,
    recent_success_count: int,
    avg_hit_rate: float,
    avg_source_weight: float,
) -> float:
    if session_count <= 0:
        return 0.0
    strong_ratio = strong_count / session_count
    usable_ratio = usable_count / session_count
    success_ratio = recent_success_count / session_count
    sample_factor = min(session_count / 3.0, 1.0)
    score = (
        0.3 * strong_ratio
        + 0.15 * usable_ratio
        + 0.15 * success_ratio
        + 0.15 * max(min(avg_hit_rate, 1.0), 0.0)
        + 0.1 * sample_factor
        + 0.15 * max(min(avg_source_weight, 1.0), 0.0)
    )
    return round(max(min(score, 1.0), 0.0), 3)


def describe_family_prior_seed(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "").strip()
    confidence = float(row.get("confidence") or 0.0)
    sample_count = int(row.get("sample_count") or row.get("session_count") or 0)
    recent_success_count = int(row.get("recent_success_count") or 0)
    if status not in {"strong_family", "stable_family"}:
        return {
            "seed_ready": False,
            "seed_gate": "status",
            "seed_reason": f"family status {status or 'unknown'} is not strong enough",
            "seed_recommendation": "stabilize same-family reuse quality before promoting this prior into seed behavior",
        }
    if confidence < 0.7:
        return {
            "seed_ready": False,
            "seed_gate": "confidence",
            "seed_reason": f"confidence {confidence:.2f} is below the 0.70 seed threshold",
            "seed_recommendation": "add one more high-trust success path, ideally via manual ingest or workflow closure",
        }
    if sample_count < 2:
        return {
            "seed_ready": False,
            "seed_gate": "sample_count",
            "seed_reason": f"only {sample_count} sample is available for this family prior",
            "seed_recommendation": "record at least one more successful sample in this family before using it as seed",
        }
    if recent_success_count < 1:
        return {
            "seed_ready": False,
            "seed_gate": "recent_success",
            "seed_reason": "no recent successful sample is available for this family prior",
            "seed_recommendation": "refresh this family with a recent successful validation or workflow closure",
        }
    return {
        "seed_ready": True,
        "seed_gate": "ready",
        "seed_reason": (
            f"strong prior from {sample_count} samples, confidence {confidence:.2f}, "
            f"recent_success={recent_success_count}"
        ),
        "seed_recommendation": "reuse this prior as a seed fallback when live family trust is weak",
    }


def build_consolidation_summary(
    *,
    repo_root: str,
    project_scope: str,
    limit: int = 48,
    family_limit: int = 8,
) -> dict[str, Any]:
    sessions = load_recent_sessions(
        repo_root,
        project_scope=project_scope,
        exclude_task_id=None,
        limit=limit,
    )

    family_buckets: dict[str, list[SessionState]] = {}
    pattern_keys: set[tuple[str, str, str, str]] = set()
    total_patterns = 0
    suppressed_candidates = 0
    continuity_cleaned = 0
    artifacts_reviewed = 0
    recovery_samples_reviewed = 0

    strong_family_hits: set[str] = set()
    for session in sessions:
        family = _task_family(session)
        family_buckets.setdefault(family, []).append(session)
        if session.selected_family_scope == "same_task_family" or _instrumentation_status(session) == "strong_match":
            strong_family_hits.add(family)

    for session in sessions:
        family = _task_family(session)
        if session.selected_trust_signal == "broader_similarity" and family in strong_family_hits:
            suppressed_candidates += 1
        for pattern in session.collaboration_patterns:
            normalized_summary = " ".join((pattern.reuse_hint or pattern.summary or "").lower().split())
            pattern_keys.add((pattern.task_family or family, pattern.kind, pattern.role, normalized_summary))
            total_patterns += 1
        continuity = session.continuity_snapshot or {}
        if isinstance(continuity, dict):
            continuity_cleaned += _dedupe_count(list(continuity.get("prior_artifact_refs") or []))
            continuity_cleaned += _dedupe_count(list(continuity.get("prior_collaboration_patterns") or []))
            continuity_cleaned += _dedupe_count(list(continuity.get("prior_strategy_working_sets") or []))
            continuity_cleaned += _dedupe_count(list(continuity.get("prior_strategy_validations") or []))
        artifacts_reviewed += len(session.artifacts)
        if (
            (session.execution_packet and ("recovery" in session.execution_packet.current_stage or "rollback" in session.execution_packet.current_stage))
            or any(item.kind in {"timeout", "correction", "rollback"} for item in session.artifacts)
        ):
            recovery_samples_reviewed += 1

    family_rows: list[dict[str, Any]] = []
    for family, bucket in family_buckets.items():
        statuses = [_instrumentation_status(session) for session in bucket]
        strong_count = sum(1 for status in statuses if status == "strong_match")
        usable_count = sum(1 for status in statuses if status == "usable_match")
        weak_count = sum(1 for status in statuses if status == "weak_match")
        recent_success_count = _recent_success_count(bucket)
        source_counts = _source_counts(bucket)
        avg_source_weight = _average_source_weight(bucket)
        avg_hit_rate = round(
            sum((session.instrumentation_summary.routed_artifact_hit_rate if session.instrumentation_summary else 0.0) for session in bucket)
            / max(len(bucket), 1),
            3,
        )
        if strong_count == len(bucket) and bucket:
            status = "strong_family"
        elif strong_count + usable_count == len(bucket) and bucket:
            status = "stable_family"
        else:
            status = "mixed_family"
        row = {
                "task_family": family,
                "status": status,
                "session_count": len(bucket),
                "sample_count": len(bucket),
                "strong_match_count": strong_count,
                "usable_match_count": usable_count,
                "weak_match_count": weak_count,
                "recent_success_count": recent_success_count,
                **source_counts,
                "avg_artifact_hit_rate": avg_hit_rate,
                "confidence": _prior_confidence(
                    session_count=len(bucket),
                    strong_count=strong_count,
                    usable_count=usable_count,
                    recent_success_count=recent_success_count,
                    avg_hit_rate=avg_hit_rate,
                    avg_source_weight=avg_source_weight,
                ),
                "strategy_profiles": list(
                    dict.fromkeys(
                        session.selected_strategy_profile
                        for session in bucket
                        if session.selected_strategy_profile
                    )
                )[:4],
                "sample_tasks": [session.task_id for session in bucket[:4]],
                "dominant_strategy_profile": _dominant_value(
                    [session.selected_strategy_profile for session in bucket]
                ),
                "dominant_validation_style": _dominant_value(
                    [session.selected_validation_style for session in bucket]
                ),
                "dominant_validation_command": _dominant_value(
                    [session.validation_commands[0] for session in bucket if session.validation_commands]
                ),
                "dominant_role_sequence": list(
                    dict.fromkeys(
                        item
                        for session in bucket
                        for item in session.selected_role_sequence[:3]
                        if isinstance(item, str) and item.strip()
                    )
                )[:3],
                "dominant_working_set": _dominant_working_set(bucket),
                "family_doc_prior": _family_doc_prior(bucket),
                "family_reviewer_prior": _family_reviewer_prior(bucket),
            }
        row["doc_sample_count"] = int((row.get("family_doc_prior") or {}).get("sample_count") or 0)
        row["doc_seed_ready"] = bool((row.get("family_doc_prior") or {}).get("seed_ready"))
        row["reviewer_sample_count"] = int((row.get("family_reviewer_prior") or {}).get("sample_count") or 0)
        row["reviewer_seed_ready"] = bool((row.get("family_reviewer_prior") or {}).get("seed_ready"))
        row.update(describe_family_prior_seed(row))
        family_rows.append(row)
    family_rows.sort(
        key=lambda item: (
            {"strong_family": 2, "stable_family": 1, "mixed_family": 0}.get(str(item.get("status")), -1),
            int(item.get("session_count", 0)),
            float(item.get("avg_artifact_hit_rate", 0.0)),
        ),
        reverse=True,
    )
    family_rows = family_rows[:family_limit]

    return {
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_scope": project_scope,
        "sessions_reviewed": len(sessions),
        "families_reviewed": len(family_buckets),
        "patterns_merged": max(0, total_patterns - len(pattern_keys)),
        "patterns_suppressed": suppressed_candidates,
        "continuity_cleaned": continuity_cleaned,
        "artifacts_reviewed": artifacts_reviewed,
        "recovery_samples_reviewed": recovery_samples_reviewed,
        "recent_task_ids": [session.task_id for session in sessions[:8]],
        "family_rows": family_rows,
        "explanation": (
            "Project-scoped consolidation reviewed recent sessions, merged duplicate family patterns, "
            "and identified noisy broader-similarity patterns without rewriting source sessions."
            if sessions
            else "No recent sessions were available for consolidation."
        ),
    }
