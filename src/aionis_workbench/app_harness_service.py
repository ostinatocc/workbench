from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from .app_harness_artifacts import materialize_static_demo_artifact
from .app_harness_models import (
    AppHarnessState,
    EvaluatorCriterion,
    ProductSpec,
    SprintContract,
    SprintExecutionAttempt,
    SprintEvaluation,
    SprintNegotiationRound,
    SprintRevision,
)
from .delivery_families import (
    NODE_EXPRESS_API,
    NEXTJS_WEB,
    PYTHON_FASTAPI_API,
    REACT_VITE_WEB,
    SVELTE_VITE_WEB,
    VUE_VITE_WEB,
    delivery_family_validation_commands,
    infer_delivery_family_from_prompt,
)
from .session import ArtifactReference, SessionState


def _ensure_app_harness_state(session: SessionState) -> AppHarnessState:
    if session.app_harness_state is None:
        session.app_harness_state = AppHarnessState()
    return session.app_harness_state


def _clean_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip()).strip(" .,:;!?")


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _subject_parts(prompt: str) -> tuple[str, str]:
    cleaned = _clean_prompt(prompt)
    if not cleaned:
        return ("", "")
    cleaned = re.sub(r"^(build|create|make|design|ship|prototype|plan)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(a|an|the)\s+", "", cleaned, flags=re.IGNORECASE)
    if re.search(r"\s+for\s+", cleaned, flags=re.IGNORECASE):
        head, context = re.split(r"\s+for\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
        return (head.strip(), context.strip())
    return (cleaned.strip(), "")


def _title_from_prompt(prompt: str) -> str:
    head, _context = _subject_parts(prompt)
    if not head:
        return ""
    tokens = [part for part in re.split(r"[\s/-]+", head) if part]
    return " ".join(token.capitalize() for token in tokens[:5])


def _infer_app_type(prompt: str) -> str:
    family_id = infer_delivery_family_from_prompt(prompt)
    if family_id in {PYTHON_FASTAPI_API.family_id, NODE_EXPRESS_API.family_id}:
        return "api_service"
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id, NEXTJS_WEB.family_id}:
        return "desktop_like_web_app"
    lowered = prompt.lower()
    if any(token in lowered for token in ("editor", "studio", "workspace", "explorer", "dashboard", "canvas")):
        return "desktop_like_web_app"
    return "full_stack_app"


def _infer_stack(app_type: str, prompt: str = "") -> list[str]:
    family_id = infer_delivery_family_from_prompt(prompt)
    if family_id == REACT_VITE_WEB.family_id:
        return ["React", "Vite", "SQLite"]
    if family_id == NEXTJS_WEB.family_id:
        return ["Next.js", "React", "SQLite"]
    if family_id == SVELTE_VITE_WEB.family_id:
        return ["Svelte", "Vite", "SQLite"]
    if family_id == VUE_VITE_WEB.family_id:
        return ["Vue", "Vite", "SQLite"]
    if family_id == PYTHON_FASTAPI_API.family_id:
        return ["FastAPI", "SQLite"]
    if family_id == NODE_EXPRESS_API.family_id:
        return ["Node", "Express"]
    if app_type == "desktop_like_web_app":
        return ["React", "Vite", "SQLite"]
    return ["React", "Vite", "FastAPI", "SQLite"]


def _infer_features(prompt: str) -> list[str]:
    head, context = _subject_parts(prompt)
    features: list[str] = []
    if head:
        features.append(head.lower())
    if context:
        features.append(context.lower())
    features.extend(
        [
            "project workspace",
            "stateful persistence",
        ]
    )
    deduped: list[str] = []
    for item in features:
        cleaned = item.strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:3]


def _infer_feature_groups(features: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    if features:
        groups["core_workflow"] = [features[0]]
    if len(features) >= 2:
        groups["supporting_workflows"] = [features[1]]
    if len(features) >= 3:
        groups["system_foundations"] = [features[2]]
    return groups


def _infer_feature_rationale(groups: dict[str, list[str]]) -> dict[str, str]:
    rationale: dict[str, str] = {}
    if groups.get("core_workflow"):
        rationale["core_workflow"] = "This is the primary user-visible path the first sprint should make tangible."
    if groups.get("supporting_workflows"):
        rationale["supporting_workflows"] = "These flows reinforce the core path and should be stabilized right after the first usable shell."
    if groups.get("system_foundations"):
        rationale["system_foundations"] = "These foundations keep state, navigation, and persistence coherent as the app grows."
    return rationale


def _build_planning_rationale(product: ProductSpec) -> list[str]:
    notes: list[str] = []
    core = ", ".join(product.feature_groups.get("core_workflow") or product.features[:1])
    support = ", ".join(product.feature_groups.get("supporting_workflows") or product.features[1:2])
    foundations = ", ".join(product.feature_groups.get("system_foundations") or product.features[2:3])
    if core:
        notes.append(f"Start by making the core workflow tangible: {core}.")
    if support:
        notes.append(f"Keep the second sprint focused on supporting workflows: {support}.")
    if foundations:
        notes.append(f"Treat foundational work as stability infrastructure: {foundations}.")
    lowered_stack = {item.lower() for item in product.stack}
    if "fastapi" in lowered_stack or "express" in lowered_stack or "node" in lowered_stack:
        notes.append("Bias toward a narrow, runnable service surface before widening the API.")
    elif product.app_type == "desktop_like_web_app":
        notes.append("Bias toward a dense workspace shell before polishing secondary interactions.")
    else:
        notes.append("Bias toward end-to-end product flow before widening the surface area.")
    return notes[:4]


def _build_sprint_negotiation_notes(product: ProductSpec, active: SprintContract, planned: list[SprintContract]) -> list[str]:
    notes: list[str] = []
    core = ", ".join(product.feature_groups.get("core_workflow") or product.features[:1]) or "core workflow"
    notes.append(f"Do not approve follow-up work until sprint-1 proves the {core} path.")
    if planned:
        next_scope = ", ".join(planned[0].scope[:2]) or planned[0].sprint_id
        notes.append(f"Evaluator should challenge whether {next_scope} genuinely depends on sprint-1 being stable.")
    checks = ", ".join(active.acceptance_checks[:2]) or "validation path"
    notes.append(f"Sprint negotiation should keep acceptance checks explicit: {checks}.")
    return notes[:4]


def _infer_design_direction(prompt: str, app_type: str) -> str:
    lowered = prompt.lower()
    family_id = infer_delivery_family_from_prompt(prompt)
    if family_id in {PYTHON_FASTAPI_API.family_id, NODE_EXPRESS_API.family_id}:
        return "narrow service surface with explicit endpoints and clear runtime behavior"
    if any(token in lowered for token in ("editor", "canvas", "design", "creative")):
        return "editor-first interface with dense but legible controls"
    if app_type == "desktop_like_web_app":
        return "high-signal workspace with clear navigation and compact panels"
    return "focused product shell with clear hierarchy and progressive disclosure"


def _default_evaluator_criteria() -> list[EvaluatorCriterion]:
    return [
        EvaluatorCriterion(
            name="functionality",
            description="Core product flows should work end-to-end.",
            threshold=0.85,
            weight=1.0,
        ),
        EvaluatorCriterion(
            name="design_quality",
            description="The interface should feel cohesive and intentional.",
            threshold=0.7,
            weight=1.0,
        ),
        EvaluatorCriterion(
            name="code_quality",
            description="The implementation should remain maintainable and reviewable.",
            threshold=0.75,
            weight=0.8,
        ),
    ]


def _infer_sprint_goal(product: ProductSpec) -> str:
    if product.features:
        lead = product.features[0]
        return f"Ship the first usable {lead} workflow."
    return f"Ship the first usable {product.title or 'application'} shell."


def _infer_sprint_scope(product: ProductSpec) -> list[str]:
    scope = list(product.features[:2])
    lowered_stack = {item.lower() for item in product.stack}
    if "fastapi" in lowered_stack or "express" in lowered_stack or "node" in lowered_stack:
        scope.append("service surface")
    else:
        scope.append("navigation shell")
    deduped: list[str] = []
    for item in scope:
        cleaned = item.strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:3]


