# Aionis Launcher Guide

`Aionis Launcher` is the Phase 1 local entrypoint for the Aionis product shell.

Its job is simple:

- install the local Python-side CLI
- prepare the local runtime workspace
- expose one stable command: `aionis`

Phase 1 is intentionally developer-oriented. It assumes you already have:

- `python3`
- `node`
- `npm`

It does not yet bundle Python or Node for you.

## Install

From the workspace root:

```bash
bash /Volumes/ziel/Aioniscli/Aionis/scripts/install-local-aionis.sh
```

That script:

- creates or reuses `/Volumes/ziel/Aioniscli/Aionis/workbench/.venv`
- installs Workbench in editable mode
- installs runtime dependencies in `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline`
- prints the exact `PATH` hint if you want bare `aionis` in your current shell

If you do not want to modify `PATH`, use the explicit binary:

```bash
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis status
```

## First Run

Shortest path:

```bash
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis status
/Volumes/ziel/Aioniscli/Aionis/workbench/.venv/bin/aionis --repo-root /absolute/path/to/repo
```

If `PATH` already includes `workbench/.venv/bin`, the same path is:

```bash
aionis status
aionis --repo-root /absolute/path/to/repo
```

## Launcher Commands

Phase 1 commands are:

```bash
aionis status
aionis start
aionis stop
aionis shell --repo-root /absolute/path/to/repo
```

Behavior:

- `aionis status`
  - prints the current launcher/runtime status
- `aionis start`
  - attempts to boot the local `runtime-mainline` process
- `aionis stop`
  - stops the managed local runtime process if one exists
- `aionis shell`
  - opens the Workbench shell
  - first checks runtime health
  - attempts one local runtime boot if runtime is not yet healthy
  - still falls back to the current inspect-only shell path if runtime boot does not succeed

Bare `aionis` is the same as:

```bash
aionis shell
```

## Local State

Launcher-managed state lives under:

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

This keeps launcher process state out of the repo checkout.

## What Phase 1 Does Not Do

Phase 1 does not yet provide:

- a Homebrew install
- a curl-pipe GA installer
- bundled Python
- bundled Node
- auto-update
- full release packaging

This slice is meant to prove the unified launcher contract first.
