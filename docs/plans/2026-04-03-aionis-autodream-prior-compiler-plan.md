# Aionis AutoDream Prior Compiler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade Workbench AutoDream from conservative session consolidation into a prior compiler that extracts strategy candidates, verifies them, and promotes only trustworthy family priors.

**Architecture:** Keep the existing `consolidate` and `auto_consolidate` paths, but narrow their role to triggering and family-summary production. Add a new `dream_service` pipeline that works in four stages: extract structured samples from sessions, distill strategy candidates, verify those candidates against held-out evidence, and promote or deprecate priors through an explicit lifecycle. `session_service` should eventually consume promoted priors instead of raw consolidation rows.

**Tech Stack:** Python 3.11+, existing `aionis_workbench` services, JSON persistence under `.aionis-workbench`, `pytest`.

## Implementation Status

As of `2026-04-03`, the following tasks are complete in code:

- Task 1: explicit AutoDream data models
- Task 2: dream state persistence
- Task 3: structured dream sample extraction
- Task 4: candidate distillation
- Task 5: deterministic verification
- Task 6: promotion / deprecation lifecycle
- Task 7: manual maintenance wiring via `consolidate()`, including persisted dream state and shell-visible `dream_summary`
- Task 8: `session_service` consumption of `seed_ready` promoted priors
- Task 9: forgetting-backed deprecation using repeated `suppressed` / `evicted` guidance signals
- Task 10: product-path verification proving that promoted priors affect future session seeding

Current regression result after these integrations: `190 passed`.

---

## Problem Statement

Current Workbench learning already has real value:

- validated sessions are persisted
- same-family reuse is tracked
- `consolidate` creates family summaries
- strong priors can seed new sessions

But current AutoDream is still mostly a summarizer:

- it aggregates recent sessions
- it computes `confidence`, `sample_count`, and `recent_success_count`
- it decides whether a family row is `seed_ready`

That is useful, but it is not yet a compiler. It does not explicitly represent:

- candidate strategies
- why one strategy is stronger than another
- trial vs promoted priors
- demotion / retirement of stale priors
- held-out verification

The next stage should therefore separate:

- `consolidation`: summarize recent evidence
- `dreaming`: distill reusable strategy candidates
- `promotion`: only raise candidates after verification

## Desired Product Behavior

When AutoDream is mature:

1. Users work normally with `run`, `resume`, `validate`, `ingest`, and `consolidate`.
2. Successful sessions produce structured learning samples.
3. AutoDream periodically distills those samples into strategy candidates per task family.
4. Each candidate is verified before promotion.
5. Only promoted priors are allowed to seed future sessions.
6. Repeatedly stale or superseded priors are demoted instead of silently lingering forever.

The user-facing effect should be:

- “the repo gets better reusable defaults over time”

not:

- “the system keeps piling up summaries”

## Data Model

Introduce explicit models for each learning stage.

### `DreamSample`

One sample per successful or manually recorded session.

Fields:

- `task_id`
- `project_identity`
- `project_scope`
- `task_family`
- `source`
- `strategy_profile`
- `validation_style`
- `validation_command`
- `working_set`
- `observed_changed_files`
- `artifact_refs`
- `instrumentation_status`
- `artifact_hit_rate`
- `pattern_hit_count`
- `created_at`

### `StrategyCandidate`

One synthesized candidate per `(task_family, candidate_key)`.

Fields:

- `candidate_id`
- `task_family`
- `strategy_profile`
- `validation_style`
- `dominant_validation_command`
- `dominant_working_set`
- `supporting_task_ids`
- `sample_count`
- `recent_success_count`
- `avg_artifact_hit_rate`
- `avg_pattern_hit_count`
- `source_weight`
- `status` where status is one of `candidate`, `trial`, `promoted`, `deprecated`
- `generated_at`

### `CandidateVerification`

Verification result attached to one candidate.

Fields:

- `candidate_id`
- `task_family`
- `coverage_count`
- `heldout_count`
- `heldout_match_rate`
- `regression_risk`
- `verification_status`
- `verification_reason`
- `verified_at`

### `PromotedPrior`

Stable prior consumed by `session_service`.

Fields:

- `prior_id`
- `task_family`
- `strategy_profile`
- `validation_style`
- `dominant_validation_command`
- `dominant_working_set`
- `promotion_status` where status is one of `trial`, `seed_ready`, `deprecated`
- `promotion_reason`
- `confidence`
- `sample_count`
- `recent_success_count`
- `verification_summary`
- `promoted_at`

## Persistence Layout

Do not overload `consolidation.json` with new semantics. Add dedicated files.

### New files

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_models.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_state.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`

### Local project files

- `.aionis-workbench/dream_candidates.json`
- `.aionis-workbench/dream_promotions.json`

### Project-scoped files

- `~/.aionis-workbench/projects/<project_scope>/dream_candidates.json`
- `~/.aionis-workbench/projects/<project_scope>/dream_promotions.json`

Keep `consolidation.json` unchanged for dashboard and current proof surfaces. Dream state should be additive in phase 1.

## Lifecycle Rules

AutoDream should use a simple lifecycle before any ambitious ML-style scoring.

### Candidate

Created when:

- at least 2 samples exist for the same family
- at least one reusable validation or working-set pattern appears

### Trial

Candidate enters trial when:

- `sample_count >= 2`
- `recent_success_count >= 1`
- `confidence >= 0.60`

### Seed-ready

Candidate is promoted when:

- `sample_count >= 3`
- `recent_success_count >= 1`
- `heldout_match_rate >= 0.67`
- `regression_risk <= 0.20`
- family summary is at least `stable_family`

### Deprecated

Candidate or prior is deprecated when:

- new sessions repeatedly supersede it
- linked guidance repeatedly lands in `suppressed` or `evicted`
- held-out verification falls below threshold
- recent family trend regresses materially

## Verification Rules

Keep phase-1 verification deterministic and cheap.

### Positive checks

- candidate covers more than one task
- candidate agrees with dominant validation path
- candidate agrees with dominant working set
- candidate aligns with successful instrumentation slices

### Negative checks

- candidate is contradicted by recent failing sessions
- candidate is tied to regression-expansion or scope-drift outcomes
- candidate is mostly supported by weak-match instrumentation

### Output

Verification should produce:

- `heldout_match_rate`
- `regression_risk`
- `verification_status`
- short `verification_reason`

No LLM call is needed in phase 1.

## Integration Targets

### Existing code to preserve

- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/consolidation.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`

### Existing behavior to keep working

- `/consolidate` and `/dream` shell alias still trigger maintenance
- `dashboard` still uses `consolidation.json`
- `auto_consolidate` remains time/session/lock gated
- `session_service.initial_session()` still seeds from current priors until dream promotions are wired in

## Task 1: Add explicit AutoDream data models

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_models.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_models.py`

**Step 1: Write the failing test**

```python
from aionis_workbench.dream_models import StrategyCandidate


def test_strategy_candidate_defaults_to_candidate_status():
    candidate = StrategyCandidate(
        candidate_id="cand-1",
        task_family="task:demo",
        strategy_profile="family_reuse_loop",
        validation_style="targeted_first",
        dominant_validation_command="PYTHONPATH=src python3 -m pytest tests/test_demo.py -q",
        dominant_working_set=["src/demo.py", "tests/test_demo.py"],
    )
    assert candidate.status == "candidate"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_models.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing dataclass fields.

**Step 3: Write minimal implementation**

Add dataclasses for:

- `DreamSample`
- `StrategyCandidate`
- `CandidateVerification`
- `PromotedPrior`

Include `to_dict()` / `from_dict()` helpers because these models will be stored in JSON.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_models.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_models.py workbench/tests/test_dream_models.py
git commit -m "feat: add autodream data models"
```

## Task 2: Add dream state persistence

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_state.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_state.py`

**Step 1: Write the failing test**

```python
from aionis_workbench.dream_state import save_dream_candidates, load_dream_candidates


def test_save_and_load_dream_candidates(tmp_path):
    save_dream_candidates(repo_root=str(tmp_path), project_scope="project:test/demo", payload={"candidates": []})
    loaded = load_dream_candidates(repo_root=str(tmp_path), project_scope="project:test/demo")
    assert loaded["candidates"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_state.py -q`

Expected: FAIL because state helpers do not exist.

