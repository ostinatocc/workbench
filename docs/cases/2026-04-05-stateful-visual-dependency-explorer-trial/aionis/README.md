# Aionis Artifact Slot

Current visible artifacts:

- legacy static demo:
  - artifact: [index.html](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/index.html)
  - source attempt: [index.html](/Volumes/ziel/Aioniscli/Aionis/workbench/.aionis-workbench/artifacts/artifact-trial-smoke-1/sprint-1-attempt-1/index.html)
  - preview command: `python3 -m http.server 4173 --directory /Volumes/ziel/Aioniscli/Aionis/workbench/.aionis-workbench/artifacts/artifact-trial-smoke-1/sprint-1-attempt-1`

- current exported app workspace:
  - root: [workspace](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/workspace)
  - entrypoint: [index.html](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/workspace/index.html)
  - app source: [App.tsx](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/workspace/src/App.tsx)
  - workspace manifest: [package.json](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/workspace/package.json)
  - preview command: `cd /Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/workspace && npm run dev -- --host 0.0.0.0 --port 4173`
  - export notes: [README.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/cases/2026-04-05-stateful-visual-dependency-explorer-trial/aionis/workspace/README.md)

Current status:

- the exported workspace is a real React/Vite app directory, not just a single HTML file
- this specific export was produced through the offline `--use-live-generator` scaffold fallback
- it gives a runnable app workspace you can inspect directly, but it is still scaffold-only, not a model-completed feature implementation
- the next hard milestone is the same path with live credentials, so the workspace is changed by a real bounded model execution attempt instead of just bootstrap scaffolding

Suggested contents:

- run command
- short artifact summary
- screenshot paths
- filled checklist summary
- where Aionis helped
- final verdict
