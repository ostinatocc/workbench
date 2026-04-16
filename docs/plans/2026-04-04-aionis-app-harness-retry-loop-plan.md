# Aionis App Harness Retry Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a bounded generator/evaluator retry loop to the app harness so a failed sprint can produce one structured revision attempt instead of stopping at negotiation notes.

**Architecture:** Build on the existing app harness phase-2 substrate instead of introducing a separate runtime or autonomous loop. Reuse the current `app plan`, `app qa`, and `app negotiate` artifacts, then add a first-class revision object plus a narrow `app retry` operator that records one bounded revision attempt. The first slice should support deterministic and opt-in live revision planning, persist retry metadata in session state, and prove the loop through deterministic real-e2e plus a short real-live-e2e path.

**Tech Stack:** Python, `pytest`, existing Workbench runtime/session/shell/CLI services, `execution_host.py`, real-e2e and real-live-e2e harnesses, current provider profile/live profile infrastructure.

---

## Why This Plan Exists

The current app harness can already:

- plan a product spec and initial sprint
- evaluate a sprint with deterministic or live evaluator slices
- negotiate a revision with deterministic or live planner slices

What it cannot yet do is turn that negotiation result into a bounded revision loop. Right now the harness can explain:

- why a sprint failed
- what the planner wants to revise

but it cannot persist:

- a specific revision artifact
- a retry budget
- a retry count
- a clear before/after summary of what changed between attempts

That gap is the difference between a planner/evaluator demo and a real long-running app harness. This plan closes that gap with a deliberately narrow first revision loop.

## Target Outcome

After this plan lands, Workbench should be able to:

- persist a `SprintRevision` artifact tied to a negotiation round
- expose a bounded `retry_budget` and `retry_count`
- run `app retry` as a first-class operator surface
- capture what changed between revision attempts
- re-run `app qa` after a revision and compare the outcome against the previous evaluation
- prove the narrow loop through deterministic and live scenario coverage

This plan intentionally stops short of a full autonomous generator/evaluator loop. It adds one bounded revision attempt and the evidence needed to grow that into a richer loop later.

## Recommended Files

### New source files

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_retry.py`

### Likely modified source files

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_models.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_host.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`

### Tests

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_app_harness_models.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_retry.py`

### Docs

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

## Phase-2 Retry Concepts

Minimum retry-loop objects:

- `SprintRevision`
- `revision_history`
- `retry_budget`
- `retry_count`
- `revision_diff_summary`

Minimum retry-loop surfaces:

- `/app retry`
- `aionis app retry`
- `canonical_views.app_harness.latest_revision`

Minimum retry-loop verification:

- deterministic round trip:
  - `plan -> sprint -> qa -> negotiate -> retry -> qa`
- live round trip:
  - `plan --use-live-planner -> qa --use-live-evaluator -> negotiate --use-live-planner -> retry --use-live-planner`

## Task 1: Add failing tests for revision models

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_app_harness_models.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_models.py`

**Step 1: Write the failing test**

Add tests for:

- `SprintRevision.from_dict(...)`
- `AppHarnessState` round-tripping a `latest_revision`
- revision history and retry metadata normalization

Cover:

- revision id
- source sprint id
- source negotiation action
- must-fix items
- must-keep items
- retry budget and retry count

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_app_harness_models.py -q
```

Expected:

- FAIL because the revision model does not exist yet

**Step 3: Write minimal implementation**

Add:

- `SprintRevision`
- `latest_revision`
- `revision_history`
- `retry_budget`
- `retry_count`

Keep the first shape minimal and deterministic.

**Step 4: Run test to verify it passes**

Run the same targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_app_harness_models.py src/aionis_workbench/app_harness_models.py
git commit -m "feat: add app harness revision models"
```

## Task 2: Add deterministic revision derivation in the app harness service

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a service-level test proving:

- a failed evaluation + negotiation can produce one revision artifact
- retry budget defaults to `1`
- retry count increments to `1` after `retry`
- revision preserves `must_fix` and `must_keep`

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py::test_product_app_harness_service_derives_bounded_revision -q
```

Expected:

- FAIL because `retry` behavior does not exist yet

**Step 3: Write minimal implementation**

Add service methods:

- `derive_sprint_revision(...)`
- `apply_revision_attempt(...)`
- `compare_revision_outcome(...)`

The first slice should:

- derive revision targets from the latest negotiation round
- preserve explicit objections
- keep retry budget bounded to one attempt unless explicitly expanded later

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/app_harness_service.py tests/test_product_workflows.py
git commit -m "feat: add bounded app harness revision service"
```

## Task 3: Expose revision state in canonical views

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a canonical-view test proving `inspect_session()` exposes:

- `latest_revision`
- `revision_history_count`
- `retry_budget`
- `retry_count`
- `revision_diff_summary`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because app harness canonical view does not yet include revision state

**Step 3: Write minimal implementation**

Extend `canonical_views.app_harness` with concise revision summaries only.

Do not dump large free-form blobs into the canonical view.

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/evaluation_service.py tests/test_product_workflows.py
git commit -m "feat: expose app harness revision state"
```

## Task 4: Add `app retry` to runtime

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a runtime test proving:

- `workbench.app_retry(...)` exists
- it persists a revision artifact
- it increments retry metadata
- it returns `shell_view="app_retry"`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because runtime does not yet expose retry

**Step 3: Write minimal implementation**

Add:

- `app_retry(...)`

Inputs should include:

- `task_id`
- `sprint_id`
- optional `revision_note`
- optional `use_live_planner`

The first slice should not mutate files or invoke a generator. It should only create the structured revision attempt artifact.

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime.py tests/test_product_workflows.py
git commit -m "feat: add app retry runtime surface"
```

