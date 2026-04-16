# Aionis Launcher Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn `aionis` from a Workbench-only CLI alias into a unified local product launcher that can prepare config, manage the local runtime process, and drop the user into the Workbench shell with one command.

**Architecture:** Keep `workbench` as the product entry package and add a thin launcher/process-management layer inside it. Phase 1 should assume the user already has Python and Node installed; the launcher is responsible for local state layout, runtime lifecycle, health checks, and a stable `aionis` command contract, but not for shipping a cross-platform zero-dependency installer.

**Tech Stack:** Python 3.11+, `argparse`, `subprocess`, `pathlib`, `json`, existing `aionis_workbench` CLI/runtime services, Node/npm for `runtime-mainline`, `pytest`.

---

## Why Now

`workbench` is already stable enough to deserve a real product entrypoint:

- the shell contract is clear
- `ready`, `doctor`, and `setup` already exist
- runtime probing already exists
- `aionis` is already the user-facing command alias

The main missing layer is distribution and local orchestration:

- where local Aionis state lives
- how the runtime is started and stopped
- how the launcher decides whether to boot, reuse, or warn
- how `aionis` becomes the single command users actually remember

This is the right time to build that layer because Workbench product surfaces are now much more stable than they were earlier in the week.

## Phase 1 Scope

Phase 1 should deliver:

- a real `aionis` launcher mode
- local state under `~/.aionis/`
- runtime start/stop/status helpers
- automatic local runtime boot before shell entry when possible
- a shortest-path install script for developers with Python and Node already present

Phase 1 should not deliver:

- a Homebrew tap
- a curl-pipe GA installer
- Windows support
- background auto-update
- shipping bundled Node/Python runtimes

## Product Contract

After Phase 1, the target operator flow should be:

```bash
./scripts/install-local-aionis.sh
aionis
```

Expected behavior:

1. `aionis` ensures `~/.aionis/` exists.
2. `aionis` checks whether local runtime is already healthy.
3. If not healthy, `aionis` attempts to start the bundled local runtime from the workspace.
4. If runtime becomes healthy, `aionis` launches the normal Workbench shell.
5. If runtime cannot be started, `aionis` still falls back to the current inspect-only/productized guidance.

Additional explicit commands:

- `aionis start`
- `aionis stop`
- `aionis status`
- `aionis shell`

Default:

- bare `aionis` behaves like `aionis shell`

## State Layout

Phase 1 should standardize on:

```text
~/.aionis/
  config.json
  runtime/
    pid
    stdout.log
    stderr.log
  workbench/
    last_repo_root
```

The launcher should never depend on the current repo checkout for writable process state.

## Task 1: Write the launcher contract doc and state layout constants

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/launcher_state.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_launcher_state.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the failing test**

```python
from aionis_workbench.launcher_state import launcher_paths


def test_launcher_paths_use_home_aionis_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = launcher_paths()
    assert paths.root == tmp_path / ".aionis"
    assert paths.runtime_pid == tmp_path / ".aionis" / "runtime" / "pid"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_launcher_state.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing `launcher_paths`

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class LauncherPaths:
    root: Path
    config: Path
    runtime_dir: Path
    runtime_pid: Path
    runtime_stdout: Path
    runtime_stderr: Path
    workbench_dir: Path
    last_repo_root: Path


def launcher_paths(home: Path | None = None) -> LauncherPaths:
    ...
```

Also add one short README section documenting the `~/.aionis/` layout.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_launcher_state.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/launcher_state.py tests/test_launcher_state.py README.md
git commit -m "feat: add launcher state layout"
```

## Task 2: Add a local runtime manager that can detect, start, and stop runtime-mainline

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime_manager.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_runtime_manager.py`
- Check: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/package.json`

**Step 1: Write the failing test**

```python
from aionis_workbench.runtime_manager import RuntimeManager


def test_runtime_manager_reports_missing_runtime_command(tmp_path):
    manager = RuntimeManager(workspace_root=tmp_path)
    status = manager.status()
    assert status["mode"] in {"missing", "stopped", "running"}
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_runtime_manager.py -q`
Expected: FAIL because `RuntimeManager` does not exist

**Step 3: Write minimal implementation**

```python
class RuntimeManager:
    def status(self) -> dict[str, object]:
        ...

    def start(self) -> dict[str, object]:
        ...

    def stop(self) -> dict[str, object]:
        ...
```

Implementation requirements:

- resolve workspace-local runtime path at `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline`
- use `npm` from the existing runtime workspace
- persist pid/stdout/stderr in `~/.aionis/runtime/`
- health-check the runtime using the same base URL logic Workbench already uses
- return structured statuses, not only booleans

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_runtime_manager.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime_manager.py tests/test_runtime_manager.py
git commit -m "feat: add local runtime manager"
```

## Task 3: Promote `aionis` into a launcher command family

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

