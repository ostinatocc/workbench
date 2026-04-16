# Aionis Artifact Aionis Runbook

This runbook defines the `Aionis` arm for the artifact trial.

## Goal

Use the current app harness to produce one visible, runnable artifact that can be judged side-by-side against the baseline artifact.

## Allowed Aionis path

The Aionis arm may use:

- `plan`
- `qa`
- `negotiate`
- `retry`
- `generate`
- `replan`
- `advance`
- `escalate`

The trial should prefer a visible product outcome over a pretty internal trace.

## Execution shape

### Step 1: Start from the fixed product prompt

Use the prompt from:

- [2026-04-05-aionis-artifact-trial-task.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-task.md)

### Step 2: Produce the first visible shell

Aim for:

- graph canvas
- detail panel
- timeline panel
- search/filter bar

Do not over-expand scope before the artifact is visible.

Current minimum generator behavior:

- `app generate` now writes a static HTML demo scaffold under `.aionis-workbench/artifacts/<task-id>/<attempt-id>/index.html`
- the latest execution attempt persists:
  - `artifact_kind`
  - `artifact_path`
  - `preview_command`

Use that scaffold as the first visible artifact, then judge whether the sprint needs retry, replan, or advance.

### Step 3: Use evaluator feedback as artifact feedback

Treat evaluator failures as visible product gaps, for example:

- selection does not update detail panel
- timeline linkage is unclear
- refresh persistence is broken

### Step 4: Prefer narrow retries before wide replans

Use retry for:

- wiring fixes
- persistence fixes
- bounded UI coherence issues

Use replan only when:

- the sprint is too wide
- persistence changes destabilize the core interaction
- a focused second cycle is needed to reach a demoable state

### Step 5: Stop when the artifact becomes demoable

Completion requires:

- local run command works
- the checklist is mostly `works`
- refresh no longer destroys the core workflow
- the app looks demoable

## Required output package

The Aionis arm must save:

- `run_command`
- `artifact_summary`
- `checklist_result`
- `screenshots`
- `final_verdict`
- `where_aionis_helped`

## “Where Aionis helped” note

Keep this short and concrete. Examples:

- `Aionis narrowed the sprint after persistence broke refresh behavior.`
- `Aionis used retry to stabilize the graph/detail/timeline loop before advancing.`
- `Aionis replanned around refresh persistence instead of widening scope.`

## Final Aionis verdict language

Use direct language such as:

- `Aionis produced a runnable explorer with stable refresh behavior.`
- `Aionis reached a demoable artifact after one retry and one replan.`
- `Aionis still produced a partial artifact, but it is closer to a coherent demo than the baseline.`
