# Aionis App Harness Generator Slice Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the first bounded generator execution slice to the app harness so `SprintContract` and `SprintRevision` can drive one real implementation attempt instead of stopping at planning, evaluation, and retry policy.

**Architecture:** Do not introduce a second runtime or a separate autonomous builder. Build the generator slice on top of the existing Workbench platform, reusing current session persistence, reviewer substrate, app harness state, live planner/evaluator slices, and real-e2e/live-e2e harnesses. The generator slice should remain narrow: one bounded execution attempt tied to the current sprint or current revision, with explicit artifact capture, execution summary, and post-run handoff back into `app qa`.

**Tech Stack:** Python, `pytest`, existing Workbench runtime/session/orchestrator/shell/CLI services, `execution_host.py`, `runtime-mainline`, current live provider profiles, deterministic real-e2e and real-live-e2e harnesses.

---

## Why This Plan Exists

The app harness already has:

- planner artifacts
- sprint contracts
- evaluator criteria and sprint QA
- planner/evaluator negotiation
- bounded retry
- explicit policy endings
- escalated -> replanned path

What it still does **not** have is the execution layer that turns:

- a sprint contract
- or a sprint revision

into one bounded implementation attempt.

Right now the harness can decide:

- what should be built
- how it should be evaluated
- whether it should be revised, advanced, escalated, or replanned

But it cannot yet record:

- what execution target was attempted
- what files or artifacts changed
- whether the generator ran against the base sprint or a revision
- what execution summary should feed the next evaluator step

That is the missing bridge between the current planner/evaluator control plane and a real long-running application development harness.

## Target Outcome

After this plan lands, Workbench should be able to:

- persist a bounded `SprintExecutionAttempt`
- run `app generate` as a first-class operator surface
- execute against either:
  - the active sprint contract
  - the latest sprint revision
- capture a compact execution summary and changed targets
- feed that summary back into `app qa`
- prove the slice through one deterministic real-e2e scenario and one narrow real-live-e2e scenario

This plan intentionally stops short of a full autonomous multi-turn generator. It adds one explicit generator pass and the state needed to grow that into a richer loop later.

## Recommended Files

### New source files

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_generate.py`

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
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_generate.py`

### Docs

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

## Generator Slice Concepts

Minimum generator objects:

- `SprintExecutionAttempt`
- `latest_execution_attempt`
- `execution_history`
- `execution_target_kind`
- `execution_summary`

Minimum generator surfaces:

- `/app generate`
- `aionis app generate`
- `canonical_views.app_harness.latest_execution_attempt`

Minimum generator slice behavior:

- execute once per operator invocation
- bind execution to:
  - `active_sprint_contract`
  - or `latest_revision`
- capture compact outputs only:
  - execution target
  - changed target hints
  - summary
  - execution mode
  - success/failure

Minimum generator verification:

- deterministic path:
  - `plan -> sprint -> generate -> qa`
- revision path:
  - `plan -> qa -> negotiate -> retry -> generate -> qa`
- live path:
  - `plan --use-live-planner -> generate --use-live-generator -> qa --use-live-evaluator`

## Task 1: Add failing tests for execution-attempt models

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_app_harness_models.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_models.py`

**Step 1: Write the failing test**

Add tests for:

- `SprintExecutionAttempt.from_dict(...)`
- `AppHarnessState` round-tripping:
  - `latest_execution_attempt`
  - `execution_history`

Cover:

- attempt id
- sprint id
- revision id
- execution target kind
- execution mode
- changed target hints
- summary
- success/failure state

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_app_harness_models.py -q
```

Expected:

- FAIL because the execution-attempt model does not exist yet

**Step 3: Write minimal implementation**

Add:

- `SprintExecutionAttempt`
- `latest_execution_attempt`
- `execution_history`

Keep the first shape narrow and deterministic.

**Step 4: Run test to verify it passes**

Run the same targeted suite and expect PASS.

## Task 2: Add bounded execution derivation in the app harness service

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a service-level test proving:

- the generator slice can derive an execution target from:
  - the active sprint
  - or the latest revision