```python
def test_build_parser_supports_launcher_commands():
    parser = build_parser()
    args = parser.parse_args(["status"])
    assert args.command == "status"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py -q`
Expected: FAIL because `status` is not a recognized subcommand

**Step 3: Write minimal implementation**

Add new parser commands:

- `start`
- `stop`
- `status`
- `shell`

Behavior requirements:

- bare `aionis` maps to `shell`
- `shell` first asks the runtime manager for health/startability
- `status` prints a concise structured launcher/runtime state
- `start` and `stop` are thin wrappers over `RuntimeManager`

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py tests/test_cli_shell.py
git commit -m "feat: add launcher command family"
```

## Task 4: Add shell entry behavior that boots runtime before dropping into Workbench

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

```python
def test_shell_attempts_runtime_boot_before_launch(monkeypatch, tmp_path):
    ...
    assert captured["start_called"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py tests/test_product_workflows.py -q`
Expected: FAIL because shell launch does not consult a runtime manager

**Step 3: Write minimal implementation**

Implementation requirements:

- if runtime is healthy, proceed immediately
- if runtime is unhealthy but startable, attempt a boot once
- if boot succeeds, continue into shell
- if boot fails, preserve the existing inspect-only and `ready/doctor/setup` fallback experience
- emit a stable launcher summary surface instead of dumping raw subprocess details

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py tests/test_product_workflows.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py src/aionis_workbench/ops_service.py tests/test_cli_shell.py tests/test_product_workflows.py
git commit -m "feat: auto-boot runtime on shell entry"
```

## Task 5: Add a local install script for developers with Python and Node already installed

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/scripts/install-local-aionis.sh`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/README.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the failing test**

Write a lightweight script contract in the docs first:

```bash
./scripts/install-local-aionis.sh
aionis status
```

This task is documentation-first because the script spans Python and Node setup.

**Step 2: Run the manual contract**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis
bash scripts/install-local-aionis.sh
```

Expected:

- workbench installs in editable mode
- runtime dependencies install in `runtime-mainline`
- `aionis` command becomes available in the active shell environment

**Step 3: Write minimal implementation**

Script requirements:

- verify `python3`, `pip`, `node`, and `npm` exist
- create/use `workbench/.venv`
- install `workbench` with dev extras optional but not required
- install runtime dependencies in `runtime-mainline`
- print the exact command needed to add `workbench/.venv/bin` to `PATH` if not already present

**Step 4: Run the manual contract again**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis
bash scripts/install-local-aionis.sh
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis status
```

Expected: `aionis status` prints a structured launcher/runtime status instead of failing with “command not found”

**Step 5: Commit**

```bash
git add scripts/install-local-aionis.sh README.md workbench/README.md
git commit -m "feat: add local aionis installer"
```

## Task 6: Add launcher-focused docs and first-run guidance

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/README.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionis-launcher-guide.md`

**Step 1: Write the failing docs expectation**

Add a checklist in the new guide:

- install
- start runtime
- enter shell
- inspect status
- stop runtime

**Step 2: Run the CLI manually**

Run:

```bash
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis status
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis start
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis stop
```

Expected: the guide matches the actual command behavior

**Step 3: Write minimal implementation**

Document:

- what Phase 1 does and does not automate
- that Python and Node remain prerequisites
- where `~/.aionis/` lives
- what `aionis`, `aionis start`, `aionis status`, and `aionis stop` mean

**Step 4: Run a final docs/CLI sanity check**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_launcher_state.py tests/test_runtime_manager.py tests/test_cli_shell.py tests/test_product_workflows.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add README.md workbench/README.md workbench/docs/product/2026-04-03-aionis-launcher-guide.md
git commit -m "docs: add aionis launcher guide"
```

## Acceptance Criteria

Phase 1 is complete when all of these are true:

- `aionis` is no longer just a Workbench alias in product terms; it is a launcher entrypoint
- `aionis status`, `aionis start`, `aionis stop`, and `aionis shell` exist
- shell entry attempts to boot the local runtime automatically
- failure to boot still preserves the current inspect-only product experience
- a developer with Python and Node already installed can run one local install command and then use `aionis`

## Risks

- runtime boot commands may still be too workspace-specific
- long-lived background process management may behave differently across macOS/Linux shells
- editable-install `PATH` behavior can still be confusing if the install script does not print exact next steps

## Explicit Non-Goals

- packaging `runtime-mainline` as a Python wheel
- bundling `deepagents-host` as a separate end-user command in phase 1
- daemon supervisors
- auto-upgrade
- full installer UX for users without Python/Node

## Recommended Next Phase After Phase 1

Only after this plan lands should Aionis consider:

- `brew install aionis`
- a standalone install bootstrap script
- a packaged release artifact for runtime
- a dedicated launcher repo if distribution needs diverge from Workbench internals
