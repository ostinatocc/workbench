# Aionis Workbench Execution Packet Contract V1

Last reviewed: 2026-04-01

Status:

`draft v1`

## Purpose

This contract defines the stable execution-state object that Workbench should expose to:

- planner prompts
- delegation prompts
- deterministic recovery
- artifact-first collaboration
- session inspection and backfill

The packet is the primary execution-intent surface. Legacy memory lines, correction packets, rollback hints, and delegation summaries may still exist, but they should progressively become inputs to the packet rather than parallel sources of truth.

## Canonical Packet

Workbench V1 uses one canonical packet with these fields:

- `packet_version`
- `current_stage`
- `active_role`
- `task_brief`
- `target_files`
- `next_action`
- `hard_constraints`
- `accepted_facts`
- `pending_validations`
- `unresolved_blockers`
- `rollback_notes`
- `artifact_refs`
- `evidence_refs`

### Field Semantics

`packet_version`
- Integer version of the packet contract.

`current_stage`
- One explicit execution stage such as:
  - `investigating`
  - `implementing`
  - `verifying`
  - `paused_timeout`
  - `paused_regression_expansion`
  - `paused_scope_drift`
  - `rollback_recovery`

`active_role`
- The role that should act next.
- Expected values are usually `investigator`, `implementer`, `verifier`, or `orchestrator`.

`task_brief`
- One short statement of the task currently being solved.

`target_files`
- Narrow repo-relative working set for the current stage.
- This is the authoritative file focus for planner and recovery prompts.

`next_action`
- One concrete next step.
- This field is authoritative when prompt surfaces disagree about what to do next.

`hard_constraints`
- Constraints that must not be violated.
- Examples:
  - keep validation narrow
  - do not expand beyond the correction working set
  - preserve CLI behavior

`accepted_facts`
- Facts treated as already established for the current loop.
- Examples:
  - baseline failing test is `X`
  - suspicious file is `src/click/core.py`

`pending_validations`
- Commands or validation tasks that still need to run.

`unresolved_blockers`
- Explicit blockers still preventing completion.
- Examples:
  - provider timeout
  - rollback candidate still fails baseline test

`rollback_notes`
- Recovery notes that narrow future rollback or correction work.

`artifact_refs`
- Repo-local or project-store artifact paths that should be treated as first-class context references.

`evidence_refs`
- Supporting references that justify accepted facts, blockers, or next action.

## Source-of-Truth Rules

The packet should be built from existing Workbench sources in this order:

1. current task/session inputs
2. correction packet artifact
3. rollback hint artifact
4. timeout artifact
5. validation result
6. delegation packets
7. delegation returns

If raw memory lines disagree with the packet, the packet wins.

## Prompting Rules

- memory prompts should read the execution packet before raw memory lines
- delegation prompts should surface `current_stage`, `active_role`, `target_files`, `next_action`, and the packet references
- deterministic recovery should read `accepted_facts`, `pending_validations`, and `rollback_notes` before probing older summaries

## Compatibility

- old sessions may not yet carry an execution packet
- backfill may synthesize a packet from correction, rollback, timeout, validation, and delegation artifacts
- legacy memory lines remain readable but are no longer authoritative once a packet exists
