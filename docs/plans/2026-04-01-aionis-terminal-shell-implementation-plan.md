# Aionis Terminal Shell Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a thin `aionis` terminal shell on top of the existing Workbench engine so a user can enter a repo, run one command, and interact with Aionis through a single terminal entrypoint instead of scattered subcommands.

**Architecture:** Keep the current Workbench engine (`runtime.py`, canonical surfaces, family instrumentation, `run/resume/ingest/evaluate/compare-family/dashboard`) intact and add a lightweight shell layer above it. Borrow the shell architecture from `/Volumes/ziel/CC/extracted-src/src` only at the bootstrap, command registry, prompt dispatch, and status-line layers; do not import the large REPL UI or Ink-heavy component tree.

**Tech Stack:** Python 3.11, `argparse`, existing `aionis_workbench` runtime/canonical surfaces, console scripts from `pyproject.toml`, optional ANSI terminal output only where it improves readability.

---

## Implementation Notes

Use these Claude Code reference files for architecture only:

- `/Volumes/ziel/CC/extracted-src/src/entrypoints/cli.tsx`
- `/Volumes/ziel/CC/extracted-src/src/commands.ts`
- `/Volumes/ziel/CC/extracted-src/src/types/command.ts`
- `/Volumes/ziel/CC/extracted-src/src/utils/handlePromptSubmit.ts`
- `/Volumes/ziel/CC/extracted-src/src/utils/cliArgs.ts`
- `/Volumes/ziel/CC/extracted-src/src/components/StatusLine.tsx`

Do **not** port these directly:

- `/Volumes/ziel/CC/extracted-src/src/screens/REPL.tsx`
- `/Volumes/ziel/CC/extracted-src/src/components/PromptInput/PromptInput.tsx`
- the broader Ink/React UI tree

The Aionis shell should stay thin:

- one executable entrypoint
- one interactive shell loop
- one structured command registry
- one canonical status-line builder
- one unified dispatch path

The Aionis shell should launch even when the user only wants inspect/evaluate/dashboard and should not eagerly initialize the heavy live-run path.

## Acceptance Targets

At the end of this slice, all of the following should be true:

1. A user can run `aionis` inside a repo and enter an interactive shell.
2. A user can still run non-interactive commands:
   - `aionis run`
   - `aionis resume`
   - `aionis ingest`
   - `aionis session`
   - `aionis evaluate`
   - `aionis compare-family`
   - `aionis dashboard`
3. Inside the shell, slash commands route through one unified dispatcher:
   - `/run`
   - `/resume`
   - `/ingest`
   - `/session`
   - `/evaluate`
   - `/compare-family`
   - `/dashboard`
   - `/status`
   - `/help`
   - `/exit`
4. The shell status line is computed from Workbench canonical surfaces, not raw `shared_memory`.
5. The shell can show current:
   - project identity / scope
   - task id
   - task family
   - strategy profile
   - validation style
   - instrumentation status
   - family trend
6. Automated tests cover:
   - bootstrap / parser behavior
   - command registry
   - slash parsing and dispatch
   - status-line rendering
   - shell loop exit/help/status behavior

## Task 1: Create Shell Test Harness

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_cli_shell.py`
- Create: `tests/test_shell_commands.py`
- Create: `tests/test_shell_dispatch.py`
- Create: `tests/test_statusline.py`

**Step 1: Create the test package**

Create `tests/conftest.py` with helpers for:

- temporary repo roots
- fake `AionisWorkbench` objects
- fake session payloads
- stdout capture helpers

Starter shape:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeResult:
    task_id: str = "task-123"
    session_path: str = "/tmp/session.json"
    content: str = "ok"
    runner: str = "ingest"
    session: dict | None = None
    canonical_surface: dict | None = None
    canonical_views: dict | None = None
    aionis: dict | None = None
    trace_summary: dict | None = None
```

**Step 2: Write the failing CLI-shell bootstrap test**

In `tests/test_cli_shell.py`, add a test that expects:

- `build_parser()` accepts interactive shell mode
- empty invocation can be routed to shell bootstrap
- explicit `shell` invocation is supported

Example:

```python
def test_parser_accepts_shell_mode():
    parser = build_parser()
    args = parser.parse_args(["shell"])
    assert args.command == "shell"
```

**Step 3: Write the failing command-registry test**

