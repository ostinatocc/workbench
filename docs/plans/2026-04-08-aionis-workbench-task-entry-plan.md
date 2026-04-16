# Aionis Workbench Task Entry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a single user-facing Workbench app entry that accepts a task, reads current context, internally runs plan/sprint/generate/export, and returns a usable artifact without exposing kernel phases to the user.

**Architecture:** Keep the existing Workbench kernel intact and add an upper task-entry layer inside Workbench itself. The new entry should do lightweight task intake and routing first, then call the existing app harness phases in-process, record the resulting state, and surface one coherent result payload to CLI and shell users.

**Tech Stack:** Python, argparse CLI, Workbench runtime/app harness services, shell dispatch/rendering, pytest

---

### Task 1: Document and codify the single-entry flow

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-08-aionis-workbench-task-entry-plan.md`
- Reference: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Reference: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`

**Step 1: Define the exact first-version flow**

Document this sequence explicitly:
- intake task prompt
- initialize or reset the app session
- capture lightweight context from the current repo
- create/update product spec
- ensure an active sprint exists
- run generate
- export the latest artifact

**Step 2: Freeze first-version scope**

Limit v1 to the already-working app harness path:
- app tasks only
- simple web tasks first
- existing planner/generator/export stack reused

**Step 3: Define the v1 success payload**

The new flow must return:
- task id
- route summary
- context summary
- active sprint id
- generate payload
- export payload
- final artifact entrypoint

**Step 4: Define the v1 failure model**

Failures must be surfaced as one payload with:
- phase (`plan`, `sprint`, `generate`, `export`)
- error text
- latest artifact path if any
- latest validation/failure reason if any

### Task 2: Add runtime-level app ship orchestration

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write failing tests for the new runtime entry**

Add tests that verify:
- `app_ship()` creates a missing app session from just task id + prompt
- `app_ship()` ensures there is an active sprint
- `app_ship()` runs generate and export in sequence
- `app_ship()` returns a single payload with `shell_view="app_ship"`

**Step 2: Run the targeted tests and confirm they fail**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -k app_ship -q
```

Expected: failing tests because `app_ship` does not exist yet.

**Step 3: Implement minimal app_ship orchestration**

Add a new runtime method:
- `app_ship(task_id, prompt, output_dir="", use_live_planner=False, use_live_generator=False)`

Implementation rules:
- do lightweight context scan from repo root
- call `app_plan(...)`
- inspect active sprint after plan
- if no active sprint exists, create `sprint-1` with a goal derived from the prompt
- call `app_generate(...)`
- call `app_export(...)`
- merge all outputs into one payload

**Step 4: Run targeted tests again**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -k app_ship -q
```

Expected: PASS

### Task 3: Expose app ship in the CLI

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write failing CLI tests**

Add tests that verify:
- `aionis ... app ship --task-id ... --prompt ...` parses correctly
- dispatch calls `workbench.app_ship(...)`
- live mode prints a one-line running message before work starts

**Step 2: Run CLI tests to confirm failure**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py -k app_ship -q
```

Expected: FAIL because the parser/dispatch path does not exist yet.

**Step 3: Implement the CLI command**

Add:
- `app ship`
- required args: `--task-id`, `--prompt`
- optional args: `--output-dir`, `--use-live-planner`, `--use-live-generator`

Dispatch it to `workbench.app_ship(...)`.

**Step 4: Re-run the CLI tests**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py -k app_ship -q
```

Expected: PASS

### Task 4: Expose app ship in the interactive shell

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Step 1: Write failing shell dispatch tests**

Add tests that verify:
- `/app ship TASK_ID --prompt "..."` dispatches to `workbench.app_ship(...)`
- help text is shown when prompt is missing

**Step 2: Run the shell tests and confirm failure**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_shell_dispatch.py -k app_ship -q
```

Expected: FAIL because `/app ship` is not handled yet.

**Step 3: Implement shell dispatch and rendering**

Add:
- `/app ship`
- a summary render that shows:
  - task id
  - route/context summary
  - sprint id
  - artifact entrypoint
  - validation/failure summary

**Step 4: Re-run the shell tests**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_shell_dispatch.py -k app_ship -q
```

Expected: PASS

### Task 5: Verify the new top-level flow end to end

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Add one integration-style workflow test**

Test that one `app_ship(...)` call:
- initializes the task
- produces an active sprint
- records a generation attempt
- returns an export payload with an entrypoint

**Step 2: Run the targeted workflow tests**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py tests/test_cli_shell.py tests/test_shell_dispatch.py -k "app_ship" -q
```

Expected: PASS

**Step 3: Run a small regression pack**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_delivery_executor.py tests/test_delivery_workspace.py tests/test_product_workflows.py tests/test_cli_shell.py tests/test_shell_dispatch.py -q
```

Expected: PASS

**Step 4: Commit**

```bash
git add /Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-08-aionis-workbench-task-entry-plan.md \
        /Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py \
        /Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py \
        /Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py \
        /Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py \
        /Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py \
        /Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py \
        /Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py
git commit -m "feat: add workbench app ship task entry"
```
