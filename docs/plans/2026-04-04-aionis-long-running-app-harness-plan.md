# Aionis Long-Running App Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a first-class long-running application development harness on top of Workbench's existing continuity, workflow asset, reviewer, and live validation layers.

**Architecture:** Do not replace Workbench. Build a new harness layer on top of the existing platform. Reuse current continuity, reviewer substrate, doc workflows, live validation, and learning systems, then add the missing app-harness pieces: planner artifacts, sprint contracts, evaluator criteria, and generator/evaluator loop state. Phase 1 should make these concepts first-class in packet/session/surface layers before attempting a full autonomous app-builder loop.

**Tech Stack:** Python, `pytest`, existing Workbench runtime/session/orchestrator/shell services, `runtime-mainline`, `Aionisdoc`, real-e2e/live-e2e infrastructure.

---

## Why This Plan Exists

Workbench now already has most of the substrate needed for long-running autonomous application development:

- continuity, resume, recovery
- workflow assets through `Aionisdoc`
- reviewer substrate and review-pack hydration
- live validation and provider profiles
- family priors and AutoDream

What it does **not** yet have is the harness layer described in the Anthropic long-running app harness article:

- planner-produced product spec
- sprint contract as a first-class artifact
- evaluator criteria and sprint QA records
- explicit app-harness loop state

This plan adds those missing objects and surfaces without pretending phase 1 is already a full planner/generator/evaluator system.

## Target Outcome

After this plan lands, Workbench should be able to:

- persist a planner-produced app spec
- persist negotiated sprint contracts
- persist evaluator criteria and sprint QA outcomes
- expose app-harness state in shell/CLI surfaces
- use that state as the stable substrate for a later planner/generator/evaluator loop

This phase intentionally stops short of a fully autonomous application builder. It creates the contract layer and operating surfaces first.

## Recommended Files

### New source files

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_models.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_app_harness_models.py`

### Likely modified source files

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/workflow_surface_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py`

### Tests

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py`

### Docs

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`

## Phase 1 Concepts

Minimum phase-1 app harness objects:

- `ProductSpec`
- `SprintContract`
- `EvaluatorCriterion`
- `SprintEvaluation`
- `AppHarnessState`

Minimum phase-1 surfaces:

- `/app plan`
- `/app sprint`
- `/app qa`
- `/app show`

Minimum phase-1 persistence:

- session-level harness state
- canonical views for planner/sprint/evaluator summaries

## Task 1: Add failing tests for app harness models

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_app_harness_models.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_models.py`

**Step 1: Write the failing test**

Test these round-trips:

- `EvaluatorCriterion.from_dict(...)`
- `SprintContract.from_dict(...)`
- `ProductSpec.from_dict(...)`
- `AppHarnessState.from_dict(...)`

The tests should prove:

- optional fields normalize cleanly
- nested lists round-trip
- empty or malformed inputs return `None`

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_app_harness_models.py -q
```

Expected:

- FAIL because the file and models do not exist yet

**Step 3: Write minimal implementation**

Add dataclasses with:

- `to_dict()`
- `from_dict(...)`

Keep phase 1 minimal and deterministic.

**Step 4: Run test to verify it passes**

Run the same targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_app_harness_models.py src/aionis_workbench/app_harness_models.py
git commit -m "feat: add app harness models"
```

## Task 2: Persist app harness state in sessions

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Create a session persistence test proving:

- `SessionState` can store `app_harness_state`
- save/load round-trips nested planner/sprint/evaluator data

**Step 2: Run test to verify it fails**

Run the targeted persistence case and confirm missing-field failure.

**Step 3: Write minimal implementation**

Add:

- `app_harness_state` to `SessionState`
- load-time normalization to `AppHarnessState.from_dict(...)`

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/session.py tests/test_product_workflows.py
git commit -m "feat: persist app harness state in sessions"
```

## Task 3: Add a minimal app harness service

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add tests for:

- creating a `ProductSpec` from structured input
- attaching a first `SprintContract`
- recording a `SprintEvaluation`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because the service does not exist yet

**Step 3: Write minimal implementation**

Provide deterministic service methods:

- `plan_app(...)`
- `set_sprint_contract(...)`
- `record_sprint_evaluation(...)`
- `app_state_summary(...)`

These should mutate a session and return stable payloads.

**Step 4: Run test to verify it passes**

