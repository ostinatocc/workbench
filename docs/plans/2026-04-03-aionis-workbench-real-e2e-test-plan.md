# Aionis Workbench Real E2E Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a real end-to-end test harness for `Aionis Workbench` that uses real repositories, fixed commits, local cache, real CLI/runtime/extension paths, and no mocks across the system boundary.

**Architecture:** Add a dedicated `real_e2e` harness under `workbench` that prepares a fixed corpus of real repositories, runs scenario-based flows through the actual `aionis` CLI, runtime, Aionisdoc, and extension surfaces, and records structured scenario results. Split execution into `real-e2e` for deterministic local product loops and `real-live-e2e` for model-backed nightly or manual verification.

**Tech Stack:** Python `pytest`, local git clones, JSON/TOML manifests, `aionis` CLI, `runtime-mainline`, `Aionisdoc`, VS Code/Cursor smoke harness, filesystem artifacts under `.aionis-workbench/`.

---

## Scope And Rules

This plan is intentionally strict:

- use real source repositories
- pin every repo to a specific commit SHA
- clone once, cache locally, reuse repeatedly
- do not mock Workbench, runtime, Aionisdoc, or extension boundaries
- prefer deterministic scenarios for default runs
- keep model-backed live scenarios separate from the default suite

This plan does **not** use:

- fake repo fixtures as the primary corpus
- mocked CLI calls
- mocked session persistence
- mocked doc continuity ingestion
- remote GitHub HEAD during test execution

## Proposed Test Modes

### `real-e2e`

Purpose:

- real repos
- real CLI/runtime/filesystem
- no mocks across system boundaries
- no dependency on live model output for pass/fail

This suite should be suitable for:

- local developer runs
- CI on demand
- pre-release validation

### `real-live-e2e`

Purpose:

- same real repos
- same real system boundaries
- real model-backed `run/resume` paths

This suite should be suitable for:

- nightly runs
- manual milestone checks
- product proof demos

## Corpus Strategy

Use a manifest-driven corpus.

Recommended new files:

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_repos/manifest.json`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_repos/README.md`

The manifest should define entries like:

- `id`
- `repo_url`
- `commit_sha`
- `language`
- `default_branch`
- `scenario_tags`
- `validation_commands`
- `doc_paths`
- `expected_runtime_mode`

The cache root should be:

- `/Volumes/ziel/Aioniscli/Aionis/workbench/.real-e2e-cache/`

Each cached repo should live at:

- `/Volumes/ziel/Aioniscli/Aionis/workbench/.real-e2e-cache/repos/<repo-id>/repo`

The cache metadata should include:

- `repo_url`
- `commit_sha`
- `fetched_at`
- `resolved_head`

## Initial Corpus Recommendation

Start with three real repositories:

1. small Python repo
   - good for validation, shell surfaces, doc continuity
2. mid-size TS/JS repo
   - good for registry/doc workflows and broader file layouts
3. doc/workflow-oriented repo
   - good for `.aionis.md`, publish/recover/resume, editor continuity

The exact repos should be fixed in the manifest and never float to GitHub HEAD inside test execution.

## Scenario Set

### Scenario 1: Editor-To-Dream

Real flow:

1. prepare real repo
2. bind Workbench task
3. compile/run/publish through real editor/CLI path
4. ingest continuity
5. consolidate
6. run dream
7. assert `/dream` exposes doc + editor sync evidence

### Scenario 2: Publish-Recover-Resume

Real flow:

1. prepare real repo
2. run `aionis doc publish`
3. run `aionis doc recover`
4. run `aionis doc resume`
5. inspect session continuity
6. assert `/doc show` and `/family` show a stable recovery chain

### Scenario 3: Repeated Workflow Reuse

Real flow:

1. run the same doc workflow on the same family two to three times
2. consolidate
3. assert family doc prior becomes seed-ready
4. assert `/dashboard` shows editor-driven doc reuse is live

### Scenario 4: Real Launcher Boot

Real flow:

1. run `aionis status`
2. run `aionis start`
3. verify runtime health
4. run `aionis stop`

This is a lower-level system scenario and should remain in `real-e2e`.

### Scenario 5: Live Run/Resume

Real flow:

1. run `aionis ready`
2. run real `aionis run`
3. force interruption or staged pause
4. run `aionis resume`
5. validate real session closure

This belongs only in `real-live-e2e`.

## Recommended File Layout

### Harness

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/__init__.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/manifest.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/repo_cache.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/runtime_env.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/cli_driver.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/scenario_runner.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/result_models.py`

### Tests

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_editor_to_dream.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_publish_recover_resume.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_repeated_workflow_reuse.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_launcher_runtime_cycle.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_run_resume.py`

