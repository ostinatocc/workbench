# Aionis Workbench A/B Test Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove Aionis Workbench's user-facing value with a real, complex, multi-turn application-development A/B test. The test must demonstrate that the same base model and provider become more effective when run through Aionis's continuity, workflow, reviewer, and app-harness control plane.

**Core thesis:** Do not benchmark "who writes a single feature faster." Benchmark whether a long-running application task can recover, replan, and converge more reliably under the same model budget.

**A/B definition:**
- **A (Baseline):** Same model, same provider, same repo, same prompt budget, using a thin agent loop with no Aionis continuity, no structured retry/replan state, and no reusable harness state.
- **B (Aionis):** Same model, same provider, same repo, same prompt budget, using Aionis Workbench with app harness, reviewer substrate, retry/replan policy, and live-profile convergence signals.

**Success criteria:**
- The benchmark can be re-run on at least three realistic app-building tasks.
- The output is not just logs. It produces a compact report with success/failure, convergence path, retry/replan count, and time-to-ending.
- A reader can understand the value of Aionis from the results without already knowing the internals.

**Tech Stack:** Python 3.12, pytest, Workbench runtime/service layer, real-e2e/live-e2e harness, repo-local live-profile snapshots, Markdown reporting

---

### Task 1: Freeze the benchmark contract

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-ab-test-contract.md`

**Step 1: Define what counts as a valid A/B run**

The contract should explicitly lock:
- same provider profile
- same model
- same timeout and token budget
- same repo checkout
- same user task prompt
- same validation/evaluator target

**Step 2: Define the benchmark outputs**

At minimum:
- `scenario_id`
- `arm` (`baseline` or `aionis`)
- `provider_id`
- `model`
- `ended_in`
- `total_duration_seconds`
- `retry_count`
- `replan_depth`
- `latest_convergence_signal`
- `final_execution_gate`
- `advance_reached`
- `escalated`

**Step 3: Document what is intentionally out of scope**

Explicitly exclude:
- arbitrary manual judging
- cross-model comparisons
- browser/Playwright hard QA
- team-process metrics

---

### Task 2: Choose three benchmark-grade task families

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-ab-test-scenarios.md`

**Step 1: Define the three task families**

Pick task families that require at least two of:
- bounded generation
- evaluator failure
- retry
- replan
- second-cycle handling

Recommended shape:
- `persistence-and-hydration bug`
- `stateful UI workflow refinement`
- `structured feature completion with follow-up sprint`

**Step 2: For each family, define one concrete repo-backed scenario**

For each scenario, write:
- repo
- task prompt
- expected harness path
- minimum success condition
- likely failure side

**Step 3: Record why each scenario is a fair value test**

The justification should explain why the scenario measures continuity/convergence instead of raw model cleverness.

---

### Task 3: Add a benchmark result schema

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ab_test_models.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_ab_test_models.py`

**Step 1: Add a small result model**

Include:
- `BenchmarkRun`
- `BenchmarkScenarioResult`
- `BenchmarkComparison`

**Step 2: Capture both absolute and delta fields**

Include:
- arm-local result fields
- comparison fields such as:
  - `duration_delta_seconds`
  - `retry_delta`
  - `replan_delta`
  - `convergence_delta`

**Step 3: Lock the model with tests**

Expected: PASS on serialization and stable summary fields.

---

### Task 4: Build a baseline thin-loop runner

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ab_test_baseline.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_ab_test_baseline.py`

**Step 1: Define the baseline policy**

Keep it intentionally thin:
- one planning step
- one implementation attempt
- one evaluator step
- optional one retry
- no structured replan lineage
- no reusable session memory

**Step 2: Make the baseline share provider/model config with Aionis**

Do not allow hidden tuning differences.

**Step 3: Record the same end-state fields**

Even if the baseline lacks a native `replan_depth`, normalize the output to the same schema.

---

