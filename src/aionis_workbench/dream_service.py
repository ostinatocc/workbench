from __future__ import annotations

from collections import defaultdict
from collections import Counter
from datetime import datetime, timezone

from .dream_models import CandidateVerification, DreamSample, PromotedPrior, StrategyCandidate
from .dream_state import save_dream_candidates, save_dream_promotions
from .doc_learning import build_doc_learning_record
from .reviewer_contracts import resolve_reviewer_evidence
from .session import SessionState, forgetting_signal_summary, load_recent_sessions


def _instrumentation_status(session: SessionState) -> str:
    instrumentation = session.instrumentation_summary
    if not instrumentation:
        return "unknown"
    if (
        instrumentation.family_hit
        and instrumentation.selected_pattern_hit_count > 0
        and instrumentation.routed_artifact_hit_rate >= 0.75
    ):
        return "strong_match"
    if instrumentation.family_hit or instrumentation.selected_pattern_hit_count > 0:
        return "usable_match"
    return "weak_match"


def _sample_source_weight(sample: DreamSample) -> float:
    if sample.source == "manual_ingest":
        return 1.0
    if sample.source == "workflow_closure":
        return 0.95
    if sample.source in {"run", "resume"}:
        return 0.85
    if sample.source == "validate":
        return 0.7 if sample.observed_changed_files else 0.65
    return 0.5


def _candidate_id(*parts: str) -> str:
    cleaned: list[str] = []
    for part in parts:
        piece = "".join(char if char.isalnum() else "-" for char in part.strip().lower())
        piece = "-".join(token for token in piece.split("-") if token)
        if piece:
            cleaned.append(piece)
    return "::".join(cleaned) if cleaned else "candidate::unknown"


def _confidence_for_candidate(candidate: StrategyCandidate) -> float:
    sample_factor = min(candidate.sample_count / 3.0, 1.0)
    success_ratio = (
        candidate.recent_success_count / candidate.sample_count
        if candidate.sample_count > 0
        else 0.0
    )
    score = (
        0.35 * success_ratio
        + 0.25 * max(min(candidate.avg_artifact_hit_rate, 1.0), 0.0)
        + 0.2 * max(min(candidate.source_weight, 1.0), 0.0)
        + 0.2 * sample_factor
    )
    return round(max(min(score, 1.0), 0.0), 3)


def _working_set_match_ratio(candidate: StrategyCandidate, sample: DreamSample) -> float:
    candidate_set = {item for item in candidate.dominant_working_set if item}
    sample_set = {item for item in sample.working_set if item}
    if not candidate_set:
        return 0.0
    return len(candidate_set & sample_set) / len(candidate_set)


def _dominant_text(bucket: list[DreamSample], field: str) -> str:
    counter = Counter(
        str(getattr(sample, field, "") or "").strip()
        for sample in bucket
        if str(getattr(sample, field, "") or "").strip()
    )
    return counter.most_common(1)[0][0] if counter else ""


def _reviewer_sample_fields(session: SessionState) -> dict[str, object]:
    return resolve_reviewer_evidence(
        packet=session.execution_packet,
        continuity_pack=session.continuity_review_pack,
        evolution_pack=session.evolution_review_pack,
    )