## Task 5: Add shell and CLI operator surfaces

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Step 1: Write the failing test**

Add parser/dispatch/render tests for:

- `aionis app retry --task-id ... --sprint-id ...`
- `aionis app retry --task-id ... --sprint-id ... --use-live-planner`
- `/app retry [TASK_ID] --sprint-id ...`
- `/app retry [TASK_ID] --sprint-id ... --live`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because parser and dispatch do not know about `retry`

**Step 3: Write minimal implementation**

Add:

- CLI subcommand: `retry`
- shell surface: `/app retry`
- compact rendering with:
  - retry count
  - retry budget
  - revision action
  - planner mode

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py src/aionis_workbench/shell_dispatch.py src/aionis_workbench/shell.py tests/test_cli_shell.py tests/test_shell_dispatch.py
git commit -m "feat: add app retry shell and cli surfaces"
```

## Task 6: Add live revision planning in the execution host

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_host.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a runtime/service test proving:

- a live retry path can request a compact revision object
- the returned revision object includes:
  - `must_fix`
  - `must_keep`
  - `revision_summary`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because the execution host does not yet support live revision planning

**Step 3: Write minimal implementation**

Add `revise_sprint_live(...)` with:

- strict JSON-only contract
- small token budget
- one-sprint context only

Do not add a full generator or multi-turn loop here.

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/execution_host.py tests/test_product_workflows.py
git commit -m "feat: add live app revision planner slice"
```

## Task 7: Extend the deterministic real-e2e app harness scenario

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py`

**Step 1: Write the failing test**

Extend the real deterministic scenario to exercise:

1. real `app plan`
2. real `app sprint`
3. real `app qa`
4. real `app negotiate`
5. real `app retry`
6. real `inspect_session`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because `retry` does not yet exist in the scenario

**Step 3: Write minimal implementation**

Update scenario details to assert:

- revision artifact exists
- retry count is `1`
- loop state changes from pure negotiation into a revision-tracking state

**Step 4: Run test to verify it passes**

Run the deterministic real-e2e case and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/e2e/real_e2e/scenario_runner.py tests_real_e2e/test_app_harness_planner_contract.py
git commit -m "test: cover app retry deterministic e2e"
```

## Task 8: Add a narrow real-live-e2e retry scenario

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_retry.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`

**Step 1: Write the failing test**

Create a live scenario that verifies:

1. real `app plan --use-live-planner`
2. real `app qa --use-live-evaluator`
3. real `app negotiate --use-live-planner`
4. real `app retry --use-live-planner`
5. persisted revision metadata

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_retry.py -q
```

Expected:

- SKIP without credentials
- FAIL in a live-ready environment until retry support exists

**Step 3: Write minimal implementation**

Reuse the existing live harness style:

- gate on live readiness
- keep the scenario short
- persist timing and provider metadata

**Step 4: Run test to verify it passes**

Run the targeted live test in a credentialed environment and expect PASS.

**Step 5: Commit**

```bash
git add tests_real_live_e2e/test_live_app_retry.py src/aionis_workbench/e2e/real_e2e/scenario_runner.py scripts/run-real-live-e2e.sh
git commit -m "test: add live app retry scenario"
```

## Task 9: Add revision-aware summary rendering

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

Add a render test proving app harness surfaces show:

- revision action
- retry count/budget
- revision planner mode

**Step 2: Run test to verify it fails**

Expected:

- FAIL because summary text does not yet include retry state

**Step 3: Write minimal implementation**

Keep rendering compact:

- `retry=1/1`
- `revision=revise_current_sprint@live`

Do not add verbose prose.

**Step 4: Run test to verify it passes**

Run the targeted shell/CLI render tests and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/shell.py tests/test_cli_shell.py
git commit -m "feat: render app retry state"
```

## Task 10: Update status and operator docs

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the failing doc checklist**

Document:

- what `app retry` does
- what it does not do yet
- which live tests prove it

**Step 2: Verify the docs are stale before editing**

Search for missing `app retry` references.

**Step 3: Update docs**

Add:

- operator examples
- deterministic/live retry coverage
- current limitations

**Step 4: Re-run the relevant suites**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_app_harness_models.py tests/test_product_workflows.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests_real_e2e/test_app_harness_planner_contract.py tests_real_live_e2e/test_live_app_retry.py -q
```

Expected:

- PASS, with live test skipping without credentials

**Step 5: Commit**

```bash
git add docs/plans/2026-04-04-aionis-long-running-app-harness-status.md README.md
git commit -m "docs: update app retry harness status"
```

## Acceptance Criteria

This plan is done when all of the following are true:

- `app retry` exists in runtime, CLI, and shell
- revision metadata persists in session state
- deterministic app harness real-e2e covers retry
- a narrow live retry scenario exists
- app harness surfaces clearly show retry state
- status docs reflect the new loop boundary accurately

## Non-Goals

This plan does **not** attempt to build:

- a fully autonomous generator agent
- multi-attempt retry budgets greater than one
- browser-driven QA
- automatic code mutation during retry

Those belong to the next phase after this bounded revision slice.
