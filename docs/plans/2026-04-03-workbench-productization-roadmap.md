# Workbench Productization Roadmap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn Workbench from a technically solid internal shell into a more obviously valuable product by improving default workflow clarity, reuse visibility, and product-path verification.

**Architecture:** Keep the current service split intact and focus on product-facing surfaces first. The next phase should avoid broad refactors and instead strengthen the default shell workflow, add explicit reuse/value summaries, lower setup friction, and add product-path tests around the existing `runtime`/`surface_service`/`shell` boundary.

**Tech Stack:** Python 3.11+, `argparse`, existing `aionis_workbench` shell/runtime services, `pytest`.

---

## Product Thesis

Workbench's differentiator is not one-shot code generation. Its product value is:

- persistent task memory
- same-family reuse
- recovery and rollback continuity
- project-scoped learning across many runs

The roadmap should therefore optimize for one thing above all else:

- users should quickly understand why Workbench is helping on this task right now

## Phase 1: Make Value Legible

### Task 1: Add explicit value and reuse summaries to `/work`, `/plan`, and `/review`

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Goal:** Expose stable product-facing summaries that explain:

- whether reuse is actually available
- whether the current family prior is seed-ready
- whether the next validation path is focused enough to trust

**Acceptance:**

- `/work`, `/plan`, and `/review` payloads expose `value_summary`
- `/work`, `/plan`, and `/review` payloads expose `reuse_summary`
- shell rendering shows those summaries before the raw JSON block

Implemented notes:

- `shell_dispatch.py` now emits stable `value_summary` and `reuse_summary` payload fields for `/work`, `/plan`, and `/review`
- `shell.py` renders those summaries directly in the main shell surface
- regression coverage lives in `tests/test_cli_shell.py` and `tests/test_shell_dispatch.py`

### Task 2: Surface reuse proof in dashboard and family views

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_bootstrap.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Goal:** Make dashboard/family views answer:

- what was reused
- how often it is working
- what is still blocked

**Acceptance:**

- dashboard summary shows seed-ready vs blocked family priors clearly
- family view shows one short “why this family is reusable or not” sentence

Implemented notes:

- `ops_service.py` now computes `proof_summary` and prior-seed summaries
- `/family` now renders `value_summary`, `reuse_summary`, and `prior_seed_summary`
- `/dashboard` now surfaces whether reuse is already live or still blocked by weak priors

## Phase 2: Make the Default Workflow Obvious

### Task 3: Tighten the default shell workflow

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Goal:** Make `/init -> /doctor -> /run -> /work -> /next -> /fix -> /validate` feel like one opinionated workflow instead of a command set.

**Acceptance:**

- `/work` highlights the next recommended operator action
- `/next` and `/fix` explain why they chose validation vs display-only paths
- bootstrap fallback tells the user the first narrow step more directly

Implemented notes:

- `shell_dispatch.py` now emits `workflow_path` and `recommended_command` for `/work`, `/plan`, and `/review`
- `shell.py` now renders the opinionated workflow path directly in bootstrap, `/work`, `/plan`, and `/review`
- `/work` now makes the default operator path explicit: `/work -> /next -> /fix -> /validate`
- `/plan` and `/review` now show a concrete next command instead of relying only on the generic `suggested=` hint

### Task 4: Improve degraded-mode guidance

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Goal:** Make inspect-only mode feel like a valid product mode, not just a failed live mode.

**Acceptance:**

- degraded/live-preflight surfaces recommend the next best inspect-only path
- setup/doctor output is shorter and more action-oriented

Implemented notes:

- blocked `host_error` and `live_preflight` surfaces now lead with the inspect-only continuation path, then show the live repair action separately
- `doctor`, `setup`, `doctor_summary`, and `setup_summary` now explicitly state that inspect-only remains usable
- CLI output for `doctor/setup/live_preflight/host_error` now defaults to the structured shell surface instead of raw JSON
- one-line modes remain unchanged

## Phase 3: Lower Adoption Friction

### Task 5: Add a stronger cold-start happy path

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/bootstrap.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_bootstrap.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Goal:** Make a fresh repo feel useful before any live execution succeeds.

**Acceptance:**

