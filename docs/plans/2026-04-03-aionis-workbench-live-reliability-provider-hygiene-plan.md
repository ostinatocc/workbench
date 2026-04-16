# Aionis Workbench Live Reliability And Provider Hygiene Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `Aionis Workbench` live execution faster, more repeatable, safer to operate with real providers, and releasable with explicit verification gates.

**Architecture:** Add a small reliability layer around the existing live path instead of rewriting orchestration. The work splits into four tracks: timing/profile capture, explicit provider profiles, secret/provider hygiene, and release-time live verification gates. Each track should land incrementally and be useful on its own.

**Tech Stack:** Python, `pytest`, existing Workbench CLI/runtime/orchestrator modules, environment variables, JSON/TOML profile files, shell scripts, live `real-live-e2e`.

---

## Why This Plan Exists

`real-live-e2e` is now real and green, but two product risks are still obvious:

- live scenarios are slower than they should be
- provider usage is still too ad hoc for safe release work

The next phase should not add more capability first. It should make the current live capability:

- measurable
- tunable
- safer to run
- easier to release with confidence

This plan is intentionally conservative:

- do not redesign the live execution model
- do not add a new provider abstraction layer bigger than needed
- do not block local deterministic work on model credentials
- keep `real-live-e2e` split into short slices

## Target Outcome

After this plan lands, Workbench should be able to answer:

- where live time is being spent
- which provider profile is active
- whether the current provider is approved for release verification
- whether secrets were sourced safely
- whether release gates for deterministic and live suites were satisfied

## Tracks

This plan is split into four tracks and should be implemented in this order:

1. live timing and profiling
2. provider profiles
3. secret and provider hygiene
4. release gates and reporting

Do not reverse this order. Later tracks depend on the output of earlier ones.

## Recommended Files

### New source files

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/live_profile.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/provider_profiles.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/release_gates.py`

### Likely modified source files

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`

### Tests

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_live_profile.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_provider_profiles.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_release_gates.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_run_pause.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_resume_complete.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

### Scripts and docs

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-release-gates.sh`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionis-provider-setup-guide.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionis-workbench-live-reliability-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

## Provider Model

This plan should standardize provider configuration around explicit profiles.

Minimum profile fields:

- `provider_id`
- `label`
- `base_url`
- `model`
- `timeout_seconds`
- `max_completion_tokens`
- `supports_live`
- `release_tier`
- `env_var_names`

First supported profiles:

- `zai_glm51_coding`
- `openai_default`
- `openrouter_default`

## Live Profile Model

This plan should standardize live execution modes.

Minimum live modes:

- `fast_inspect`
- `targeted_fix`
- `heavy_recovery`

Each mode should define:

- `timeout_seconds`
- `max_completion_tokens`
- `allow_resume`
- `allow_multi_validation`
- `prompt_budget_hint`

## Release Gate Model

Release validation should not be informal anymore.

Minimum required gates:

- deterministic `real-e2e` suite green
- split `real-live-e2e` suite green on one approved provider profile
- active provider profile recorded
- current live timing report recorded

## Task 1: Add failing tests for live timing records

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_live_profile.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/live_profile.py`

**Step 1: Write the failing test**

Test cases:

- a live timing record can store named phases
- total duration is computed from phase durations
- the record can render a compact summary string

Example test shape:

```python
def test_live_timing_record_summarizes_phases():
    record = LiveTimingRecord(task_id="task-1")
    record.add_phase("ready", 1.2)
    record.add_phase("run", 12.5)
    assert record.total_duration_seconds == 13.7
    assert "ready=1.2s" in record.summary()
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_live_profile.py -q
```

Expected:

- FAIL because `live_profile.py` does not exist yet

**Step 3: Write minimal implementation**

Implement:

- `LiveTimingPhase`
- `LiveTimingRecord`
- `add_phase(...)`
- `summary()`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/live_profile.py tests/test_live_profile.py
git commit -m "test: add live timing record"
```

## Task 2: Capture timing in scenario runner

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_run_pause.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_resume_complete.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_live_profile.py`

**Step 1: Write the failing test**

Add assertions that live scenario results now expose timing sections such as:

- `ready_duration_seconds`
- `run_duration_seconds`
- `resume_duration_seconds`
- `total_duration_seconds`