def _infer_acceptance_checks(product: ProductSpec) -> list[str]:
    lowered_stack = {item.lower() for item in product.stack}
    if "fastapi" in lowered_stack:
        return delivery_family_validation_commands(PYTHON_FASTAPI_API.family_id)
    if "express" in lowered_stack or "node" in lowered_stack:
        return delivery_family_validation_commands(NODE_EXPRESS_API.family_id)
    if "next.js" in lowered_stack or "nextjs" in lowered_stack:
        return ["npm run build"]
    if "react" in lowered_stack or "vue" in lowered_stack or "svelte" in lowered_stack or "vite" in lowered_stack:
        return ["npm run build"]
    return ["pytest -q"]


def _infer_done_definition(product: ProductSpec) -> list[str]:
    items: list[str] = []
    lowered_stack = {item.lower() for item in product.stack}
    if "fastapi" in lowered_stack or "express" in lowered_stack or "node" in lowered_stack:
        for feature in product.features[:2]:
            items.append(f"{feature} is exposed through the runnable service surface")
        items.append("the primary endpoint contract is coherent")
    else:
        for feature in product.features[:2]:
            items.append(f"{feature} is visibly wired into the app shell")
        items.append("primary navigation and state flow are coherent")
    deduped: list[str] = []
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:3]


def _seed_followup_sprint(state: AppHarnessState, product: ProductSpec) -> bool:
    if any(item.sprint_id == "sprint-2" for item in state.planned_sprint_contracts):
        return False
    supporting_scope = list(product.feature_groups.get("supporting_workflows") or [])
    supporting_scope.extend(product.feature_groups.get("system_foundations") or [])
    if not supporting_scope:
        supporting_scope = list(product.features[1:3]) or list(product.features[:1])
    supporting_scope.append("quality pass")
    deduped_scope: list[str] = []
    for item in supporting_scope:
        cleaned = item.strip()
        if cleaned and cleaned not in deduped_scope:
            deduped_scope.append(cleaned)
    core_name = next(iter(product.feature_groups.get("core_workflow") or product.features[:1]), product.title or "core workflow")
    goal_subject = " and ".join(deduped_scope[:2]) if deduped_scope else "supporting workflows"
    followup = SprintContract(
        sprint_id="sprint-2",
        goal=f"Stabilize {goal_subject} around the {core_name} release path.",
        scope=deduped_scope[:3],
        acceptance_checks=_infer_acceptance_checks(product),
        done_definition=[
            f"{item} holds up under the primary workflow" for item in deduped_scope[:2]
        ]
        + [
            f"{core_name} feels cohesive end-to-end",
        ],
        proposed_by="planner",
        approved=False,
    )
    state.planned_sprint_contracts.append(followup)
    if "sprint-2" not in product.sprint_ids:
        product.sprint_ids.append("sprint-2")
    return True


def _seed_initial_sprint(state: AppHarnessState, product: ProductSpec) -> bool:
    if state.active_sprint_contract is not None or state.sprint_history:
        return False
    state.active_sprint_contract = SprintContract(
        sprint_id="sprint-1",
        goal=_infer_sprint_goal(product),
        scope=_infer_sprint_scope(product),
        acceptance_checks=_infer_acceptance_checks(product),
        done_definition=_infer_done_definition(product),
        proposed_by="planner",
        approved=False,
    )
    if "sprint-1" not in product.sprint_ids:
        product.sprint_ids.append("sprint-1")
    state.sprint_history.append(state.active_sprint_contract)
    return True


def _default_criterion_score(
    criterion: EvaluatorCriterion,
    *,
    contract: SprintContract | None,
    summary: str,
    blocker_notes: list[str],
    requested_status: str,
    execution_summary: str,
    changed_target_hints: list[str],
    execution_success: bool | None,
) -> float:
    baseline = max(criterion.threshold, 0.72)
    if contract and contract.acceptance_checks:
        baseline += 0.08
    if contract and contract.done_definition:
        baseline += 0.05
    if contract and contract.approved:
        baseline += 0.03
    if not summary:
        baseline -= 0.05
    if execution_summary:
        baseline += 0.04
    if changed_target_hints:
        baseline += 0.03
    if execution_success is False:
        baseline -= 0.08
    if blocker_notes:
        baseline -= 0.24
    if requested_status == "failed":
        baseline -= 0.12
    elif requested_status == "passed":
        baseline = max(baseline, criterion.threshold + 0.05)
    return _clamp_score(baseline)


def _derive_criteria_scores(
    criteria: list[EvaluatorCriterion],
    *,
    explicit_scores: dict[str, float],
    contract: SprintContract | None,
    summary: str,
    blocker_notes: list[str],
    requested_status: str,
    execution_summary: str,
    changed_target_hints: list[str],
    execution_success: bool | None,
) -> dict[str, float]:
    scores: dict[str, float] = {
        key.strip(): _clamp_score(float(value))
        for key, value in explicit_scores.items()
        if isinstance(key, str) and key.strip()
    }
    for criterion in criteria:
        if criterion.name in scores:
            continue
        scores[criterion.name] = _default_criterion_score(
            criterion,
            contract=contract,
            summary=summary,
            blocker_notes=blocker_notes,
            requested_status=requested_status,
            execution_summary=execution_summary,
            changed_target_hints=changed_target_hints,
            execution_success=execution_success,
        )
    return scores


def _classify_criteria(
    criteria: list[EvaluatorCriterion],
    *,
    scores: dict[str, float],
) -> tuple[list[str], list[str]]:
    passing: list[str] = []
    failing: list[str] = []
    threshold_map = {criterion.name: float(criterion.threshold) for criterion in criteria}
    for name, score in scores.items():
        threshold = threshold_map.get(name, 0.0)
        if score >= threshold:
            passing.append(name)
        else:
            failing.append(name)
    return passing, failing


def _normalize_criteria_names(
    values: list[str] | None,
    *,
    allowed_names: set[str],
) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned not in allowed_names or cleaned in normalized:
            continue
        normalized.append(cleaned)
    return normalized


def _derive_evaluation_status(
    requested_status: str,
    *,
    blocker_notes: list[str],
    failing_criteria: list[str],
) -> str:
    normalized = requested_status.strip().lower()
    if normalized and normalized != "auto":
        return normalized
    if blocker_notes or failing_criteria:
        return "failed"
    return "passed"


def _derive_evaluation_summary(
    requested_summary: str,
    *,
    contract: SprintContract | None,
    status: str,
    passing_criteria: list[str],
    failing_criteria: list[str],
    blocker_notes: list[str],
    execution_summary: str,
    changed_target_hints: list[str],
) -> str:
    summary = requested_summary.strip()
    if summary:
        return summary
    sprint_label = contract.goal if contract and contract.goal else "current sprint"
    execution_suffix = ""
    if execution_summary.strip():
        execution_suffix = f" after {execution_summary.strip()}"
    elif changed_target_hints:
        execution_suffix = f" after targeting {', '.join(_dedup_text_items(list(changed_target_hints))[:2])}"
    if status == "passed":
        passed = ", ".join(passing_criteria[:2]) or "all evaluator criteria"
        return f"{sprint_label}{execution_suffix} meets the current evaluator bar across {passed}."
    failed = ", ".join(failing_criteria[:2]) or "the evaluator contract"
    blocker = blocker_notes[0] if blocker_notes else "follow-up fixes are still required."
    return f"{sprint_label}{execution_suffix} still fails {failed}; {blocker}"


