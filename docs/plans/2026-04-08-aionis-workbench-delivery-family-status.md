# Aionis Workbench Delivery Family Status

Date: 2026-04-08

## First principles

`Aionis Workbench` should not expose internal kernel steps as the user product.
It should accept a task once, route that task into the right delivery family, then
internally drive planning, execution, QA, retry/replan, and export.

The smallest stable unit is not "every stack in the world". It is:

1. A single product entrypoint: `app ship`
2. A small set of explicit bootstrap families
3. Family-specific validation and preview rules
4. A shared execution / artifact / recovery loop

## Families proven so far

### 1. `react_vite_web`

Use for:
- landing pages
- homepages
- dashboards
- explorers
- editor/demo style web tasks

Bootstrap:
- `package.json`
- `vite.config.ts`
- `tsconfig.json`
- `index.html`
- `src/main.tsx`
- `src/App.tsx`
- `src/styles.css`

Validation:
- `npm run build`
- verify `dist/index.html` exists
- verify `src/App.tsx` is a non-sparse primary page surface

Live tasks already proven:
- landing page
- analytics dashboard
- feature explorer demo

### 2. `python_fastapi_api`

Use for:
- API/backend/service/server prompts with FastAPI markers

Bootstrap:
- `requirements.txt`
- `main.py`

Validation:
- `python3 -m py_compile main.py`
- verify `requirements.txt` includes `fastapi` and `uvicorn`
- verify `FastAPI(`, `app =`, `/health`, and `/features` are present

Preview:
- `python3 -m pip install -r requirements.txt && python3 -m uvicorn main:app --host 0.0.0.0 --port 4173`

Live task already proven:
- FastAPI backend service with health/features endpoints

### 3. `node_express_api`

Use for:
- API/backend/service/server prompts with Express or Node markers

Bootstrap:
- `package.json`
- `main.js`

Validation:
- `node --check main.js`
- verify `package.json` declares `express` and a `dev` or `start` script
- verify `express`, `app.get(`, `/health`, and `/features` are present

Preview:
- `npm install --no-fund --no-audit && npm run dev`

Live task already proven:
- Express backend service with health/features endpoints

### 4. `vue_vite_web`

Use for:
- Vue landing pages
- Vue dashboards
- Vue explorer/demo style web tasks

Bootstrap:
- `package.json`
- `vite.config.ts`
- `tsconfig.json`
- `index.html`
- `src/main.ts`
- `src/App.vue`
- `src/styles.css`

Validation:
- `npm run build`
- verify `dist/index.html` exists
- verify `src/App.vue` is a non-sparse primary page surface

Live task already proven:
- Vue dashboard for an AI agent platform

### 5. `nextjs_web`

Use for:
- Next.js landing pages
- Next.js product sites
- Next.js dashboard/explorer style web tasks

Bootstrap:
- `package.json`
- `next.config.mjs`
- `tsconfig.json`
- `next-env.d.ts`
- `app/layout.tsx`
- `app/page.tsx`
- `app/globals.css`

Validation:
- `npm run build`
- verify `.next/BUILD_ID` exists
- verify `app/page.tsx` is a non-sparse primary page surface

Preview:
- `npm install --no-fund --no-audit && npm run dev`

Live task already proven:
- Next.js landing page for an AI agent platform

### 6. `svelte_vite_web`

Use for:
- Svelte landing pages
- Svelte dashboards
- Svelte explorer/demo style web tasks

Bootstrap:
- `package.json`
- `vite.config.ts`
- `tsconfig.json`
- `svelte.config.js`
- `index.html`
- `src/main.ts`
- `src/App.svelte`
- `src/app.css`

Validation:
- `npm run build`
- verify `dist/index.html` exists
- verify `src/App.svelte` is a non-sparse primary page surface

Preview:
- `python3 -m http.server 4173 --directory dist`

Live task already proven:
- Svelte landing page for an AI agent platform

## Changes landed

- Delivery routing now uses an explicit family detector instead of only
  `simple web` special-casing.
- Delivery family handling now has a first-class registry module that owns:
  - `family_id`
  - bootstrap targets
  - validation commands
  - workspace validation defaults
  - delivery-contract instructions
  - `app ship` default acceptance checks / done definitions
  - export entrypoint rules
  - preview command rules
  - development command rules
  - artifact-kind inference rules
- Delivery workspace can now bootstrap:
  - empty React/Vite web apps
  - empty Vue/Vite web apps
  - empty Svelte/Vite web apps
  - empty Next.js web apps
  - empty FastAPI API services
  - empty Node/Express API services
- Export now resolves entrypoint / preview / development commands through family
  rules instead of ad hoc branching, including the correct Python API entrypoint
  (`main.py`) instead of surfacing `requirements.txt`.
- Workspace preview / artifact-kind / default validation inference now also flow
  through family rules instead of separate executor/workspace branching.
- Workspace preview commands for web and API families now install dependencies
  before starting a dev server when the artifact is still a source workspace
  instead of a built export.
- Timeout recovery now refreshes artifact paths after successful validation so
  `app show` and `app export` surface the final built artifact (`dist/index.html`)
  instead of stale workspace-level paths.
- Delivery shell commands are sanitized at execution time so the trace no longer
  records bad `cd / && ...` root-reset commands.

## What is still not solved

- Families are still code-defined; Workbench does not yet have a dynamic plugin/registry loading model.
- Full-stack families are not proven.
- Provider stability remains a real dependency for live task success.

## Next move

Keep the registry as the single family authority, then move the remaining export/runtime
surface rules under the same family contract:

1. keep raising family-specific validation depth toward runnable-product checks
2. the next narrow family without changing the `app ship` product shape