**Step 2: Run the targeted test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_run_pause.py tests_real_live_e2e/test_live_resume_complete.py -q
```

Expected:

- FAIL because timing fields are not present

**Step 3: Write minimal implementation**

Capture `time.monotonic()` around:

- readiness probe
- run half
- resume half

Persist the fields into scenario results.

**Step 4: Run tests to verify they pass**

Run the same command and expect PASS or SKIP depending on credentials.

**Step 5: Commit**

```bash
git add src/aionis_workbench/e2e/real_e2e/scenario_runner.py tests_real_live_e2e/test_live_run_pause.py tests_real_live_e2e/test_live_resume_complete.py
git commit -m "feat: add live timing capture to real-live-e2e"
```

## Task 3: Add CLI surface for live timing reports

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

Add a CLI test for:

- `aionis live-profile --repo-root ...`

Expected output should contain:

- active provider
- active live mode
- latest ready/run/resume timings when available

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py -q
```

Expected:

- FAIL because `live-profile` command does not exist

**Step 3: Write minimal implementation**

Add:

- runtime facade method to return latest timing payload
- `aionis live-profile`

Keep the first version read-only.

**Step 4: Run tests to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py src/aionis_workbench/runtime.py tests/test_cli_shell.py
git commit -m "feat: add live profile cli surface"
```

## Task 4: Add failing tests for provider profiles

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_provider_profiles.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/provider_profiles.py`

**Step 1: Write the failing test**

Test cases:

- provider profiles load by `provider_id`
- `zai_glm51_coding` resolves to the current Z.AI coding endpoint
- profile objects expose timeout and token defaults
- unsupported provider id raises a clear error

Example test shape:

```python
def test_zai_glm51_profile_has_expected_endpoint():
    profile = get_provider_profile("zai_glm51_coding")
    assert profile.base_url == "https://api.z.ai/api/coding/paas/v4"
    assert profile.model == "glm-5.1"
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_provider_profiles.py -q
```

Expected:

- FAIL because provider profile module does not exist

**Step 3: Write minimal implementation**

Implement:

- `ProviderProfile`
- `get_provider_profile(...)`
- built-in profiles for `zai_glm51_coding`, `openai_default`, `openrouter_default`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/provider_profiles.py tests/test_provider_profiles.py
git commit -m "feat: add provider profiles"
```

## Task 5: Let live scenarios consume explicit provider profiles

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_run_pause.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_resume_complete.py`

**Step 1: Write the failing test**

Add assertions that:

- the scenario result records an explicit `provider_id`
- the result records the effective `model`
- the result records the effective `timeout_seconds` and `max_completion_tokens`

**Step 2: Run test to verify it fails**

Run the live tests in no-credential mode:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_run_pause.py tests_real_live_e2e/test_live_resume_complete.py -q
```

Expected:

- FAIL or SKIP with missing fields depending on how the tests are written

**Step 3: Write minimal implementation**

Teach the live runner to:

- read `AIONIS_PROVIDER_PROFILE`
- hydrate env vars from the selected profile
- include provider metadata in scenario outputs

**Step 4: Run tests to verify it passes**

Run the same command and expect PASS or SKIP.

**Step 5: Commit**

```bash
git add src/aionis_workbench/e2e/real_e2e/scenario_runner.py scripts/run-real-live-e2e.sh tests_real_live_e2e/test_live_run_pause.py tests_real_live_e2e/test_live_resume_complete.py
git commit -m "feat: add explicit provider profiles to live e2e"
```

## Task 6: Add failing tests for release gates

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_release_gates.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/release_gates.py`

**Step 1: Write the failing test**

Test cases:

- release gates fail when deterministic suite is missing
- release gates fail when live suite is missing
- release gates fail when provider profile is not approved for release
- release gates pass when all required inputs are present

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_release_gates.py -q
```

Expected:

- FAIL because release gate module does not exist

**Step 3: Write minimal implementation**

Implement:

- `ReleaseGateResult`
- `evaluate_release_gates(...)`
- small helper for emitting a compact summary

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/release_gates.py tests/test_release_gates.py
git commit -m "feat: add release gate evaluator"
```

## Task 7: Add release gate script

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-release-gates.sh`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

Add a test that verifies release gate output uses:

- deterministic suite status
- live suite status
- provider profile
- final pass/fail

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py -q
```

Expected:

- FAIL because the release gate script and output contract do not exist

**Step 3: Write minimal implementation**

Create a shell script that:

- runs deterministic `real-e2e`
- runs split `real-live-e2e`
- evaluates release gates
- exits non-zero when required gates fail

**Step 4: Run tests to verify it passes**

Run the targeted test and then:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
bash scripts/run-release-gates.sh
```

Expected:

- clear gate summary
- correct exit code

**Step 5: Commit**

```bash
git add scripts/run-release-gates.sh README.md tests/test_cli_shell.py
git commit -m "feat: add release gate runner"
```

## Task 8: Add secret hygiene checks

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionis-provider-setup-guide.md`

**Step 1: Write the failing test**

Add tests that:

- provider help output never prints the actual API key value
- readiness errors do not echo key material
- setup docs mention safe env loading rather than raw inline export commands

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py -q
```

Expected:

- FAIL because current messages are not hygiene-focused enough

**Step 3: Write minimal implementation**

Implement:

- key-safe provider/readiness messaging
- provider setup guide with:
  - `.env` loading
  - shell-local export guidance
  - rotation reminder
  - provider profile examples

**Step 4: Run tests to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py tests/test_cli_shell.py docs/product/2026-04-03-aionis-provider-setup-guide.md
git commit -m "docs: add provider setup and secret hygiene guidance"
```

## Task 9: Add focused regression for resume validation override

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py`

**Step 1: Write the failing test**

Add a focused deterministic regression:

- start with a session containing `validation_commands=["false"]`
- resume with explicit `validation_commands=["true"]`
- assert the effective validation chain is exactly `["true"]`

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -q
```

Expected:

- FAIL if the override fix regresses

**Step 3: Write minimal implementation**

If needed, keep the current override behavior and tighten any helper code that could reintroduce appending.

**Step 4: Run tests to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/orchestrator.py tests/test_product_workflows.py
git commit -m "test: lock resume validation override behavior"
```

## Task 10: Add live reliability status document

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionis-workbench-live-reliability-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionis-workbench-real-e2e-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the status doc**

Document:

- active live modes
- active provider profiles
- current timing numbers
- accepted release gates
- current open risks

**Step 2: Run minimal verification**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_live_profile.py tests/test_provider_profiles.py tests/test_release_gates.py -q
```

Expected:

- PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-04-03-aionis-workbench-live-reliability-status.md docs/plans/2026-04-03-aionis-workbench-real-e2e-status.md README.md
git commit -m "docs: add live reliability and provider hygiene status"
```

## Acceptance Criteria

This plan is complete when all of the following are true:

- live scenario outputs include timing data
- Workbench has explicit provider profiles
- live runs record which provider profile they used
- release gates are machine-evaluable
- provider setup docs are key-safe
- the `resume --validation-command` override bug is locked by regression
- the team has one documented place to inspect live reliability state

## Non-Goals

This plan does not attempt to:

- redesign prompt strategy
- add a new network API between extension and Workbench
- support every provider under the sun
- make live runs fast enough for all use cases
- remove the need for manual live verification during provider bring-up

## Recommended Execution Order

Implement in this exact order:

1. Task 1
2. Task 2
3. Task 9
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8
9. Task 10

Task 3 can land after Task 2 if a user-facing timing surface is immediately useful.

## Verification Commands

Targeted build-up:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_live_profile.py tests/test_provider_profiles.py tests/test_release_gates.py -q
```

Deterministic suite:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest \
  tests_real_e2e/test_manifest_loader.py \
  tests_real_e2e/test_repo_cache.py \
  tests_real_e2e/test_cli_driver.py \
  tests_real_e2e/test_runtime_env.py \
  tests_real_e2e/test_result_models.py \
  tests_real_e2e/test_editor_to_dream.py \
  tests_real_e2e/test_publish_recover_resume.py \
  tests_real_e2e/test_repeated_workflow_reuse.py \
  tests_real_e2e/test_launcher_runtime_cycle.py \
  tests/test_launcher_state.py \
  tests/test_runtime_manager.py \
  tests/test_cli_shell.py \
  tests/test_product_workflows.py -q
```

Live suite:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
bash scripts/run-real-live-e2e.sh
```

Release gates:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
bash scripts/run-release-gates.sh
```

## Final Judgment

The platform already has real live capability. This plan exists to make that capability operationally trustworthy.

The right next step is not more surface area. It is:

- measuring live behavior
- standardizing provider use
- tightening secret handling
- and making release claims reproducible