def _derive_negotiation_round(
    *,
    sprint: SprintContract,
    evaluation: SprintEvaluation | None,
    planned_sprints: list[SprintContract],
    explicit_objections: list[str] | None = None,
) -> SprintNegotiationRound:
    objections: list[str] = []
    for name in (evaluation.failing_criteria if evaluation else []):
        cleaned = name.strip()
        if cleaned and f"Resolve failing criterion: {cleaned}." not in objections:
            objections.append(f"Resolve failing criterion: {cleaned}.")
    for note in (evaluation.blocker_notes if evaluation else []):
        cleaned = note.strip()
        if cleaned and cleaned not in objections:
            objections.append(cleaned)
    for note in explicit_objections or []:
        cleaned = note.strip()
        if cleaned and cleaned not in objections:
            objections.append(cleaned)
    if not objections and evaluation and evaluation.status == "failed":
        objections.append("Sprint still needs revision before it should be approved for follow-up work.")

    planner_response: list[str] = []
    if objections:
        planner_response.append(f"Keep {sprint.sprint_id} narrow until the evaluator objections are cleared.")
    else:
        planner_response.append(f"{sprint.sprint_id} can advance without revising the current contract.")
    if planned_sprints:
        next_sprint = planned_sprints[0]
        next_scope = ", ".join(next_sprint.scope[:2]) or next_sprint.sprint_id
        planner_response.append(
            f"Do not approve {next_sprint.sprint_id} until {sprint.sprint_id} proves the current path and {next_scope} depends on it."
        )
    if sprint.acceptance_checks:
        planner_response.append(
            f"Keep the next revision anchored to acceptance checks: {', '.join(sprint.acceptance_checks[:2])}."
        )
    recommended_action = "revise_current_sprint" if objections else "advance_to_next_sprint"
    return SprintNegotiationRound(
        sprint_id=sprint.sprint_id,
        planner_mode="deterministic",
        evaluator_mode=evaluation.evaluator_mode if evaluation else "",
        evaluator_status=evaluation.status if evaluation else "",
        objections=objections[:4],
        planner_response=planner_response[:4],
        recommended_action=recommended_action,
    )


def _normalize_recommended_action(value: str) -> str:
    cleaned = value.strip()
    if cleaned in {"revise_current_sprint", "advance_to_next_sprint"}:
        return cleaned
    return ""


