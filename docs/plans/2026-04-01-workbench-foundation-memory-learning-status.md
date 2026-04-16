# Aionis Workbench Foundation Memory Learning Status

Date: 2026-04-01

Reference plan:
- [2026-03-31-workbench-foundation-memory-learning-plan.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-03-31-workbench-foundation-memory-learning-plan.md)

## Overall

The foundation memory learning plan is no longer at the “proposal” stage. The product now has:

- trust-shaped strategy selection
- a persisted execution packet
- planner/provenance summaries
- layered context assembly with budgets
- canonical inspect/debug surfaces
- a first structured continuity surface

Current overall completion is roughly:

- `75% to 80% complete`

That means the foundation is already real and running, but the slice is not yet fully closed. The remaining work is mostly:

- shrinking the remaining legacy memory-line control paths
- formalizing acceptance/evaluation
- adding instrumentation for why a strategy was selected

## Status By Task

### Task 1: Product Contract Docs

Status: `done`

Delivered:
- [workbench-execution-packet-v1.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/workbench-execution-packet-v1.md)
- [workbench-planner-provenance-v1.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/workbench-planner-provenance-v1.md)
- [README.md](/Volumes/ziel/Aioniscli/Aionis/workbench/README.md) updated to explain packet-first and canonical surfaces

### Task 2: Trust-Shaped Strategy Affinity

Status: `done (v1)`

Delivered:
- `CollaborationPattern` now carries:
  - `task_signature`
  - `task_family`
  - `error_family`
  - `affinity_level`
- `select_collaboration_strategy()` now prefers:
  - `exact_task_signature`
  - `same_task_family`
  - `same_error_family`
  - only then broader similarity
- pattern promotion and refresh paths persist family metadata

Key files:
- [session.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py)
- [policies.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/policies.py)
- [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py)

### Task 3: Stable Execution Packet Model

Status: `done (v1)`

Delivered:
- [execution_packet.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_packet.py)
- persisted:
  - `execution_packet`
  - `execution_packet_summary`
- packet builder now derives canonical execution state from correction / rollback / timeout / validation / artifacts

### Task 4: Packet Lifecycle Unification

Status: `mostly done`

Delivered:
- explicit stages such as:
  - `investigating`
  - `implementing`
  - `verifying`
  - `paused_timeout`
  - `paused_regression_expansion`
  - `paused_scope_drift`
  - `rollback_recovery`
- `accepted_facts`
- `unresolved_blockers`
- centralized `next_action`

Remaining:
- more of the recovery branch logic could still be simplified to depend only on packet/state instead of helper-specific branching

### Task 5: Layered Context Assembly + Budget

Status: `done (v1)`

Delivered:
- [context_layers.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/context_layers.py)
- layers:
  - `facts`
  - `episodes`
  - `rules`
  - `static`
  - `decisions`
  - `tools`
  - `citations`
- budget controls:
  - total char budget
  - per-layer char budget
  - per-layer item limits
  - forgetting-aware re-entry

Now used by prompt assembly and session snapshots.

### Task 6: Planner / Provenance Runtime Surface

Status: `done (v1+)`

Delivered:
- [provenance.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/provenance.py)
- persisted summaries:
  - `planner_packet`
  - `strategy_summary`
  - `pattern_signal_summary`
  - `workflow_signal_summary`
  - `maintenance_summary`
- prompts are now canonical-first
- inspect/debug now exposes:
  - `canonical_surface`
  - `canonical_views`

This part is beyond the original minimum.

### Task 7: Backfill Click Corpus

Status: `partial to mostly done`

Delivered:
- `backfill` refreshes:
  - pattern affinity metadata
  - execution packet
  - planner/provenance summaries
  - context layers
  - continuity snapshot
- key sessions have already been refreshed successfully

Not fully completed:
- the plan’s full named corpus has not been re-walked as one formal batch run

### Task 8: Validate On New Real Click Task

Status: `done, and exceeded`

Delivered:
- multiple real Click tasks across multiple module families, not just one
- the product has been exercised on:
  - `testing`
  - `_termui_impl`
  - `termui`
  - `shell_completion`
  - `core/help`
  - `types`
  - `utils`
  - `_utils`

### Task 9: Final Acceptance Checklist

Status: `partial`

Technically, most product checks are now true:
- trust-shaped strategy selection exists
- execution packet exists
- planner/provenance surfaces exist
- context assembly is layered and budgeted

What is still missing:
- one explicit acceptance pass recorded as a close-out review
- one formal corpus check written as a final checklist outcome

### Task 10: Post-Slice Follow-Up

Status: `started, not complete`

Delivered:
- `canonical_surface`
- `canonical_views`
- clearer strategy explanation surfaces

Not yet completed:
- live instrumentation sheet for:
  - selected strategy
  - match reason
  - selected family
  - injected artifacts
- evaluation sheet comparing early vs later tasks
- second repo expansion

## What Changed Beyond The Original Plan

These parts grew beyond the original plan because they became necessary product surfaces:

- `canonical_surface`
- `canonical_views`
- `continuity_snapshot`
- recovery stress-case formalization for `click-2786`
- tighter separation between:
  - storage lane
  - explanation surface
  - control surface

## Current Product State

The strongest current product properties are:

- project-scoped continuity
- trust-shaped strategy selection
- packet-first execution state
- planner/provenance summaries
- layered context assembly
- canonical inspect/debug surfaces

The main remaining product debt is:

- `shared_memory` still exists as a compatibility lane and has not been fully replaced by structured continuity objects
- live instrumentation and evaluation are not yet formalized
- some recovery logic is still more procedural than contract-driven

## Recommended Next Slice

Priority order:

1. Make `continuity_snapshot` the primary continuity seed and inspect surface.
2. Continue reducing direct `shared_memory` control influence until it becomes a compatibility/storage layer only.
3. Add live strategy instrumentation.
4. Run a formal acceptance pass for the foundation plan.

## Bottom Line

This plan is no longer in the “building foundations from scratch” phase.

It is now in the:

- `foundation largely built`
- `control surfaces becoming canonical`
- `final cleanup, instrumentation, and acceptance still needed`

phase.