class DreamService:
    def __init__(self, *, repo_root: str, project_scope: str) -> None:
        self._repo_root = repo_root
        self._project_scope = project_scope

    def _sample_from_session(self, session: SessionState) -> DreamSample | None:
        continuity = session.continuity_snapshot or {}
        learning = continuity.get("learning") if isinstance(continuity, dict) else {}
        if not isinstance(learning, dict):
            return None
        doc_learning = build_doc_learning_record(session) or {}
        task_family = str(learning.get("task_family") or session.selected_task_family or "").strip()
        strategy_profile = str(learning.get("strategy_profile") or session.selected_strategy_profile or "").strip()
        validation_style = str(session.selected_validation_style or "").strip()
        validation_command = str(
            learning.get("validation_command")
            or (session.last_validation_result or {}).get("command")
            or ""
        ).strip()
        working_set = [
            item
            for item in (learning.get("working_set") or session.target_files)
            if isinstance(item, str) and item.strip()
        ][:6]
        passive = continuity.get("passive_observation") if isinstance(continuity, dict) else {}
        observed_changed_files: list[str] = []
        if isinstance(passive, dict):
            changed_files = passive.get("changed_files")
            if isinstance(changed_files, list):
                observed_changed_files = [item for item in changed_files if isinstance(item, str) and item.strip()][:6]
        forgetting = forgetting_signal_summary(
            session,
            linked_values=[validation_command, *working_set],
        )
        instrumentation = session.instrumentation_summary
        reviewer = _reviewer_sample_fields(session)
        return DreamSample(
            task_id=session.task_id,
            project_identity=session.project_identity,
            project_scope=session.project_scope,
            task_family=task_family,
            source=str(learning.get("source") or "").strip(),
            strategy_profile=strategy_profile,
            validation_style=str(learning.get("validation_style") or validation_style).strip(),
            validation_command=validation_command,
            working_set=working_set,
            observed_changed_files=observed_changed_files,
            artifact_refs=[item.path for item in session.artifacts[:4]],
            doc_input=str(doc_learning.get("doc_input") or "").strip(),
            source_doc_id=str(doc_learning.get("source_doc_id") or "").strip(),
            doc_action=str(doc_learning.get("latest_action") or "").strip(),
            handoff_anchor=str(doc_learning.get("handoff_anchor") or "").strip(),
            selected_tool=str(doc_learning.get("selected_tool") or "").strip(),
            event_source=str(doc_learning.get("event_source") or "").strip(),
            recorded_at=str(doc_learning.get("recorded_at") or "").strip(),
            reviewer_standard=str(reviewer.get("reviewer_standard") or "").strip(),
            reviewer_required_outputs=list(reviewer.get("reviewer_required_outputs") or []),
            reviewer_acceptance_checks=list(reviewer.get("reviewer_acceptance_checks") or []),
            reviewer_pack_source=str(reviewer.get("reviewer_pack_source") or "").strip(),
            reviewer_selected_tool=str(reviewer.get("reviewer_selected_tool") or "").strip(),
            reviewer_resume_anchor=str(reviewer.get("reviewer_resume_anchor") or "").strip(),
            reviewer_ready_required=reviewer.get("reviewer_ready_required") is True,
            reviewer_rollback_required=reviewer.get("reviewer_rollback_required") is True,
            instrumentation_status=_instrumentation_status(session),
            artifact_hit_rate=(
                float(instrumentation.routed_artifact_hit_rate) if instrumentation is not None else 0.0
            ),
            pattern_hit_count=(
                int(instrumentation.selected_pattern_hit_count) if instrumentation is not None else 0
            ),
            suppressed_forgetting_count=int(forgetting.get("suppressed_count") or 0),
            evicted_forgetting_count=int(forgetting.get("evicted_count") or 0),
            stale_guidance_count=int(forgetting.get("linked_stale_count") or 0),
        )

    def extract_samples(self, *, limit: int = 48) -> list[DreamSample]:
        recent = load_recent_sessions(
            self._repo_root,
            project_scope=self._project_scope,
            exclude_task_id=None,
            limit=limit,
        )
        samples: list[DreamSample] = []
        for session in recent:
            sample = self._sample_from_session(session)
            if sample is None:
                continue
            if not sample.task_family and not sample.strategy_profile:
                continue
            samples.append(sample)
        return samples

    def distill_candidates(self, samples: list[DreamSample]) -> list[StrategyCandidate]:
        grouped: dict[tuple[str, str, str, str], list[DreamSample]] = defaultdict(list)
        for sample in samples:
            key = (
                sample.task_family,
                sample.strategy_profile,
                sample.validation_style,
                sample.validation_command,
                sample.reviewer_standard,
                tuple(sample.reviewer_required_outputs),
                tuple(sample.reviewer_acceptance_checks),
                sample.reviewer_ready_required,
                sample.reviewer_rollback_required,
            )
            grouped[key].append(sample)

        candidates: list[StrategyCandidate] = []
        for (
            task_family,
            strategy_profile,
            validation_style,
            validation_command,
            _reviewer_standard,
            _reviewer_outputs,
            _reviewer_checks,
            _reviewer_ready_required,
            _reviewer_rollback_required,
        ), bucket in grouped.items():
            working_set: list[str] = []
            supporting_task_ids: list[str] = []
            for sample in bucket:
                for item in sample.working_set:
                    if item not in working_set:
                        working_set.append(item)
                if sample.task_id not in supporting_task_ids:
                    supporting_task_ids.append(sample.task_id)
            avg_artifact_hit_rate = round(
                sum(sample.artifact_hit_rate for sample in bucket) / len(bucket),
                3,
            )
            avg_pattern_hit_count = round(
                sum(sample.pattern_hit_count for sample in bucket) / len(bucket),
                2,
            )
            source_weight = round(
                sum(_sample_source_weight(sample) for sample in bucket) / len(bucket),
                3,
            )
            suppressed_forgetting_count = sum(sample.suppressed_forgetting_count for sample in bucket)
            evicted_forgetting_count = sum(sample.evicted_forgetting_count for sample in bucket)
            stale_guidance_count = sum(sample.stale_guidance_count for sample in bucket)
            dominant_doc_input = _dominant_text(bucket, "doc_input")
            dominant_source_doc_id = _dominant_text(bucket, "source_doc_id")
            dominant_doc_action = _dominant_text(bucket, "doc_action")
            dominant_selected_tool = _dominant_text(bucket, "selected_tool")
            dominant_event_source = _dominant_text(bucket, "event_source")
            dominant_reviewer_standard = _dominant_text(bucket, "reviewer_standard")
            dominant_reviewer_pack_source = _dominant_text(bucket, "reviewer_pack_source")
            dominant_reviewer_selected_tool = _dominant_text(bucket, "reviewer_selected_tool")
            dominant_reviewer_resume_anchor = _dominant_text(bucket, "reviewer_resume_anchor")
            latest_recorded_at = max(
                (str(sample.recorded_at or "").strip() for sample in bucket if str(sample.recorded_at or "").strip()),
                default="",
            )
            doc_sample_count = sum(1 for sample in bucket if sample.doc_input or sample.source_doc_id)
            editor_sync_count = sum(1 for sample in bucket if sample.event_source)
            reviewer_outputs = Counter(
                "|".join(item for item in sample.reviewer_required_outputs if item)
                for sample in bucket
                if sample.reviewer_required_outputs
            )
            reviewer_checks = Counter(
                " && ".join(item for item in sample.reviewer_acceptance_checks if item)
                for sample in bucket
                if sample.reviewer_acceptance_checks
            )
            dominant_reviewer_outputs = [
                item for item in (reviewer_outputs.most_common(1)[0][0].split("|") if reviewer_outputs else []) if item
            ]
            dominant_reviewer_checks = [
                item for item in (reviewer_checks.most_common(1)[0][0].split(" && ") if reviewer_checks else []) if item
            ]
            reviewer_sample_count = sum(1 for sample in bucket if sample.reviewer_standard)
            reviewer_ready_count = sum(1 for sample in bucket if sample.reviewer_ready_required)
            reviewer_rollback_count = sum(1 for sample in bucket if sample.reviewer_rollback_required)
            candidates.append(
                StrategyCandidate(
                    candidate_id=_candidate_id(task_family, strategy_profile, validation_style, validation_command),
                    task_family=task_family,
                    strategy_profile=strategy_profile,
                    validation_style=validation_style,
                    dominant_validation_command=validation_command,
                    dominant_working_set=working_set[:6],
                    dominant_doc_input=dominant_doc_input,
                    dominant_source_doc_id=dominant_source_doc_id,
                    dominant_doc_action=dominant_doc_action,
                    dominant_selected_tool=dominant_selected_tool,
                    dominant_event_source=dominant_event_source,
                    latest_recorded_at=latest_recorded_at,
                    doc_sample_count=doc_sample_count,
                    editor_sync_count=editor_sync_count,
                    dominant_reviewer_standard=dominant_reviewer_standard,
                    dominant_reviewer_outputs=dominant_reviewer_outputs,
                    dominant_reviewer_checks=dominant_reviewer_checks,
                    dominant_reviewer_pack_source=dominant_reviewer_pack_source,
                    dominant_reviewer_selected_tool=dominant_reviewer_selected_tool,
                    dominant_reviewer_resume_anchor=dominant_reviewer_resume_anchor,
                    reviewer_sample_count=reviewer_sample_count,
                    reviewer_ready_count=reviewer_ready_count,
                    reviewer_rollback_count=reviewer_rollback_count,
                    supporting_task_ids=supporting_task_ids,
                    sample_count=len(bucket),
                    recent_success_count=len(bucket),
                    avg_artifact_hit_rate=avg_artifact_hit_rate,
                    avg_pattern_hit_count=avg_pattern_hit_count,
                    source_weight=source_weight,
                    suppressed_forgetting_count=suppressed_forgetting_count,
                    evicted_forgetting_count=evicted_forgetting_count,
                    stale_guidance_count=stale_guidance_count,
                )
            )
        candidates.sort(
            key=lambda item: (
                item.sample_count,
                item.recent_success_count,
                item.avg_artifact_hit_rate,
                item.avg_pattern_hit_count,
            ),
            reverse=True,
        )
        return candidates

    def verify_candidate(
        self,
        candidate: StrategyCandidate,
        heldout_samples: list[DreamSample],
    ) -> CandidateVerification:
        relevant = [
            sample
            for sample in heldout_samples
            if sample.task_family == candidate.task_family and sample.task_id not in candidate.supporting_task_ids
        ]
        heldout_count = len(relevant)
        matched = 0
        contradictory = 0
        for sample in relevant:
            validation_match = (
                bool(candidate.dominant_validation_command)
                and sample.validation_command == candidate.dominant_validation_command
            )
            working_set_match = _working_set_match_ratio(candidate, sample) >= 0.5
            strong_instrumentation = sample.instrumentation_status in {"strong_match", "usable_match"}
            if validation_match or (working_set_match and strong_instrumentation):
                matched += 1
            if sample.instrumentation_status == "weak_match" and not validation_match:
                contradictory += 1
        heldout_match_rate = round((matched / heldout_count), 3) if heldout_count else 1.0
        regression_risk = round((contradictory / heldout_count), 3) if heldout_count else 0.0
        coverage_count = len(candidate.supporting_task_ids)
        if coverage_count >= 2 and heldout_match_rate >= 0.67 and regression_risk <= 0.2:
            verification_status = "passed"
            verification_reason = "candidate held across the held-out family slice"
        elif heldout_count <= 0 and coverage_count >= 2:
            verification_status = "provisional"
            verification_reason = "candidate has enough support but no held-out slice yet"
        else:
            verification_status = "failed"
            verification_reason = "candidate does not hold strongly enough across held-out family evidence"
        return CandidateVerification(
            candidate_id=candidate.candidate_id,
            task_family=candidate.task_family,
            coverage_count=coverage_count,
            heldout_count=heldout_count,
            heldout_match_rate=heldout_match_rate,
            regression_risk=regression_risk,
            verification_status=verification_status,
            verification_reason=verification_reason,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )

    def promote_candidates(
        self,
        candidates: list[StrategyCandidate],
        verifications: list[CandidateVerification],
    ) -> list[PromotedPrior]:
        verification_map = {item.candidate_id: item for item in verifications}
        promotions: list[PromotedPrior] = []
        for candidate in candidates:
            verification = verification_map.get(candidate.candidate_id)
            confidence = _confidence_for_candidate(candidate)
            promotion_status = "candidate"
            promotion_reason = "candidate has not yet reached trial thresholds"
            forgetting_stale = (
                candidate.evicted_forgetting_count >= 2
                or candidate.stale_guidance_count >= 2
                or candidate.suppressed_forgetting_count >= 3
            )
            if forgetting_stale:
                promotion_status = "deprecated"
                promotion_reason = (
                    "candidate guidance has been repeatedly suppressed or evicted by newer successful guidance"
                )
            if (
                not forgetting_stale
                and verification
                and verification.verification_status == "passed"
                and candidate.sample_count >= 3
                and candidate.recent_success_count >= 1
                and verification.heldout_match_rate >= 0.67
                and verification.regression_risk <= 0.2
            ):
                promotion_status = "seed_ready"
                promotion_reason = "candidate passed held-out verification and met seed thresholds"
            elif (
                not forgetting_stale
                and candidate.sample_count >= 2
                and candidate.recent_success_count >= 1
                and confidence >= 0.6
            ):
                promotion_status = "trial"
                promotion_reason = "candidate has enough support to enter trial but is not yet seed-ready"
            if (
                not forgetting_stale
                and verification
                and verification.verification_status == "failed"
                and verification.regression_risk >= 0.5
            ):
                promotion_status = "deprecated"
                promotion_reason = "candidate shows too much contradictory evidence in the held-out slice"
            promotions.append(
                PromotedPrior(
                    prior_id=candidate.candidate_id,
                    task_family=candidate.task_family,
                    strategy_profile=candidate.strategy_profile,
                    validation_style=candidate.validation_style,
                    dominant_validation_command=candidate.dominant_validation_command,
                    dominant_working_set=candidate.dominant_working_set[:6],
                    dominant_doc_input=candidate.dominant_doc_input,
                    dominant_source_doc_id=candidate.dominant_source_doc_id,
                    dominant_doc_action=candidate.dominant_doc_action,
                    dominant_selected_tool=candidate.dominant_selected_tool,
                    dominant_event_source=candidate.dominant_event_source,
                    latest_recorded_at=candidate.latest_recorded_at,
                    doc_sample_count=candidate.doc_sample_count,
                    editor_sync_count=candidate.editor_sync_count,
                    dominant_reviewer_standard=candidate.dominant_reviewer_standard,
                    dominant_reviewer_outputs=candidate.dominant_reviewer_outputs,
                    dominant_reviewer_checks=candidate.dominant_reviewer_checks,
                    dominant_reviewer_pack_source=candidate.dominant_reviewer_pack_source,
                    dominant_reviewer_selected_tool=candidate.dominant_reviewer_selected_tool,
                    dominant_reviewer_resume_anchor=candidate.dominant_reviewer_resume_anchor,
                    reviewer_sample_count=candidate.reviewer_sample_count,
                    reviewer_ready_count=candidate.reviewer_ready_count,
                    reviewer_rollback_count=candidate.reviewer_rollback_count,
                    promotion_status=promotion_status,
                    promotion_reason=promotion_reason,
                    confidence=confidence,
                    sample_count=candidate.sample_count,
                    recent_success_count=candidate.recent_success_count,
                    verification_summary=(
                        verification.verification_reason if verification else "candidate has not been verified yet"
                    ),
                    promoted_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return promotions

    def run_cycle(self, *, limit: int = 48) -> dict[str, object]:
        generated_at = datetime.now(timezone.utc).isoformat()
        samples = self.extract_samples(limit=limit)
        candidates = self.distill_candidates(samples)
        verifications = [self.verify_candidate(candidate, samples) for candidate in candidates]
        promotions = self.promote_candidates(candidates, verifications)

        summary = {
            "generated_at": generated_at,
            "samples_reviewed": len(samples),
            "families_reviewed": len({sample.task_family for sample in samples if sample.task_family}),
            "candidates_generated": len(candidates),
            "verifications_generated": len(verifications),
            "promotions_generated": len(promotions),
            "seed_ready_count": sum(1 for item in promotions if item.promotion_status == "seed_ready"),
            "trial_count": sum(1 for item in promotions if item.promotion_status == "trial"),
            "candidate_count": sum(1 for item in promotions if item.promotion_status == "candidate"),
            "deprecated_count": sum(1 for item in promotions if item.promotion_status == "deprecated"),
            "top_families": list(
                dict.fromkeys(item.task_family for item in promotions if item.task_family)
            )[:6],
        }
        candidates_payload = {
            "generated_at": generated_at,
            "summary": summary,
            "samples": [item.to_dict() for item in samples],
            "candidates": [item.to_dict() for item in candidates],
            "verifications": [item.to_dict() for item in verifications],
        }
        promotions_payload = {
            "generated_at": generated_at,
            "summary": summary,
            "promotions": [item.to_dict() for item in promotions],
        }
        candidate_local_path, candidate_project_path = save_dream_candidates(
            repo_root=self._repo_root,
            project_scope=self._project_scope,
            payload=candidates_payload,
        )
        promotion_local_path, promotion_project_path = save_dream_promotions(
            repo_root=self._repo_root,
            project_scope=self._project_scope,
            payload=promotions_payload,
        )
        return {
            "generated_at": generated_at,
            "summary": summary,
            "samples": samples,
            "candidates": candidates,
            "verifications": verifications,
            "promotions": promotions,
            "candidate_path": str(candidate_local_path),
            "project_candidate_path": str(candidate_project_path),
            "promotion_path": str(promotion_local_path),
            "project_promotion_path": str(promotion_project_path),
        }