### Task 5: Add an Aionis benchmark runner

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ab_test_runner.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_ab_test_runner.py`

**Step 1: Wrap the current app harness**

The runner should be able to execute:
- `plan`
- `qa`
- `negotiate`
- `retry`
- `generate`
- `replan`
- `advance`
- `escalate`

**Step 2: Reduce the output to benchmark fields**

Do not dump the full session. Produce a compact comparable result.

**Step 3: Include convergence and policy signals**

At minimum:
- `latest_convergence_signal`
- `execution_gate`
- `gate_flow`
- `policy_stage`

---

### Task 6: Build a comparison report surface

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ab_test_report.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_ab_test_report.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Add a narrow surface**

Recommended non-interactive entry:
- `aionis ab-test ...`

Recommended shell surface:
- `/ab-test ...`

**Step 2: Keep the output compact**

The report should make it obvious:
- which arm converged
- which arm escalated
- which arm replanned more
- which arm reached `advance`
- how much longer/shorter it took

**Step 3: Include one human-readable conclusion line**

For example:
- `Aionis converged after one retry and one replan; baseline escalated without reaching sprint-2.`

---

### Task 7: Add deterministic benchmark coverage

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_ab_test_report.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`

**Step 1: Pick one scenario family first**

Start with the strongest current path:
- bounded retry/replan app harness scenario

**Step 2: Run both arms on the same deterministic setup**

The deterministic real-e2e should prove:
- baseline and Aionis both execute
- both return comparable summaries
- the report is generated

**Step 3: Lock one meaningful difference**

Do not make the deterministic version fake a win. Lock a real structural difference such as:
- Aionis reaches `ready_for_next_sprint`
- baseline ends in `escalated`

---

### Task 8: Add one narrow credential-gated live A/B scenario

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_ab_test_report.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`

**Step 1: Pick the strongest live scenario**

Recommended:
- first-cycle `retry -> qa compare -> advance/escalate`
or
- second-cycle replan ending

**Step 2: Keep the live benchmark narrow**

One scenario is enough for phase 1.

**Step 3: Capture timing and convergence deltas**

The live report must show:
- `baseline.latest_convergence_signal`
- `aionis.latest_convergence_signal`
- duration difference
- final ending difference

---

### Task 9: Write the proof-facing benchmark summary

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-ab-test-status.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the benchmark narrative**

The status doc should explain:
- what the A/B test measures
- what it does not measure
- why the chosen scenarios are fair

**Step 2: Add result tables**

Include:
- per-scenario result
- arm comparison
- timing
- convergence signal
- ending

**Step 3: Make the value proposition explicit**

State the user-facing conclusion in plain language:
- Aionis is not winning because it chats better.
- Aionis is winning because it preserves state, structures retries, and converges across longer loops.

---

### Task 10: Final review and benchmark hygiene

**Files:**
- Modify as needed across benchmark files

**Step 1: Run targeted test suites**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_ab_test_models.py tests/test_ab_test_baseline.py tests/test_ab_test_runner.py tests/test_ab_test_report.py -q
.venv/bin/python -m pytest tests_real_e2e/test_ab_test_report.py -q
```

**Step 2: Run the live benchmark in a credentialed shell**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_ab_test_report.py -q
```

**Step 3: Review for fairness**

Before calling it done, verify:
- same model/provider across arms
- no hidden extra retry budget in Aionis unless explicitly reported
- no hidden evaluator shortcut in baseline unless documented
- comparison report does not overclaim

---

## Expected Outcome

After this plan:

- Workbench will have a real A/B benchmark surface
- the benchmark will compare long-running app-development convergence, not single-turn output
- both deterministic and live benchmark evidence will exist
- the resulting report will be usable for product proof, demos, and positioning

## Not in Scope

This plan does **not** attempt to:

- create a full autonomous benchmark farm
- add browser/Playwright hard QA
- benchmark multiple models against each other
- benchmark team collaboration or editor latency
- replace the existing app harness status docs

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8
9. Task 9
10. Task 10