**Step 3: Write minimal implementation**

Add helpers matching the existing persistence style:

- `dream_candidates_path(repo_root)`
- `project_dream_candidates_path(project_scope)`
- `load_dream_candidates(...)`
- `save_dream_candidates(...)`
- `dream_promotions_path(repo_root)`
- `project_dream_promotions_path(project_scope)`
- `load_dream_promotions(...)`
- `save_dream_promotions(...)`

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_state.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_state.py workbench/tests/test_dream_state.py
git commit -m "feat: add autodream state persistence"
```

## Task 3: Extract structured dream samples from sessions

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py`

**Step 1: Write the failing test**

```python
def test_extract_samples_reads_successful_session_learning(tmp_path, monkeypatch):
    # create a validated session with learning + instrumentation
    samples = service.extract_samples(limit=12)
    assert samples[0].task_family == "task:demo"
    assert samples[0].strategy_profile == "family_reuse_loop"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: FAIL because `DreamService` does not exist.

**Step 3: Write minimal implementation**

Implement `DreamService.extract_samples()` using existing session data:

- `continuity_snapshot["learning"]`
- `selected_task_family`
- `selected_strategy_profile`
- `selected_validation_style`
- `target_files`
- `last_validation_result`
- `instrumentation_summary`

Do not invent new signals in this step.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_service.py workbench/src/aionis_workbench/surface_service.py workbench/tests/test_dream_service.py
git commit -m "feat: extract autodream samples from sessions"
```

## Task 4: Distill strategy candidates from dream samples

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py`

**Step 1: Write the failing test**

```python
def test_distill_candidates_groups_samples_by_family_and_strategy():
    candidates = service.distill_candidates(samples)
    assert candidates[0].task_family == "task:demo"
    assert candidates[0].sample_count == 3
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: FAIL because `distill_candidates` is missing.

**Step 3: Write minimal implementation**

Implement candidate grouping by:

- `task_family`
- `strategy_profile`
- `validation_style`
- dominant validation command

Compute:

- `sample_count`
- `recent_success_count`
- `avg_artifact_hit_rate`
- `avg_pattern_hit_count`
- `source_weight`

Default all new candidates to `status="candidate"`.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_service.py workbench/tests/test_dream_service.py
git commit -m "feat: distill autodream strategy candidates"
```

## Task 5: Add deterministic candidate verification

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py`

**Step 1: Write the failing test**

```python
def test_verify_candidate_marks_seed_ready_when_heldout_checks_pass():
    verification = service.verify_candidate(candidate, heldout_samples)
    assert verification.verification_status == "passed"
    assert verification.heldout_match_rate >= 0.67
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: FAIL because `verify_candidate` is missing.

**Step 3: Write minimal implementation**

Compute:

- `coverage_count`
- `heldout_count`
- `heldout_match_rate`
- `regression_risk`
- `verification_status`
- `verification_reason`

Only use deterministic checks derived from:

- matching validation command
- matching working set
- successful instrumentation
- recent failing contradiction

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_service.py workbench/tests/test_dream_service.py
git commit -m "feat: verify autodream candidates"
```

## Task 6: Add promotion and deprecation lifecycle

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_state.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py`

**Step 1: Write the failing test**

```python
def test_promote_candidates_marks_only_verified_candidates_seed_ready():
    promotions = service.promote_candidates(candidates, verifications)
    assert promotions[0].promotion_status == "seed_ready"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: FAIL because promotion lifecycle is missing.

**Step 3: Write minimal implementation**

Implement:

- `trial` state for partially ready candidates
- `seed_ready` promotion for verified candidates
- `deprecated` status for stale / contradicted priors

Persist promotions separately from raw candidates.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_service.py workbench/src/aionis_workbench/dream_state.py workbench/tests/test_dream_service.py
git commit -m "feat: add autodream prior lifecycle"
```

## Task 7: Wire AutoDream into manual and automatic maintenance

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Step 1: Write the failing test**

```python
def test_consolidate_surface_includes_dream_candidate_summary():
    payload = workbench.consolidate(limit=12, family_limit=4)
    assert "dream_summary" in payload
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py -q`

Expected: FAIL because dream summary is not surfaced.

**Step 3: Write minimal implementation**

After `consolidate`, also run dream distillation and attach:

- candidate count
- promoted prior count
- trial prior count
- deprecated prior count
- top recommendation or blocker

Keep current `consolidation.json` path and shell contract stable.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/ops_service.py workbench/src/aionis_workbench/shell.py workbench/src/aionis_workbench/shell_dispatch.py workbench/tests/test_cli_shell.py workbench/tests/test_shell_dispatch.py
git commit -m "feat: surface autodream prior compiler results"
```

