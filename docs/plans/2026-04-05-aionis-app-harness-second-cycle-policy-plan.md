# Aionis App Harness Second-Cycle Policy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make second-cycle replanned sprints behave like first-class policy states, with explicit deterministic and live coverage for `generate -> qa -> advance` and `generate -> qa -> escalate/replan`.

**Architecture:** Build on the existing bounded app harness loop instead of adding a new actor. Keep `app_harness_service.py` as the policy source of truth, then project the new second-cycle policy state into canonical views, shell output, deterministic real-e2e, and narrow live-e2e scenarios. Treat second-cycle behavior as a stricter extension of the current `replan_depth / replan_root_sprint_id / retry_budget` state, not a separate workflow family.

**Tech Stack:** Python 3.12, pytest, Workbench runtime/service layer, real-e2e/live-e2e harness, shell/CLI surfaces

---

### Task 1: Lock the deterministic second-cycle policy endings

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing tests**

Add targeted tests for:
- `second_replan -> generate -> qa(pass) -> advance`
- `second_replan -> generate -> qa(fail) -> escalate`
- `second_replan -> generate -> qa(fail) -> replan`

The assertions should cover:
- `replan_depth == 2`
- `replan_root_sprint_id == "sprint-1"`
- `retry_count == 0` after replan
- `recommended_next_action`
- `loop_status`
- active sprint transitions

**Step 2: Run the targeted tests to confirm failure**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -k "second_replan and (advance or escalate or replan)" -q
```

Expected: FAIL because second-cycle endings are not yet fully enforced.

**Step 3: Implement the minimal policy behavior**

Adjust `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py` so second-cycle replanned sprints use the same explicit ending rules as first-cycle replanned sprints, instead of relying on generic post-QA state.

**Step 4: Re-run the targeted tests**

Expected: PASS.

### Task 2: Make execution outcome a required input for second-cycle policy

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/app_harness_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write a failing test**

Add a test that shows a second replanned sprint cannot:
- advance without a settled `latest_execution_attempt.outcome_status == "qa_passed"`
- replan/escalate without carrying the latest execution summary and changed-target hints

**Step 2: Run the targeted test**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -k "second_replan and execution" -q
```

Expected: FAIL.

**Step 3: Implement the minimal service change**

Update policy derivation so second-cycle `advance` and `replan` explicitly inspect the current sprint’s latest execution attempt, not only the latest evaluator summary.

**Step 4: Re-run the targeted test**

Expected: PASS.

### Task 3: Expose second-cycle policy state in canonical views and shell output

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Step 1: Write the failing output expectations**

Add assertions that `/app show` exposes compact second-cycle policy hints, for example:
- second-cycle stage/ending status
- current replan lineage
- current retry window
- execution outcome readiness

**Step 2: Run the focused shell tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py -k "replan or retry or app_show" -q
```

Expected: FAIL on the new output expectations.

**Step 3: Implement the surface changes**

Keep the shell summary compact. Do not add another command. Extend the current `/app` line with second-cycle policy state only if it materially changes operator action.

**Step 4: Re-run the focused shell tests**

Expected: PASS.

### Task 4: Extend deterministic real-e2e to include a second-cycle ending

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_e2e/test_app_harness_planner_contract.py`

**Step 1: Write the failing scenario assertions**

Extend the deterministic app harness scenario to continue through:
- first replan
- second replan
- second-cycle `generate -> qa`
- one explicit ending (`advance` recommended or `replan/escalate` recommended)

**Step 2: Run the deterministic real-e2e test**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_e2e/test_app_harness_planner_contract.py -q
```

Expected: FAIL until the scenario is extended.

**Step 3: Implement the scenario update**

Keep it narrow. Do not add browser automation. Only carry the loop far enough to prove second-cycle policy behavior.

**Step 4: Re-run the deterministic real-e2e test**

Expected: PASS.

### Task 5: Add the first live second-cycle policy-ending scenario

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`

