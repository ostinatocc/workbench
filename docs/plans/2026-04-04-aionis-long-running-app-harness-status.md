# Aionis Long-Running App Harness Status

Last updated: 2026-04-04

## Summary

Phase 1 is now active and usable.

Workbench can already persist and inspect the minimum harness objects needed for a later planner/generator/evaluator loop:

- `ProductSpec`
- `SprintContract`
- `EvaluatorCriterion`
- `SprintEvaluation`
- `AppHarnessState`

This is not yet a full autonomous app-builder harness. It is the contract and operator layer that makes one possible on top of the existing Workbench platform.

Phase 2 has also started in a narrow way: `app plan` can now derive a usable `ProductSpec`, feature grouping, feature rationale, planning rationale, sprint negotiation notes, default evaluator criteria, a default product direction, an initial unapproved `sprint-1` proposal, and a follow-up `sprint-2` proposal from a prompt-only request. It also now supports an opt-in live planner slice via `--use-live-planner`, but that live path is intentionally a live-assisted first step: the model only proposes a compact title/design-direction/rationale/sprint-1 payload, and deterministic planning still fills the rest of the contract. `app qa` has also grown into a first contract-driven evaluator slice: it can now treat `--status auto` as a real evaluator path, score missing criteria against the current sprint contract, and persist `evaluator_mode`, passing criteria, and failing criteria into the harness state. `app negotiate` now closes the first narrow planner/evaluator loop by turning the latest evaluator result into structured objections, planner responses, and a recommended action for the current sprint, and it now has an opt-in live planner revision slice via `--use-live-planner`. `app retry` now turns that negotiation result into one bounded revision artifact with `latest_revision`, `retry_count`, `retry_budget`, and an opt-in live revision planner slice. `app generate` now adds the first bounded generator execution slice: it records one compact execution attempt against either the active sprint or the latest revision, persists a stable execution summary plus changed-target hints, and supports an opt-in live generator slice via `--use-live-generator`. `app qa` now also consumes the latest execution attempt context, so both deterministic and live evaluator paths can explicitly judge the most recent bounded implementation attempt instead of evaluating the sprint in isolation, and the latest execution attempt now has a real lifecycle: it starts as `recorded` and is then back-written to `qa_passed` or `qa_failed` when evaluator results land.

That generator/evaluator seam is now tighter than a generic "latest attempt" reference. Workbench derives a compact `execution_focus` from the most recent bounded implementation attempt and now feeds that signal into the live planner, live generator, and live evaluator slices. The app harness canonical view also surfaces `policy_stage`, `execution_gate`, `execution_outcome_ready`, and `execution_focus`, so second-cycle replan behavior is inspectable without reconstructing the state machine from raw sprint ids.

## Implemented

### Data and persistence

- app harness models exist in [app_harness_models.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_models.py)
- session persistence exists in [session.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py)
- app harness state survives save/load round-trips

### Deterministic service layer

- [app_harness_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py) now provides:
  - `plan_app(...)`
  - `set_sprint_contract(...)`
  - `record_sprint_evaluation(...)`
  - `app_state_summary(...)`
- prompt-only `plan_app(...)` now infers:
  - `title`
  - `app_type`
  - `stack`
  - `features`
  - `feature_groups`
  - `feature_rationale`
  - `planning_rationale`
  - `sprint_negotiation_notes`
  - `design_direction`
  - default evaluator criteria
  - initial `sprint-1` proposal
  - follow-up `sprint-2` proposal

### Runtime and canonical views

- [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py) exposes:
  - `app_show(...)`
  - `app_plan(...)`
  - `app_sprint(...)`
  - `app_qa(...)`
  - `app_negotiate(...)`
  - `app_generate(...)`
  - `app_retry(...)`
- [evaluation_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py) exposes `canonical_views.app_harness`

### Operator surfaces

Interactive shell:

- `/app show [TASK_ID]`
- `/app plan [TASK_ID] --prompt ...`
- `/app sprint [TASK_ID] --sprint-id ... --goal ...`
- `/app negotiate [TASK_ID] [--sprint-id ...] [--objection ...] [--live]`
- `/app generate [TASK_ID] [--sprint-id ...] [--summary ...] [--target ...] [--live]`
- `/app retry [TASK_ID] [--sprint-id ...] [--revision-note ...] [--live]`
- `/app advance [TASK_ID] [--sprint-id ...]`
- `/app replan [TASK_ID] [--sprint-id ...] [--note ...]`
- `/app escalate [TASK_ID] [--sprint-id ...] [--note ...]`
- `/app qa [TASK_ID] --sprint-id ... [--status passed|failed|auto]`

Non-interactive CLI:

- `aionis app show --task-id ...`
- `aionis app plan --task-id ... --prompt ...`
- `aionis app plan --task-id ... --prompt ... --use-live-planner`
- `aionis app sprint --task-id ... --sprint-id ... --goal ...`
- `aionis app negotiate --task-id ... [--sprint-id ...] [--objection ...]`
- `aionis app negotiate --task-id ... [--sprint-id ...] [--objection ...] --use-live-planner`
- `aionis app generate --task-id ... [--sprint-id ...] [--summary ...] [--target ...]`
- `aionis app generate --task-id ... [--sprint-id ...] [--summary ...] [--target ...] --use-live-generator`
- `aionis app retry --task-id ... [--sprint-id ...] [--revision-note ...]`
- `aionis app retry --task-id ... [--sprint-id ...] [--revision-note ...] --use-live-planner`
- `aionis app advance --task-id ... [--sprint-id ...]`
- `aionis app replan --task-id ... [--sprint-id ...] [--note ...]`
- `aionis app escalate --task-id ... [--sprint-id ...] [--note ...]`
- `aionis app qa --task-id ... --sprint-id ... [--status passed|failed|auto]`

### Real scenario coverage

The first real deterministic app-harness scenario now exists:

- [test_app_harness_planner_contract.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py)

It exercises:

1. real pinned repo checkout
2. real `aionis ingest`
3. real prompt-only `aionis app plan`
4. real `aionis app sprint`
5. real `aionis app qa`
6. real `aionis app negotiate`
7. real `app retry`
8. real `app generate`
9. real `inspect_session()` verification

That deterministic app-harness scenario now also verifies the first evaluator slice:

- `app qa` can run with `status=auto`
- the harness persists `latest_sprint_evaluation.evaluator_mode=contract_driven`
- the harness persists contract-derived failing criteria
- `app negotiate` persists a structured recommended action and negotiation objections
- `app generate` persists `latest_execution_attempt` with execution mode, execution target kind, and a compact execution summary
- `app qa` consumes `latest_execution_attempt` so summary derivation and live evaluator inputs can explicitly reflect the most recent bounded execution pass
- `latest_execution_attempt` now has an outcome lifecycle (`recorded -> qa_passed|qa_failed`) instead of staying as a write-only generator artifact

There is now also a first real-live-e2e planner slice:

- `tests_real_live_e2e/test_live_app_plan.py`

It verifies:

1. real live-ready environment
2. real `aionis app plan --use-live-planner`
3. persisted `planner_mode=live`
4. persisted live-produced `sprint-1` proposal and planning rationale
5. deterministic follow-up planning still fills `feature_groups`, negotiation notes, and `sprint-2`

The first credentialed live reference pass has now been captured on the
`zai_glm51_coding` profile (`GLM-5.1` via the Z.AI coding endpoint):

- `1 passed in 69.54s` for `tests_real_live_e2e/test_live_app_plan.py`
- `1 passed in 65.48s` for `tests_real_live_e2e/test_live_app_qa.py`

There is now also a first live generator harness entry:

- `tests_real_live_e2e/test_live_app_generate.py`

It verifies:

1. real live-ready environment
2. real `aionis app generate --use-live-generator`
3. persisted `latest_execution_attempt.execution_mode=live`
4. persisted live-produced `execution_summary`
5. persisted live-produced changed-target hints

There is now also a live negotiation harness entry:

- `tests_real_live_e2e/test_live_app_negotiate.py`

It verifies:

1. real live-ready environment
2. real `aionis app qa --use-live-evaluator`
3. real `aionis app negotiate --use-live-planner`
4. persisted `latest_negotiation_round.planner_mode=live`
5. persisted live planner response and negotiation notes

There is now also a live bounded revision harness entry:

- `tests_real_live_e2e/test_live_app_retry.py`

It verifies:

1. real live-ready environment
2. real `aionis app qa --use-live-evaluator`
3. real `aionis app negotiate --use-live-planner`
4. real `aionis app retry --use-live-planner`
5. persisted `latest_revision.planner_mode=live`
6. persisted live `must_fix` and `must_keep` revision targets
7. persisted bounded retry state (`retry_count=1`, `retry_budget=1`)

There is now also a live retry-comparison harness entry:

- `tests_real_live_e2e/test_live_app_retry_compare.py`

It verifies:

1. real live-ready environment
2. real `aionis app qa --use-live-evaluator`
3. real `aionis app negotiate --use-live-planner`
4. real `aionis app retry --use-live-planner`
5. real post-retry `aionis app qa --use-live-evaluator`
6. persisted revision baseline/outcome comparison fields
7. terminal `improvement_status` and settled loop status after the re-check

The first credentialed live reference pass for that narrow comparison loop has now
also been captured on the `zai_glm51_coding` profile:

- `1 passed in 140.88s` for `tests_real_live_e2e/test_live_app_retry_compare.py`