### Scripts

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-e2e.sh`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`

## Task 1: Create the failing manifest loader

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/manifest.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_repos/manifest.json`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_manifest_loader.py`

**Step 1: Write the failing test**

Test cases:

- manifest file loads
- every repo has `id`, `repo_url`, `commit_sha`
- every repo has at least one `scenario_tag`

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_manifest_loader.py -q
```

Expected:

- FAIL because manifest loader and manifest file do not exist yet

**Step 3: Write minimal implementation**

Implement:

- `load_real_repo_manifest(path: str | None = None) -> dict`
- create a starter manifest with 3 pinned repos

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/manifest.py e2e/real_repos/manifest.json tests_real_e2e/test_manifest_loader.py
git commit -m "test: add real repo manifest loader"
```

## Task 2: Add local clone cache with fixed commit checkout

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/repo_cache.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_repo_cache.py`

**Step 1: Write the failing test**

Test cases:

- clone happens into `.real-e2e-cache/repos/<repo-id>/repo`
- second run reuses existing clone
- checkout lands on the requested `commit_sha`

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_repo_cache.py -q
```

Expected:

- FAIL because cache helper does not exist

**Step 3: Write minimal implementation**

Implement helpers:

- `ensure_repo_cached(repo_entry)`
- `repo_checkout_path(repo_entry)`
- `repo_metadata_path(repo_entry)`

Use real `git clone`, `git fetch`, and `git checkout --detach <sha>`.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/repo_cache.py tests_real_e2e/test_repo_cache.py
git commit -m "test: add real repo cache helper"
```

## Task 3: Add real CLI driver

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/cli_driver.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_cli_driver.py`

**Step 1: Write the failing test**

Test cases:

- can run `aionis status`
- captures `stdout`, `stderr`, `exit_code`
- can target a specific repo root

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_cli_driver.py -q
```

Expected:

- FAIL because the driver does not exist

**Step 3: Write minimal implementation**

Implement:

- `run_aionis(args: list[str], cwd: str | None = None, env: dict[str, str] | None = None)`

This must call the real launcher binary from:

- `/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/cli_driver.py tests_real_e2e/test_cli_driver.py
git commit -m "test: add real aionis cli driver"
```

## Task 4: Add runtime environment helper

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/runtime_env.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_runtime_env.py`

**Step 1: Write the failing test**

Test cases:

- can start local runtime
- can confirm health
- can stop runtime

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_runtime_env.py -q
```

Expected:

- FAIL because runtime helper does not exist

**Step 3: Write minimal implementation**

Implement:

- `ensure_runtime_started()`
- `wait_for_runtime_health()`
- `stop_runtime_if_started_by_test()`

Reuse the real launcher:

- `aionis start`
- `aionis status`
- `aionis stop`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/runtime_env.py tests_real_e2e/test_runtime_env.py
git commit -m "test: add runtime environment helper"
```

## Task 5: Add scenario result model

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/result_models.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_result_models.py`

**Step 1: Write the failing test**

Test cases:

- scenario result can serialize to JSON
- suite result summarizes pass/fail counts

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_result_models.py -q
```

Expected:

- FAIL because result models do not exist

**Step 3: Write minimal implementation**

Add:

- `ScenarioResult`
- `SuiteResult`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/result_models.py tests_real_e2e/test_result_models.py
git commit -m "test: add real e2e result models"
```

## Task 6: Implement Scenario 1 editor-to-dream

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_editor_to_dream.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/scenario_runner.py`

**Step 1: Write the failing test**

The scenario must:

- prepare one real repo from manifest
- ensure runtime is healthy
- create a real Workbench task
- drive a real doc workflow through Workbench/extension-compatible ingest
- run `consolidate`
- run `dream`
- assert dream surface exposes doc/editor evidence

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_editor_to_dream.py -q
```

Expected:

- FAIL because scenario runner does not exist yet

**Step 3: Write minimal implementation**

Implement a real scenario runner using:

- cached repo root
- real `aionis` CLI
- real `aionis doc ...`
- real session continuity assertions

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/scenario_runner.py tests_real_e2e/test_editor_to_dream.py
git commit -m "test: add real editor-to-dream scenario"
```

## Task 7: Implement Scenario 2 publish-recover-resume

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_publish_recover_resume.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/scenario_runner.py`

**Step 1: Write the failing test**

The scenario must:

- use a real repo
- call real `aionis doc publish`
- call real `aionis doc recover`
- call real `aionis doc resume`
- inspect persisted session JSON
- inspect `/doc show` output

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_publish_recover_resume.py -q
```

Expected:

- FAIL because the scenario is not implemented yet