Run the targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/app_harness_service.py tests/test_product_workflows.py
git commit -m "feat: add app harness service"
```

## Task 4: Expose app harness state through runtime and canonical views

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a test proving `inspect_session()` exposes:

- planner summary
- active sprint summary
- evaluator summary

**Step 2: Run test to verify it fails**

Expected:

- FAIL because canonical views do not include app harness yet

**Step 3: Write minimal implementation**

Add `app_harness` canonical view with:

- `product_spec`
- `active_sprint_contract`
- `latest_sprint_evaluation`
- `loop_status`

**Step 4: Run test to verify it passes**

Run targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime.py src/aionis_workbench/evaluation_service.py tests/test_product_workflows.py
git commit -m "feat: surface app harness canonical views"
```

## Task 5: Add `/app show` and `/app plan` shell surfaces

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

Add shell-dispatch and render tests for:

- `/app show`
- `/app plan`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because the shell commands do not exist

**Step 3: Write minimal implementation**

Add:

- command parsing
- runtime routing
- render lines for product spec and active sprint contract

**Step 4: Run test to verify it passes**

Run the targeted shell suites and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/shell_dispatch.py src/aionis_workbench/shell.py tests/test_shell_dispatch.py tests/test_cli_shell.py
git commit -m "feat: add app shell surfaces"
```

## Task 6: Add `/app sprint` and `/app qa`

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

Add tests for:

- updating sprint contract
- recording sprint QA result
- rendering evaluator thresholds and pass/fail summary

**Step 2: Run test to verify it fails**

Expected:

- FAIL because sprint/qa surfaces do not exist

**Step 3: Write minimal implementation**

Add:

- `/app sprint`
- `/app qa`

Keep it deterministic and artifact-based.

**Step 4: Run test to verify it passes**

Run the targeted shell suites and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/shell_dispatch.py src/aionis_workbench/shell.py tests/test_shell_dispatch.py tests/test_cli_shell.py
git commit -m "feat: add sprint and qa app surfaces"
```

## Task 7: Add non-interactive CLI for app harness

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

Add parser and main-path tests for:

- `aionis app show`
- `aionis app plan`
- `aionis app sprint`
- `aionis app qa`

**Step 2: Run test to verify it fails**

Expected:

- FAIL because CLI app subcommands do not exist

**Step 3: Write minimal implementation**

Wire the new runtime service into CLI.

**Step 4: Run test to verify it passes**

Run the targeted CLI suite and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py tests/test_cli_shell.py
git commit -m "feat: add app harness cli"
```

## Task 8: Add a real-e2e scenario for planner-to-contract flow

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`

**Step 1: Write the failing test**

Create a scenario that uses a real pinned repo and real Workbench shell/CLI boundaries to:

- create an app spec
- attach a sprint contract
- record a QA result
- inspect resulting app harness state

**Step 2: Run test to verify it fails**

Expected:

- FAIL until app harness surfaces exist

**Step 3: Write minimal implementation**

Add a compact deterministic real-e2e scenario runner.

**Step 4: Run test to verify it passes**

Run the targeted real-e2e test and expect PASS.

**Step 5: Commit**

```bash
git add tests_real_e2e/test_app_harness_planner_contract.py src/aionis_workbench/e2e/real_e2e/scenario_runner.py
git commit -m "test: add app harness real e2e scenario"
```

## Task 9: Add status documentation

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the status doc**

Document:

- what phase 1 landed
- what phase 1 explicitly does not yet include
- current surfaces
- current tests

**Step 2: Verify links and references**

Open the new doc and README references and confirm paths are correct.

**Step 3: Commit**

```bash
git add docs/plans/2026-04-04-aionis-long-running-app-harness-status.md README.md
git commit -m "docs: add app harness status"
```

## Task 10: Define phase-2 handoff

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`

**Step 1: Capture phase-2 gaps**

Write the next-layer items explicitly:

- planner agent
- evaluator agent
- sprint negotiation loop
- generator/evaluator retry loop
- Playwright-backed QA

**Step 2: Verify it is clearly separated from phase 1**

Make sure the document does not imply phase 2 already exists.

**Step 3: Commit**

```bash
git add docs/plans/2026-04-04-aionis-long-running-app-harness-status.md
git commit -m "docs: define app harness phase two handoff"
```