**Step 1: Write the gated live test**

Add a new live scenario that proves:
- second replan exists
- second replanned sprint can `generate`
- second replanned sprint can `qa(pass)`
- second-cycle `advance` unlocks and activates the next sprint

**Step 2: Run the new live test without credentials**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py -q -rs
```

Expected: SKIP with a live-credentials gate in non-live shells.

**Step 3: Implement the scenario**

Reuse the existing second replan lineage setup. Do not duplicate planner/evaluator/generator prompts more than necessary. Only add the extra second-cycle `generate -> qa -> advance` tail.

**Step 4: Run the new live test in a credentialed shell**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py -q
```

Expected: PASS with a captured timing baseline.

### Task 6: Add the live failure-side second-cycle exit

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-live-e2e.sh`

**Step 1: Write the gated live failure-path test**

Cover:
- second replanned sprint
- live `generate`
- live `qa(fail)`
- explicit `escalate` or `replan` recommendation

**Step 2: Run it in a non-live shell**

Expected: SKIP.

**Step 3: Implement the narrow failure-side live scenario**

Keep the scenario bounded. The goal is to prove the policy ending, not to solve the sprint.

**Step 4: Run it in a credentialed shell**

Expected: PASS with timing captured.

### Task 7: Document second-cycle policy and timing baselines

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md`

**Step 1: Update the live coverage list**

Add the new second-cycle policy-ending tests to the README and status doc.

**Step 2: Record timing baselines**

Add the first credentialed reference timings for:
- second replan lineage
- second-cycle `generate -> qa -> advance`
- second-cycle `generate -> qa -> escalate`

**Step 3: Add the explicit next-gap statement**

After second-cycle endings are covered, the next remaining gap should be called out clearly:
- true generator execution engine
- browser-backed evaluator

### Task 8: Run the full verification set

**Files:**
- No code changes

**Step 1: Run deterministic verification**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests_real_e2e/test_app_harness_planner_contract.py -q
```

Expected: PASS.

**Step 2: Run gated live verification**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_app_second_replan.py tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py -q -rs
```

Expected:
- SKIP in shells without credentials
- PASS in the credentialed provider profile

**Step 3: Run the live suite entrypoint**

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
bash ./scripts/run-real-live-e2e.sh
```

Expected:
- exit `2` without credentials
- PASS in a credentialed shell

### Task 9: Final consistency review

**Files:**
- Review only

**Step 1: Re-check state semantics**

Confirm these remain true after implementation:
- `retry_count` is sprint-scoped
- `replan_depth` increments only on actual replans
- `replan_root_sprint_id` remains the original sprint root
- `current_sprint_execution_count` is sprint-scoped
- historical sprint actions do not overwrite active sprint state

**Step 2: Re-check operator surfaces**

Confirm `/app show` and `aionis app show` still read cleanly and do not become a changelog dump.

**Step 3: Commit**

```bash
git add workbench/src/aionis_workbench/app_harness_service.py \
  workbench/src/aionis_workbench/evaluation_service.py \
  workbench/src/aionis_workbench/shell.py \
  workbench/src/aionis_workbench/e2e/real_e2e/scenario_runner.py \
  workbench/tests/test_product_workflows.py \
  workbench/tests/test_cli_shell.py \
  workbench/tests/test_shell_dispatch.py \
  workbench/tests_real_e2e/test_app_harness_planner_contract.py \
  workbench/tests_real_live_e2e/test_live_app_second_replan.py \
  workbench/tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py \
  workbench/tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py \
  workbench/scripts/run-real-live-e2e.sh \
  workbench/README.md \
  workbench/docs/plans/2026-04-04-aionis-long-running-app-harness-status.md \
  workbench/docs/plans/2026-04-05-aionis-app-harness-second-cycle-policy-plan.md
git commit -m "feat: add second-cycle app harness policy endings"
```

Expected: commit succeeds once all deterministic tests pass and live results are either captured or intentionally gated.
