# Aionis Workbench Foundation Memory Learning Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade Aionis Workbench from a project-scoped memory workbench into a system that learns reusable multi-agent execution strategy through execution packets, trust-shaped pattern affinity, planner/provenance contracts, and layered context budgeting.

**Architecture:** Keep `tenant -> project scope -> session -> lane` as the persistent boundary model, but add a stable `execution packet` surface, strategy affinity based on `task signature / task family / error family`, a planner/provenance summary contract, and a layered context assembly pipeline with explicit budgets and forgetting. The end state is that Workbench no longer chooses strategy mostly from file similarity and ad hoc memory lines, but from structured execution state and trust-shaped project memory.

**Tech Stack:** Python 3.11, dataclasses, JSON session persistence, Deep Agents host flow, Aionis Core HTTP bridge, Click real-task project corpus, local artifact store.

---

### Task 1: Create the product contract docs before code changes

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/workbench-execution-packet-v1.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/contracts/workbench-planner-provenance-v1.md`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Write the execution packet contract**

Document a stable `execution packet` with these fields:
- `packet_version`
- `current_stage`
- `active_role`
- `task_brief`
- `target_files`
- `next_action`
- `hard_constraints`
- `accepted_facts`
- `pending_validations`
- `unresolved_blockers`
- `rollback_notes`
- `artifact_refs`
- `evidence_refs`

**Step 2: Write the planner/provenance contract**

Document canonical surfaces for:
- `planner_packet`
- `strategy_summary`
- `pattern_signal_summary`
- `workflow_signal_summary`
- `maintenance_summary`
- `execution_packet_summary`

Define which field is authoritative when summaries and session memory disagree.

**Step 3: Update README**

Add a concise product section that explains:
- Workbench now learns from `execution packets`
- strategy choice is trust-shaped, not only path-matched
- artifacts and provenance are first-class memory surfaces

**Step 4: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
test -f docs/contracts/workbench-execution-packet-v1.md
test -f docs/contracts/workbench-planner-provenance-v1.md
```

Expected:
- both contract docs exist

### Task 2: Introduce trust-shaped strategy affinity primitives

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/policies.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`

**Step 1: Extend collaboration patterns with affinity metadata**

Add these optional fields to `CollaborationPattern`:
- `task_signature`
- `task_family`
- `error_family`
- `affinity_level`

Use conservative defaults so old sessions still load.

**Step 2: Add task and error family extraction helpers**

Implement helpers in `policies.py` that derive:
- `task_signature`
- `task_family`
- `error_family`

Sources should include:
- task text
- target files
- validation summary
- correction packet failure name
- rollback/timeout artifact summaries

**Step 3: Replace pure file-based ranking with mixed affinity**

Upgrade `select_collaboration_strategy()` to score prior sessions and patterns by:
1. `exact_task_signature`
2. `same_task_family`
3. `same_error_family`
4. `module_affinity`
5. `path_affinity`

`task/error family` should beat module/path affinity when available.

**Step 4: Refresh pattern promotion**

Update `refresh_collaboration_patterns()` and `promote_insights()` so new patterns store the inferred task/error family metadata.

**Step 5: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
PYTHONPATH=src python3 - <<'PY'
from aionis_workbench.session import load_session
from aionis_workbench.policies import select_collaboration_strategy

prior = load_session('/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth', 'click-3193-ingest-1')
strategy = select_collaboration_strategy(
    prior_sessions=[prior] if prior else [],
    target_files=['src/click/_utils.py', 'tests/test_utils.py'],
    validation_commands=['PYTHONPATH=src python3 tmp/repro_3193.py'],
)
print(strategy.role_sequence)
print(strategy.preferred_artifacts[:2])
PY
```

Expected:
- compile succeeds
- strategy returns a non-empty role sequence
- preferred artifacts are drawn from the `_utils.py` task line, not unrelated files

