# Aionisdoc Workbench Event Contract v1

Date: `2026-04-03`

## Goal

Define a small JSON envelope that a VS Code or Cursor integration can emit after a doc action so `Aionis Workbench` can record continuity without re-running the full `aionis doc ...` command.

This contract is intentionally shaped to be compatible with the payloads Workbench already receives from:

- `aionis doc compile`
- `aionis doc run`
- `aionis doc publish`
- `aionis doc recover`
- `aionis doc resume`

## Version

Current contract id:

```text
aionisdoc_workbench_event_v1
```

The extension should send:

- `event_version = "aionisdoc_workbench_event_v1"`

Workbench should reject unknown versions.

## Supported Actions

The event currently supports:

- `compile`
- `run`
- `publish`
- `recover`
- `resume`

## Envelope Shape

```json
{
  "event_version": "aionisdoc_workbench_event_v1",
  "event_source": "cursor_extension",
  "task_id": "task-123",
  "doc_action": "publish",
  "doc_input": "flows/workflow.aionis.md",
  "status": "completed",
  "occurred_at": "2026-04-03T18:30:00Z",
  "payload": {
    "shell_view": "doc_publish",
    "doc_action": "publish",
    "doc_input": "flows/workflow.aionis.md",
    "status": "completed",
    "publish_result": {
      "publish_result_version": "aionis_doc_publish_result_v1",
      "source_doc_id": "workflow-001",
      "source_doc_version": "1.0",
      "request": {
        "anchor": "workflow-anchor-1",
        "handoff_kind": "doc_runtime_handoff"
      },
      "response": {
        "handoff_anchor": "workflow-anchor-1",
        "handoff_kind": "doc_runtime_handoff"
      }
    }
  }
}
```

## Field Semantics

- `event_version`
  - required
  - must equal `aionisdoc_workbench_event_v1`
- `event_source`
  - required
  - examples:
    - `cursor_extension`
    - `vscode_extension`
    - `editor_sidecar`
- `task_id`
  - required
  - must match the Workbench task that should receive continuity updates
- `doc_action`
  - required
  - one of the supported actions above
- `doc_input`
  - required
  - the workflow path or source input used by the editor action
- `status`
  - optional but strongly recommended
  - examples:
    - `ok`
    - `completed`
    - `failed`
- `occurred_at`
  - optional
  - kept for operator/debugging value; Workbench does not require it in v1
- `payload`
  - required
  - should mirror the existing Workbench-facing `doc_*` payload shape for the same action

## Action-Specific Payload Keys

The nested `payload` should include the existing action result key:

- `compile` -> `compile_result`
- `run` -> `run_result`
- `publish` -> `publish_result`
- `recover` -> `recover_result`
- `resume` -> `resume_result`

Workbench v1 intentionally reuses these existing payload shapes so editor integrations do not need a second artifact schema.

## Ingestion Path

Current Workbench ingestion entrypoint:

```bash
aionis doc --repo-root /absolute/path/to/repo event --task-id task-123 --event ./editor-event.json
```

That path should:

- record doc artifacts for the matching task
- update `continuity.doc_workflow`
- update `preferred_artifact_refs`
- make the event visible through:
  - `inspect_session()`
  - `/doc show`
  - `/family`
  - `/dashboard`
  - `/dream`

## What The Extension Should Not Do

The editor integration should not:

- write directly into session JSON files
- write directly into `.aionis-workbench/consolidation.json`
- write directly into dream state files
- assume Workbench storage layout

It should emit the event envelope and let Workbench project that into continuity.

## Matching Rules

The extension should prefer this order:

1. explicit user-selected `task_id`
2. task id already associated with the current editor workflow session
3. no emission if task identity is unclear

The extension should not guess a task id from only file path similarity.

## Forward Compatibility

Future versions may add:

- `registry_path`
- `selected_artifact`
- `workspace_root`
- `session_hint`
- `editor_session_id`

But v1 keeps the contract narrow on purpose.