**Step 3: Write minimal implementation**

Add runner support for a chained doc workflow scenario with filesystem assertions.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/scenario_runner.py tests_real_e2e/test_publish_recover_resume.py
git commit -m "test: add real publish-recover-resume scenario"
```

## Task 8: Implement Scenario 3 repeated workflow reuse

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_repeated_workflow_reuse.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_e2e/scenario_runner.py`

**Step 1: Write the failing test**

The scenario must:

- run the same family workflow multiple times on a real repo
- consolidate after repetition
- assert `family_doc_prior` becomes seed-ready
- assert dashboard proof says editor-driven doc reuse is live

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_repeated_workflow_reuse.py -q
```

Expected:

- FAIL because the scenario is not implemented yet

**Step 3: Write minimal implementation**

Add repeated-run support and proof-surface assertions.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add e2e/real_e2e/scenario_runner.py tests_real_e2e/test_repeated_workflow_reuse.py
git commit -m "test: add real repeated workflow reuse scenario"
```

## Task 9: Implement Scenario 4 launcher runtime cycle

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_launcher_runtime_cycle.py`

**Step 1: Write the failing test**

The scenario must:

- run real `aionis status`
- run real `aionis start`
- verify runtime health
- run real `aionis stop`

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_launcher_runtime_cycle.py -q
```

Expected:

- FAIL because scenario file does not exist

**Step 3: Write minimal implementation**

Use the same real CLI driver and runtime helper.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add tests_real_e2e/test_launcher_runtime_cycle.py
git commit -m "test: add real launcher runtime cycle scenario"
```

## Task 10: Add the `real-e2e` suite runner

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-e2e.sh`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the failing test**

Create a smoke assertion that:

- the runner script exists
- it invokes the `tests_real_e2e` suite

**Step 2: Run test to verify it fails**

Add a small script presence test and run it.

**Step 3: Write minimal implementation**

Runner should:

- ensure cache dir exists
- optionally warm repo cache
- run `pytest tests_real_e2e -q`

**Step 4: Run test to verify it passes**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
bash scripts/run-real-e2e.sh
```

Expected:

- suite starts and emits real scenario output

**Step 5: Commit**

```bash
git add scripts/run-real-e2e.sh README.md
git commit -m "test: add real e2e runner"
```

## Task 11: Add the `real-live-e2e` slice

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_run_resume.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the failing test**

The scenario must:

- require model credentials explicitly
- run real `aionis ready`
- run real `aionis run`
- run real `aionis resume`
- assert session closes or pauses cleanly

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_run_resume.py -q
```

Expected:

- FAIL because live scenario file does not exist

**Step 3: Write minimal implementation**

Keep this suite gated behind explicit environment checks.

**Step 4: Run test to verify it passes**

Run manually only when credentials and runtime are available.

**Step 5: Commit**

```bash
git add tests_real_live_e2e/test_live_run_resume.py scripts/run-real-live-e2e.sh README.md
git commit -m "test: add real live e2e slice"
```

## Task 12: Document corpus and operating rules

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/e2e/real_repos/README.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the failing doc check**

Add a simple documentation presence assertion if desired, or verify manually.

**Step 2: Write the documentation**

Document:

- why repos are pinned
- why GitHub HEAD is not used during runs
- how cache invalidation works
- when to run `real-e2e`
- when to run `real-live-e2e`

**Step 3: Verify documentation**

Confirm commands and paths match the implementation.

**Step 4: Commit**

```bash
git add e2e/real_repos/README.md README.md
git commit -m "docs: add real e2e corpus guide"
```

## Acceptance Criteria

This plan is complete when:

- there is a manifest of fixed real repositories
- repos are cached locally and checked out to exact SHAs
- `real-e2e` can run without mocks across system boundaries
- at least three real multi-step scenarios pass
- `real-live-e2e` exists as a separately gated suite
- README explains how to run both suites

## Risks And Guardrails

### Risk: upstream drift

Guardrail:

- always pin to exact commit SHA

### Risk: suite becomes too flaky

Guardrail:

- keep default `real-e2e` deterministic and model-free where possible
- isolate model-backed checks into `real-live-e2e`

### Risk: cache corruption

Guardrail:

- store repo metadata next to each cached clone
- verify checked-out SHA before each scenario

### Risk: tests become too slow

Guardrail:

- reuse local clones
- reuse prepared runtime where safe
- keep scenario count small and high-value

## Notes

- This plan intentionally assumes no mocks across product boundaries.
- The recommended first slice is `Editor-To-Dream`, because it exercises the most differentiated product loop.
- The current workspace is not a git repository, so commit steps are part of the implementation plan but cannot be executed in this workspace as-is.
