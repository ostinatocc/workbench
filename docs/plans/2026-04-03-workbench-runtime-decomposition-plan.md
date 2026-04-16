# Aionis Workbench Runtime Decomposition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decompose the current Workbench runtime into smaller services without changing the external `aionis` product contract, so the shell, orchestration, recovery, and runtime-bridge layers can evolve independently.

**Architecture:** Keep `AionisWorkbench` as a thin facade and move behavior out of [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py) into focused modules: `ops_service`, `session_service`, `orchestrator`, and `recovery_service`. Preserve the existing runtime API boundary through [aionis_bridge.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionis_bridge.py) and add local response validation so Workbench depends on stable contracts instead of runtime implementation detail.

**Tech Stack:** Python 3.11+, `argparse`, `httpx`, existing `aionis_workbench` session/policies modules, `deepagents`, `pytest`.

---

## Why This Refactor Now

Current state:

- [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py) is `4417` lines and mixes product ops, session lifecycle, orchestration, recovery, validation, dashboarding, and consolidation.
- `workbench` can start and import, but its test entry is not turnkey.
- The runtime bridge is already narrow enough to stabilize, but response handling is still mostly ad hoc.

Main risks if this is not done:

- every new feature grows `runtime.py`
- recovery changes can accidentally regress shell and onboarding behavior
- `workbench` remains harder to test than `runtime-mainline`
- runtime API drift will be caught late

## Refactor Rules

Do not change these product surfaces during the decomposition:

- CLI entrypoint names in [cli.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py)
- shell command names and routing in [shell_dispatch.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py)
- session JSON shape in [session.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py)
- canonical surface names described in:
  - [workbench-execution-packet-v1.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/workbench-execution-packet-v1.md)
  - [workbench-planner-provenance-v1.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/workbench-planner-provenance-v1.md)
- runtime endpoint paths consumed by [aionis_bridge.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionis_bridge.py)

Non-goals for this plan:

- replacing `deepagents`
- redesigning `continuity_snapshot`
- changing runtime route structure in `runtime-mainline`
- building a TUI or web UI

## Target Module Layout

At the end of this plan, Workbench should converge on this structure:

- `src/aionis_workbench/runtime.py`
  - thin facade only
  - config + dependency wiring
  - public methods delegate to services
- `src/aionis_workbench/ops_service.py`
  - `doctor`
  - `setup`
  - `host_contract`
  - `background_status`
  - `dashboard`
  - `compare_family`
  - `recent_tasks`
- `src/aionis_workbench/session_service.py`
  - session init
  - session loading/saving
  - bootstrap seeding
  - normalization helpers
- `src/aionis_workbench/recovery_service.py`
  - pause decisions
  - rollback recovery
  - validation failure handling
  - correction / rollback artifact assembly
- `src/aionis_workbench/orchestrator.py`
  - `run`
  - `resume`
  - `ingest`
  - live execution flow
  - runtime host calls
- `src/aionis_workbench/runtime_contracts.py`
  - validation/parsing for runtime bridge responses

## Acceptance Targets

The slice is complete when all of the following are true:

1. [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py) is below `1200` lines.
2. `AionisWorkbench` primarily wires services and delegates public methods.
3. `doctor`, `setup`, `dashboard`, `background_status`, and `host_contract` live outside `runtime.py`.
4. `run`, `resume`, and `ingest` live outside `runtime.py`.
5. runtime bridge responses are validated by local schema/helpers before use.
6. test bootstrap does not require manually setting `PYTHONPATH=src`.
7. Workbench has deterministic commands for:
   - unit tests
   - service-level tests
   - bridge contract tests
   - shell/CLI regression tests

## Task 1: Stabilize the Test Entry and Dev Setup

**Files:**
- Modify: `workbench/pyproject.toml`
- Modify: `workbench/tests/conftest.py`
- Create: `workbench/tests/test_test_bootstrap.py`

