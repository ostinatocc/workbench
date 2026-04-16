# Aionisdoc Editor Continuity Status

Date: `2026-04-03`

## Outcome

The `Aionisdoc -> editor -> Workbench` continuity loop is now functionally complete for the current phase.

This is no longer only a file-based ingest experiment.

The extension can now:

- bind to a real Workbench task
- sync local `compile/run` through `event v1`
- persist `publish/recover/resume` directly through Workbench CLI
- recover from failed syncs
- show local operator state for binding and sync health

Workbench can now:

- record editor-originated doc workflow evidence into `continuity.doc_workflow`
- project that evidence into `doc_learning`
- surface it in `/doc show`, `/family`, `/dashboard`, and `/dream`
- carry the same evidence into family doc priors and AutoDream promotions

## What Exists Now

### Extension side

In [extension.ts](/Users/lucio/Desktop/Aionis/packages/aionis-doc-vscode/src/extension.ts), the editor integration now includes:

- explicit Workbench task binding
- recent-task lookup through `aionis recent-tasks`
- suggestion ordering that prefers tasks already associated with the active `.aionis.md`
- `compile/run` event emission through `aionisdoc_workbench_event_v1`
- direct Workbench persistence for `publish/recover/resume`
- failed sync retry
- event file preservation for failed `compile/run` sync
- sync status bar
- sync history
- binding status bar
- operator surfaces backed by output channel + QuickPick

The extension now exposes these operator commands:

- `Aionis Doc: Bind Workbench Task`
- `Aionis Doc: Clear Workbench Task Binding`
- `Aionis Doc: Show Current Workbench Binding`
- `Aionis Doc: Show Workbench Sync Status`
- `Aionis Doc: Show Workbench Sync History`
- `Aionis Doc: Retry Last Workbench Sync`

### Workbench side

Workbench now has these continuity surfaces and projections:

- [session_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py)
  - records `event_source`, `event_origin`, and `recorded_at`
- [doc_learning.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/doc_learning.py)
  - normalizes editor-originated doc workflow evidence
- [consolidation.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/consolidation.py)
  - derives family-level doc prior plus editor-sync counts
- [ops_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py)
  - rolls editor-sync evidence into dashboard summary and proof text
- [dream_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py)
  - carries editor-sync evidence into dream samples, candidates, and promotions
- [shell.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py)
  - renders editor-driven evidence in task, family, dashboard, and dream surfaces

## User-Visible Effects

The continuity loop is now visible at four levels:

### 1. Task level

`/doc show` now exposes:

- latest doc action/status
- selected tool
- handoff anchor
- sync source
- latest sync timestamp

### 2. Family level

`/family` now exposes:

- `doc_prior=...`
- `doc_sync=<source> count=<n> last=<timestamp>`

This means the user can see not only that a doc workflow is reusable, but also that it is repeatedly arriving through editor-driven continuity.

### 3. Repo level

`/dashboard` now exposes:

- doc prior counts
- editor sync counts across families
- top family/source pair for editor-originated doc reuse
- a stronger proof summary when editor-driven doc reuse is live

### 4. Dream level

`/dream` now exposes:

- `top_docs=...`
- `top_doc_syncs=...`

This makes it visible when a promoted prior is not only doc-backed, but editor-backed.

## Current Loop

The current end-to-end loop now looks like this:

1. user binds the active editor workflow to a Workbench `task_id`
2. editor performs `compile`, `run`, `publish`, `recover`, or `resume`
3. extension syncs the result into Workbench continuity
4. Workbench records structured doc workflow evidence
5. doc evidence becomes task-level `doc_learning`
6. repeated evidence becomes family-level `doc_prior`
7. repeated validated evidence becomes dream-visible prior evidence
8. dashboard proof surfaces can now say editor-driven doc reuse is live

## Verification

Latest high-signal Workbench regression:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_bootstrap.py tests/test_doc_learning.py tests/test_shell_dispatch.py tests/test_cli_shell.py tests/test_product_workflows.py tests/test_aionisdoc_service.py tests/test_aionisdoc_bridge.py tests/test_dream_service.py tests/test_dream_models.py -q
```

Result:

- `230 passed`

Latest extension smoke:

```bash
cd /Users/lucio/Desktop/Aionis/packages/aionis-doc-vscode
npm run smoke
```

Result:

- `smoke passed`

## Current Limits

This phase is now strong enough for internal product use, but it still has clear boundaries:

- the extension still shells out to CLI rather than using a local API/socket
- task binding is assisted by recent-task suggestions, but still user-confirmed rather than automatic
- sync history is bounded and lightweight, not a full audit browser
- Workbench surfaces show the strongest editor-sync evidence, not an exhaustive per-task sync timeline

## Most Important Remaining Debt

- add a richer ranked browser if users need more than the compact recent sync history
- consider a direct local API if CLI shell-out latency becomes an issue
- expose editor-sync evidence in more structured dashboard/family exports if other consumers need it

## Notes

- This status reflects the current implementation after editor continuity, repo-level projections, and dream-level editor-sync visibility all landed on `2026-04-03`.
- The workspace used here was not a git repository, so no commit metadata was recorded during implementation.
