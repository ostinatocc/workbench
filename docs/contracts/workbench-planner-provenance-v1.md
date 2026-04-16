# Aionis Workbench Planner And Provenance Contract V1

Last reviewed: 2026-04-01

Status:

`draft v1`

## Purpose

This contract defines the compact planner-facing and operator-facing summaries that explain:

- why Workbench chose a strategy
- which prior patterns/artifacts were trusted
- which execution state is current
- which maintenance action should happen next

The goal is to keep strategy selection explainable without forcing consumers to reverse-engineer raw memory lines, artifact blobs, or legacy summaries.

## Canonical Summary Surfaces

Workbench should converge on these stable summary objects:

- `planner_packet`
- `strategy_summary`
- `pattern_signal_summary`
- `workflow_signal_summary`
- `maintenance_summary`
- `execution_packet_summary`

## Summary Definitions

`planner_packet`
- Compact planner-facing view of the current execution packet plus trusted collaboration inputs.
- This is the primary structured surface for the next model step.

`strategy_summary`
- Why a specific working set, role sequence, validation path, and preferred artifacts were selected.
- Must explicitly name the strongest trust signal:
  - `exact_task_signature`
  - `same_task_family`
  - `same_error_family`
  - `broader_similarity`

`pattern_signal_summary`
- Compact report of which collaboration patterns were trusted, contested, or ignored.
- Should include both reused patterns and the trust level that admitted them.

`workflow_signal_summary`
- Compact report of the collaboration workflow being used.
- Examples:
  - `investigator -> implementer -> verifier`
  - timeout-aware direct mode
  - rollback-first recovery

`maintenance_summary`
- What maintenance or cleanup should happen to memory after this run.
- Examples:
  - promote validation strategy
  - suppress stale working-set hint
  - evict superseded insight

`execution_packet_summary`
- Minimal human-readable projection of the canonical execution packet.
- Must stay aligned with packet stage, active role, next action, and blockers.

## Authority Rules

When surfaces disagree, authority is:

1. `execution_packet`
2. `planner_packet`
3. `strategy_summary`
4. `pattern_signal_summary`
5. `workflow_signal_summary`
6. `maintenance_summary`
7. legacy memory lines

Examples:

- If `strategy_summary` says the task is in verification but `execution_packet.current_stage` says `rollback_recovery`, the packet wins.
- If a legacy memory line suggests a broader working set than `planner_packet.target_files`, the planner packet wins.

## Provenance Phrasing Rules

Workbench summaries should describe provenance explicitly.

Preferred phrasing:

- `Selected because same_task_family matched prior termui work.`
- `Preferred artifact reused from click-3242-ingest-1 investigator artifact.`
- `Rollback-first recovery chosen because regression expansion widened the failing set.`
- `Validation path promoted after repeated targeted success on the same module family.`

Avoid vague phrasing such as:

- `this seems relevant`
- `probably useful`
- `picked from memory`

## Contract Intent

This contract exists so Workbench can become:

- more explainable
- more debuggable
- more stable across run, resume, ingest, and backfill
- less dependent on ad hoc prompt assembly
