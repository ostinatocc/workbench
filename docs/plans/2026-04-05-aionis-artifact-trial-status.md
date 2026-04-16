# Aionis Artifact Trial Status

Updated: 2026-04-05

## Summary

The artifact trial is now defined as a visible side-by-side product comparison, not a benchmark-only exercise.

The main generator blocker has also been reduced: `app generate` no longer records only execution metadata. It now materializes a minimal static HTML demo scaffold for the current sprint attempt, with:

- a graph surface
- detail panel updates
- timeline updates
- search/filter controls
- localStorage-backed selection/filter persistence

Current fixed trial:

- task: `Stateful Visual Dependency Explorer`
- output: `baseline artifact` vs `Aionis artifact`
- judgment mode: runnable artifact + screenshots + shared checklist

## Locked inputs

The trial now has fixed source documents:

- [2026-04-05-aionis-artifact-trial-spec.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-spec.md)
- [2026-04-05-aionis-artifact-trial-task.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-task.md)
- [2026-04-05-aionis-artifact-trial-checklist.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-checklist.md)
- [2026-04-05-aionis-artifact-baseline-runbook.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-baseline-runbook.md)
- [2026-04-05-aionis-artifact-aionis-runbook.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-aionis-runbook.md)
- [2026-04-05-aionis-artifact-trial-report-template.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-report-template.md)

## Current result location

The trial now has a dedicated case directory:

- [2026-04-05-stateful-visual-dependency-explorer-trial](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial)

It is intended to hold:

- `baseline/`
- `aionis/`
- `report.md`

## What is ready

- fixed task prompt
- fixed visible checklist
- baseline runbook
- Aionis runbook
- side-by-side report template
- dedicated trial case directory
- minimal Aionis artifact generator scaffold
- artifact path + preview command persisted on the latest execution attempt

## What is not done yet

- baseline artifact run
- Aionis artifact run
- screenshots
- final side-by-side verdict

## First rehearsal

The first deterministic Aionis-only rehearsal now exists:

- task id: `artifact-trial-smoke-1`
- generated artifact:
  - [case copy](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/index.html)
  - [source attempt](/Volumes/ziel/Aioniscli/Aionis/workbench/.aionis-workbench/artifacts/artifact-trial-smoke-1/sprint-1-attempt-1/index.html)
- preview command:
  - `python3 -m http.server 4173 --directory /Volumes/ziel/Aioniscli/Aionis/workbench/.aionis-workbench/artifacts/artifact-trial-smoke-1/sprint-1-attempt-1`

This is still a rehearsal artifact, not the final Aionis arm verdict, but it proves the trial can now produce a visible demo file through the real app harness path.

## Next step

Run the full Aionis artifact arm against the fixed trial checklist, capture screenshots from the rehearsal artifact, then start the baseline arm for the side-by-side comparison.
