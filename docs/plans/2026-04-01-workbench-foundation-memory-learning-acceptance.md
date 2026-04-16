# Workbench Foundation Memory Learning Acceptance

Date: 2026-04-01

Scope:

- `trust-shaped strategy affinity`
- `execution packet contract`
- `planner/provenance runtime surfaces`
- `context layering + budget`
- `continuity_snapshot` as the primary continuity surface
- `shared_memory` demoted to a thin compatibility lane

Acceptance target:

- canonical surfaces are present and stable
- continuity no longer depends on legacy `shared_memory` prior-lines
- prompt and inspect surfaces are canonical-first
- representative real sessions pass a readiness evaluation

## Acceptance command

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root <repo-root> --task-id <task-id>
```

The acceptance evaluator checks:

- `execution_packet_present`
- `planner_surface_present`
- `provenance_surface_present`
- `context_layers_present`
- `continuity_snapshot_present`
- `continuity_has_prior_memory`
- `shared_memory_is_thin`
- `canonical_views_present`

## Representative sessions

### 1. Success sample: `_utils.py` multiprocessing sentinel

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth/.aionis-workbench/sessions/click-3193-ingest-1.json`
- Command:
  - `PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth --task-id click-3193-ingest-1`
- Result:
  - `status = ready`
  - `score = 100.0`
  - `legacy_prior_line_count = 0`

Why this sample matters:

- validates canonical surfaces on a successful ingest path
- validates continuity reuse across prior `utils/types` samples
- confirms `shared_memory` is now only a thin compatibility projection

### 2. Success sample: `utils.py` FIFO lazy read

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-seventeenth/.aionis-workbench/sessions/click-2645-ingest-1.json`
- Command:
  - `PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-seventeenth --task-id click-2645-ingest-1`
- Result:
  - `status = ready`
  - `score = 100.0`
  - `legacy_prior_line_count = 0`

Why this sample matters:

- validates canonical surfaces on a different module face
- confirms project-scoped continuity still exposes prior artifacts and patterns
- confirms thin `shared_memory` survives backfill/save cycles

### 3. Recovery stress sample: `#2786`

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth/.aionis-workbench/sessions/click-2786-workbench-2.json`
- Command:
  - `PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth --task-id click-2786-workbench-2`
- Result:
  - `status = ready`
  - `score = 100.0`
  - `legacy_prior_line_count = 0`

Why this sample matters:

- validates the same foundation slice on a non-success path
- confirms `rollback_first` / recovery surfaces still flow through canonical packet, provenance, continuity, and layers
- confirms recovery sessions no longer need legacy prior-lines in `shared_memory`

## Structural acceptance findings

The foundation slice is accepted because the system now has:

- `execution_packet` and `execution_packet_summary`
- `planner_packet`
- `strategy_summary`
- `pattern_signal_summary`
- `workflow_signal_summary`
- `maintenance_summary`
- `context_layers_snapshot`
- `continuity_snapshot`

These are now the canonical control and explanation surfaces for:

- prompt construction
- inspect/debug output
- strategy reasoning
- continuity seeding
- recovery state inspection

## Continuity acceptance findings

The critical continuity condition is now satisfied:

- prior continuity is preserved structurally in `continuity_snapshot`
- `build_continuity_snapshot()` can rebuild reusable continuity even if `shared_memory` is cleared
- `shared_memory` no longer carries legacy prior strategy/pattern/artifact lines by default

Observed accepted state:

- `shared_memory` is limited to:
  - project identity/scope
  - current session working set
  - current validation paths
  - kickoff / recovered handoff when present
  - a light `Recent working sets` projection

## Outcome

Foundation status:

- `accepted`

Accepted slice:

- the Workbench foundation memory-learning plan is complete enough to treat as the default runtime shell

What remains is no longer foundation work. The next slice should be product extension work:

- stronger multi-agent collaboration learning
- richer strategy selection
- live instrumentation / evaluation views
- continued real-task validation across new module families