### Task 3: Create a stable execution packet model

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_packet.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/policies.py`

**Step 1: Add packet dataclasses**

Create dataclasses:
- `ExecutionPacket`
- `ExecutionPacketSummary`

Include fields:
```python
packet_version: int
current_stage: str
active_role: str
task_brief: str
target_files: list[str]
next_action: str | None
hard_constraints: list[str]
accepted_facts: list[str]
pending_validations: list[str]
unresolved_blockers: list[str]
rollback_notes: list[str]
artifact_refs: list[str]
evidence_refs: list[str]
```

**Step 2: Persist packet state in sessions**

Add `execution_packet` and `execution_packet_summary` to `SessionState`.

Update load/save logic so old sessions still deserialize.

**Step 3: Build packets from current Workbench artifacts**

In `runtime.py`, create one canonical builder that derives the packet from:
- correction packet
- rollback hint
- timeout artifact
- validation result
- delegation packets
- current task/working set

**Step 4: Stop duplicating execution intent across prompt surfaces**

Update `build_memory_prompts()` and `build_delegation_prompt()` to read from `execution_packet` first, then fall back to raw legacy memory lines.

**Step 5: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
PYTHONPATH=src python3 - <<'PY'
from aionis_workbench.session import load_session
session = load_session('/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth', 'click-2786-workbench-2', project_scope='project:pallets/click')
print(bool(session and getattr(session, 'execution_packet', None)))
PY
```

Expected:
- compile succeeds
- stress-case session has an execution packet after refresh/backfill

### Task 4: Unify correction, rollback, and delegation into the packet lifecycle

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/policies.py`

**Step 1: Map each failure class to packet stages**

Use explicit stages such as:
- `investigating`
- `implementing`
- `verifying`
- `paused_timeout`
- `paused_regression_expansion`
- `paused_scope_drift`
- `rollback_recovery`

**Step 2: Populate `accepted_facts` and `unresolved_blockers`**

Examples:
- `accepted_facts = ['baseline failing test is X', 'target file is src/click/core.py']`
- `unresolved_blockers = ['provider timeout', 'rollback candidate still fails baseline test']`

**Step 3: Move next-action phrasing into one place**

Generate `next_action` only from the packet builder, not from scattered prompt helpers.

**Step 4: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 - <<'PY'
from aionis_workbench.session import load_session
session = load_session('/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth', 'click-2786-workbench-2', project_scope='project:pallets/click')
packet = getattr(session, 'execution_packet', None)
print(packet.current_stage if packet else None)
print(packet.next_action if packet else None)
print(packet.unresolved_blockers[:3] if packet else [])
PY
```

Expected:
- stress-case session exposes one clear stage and one clear next action

### Task 5: Introduce layered context assembly with explicit budgets

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/context_layers.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/policies.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`

**Step 1: Add layer and budget models**

Create layer names:
- `facts`
- `episodes`
- `rules`
- `static`
- `decisions`
- `tools`
- `citations`

Add config objects for:
- `char_budget_total`
- `char_budget_by_layer`
- `max_items_by_layer`
- `forgetting_policy`

**Step 2: Map current Workbench memory into layers**

Map:
- promoted insights -> `facts`
- prior sessions / delegation returns -> `episodes`
- hard constraints / rollback guidance -> `rules`
- repo identity / static task framing -> `static`
- execution packet summaries -> `decisions`
- validation commands / tool choices -> `tools`
- artifact refs / evidence refs -> `citations`

**Step 3: Build one context assembly function**

Add a function like:
```python
assemble_context_layers(session, strategy) -> dict[str, list[str]]
```

Then build final prompt surfaces from the layered output instead of ad hoc concatenation.

**Step 4: Honor budgets and forgetting**

When the layer budget is exceeded:
- higher salience items win
- `evicted` forgetting entries never re-enter active layers
- `suppressed` entries only re-enter if exact task signature matches

**Step 5: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
PYTHONPATH=src python3 - <<'PY'
from aionis_workbench.session import load_session
from aionis_workbench.context_layers import assemble_context_layers

session = load_session('/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-seventeenth', 'click-2645-ingest-1', project_scope='project:pallets/click')
layers = assemble_context_layers(session=session)
print(sorted(layers.keys()))
for key, value in layers.items():
    print(key, len(value))
PY
```

Expected:
- layer assembly returns the expected layer names
- each layer has bounded item counts

