from __future__ import annotations

import os
from typing import Any, Callable

from .bootstrap import build_bootstrap_snapshot
from .consolidation import describe_family_prior_seed
from .consolidation_state import load_consolidation_summary
from .dream_state import load_dream_promotions
from .execution_packet import StrategySummary
from .policies import (
    _derive_task_family,
    normalize_session_memory,
    refresh_delegation_packets,
    seed_continuity_snapshot,
    seed_shared_memory,
    select_collaboration_strategy,
)
from .session import ArtifactReference, SessionState, load_recent_sessions, load_session, save_artifact_payload
from .tracing import normalize_target_paths


def _normalize_validation_commands(commands: list[str], repo_root: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in commands:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized[:8]


def _reorder_artifacts(
    artifacts: list[ArtifactReference],
    *,
    preferred_paths: list[str],
    limit: int,
) -> list[ArtifactReference]:
    if not artifacts:
        return []
    if not preferred_paths:
        return artifacts[:limit]
    ordered: list[ArtifactReference] = []
    seen: set[str] = set()
    artifact_by_path = {item.path: item for item in artifacts}
    for path in preferred_paths:
        artifact = artifact_by_path.get(path)
        if artifact and artifact.path not in seen:
            ordered.append(artifact)
            seen.add(artifact.path)
    for artifact in artifacts:
        if artifact.path in seen:
            continue
        ordered.append(artifact)
        seen.add(artifact.path)
    return ordered[:limit]


def _reorder_delegation_packets(
    packets: list[Any],
    *,
    role_sequence: list[str],
) -> list[Any]:
    if not packets or not role_sequence:
        return packets
    ordered: list[Any] = []
    seen_roles: set[str] = set()
    packet_by_role = {packet.role: packet for packet in packets if getattr(packet, "role", None)}
    for role in role_sequence:
        packet = packet_by_role.get(role)
        if packet is None or role in seen_roles:
            continue
        ordered.append(packet)
        seen_roles.add(role)
    for packet in packets:
        if getattr(packet, "role", None) in seen_roles:
            continue
        ordered.append(packet)
    return ordered


def _load_family_prior(repo_root: str, project_scope: str, task_family: str) -> dict[str, Any]:
    if not task_family:
        return {}
    dream_payload = load_dream_promotions(
        repo_root=repo_root,
        project_scope=project_scope,
    )
    promotions = dream_payload.get("promotions", [])
    if isinstance(promotions, list):
        matching = [
            item
            for item in promotions
            if (
                isinstance(item, dict)
                and item.get("task_family") == task_family
                and str(item.get("promotion_status") or "") == "seed_ready"
            )
        ]
        matching.sort(
            key=lambda item: (
                float(item.get("confidence") or 0.0),
                int(item.get("sample_count") or 0),
                int(item.get("recent_success_count") or 0),
            ),
            reverse=True,
        )
        if matching:
            promoted = matching[0]
            family_doc_prior = {}
            dominant_doc_input = str(promoted.get("dominant_doc_input") or "").strip()
            dominant_source_doc_id = str(promoted.get("dominant_source_doc_id") or "").strip()
            if dominant_doc_input or dominant_source_doc_id:
                family_doc_prior = {
                    "dominant_doc_input": dominant_doc_input,
                    "dominant_source_doc_id": dominant_source_doc_id,
                    "dominant_action": str(promoted.get("dominant_doc_action") or "").strip(),
                    "dominant_selected_tool": str(promoted.get("dominant_selected_tool") or "").strip(),
                    "dominant_event_source": str(promoted.get("dominant_event_source") or "").strip(),
                    "latest_recorded_at": str(promoted.get("latest_recorded_at") or "").strip(),
                    "sample_count": int(promoted.get("doc_sample_count") or 0),
                    "editor_sync_count": int(promoted.get("editor_sync_count") or 0),
                    "seed_ready": True,
                    "seed_reason": str(promoted.get("promotion_reason") or "AutoDream promoted this doc prior to seed-ready."),
                }
            family_reviewer_prior = {}
            dominant_reviewer_standard = str(promoted.get("dominant_reviewer_standard") or "").strip()
            if dominant_reviewer_standard:
                family_reviewer_prior = {
                    "dominant_standard": dominant_reviewer_standard,
                    "dominant_required_outputs": list(promoted.get("dominant_reviewer_outputs") or []),
                    "dominant_acceptance_checks": list(promoted.get("dominant_reviewer_checks") or []),
                    "dominant_pack_source": str(promoted.get("dominant_reviewer_pack_source") or "").strip(),
                    "dominant_selected_tool": str(promoted.get("dominant_reviewer_selected_tool") or "").strip(),
                    "dominant_resume_anchor": str(promoted.get("dominant_reviewer_resume_anchor") or "").strip(),
                    "sample_count": int(promoted.get("reviewer_sample_count") or 0),
                    "ready_required_count": int(promoted.get("reviewer_ready_count") or 0),
                    "rollback_required_count": int(promoted.get("reviewer_rollback_count") or 0),
                    "seed_ready": True,
                    "seed_reason": str(
                        promoted.get("promotion_reason") or "AutoDream promoted this reviewer prior to seed-ready."
                    ),
                }
            return {
                "task_family": task_family,
                "status": "strong_family",
                "confidence": float(promoted.get("confidence") or 0.0),
                "sample_count": int(promoted.get("sample_count") or 0),
                "recent_success_count": int(promoted.get("recent_success_count") or 0),
                "dominant_strategy_profile": str(promoted.get("strategy_profile") or ""),
                "dominant_validation_style": str(promoted.get("validation_style") or ""),
                "dominant_validation_command": str(promoted.get("dominant_validation_command") or ""),
                "dominant_working_set": list(promoted.get("dominant_working_set") or [])[:6],
                "seed_ready": True,
                "seed_gate": "dream_seed_ready",
                "seed_reason": str(promoted.get("promotion_reason") or "AutoDream promoted this prior to seed-ready."),
                "seed_recommendation": "reuse this promoted prior as the default narrow seed for this family",
                "prior_source": "dream_promotion",
                "promotion_status": "seed_ready",
                "verification_summary": str(promoted.get("verification_summary") or ""),
                "family_doc_prior": family_doc_prior,
                "family_reviewer_prior": family_reviewer_prior,
            }
    summary = load_consolidation_summary(
        repo_root=repo_root,
        project_scope=project_scope,
    )
    family_rows = summary.get("family_rows", [])
    if not isinstance(family_rows, list):
        return {}
    for row in family_rows:
        if isinstance(row, dict) and row.get("task_family") == task_family:
            annotated = dict(row)
            annotated.update(describe_family_prior_seed(annotated))
            return annotated
    return {}


def _family_prior_is_strong(row: dict[str, Any]) -> bool:
    if row.get("seed_ready") is True:
        return True
    if str(row.get("promotion_status") or "") == "seed_ready":
        return True
    return bool(describe_family_prior_seed(row).get("seed_ready"))


def _doc_result_key(action: str) -> str:
    return {
        "compile": "compile_result",
        "run": "run_result",
        "execute": "execute_result",
        "runtime_handoff": "runtime_handoff",
        "handoff_store": "handoff_store_request",
        "publish": "publish_result",
        "recover": "recover_result",
        "resume": "resume_result",
    }.get(action, "")


def _doc_source_info(result: dict[str, Any]) -> tuple[str, str]:
    source_doc_id = str(
        result.get("source_doc_id")
        or (((result.get("artifacts") or {}) if isinstance(result.get("artifacts"), dict) else {}).get("plan") or {}).get("doc", {}).get("id")
        or ""
    ).strip()
    source_doc_version = str(
        result.get("source_doc_version")
        or (((result.get("artifacts") or {}) if isinstance(result.get("artifacts"), dict) else {}).get("plan") or {}).get("doc", {}).get("version")
        or ""
    ).strip()
    return source_doc_id, source_doc_version


def _doc_handoff_fields(action: str, result: dict[str, Any]) -> tuple[str, str]:
    if action == "publish":
        request = result.get("request") or {}
        request = request if isinstance(request, dict) else {}
        response = result.get("response") or {}
        response = response if isinstance(response, dict) else {}
        anchor = str(response.get("handoff_anchor") or request.get("anchor") or "").strip()
        handoff_kind = str(response.get("handoff_kind") or request.get("handoff_kind") or "").strip()
        return anchor, handoff_kind
    if action == "recover":
        request = result.get("recover_request") or {}
        request = request if isinstance(request, dict) else {}
        response = result.get("recover_response") or {}
        response = response if isinstance(response, dict) else {}
        data = response.get("data") or {}
        data = data if isinstance(data, dict) else {}
        anchor = str(data.get("anchor") or request.get("anchor") or "").strip()
        handoff_kind = str(data.get("handoff_kind") or request.get("handoff_kind") or "").strip()
        return anchor, handoff_kind
    if action == "resume":
        recover_result = result.get("recover_result") or {}
        recover_result = recover_result if isinstance(recover_result, dict) else {}
        recover_request = recover_result.get("recover_request") or {}
        recover_request = recover_request if isinstance(recover_request, dict) else {}
        recover_response = recover_result.get("recover_response") or {}
        recover_response = recover_response if isinstance(recover_response, dict) else {}
        recover_data = recover_response.get("data") or {}
        recover_data = recover_data if isinstance(recover_data, dict) else {}
        anchor = str(recover_data.get("anchor") or recover_request.get("anchor") or "").strip()
        handoff_kind = str(recover_data.get("handoff_kind") or recover_request.get("handoff_kind") or "").strip()
        return anchor, handoff_kind
    return "", ""


def _dedupe_strings(values: list[str], *, limit: int = 8) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped[:limit]


class SessionService:
    def __init__(
        self,
        *,
        repo_root: str,
        project_identity: str,
        project_scope: str,
        save_session_fn: Callable[[SessionState], Any],
    ) -> None:
        self._repo_root = repo_root
        self._project_identity = project_identity
        self._project_scope = project_scope
        self._save_session = save_session_fn

    def normalize_target_files(self, target_files: list[str]) -> list[str]:
        return normalize_target_paths(target_files, repo_root=self._repo_root, limit=12)

    def normalize_validation_commands(self, validation_commands: list[str]) -> list[str]:
        return _normalize_validation_commands(validation_commands, self._repo_root)

    def load_session(self, *, task_id: str) -> SessionState | None:
        return load_session(self._repo_root, task_id, project_scope=self._project_scope)

    def bootstrap_snapshot(self) -> dict[str, Any]:
        return build_bootstrap_snapshot(
            repo_root=self._repo_root,
            project_identity=self._project_identity,
            project_scope=self._project_scope,
        )

    def record_doc_result(
        self,
        *,
        session: SessionState,
        action: str,
        doc_input: str,
        payload: dict[str, Any],
    ) -> list[ArtifactReference]:
        result_key = _doc_result_key(action)
        result = payload.get(result_key) if result_key else {}
        result = result if isinstance(result, dict) else {}
        status = str(payload.get("status") or result.get("status") or "ok").strip() or "ok"
        source_doc_id, source_doc_version = _doc_source_info(result)
        handoff_anchor, handoff_kind = _doc_handoff_fields(action, result)
        basename = os.path.basename(doc_input.strip()) or doc_input.strip() or "workflow.aionis.md"
        event_source = str(payload.get("event_source") or "").strip()
        event_origin = str(payload.get("event_origin") or "").strip()
        recorded_at = str(payload.get("recorded_at") or "").strip()

        created: list[ArtifactReference] = []

        artifact_name = f"doc-{action}.json"
        artifact_kind = f"doc_{action}_result"
        artifact_summary = f"Aionisdoc {action} {status} for {basename}"
        artifact_payload = {
            "task_id": session.task_id,
            "project_scope": session.project_scope,
            "kind": artifact_kind,
            "role": "orchestrator",
            "summary": artifact_summary,
            "doc_action": action,
            "doc_input": doc_input,
            "status": status,
            "source_doc_id": source_doc_id or None,
            "source_doc_version": source_doc_version or None,
            "handoff_anchor": handoff_anchor or None,
            "handoff_kind": handoff_kind or None,
            "event_source": event_source or None,
            "event_origin": event_origin or None,
            "recorded_at": recorded_at or None,
            "result": result,
        }
        artifact_path = save_artifact_payload(
            repo_root=session.repo_root,
            project_scope=session.project_scope,
            task_id=session.task_id,
            artifact_name=artifact_name,
            payload=artifact_payload,
        )
        created.append(
            ArtifactReference(
                artifact_id=f"{session.task_id}:doc:{action}",
                kind=artifact_kind,
                role="orchestrator",
                summary=artifact_summary,
                path=artifact_path,
                metadata={
                    "doc_action": action,
                    "status": status,
                    "doc_input": doc_input,
                    "source_doc_id": source_doc_id,
                    "source_doc_version": source_doc_version,
                },
            )
        )

        if handoff_anchor or handoff_kind:
            handoff_payload = {
                "task_id": session.task_id,
                "project_scope": session.project_scope,
                "kind": "doc_runtime_handoff",
                "role": "orchestrator",
                "summary": f"Aionisdoc {action} handoff for {basename}",
                "doc_action": action,
                "doc_input": doc_input,
                "anchor": handoff_anchor or None,
                "handoff_kind": handoff_kind or None,
                "source_doc_id": source_doc_id or None,
                "source_doc_version": source_doc_version or None,
                "event_source": event_source or None,
                "event_origin": event_origin or None,
                "recorded_at": recorded_at or None,
            }
            handoff_path = save_artifact_payload(
                repo_root=session.repo_root,
                project_scope=session.project_scope,
                task_id=session.task_id,
                artifact_name=f"doc-runtime-handoff-{action}.json",
                payload=handoff_payload,
            )
            created.append(
                ArtifactReference(
                    artifact_id=f"{session.task_id}:doc-handoff:{action}",
                    kind="doc_runtime_handoff",
                    role="orchestrator",
                    summary=handoff_payload["summary"],
                    path=handoff_path,
                    metadata={
                        "doc_action": action,
                        "anchor": handoff_anchor,
                        "handoff_kind": handoff_kind,
                        "source_doc_id": source_doc_id,
                        "source_doc_version": source_doc_version,
                    },
                )
            )

        existing = [
            artifact
            for artifact in session.artifacts
            if artifact.artifact_id not in {item.artifact_id for item in created}
        ]
        session.artifacts = [*created, *existing]

        continuity = dict(session.continuity_snapshot or {})
        doc_workflow = continuity.get("doc_workflow")
        doc_workflow = dict(doc_workflow) if isinstance(doc_workflow, dict) else {}
        event = {
            "action": action,
            "status": status,
            "doc_input": doc_input,
            "source_doc_id": source_doc_id or None,
            "source_doc_version": source_doc_version or None,
            "handoff_anchor": handoff_anchor or None,
            "handoff_kind": handoff_kind or None,
            "artifact_refs": [item.path for item in created],
            "selected_tool": (
                ((result.get("resume_summary") or {}) if isinstance(result.get("resume_summary"), dict) else {}).get("selected_tool")
                or None
            ),
            "event_source": event_source or None,
            "event_origin": event_origin or None,
            "recorded_at": recorded_at or None,
        }
        history = [event]
        for item in doc_workflow.get("history") or []:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("action") or "") == action
                and str(item.get("doc_input") or "") == doc_input
            ):
                continue
            history.append(item)
        doc_workflow.update(
            {
                "latest_action": action,
                "status": status,
                "doc_input": doc_input,
                "source_doc_id": source_doc_id or doc_workflow.get("source_doc_id"),
                "source_doc_version": source_doc_version or doc_workflow.get("source_doc_version"),
                "handoff_anchor": handoff_anchor or doc_workflow.get("handoff_anchor"),
                "handoff_kind": handoff_kind or doc_workflow.get("handoff_kind"),
                "selected_tool": event.get("selected_tool") or doc_workflow.get("selected_tool"),
                "event_source": event_source or doc_workflow.get("event_source"),
                "event_origin": event_origin or doc_workflow.get("event_origin"),
                "recorded_at": recorded_at or doc_workflow.get("recorded_at"),
                "artifact_refs": _dedupe_strings(
                    [*(item.path for item in created), *(doc_workflow.get("artifact_refs") or [])]
                ),
                "history": history[:6],
            }
        )
        continuity["doc_workflow"] = doc_workflow
        continuity["preferred_artifact_refs"] = _dedupe_strings(
            [*(item.path for item in created), *(continuity.get("preferred_artifact_refs") or [])],
            limit=6,
        )
        session.continuity_snapshot = continuity

        insight_line = f"Doc workflow {action}: {status} for {basename}"
        if insight_line not in session.promoted_insights:
            session.promoted_insights.append(insight_line)
        if handoff_anchor:
            anchor_line = f"Doc handoff anchor: {handoff_anchor}"
            if anchor_line not in session.promoted_insights:
                session.promoted_insights.append(anchor_line)
        return created

    def record_doc_event(
        self,
        *,
        session: SessionState,
        event: dict[str, Any],
    ) -> list[ArtifactReference]:
        if not isinstance(event, dict):
            raise ValueError("doc event must be a JSON object")
        version = str(event.get("event_version") or "").strip()
        if version != "aionisdoc_workbench_event_v1":
            raise ValueError("unsupported doc event version")
        action = str(event.get("doc_action") or "").strip()
        if action not in {"compile", "run", "publish", "recover", "resume"}:
            raise ValueError("unsupported doc event action")
        doc_input = str(event.get("doc_input") or "").strip()
        if not doc_input:
            raise ValueError("doc event missing doc_input")
        payload = event.get("payload")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("doc event missing payload")
        normalized = dict(payload)
        normalized.setdefault("shell_view", f"doc_{action}")
        normalized.setdefault("doc_action", action)
        normalized.setdefault("doc_input", doc_input)
        normalized.setdefault("status", str(event.get("status") or normalized.get("status") or "ok"))
        normalized["event_version"] = version
        normalized["event_source"] = str(event.get("event_source") or "").strip()
        normalized["event_origin"] = "editor_extension"
        normalized["recorded_at"] = str(event.get("occurred_at") or "").strip()
        normalized["recording_mode"] = "editor_event"
        return self.record_doc_result(
            session=session,
            action=action,
            doc_input=doc_input,
            payload=normalized,
        )

    def initial_session(
        self,
        *,
        task_id: str,
        task: str,
        target_files: list[str],
        validation_commands: list[str],
        apply_strategy: bool = True,
        seed_priors: bool = True,
    ) -> SessionState:
        bootstrap = self.bootstrap_snapshot()
        bootstrap_target_files = list(bootstrap.get("bootstrap_working_set") or [])
        bootstrap_validation_commands = list(bootstrap.get("bootstrap_validation_commands") or [])
        initial_task_family = _derive_task_family(
            task_text=task,
            target_files=target_files or [],
            validation_summary="",
        )
        initial_family_prior = _load_family_prior(
            self._repo_root,
            self._project_scope,
            initial_task_family,
        )
        initial_prior_validation = str(initial_family_prior.get("dominant_validation_command") or "").strip()
        session = SessionState(
            task_id=task_id,
            goal=task,
            repo_root=self._repo_root,
            project_identity=self._project_identity,
            project_scope=self._project_scope,
            target_files=self.normalize_target_files(target_files or bootstrap_target_files),
            validation_commands=self.normalize_validation_commands(
                validation_commands
                or ([initial_prior_validation] if initial_prior_validation else [])
                or bootstrap_validation_commands
            ),
        )
        session.continuity_snapshot = {"bootstrap": bootstrap}
        prior_sessions = (
            load_recent_sessions(
                self._repo_root,
                project_scope=self._project_scope,
                exclude_task_id=task_id,
                limit=24,
            )
            if seed_priors
            else []
        )
        for prior in prior_sessions:
            prior.target_files = normalize_target_paths(prior.target_files, repo_root=self._repo_root, limit=12)
            prior.validation_commands = self.normalize_validation_commands(prior.validation_commands)
        strategy = None
        if apply_strategy:
            strategy = select_collaboration_strategy(
                prior_sessions=prior_sessions,
                target_files=session.target_files,
                validation_commands=session.validation_commands,
                task_text=task,
            )
            session.target_files = self.normalize_target_files(strategy.target_files)
            session.validation_commands = self.normalize_validation_commands(strategy.validation_commands)
            session.selected_strategy_profile = strategy.strategy_profile
            session.selected_validation_style = strategy.validation_style
            session.selected_artifact_budget = strategy.artifact_limit
            session.selected_memory_source_limit = strategy.memory_source_limit
            session.selected_trust_signal = strategy.trust_signal
            session.selected_task_family = strategy.task_family
            session.selected_family_scope = strategy.family_scope
            session.selected_family_candidate_count = strategy.family_candidate_count
            session.selected_pattern_summaries = strategy.selected_pattern_summaries[:4]
            session.strategy_summary = StrategySummary(
                trust_signal=strategy.trust_signal,
                strategy_profile=strategy.strategy_profile,
                validation_style=strategy.validation_style,
                task_family=strategy.task_family,
                family_scope=strategy.family_scope,
                family_candidate_count=strategy.family_candidate_count,
                selected_working_set=self.normalize_target_files(strategy.selected_working_set or session.target_files)[:8],
                selected_validation_paths=self.normalize_validation_commands(strategy.validation_commands)[:4],
                selected_role_sequence=strategy.role_sequence[:3],
                preferred_artifact_refs=strategy.preferred_artifacts[: strategy.artifact_limit],
                selected_pattern_summaries=strategy.selected_pattern_summaries[:4],
                artifact_budget=strategy.artifact_limit,
                memory_source_limit=strategy.memory_source_limit,
                explanation="; ".join(strategy.memory_lines[:3])[:400],
            )
            family_prior = _load_family_prior(
                self._repo_root,
                self._project_scope,
                strategy.task_family or initial_task_family,
            )
            if family_prior and _family_prior_is_strong(family_prior):
                prior_strategy_profile = str(family_prior.get("dominant_strategy_profile") or "").strip()
                prior_validation_style = str(family_prior.get("dominant_validation_style") or "").strip()
                prior_working_set = [
                    value
                    for value in (family_prior.get("dominant_working_set") or [])[:4]
                    if isinstance(value, str) and value.strip()
                ]
                prior_validation_command = str(family_prior.get("dominant_validation_command") or "").strip()
                if prior_strategy_profile:
                    session.selected_strategy_profile = prior_strategy_profile
                if prior_validation_style:
                    session.selected_validation_style = prior_validation_style
                if not target_files and prior_working_set:
                    session.target_files = self.normalize_target_files([*prior_working_set, *session.target_files])
                if not validation_commands and prior_validation_command:
                    session.validation_commands = self.normalize_validation_commands(
                        [prior_validation_command, *session.validation_commands]
                    )
            if session.strategy_summary:
                session.strategy_summary.strategy_profile = session.selected_strategy_profile
                session.strategy_summary.validation_style = session.selected_validation_style
                session.strategy_summary.selected_working_set = self.normalize_target_files(
                    strategy.selected_working_set or session.target_files
                )[:8]
                session.strategy_summary.selected_validation_paths = self.normalize_validation_commands(
                    session.validation_commands
                )[:4]
        if seed_priors:
            seeded_artifacts: list[ArtifactReference] = []
            seen_artifacts: set[tuple[str, str, str]] = set()
            for prior in prior_sessions:
                for artifact in prior.artifacts[:2]:
                    key = (artifact.role, artifact.kind, artifact.path)
                    if key in seen_artifacts:
                        continue
                    seen_artifacts.add(key)
                    seeded_artifacts.append(artifact)
            if seeded_artifacts:
                artifact_limit = strategy.artifact_limit if strategy else 6
                preferred_paths = strategy.preferred_artifacts if strategy else []
                session.artifacts = _reorder_artifacts(
                    seeded_artifacts,
                    preferred_paths=preferred_paths,
                    limit=artifact_limit,
                )
            refresh_delegation_packets(session)
            session.delegation_packets = _reorder_delegation_packets(
                session.delegation_packets,
                role_sequence=strategy.role_sequence if strategy else [],
            )
            if strategy and strategy.role_sequence:
                session.selected_role_sequence = strategy.role_sequence[:3]
        session.continuity_snapshot = seed_continuity_snapshot(
            session=session,
            prior_sessions=prior_sessions,
        )
        seed_shared_memory(session=session, prior_sessions=prior_sessions)
        normalize_session_memory(session)
        self._save_session(session)
        return session