There are now also explicit live policy-ending harness entries:

- `tests_real_live_e2e/test_live_app_advance.py`
- `tests_real_live_e2e/test_live_app_escalate.py`

They verify:

1. a live retry-comparison loop can end in an explicit `advance` action that activates `sprint-2`
2. a live failed retry path can end in an explicit `escalate` action that marks the loop `escalated`

The first credentialed live reference pass for those explicit policy-ending paths has
also now been captured on the `zai_glm51_coding` profile:

- `2 passed in 287.05s (0:04:47)` for
  `tests_real_live_e2e/test_live_app_advance.py` and
  `tests_real_live_e2e/test_live_app_escalate.py`

Those first-cycle live endings now also persist compact pre-ending execution-state
details in their scenario results:

- `pre_advance_execution_focus`
- `pre_advance_execution_gate`
- `pre_advance_execution_outcome_ready`
- `pre_escalate_execution_focus`
- `pre_escalate_execution_gate`
- `pre_escalate_execution_outcome_ready`

That means the first-cycle live policy endings now prove the same compact
execution-state seam that the second-cycle endings already exposed: the sprint can
reach `advance` only after a ready execution gate, and it can reach `escalate`
only after a failed execution gate.

Those compact execution-state details are now also projected into the repo-local
live-profile snapshot, so `aionis live-profile` can report not just timing but the
latest app-harness execution gate:

- `latest_execution_focus`
- `latest_execution_gate`
- `latest_execution_gate_transition`
- `latest_execution_outcome_ready`
- `latest_last_policy_action`

`aionis live-profile` now also derives a compact comparison string from those
fields:

- `latest_convergence_signal`
- `recent_convergence_signals`

Example shape:

- `live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed`

For older snapshots that only persisted the latest gate transition, `aionis live-profile`
now back-fills `recent_convergence_signals` from `latest_convergence_signal`, so the
comparison surface stays usable across repo-local snapshot upgrades.

The canonical app-harness summary and `/app show` surface now also keep a compact
execution-gate trail across policy actions:

- `last_execution_gate_from`
- `last_execution_gate_to`
- `last_execution_gate_transition`
- `last_policy_action`

That trail is intentionally execution-only. If a sprint reaches `escalate` or
`replan` without a bounded execution attempt, the trail will stay at
`no_execution`, instead of pretending there was a concrete generator outcome.

There is now also a gated second-replan lineage harness entry:

- `tests_real_live_e2e/test_live_app_second_replan.py`

It verifies:

1. a failed sprint can replan into `sprint-1-replan-*`
2. the first replanned sprint can fail, retry once, and escalate again
3. a second live replan activates `sprint-1-replan-*-replan-*`
4. `replan_depth` and `replan_root_sprint_id` remain stable across that second cycle
5. the retry window resets on the second replanned sprint

The first credentialed live reference pass for that second-cycle lineage path has
now also been captured on the `zai_glm51_coding` profile:

- `1 passed in 336.05s (0:05:36)` for
  `tests_real_live_e2e/test_live_app_second_replan.py`

There are now also gated second-cycle policy-ending harness entries:

- `tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py`
- `tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py`

They verify:

1. a second replanned sprint can `generate`
2. that sprint can `qa(pass)` and explicitly unlock `advance`
3. that sprint can also `qa(fail)` and explicitly settle to `escalated`
4. second-cycle `replan_depth` and `replan_root_sprint_id` remain stable across those endings

The first credentialed live reference passes for those second-cycle policy endings
have now also been captured on the `zai_glm51_coding` profile:

- `1 passed in 381.92s (0:06:21)` for
  `tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py`
- `1 passed in 390.00s (0:06:29)` for
  `tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py`

The harness now also exposes explicit post-retry policy fields:

- `retry_available`
- `retry_remaining`
- `next_sprint_ready`
- `next_sprint_candidate_id`
- `recommended_next_action`
- `replan_depth`
- `replan_root_sprint_id`
- `policy_stage`
- `execution_gate`
- `execution_outcome_ready`
- `execution_focus`

The gated second-cycle live ending scenarios now also persist result details that
prove the compact execution signal survives the whole loop:

- `second_replanned_execution_focus`
- `second_replanned_execution_gate`
- `second_replanned_execution_outcome_ready`

That means the current second-cycle live evidence does not only show that
`advance` and `escalate` are reachable. It also shows that the same compact
execution signal is carried through the second replan's live planner, live
generator, live evaluator, and final scenario result details.

And it now supports two explicit operator exits from that policy:

- `app advance`
  - promotes the next planned sprint into the active sprint when the current sprint has cleared the evaluator bar
- `app replan`
  - turns an escalated or retry-budget-exhausted sprint into a new active sprint proposal with a narrowed scope and a reset retry budget