In `tests/test_shell_commands.py`, add a test that expects the registry to contain:

- `run`
- `resume`
- `ingest`
- `session`
- `evaluate`
- `compare-family`
- `dashboard`
- `status`
- `help`
- `exit`

**Step 4: Write the failing dispatch test**

In `tests/test_shell_dispatch.py`, add a test that expects:

- `/dashboard` to dispatch to the dashboard path
- `/status` to render shell status
- plain text to fall back to help text or task creation guidance

**Step 5: Write the failing status-line test**

In `tests/test_statusline.py`, add a test that builds a line from canonical surfaces and asserts it includes:

- project scope
- task family
- strategy profile
- instrumentation status

**Step 6: Run the test files and confirm they fail**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_cli_shell.py tests/test_shell_commands.py tests/test_shell_dispatch.py tests/test_statusline.py -q
```

Expected:

- import failures for missing shell modules
- parser failures for missing `shell`
- registry/statusline tests fail because implementation does not exist yet

**Step 7: Commit**

```bash
git add tests
git commit -m "test: add failing coverage for aionis terminal shell"
```

## Task 2: Add a Shell Command Contract and Registry

**Files:**
- Create: `src/aionis_workbench/shell_commands.py`
- Modify: `src/aionis_workbench/__init__.py`
- Test: `tests/test_shell_commands.py`

**Step 1: Define the command dataclasses**

Create `src/aionis_workbench/shell_commands.py` with:

- `ShellCommand`
- `ShellCommandContext`
- helper functions:
  - `get_shell_commands()`
  - `find_shell_command()`

Starter shape:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ShellCommand:
    name: str
    description: str
    aliases: tuple[str, ...] = ()
    immediate: bool = False
    expects_args: bool = False
```

**Step 2: Populate the first registry**

Register the built-in shell commands:

- `run`
- `resume`
- `ingest`
- `session`
- `evaluate`
- `compare-family`
- `dashboard`
- `status`
- `help`
- `exit`

**Step 3: Add command lookup helpers**

Implement:

- exact match by command name
- alias match
- normalized slash-command names

**Step 4: Re-run the command-registry tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_shell_commands.py -q
```

Expected:

- all registry tests pass

**Step 5: Commit**

```bash
git add src/aionis_workbench/shell_commands.py src/aionis_workbench/__init__.py tests/test_shell_commands.py
git commit -m "feat: add aionis shell command registry"
```

## Task 3: Build a Canonical Status-Line Contract

**Files:**
- Create: `src/aionis_workbench/statusline.py`
- Modify: `src/aionis_workbench/runtime.py`
- Test: `tests/test_statusline.py`

**Step 1: Create a structured status-line builder**

Add `src/aionis_workbench/statusline.py` with:

- `StatusLineInput`
- `build_statusline_input(...)`
- `render_statusline(...)`

It should read from:

- `canonical_surface`
- `canonical_views`
- `continuity_snapshot`
- dashboard summary rows when available

**Step 2: Keep the status-line based on canonical surfaces**

Do not read:

- `shared_memory`
- raw `memory_lines`
- unstructured legacy strings

The status line should prefer:

- `project_scope`
- `task_id`
- `task_family`
- `strategy_profile`
- `validation_style`
- `instrumentation.status`
- `family trend`

**Step 3: Add a runtime helper for shell status**

In `runtime.py`, add a method such as:

```python
def shell_status(self, task_id: str | None = None) -> dict[str, Any]:
    ...
```

This should return structured inputs for the shell instead of a preformatted blob.

**Step 4: Re-run status-line tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_statusline.py -q
```

Expected:

- status-line tests pass

**Step 5: Commit**

```bash
git add src/aionis_workbench/statusline.py src/aionis_workbench/runtime.py tests/test_statusline.py
git commit -m "feat: add canonical status line for aionis shell"
```

## Task 4: Implement Unified Slash/Prompt Dispatch

**Files:**
- Create: `src/aionis_workbench/shell_dispatch.py`
- Modify: `src/aionis_workbench/shell_commands.py`
- Modify: `src/aionis_workbench/runtime.py`
- Test: `tests/test_shell_dispatch.py`

**Step 1: Add a slash-command parser**

Implement:

- `/command args`
- plain `command args`
- `exit`, `quit`, `:q` aliases

Keep it minimal.

Starter shape:

