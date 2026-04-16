# Workbench Foundation Slice Acceptance

Date: 2026-04-01

This document closes the `foundation memory-learning` slice and records the final acceptance result for the current Workbench runtime shell.

## Scope accepted

The accepted foundation includes:

- `trust-shaped strategy affinity`
- `execution packet contract`
- `planner/provenance runtime surfaces`
- `context layering + budget`
- `continuity_snapshot` as the primary continuity seed and inspect surface
- `shared_memory` reduced to a thin compatibility projection
- `canonical_surface` and `canonical_views` as the default explain/debug surfaces
- `evaluate` as the formal readiness check for a persisted session

## Acceptance command

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root <repo-root> --task-id <task-id>
```

The evaluator checks:

- `execution_packet_present`
- `planner_surface_present`
- `provenance_surface_present`
- `context_layers_present`
- `continuity_snapshot_present`
- `continuity_has_prior_memory`
- `shared_memory_is_thin`
- `canonical_views_present`

## Representative accepted sessions

### 1. Successful ingest sample: `click-3193-ingest-1`

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth/.aionis-workbench/sessions/click-3193-ingest-1.json`
- Command:
  - `PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth --task-id click-3193-ingest-1`
- Result:
  - `status = ready`
  - `score = 100.0`
  - `legacy_prior_line_count = 0`

Why it matters:

- proves a successful ingest session is now fully canonical
- proves continuity carries prior artifacts and prior collaboration patterns structurally
- proves thin `shared_memory` no longer blocks acceptance

### 2. Successful ingest sample: `click-2645-ingest-1`

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-seventeenth/.aionis-workbench/sessions/click-2645-ingest-1.json`
- Command:
  - `PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-seventeenth --task-id click-2645-ingest-1`
- Result:
  - `status = ready`
  - `score = 100.0`
  - `legacy_prior_line_count = 0`

Why it matters:

- proves a second module face also passes the canonical readiness bar
- confirms project-scoped continuity survives save/backfill cycles without legacy prior-lines

### 3. Recovery stress sample: `click-2786-workbench-2`

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth/.aionis-workbench/sessions/click-2786-workbench-2.json`
- Command:
  - `PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth --task-id click-2786-workbench-2`
- Result:
  - `status = ready`
  - `score = 100.0`
  - `legacy_prior_line_count = 0`

Why it matters:

- proves the same canonical foundation also holds on a recovery-heavy session
- confirms rollback/correction/timeout surfaces now flow through packet, provenance, continuity, and layers without legacy prior-lines

## Final structural acceptance

The slice is accepted because the default runtime shell now has all of these active at once:

- `execution_packet`
- `execution_packet_summary`
- `planner_packet`
- `strategy_summary`
- `pattern_signal_summary`
- `workflow_signal_summary`
- `maintenance_summary`
- `continuity_snapshot`
- `context_layers_snapshot`
- `canonical_surface`
- `canonical_views`

These are no longer optional secondary summaries. They are now the primary surfaces for:

- prompt construction
- inspect/debug
- continuity seeding
- strategy explanation
- recovery inspection
- session readiness evaluation

## Continuity acceptance

The most important continuity condition is now satisfied:

- reusable prior continuity survives structurally in `continuity_snapshot`
- `build_continuity_snapshot()` can still rebuild reusable continuity even if `shared_memory` is empty
- `shared_memory` no longer carries default `Prior strategy / Prior artifact / Prior collaboration pattern` lines

Observed accepted `shared_memory` shape:

- `Project identity`
- `Project scope`
- `Session working set`
- `Session validation path`
- `Kickoff ...` only when present
- `Recovered handoff ...` only when present
- one light `Recent working sets` projection

## Outcome

Foundation slice status:

- `accepted`

Foundation implication:

- Workbench no longer needs additional foundation work before the next product phase

The next slice should now focus on product extension rather than base cleanup:

- stronger multi-agent collaboration learning
- richer strategy selection
- live instrumentation / evaluation views
- continued cross-module real-task validation
