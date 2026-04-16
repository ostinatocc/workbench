# Aionisdoc Editor Continuity Guide

`Aionisdoc` editor integrations should not write directly into Workbench storage.

They should emit a stable event envelope and let Workbench record the result into the selected task.

## Contract

Use the event contract here:

- [aionisdoc-workbench-event-v1.md](../contracts/aionisdoc-workbench-event-v1.md)

## Current Ingest Command

```bash
aionis doc --repo-root /absolute/path/to/repo event --task-id task-123 --event ./editor-event.json
```

## Recommended Flow

1. In the editor, bind the workflow run to a known Workbench `task_id`.
2. After `compile` or `run`, write a JSON event file using the v1 contract.
3. Call `aionis doc ... event` with the same `task_id`.
4. Inspect the result from Workbench:
   - `/doc show`
   - `/family`
   - `/dashboard`
   - `/dream`

## Current Extension Slice

The current VS Code / Cursor extension slice already supports:

- explicit task binding
- recent-task suggestions during binding
- compile-to-Workbench sync
- run-to-Workbench sync
- publish-to-Workbench sync
- recover-to-Workbench sync
- resume-to-Workbench sync

Current extension commands:

- `Aionis Doc: Bind Workbench Task`
- `Aionis Doc: Clear Workbench Task Binding`
- `Aionis Doc: Compile Active Document`
- `Aionis Doc: Run Active Document`

The extension currently shells out to:

```bash
aionis doc --repo-root <workspace-root> event --task-id <bound-task-id> --event <temp-json>
```

That means users no longer need to manually replay `compile/run` through Workbench just to record continuity.

For `publish`, `recover`, and `resume`, the current extension slice uses Workbench directly:

```bash
aionis doc --repo-root <workspace-root> publish --input <active-doc> --task-id <bound-task-id>
aionis doc --repo-root <workspace-root> recover --input <active-doc> --input-kind source --task-id <bound-task-id>
aionis doc --repo-root <workspace-root> resume --input <active-doc> --input-kind source --task-id <bound-task-id>
```

This is intentional. These actions already produce Workbench-native persistence, so the extension does not need to re-project them through a second event envelope.

## Failure Recovery

The current extension slice now supports a minimal recovery path:

- failed `compile/run` Workbench sync keeps the generated event JSON on disk
- the warning action can reveal that file in Finder
- `Aionis Doc: Retry Last Workbench Sync` retries the last failed sync for the current workspace

This keeps operator recovery explicit without adding a heavier socket or background queue yet.

## Current Visibility

The extension now exposes the latest Workbench sync state through:

- a dedicated Workbench sync status bar item
- `Aionis Doc: Show Workbench Sync Status`
- `Aionis Doc: Show Workbench Sync History`

This is intentionally lightweight. It answers both:

- what happened last
- whether the last few syncs are stable or failing repeatedly

without introducing a larger inline Workbench panel yet.

The extension also exposes current binding state through:

- a dedicated Workbench binding status bar item
- `Aionis Doc: Show Current Workbench Binding`

That binding surface now includes:

- the current bound task
- recent Workbench tasks
- lightweight suggestions when a recent task already matches the active `.aionis.md`

## What Workbench Records

When the event is ingested successfully, Workbench updates:

- task artifacts such as `doc_publish_result` or `doc_runtime_handoff`
- `continuity.doc_workflow`
- `preferred_artifact_refs`
- `doc_learning`
- family-level doc prior summaries
- dream-visible doc workflow evidence
- dashboard-visible editor-sync proof summaries

## Task Matching Guidance

Best practice:

- let the user pick a task in Workbench first
- keep that `task_id` attached to the editor workflow session
- reuse the same `task_id` for follow-up `recover` and `resume` events

Avoid:

- guessing a task id from file path only
- emitting the event when the editor has no stable task association

## Out-of-Sync Recovery

If the editor and shell get out of sync:

1. run `/doc show TASK_ID`
2. inspect the latest `doc_workflow` action and anchor
3. re-emit the latest editor event if the shell is missing it
4. only fall back to manual `aionis doc publish|recover|resume` if the event payload is unavailable

## Current Boundary

This guide covers:

- editor-originated event ingestion into Workbench continuity

It does not yet cover:

- editor-native inline Workbench controls
- fully automatic task binding without user confirmation
- richer structured sync analytics beyond the bounded recent-history surface
- extension-to-Workbench live socket/session protocols