**Step 1: Add a dev extra for test dependencies**

Update [pyproject.toml](/Volumes/ziel/Aioniscli/Aionis/workbench/pyproject.toml) to include:

- `pytest>=8`

Add an optional dependency group:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
```

**Step 2: Make tests import `src/` without shell hacks**

Update [conftest.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/conftest.py) to insert:

- repo `src/` directory into `sys.path`

Keep this limited to test bootstrap only.

**Step 3: Add a regression test for test bootstrap**

Create [test_test_bootstrap.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_test_bootstrap.py) with a simple import assertion:

```python
def test_can_import_aionis_workbench_from_test_process():
    import aionis_workbench.cli
```

**Step 4: Install editable package with dev dependencies**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pip install -e '.[dev]'
```

Expected:

- `pytest` installed
- editable package available

**Step 5: Run the narrow bootstrap tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests/test_test_bootstrap.py tests/test_cli_shell.py -q
```

Expected:

- imports succeed
- parser/shell tests still pass

**Step 6: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/test_test_bootstrap.py
git commit -m "test: stabilize workbench test bootstrap"
```

## Task 2: Extract Product Ops into `ops_service.py`

**Files:**
- Create: `workbench/src/aionis_workbench/ops_service.py`
- Modify: `workbench/src/aionis_workbench/runtime.py`
- Test: `workbench/tests/test_bootstrap.py`
- Test: `workbench/tests/test_cli_shell.py`

**Step 1: Create an ops service container**

Create [ops_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py) with an `OpsService` class that receives:

- `WorkbenchConfig`
- `AionisConfig`
- execution host
- runtime host

Move these methods first:

- `host_contract`
- `doctor`
- `setup`

Do not change payload shape.

**Step 2: Route `AionisWorkbench` through the new service**

In [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py), keep public methods:

- `host_contract`
- `doctor`
- `setup`

but delegate their body to `self._ops`.

**Step 3: Move project-level inspect surfaces**

Move these next:

- `background_status`
- `recent_tasks`
- `compare_family`
- `dashboard`
- `consolidate`
- `_maybe_auto_consolidate`

If a helper is used only by these methods, move it too.

**Step 4: Re-run shell and bootstrap regressions**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests/test_bootstrap.py tests/test_cli_shell.py tests/test_statusline.py -q
```

Expected:

- no payload changes
- no shell rendering regressions

**Step 5: Commit**

```bash
git add src/aionis_workbench/ops_service.py src/aionis_workbench/runtime.py tests/test_bootstrap.py tests/test_cli_shell.py tests/test_statusline.py
git commit -m "refactor: extract workbench ops service"
```

## Task 3: Extract Session Construction and Persistence Policy

**Files:**
- Create: `workbench/src/aionis_workbench/session_service.py`
- Modify: `workbench/src/aionis_workbench/runtime.py`
- Modify: `workbench/src/aionis_workbench/session.py`
- Test: `workbench/tests/test_bootstrap.py`

**Step 1: Create a focused session service**

Create [session_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py) and move logic for:

- `_initial_session`
- session normalization helpers
- session save/load wrappers used by runtime flows
- bootstrap seeding and family-prior seeding

The service should own:

- creating `SessionState`
- applying strategy
- seeding continuity
- saving local + project-scoped session state

**Step 2: Keep `session.py` as data and storage primitives**

Do not move dataclasses out of [session.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py). Keep:

- dataclasses
- file path helpers
- low-level load/save helpers

Move orchestration policy only.

**Step 3: Delegate from runtime**

Update [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py) so public flows call `self._sessions`.

**Step 4: Add narrow tests for session initialization**

Extend [test_bootstrap.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_bootstrap.py) with explicit coverage for:

- target file seeding
- validation command seeding
- family prior boost behavior
- project-scope persistence

**Step 5: Run targeted tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests/test_bootstrap.py -q
```

Expected:

- all existing bootstrap/session tests still pass

**Step 6: Commit**

```bash
git add src/aionis_workbench/session_service.py src/aionis_workbench/runtime.py src/aionis_workbench/session.py tests/test_bootstrap.py
git commit -m "refactor: extract workbench session service"
```

## Task 4: Extract Recovery and Validation Decisions

**Files:**
- Create: `workbench/src/aionis_workbench/recovery_service.py`
- Modify: `workbench/src/aionis_workbench/runtime.py`
- Test: `workbench/tests/test_bootstrap.py`
- Create: `workbench/tests/test_recovery_service.py`

**Step 1: Move recovery-only logic**

Create [recovery_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/recovery_service.py) and move logic for:

- rollback recovery
- validation failure pause decisions
- correction packet construction
- rollback hint construction
- failure artifact construction

Keep packet/provenance builders where they already belong unless they are recovery-only.

**Step 2: Define one recovery result object**

Add a dataclass such as:

```python
@dataclass
class RecoveryDecision:
    should_pause: bool
    next_action: str
    summary: str
    evidence: list[dict[str, object]]
```

Use this instead of scattered tuple/dict conventions in runtime flow.

**Step 3: Add service-level tests**

Create [test_recovery_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_recovery_service.py) for:

- validation failure -> pause
- clean validation -> no pause
- rollback recovery success path
- rollback recovery leaves guidance when it cannot repair

**Step 4: Run the recovery-focused tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests/test_recovery_service.py tests/test_bootstrap.py -q
```

Expected:

- recovery behavior unchanged
- fewer direct branches remain in `runtime.py`

**Step 5: Commit**

```bash
git add src/aionis_workbench/recovery_service.py src/aionis_workbench/runtime.py tests/test_recovery_service.py tests/test_bootstrap.py
git commit -m "refactor: extract workbench recovery service"
```

## Task 5: Extract Live Task Orchestration into `orchestrator.py`

**Files:**
- Create: `workbench/src/aionis_workbench/orchestrator.py`
- Modify: `workbench/src/aionis_workbench/runtime.py`
- Test: `workbench/tests/test_bootstrap.py`
- Test: `workbench/tests/test_cli_shell.py`

**Step 1: Create a dedicated orchestrator**

Create [orchestrator.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py) and move:

- `run`
- `resume`
- `ingest`

The orchestrator should depend on:

- session service
- recovery service
- execution host
- runtime host
- trace recorder

**Step 2: Separate orchestration from rendering**

Keep shell/CLI payload rendering outside the orchestrator. The orchestrator should return:

- session
- task result text
- runtime metadata
- trace summary

and `runtime.py` can adapt that to the existing `WorkbenchRunResult`.

**Step 3: Preserve external method names**

`AionisWorkbench.run()`, `.resume()`, `.ingest()` should still exist and delegate.

**Step 4: Run the high-signal regression set**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests/test_bootstrap.py tests/test_cli_shell.py tests/test_shell_dispatch.py -q
```

Expected:

- shell routing unchanged
- bootstrap/recovery behavior unchanged
- CLI exit codes unchanged

**Step 5: Commit**

```bash
git add src/aionis_workbench/orchestrator.py src/aionis_workbench/runtime.py tests/test_bootstrap.py tests/test_cli_shell.py tests/test_shell_dispatch.py
git commit -m "refactor: extract live orchestration flow"
```

## Task 6: Add Runtime Bridge Contracts

**Files:**
- Create: `workbench/src/aionis_workbench/runtime_contracts.py`
- Modify: `workbench/src/aionis_workbench/aionis_bridge.py`
- Create: `workbench/tests/test_runtime_bridge_contracts.py`

**Step 1: Create local bridge response validators**

Create [runtime_contracts.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime_contracts.py) with parsing helpers for:

- kickoff recommendation response
- handoff recover response
- handoff store response
- replay run start/end response

