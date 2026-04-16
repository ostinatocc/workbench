# Aionis Shell Guide

`Aionis Workbench` now has a thin terminal shell that is meant to feel closer to a single-entry product, without introducing a heavy TUI.

The shell is still intentionally small. It is a workflow surface over the existing Workbench engine, not a separate runtime.

## Start

```bash
cd /path/to/workbench
aionis --repo-root /absolute/path/to/repo
```

Example:

```bash
aionis --repo-root /absolute/path/to/repo
```

If you want to materialize bootstrap state explicitly for a new repo:

```bash
aionis init --repo-root /absolute/path/to/repo
```

If you want a one-command readiness check before trying live execution:

```bash
aionis doctor --repo-root /absolute/path/to/repo
```

If you want the shortest setup checklist with concrete command hints:

```bash
aionis setup --repo-root /absolute/path/to/repo
```

If you only want the still-pending setup blockers:

```bash
aionis setup --repo-root /absolute/path/to/repo --pending-only
```

If you want compact script-friendly summaries:

```bash
aionis doctor --repo-root /absolute/path/to/repo --summary
aionis setup --repo-root /absolute/path/to/repo --summary
aionis doctor --repo-root /absolute/path/to/repo --one-line
aionis setup --repo-root /absolute/path/to/repo --one-line
aionis run --repo-root /absolute/path/to/repo --task-id task-1 --preflight-only --one-line
aionis resume --repo-root /absolute/path/to/repo --task-id task-1 --preflight-only --one-line
```

If you want one named check directly:

```bash
aionis doctor --repo-root /absolute/path/to/repo --check runtime_host
aionis setup --repo-root /absolute/path/to/repo --check credentials_configured
```

For `--check NAME`, the CLI exit codes are stable:

- `0` means the named check is satisfied
- `1` means the named check exists but is still blocked
- `2` means the named check was not found

Recommended first-time setup path:

```bash
aionis init --repo-root /absolute/path/to/repo
aionis setup --repo-root /absolute/path/to/repo
aionis doctor --repo-root /absolute/path/to/repo
aionis --repo-root /absolute/path/to/repo
```

## The default path

For day-to-day use, the shell now has a simple default path:

1. pick a task
2. inspect the task and its family
3. execute the default next step
4. re-check readiness

In practice that usually looks like:

```text
/latest
/plan
/work
/fix
/review
```

If you want to select a different recent task first:

```text
/tasks --limit 5
/pick 2
/work
```

If the repo has no recorded sessions yet, the shell falls back to a cold-start bootstrap surface:

```text
/init
/status
/plan
/work
/run task-001 "Create the first narrow task" --target-file src/... --validation-command "..."
/run task-001 --preflight-only
```

That bootstrap view is inferred from the repo layout. It tries to detect source roots, test roots, manifest files, and a first validation hint so the shell is not empty on day one.
`/init` also persists the bootstrap snapshot to `.aionis-workbench/bootstrap.json` and imports a small amount of recent git history when available.
`/init` now also surfaces a compact setup summary so you can see whether the repo is already `live` or still `inspect-only`, plus the next setup step.
Structured live-preflight and host-error payloads now expose:
- `recovery_class`
- `recovery_summary`
- `recovery_command_hint`
Live execution summaries now also distinguish between:
- `missing_runtime`: the runtime is missing or unreachable
- `runtime_degraded`: the runtime is configured but currently unhealthy

## What each command is for

### `/work`

Use `/work` when you want the default working surface for the current task.

It shows:

- current task status
- task family
- selected strategy
- score
- next action
- primary validation path
- family strength and trend
- routing and artifact counts
- top same-family peers

This is the best first command after selecting a task.

### `/fix`

Use `/fix` when you want the shell to execute the default action for the current task.

Current behavior:

- if the task has a primary validation path, `/fix` executes that narrow validation step
- after the step runs, the shell refreshes the status line
- if that narrow step succeeds, Workbench records the result as a workflow-closure learning signal

Right now `/fix` is intentionally thin. It still prefers the same narrow-step execution path as `/next`, but it gives the product a clearer primary execution command and a clearer successful-closure learning signal.

### `/plan`

Use `/plan` when you want the shortest actionable summary for the current task.

It shows:

- task status
- task family
- current strategy
- current evaluation state
- the default next action
- the primary validation command
- family strength and trend
- the recommended shell path

This is the best command for quickly answering:

- what should I do right now?
- is this task ready for `/fix`?
- is this family already strong enough to trust the default path?

### `/next`

Use `/next` when you want to see or execute the recorded next step directly.

Current behavior:

- if a validation path exists, it executes validation
- otherwise it falls back to a recommendation view

`/next` is a lower-level workflow command than `/fix`.

### `/review`

Use `/review` when you want a compact readiness view before or after doing work.

It combines:

- task summary
- family summary
- evaluation status and score
- next action
- primary validation path
- instrumentation strength
- top peers

This is the best command for quickly answering:

- is this task in good shape?
- is this family already strong?
- what should I do next?

## Task selection commands

The shell keeps a current task context in the prompt. These commands help you move that context without repeatedly typing full task ids.

- `/latest`
  - switch to the latest task in the current project scope
- `/tasks [--limit N]`
  - list recent tasks
- `/pick N`
  - select one task from `/tasks`
- `/use TASK_ID`
  - pin an explicit task
- `/clear`
  - return to project-level context

## Inspection commands

- `/show [TASK_ID]`
  - show the current task summary surface
- `/family [TASK_ID] [--limit N]`
  - show the current task family reuse surface
- `/hosts`
  - show the current unified host contract for the shell, Workbench engine, and execution host
  - includes execution/runtime capability state and any degraded-mode reason
  - health states now surface directly as `available`, `degraded`, or `offline`
- `/doctor`
  - show a compact onboarding and readiness surface for the current repo
  - reports whether the current mode is `live` or `inspect-only`
  - also exposes a short `live_ready_summary` label so the readiness state can be read quickly from the shell or scripts
  - now also carries `recovery_summary` when live execution is blocked or degraded
  - highlights missing bootstrap, missing credentials, or unreachable runtime
  - add `--summary` for a compact script-friendly surface
  - add `--check NAME` to query one named readiness check directly
- `/setup`
  - show only the pending setup checklist for the current repo
  - also exposes the same short `live_ready_summary` label as `/doctor`
  - now also carries the same `recovery_summary` guidance as `/doctor`
  - highlights the next concrete command to move from `inspect-only` toward `live`
  - add `--pending-only` when you only want the remaining blockers
  - add `--summary` for a compact setup summary
  - add `--check NAME` to query one named setup item directly
- `/status`
  - now includes a compact `hosts:` summary in the status line
- `/validate [TASK_ID]`
  - rerun the primary validation path
- `/session [TASK_ID]`
  - inspect the persisted session
- `/evaluate [TASK_ID]`
  - evaluate the task against canonical surfaces
- `/compare-family [TASK_ID] [--limit N]`
  - compare against same-family peers
- `/dashboard [--limit N] [--family-limit N]`
  - show project-level family instrumentation
- `/consolidate [--limit N] [--family-limit N]`
  - run a conservative project-scoped consolidation pass
- `/dream [--limit N] [--family-limit N]`
  - shell alias for `/consolidate`
- `/background`
  - show the current consolidation maintenance state

`/family`, `/compare-family`, and `/dashboard` now also surface the latest consolidation status so reuse summaries can be read together with recent maintenance state.
`/family` also shows the latest consolidated family prior, including the dominant strategy, validation style, confidence, sample count, recent success count, source-tier counts, and the current `prior_seed` gate/reason from the last consolidation pass. If the prior is blocked, `/family` now also shows the recommended next action for unblocking it. The same recommendation now surfaces in `/plan`, `/next`, and `/fix` when the current task is sitting on that blocked prior.
`/plan`, `/work`, and `/review` also show a one-line host summary so the default workflow stays anchored to the unified CLI / Workbench / execution-host contract.
When `/run` or `/resume` fails in degraded mode, the shell now returns a structured host-aware error surface instead of only printing a raw runtime failure string. Those commands also perform a host preflight first, so an obviously unhealthy execution/runtime host is blocked before the shell tries to enter the live path.
If you only want to ask whether live execution is currently available, use `/run TASK_ID --preflight-only` or `/resume ... --preflight-only`. Add `--one-line` when you want a single-line readiness summary for scripts or startup hooks. Those variants return the same host-aware readiness surface without actually starting a live task.
Those degraded-mode and preflight surfaces now also expose a stable recovery classification and hint, so both users and scripts can distinguish missing credentials, missing runtime, and broader degraded states.

## Output modes

`/status` now also carries a compact consolidation token in the status line, so you can tell at a glance whether maintenance is disabled, running, completed, or recently skipped.

The shell defaults to short summaries.

If you want the full JSON payloads behind each command:

```text
/raw on
```

Turn it off again with:

```text
/raw off
```

## Recommended usage patterns

### Quick continue

```text
/latest
/plan
/work
/fix
/review
```

### Inspect first, then act

```text
/tasks --limit 5
/pick 3
/show
/family
/fix
```

### Project-level check

```text
/dashboard
/dream
/latest
/review
```

## Current scope

The shell is intentionally thin.

It already gives you:

- a single entry point
- task context in the prompt
- family-aware summaries
- a default execution action
- compact readiness review

It does **not** try to be:

- a full-screen TUI
- a chat UI replacement
- a heavy orchestration layer separate from Workbench

Its job is to expose the strongest current Workbench flows in a terminal-first product shape.
