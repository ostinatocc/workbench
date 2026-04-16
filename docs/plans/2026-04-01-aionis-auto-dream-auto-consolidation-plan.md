# Aionis Auto-Dream / Auto-Consolidation Plan

**Goal:** Add a background consolidation capability to `Aionis Workbench` so project memory, family-level patterns, artifact-routing signals, and recovery samples can be periodically cleaned up and strengthened without requiring the user to manually run ingest-style maintenance.

**Product intent:** In the unified `aionis` CLI, learning should become a default system behavior rather than a manual user behavior. Successful tasks, validated tasks, and same-family reuse should accumulate automatically; a background consolidation loop should periodically convert that raw accumulation into cleaner, more stable project memory.

**Reference implementation:** Borrow the architectural pattern from `/Volumes/ziel/CC/extracted-src/src/services/autoDream/autoDream.ts` and its related files, but do not copy the memdir model directly. The parts worth borrowing are:

- gated background triggering
- a dedicated background task type
- a manual command plus automatic mode
- lock/throttle protection
- consolidation as a forked/background sub-agent workflow

The parts that should stay Aionis-specific are:

- project-scoped session store
- canonical surfaces
- continuity snapshot
- family-level strategy learning
- artifact routing and evaluation signals

---

## What We Learned From `/Volumes/ziel/CC/extracted-src/src`

The extracted source does appear to have a real `Auto-Dream` implementation.

Important reference files:

- `/Volumes/ziel/CC/extracted-src/src/services/autoDream/config.ts`
- `/Volumes/ziel/CC/extracted-src/src/services/autoDream/autoDream.ts`
- `/Volumes/ziel/CC/extracted-src/src/query/stopHooks.ts`
- `/Volumes/ziel/CC/extracted-src/src/utils/backgroundHousekeeping.ts`
- `/Volumes/ziel/CC/extracted-src/src/tasks/DreamTask/DreamTask.ts`
- `/Volumes/ziel/CC/extracted-src/src/components/memory/MemoryFileSelector.tsx`

Key takeaways:

1. `Auto-Dream` is real and configurable.
   - It is enabled by a user setting (`autoDreamEnabled`) or a feature flag fallback.

2. It is background consolidation, not a foreground command disguised as a feature.
   - It runs as a forked background subagent.

3. It is **gated**, not always on.
   - Time gate
   - session-count gate
   - lock gate
   - scan throttle

4. It is **visible** as a background task.
   - Not a silent invisible maintenance thread.

5. Automatic and manual paths coexist.
   - Background auto-dream
   - manual `/dream`

For Aionis, that means the right design is not "run memory cleanup every turn". The right design is:

- explicit background consolidation
- gated and throttled
- visible in CLI status / task views
- operating over Aionis project memory and canonical surfaces

---

## Problem Statement

Right now Aionis has these strengths:

- durable project-scoped session memory
- family-level strategy learning
- artifact routing feedback
- canonical packet / provenance / continuity surfaces
- a usable `aionis` shell with `/plan`, `/work`, `/review`, `/fix`

But it still has a missing product behavior:

- it learns from tasks
- but it does not yet **consolidate** that learning in the background

Without consolidation, the system risks:

- duplicated or drifting family patterns
- stale artifact priors staying too long
- continuity snapshots accumulating noisy projections
- recovery samples staying fragmented instead of becoming stronger priors
- heavier memory surfaces than necessary

The goal of `Auto-Consolidation` is to solve that.

---

## Desired Product Behavior

In the complete `aionis` CLI product:

1. The user works normally.
   - `/run`
   - `/resume`
   - `/fix`
   - `/validate`
   - `/ingest`

2. The system automatically absorbs successful and validated work into project memory.

3. When enough time and enough new sessions have accumulated, Aionis runs a background consolidation task.

4. That consolidation task strengthens:
   - family priors
   - artifact-routing strategies
   - continuity summaries
   - recovery sample quality

5. The user can also trigger it manually when needed.

This should feel like:

- "the project gets cleaner and smarter over time"

not:

- "I have to remember to manually reorganize Aionis memory"

---

## Scope

This slice covers:

- background consolidation design
- CLI contract
- state/lock/throttle model
- background task surface
- candidate input/output surfaces
- verification plan

This slice does **not** require:

- a web UI
- a full-screen TUI
- a full autonomous daemon separate from the shell
- a full cross-project memory optimizer

---

## Consolidation Object Model

The consolidation run should operate over the current project scope only.

Primary inputs:

- recent sessions from the current `project scope`
- canonical surfaces from those sessions:
  - `execution_packet`
  - `planner_packet`
  - `strategy_summary`
  - `pattern_signal_summary`
  - `workflow_signal_summary`
  - `maintenance_summary`
  - `context_layers_snapshot`
  - `continuity_snapshot`
