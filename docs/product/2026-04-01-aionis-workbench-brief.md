# Aionis Workbench Brief

Date: 2026-04-01

## What It Is

Aionis Workbench is a project-scoped multi-agent coding workbench.

It sits on top of:

- `deepagents` for execution
- `Aionis Core` for continuity, handoff, and replay
- `aionis-workbench` for strategy selection, artifact routing, and project memory

Its purpose is not only to run agents on a task once. Its purpose is to make later tasks in the same repo start better, reuse better evidence, and recover more cleanly.

## Core Product Claim

Workbench turns prior validated work into an advantage for later work in the same codebase.

In practice that means:

- narrower starting working sets
- more targeted validation paths
- reusable artifact-level handoffs between roles
- reusable recovery state when tasks fail
- clearer explanations for why the current strategy was selected

## How It Works

Workbench maintains project-scoped continuity through structured surfaces instead of loose memory strings.

The main control surfaces are:

- `execution_packet`
- `planner_packet`
- `strategy_summary`
- `routing_signal_summary`
- `context_layers_snapshot`
- `continuity_snapshot`

These surfaces let Workbench do four product-level things:

1. select a collaboration strategy from prior project evidence
2. route the right artifacts to the right roles
3. preserve successful work as reusable project continuity
4. preserve failures as reusable recovery state

## What Is Already Working

Foundation is already accepted:

- canonical surfaces are present and stable
- continuity no longer depends on legacy prior lines
- inspect and prompt surfaces are canonical-first
- representative real sessions evaluate as `ready / 100.0`

Workbench is already validated on a real-task corpus in `pallets/click`.

Recent validated families include:

- `task:termui`
- `task:completion-shell`
- `task:utils`
- `task:_utils`

Representative real tasks:

- `#2403`: confirm now recovers cleanly from `UnicodeDecodeError` prompt failures
- `#2869`: `click.edit(filename=Path(...))` now accepts `PathLike`
- `#2836`: string-valued `show_default` now reaches prompt display correctly
- `#2184`: shell completion callbacks now see parsed positional arguments
- `#3043`: fish completion help is normalized into a protocol-safe single line

## Current Product Advantage

The strongest current advantage is family-scoped collaboration reuse.

Workbench can now show that:

- a new `termui` task reuses prior `termui` artifact routing
- a new `shell_completion` task reuses prior `shell_completion` routing
- same-family reuse no longer drifts into unrelated modules as often

This is now visible through:

- `evaluate`
- `compare-family`
- `canonical_views.instrumentation`

## Evidence

Two representative family comparisons are already green.

### Interactive family

Anchor:

- [click-2403-ingest-1.json](/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-twentysecond/.aionis-workbench/sessions/click-2403-ingest-1.json)

Observed:

- `task_family = task:termui`
- `strategy_profile = interactive_reuse_loop`
- `instrumentation_status = strong_match`
- routed artifact hit rate = `1.0`
- same-family peers also evaluate as `strong_match`

### Completion family

Anchor:

- [click-2184-ingest-1.json](/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-nineteenth/.aionis-workbench/sessions/click-2184-ingest-1.json)

Observed:

- `task_family = task:completion-shell`
- `strategy_profile = completion_family_loop`
- `instrumentation_status = strong_match`
- routed artifact hit rate = `1.0`
- same-family peer [click-3043-ingest-1.json](/Users/lucio/.aionis-workbench/projects/project_pallets_click/sessions/click-3043-ingest-1.json) also evaluates as `strong_match`

## Current Stage

Workbench should currently be described as:

- `foundation accepted`
- `product enhancement in progress`
- `collaboration learning active`

It is already a real product kernel, but not yet a full market-facing shell.

Current limits:

- no web UI
- no public API layer
- no dashboard frontend
- collaboration learning is active, but not yet a fully dynamic routing policy engine

## Near-Term Direction

The next stage is live instrumentation and dashboarding:

- family-level match quality
- family trend and regression detection on recent session slices
- pattern reuse hit/miss
- routed artifact origin quality
- strategy explanations that can be shown directly to operators and stakeholders

That work is now underway.
