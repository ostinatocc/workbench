# Aionis Workbench Real E2E Status

Date: 2026-04-03

## Current State

`real-e2e` is now beyond scaffolding. The harness is in place, uses real repositories pinned to fixed commits, and already covers four real complex product scenarios without mocking the Workbench/runtime/Aionisdoc boundary. `real-live-e2e` also now exists as a separately gated slice for actual model-backed `run/resume`.

## Completed Harness Pieces

- manifest loader
- pinned real repo corpus
- local clone cache with fixed detached checkout
- real `aionis` CLI driver
- real runtime start/health/stop environment
- structured scenario result models

## Completed Real Scenarios

### 1. Editor-To-Dream

Flow covered:

1. real repo checkout
2. real `aionis ingest`
3. real `aionis doc compile`
4. real continuity persistence
5. real `consolidate`
6. real `dream`

Assertions covered:

- doc workflow evidence enters continuity
- dream promotions contain doc evidence
- editor-origin evidence is preserved
- promoted prior exposes `dominant_doc_action`, `dominant_event_source`, and `editor_sync_count`

### 2. Publish-Recover-Resume

Flow covered:

1. real repo checkout
2. real `aionis ingest`
3. real `aionis doc publish`
4. real `aionis doc recover --input-kind publish-result`
5. real `aionis doc resume --input-kind recover-result`
6. real session continuity inspection

Assertions covered:

- `doc_workflow.history` stabilizes as `resume -> recover -> publish`
- handoff anchor is preserved
- selected tool is preserved
- persisted artifacts include publish/recover/resume result payloads

### 3. Repeated Workflow Reuse

Flow covered:

1. real repo checkout
2. real `aionis ingest` repeated across the same workflow family
3. real `aionis doc compile` repeated with editor-origin evidence
4. real `consolidate`
5. real `dashboard`

Assertions covered:

- repeated doc evidence converges into `family_doc_prior`
- `family_doc_prior.seed_ready` becomes true
- `editor_sync_count` accumulates across repeated workflow events
- repo-level dashboard proof can explicitly say editor-driven doc reuse is live

### 4. Launcher Runtime Cycle

Flow covered:

1. real repo checkout
2. real `aionis status`
3. real `aionis start`
4. real `aionis status`
5. real `aionis stop`

Assertions covered:

- launcher starts from a clean stopped state under an isolated temporary home
- `aionis start` produces a healthy available runtime
- `aionis status` observes the same healthy runtime
- `aionis stop` returns the launcher to stopped mode

## Completed Real-Live Slice

### 5. Live Run/Pause

Flow covered:

1. prepare a real pinned repository
2. run real `aionis ready`
3. run real `aionis run`
4. force a deterministic staged pause via a real failing validation command
5. inspect the persisted session after the run half

Assertions covered:

- the slice is gated by actual live readiness instead of synthetic flags
- when credentials are missing, the suite skips instead of misreporting product failure
- when live execution is ready, `run` must converge to a resumable session
- the run half must emit a real Aionis `pause` payload
- the task remains inspectable through the persisted Workbench session

### 6. Live Resume/Complete

Flow covered:

1. prepare a real pinned repository
2. run real `aionis ready`
3. run real `aionis run`
4. force a deterministic staged pause via a real failing validation command
5. run real `aionis resume`
6. inspect the persisted session after completion

Assertions covered:

- the slice is gated by actual live readiness instead of synthetic flags
- when credentials are missing, the suite skips instead of misreporting product failure
- when live execution is ready, `run` must converge to a resumable session with a real pause payload
- `resume` must converge to a completed session with a real complete payload
- the task state remains inspectable through the persisted Workbench session

## Product Fixes Proven By Real E2E

These real scenarios forced two concrete fixes:

- Workbench now auto-supplies `base_url`, `repo_root`, and source `file_path` defaults for `doc publish/recover/resume`
- `Aionisdoc` recover parsing now accepts `execution_result_summary: null`
- explicit `resume --validation-command ...` now overrides the previous failed validation chain instead of appending to it

## Current Verification

Focused merged regression:

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
  tests/test_launcher_state.py \
  tests/test_runtime_manager.py \
  tests/test_cli_shell.py \
  tests/test_product_workflows.py -q
```

Latest deterministic merged result:

- `151 passed in 127.94s`

Latest split `real-live-e2e` gate result on this machine:

- `2 skipped in 26.26s`
- skip reason: missing model credentials (`OPENAI_API_KEY` / `OPENROUTER_API_KEY`)

## GLM-5.1 Live Bring-Up

On 2026-04-03, the live slice was brought up against Z.AI's OpenAI-compatible coding endpoint using:

- `OPENAI_BASE_URL=https://api.z.ai/api/coding/paas/v4`
- `WORKBENCH_MODEL=glm-5.1`

The live preflight path succeeded:

- `aionis ready --repo-root ...` reported `live_ready=True`

The first true model-backed `run` also succeeded in reaching the runtime and model, but exposed a real behavior mismatch in the test harness:

- the session converged to `needs_attention` with a real Aionis `pause` payload after validation failure
- this required relaxing the run-half assertion from only `paused` to `paused | needs_attention`

This confirms the Z.AI/GLM-5.1 provider path is not the blocker.

Latest real live verification on the credentialed machine:

- `tests_real_live_e2e/test_live_run_pause.py`: `1 passed in 57.66s`
- `tests_real_live_e2e/test_live_resume_complete.py`: `1 passed in 106.87s`
- `./scripts/run-real-live-e2e.sh`: `2 passed in 158.31s`

Latest live reliability/status companion doc:

- [2026-04-03-aionis-workbench-live-reliability-status.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionis-workbench-live-reliability-status.md)

## Remaining High-Value Work

- decide whether to keep the current live budgets (`15s` model timeout / `256` max completion tokens) or tune them further
- add a CLI-facing live profile report instead of only exposing timing through scenario output and status docs
- keep tightening provider/release hygiene until more than one profile is approved for release gating

## Judgment

`real-e2e` is credible, and `real-live-e2e` has now crossed the implementation boundary. The remaining gap is no longer harness design; it is running the live slice inside a credentialed environment and hardening whatever the first true model-backed failures expose.