- `app escalate`
  - explicitly marks the current sprint as escalated when the retry path should stop and re-planning or operator intervention is required

## Current boundaries

The current harness still does **not** provide:

- an autonomous planner agent
- a separate evaluator agent
- a multi-turn generator/evaluator negotiation loop
- hard-threshold browser QA
- a full iterative app-builder loop

Those remain phase-2 work.

## Phase 2 Handoff

Phase 2 should begin from the assumption that phase 1 is only the contract and operator layer.

It should **not** claim that Workbench already has a full Anthropic-style long-running app harness. That next layer still needs to be built explicitly.

### 1. Planner agent

Missing phase-2 work:

- turn a loose product request into a structured `ProductSpec` with model-backed planning instead of deterministic inference
- propose initial evaluator criteria using an explicit planner role instead of only deterministic defaults
- propose the first sprint breakdown rather than waiting for operator input

Phase-1 dependency that already exists:

- persisted `ProductSpec`
- persisted evaluator criteria
- `/app plan`
- prompt-only deterministic `app plan`

### 2. Evaluator agent

Missing phase-2 work:

- a dedicated evaluator role, distinct from generic review surfaces
- evaluator-owned scoring rules
- explicit pass/fail semantics that are stronger than a free-form summary

Phase-1 dependency that already exists:

- persisted `SprintEvaluation`
- reviewer substrate
- `/app qa`

### 3. Sprint negotiation loop

Missing phase-2 work:

- a generator/evaluator handshake before implementation begins
- explicit contract revision when a sprint is rejected
- an artifact that explains why a sprint was accepted or blocked

Phase-1 dependency that already exists:

- persisted `SprintContract`
- app harness loop status
- `/app sprint`

### 4. Generator/evaluator retry loop

Missing phase-2 work:

- multiple implementation/evaluation cycles inside one sprint
- bounded retry budget
- escalation rules for repeated failure
- a stable summary of what changed between attempts

Phase-1 dependency that already exists:

- Workbench continuity
- resume/recovery
- reviewer and dream evidence layers

### 5. Playwright-backed QA

Missing phase-2 work:

- browser-driven application QA
- hard thresholds for core criteria like functionality and design quality
- artifact capture for screenshots, traces, and evaluator evidence

Phase-1 dependency that already exists:

- live validation substrate
- real-e2e and real-live-e2e harnesses
- artifact persistence

### Recommended phase-2 order

1. planner-produced `ProductSpec`
2. evaluator agent contract
3. sprint negotiation semantics
4. bounded generator/evaluator retry loop
5. Playwright-backed QA

That order keeps phase 2 aligned with the current platform: Workbench already has strong continuity and evidence layers, so the next step is to make the planning and evaluation actors explicit rather than adding more passive surfaces.

## Why This Matters

Workbench now has enough harness substrate to support long-running app development as a first-class workflow, instead of treating it as an improvised combination of session notes, review hints, and validation commands.

The current phase creates stable artifacts and operator surfaces first. That is the right order for this platform because Workbench already has:

- continuity
- reviewer substrate
- workflow assets
- learning and family reuse
- real-e2e and real-live-e2e verification

## Verification

Recent high-signal checks:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_app_harness_planner_contract.py -q
# 1 passed

.venv/bin/python -m pytest tests/test_product_workflows.py -q
# 29 passed

.venv/bin/python -m pytest tests_real_e2e/test_app_harness_planner_contract.py tests/test_cli_shell.py tests/test_shell_dispatch.py -q
# 177 passed

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_plan.py -q
# 1 passed in 71.85s

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_qa.py -q
# 1 passed in 65.48s

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_negotiate.py -q
# 1 passed

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_retry.py -q
# 1 passed

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_replan_generate_qa.py -q
# gated live coverage exists for replanned sprint -> generate -> qa

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_replan_generate_qa_advance.py -q
# gated live coverage exists for replanned sprint -> generate -> qa(pass) -> advance

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_second_replan.py -q
# 1 passed in 336.05s (0:05:36)

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py -q
# 1 passed in 381.92s (0:06:21)

.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py -q
# 1 passed in 390.00s (0:06:29)
```

The first credentialed live reference pass for that replanned-sprint advance path has
now also been captured on the `zai_glm51_coding` profile:

- `1 passed in 245.11s (0:04:05)` for
  `tests_real_live_e2e/test_live_app_replan_generate_qa_advance.py`

## Next Recommended Work

1. Upgrade deterministic prompt-only planning into an explicit planner actor against the current `ProductSpec` contract
2. Define the evaluator agent contract before building a richer evaluator loop
3. Add one more real scenario:
   - app harness state feeding a later review/evaluator step
4. Only then add richer `/app` views or automation
