# Aionisdoc -> Workbench Phase 2 Plan

**Goal:** Move `Aionisdoc` from a callable sidecar into a reusable, learnable workflow asset layer inside `Aionis Workbench`.

**Status of Phase 1:** Already complete.

Phase 1 delivered:

- `AionisdocBridge`
- `AionisdocService`
- `aionis doc ...` CLI
- `/doc ...` shell commands
- session artifact persistence
- `continuity.doc_workflow`
- publish -> recover -> resume product-path regression

Latest broad regression at the end of Phase 1:

```text
205 passed
```

Current regression after the latest Phase 2 slices:

```text
223 passed
```

---

## Why Phase 2 Exists

Phase 1 proved that Workbench can:

- compile and run `.aionis.md`
- publish/recover/resume runtime handoffs
- persist structured doc evidence into the current task session

But Phase 1 still treats doc workflows mostly as:

- operator-triggered tools
- session-scoped evidence

Phase 2 should upgrade them into:

- reusable family assets
- explainable workflow surfaces
- editor-connected workflow continuity

In short:

- Phase 1 = `Aionisdoc is callable`
- Phase 2 = `Aionisdoc becomes a learnable workflow layer`

---

## Phase 2 Priorities

The next work should happen in this order:

1. `doc -> learning`
2. `doc operator surfaces`
3. `editor / extension continuity`

Do not reverse this order.

The first priority creates durable product value.
The second makes that value visible and operable.
The third makes the whole loop feel like a product rather than a shell integration.

---

## Track 1: Doc -> Learning

### Objective

Let Workbench learn from successful doc workflows the same way it already learns from validated execution sessions.

### Product outcome

After this track lands, Workbench should be able to say:

- which `.aionis.md` workflows are commonly used for a task family
- which workflow shapes are stable enough to recommend
- which doc workflows are stale or no longer worth seeding

### What should be added

#### 1. Doc learning records

Extend the current continuity/session evidence so successful doc actions can emit structured learning rows such as:

- `task_family`
- `source_doc_id`
- `source_doc_version`
- `doc_input`
- `doc_action`
- `handoff_kind`
- `handoff_anchor`
- `selected_tool`
- `registry_path`
- `selected_artifact`
- `status`

These should be stored separately from raw artifacts.

Recommended file:

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/doc_learning.py`

This module should normalize doc workflow evidence into compact, reusable records.

#### 2. Family-level doc priors

Extend family summarization so a family can accumulate:

- dominant doc workflow
- dominant registry path
- dominant resume tool
- recent doc success count
- doc workflow confidence

These should not replace current strategy priors.
They should sit alongside them.

Recommended shape:

- `family_doc_prior`
- `doc_seed_ready`
- `doc_seed_reason`

#### 3. AutoDream integration

AutoDream should begin consuming doc workflow signals, but conservatively.

Phase 2 should let Dream evaluate:

- repeated successful use of the same `source_doc_id`
- repeated successful use of the same workflow path inside one family
- repeated recover/resume chains that converge on the same selected tool

Dream should then be able to promote:

- doc workflow candidates
- doc runtime handoff patterns

It should not yet synthesize entirely new `.aionis.md` files.

### Files likely involved

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/consolidation.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/doc_learning.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py`

### Acceptance

Track 1 is complete when:

- successful doc workflows show up in family-level summaries
- Dream can emit a doc-oriented candidate or seed-ready prior
- a later session can inspect a task family and see doc workflow reuse evidence

---

## Track 2: Doc Operator Surfaces

### Objective

Make doc workflows operable without reading raw payloads or scanning stored artifacts manually.

### Product outcome

Users should be able to answer these questions directly from Workbench:

- what doc workflow is bound to this task
- what was the latest doc action
- what anchor/handoff is active
- what can I do next

### What should be added

#### 1. `/doc show`

Add a shell surface for the current task’s doc workflow state.

It should show:

- latest action
- latest status
- source doc id/version
- handoff anchor/kind
- selected resume tool
- recent history
- preferred artifact refs

#### 2. `/doc list`

Add a repo-level discovery surface for `.aionis.md` files.

Keep this simple in Phase 2:

- search the repo root for `.aionis.md`
- show path
- maybe show whether it has known session evidence

This should not try to be a registry browser yet.

#### 3. `/doc inspect`

Add a detail surface for a specific doc path or stored doc artifact.

It should summarize:

- compile diagnostics
- selected artifact
- registry path
- handoff anchor
- recover/resume state

#### 4. CLI parity

Any shell-only doc surface that proves valuable should have a CLI equivalent:

- `aionis doc show`
- `aionis doc list`
- `aionis doc inspect`

### Files likely involved

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionisdoc_surface_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

### Acceptance

Track 2 is complete when:

- a task with doc history can be inspected from shell without raw JSON
- repo-level doc discovery is possible
- CLI and shell expose the same high-signal doc surfaces

---

## Track 3: Editor / Extension Continuity

### Objective

Connect authoring in VS Code / Cursor with Workbench continuity so doc workflows do not feel split across separate products.

### Product outcome

The user should be able to:

- write a `.aionis.md` workflow in the editor
- compile/run/publish it from the editor
- immediately see the effect in Workbench session continuity

### Why this matters

This is the product layer that can make:

- `Aionisdoc` = authoring surface
- `Workbench` = continuity, recovery, learning layer

feel like one system.

### What should be added

#### 1. Stable handoff/event contract

Define a small, stable event payload that an editor integration can emit after:

- compile
- run
- publish
- recover
- resume

Workbench should be able to ingest that payload without replaying the whole CLI chain.

Recommended file:

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/aionisdoc-workbench-event-v1.md`

#### 2. Ingest path for editor-originated doc events

Add a lightweight ingest surface that takes a doc event and projects it into:

- session artifacts
- `continuity.doc_workflow`
- family/doc learning rows

This should reuse Track 1 data structures.

#### 3. Last-mile guide

Write operator guidance for:

- using editor integration with a selected Workbench task
- matching `task_id`
- recovering when editor and shell get out of sync

### Files likely involved

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/aionisdoc-workbench-event-v1.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionisdoc-editor-continuity-guide.md`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

### Acceptance

Track 3 is complete when:

- editor-originated doc events can be recorded without manually re-running the shell command
- Workbench sees the same task continuity regardless of whether the action came from shell, CLI, or editor extension

---

## Execution Order

### Phase 2A

Do first:

- Track 1.1 doc learning records
- Track 2.1 `/doc show`
- Track 2.2 `/doc list`

This is the smallest slice that turns doc support from “callable” into “inspectable and learnable”.

Current status: complete.

Delivered:

- [doc_learning.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/doc_learning.py)
- `/doc show`
- `/doc list`
- `/doc inspect`
- `inspect_session()` now exposes `doc_learning`

### Phase 2B

Do next:

- Track 1.2 family-level doc priors
- Track 2.3 `/doc inspect`
- Track 2.4 CLI parity

Current status: mostly complete.

Delivered:

- family-level `family_doc_prior`
- `doc_seed_ready` / `doc_seed_reason`
- `/family` now exposes doc-prior reuse
- `/dashboard` now exposes repo-level doc-prior counts and top doc-prior family
- CLI/shell parity for the current doc operator surfaces
- families with only consolidated doc evidence can still appear in `dashboard`

### Phase 2C

Do last:

- Track 1.3 AutoDream doc integration
- Track 3 editor/extension continuity

Current status: partially complete.

Delivered from Track 1.3:

- AutoDream samples now absorb doc workflow evidence
- dream candidates and promoted priors now retain:
  - dominant doc input
  - dominant source doc id
  - dominant doc action
  - dominant selected tool
  - doc sample count
- `/dream` now exposes top promoted doc workflows through `top_docs=...`
- `session_service` now carries dream-promoted doc prior annotations into family prior loading

Delivered from Track 3:

- [aionisdoc-workbench-event-v1.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/aionisdoc-workbench-event-v1.md)
- `aionis doc --repo-root ... event --task-id ... --event ...`
- editor-originated doc events can now be projected into:
  - session artifacts
  - `continuity.doc_workflow`
  - `doc_learning`

Still pending in Phase 2C:

- direct extension-side emit/submit path, so the editor does not have to shell out through a file-based event handoff

---

## What Not To Do Yet

Do not do these in Phase 2:

- generate new `.aionis.md` files automatically from Dream
- replace DeepAgents with Aionisdoc execution
- build full registry authoring UX in Workbench
- build a large TUI around doc workflows

Those are later-stage product moves.

---

## Recommended First Slice

If only one next implementation slice is chosen, it should be:

1. Create `doc_learning.py`
2. Emit doc learning rows from successful publish/recover/resume
3. Add `/doc show`
4. Add product-path tests that assert doc learning is visible from task inspection

That slice has the best ratio of:

- user-visible value
- architectural leverage
- low integration risk

---

## Success Criteria

Phase 2 is successful when `Aionisdoc` is no longer just a sidecar command set.

It should become:

- visible in task continuity
- reusable at family level
- explainable from shell/CLI surfaces
- ready for editor-originated continuity ingestion

At that point, `Aionisdoc` will have moved from:

- `workflow toolchain`

to:

- `Workbench workflow asset layer`

Current assessment:

- that transition is already underway
- the workflow asset layer now exists at task, family, dashboard, and dream surfaces
- the remaining gap is editor-originated continuity, not core learnability
