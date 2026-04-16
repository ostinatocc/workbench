# Aionis Artifact Trial Spec

**Trial name:** `Stateful Visual Dependency Explorer`

**Purpose:** Produce two directly inspectable artifacts for the same long task:

- `Baseline artifact`
- `Aionis artifact`

The trial is successful only if a human can compare the two final outputs without reading internal Workbench state.

## Artifact contract

Each arm must produce:

- one runnable local project
- one clear local run command
- one short operator note
- 2-4 screenshots
- one filled comparison checklist

The output must be judged as an artifact, not as a benchmark trace.

## Shared visible acceptance criteria

Both artifacts are evaluated against the same visible criteria:

1. The graph canvas renders and looks coherent.
2. Selecting a node updates the detail panel.
3. Selecting a node updates the timeline panel.
4. Search or filter changes graph visibility.
5. Refresh preserves:
   selected node, active filters, and timeline focus.
6. The app remains demoable after persistence is added.

## Fairness rules

Both arms must share:

- the same repo fixture or starting point
- the same task prompt
- the same provider/model family
- the same visible target

This trial does not try to prove:

- arbitrary model superiority
- browser-grade production QA
- large backend integration quality

It tries to prove:

- whether Aionis can drive a long task to a more demoable visible outcome.

## Artifact proof package

Each arm must end with:

- `run_command`
- `screenshots`
- `checklist_result`
- `artifact_summary`

The final side-by-side report must answer:

- which artifact is more complete
- which artifact is more stable
- which artifact is more demoable

## Verdict rule

The preferred verdict is artifact-first:

- `Baseline produced a partial shell.`
- `Aionis produced a runnable explorer with stable refresh behavior.`

Avoid verdicts that only mention internal state or convergence metrics.