def _dedup_text_items(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _derive_revision_diff_summary(
    *,
    must_fix: list[str],
    must_keep: list[str],
    explicit_notes: list[str],
) -> list[str]:
    summary: list[str] = []
    if must_fix:
        summary.append(f"Fix: {', '.join(must_fix[:2])}.")
    if must_keep:
        summary.append(f"Keep: {', '.join(must_keep[:2])}.")
    if explicit_notes:
        summary.append(f"Operator notes: {', '.join(explicit_notes[:2])}.")
    return summary[:3]


def _next_replanned_sprint_id(state: AppHarnessState, sprint_id: str) -> str:
    prefix = f"{sprint_id}-replan-"
    max_index = 0
    for contract in state.sprint_history + state.planned_sprint_contracts:
        if not contract.sprint_id.startswith(prefix):
            continue
        suffix = contract.sprint_id[len(prefix) :].strip()
        if suffix.isdigit():
            max_index = max(max_index, int(suffix))
    active = state.active_sprint_contract
    if active is not None and active.sprint_id.startswith(prefix):
        suffix = active.sprint_id[len(prefix) :].strip()
        if suffix.isdigit():
            max_index = max(max_index, int(suffix))
    return f"{prefix}{max_index + 1}"


def _replan_depth(sprint_id: str) -> int:
    cleaned = sprint_id.strip()
    if not cleaned:
        return 0
    return cleaned.count("-replan-")


def _replan_root_sprint_id(sprint_id: str) -> str:
    cleaned = sprint_id.strip()
    if not cleaned:
        return ""
    return cleaned.split("-replan-", 1)[0]


def _derive_execution_summary(
    *,
    sprint: SprintContract,
    revision: SprintRevision | None,
    explicit_summary: str,
    changed_target_hints: list[str] | None = None,
) -> str:
    summary = explicit_summary.strip()
    if summary:
        return summary
    target_preview = ", ".join(
        item.rstrip(".").strip()
        for item in _dedup_text_items(list(changed_target_hints or []))[:2]
        if item.strip()
    ).strip()
    if revision is not None:
        top_fix = target_preview or ", ".join(revision.must_fix[:2]) or revision.revision_summary or sprint.goal
        return f"Execute the bounded revision for {sprint.sprint_id}: {top_fix}."
    top_scope = target_preview or ", ".join(sprint.scope[:2]) or sprint.goal
    return f"Execute the current sprint contract for {sprint.sprint_id}: {top_scope}."


def _derive_revision_improvement_status(
    *,
    baseline_status: str,
    baseline_failing: list[str],
    outcome_status: str,
    outcome_failing: list[str],
) -> str:
    normalized_baseline = baseline_status.strip().lower()
    normalized_outcome = outcome_status.strip().lower()
    if not normalized_outcome:
        return "pending"
    if normalized_baseline == "failed" and normalized_outcome == "passed":
        return "improved"
    if normalized_baseline == "passed" and normalized_outcome == "failed":
        return "regressed"
    baseline_count = len(_dedup_text_items(list(baseline_failing)))
    outcome_count = len(_dedup_text_items(list(outcome_failing)))
    if outcome_count < baseline_count:
        return "improved"
    if outcome_count > baseline_count:
        return "regressed"
    if normalized_baseline == normalized_outcome:
        return "unchanged"
    return "changed"


def _latest_execution_attempt_for_sprint(
    state: AppHarnessState,
    *,
    sprint_id: str,
) -> SprintExecutionAttempt | None:
    if not sprint_id:
        return None
    if state.latest_execution_attempt is not None and state.latest_execution_attempt.sprint_id == sprint_id:
        return state.latest_execution_attempt
    for item in reversed(state.execution_history):
        if item.sprint_id == sprint_id:
            return item
    return None


def _derive_policy_stage(sprint_id: str) -> str:
    depth = _replan_depth(sprint_id)
    if depth <= 0:
        return "base"
    if depth == 1:
        return "replanned"
    if depth == 2:
        return "second_replan"
    return "deep_replan"


def _derive_execution_outcome_projection(
    attempt: SprintExecutionAttempt | None,
) -> dict[str, Any]:
    if attempt is None:
        return {
            "execution_outcome_ready": False,
            "execution_gate": "no_execution",
            "execution_focus": "",
        }
    focus = attempt.execution_summary.strip()
    if not focus:
        focus = ", ".join(_dedup_text_items(list(attempt.changed_target_hints))[:2]).strip()
    status = (attempt.status or "").strip()
    if status == "qa_passed" and attempt.success is True:
        gate = "ready"
        ready = True
    elif status == "recorded":
        gate = "needs_qa"
        ready = False
    elif status == "qa_failed" or attempt.success is False:
        gate = "qa_failed"
        ready = False
    else:
        gate = status or "unsettled"
        ready = False
    return {
        "execution_outcome_ready": ready,
        "execution_gate": gate,
        "execution_focus": focus,
    }


def _record_execution_gate_transition(
    state: AppHarnessState,
    *,
    previous_gate: str = "",
    current_gate: str = "",
    action: str = "",
) -> None:
    previous = str(previous_gate or "").strip()
    current = str(current_gate or "").strip()
    normalized_action = str(action or "").strip()
    transition = ""
    if previous and current:
        transition = f"{previous}->{current}"
    elif current:
        transition = current
    elif previous:
        transition = previous
    state.last_execution_gate_from = previous
    state.last_execution_gate_to = current
    state.last_execution_gate_transition = transition
    state.last_policy_action = normalized_action


def _derive_post_revision_policy(state: AppHarnessState) -> dict[str, Any]:
    next_sprint = state.planned_sprint_contracts[0] if state.planned_sprint_contracts else None
    latest_evaluation = state.latest_sprint_evaluation
    latest_revision = state.latest_revision
    sprint_id = state.active_sprint_contract.sprint_id if state.active_sprint_contract is not None else ""
    latest_execution_attempt = _latest_execution_attempt_for_sprint(state, sprint_id=sprint_id)
    execution_projection = _derive_execution_outcome_projection(latest_execution_attempt)
    retry_remaining = max(0, int(state.retry_budget) - int(state.retry_count))
    next_sprint_id = next_sprint.sprint_id if next_sprint is not None else ""

    if state.loop_status == "sprint_replanned":
        return {
            **execution_projection,
            "next_sprint_ready": False,
            "next_sprint_candidate_id": "",
            "retry_available": False,
            "retry_remaining": retry_remaining,
            "recommended_next_action": "run_current_sprint",
            "loop_status": "sprint_replanned",
        }

    if latest_revision is not None and latest_evaluation is not None and latest_revision.sprint_id == latest_evaluation.sprint_id:
        if (
            latest_execution_attempt is not None
            and latest_execution_attempt.sprint_id == latest_evaluation.sprint_id
            and latest_execution_attempt.status == "recorded"
        ):
            return {
                **execution_projection,
                "next_sprint_ready": False,
                "next_sprint_candidate_id": "",
                "retry_available": False,
                "retry_remaining": retry_remaining,
                "recommended_next_action": "evaluate_current_execution",
                "loop_status": "execution_recorded",
            }
        if latest_evaluation.status == "passed":
            return {
                **execution_projection,
                "next_sprint_ready": bool(next_sprint_id),
                "next_sprint_candidate_id": next_sprint_id,
                "retry_available": False,
                "retry_remaining": retry_remaining,
                "recommended_next_action": "advance_to_next_sprint" if next_sprint_id else "close_current_sprint",
                "loop_status": "ready_for_next_sprint",
            }
        if retry_remaining > 0:
            return {
                **execution_projection,
                "next_sprint_ready": False,
                "next_sprint_candidate_id": "",
                "retry_available": True,
                "retry_remaining": retry_remaining,
                "recommended_next_action": "retry_current_sprint",
                "loop_status": "retry_available",
            }
        return {
            **execution_projection,
            "next_sprint_ready": False,
            "next_sprint_candidate_id": "",
            "retry_available": False,
            "retry_remaining": retry_remaining,
            "recommended_next_action": "replan_or_escalate",
            "loop_status": "retry_budget_exhausted",
        }

    if latest_evaluation is not None and latest_evaluation.status == "passed":
        if latest_execution_attempt is not None and latest_execution_attempt.status == "recorded":
            return {
                **execution_projection,
                "next_sprint_ready": False,
                "next_sprint_candidate_id": "",
                "retry_available": False,
                "retry_remaining": retry_remaining,
                "recommended_next_action": "evaluate_current_execution",
                "loop_status": "execution_recorded",
            }
        return {
            **execution_projection,
            "next_sprint_ready": bool(next_sprint_id),
            "next_sprint_candidate_id": next_sprint_id,
            "retry_available": False,
            "retry_remaining": retry_remaining,
            "recommended_next_action": "advance_to_next_sprint" if next_sprint_id else "close_current_sprint",
            "loop_status": "ready_for_next_sprint",
        }

    if latest_evaluation is not None and latest_evaluation.status == "failed":
        return {
            **execution_projection,
            "next_sprint_ready": False,
            "next_sprint_candidate_id": "",
            "retry_available": False,
            "retry_remaining": retry_remaining,
            "recommended_next_action": "negotiate_current_sprint",
            "loop_status": "needs_revision",
        }

    return {
        **execution_projection,
        "next_sprint_ready": False,
        "next_sprint_candidate_id": "",
        "retry_available": retry_remaining > 0 and latest_revision is not None,
        "retry_remaining": retry_remaining,
        "recommended_next_action": "",
        "loop_status": state.loop_status,
    }


def _active_sprint_for_update(state: AppHarnessState, sprint_id: str = "") -> SprintContract | None:
    sprint = state.active_sprint_contract
    if sprint is None:
        return None
    if sprint_id and sprint.sprint_id != sprint_id:
        return None
    return sprint


def _sprint_for_id(state: AppHarnessState, sprint_id: str) -> SprintContract | None:
    if not sprint_id:
        return None
    if state.active_sprint_contract is not None and state.active_sprint_contract.sprint_id == sprint_id:
        return state.active_sprint_contract
    for collection in (state.planned_sprint_contracts, state.sprint_history):
        for item in collection:
            if item.sprint_id == sprint_id:
                return item
    return None


def _attach_execution_artifact(
    session: SessionState,
    *,
    state: AppHarnessState,
    attempt: SprintExecutionAttempt,
) -> SprintExecutionAttempt:
    if attempt.artifact_kind and attempt.artifact_path:
        artifact_ref = ArtifactReference(
            artifact_id=attempt.attempt_id,
            kind=attempt.artifact_kind,
            role="generator",
            summary=attempt.execution_summary or f"Execution artifact for {attempt.attempt_id}",
            path=attempt.artifact_path,
            metadata={"attempt_id": attempt.attempt_id},
        )
        session.artifacts = [
            item
            for item in session.artifacts
            if not (item.kind == artifact_ref.kind and item.metadata.get("attempt_id") == attempt.attempt_id)
        ]
        session.artifacts.insert(0, artifact_ref)
        return attempt
    sprint = _sprint_for_id(state, attempt.sprint_id)
    if sprint is None:
        return attempt
    revision = state.latest_revision if state.latest_revision and state.latest_revision.sprint_id == attempt.sprint_id else None
    artifact_kind, artifact_path, preview_command, artifact_ref = materialize_static_demo_artifact(
        session=session,
        state=state,
        sprint=sprint,
        revision=revision,
        attempt=attempt,
    )
    updated = replace(
        attempt,
        artifact_kind=artifact_kind,
        artifact_path=artifact_path,
        preview_command=preview_command,
    )
    session.artifacts = [
        item
        for item in session.artifacts
        if not (item.kind == artifact_ref.kind and item.metadata.get("attempt_id") == attempt.attempt_id)
    ]
    session.artifacts.insert(0, artifact_ref)
    return updated


def _reset_sprint_loop_state(
    state: AppHarnessState,
    *,
    clear_execution_attempt: bool = True,
    reset_retry_count: bool = True,
) -> None:
    state.latest_sprint_evaluation = None
    state.latest_negotiation_round = None
    state.latest_revision = None
    if clear_execution_attempt:
        state.latest_execution_attempt = None
    if reset_retry_count:
        state.retry_count = 0


class AppHarnessService:
    def plan_app(
        self,
        session: SessionState,
        *,
        prompt: str,
        title: str = "",
        app_type: str = "",
        stack: list[str] | None = None,
        features: list[str] | None = None,
        feature_groups: dict[str, list[str]] | None = None,
        feature_rationale: dict[str, str] | None = None,
        design_direction: str = "",
        evaluator_criteria: list[EvaluatorCriterion] | None = None,
        planning_rationale: list[str] | None = None,
        sprint_negotiation_notes: list[str] | None = None,
        initial_sprint_contract: SprintContract | None = None,
        planner_mode: str = "deterministic",
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        resolved_title = title or _title_from_prompt(prompt)
        resolved_app_type = app_type or _infer_app_type(prompt)
        resolved_stack = list(stack or _infer_stack(resolved_app_type, prompt))
        resolved_features = list(features or _infer_features(prompt))
        resolved_feature_groups = feature_groups or _infer_feature_groups(resolved_features)
        resolved_design_direction = design_direction or _infer_design_direction(prompt, resolved_app_type)
        product_spec = ProductSpec(
            prompt=prompt,
            title=resolved_title,
            app_type=resolved_app_type,
            stack=resolved_stack,
            features=resolved_features,
            feature_groups=resolved_feature_groups,
            feature_rationale=feature_rationale or _infer_feature_rationale(resolved_feature_groups),
            design_direction=resolved_design_direction,
            sprint_ids=list(state.product_spec.sprint_ids) if state.product_spec else [],
        )
        state.product_spec = product_spec
        state.evaluator_criteria = list(evaluator_criteria or _default_evaluator_criteria())
        state.planner_mode = planner_mode
        seeded = False
        if initial_sprint_contract is not None and state.active_sprint_contract is None and not state.sprint_history:
            state.active_sprint_contract = initial_sprint_contract
            if initial_sprint_contract.sprint_id not in product_spec.sprint_ids:
                product_spec.sprint_ids.append(initial_sprint_contract.sprint_id)
            state.sprint_history = [
                item for item in state.sprint_history if item.sprint_id != initial_sprint_contract.sprint_id
            ]
            state.sprint_history.append(initial_sprint_contract)
            seeded = True
        else:
            seeded = _seed_initial_sprint(state, product_spec)
        _seed_followup_sprint(state, product_spec)
        if state.active_sprint_contract is not None:
            state.planning_rationale = list(planning_rationale or _build_planning_rationale(product_spec))
            state.sprint_negotiation_notes = list(sprint_negotiation_notes or _build_sprint_negotiation_notes(
                product_spec,
                state.active_sprint_contract,
                state.planned_sprint_contracts,
            ))
        if seeded:
            state.loop_status = "sprint_proposed"
        else:
            state.loop_status = state.loop_status or "planned"
        return self.app_state_summary(session)

    def set_sprint_contract(
        self,
        session: SessionState,
        *,
        sprint_id: str,
        goal: str,
        scope: list[str] | None = None,
        acceptance_checks: list[str] | None = None,
        done_definition: list[str] | None = None,
        proposed_by: str = "",
        approved: bool = False,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        contract = SprintContract(
            sprint_id=sprint_id,
            goal=goal,
            scope=list(scope or []),
            acceptance_checks=list(acceptance_checks or []),
            done_definition=list(done_definition or []),
            proposed_by=proposed_by,
            approved=approved,
        )
        _reset_sprint_loop_state(state)
        state.active_sprint_contract = contract
        state.planned_sprint_contracts = [
            item for item in state.planned_sprint_contracts if item.sprint_id != sprint_id
        ]
        state.sprint_history = [item for item in state.sprint_history if item.sprint_id != sprint_id]
        state.sprint_history.append(contract)
        if state.product_spec is not None and sprint_id not in state.product_spec.sprint_ids:
            state.product_spec = replace(
                state.product_spec,
                sprint_ids=[*state.product_spec.sprint_ids, sprint_id],
            )
        state.loop_status = "in_sprint"
        return self.app_state_summary(session)

    def record_sprint_evaluation(
        self,
        session: SessionState,
        *,
        sprint_id: str,
        status: str = "",
        summary: str = "",
        criteria_scores: dict[str, float] | None = None,
        blocker_notes: list[str] | None = None,
        evaluator_mode: str = "",
        passing_criteria: list[str] | None = None,
        failing_criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        blockers = list(blocker_notes or [])
        explicit_scores = dict(criteria_scores or {})
        contract = _active_sprint_for_update(state, sprint_id)
        if contract is None:
            return self.app_state_summary(session)
        execution_attempt = (
            state.latest_execution_attempt
            if state.latest_execution_attempt and state.latest_execution_attempt.sprint_id == sprint_id
            else None
        )
        previous_execution_gate = str(_derive_execution_outcome_projection(execution_attempt).get("execution_gate") or "")
        execution_summary = execution_attempt.execution_summary if execution_attempt else ""
        changed_target_hints = execution_attempt.changed_target_hints if execution_attempt else []
        execution_success: bool | None = None
        if execution_attempt is not None and execution_attempt.status not in {"", "recorded"}:
            execution_success = execution_attempt.success
        resolved_scores = _derive_criteria_scores(
            list(state.evaluator_criteria),
            explicit_scores=explicit_scores,
            contract=contract,
            summary=summary,
            blocker_notes=blockers,
            requested_status=status,
            execution_summary=execution_summary,
            changed_target_hints=changed_target_hints,
            execution_success=execution_success,
        )
        resolved_passing, resolved_failing = _classify_criteria(
            list(state.evaluator_criteria),
            scores=resolved_scores,
        )
        allowed_names = {criterion.name for criterion in state.evaluator_criteria}
        normalized_passing = _normalize_criteria_names(passing_criteria, allowed_names=allowed_names)
        normalized_failing = _normalize_criteria_names(failing_criteria, allowed_names=allowed_names)
        if normalized_passing or normalized_failing:
            resolved_passing = normalized_passing or [name for name in resolved_passing if name not in normalized_failing]
            resolved_failing = normalized_failing or [name for name in resolved_failing if name not in normalized_passing]
        resolved_status = _derive_evaluation_status(
            status,
            blocker_notes=blockers,
            failing_criteria=resolved_failing,
        )
        resolved_summary = _derive_evaluation_summary(
            summary,
            contract=contract,
            status=resolved_status,
            passing_criteria=resolved_passing,
            failing_criteria=resolved_failing,
            blocker_notes=blockers,
            execution_summary=execution_summary,
            changed_target_hints=changed_target_hints,
        )
        evaluation = SprintEvaluation(
            sprint_id=sprint_id,
            status=resolved_status,
            summary=resolved_summary,
            evaluator_mode=(evaluator_mode or "contract_driven").strip() or "contract_driven",
            criteria_scores=resolved_scores,
            passing_criteria=resolved_passing,
            failing_criteria=resolved_failing,
            blocker_notes=blockers,
        )
        state.latest_sprint_evaluation = evaluation
        if execution_attempt is not None and execution_attempt.attempt_id:
            self.apply_execution_outcome(
                session,
                attempt_id=execution_attempt.attempt_id,
                status=f"qa_{resolved_status}",
                success=resolved_status == "passed",
            )
        if state.latest_revision is not None and state.latest_revision.sprint_id == sprint_id:
            self.compare_revision_outcome(
                session,
                sprint_id=sprint_id,
                evaluation=evaluation,
            )
        policy = _derive_post_revision_policy(state)
        _record_execution_gate_transition(
            state,
            previous_gate=previous_execution_gate,
            current_gate=str(policy.get("execution_gate") or ""),
            action=f"qa:{resolved_status}",
        )
        state.loop_status = str(
            policy.get("loop_status")
            or ("ready_for_next_sprint" if resolved_status == "passed" else "needs_revision")
        )
        return self.app_state_summary(session)

    def negotiate_sprint(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        evaluator_objections: list[str] | None = None,
        planner_mode: str = "",
        planner_response: list[str] | None = None,
        recommended_action: str = "",
        sprint_negotiation_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        sprint = _active_sprint_for_update(state, sprint_id)
        if sprint is None:
            return self.app_state_summary(session)
        round_summary = _derive_negotiation_round(
            sprint=sprint,
            evaluation=(
                state.latest_sprint_evaluation
                if state.latest_sprint_evaluation and state.latest_sprint_evaluation.sprint_id == sprint.sprint_id
                else None
            ),
            planned_sprints=list(state.planned_sprint_contracts),
            explicit_objections=evaluator_objections,
        )
        normalized_response = [
            str(item).strip() for item in (planner_response or []) if str(item).strip()
        ]
        normalized_action = _normalize_recommended_action(recommended_action)
        normalized_notes = [
            str(item).strip() for item in (sprint_negotiation_notes or []) if str(item).strip()
        ]
        if planner_mode.strip():
            round_summary.planner_mode = planner_mode.strip()
        if normalized_response:
            round_summary.planner_response = normalized_response[:4]
        if normalized_action:
            round_summary.recommended_action = normalized_action
        state.latest_negotiation_round = round_summary
        state.negotiation_history = [
            item for item in state.negotiation_history if item.sprint_id != round_summary.sprint_id
        ]
        state.negotiation_history.append(round_summary)
        state.sprint_negotiation_notes = normalized_notes[:4] if normalized_notes else list(round_summary.planner_response)
        state.loop_status = "negotiation_pending" if round_summary.recommended_action == "revise_current_sprint" else "ready_for_next_sprint"
        return self.app_state_summary(session)

    def derive_sprint_revision(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        planner_mode: str = "",
        revision_summary: str = "",
        must_fix: list[str] | None = None,
        must_keep: list[str] | None = None,
        explicit_notes: list[str] | None = None,
        merge_with_derived: bool = True,
    ) -> SprintRevision | None:
        state = _ensure_app_harness_state(session)
        sprint = _active_sprint_for_update(state, sprint_id)
        if sprint is None:
            return None
        negotiation = state.latest_negotiation_round
        evaluation = state.latest_sprint_evaluation
        if negotiation and negotiation.sprint_id != sprint.sprint_id:
            negotiation = None
        if evaluation and evaluation.sprint_id != sprint.sprint_id:
            evaluation = None
        explicit_fix = _dedup_text_items(list(must_fix or []))
        derived_fix: list[str] = []
        if negotiation:
            derived_fix.extend(negotiation.objections)
        if evaluation:
            if not negotiation or not negotiation.objections:
                derived_fix.extend([f"Recover failing criterion: {item}." for item in evaluation.failing_criteria])
            derived_fix.extend(evaluation.blocker_notes)
        if merge_with_derived:
            combined_fix = _dedup_text_items(explicit_fix + derived_fix)[:4]
        else:
            combined_fix = explicit_fix[:4] or _dedup_text_items(derived_fix)[:4]
        explicit_keep = _dedup_text_items(list(must_keep or []))
        derived_keep = _dedup_text_items(
            list(sprint.acceptance_checks[:2])
            + list(sprint.done_definition[:2])
            + (evaluation.passing_criteria[:2] if evaluation else [])
        )
        if merge_with_derived:
            combined_keep = _dedup_text_items(explicit_keep + derived_keep)[:4]
        else:
            combined_keep = explicit_keep[:4] or _dedup_text_items(derived_keep)[:4]
        operator_notes = _dedup_text_items(list(explicit_notes or []))
        combined_summary = revision_summary.strip()
        if not combined_summary:
            if negotiation and negotiation.planner_response:
                combined_summary = negotiation.planner_response[0]
            else:
                combined_summary = f"Revise {sprint.sprint_id} around the current evaluator objections."
        revision_id = f"{sprint.sprint_id}-revision-{state.retry_count + 1}"
        return SprintRevision(
            revision_id=revision_id,
            sprint_id=sprint.sprint_id,
            planner_mode=(planner_mode or (negotiation.planner_mode if negotiation else state.planner_mode) or "deterministic").strip() or "deterministic",
            source_negotiation_action=(
                negotiation.recommended_action if negotiation else "revise_current_sprint"
            ),
            must_fix=combined_fix,
            must_keep=combined_keep,
            revision_summary=combined_summary,
            revision_diff_summary=_derive_revision_diff_summary(
                must_fix=combined_fix,
                must_keep=combined_keep,
                explicit_notes=operator_notes,
            ),
            baseline_status=evaluation.status if evaluation else "",
            baseline_failing_criteria=(evaluation.failing_criteria[:4] if evaluation else []),
            improvement_status="pending",
        )

    def apply_revision_attempt(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        planner_mode: str = "",
        revision_summary: str = "",
        must_fix: list[str] | None = None,
        must_keep: list[str] | None = None,
        explicit_notes: list[str] | None = None,
        merge_with_derived: bool = True,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        if state.retry_budget <= 0:
            state.retry_budget = 1
        if state.retry_count >= state.retry_budget:
            state.loop_status = "retry_budget_exhausted"
            return self.app_state_summary(session)
        revision = self.derive_sprint_revision(
            session,
            sprint_id=sprint_id,
            planner_mode=planner_mode,
            revision_summary=revision_summary,
            must_fix=must_fix,
            must_keep=must_keep,
            explicit_notes=explicit_notes,
            merge_with_derived=merge_with_derived,
        )
        if revision is None:
            return self.app_state_summary(session)
        state.latest_revision = revision
        state.revision_history = [
            item for item in state.revision_history if item.revision_id != revision.revision_id
        ]
        state.revision_history.append(revision)
        state.retry_count += 1
        state.loop_status = "revision_recorded"
        return self.app_state_summary(session)

    def advance_to_next_sprint(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        policy = _derive_post_revision_policy(state)
        current_sprint_id = state.active_sprint_contract.sprint_id if state.active_sprint_contract else ""
        latest_execution_attempt = _latest_execution_attempt_for_sprint(state, sprint_id=current_sprint_id)
        candidate_id = sprint_id.strip() or str(policy.get("next_sprint_candidate_id") or "").strip()
        if latest_execution_attempt is not None and (
            latest_execution_attempt.status != "qa_passed" or latest_execution_attempt.success is not True
        ):
            state.loop_status = "execution_recorded"
            return self.app_state_summary(session)
        if not candidate_id or not bool(policy.get("next_sprint_ready")):
            return self.app_state_summary(session)
        next_sprint = next((item for item in state.planned_sprint_contracts if item.sprint_id == candidate_id), None)
        if next_sprint is None:
            return self.app_state_summary(session)
        previous_gate = str(policy.get("execution_gate") or "")
        _reset_sprint_loop_state(state)
        state.active_sprint_contract = next_sprint
        state.planned_sprint_contracts = [
            item for item in state.planned_sprint_contracts if item.sprint_id != candidate_id
        ]
        state.sprint_history = [item for item in state.sprint_history if item.sprint_id != candidate_id]
        state.sprint_history.append(next_sprint)
        _record_execution_gate_transition(
            state,
            previous_gate=previous_gate,
            current_gate="no_execution",
            action="advance",
        )
        state.loop_status = "in_sprint"
        return self.app_state_summary(session)

    def escalate_current_sprint(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        sprint = state.active_sprint_contract
        if sprint is None:
            return self.app_state_summary(session)
        if sprint_id and sprint.sprint_id != sprint_id:
            return self.app_state_summary(session)
        note_text = note.strip() or "Retry budget exhausted; escalate or replan before continuing."
        existing = [item for item in state.sprint_negotiation_notes if item.strip()]
        if note_text not in existing:
            existing.append(note_text)
        state.sprint_negotiation_notes = existing[:4]
        current_gate = str(_derive_post_revision_policy(state).get("execution_gate") or "")
        _record_execution_gate_transition(
            state,
            previous_gate=current_gate,
            current_gate=current_gate,
            action="escalate",
        )
        state.loop_status = "escalated"
        return self.app_state_summary(session)

    def replan_current_sprint(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        note: str = "",
        planner_mode: str = "",
        goal: str = "",
        scope: list[str] | None = None,
        acceptance_checks: list[str] | None = None,
        done_definition: list[str] | None = None,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        sprint = state.active_sprint_contract
        if sprint is None:
            return self.app_state_summary(session)
        if sprint_id and sprint.sprint_id != sprint_id:
            return self.app_state_summary(session)
        if state.loop_status not in {"escalated", "retry_budget_exhausted"}:
            return self.app_state_summary(session)

        new_sprint_id = _next_replanned_sprint_id(state, sprint.sprint_id)
        revision = state.latest_revision
        latest_execution_attempt = _latest_execution_attempt_for_sprint(state, sprint_id=sprint.sprint_id)
        failing = state.latest_sprint_evaluation.failing_criteria[:2] if state.latest_sprint_evaluation else []
        derived_scope = _dedup_text_items(
            (revision.must_fix[:2] if revision else [])
            + (latest_execution_attempt.changed_target_hints[:2] if latest_execution_attempt else [])
            + [f"recover {item}" for item in failing]
            + sprint.scope[:2]
        )[:3]
        derived_done_definition = _dedup_text_items(
            sprint.done_definition[:2]
            + ([f"stabilize latest execution path: {latest_execution_attempt.execution_summary}"] if latest_execution_attempt and latest_execution_attempt.execution_summary else [])
            + [f"resolve {item}" for item in failing]
        )[:3]
        replanned_goal = goal.strip() or note.strip() or (
            f"Replanned {sprint.goal}".strip()
            if sprint.goal
            else f"Replanned {sprint.sprint_id} scope."
        )
        replanned = SprintContract(
            sprint_id=new_sprint_id,
            goal=replanned_goal,
            scope=_dedup_text_items(list(scope or []) or derived_scope)[:3],
            acceptance_checks=_dedup_text_items(list(acceptance_checks or []) or list(sprint.acceptance_checks))[:2],
            done_definition=_dedup_text_items(list(done_definition or []) or derived_done_definition)[:3],
            proposed_by=(planner_mode or state.planner_mode or "deterministic").strip() or "deterministic",
            approved=False,
        )
        state.active_sprint_contract = replanned
        state.sprint_history = [item for item in state.sprint_history if item.sprint_id != replanned.sprint_id]
        state.sprint_history.append(replanned)
        if state.product_spec is not None and replanned.sprint_id not in state.product_spec.sprint_ids:
            state.product_spec = replace(
                state.product_spec,
                sprint_ids=[*state.product_spec.sprint_ids, replanned.sprint_id],
            )
        replan_note = note.strip() or "Replanned after escalation to narrow scope and re-run the current sprint."
        if latest_execution_attempt and latest_execution_attempt.execution_summary:
            replan_note = f"{replan_note} Previous execution outcome: {latest_execution_attempt.execution_summary}"
        state.sprint_negotiation_notes = _dedup_text_items(
            [replan_note] + state.sprint_negotiation_notes[:3]
        )[:4]
        previous_gate = str(_derive_post_revision_policy(state).get("execution_gate") or "")
        _reset_sprint_loop_state(state)
        _record_execution_gate_transition(
            state,
            previous_gate=previous_gate,
            current_gate="no_execution",
            action="replan",
        )
        state.loop_status = "sprint_replanned"
        return self.app_state_summary(session)

    def derive_execution_attempt(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        execution_mode: str = "",
        execution_summary: str = "",
        changed_target_hints: list[str] | None = None,
        changed_files: list[str] | None = None,
        artifact_root: str = "",
        artifact_kind: str = "",
        artifact_path: str = "",
        preview_command: str = "",
        trace_path: str = "",
        validation_command: str = "",
        validation_summary: str = "",
        failure_reason: str = "",
        status: str = "",
        success: bool | None = None,
    ) -> SprintExecutionAttempt | None:
        state = _ensure_app_harness_state(session)
        sprint = _active_sprint_for_update(state, sprint_id)
        if sprint is None:
            return None
        revision = state.latest_revision if state.latest_revision and state.latest_revision.sprint_id == sprint.sprint_id else None
        target_kind = "revision" if revision is not None else "sprint"
        explicit_hints = _dedup_text_items(list(changed_target_hints or []))
        derived_hints = _dedup_text_items(
            (revision.must_fix[:2] if revision else [])
            + sprint.scope[:2]
            + sprint.acceptance_checks[:1]
        )
        attempt_hints = (explicit_hints or derived_hints)[:4]
        attempt_index = len(state.execution_history) + 1
        return SprintExecutionAttempt(
            attempt_id=f"{sprint.sprint_id}-attempt-{attempt_index}",
            sprint_id=sprint.sprint_id,
            revision_id=revision.revision_id if revision is not None else "",
            execution_target_kind=target_kind,
            execution_mode=(execution_mode or "deterministic").strip() or "deterministic",
            changed_target_hints=attempt_hints,
            changed_files=_dedup_text_items(list(changed_files or []))[:8],
            execution_summary=_derive_execution_summary(
                sprint=sprint,
                revision=revision,
                explicit_summary=execution_summary,
                changed_target_hints=attempt_hints,
            ),
            artifact_root=artifact_root.strip(),
            artifact_kind=artifact_kind.strip(),
            artifact_path=artifact_path.strip(),
            preview_command=preview_command.strip(),
            trace_path=trace_path.strip(),
            validation_command=validation_command.strip(),
            validation_summary=validation_summary.strip(),
            failure_reason=failure_reason.strip(),
            status=status.strip() or "recorded",
            success=False if success is None else success,
        )

    def record_execution_attempt(
        self,
        session: SessionState,
        *,
        sprint_id: str = "",
        execution_mode: str = "",
        execution_summary: str = "",
        changed_target_hints: list[str] | None = None,
        changed_files: list[str] | None = None,
        artifact_root: str = "",
        artifact_kind: str = "",
        artifact_path: str = "",
        preview_command: str = "",
        trace_path: str = "",
        validation_command: str = "",
        validation_summary: str = "",
        failure_reason: str = "",
        status: str = "",
        success: bool | None = None,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        attempt = self.derive_execution_attempt(
            session,
            sprint_id=sprint_id,
            execution_mode=execution_mode,
            execution_summary=execution_summary,
            changed_target_hints=changed_target_hints,
            changed_files=changed_files,
            artifact_root=artifact_root,
            artifact_kind=artifact_kind,
            artifact_path=artifact_path,
            preview_command=preview_command,
            trace_path=trace_path,
            validation_command=validation_command,
            validation_summary=validation_summary,
            failure_reason=failure_reason,
            status=status,
            success=success,
        )
        if attempt is None:
            return self.app_state_summary(session)
        previous_gate = str(_derive_post_revision_policy(state).get("execution_gate") or "")
        attempt = _attach_execution_artifact(session, state=state, attempt=attempt)
        state.latest_execution_attempt = attempt
        state.execution_history = [item for item in state.execution_history if item.attempt_id != attempt.attempt_id]
        state.execution_history.append(attempt)
        _record_execution_gate_transition(
            state,
            previous_gate=previous_gate,
            current_gate=str(_derive_execution_outcome_projection(attempt).get("execution_gate") or ""),
            action=f"generate:{attempt.execution_mode}",
        )
        state.loop_status = "execution_recorded"
        return self.app_state_summary(session)

    def apply_execution_outcome(
        self,
        session: SessionState,
        *,
        attempt_id: str,
        status: str = "",
        success: bool | None = None,
        execution_summary: str = "",
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        attempt = state.latest_execution_attempt
        if attempt is None or attempt.attempt_id != attempt_id:
            return self.app_state_summary(session)
        normalized_status = status.strip() or attempt.status or "recorded"
        updated = replace(
            attempt,
            status=normalized_status,
            success=attempt.success if success is None else success,
            execution_summary=execution_summary.strip() or attempt.execution_summary,
        )
        state.latest_execution_attempt = updated
        state.execution_history = [
            updated if item.attempt_id == updated.attempt_id else item
            for item in state.execution_history
        ]
        return self.app_state_summary(session)

    def compare_revision_outcome(
        self,
        session: SessionState,
        *,
        sprint_id: str,
        evaluation: SprintEvaluation,
    ) -> dict[str, Any]:
        state = _ensure_app_harness_state(session)
        revision = state.latest_revision
        if revision is None or revision.sprint_id != sprint_id:
            return self.app_state_summary(session)
        revision.outcome_status = evaluation.status
        revision.outcome_failing_criteria = list(evaluation.failing_criteria[:4])
        revision.outcome_summary = evaluation.summary
        revision.improvement_status = _derive_revision_improvement_status(
            baseline_status=revision.baseline_status,
            baseline_failing=revision.baseline_failing_criteria,
            outcome_status=revision.outcome_status,
            outcome_failing=revision.outcome_failing_criteria,
        )
        state.latest_revision = revision
        state.revision_history = [
            revision if item.revision_id == revision.revision_id else item
            for item in state.revision_history
        ]
        policy = _derive_post_revision_policy(state)
        state.loop_status = str(policy.get("loop_status") or state.loop_status)
        return self.app_state_summary(session)

    def app_state_summary(self, session: SessionState) -> dict[str, Any]:
        state = session.app_harness_state
        if state is None:
            return {
                "status": "empty",
                "product_spec": None,
                "planner_mode": "deterministic",
                "active_sprint_contract": None,
                "planned_sprint_contracts": [],
                "planning_rationale": [],
                "sprint_negotiation_notes": [],
                "latest_negotiation_round": None,
                "negotiation_history_count": 0,
                "latest_sprint_evaluation": None,
                "loop_status": "",
                "evaluator_criteria_count": 0,
            }
        product = state.product_spec
        sprint = state.active_sprint_contract
        sprint_id = sprint.sprint_id if sprint else ""
        evaluation = (
            state.latest_sprint_evaluation
            if state.latest_sprint_evaluation and state.latest_sprint_evaluation.sprint_id == sprint_id
            else None
        )
        latest_negotiation_round = (
            state.latest_negotiation_round
            if state.latest_negotiation_round and state.latest_negotiation_round.sprint_id == sprint_id
            else None
        )
        latest_revision = (
            state.latest_revision
            if state.latest_revision and state.latest_revision.sprint_id == sprint_id
            else None
        )
        latest_execution_attempt = (
            state.latest_execution_attempt
            if state.latest_execution_attempt and state.latest_execution_attempt.sprint_id == sprint_id
            else None
        )
        replan_depth = _replan_depth(sprint_id)
        replan_root_sprint_id = _replan_root_sprint_id(sprint_id)
        policy_stage = _derive_policy_stage(sprint_id)
        current_sprint_execution_count = sum(
            1
            for item in state.execution_history
            if isinstance(item.sprint_id, str) and item.sprint_id == sprint_id
        )
        policy = _derive_post_revision_policy(state)
        return {
            "status": "ready",
            "product_spec": {
                "title": product.title if product else "",
                "prompt": product.prompt if product else "",
                "app_type": product.app_type if product else "",
                "feature_count": len(product.features) if product else 0,
                "feature_groups": list((product.feature_groups or {}).keys())[:4] if product else [],
                "stack": product.stack[:4] if product else [],
                "sprint_ids": product.sprint_ids[:6] if product else [],
            },
            "planner_mode": state.planner_mode or "deterministic",
            "active_sprint_contract": {
                "sprint_id": sprint.sprint_id if sprint else "",
                "goal": sprint.goal if sprint else "",
                "scope": sprint.scope[:4] if sprint else [],
                "acceptance_checks": sprint.acceptance_checks[:3] if sprint else [],
                "done_definition": sprint.done_definition[:3] if sprint else [],
                "proposed_by": sprint.proposed_by if sprint else "",
                "approved": sprint.approved if sprint else False,
            },
            "planned_sprint_contracts": [
                {
                    "sprint_id": item.sprint_id,
                    "goal": item.goal,
                    "scope": item.scope[:4],
                    "proposed_by": item.proposed_by,
                    "approved": item.approved,
                }
                for item in state.planned_sprint_contracts[:3]
            ],
            "planning_rationale": state.planning_rationale[:4],
            "sprint_negotiation_notes": state.sprint_negotiation_notes[:4],
            "latest_negotiation_round": {
                "sprint_id": latest_negotiation_round.sprint_id if latest_negotiation_round else "",
                "planner_mode": latest_negotiation_round.planner_mode if latest_negotiation_round else "",
                "evaluator_mode": latest_negotiation_round.evaluator_mode if latest_negotiation_round else "",
                "evaluator_status": latest_negotiation_round.evaluator_status if latest_negotiation_round else "",
                "objections": latest_negotiation_round.objections[:4] if latest_negotiation_round else [],
                "planner_response": latest_negotiation_round.planner_response[:4] if latest_negotiation_round else [],
                "recommended_action": latest_negotiation_round.recommended_action if latest_negotiation_round else "",
            },
            "negotiation_history_count": len(state.negotiation_history),
            "latest_revision": {
                "revision_id": latest_revision.revision_id if latest_revision else "",
                "sprint_id": latest_revision.sprint_id if latest_revision else "",
                "planner_mode": latest_revision.planner_mode if latest_revision else "",
                "source_negotiation_action": latest_revision.source_negotiation_action if latest_revision else "",
                "must_fix": latest_revision.must_fix[:4] if latest_revision else [],
                "must_keep": latest_revision.must_keep[:4] if latest_revision else [],
                "revision_summary": latest_revision.revision_summary if latest_revision else "",
                "revision_diff_summary": latest_revision.revision_diff_summary[:3] if latest_revision else [],
                "baseline_status": latest_revision.baseline_status if latest_revision else "",
                "baseline_failing_criteria": latest_revision.baseline_failing_criteria[:4] if latest_revision else [],
                "outcome_status": latest_revision.outcome_status if latest_revision else "",
                "outcome_failing_criteria": latest_revision.outcome_failing_criteria[:4] if latest_revision else [],
                "outcome_summary": latest_revision.outcome_summary if latest_revision else "",
                "improvement_status": latest_revision.improvement_status if latest_revision else "",
            },
            "revision_history_count": len(state.revision_history),
            "latest_execution_attempt": {
                "attempt_id": latest_execution_attempt.attempt_id if latest_execution_attempt else "",
                "sprint_id": latest_execution_attempt.sprint_id if latest_execution_attempt else "",
                "revision_id": latest_execution_attempt.revision_id if latest_execution_attempt else "",
                "execution_target_kind": latest_execution_attempt.execution_target_kind if latest_execution_attempt else "",
                "execution_mode": latest_execution_attempt.execution_mode if latest_execution_attempt else "",
                "changed_target_hints": latest_execution_attempt.changed_target_hints[:4] if latest_execution_attempt else [],
                "changed_files": latest_execution_attempt.changed_files[:8] if latest_execution_attempt else [],
                "execution_summary": latest_execution_attempt.execution_summary if latest_execution_attempt else "",
                "artifact_root": latest_execution_attempt.artifact_root if latest_execution_attempt else "",
                "artifact_kind": latest_execution_attempt.artifact_kind if latest_execution_attempt else "",
                "artifact_path": latest_execution_attempt.artifact_path if latest_execution_attempt else "",
                "preview_command": latest_execution_attempt.preview_command if latest_execution_attempt else "",
                "trace_path": latest_execution_attempt.trace_path if latest_execution_attempt else "",
                "validation_command": latest_execution_attempt.validation_command if latest_execution_attempt else "",
                "validation_summary": latest_execution_attempt.validation_summary if latest_execution_attempt else "",
                "failure_reason": latest_execution_attempt.failure_reason if latest_execution_attempt else "",
                "status": latest_execution_attempt.status if latest_execution_attempt else "",
                "success": latest_execution_attempt.success if latest_execution_attempt else False,
            },
            "execution_history_count": len(state.execution_history),
            "current_sprint_execution_count": current_sprint_execution_count,
            "policy_stage": policy_stage,
            "replan_depth": replan_depth,
            "replan_root_sprint_id": replan_root_sprint_id,
            "retry_budget": state.retry_budget,
            "retry_count": state.retry_count,
            "last_execution_gate_from": state.last_execution_gate_from,
            "last_execution_gate_to": state.last_execution_gate_to,
            "last_execution_gate_transition": state.last_execution_gate_transition,
            "last_policy_action": state.last_policy_action,
            "execution_outcome_ready": bool(policy.get("execution_outcome_ready")),
            "execution_gate": str(policy.get("execution_gate") or ""),
            "execution_focus": str(policy.get("execution_focus") or ""),
            "retry_available": bool(policy.get("retry_available")),
            "retry_remaining": int(policy.get("retry_remaining") or 0),
            "next_sprint_ready": bool(policy.get("next_sprint_ready")),
            "next_sprint_candidate_id": str(policy.get("next_sprint_candidate_id") or ""),
            "recommended_next_action": str(policy.get("recommended_next_action") or ""),
            "latest_sprint_evaluation": {
                "sprint_id": evaluation.sprint_id if evaluation else "",
                "status": evaluation.status if evaluation else "",
                "summary": evaluation.summary if evaluation else "",
                "evaluator_mode": evaluation.evaluator_mode if evaluation else "",
                "passing_criteria": evaluation.passing_criteria[:4] if evaluation else [],
                "failing_criteria": evaluation.failing_criteria[:4] if evaluation else [],
                "criteria_scores": dict(evaluation.criteria_scores) if evaluation else {},
                "blocker_notes": evaluation.blocker_notes[:4] if evaluation else [],
            },
            "loop_status": state.loop_status,
            "evaluator_criteria_count": len(state.evaluator_criteria),
        }