- one execution attempt is recorded
- the attempt captures:
  - `execution_target_kind`
  - `execution_summary`
  - `changed_target_hints`

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py::test_product_app_harness_records_bounded_execution_attempt -q
```

Expected:

- FAIL because no execution-attempt behavior exists yet

**Step 3: Write minimal implementation**

Add service methods:

- `derive_execution_attempt(...)`
- `record_execution_attempt(...)`
- `apply_execution_outcome(...)`

The first slice should:

- prefer `latest_revision` when one exists and is still current
- otherwise target the active sprint
- stay artifact-first and compact
- not try to execute a full autonomous loop

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

## Task 3: Expose execution state in canonical views

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a canonical-view test proving `inspect_session()` exposes:

- `latest_execution_attempt`
- `execution_history_count`
- `execution_target_kind`
- `execution_mode`
- `execution_summary`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because app harness canonical view does not yet include execution state

**Step 3: Write minimal implementation**

Extend `canonical_views.app_harness` with concise execution summaries only.

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

## Task 4: Add `app generate` to runtime

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a runtime-level test proving:

- `app_generate(...)` records an execution attempt
- it binds to the right sprint/revision
- it persists the attempt into session state

**Step 2: Run test to verify it fails**

Expected:

- FAIL because runtime does not expose `app_generate(...)`

**Step 3: Write minimal implementation**

Add:

- `app_generate(...)`

This should:

- load the session
- derive the execution attempt
- persist it
- return `inspect_session(...)` with `shell_view=app_generate`

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

## Task 5: Add CLI and shell surfaces

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Step 1: Write the failing tests**

Add parser/dispatch/render tests for:

- `aionis app generate --task-id ... [--sprint-id ...] [--use-live-generator]`
- `/app generate [TASK_ID] [--sprint-id ...] [--live]`

**Step 2: Run tests to verify they fail**

Expected:

- FAIL because the command does not exist yet

**Step 3: Write minimal implementation**

Add:

- CLI parser branch
- shell dispatch branch
- shell rendering for `app_generate`

Keep rendering compact and consistent with current app harness surfaces.

**Step 4: Run test to verify it passes**

Run targeted CLI/shell suites and expect PASS.

## Task 6: Add a deterministic generator summary slice

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a deterministic behavior test proving:

- `app_generate` produces a stable `execution_summary`
- summary reflects the current target:
  - base sprint
  - or revision
- summary contains compact changed target hints

**Step 2: Run test to verify it fails**

Expected:

- FAIL because generation summary is still empty or unstable

**Step 3: Write minimal implementation**

For the deterministic slice:

- derive summary from the sprint goal, current revision, and top scope items
- do not pretend the code has been autonomously written yet
- treat this as an execution-intent artifact

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

## Task 7: Add a live generator slice

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_host.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a narrow runtime/service test proving:

- `app_generate(..., use_live_generator=True)` records:
  - `execution_mode=live`
  - a compact generator-produced execution summary

**Step 2: Run test to verify it fails**

Expected:

- FAIL because no live generator path exists yet

**Step 3: Write minimal implementation**

Add a compact `live_app_generator(...)` path in `execution_host.py`.

The prompt should only ask for:

- the immediate implementation target
- compact changed target hints
- a short execution summary

Do not ask the live generator to run an unbounded coding loop in this first slice.

**Step 4: Run test to verify it passes**

Run targeted deterministic suites and expect PASS.

## Task 8: Add deterministic real-e2e coverage

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py`

**Step 1: Extend the real scenario**

Upgrade the deterministic app harness scenario from:

- `plan -> sprint -> qa -> negotiate -> retry -> qa`

to:

- `plan -> sprint -> generate -> qa`

or

- `plan -> qa -> negotiate -> retry -> generate -> qa`

depending on which path is more stable.

**Step 2: Verify the scenario fails first**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_app_harness_planner_contract.py -q
```

Expected:

- FAIL until generator state is wired through

**Step 3: Make it pass**

Assert:

- `latest_execution_attempt.attempt_id`
- `execution_mode`
- `execution_target_kind`
- `execution_history_count`

## Task 9: Add narrow real-live-e2e coverage

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_generate.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`

**Step 1: Add a skip-gated live test**

Cover the narrowest stable path:

- `app plan --use-live-planner`
- `app generate --use-live-generator`
- `app qa --use-live-evaluator`

**Step 2: Verify the test skips cleanly without credentials**

Expected:

- `skipped`, not failed, in non-live shells

**Step 3: Run one credentialed reference pass**

Capture:

- provider profile
- timing
- `execution_mode=live`
- persisted execution summary

## Task 10: Update status docs and README

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Update status**

Document:

- what the generator slice does
- what it still does not do
- current deterministic and live verification coverage

**Step 2: Update README**

Add:

- `app generate`
- live generator coverage entry

## Acceptance Criteria

This plan is complete when:

- Workbench persists a bounded `SprintExecutionAttempt`
- `app generate` exists in runtime, shell, and CLI
- generator attempts bind to the right sprint/revision target
- canonical views expose compact execution state
- deterministic real-e2e covers at least one generator path
- narrow real-live-e2e covers at least one live generator path
- docs clearly describe the slice as a bounded execution layer, not a full autonomous builder

## Out of Scope

Do not include in this slice:

- unbounded coding loops
- multi-turn autonomous implementation
- browser/Playwright execution
- automatic git commits or PR creation
- replacing the existing orchestrator runtime

Those belong to later app-harness phases.

## Recommended Execution Order

1. model + state
2. service + canonical view
3. runtime + CLI/shell
4. deterministic generator summary
5. live generator slice
6. real-e2e
7. real-live-e2e
8. docs

That order keeps the slice narrow, testable, and aligned with the current Workbench architecture.