```python
def parse_shell_input(text: str) -> tuple[str | None, str]:
    text = text.strip()
    if not text:
        return None, ""
    if text.startswith("/"):
        raw = text[1:]
    else:
        raw = text
    parts = raw.split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""
```

**Step 2: Add one unified dispatcher**

Implement:

- `dispatch_shell_input(...)`

It should:

- resolve the command via registry
- route to runtime methods
- return a structured payload:
  - `kind`
  - `text`
  - `payload`
  - `should_exit`
  - `should_refresh_status`

**Step 3: Map shell commands to existing runtime methods**

Dispatch targets:

- `run` -> `AionisWorkbench.run(...)`
- `resume` -> `AionisWorkbench.resume(...)`
- `ingest` -> `AionisWorkbench.ingest(...)`
- `session` -> `inspect_session(...)`
- `evaluate` -> `evaluate_session(...)`
- `compare-family` -> `compare_family(...)`
- `dashboard` -> `dashboard(...)`
- `status` -> `shell_status(...)`

**Step 4: Add help text rendering**

Add a helper that prints:

- command names
- aliases
- one-line descriptions

**Step 5: Re-run dispatch tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_shell_dispatch.py -q
```

Expected:

- slash parsing tests pass
- dispatcher tests pass
- exit/help/status tests pass

**Step 6: Commit**

```bash
git add src/aionis_workbench/shell_dispatch.py src/aionis_workbench/shell_commands.py src/aionis_workbench/runtime.py tests/test_shell_dispatch.py
git commit -m "feat: add unified shell dispatch for aionis"
```

## Task 5: Build the Thin Interactive Shell Loop

**Files:**
- Create: `src/aionis_workbench/shell.py`
- Modify: `src/aionis_workbench/runtime.py`
- Test: `tests/test_cli_shell.py`

**Step 1: Implement the shell loop**

Create `src/aionis_workbench/shell.py` with:

- `run_shell(workbench: AionisWorkbench, initial_task_id: str | None = None) -> int`

The loop should:

- render status line
- read one user input line
- dispatch via `dispatch_shell_input(...)`
- print structured JSON or short text summaries
- refresh status after mutating commands
- exit cleanly on `/exit`

Use plain `input()` or a minimal `readline`-friendly loop. Do not add Ink/TUI in this slice.

**Step 2: Keep the shell deterministic**

For each command:

- print a short human-readable summary
- optionally print JSON after it when a `--json` mode exists later

Do not mix:

- notifications
- popovers
- modal UI
- rich async task panes

**Step 3: Add a shell banner**

Show:

- repo root
- detected project identity
- quick help hint:
  - `/help`
  - `/dashboard`
  - `/run ...`
  - `/resume ...`

**Step 4: Re-run CLI-shell tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_cli_shell.py -q
```

Expected:

- shell bootstrap tests pass
- exit/help/status loop tests pass

**Step 5: Commit**

```bash
git add src/aionis_workbench/shell.py src/aionis_workbench/runtime.py tests/test_cli_shell.py
git commit -m "feat: add thin interactive aionis shell"
```

## Task 6: Integrate the Bootstrap Entry and `aionis` Console Script

**Files:**
- Modify: `src/aionis_workbench/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli_shell.py`

**Step 1: Add a `shell` subcommand**

In `cli.py`, extend the parser with:

- `shell`
- optional `--repo-root`
- optional `--task-id`

**Step 2: Make empty invocation launch the shell**

Update parser/bootstrap behavior so:

- `aionis` launches shell
- `aionis shell` launches shell
- existing subcommands still work unchanged

If needed, use a tiny eager argv branch before `argparse` fully errors out.

**Step 3: Add a second console-script alias**

Update `pyproject.toml`:

```toml
[project.scripts]
aionis-workbench = "aionis_workbench.cli:main"
aionis = "aionis_workbench.cli:main"
```

**Step 4: Keep non-interactive commands stable**

Make sure:

- `aionis run ...`
- `aionis dashboard ...`

still emit the exact JSON payloads users already rely on.

