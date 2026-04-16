# Aionis Artifact Baseline Runbook

This runbook defines the `baseline` arm for the artifact trial.

## Goal

Produce one visible artifact with a thin loop:

- one plan
- one implementation attempt
- one evaluator pass
- optional one retry
- no structured replan lineage
- no persistent harness state beyond the immediate run

The baseline arm must still end with a runnable output and a visible checklist result.

## Shared fairness constraints

The baseline arm must use the same:

- repo starting point
- task prompt
- provider/model family
- visible acceptance criteria

Do not add hidden manual rescue steps that the Aionis arm is not also allowed to use.

## Execution shape

### Step 1: Initialize the baseline task

Use the fixed prompt from:

- [2026-04-05-aionis-artifact-trial-task.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-task.md)

### Step 2: Produce one artifact attempt

The baseline output should aim to build:

- graph canvas
- detail panel
- timeline panel
- search/filter bar

### Step 3: Do one visible evaluation

Judge the baseline artifact using:

- [2026-04-05-aionis-artifact-trial-checklist.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-checklist.md)

If refresh persistence is clearly broken, record it directly.

### Step 4: Allow at most one bounded retry

If the first attempt is visibly incomplete, allow one retry limited to:

- fixing broken interaction wiring
- fixing refresh persistence
- clarifying graph/detail/timeline linkage

Do not introduce a structured second-cycle replan.

## Required output package

The baseline arm must save:

- `run_command`
- `artifact_summary`
- `checklist_result`
- `screenshots`
- `final_verdict`

## Expected baseline failure modes

Common failure modes that should be recorded plainly:

- graph shell exists but interactions are partial
- refresh loses selection or filters
- timeline panel is disconnected
- artifact is runnable but not demoable

## Final baseline verdict language

Use direct language such as:

- `Baseline produced a partial shell.`
- `Baseline rendered the graph but lost state after refresh.`
- `Baseline is runnable but not demoable.`