Use standard-library dataclasses or typed dicts. Keep it lightweight.

**Step 2: Validate bridge responses before returning them**

Update [aionis_bridge.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionis_bridge.py) so each public method:

- parses runtime JSON
- raises a clear local contract error if required fields are missing

Do not silently accept malformed responses.

**Step 3: Add contract tests with mocked HTTP responses**

Create [test_runtime_bridge_contracts.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_runtime_bridge_contracts.py) covering:

- valid kickoff payload
- missing kickoff fields
- valid handoff payload
- runtime 404 handoff not found
- valid replay payload

**Step 4: Run the bridge tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests/test_runtime_bridge_contracts.py -q
```

Expected:

- malformed payloads fail locally with explicit errors

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime_contracts.py src/aionis_workbench/aionis_bridge.py tests/test_runtime_bridge_contracts.py
git commit -m "test: add runtime bridge contract validation"
```

## Task 7: Shrink `runtime.py` to a Thin Facade

**Files:**
- Modify: `workbench/src/aionis_workbench/runtime.py`
- Test: `workbench/tests/test_bootstrap.py`
- Test: `workbench/tests/test_cli_shell.py`
- Test: `workbench/tests/test_shell_dispatch.py`

**Step 1: Remove migrated private helpers from `runtime.py`**

Delete or move helpers that are now owned by:

- `ops_service.py`
- `session_service.py`
- `recovery_service.py`
- `orchestrator.py`

Leave only:

- constructor wiring
- service properties
- public facade methods
- thin result adaptation helpers that are still shared

**Step 2: Verify file-size target**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis
wc -l workbench/src/aionis_workbench/runtime.py
```

Expected:

- under `1200` lines

**Step 3: Run the full workbench regression suite**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
python3 -m pytest tests -q
```

Expected:

- full suite passes

**Step 4: Commit**

```bash
git add src/aionis_workbench/runtime.py tests
git commit -m "refactor: reduce runtime facade to service wiring"
```

## Task 8: Document the New Internal Boundary

**Files:**
- Modify: `workbench/README.md`
- Create: `workbench/docs/plans/2026-04-03-workbench-runtime-decomposition-status.md`
- Modify: `workbench/docs/product/2026-04-01-aionis-workbench-overview.md`

**Step 1: Update README internals section**

Add a short internal architecture section describing:

- facade runtime
- ops service
- session service
- recovery service
- orchestrator
- runtime bridge contracts

**Step 2: Write a status close-out**

Create a short status doc mirroring the execution plan and record:

- what moved
- final `runtime.py` line count
- tests added
- remaining debt

**Step 3: Update product overview wording**

In [aionis-workbench-overview.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-01-aionis-workbench-overview.md), update the engine module list so it no longer implies `runtime.py` is the operational home of every behavior.

**Step 4: Commit**

```bash
git add README.md docs/product/2026-04-01-aionis-workbench-overview.md docs/plans/2026-04-03-workbench-runtime-decomposition-status.md
git commit -m "docs: record workbench runtime decomposition"
```

## Recommended Execution Order

1. Task 1: stabilize tests
2. Task 2: extract ops service
3. Task 3: extract session service
4. Task 4: extract recovery service
5. Task 5: extract orchestrator
6. Task 6: add runtime bridge contracts
7. Task 7: shrink runtime facade
8. Task 8: document and close out

## Rollback Guidance

If the refactor destabilizes live paths:

- keep `runtime.py` facade signatures unchanged
- revert the last service extraction commit only
- do not revert session JSON contract changes and refactor changes in the same commit
- prefer one service extraction per commit so rollback stays narrow

## Bottom Line

This plan does not change the product. It changes where the product logic lives.

The intended outcome is:

- easier testing
- smaller review surfaces
- safer recovery changes
- a stable Workbench-to-Runtime contract
- room to continue productizing Workbench without turning `runtime.py` into the permanent bottleneck