**Step 5: Re-run shell/bootstrap tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py -q
```

Expected:

- shell bootstrap tests pass
- legacy subcommand behavior remains green

**Step 6: Commit**

```bash
git add src/aionis_workbench/cli.py pyproject.toml tests/test_cli_shell.py tests/test_shell_dispatch.py
git commit -m "feat: add aionis single-entry terminal bootstrap"
```

## Task 7: Add Integration Tests Against the Real Workbench Engine

**Files:**
- Create: `tests/test_shell_integration.py`
- Modify: `tests/conftest.py`

**Step 1: Add an integration fixture**

Create a fixture that points at one of the existing real repos:

- `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond`

and uses sessions like:

- `click-2403-ingest-1`

**Step 2: Write the integration tests**

Add tests for:

- `shell_status()` pulls canonical surfaces correctly
- `dashboard` command renders family data
- `compare-family` inside the dispatcher resolves same-family peers

**Step 3: Run the integration tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m pytest tests/test_shell_integration.py -q
```

Expected:

- integration tests pass against persisted real sessions

**Step 4: Commit**

```bash
git add tests/test_shell_integration.py tests/conftest.py
git commit -m "test: add shell integration coverage against real workbench sessions"
```

## Task 8: Add User Docs for the New Shell

**Files:**
- Modify: `README.md`
- Create: `docs/product/2026-04-01-aionis-terminal-shell-brief.md`

**Step 1: Update README**

Add sections for:

- `aionis` quick start
- shell commands
- non-interactive commands
- how shell status derives from canonical surfaces

**Step 2: Add the short product note**

Create `docs/product/2026-04-01-aionis-terminal-shell-brief.md` with:

- what changed
- what the shell does
- why it is intentionally thin
- what it borrows from the inspected CC shell architecture

**Step 3: Verify README examples**

Run these manually:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m aionis_workbench.cli shell --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond
PYTHONPATH=src python3 -m aionis_workbench.cli dashboard --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond
```

Expected:

- shell opens cleanly
- dashboard command still prints valid JSON

**Step 4: Commit**

```bash
git add README.md docs/product/2026-04-01-aionis-terminal-shell-brief.md
git commit -m "docs: add aionis terminal shell usage guide"
```

## Task 9: Final Validation and Acceptance

**Files:**
- Modify: `docs/plans/2026-04-01-aionis-terminal-shell-implementation-plan.md`
- Create: `docs/plans/2026-04-01-aionis-terminal-shell-acceptance.md`

**Step 1: Run the full test suite for this slice**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
PYTHONPATH=src python3 -m pytest tests/test_cli_shell.py tests/test_shell_commands.py tests/test_shell_dispatch.py tests/test_statusline.py tests/test_shell_integration.py -q
```

Expected:

- compile succeeds
- all shell tests pass

**Step 2: Run manual acceptance commands**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m aionis_workbench.cli evaluate --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond --task-id click-2403-ingest-1
PYTHONPATH=src python3 -m aionis_workbench.cli compare-family --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond --task-id click-2403-ingest-1
PYTHONPATH=src python3 -m aionis_workbench.cli dashboard --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond
```

Expected:

- evaluate stays `ready / 100.0 / legacy_prior_line_count = 0`
- compare-family still shows `strong_match`
- dashboard still shows strong `termui` and `completion-shell` families

**Step 3: Write acceptance notes**

Create `docs/plans/2026-04-01-aionis-terminal-shell-acceptance.md` with:

- what shipped
- shell scope
- what was intentionally deferred
- acceptance evidence

**Step 4: Commit**

```bash
git add docs/plans/2026-04-01-aionis-terminal-shell-acceptance.md
git commit -m "docs: record aionis terminal shell acceptance"
```

## Deferred Work

Do not include these in this slice:

- Ink/TUI shell
- live panes for background tasks
- modal dialogs
- inline diff viewers
- complex prompt-history UI
- desktop integration
- web dashboard

Those belong in a later shell-v2 or UI-v1 slice after the thin shell proves useful.

## Recommended Execution Order

1. Task 1: test harness
2. Task 2: command contract
3. Task 3: canonical status line
4. Task 4: unified dispatch
5. Task 5: shell loop
6. Task 6: CLI/bootstrap integration
7. Task 7: integration tests
8. Task 8: docs
9. Task 9: acceptance

## Expected End State

After this plan is implemented, Aionis Workbench should have:

- a single-command terminal entrypoint
- a thin interactive shell
- a structured command system
- a canonical status line
- a unified prompt/command dispatch path
- preserved non-interactive JSON commands
- test coverage and acceptance docs

Plan complete and saved to `docs/plans/2026-04-01-aionis-terminal-shell-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