- artifacts:
  - investigator
  - implementer
  - verifier
  - validation
  - timeout
  - correction
  - rollback
- instrumentation signals:
  - strong/usable/weak match
  - family trend
  - routed artifact hit rate
  - selected pattern hit count

Primary outputs:

- consolidated family priors
- pruned duplicate collaboration patterns
- updated continuity summaries
- suggested evictions / suppressions
- stronger routed artifact preferences
- recovery sample rollups

---

## Background Trigger Model

Borrow the **gated trigger** pattern from Claude Code’s `Auto-Dream`, but apply it to Aionis project memory.

### Required gates

1. **Enabled gate**
   - user setting or config flag controls whether auto-consolidation runs

2. **Project-memory gate**
   - skip if the current project has no usable sessions yet

3. **Time gate**
   - only run if enough time has elapsed since the last consolidation

4. **Session-count gate**
   - only run if enough new sessions have accumulated since the last consolidation

5. **Lock gate**
   - do not allow concurrent consolidation tasks for the same project scope

6. **Throttle gate**
   - if time gate passes but session gate does not, avoid rescanning every turn

### Recommended defaults

- `min_hours = 24`
- `min_new_sessions = 5`
- `scan_throttle_minutes = 10`

These are intentionally conservative.

---

## Trigger Location

The Aionis version should initially trigger from existing product paths, not from a brand-new scheduler.

### Phase 1 trigger points

- end of `run`
- end of `resume`
- end of `ingest`
- end of explicit `backfill`

This is closest to the Claude Code pattern:

- stop-hook / turn-end background bookkeeping

For Aionis, the equivalent is:

- end-of-task background bookkeeping

### Why this is the right first step

- the process is already alive
- project scope is known
- the just-finished session is already persisted
- there is no need to build a separate daemon first

Later, this can be extended to:

- cron-like maintenance
- shell idle maintenance
- explicit background maintenance worker

---

## Manual Command

There should also be a manual entrypoint.

Recommended shell and CLI surfaces:

- shell:
  - `/dream`
  - or `/consolidate`
- non-interactive:
  - `aionis consolidate --repo-root ...`

### Product semantics

- manual command runs the same project-scoped consolidation flow
- it should stamp/update the last consolidation time
- it should appear in shell output and canonical views

Manual command is important because:

- operators need a deterministic way to force consolidation
- debugging and demos are easier
- early rollout can rely on manual use before auto mode is enabled by default

---

## Background Task Surface

Consolidation should not be invisible.

Add a dedicated background task type, conceptually similar to Claude Code’s `DreamTask`, but Aionis-specific.

Recommended task type:

- `consolidation`

Recommended task state:

- `project_scope`
- `started_at`
- `status`
  - `running`
  - `completed`
  - `failed`
  - `killed`
- `sessions_reviewing`
- `families_reviewing`
- `patterns_updated`
- `artifacts_reviewed`
- `files_touched`
- `summary_turns`
- `prior_lock_stamp`

Recommended shell/debug surface later:

- `/background`
- or background section in `/status`

For the first slice, a persisted task record plus minimal shell visibility is enough.

---

## Consolidation Actions

The consolidation step should **not** mutate everything. It should be scoped and explicit.

### What it may do

1. Merge duplicate family patterns
   - same family
   - same routed artifact guidance
   - similar explanation text

2. Promote high-confidence family priors
   - strong same-family success
   - high routed artifact hit rate
   - multiple strong-match sessions

3. Suppress noisy or weak patterns
   - broader-similarity patterns eclipsed by same-family evidence
   - stale low-hit routing patterns

4. Tighten continuity snapshots
   - reduce duplicate prior artifact refs
   - collapse stale prior pattern projections

5. Improve recovery sample quality
   - group correction / rollback / timeout evidence into cleaner recovery references

### What it should not do in phase 1

- rewrite arbitrary raw sessions
- destroy source artifacts
- delete project history aggressively
- invent new task outcomes

Phase 1 should be **conservative consolidation**, not aggressive rewriting.

---

## Aionis-Specific Consolidation Targets

The most valuable Aionis-specific targets are:

### 1. Family priors

Consolidate:

- `task_family`
- `strategy_profile`
- `validation_style`
- `role_sequence`
- `trust_signal`

Result:

- stronger family defaults
- less drift between same-family sessions

### 2. Artifact routing patterns

Consolidate:

- `artifact_routing_strategy`
- routed role counts
- routed artifact refs
- hit/miss outcomes

Result:

- cleaner routed artifact preferences per family