### Task 6: Make planner/provenance summaries a real runtime surface

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/provenance.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`

**Step 1: Define summary builders**

Create functions for:
- `build_execution_packet_summary`
- `build_pattern_signal_summary`
- `build_workflow_signal_summary`
- `build_maintenance_summary`

**Step 2: Persist summaries with sessions**

Add fields to `SessionState` for:
- `planner_packet_summary`
- `pattern_signal_summary`
- `maintenance_summary`

**Step 3: Use provenance text consistently**

Standardize phrases like:
- `Selected strategy because exact task signature matched`
- `Selected artifacts because same task family matched`
- `Suppressed prior pattern because a newer validation strategy superseded it`

These summaries should be the only canonical explanation lines injected into prompts and shown in docs/examples.

**Step 4: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
PYTHONPATH=src python3 - <<'PY'
from aionis_workbench.session import load_session
session = load_session('/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth', 'click-3193-ingest-1', project_scope='project:pallets/click')
print(bool(session and getattr(session, 'planner_packet_summary', None)))
print(bool(session and getattr(session, 'pattern_signal_summary', None)))
PY
```

Expected:
- summaries exist and are non-empty

### Task 7: Backfill the Click corpus into the new schema

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`

**Step 1: Extend `backfill`**

Backfill should now refresh:
- collaboration pattern affinity metadata
- execution packet
- planner/provenance summaries
- context layers snapshot if present

**Step 2: Rebuild the canonical Click project corpus**

Backfill at least these sessions:
- `click-2645-ingest-1`
- `click-3193-ingest-1`
- `click-3242-ingest-1`
- `click-2968-ingest-1`
- `click-3110-ingest-1`

**Step 3: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m aionis_workbench.cli backfill --repo-root /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth --task-id click-3193-ingest-1
```

Expected:
- session rewrites cleanly
- no model key required
- no runtime required

### Task 8: Validate behavior on one new real Click task

**Files:**
- No fixed code files in advance; task-dependent

**Step 1: Pick one new task in `decorators`, `utils`, or `core/help`**

Create a fresh worktree under:
```bash
/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-nineteenth
```

**Step 2: Run the new Workbench strategy selection**

Confirm the new task starts with:
- `task/error family`-aware strategy
- layered context
- execution packet
- preferred artifact refs

**Step 3: Measure whether start-up is narrower**

Record:
- chosen working set
- chosen validation path
- selected prior artifacts
- selected role sequence

**Step 4: Commit**

When the implementation slice is complete:
```bash
git add docs/contracts docs/plans src
git commit -m "feat: add foundation memory learning contracts"
```

### Task 9: Final acceptance checklist

**Files:**
- Review only

**Step 1: Product checks**

Confirm:
- Workbench no longer depends only on path/module affinity
- execution state is represented by a stable packet
- planner/provenance surfaces are explicit
- context assembly is layered and budgeted

**Step 2: Corpus checks**

Confirm at least two different module families in `project:pallets/click` now produce:
- non-empty execution packets
- non-empty planner summaries
- task/error family metadata

**Step 3: Regression checks**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
```

Then rerun targeted validations for the latest real samples:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-seventeenth
PYTHONPATH=src python3 tmp/repro_2645.py
PYTHONPATH=src python3 -m pytest tests/test_utils.py -q -k 'lazyfile_read_fifo_does_not_eagerly_drain_pipe'

cd /Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-eighteenth
PYTHONPATH=src python3 tmp/repro_3193.py
PYTHONPATH=src python3 -m pytest tests/test_utils.py -q -k 'unset_sentinel_round_trips_through_multiprocessing or test_unset_sentinel'
```

Expected:
- all pass

### Task 10: Post-slice follow-up

**Files:**
- Follow-up only

**Step 1: Add live instrumentation**

Track:
- strategy selected
- why it was selected
- which family matched
- which artifacts were injected

**Step 2: Add evaluation sheet**

Compare later Click tasks against early tasks by:
- initial working set width
- number of validation attempts
- artifact reuse count
- pattern reuse count

**Step 3: Expand beyond Click**

Only after this slice is stable, try the same product model on one second repo.
