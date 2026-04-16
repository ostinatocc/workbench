# Aionis Workbench Platform Status

Date: `2026-04-03`

## Outcome

`Aionis Workbench` is now in a strong internal-product state.

The platform is no longer only:

- a CLI shell
- a task memory layer
- a runtime adapter

It now behaves as an integrated product stack with four working layers:

1. `Workbench` control plane
2. `AutoDream` prior compiler
3. `Aionisdoc` workflow asset layer
4. `editor continuity` through the VS Code / Cursor extension

The most important threshold change is this:

The system can now carry a workflow from editor execution into Workbench continuity, then project that workflow upward into:

- task surfaces
- family priors
- repo-level proof summaries
- dream-visible promotion evidence

## Layer Status

### 1. Workbench control plane

This layer is now stable and modular.

Main modules:

- [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py)
- [ops_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py)
- [session_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py)
- [recovery_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/recovery_service.py)
- [orchestrator.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py)
- [surface_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py)
- [runtime_contracts.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime_contracts.py)

Current product state:

- launcher phase 1 is working
- default shell workflow is productized
- degraded and inspect-only paths are explicit
- major shell surfaces are stable

### 2. AutoDream prior compiler

This layer is functionally complete for phase 1.

Main modules:

- [dream_models.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_models.py)
- [dream_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py)
- [dream_state.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_state.py)

Current product state:

- extracts structured samples from sessions
- distills candidates
- verifies held-out evidence
- promotes `trial` and `seed_ready` priors
- deprecates stale/contradictory priors
- now carries doc workflow evidence
- now carries editor-sync evidence for doc-backed priors

### 3. Aionisdoc workflow asset layer

This layer is now beyond sidecar status.

Main modules:

- [aionisdoc_bridge.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionisdoc_bridge.py)
- [aionisdoc_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionisdoc_service.py)
- [doc_learning.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/doc_learning.py)

Current product state:

- `aionis doc ...` CLI is live
- `/doc ...` shell surfaces are live
- `publish/recover/resume` continuity is persistent
- doc workflow evidence becomes `doc_learning`
- repeated evidence becomes `family_doc_prior`
- repo-level dashboard now sees doc priors

### 4. Editor continuity

This layer is now product-real, not only experimental.

Main implementation:

- [extension.ts](/Users/lucio/Desktop/Aionis/packages/aionis-doc-vscode/src/extension.ts)
- [workbenchBinding.ts](/Users/lucio/Desktop/Aionis/packages/aionis-doc-vscode/src/workbenchBinding.ts)

Current product state:

- explicit task binding
- recent-task suggestions
- compile/run event sync
- publish/recover/resume direct sync
- failed sync retry
- event-file preservation
- sync status/history
- binding status surface

## Cross-Layer Product Loop

The important platform loop now looks like this:

1. user binds an editor workflow to a Workbench `task_id`
2. editor performs a doc action
3. extension syncs the result into Workbench continuity
4. Workbench records task-level doc evidence
5. repeated evidence becomes family-level doc priors
6. repo-level dashboard sees editor-driven doc reuse
7. AutoDream promotion carries the same evidence upward
8. `/dream` shows which promoted priors are doc-backed and editor-backed

This means the platform can now prove:

- the workflow happened
- the workflow persisted
- the workflow repeated
- the workflow was promoted into reusable evidence

## User-Visible Surfaces

### Task surfaces

- `/doc show`
- `/show`

### Family surfaces

- `/family`

### Repo surfaces

- `/dashboard`
- `/dream`

### Editor surfaces

- Workbench binding status
- Workbench sync status
- Workbench sync history

## What Is Strong Now

The strongest current properties of the platform are:

- continuity survives across shell and editor boundaries
- doc workflows are not only stored, but promoted into reusable evidence
- dream promotions can now explain doc-backed and editor-backed reuse
- repo-level proof surfaces can show when editor-driven doc reuse is live

## Current Limits

The platform is still not at final external-product shape.

Current limits:

- launcher/distribution is phase 1, not GA
- extension still uses CLI shell-out rather than local API or socket
- sync history is intentionally compact
- task binding is suggestion-assisted, not fully automatic
- dashboard and dream surfaces show top evidence, not a deep ranked browser

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

## Recommended Next Focus

The next work should now bias toward product refinement rather than core capability expansion.

Best next targets:

- a unified top-level product status/guide entry from the README
- richer but still compact repo-level exports for editor-sync evidence
- deciding whether the extension should stay CLI-driven or move to a local API boundary

## References

- [2026-04-03-workbench-runtime-decomposition-status.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-workbench-runtime-decomposition-status.md)
- [2026-04-03-aionis-autodream-prior-compiler-status.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionis-autodream-prior-compiler-status.md)
- [2026-04-03-aionisdoc-editor-continuity-status.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionisdoc-editor-continuity-status.md)
- [2026-04-03-aionis-launcher-guide.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionis-launcher-guide.md)
- [2026-04-03-aionisdoc-workbench-guide.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionisdoc-workbench-guide.md)
- [2026-04-03-aionisdoc-editor-continuity-guide.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionisdoc-editor-continuity-guide.md)