### 3. Continuity projection

Consolidate:

- `continuity_snapshot.prior_artifact_refs`
- `prior_collaboration_patterns`
- `prior_strategy_*`

Result:

- smaller, more stable continuity seed

### 4. Recovery samples

Consolidate:

- timeout
- correction packet
- rollback hint
- regression expansion outcomes

Result:

- stronger recovery priors
- less fragmented failure memory

---

## Implementation Phases

## Phase 1: Conservative Manual Consolidation

**Goal:** add a manual project-scoped consolidation path with no automatic trigger yet.

### Deliverables

- new consolidation runtime entrypoint
- `aionis consolidate`
- shell alias `/dream` or `/consolidate`
- project-scoped lock and last-run stamp
- dry summary output:
  - sessions reviewed
  - families reviewed
  - patterns merged
  - patterns suppressed
  - continuity cleaned

### Files likely involved

- `src/aionis_workbench/runtime.py`
- `src/aionis_workbench/cli.py`
- `src/aionis_workbench/shell_dispatch.py`
- `src/aionis_workbench/shell_commands.py`
- new:
  - `src/aionis_workbench/consolidation.py`
  - `src/aionis_workbench/consolidation_state.py`

### Acceptance

- manual consolidation runs on one repo
- output is deterministic and project-scoped
- no live task path is broken

## Phase 2: Auto-Consolidation Gate

**Goal:** trigger consolidation automatically after task-ending flows when gates pass.

### Deliverables

- enabled flag
- time gate
- session-count gate
- scan throttle
- lock
- background invocation from task-ending flows

### Trigger points

- after `run`
- after `resume`
- after `ingest`
- after `backfill`

### Acceptance

- no consolidation when gates do not pass
- exactly one consolidation when gates do pass
- lock prevents duplicate runs

## Phase 3: Background Task Surface

**Goal:** make consolidation visible as a first-class background task.

### Deliverables

- background task record
- persisted task state
- shell visibility
- kill / fail / complete states

### Acceptance

- consolidation task visible during run
- status and completion visible after run

## Phase 4: Stronger Family Consolidation

**Goal:** use consolidation to improve strategy quality, not just reduce clutter.

### Deliverables

- merge duplicate family priors
- strengthen routed artifact preferences
- suppress weak cross-family noise
- write compact family-level summaries

### Acceptance

- compare-family and dashboard outputs become cleaner
- same-family reuse remains correct or improves

---

## CLI and Shell Contract

Recommended product surfaces:

### Non-interactive

```bash
aionis consolidate --repo-root /absolute/path/to/repo
```

Optional flags later:

- `--family task:termui`
- `--dry-run`
- `--limit N`

### Shell

```text
/dream
```

or

```text
/consolidate
```

Recommendation:

- use `/dream` as the user-facing ergonomic alias
- keep `consolidate` as the explicit implementation name

---

## Verification Plan

Verification should happen at three layers.

### 1. Unit coverage

Test:

- gate logic
- lock logic
- throttle logic
- candidate selection
- family merge/suppress decisions

### 2. Shell / CLI coverage

Test:

- `/dream` or `/consolidate`
- non-interactive `aionis consolidate`
- summary rendering
- error path rendering

### 3. Real project validation

Use real Click project scopes already accumulated in Workbench.

Priority families:

- `task:termui`
- `task:testing`
- `task:completion-shell`
- `task:decorators`

Check:

- pattern count before/after
- family status before/after
- routed artifact quality before/after
- continuity snapshot size/clarity before/after

---

## Acceptance Targets

This slice should be considered successful when:

1. A user can trigger project-scoped consolidation manually.
2. Consolidation is gated and safe.
3. Consolidation does not corrupt existing session history.
4. Family-level summaries become cleaner after consolidation.
5. Routed artifact guidance remains correct or improves.
6. The product has a clear path from:
   - manual consolidation
   - to auto-consolidation
   - to visible background maintenance

---

## Recommended Build Order

1. Manual consolidation runtime
2. CLI command
3. Shell command
4. Lock + last-run state
5. Conservative family/pattern consolidation
6. Auto-trigger gates
7. Background task surface

This order is important.

Do **not** start with a silent automatic daemon. Start with a manual, observable, deterministic consolidation path, then add automation.

---

## Bottom Line

The Claude Code extracted source confirms that `Auto-Dream` is a real and useful architectural pattern:

- gated
- background
- visible
- manual + automatic
- focused on memory consolidation

For Aionis, the right adaptation is:

- **project-scoped auto-consolidation**
- over canonical surfaces, family priors, routing patterns, and recovery samples
- first manual, then gated automatic
- visible as a background product capability rather than hidden maintenance
