# Aionisdoc Workbench Guide

`Aionisdoc` is integrated into `Aionis Workbench` as a structured workflow sidecar.

Use it when you want Workbench to:

- compile or run `.aionis.md` workflows
- publish runtime handoffs from those workflows
- recover and resume workflow execution
- persist doc execution evidence into the current task session

Phase 1 kept `Aionisdoc` isolated from the default DeepAgents live loop. Workbench called the external Node toolchain, then projected the result into shell surfaces, CLI payloads, session artifacts, and continuity.

The current integration is now beyond pure Phase 1. Workbench also exposes repo and learning surfaces for doc workflows:

- `doc_learning` records normalized from `continuity.doc_workflow`
- `/doc show`
- `/doc list`
- `/doc inspect`
- family-level `doc prior`
- dashboard-level doc-prior summaries
- AutoDream doc evidence in `/dream`

## Prerequisites

Workbench now prefers the official `Aionisdoc` package roots in this order:

```text
$AIONISDOC_PACKAGE_ROOT
$AIONISDOC_WORKSPACE_ROOT/packages/aionis-doc
../AionisCore/packages/aionis-doc
../AionisRuntime/packages/aionis-doc
~/Desktop/Aionis/packages/aionis-doc
```

The most direct override is:

```bash
export AIONISDOC_PACKAGE_ROOT="/absolute/path/to/AionisCore/packages/aionis-doc"
```

Legacy workspace-root override still works:

```bash
export AIONISDOC_WORKSPACE_ROOT="/absolute/path/to/Aionis"
```

## Non-interactive CLI

Compile a workflow:

```bash
aionis doc --repo-root /absolute/path/to/repo compile --input ./workflow.aionis.md
```

Run a workflow with a module registry:

```bash
aionis doc --repo-root /absolute/path/to/repo run --input ./workflow.aionis.md --registry ./module-registry.json
```

Publish a workflow into runtime handoff storage and attach the result to the current task:

```bash
aionis doc --repo-root /absolute/path/to/repo publish --input ./workflow.aionis.md --task-id task-123
```

Recover a previously published workflow handoff:

```bash
aionis doc --repo-root /absolute/path/to/repo recover --input ./publish-result.json --input-kind publish-result --task-id task-123
```

Resume from a recover result:

```bash
aionis doc --repo-root /absolute/path/to/repo resume --input ./recover-result.json --input-kind recover-result --task-id task-123 --candidate read
```

Record an editor-originated doc event:

```bash
aionis doc --repo-root /absolute/path/to/repo event --task-id task-123 --event ./editor-event.json
```

## Shell Commands

Inside `aionis --repo-root /absolute/path/to/repo`:

```text
/doc compile ./workflow.aionis.md --emit plan
/doc run ./workflow.aionis.md --registry ./module-registry.json
/doc publish ./workflow.aionis.md
/doc recover ./publish-result.json --input-kind publish-result
/doc resume ./recover-result.json --input-kind recover-result --candidate read
/doc show
/doc list
/doc inspect ./workflow.aionis.md
```

When a current task is selected, Workbench passes that task id into the doc action automatically.

## What Gets Persisted

When `publish`, `recover`, or `resume` runs against a selected task, Workbench persists:

- `doc_<action>_result` artifacts
- `doc_runtime_handoff` artifacts when an anchor or handoff kind is present
- `continuity.doc_workflow`
  - latest action
  - current status
  - source doc id/version
  - handoff anchor/kind
  - selected tool on resume
  - bounded action history
- `continuity.preferred_artifact_refs`

That means `inspect_session`, `show`, and later family learning surfaces can see structured doc evidence instead of only free-form notes.

## Learning and Reuse Surfaces

Doc workflows now appear in four layers of Workbench:

- task level
  - `inspect_session()` exposes `doc_learning`
  - `/doc show` summarizes the current task's latest doc action, anchor, tool, and history
- repo level
  - `/doc list` finds `.aionis.md` files and attaches recent evidence when available
  - `/doc inspect` summarizes either a workflow path or a stored doc artifact
- family level
  - `/family` now exposes `doc_prior=...` when a task family has repeated doc workflow evidence
- project / dream level
  - `/dashboard` now surfaces `doc_priors=ready/blocked`
  - `/dream` now exposes promoted doc workflow evidence via `top_docs=...`

## Current Boundaries

The current integration does support:

- compile
- run
- publish
- recover
- resume
- session artifact persistence
- continuity tracking for doc workflow history
- normalized `doc_learning`
- family-level doc priors
- dashboard-level doc prior summaries
- AutoDream doc evidence attached to candidates and promotions
- `/dream` visibility for promoted doc workflows
- file-based editor event ingestion via `aionis doc ... event`

It does not yet support:

- replacing the default Workbench execution host
- registry authoring UX inside Workbench
- editor-native inline controls from Workbench itself
- direct extension-to-Workbench submit path without a file-based event handoff

For the current file-based editor handoff flow, see:

- [2026-04-03-aionisdoc-editor-continuity-guide.md](2026-04-03-aionisdoc-editor-continuity-guide.md)

## Verification State

This integration currently has product-path tests for:

- doc compile and doc shell surfaces
- doc result persistence into session artifacts
- publish -> recover -> resume continuity history

The latest local regression run that covered bootstrap, shell/CLI, doc product paths, and dream/doc learning paths passed with:

```text
223 passed
```