## Task 8: Consume promoted priors in session initialization

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_bootstrap.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

```python
def test_initial_session_prefers_promoted_prior_over_raw_consolidation_row():
    session = workbench._initial_session(...)
    assert session.validation_commands[0] == "PYTHONPATH=src python3 -m pytest tests/test_demo.py -q"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py tests/test_product_workflows.py -q`

Expected: FAIL because session initialization still consumes raw family rows only.

**Step 3: Write minimal implementation**

Update `session_service` so seeding order is:

1. promoted dream prior
2. raw seed-ready consolidation row
3. bootstrap defaults

Do not delete the old fallback yet.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py tests/test_product_workflows.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/session_service.py workbench/tests/test_bootstrap.py workbench/tests/test_product_workflows.py
git commit -m "feat: seed sessions from promoted autodream priors"
```

## Task 9: Connect forgetting to prior deprecation

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py`

**Step 1: Write the failing test**

```python
def test_repeatedly_evicted_guidance_degrades_prior_status():
    promotions = service.promote_candidates(candidates, verifications)
    assert promotions[0].promotion_status == "deprecated"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: FAIL because forgetting signals do not influence dream lifecycle.

**Step 3: Write minimal implementation**

Use these signals as deprecation inputs:

- repeated `suppressed`
- repeated `evicted`
- prior-linked guidance being superseded by newer successful guidance

Keep the rule simple and deterministic in phase 1.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/src/aionis_workbench/dream_service.py workbench/src/aionis_workbench/session.py workbench/tests/test_dream_service.py
git commit -m "feat: connect forgetting signals to autodream deprecation"
```

## Task 10: Add product-path verification for promoted priors

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_bootstrap.py`

**Step 1: Write the failing test**

```python
def test_promoted_prior_is_used_after_dream_promotion(tmp_path, monkeypatch):
    # create prior, run dream, initialize session
    assert session.selected_strategy_profile == "family_reuse_loop"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py tests/test_bootstrap.py -q`

Expected: FAIL because dream promotions are not yet fully wired.

**Step 3: Write minimal implementation**

Only implement whatever small glue is still missing after Tasks 1-9.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py tests/test_bootstrap.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add workbench/tests/test_product_workflows.py workbench/tests/test_bootstrap.py
git commit -m "test: cover autodream promotion product path"
```

## Acceptance Criteria

This plan is complete when all of the following are true:

- AutoDream has explicit models for sample, candidate, verification, and promoted prior
- consolidation and dream state are stored separately
- candidate verification exists and is deterministic
- promoted priors have a lifecycle beyond simple `seed_ready`
- `session_service` can consume promoted priors
- forgetting signals can deprecate stale priors
- shell and dashboard surfaces expose dream results without breaking current consolidation surfaces
- product-path tests prove that promoted priors affect future session seeding

## Suggested Execution Order

If you want the fastest value path, do tasks in this order:

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 8
8. Task 7
9. Task 9
10. Task 10

This order gets the compiler working before spending time on richer shell surfaces.

## Risks

- Overfitting dream promotions to tiny sample sets
- letting dream state duplicate too much of `consolidation.json`
- making verification look sophisticated while still being noisy
- prematurely replacing the current stable consolidation fallback

The mitigation is:

- keep deterministic gates
- keep old consolidation fallback until dream promotions prove stable
- make promotion state explicit and inspectable

## Verification Commands

Use these checkpoints throughout implementation:

- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_models.py -q`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_state.py -q`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_dream_service.py -q`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py tests/test_product_workflows.py -q`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py -q`
- `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_bootstrap.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_recovery_service.py tests/test_runtime_bridge_contracts.py tests/test_product_workflows.py -q`