- bootstrap surfaces clearly explain the first narrow task
- bootstrap reuse notes are concise and directly actionable

Implemented notes:

- `bootstrap.py` now emits `bootstrap_focus`, `bootstrap_first_step`, `bootstrap_validation_step`, and `bootstrap_reuse_summary`
- bootstrap shell surfaces now lead with the focus slice, first narrow step, and first validation action instead of relying on a generic `next_action` alone
- cold-start reuse messaging is now concise: either a recent prior / learning hint, or an explicit “first validated success seeds reuse” note
- regression coverage was added in `tests/test_bootstrap.py` and `tests/test_cli_shell.py`

### Task 6: Add a single-command readiness path

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Goal:** Reduce first-time setup friction.

**Acceptance:**

- one command gives repo init/setup/doctor guidance in one place
- docs show the shortest getting-started path

Implemented notes:

- `cli.py` now exposes `aionis ready --repo-root ...`
- `ready` combines setup blockers, doctor state, and the final shell launch command into one structured surface
- `ready` exits `0` when `live_ready=True` and `1` otherwise, so it can be used both interactively and in lightweight scripts
- `README.md` now treats `aionis ready` as the shortest first-time path

## Phase 4: Prove the Product Path

### Task 7: Add product-path regression tests

Status: completed on 2026-04-03

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Goal:** Test the user-visible workflow, not only module internals.

**Scenarios:**

- cold-start repo
- run success
- validate success with auto-learning
- ingest external work
- backfill legacy session
- family prior becomes seed-ready

Implemented notes:

- `tests/test_product_workflows.py` now covers six product-path scenarios through the public `AionisWorkbench` surfaces
- cold-start, run-success wrapping, validate auto-learning, ingest continuity, legacy backfill, and seed-ready consolidation are now locked as regression contracts
- the `run` scenario uses an orchestration stub so the product contract is tested without depending on live runtime/execution availability

## Phase 5: Contain the Next Hotspot

### Task 8: Split `surface_service.py` by product slice

Status: completed on 2026-04-03

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/workflow_surface_service.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/backfill_service.py`
- Test: related shell/bootstrap tests

**Goal:** Prevent `surface_service.py` from becoming the next monolith.

**Acceptance:**

- evaluation/status logic is isolated
- workflow shell actions are isolated
- backfill/maintenance logic is isolated

Implemented notes:

- `surface_service.py` is now reduced to shared bootstrap/learning/session-persistence orchestration plus thin delegation
- evaluation and status surfaces now live in `evaluation_service.py`
- validate/workflow actions now live in `workflow_surface_service.py`
- legacy recovery normalization and backfill now live in `backfill_service.py`
- `surface_service.py` dropped to 505 lines from the previous 1093-line hotspot

## Milestones

### Milestone A

- `/work`, `/plan`, `/review` clearly explain reuse value
- users can tell whether a family prior is trustworthy without reading raw JSON

### Milestone B

- default workflow is opinionated and low-friction
- inspect-only mode feels intentionally useful

### Milestone C

- cold-start setup is easier
- product-path tests protect the shell contract

## Success Metrics

Treat these as the product signals to optimize:

- a user can understand the recommended next step from `/work` alone
- a user can tell whether reuse is real from `/plan` or `/review` in under 10 seconds
- bootstrap mode gives one concrete first action
- product-path regressions are caught by dedicated tests, not discovered by manual shell use

## Immediate Execution Batch

Completed now:

1. Task 1: add `value_summary` and `reuse_summary` to `/work`, `/plan`, and `/review`
2. Task 2: dashboard/family proof enhancements
3. Task 3: default workflow tightening
4. Task 4: degraded-mode guidance
5. Task 5: stronger cold-start happy path
6. Task 6: single-command readiness path
7. Task 7: product-path regression tests
8. Task 8: `surface_service.py` split

## Latest Verification

- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_shell_dispatch.py tests/test_cli_shell.py -q`
  - `131 passed`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py -q`
  - `27 passed`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py tests/test_product_workflows.py tests/test_cli_shell.py -q`
  - `120 passed`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
  - `6 passed`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_recovery_service.py tests/test_runtime_bridge_contracts.py tests/test_product_workflows.py -q`
  - `175 passed`
