# AionisPro Reviewer Substrate To Workbench Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Promote AionisPro's evaluator-like reviewer contract and review-pack substrate into Workbench as first-class packet, session, review, and orchestration capabilities.

**Architecture:** Do not invent a new evaluator system first. Reuse the reviewer substrate that already exists in `runtime-mainline` and project it all the way through Workbench's Python packet/session/surface/orchestration layers. Where `AionisPro` has reviewer-oriented continuity/evolution pack shapes that `runtime-mainline` does not yet expose, add only the smallest possible parity patch to `runtime-mainline` first, then consume that contract from Workbench. Land this in four slices: packet model parity, session persistence, review-aware surfaces and gating, then reviewer-pack and learning integration.

**Tech Stack:** Python, `pytest`, existing Workbench runtime/session/orchestrator/shell modules, current `runtime-mainline` execution packet contract, JSON session persistence.

---

## Why This Plan Exists

The current repo already contains most of the reviewer substrate on the TypeScript runtime side:

- `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/execution/types.ts`
- `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/execution/packet.ts`
- `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/execution/transitions.ts`
- `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/memory/handoff.ts`
- `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/routes/memory-context-runtime.ts`

Desktop `AionisPro` confirms the intended shape:

- `/Users/lucio/Desktop/Aionis/src/execution/types.ts`
- `/Users/lucio/Desktop/Aionis/src/memory/continuity/history.ts`
- `/Users/lucio/Desktop/Aionis/src/memory/evolution-inspect.ts`

The main missing layer is Workbench.

Right now Workbench still treats execution packets as a reduced summary object:

- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_packet.py`

That means reviewer contract data exists in the runtime substrate, but Workbench cannot yet:

- persist it as first-class session state
- show it in `/work`, `/plan`, `/review`
- use it to gate resume/fix/validate flows
- learn from review contracts later

This plan closes that gap without pretending Workbench already has a full standalone evaluator agent.

One important refinement from the repository diff:

- `runtime-mainline` already matches `AionisPro` on execution-level reviewer substrate
- `runtime-mainline` does **not** currently expose `continuity_review_pack` / `evolution_review_pack` equivalents in the same shape as `AionisPro`

So this plan is **Workbench-first with a minimal runtime-mainline parity patch where strictly necessary**.

## Target Outcome

After this plan lands, Workbench should be able to:

- carry `review_contract` and `reviewer_ready_required` in its execution packet model
- persist reviewer contract state in sessions and continuity
- show reviewer expectations in `work`, `plan`, and `review`
- respect reviewer gating in `workflow_fix`, `validate_session`, and resume-facing flows
- expose reviewer-oriented continuity/evolution pack summaries as inspectable artifacts

This plan explicitly does **not** require a full `planner -> generator -> evaluator` harness yet. It only makes reviewer substrate first-class so that harness can be built later on stable ground.

## Implementation Status

Completed on 2026-04-04:

- `Task 0`: `runtime-mainline` reviewer-pack parity routes landed
- `Task 1`: reviewer contract models landed
- `Task 2`: execution packet reviewer parity landed
- `Task 3`: session persistence for reviewer substrate landed
- `Task 4`: reviewer-aware execution packet construction landed
- `Task 5`: `/work`, `/plan`, `/review` reviewer surfaces landed
- `Task 6`: reviewer gating now prefers acceptance checks on validate/fix paths
- `Task 7`: continuity/evolution review-pack summaries now surface through canonical views and shell
- `Task 9`: bridge/runtime-host contract coverage for review-pack routes landed

Remaining:

- none; Tasks `0-10` are now complete

## Recommended Files

### New source files

- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/reviewer_contracts.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_reviewer_contracts.py`

### Likely modified source files

- Modify: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/memory/handoff.ts`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/routes/memory-access.ts`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/memory/schemas.ts`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_packet.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/workflow_surface_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`

### Tests

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_runtime_bridge_contracts.py`

### Docs

- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionispro-reviewer-substrate-status.md`

## Contract Mapping

The Workbench-side model should align with the existing runtime substrate rather than inventing new names.

Minimum reviewer contract fields:

- `standard`
- `required_outputs`
- `acceptance_checks`
- `rollback_required`

Minimum packet additions:

- `review_contract`
- `reviewer_ready_required`
- `resume_anchor`

Minimum review-pack summary fields:

- `pack_version`
- `source`
- `review_contract`
- `selected_tool`
- `target_files`
- `next_action`
- `artifact_refs`

## Task 0: Verify and patch minimal runtime-mainline reviewer parity

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/memory/handoff.ts`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/routes/memory-access.ts`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/runtime-mainline/src/memory/schemas.ts`
- Test: existing runtime-mainline reviewer or memory route tests

**Step 1: Write the failing test**

Add the smallest failing test or route-level assertion that proves the current `runtime-mainline` contract is missing one or both of:

- continuity review-pack summary shape
- evolution review-pack summary shape

Do **not** invent a large new API. The goal is only to match the minimum reviewer-oriented pack data that Workbench will consume later.

**Step 2: Run test to verify it fails**

Run the targeted `runtime-mainline` suite for the touched route or memory builder.

Expected:

- FAIL because current `runtime-mainline` does not yet expose the required reviewer pack summary

**Step 3: Write minimal implementation**

Implement only the missing parity:

- continuity review-pack summary shape compatible with Pro
- evolution review-pack summary shape compatible with Pro
- schema and route registration if needed

Do not add a new evaluator loop, new workflow system, or a second runtime dependency.

**Step 4: Run test to verify it passes**

Run the same targeted suite and expect PASS.

**Step 5: Commit**

```bash
git add runtime-mainline/src/memory/handoff.ts runtime-mainline/src/routes/memory-access.ts runtime-mainline/src/memory/schemas.ts
git commit -m "feat: add reviewer pack parity to runtime-mainline"
```

## Task 1: Add failing tests for reviewer contract models

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_reviewer_contracts.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/reviewer_contracts.py`

**Step 1: Write the failing test**

Test cases:

- `ReviewerContract.from_dict(...)` accepts runtime-shaped data
- missing or malformed data returns `None`
- `ResumeAnchor.from_dict(...)` and `ReviewPackSummary.from_dict(...)` round-trip stable dictionaries

Example test shape:

```python
def test_reviewer_contract_from_dict_accepts_runtime_shape():
    contract = ReviewerContract.from_dict(
        {
            "standard": "strict",
            "required_outputs": ["patch", "tests"],
            "acceptance_checks": ["pytest -q"],
            "rollback_required": True,
        }
    )
    assert contract is not None
    assert contract.standard == "strict"
    assert contract.rollback_required is True
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_reviewer_contracts.py -q
```

Expected:

- FAIL because `reviewer_contracts.py` does not exist yet

**Step 3: Write minimal implementation**

Implement:

- `ReviewerContract`
- `ResumeAnchor`
- `ReviewPackSummary`
- `from_dict(...)`
- `to_dict(...)`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/reviewer_contracts.py tests/test_reviewer_contracts.py
git commit -m "test: add reviewer contract models"
```

## Task 2: Extend execution packet parity with reviewer fields

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_packet.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/tests/test_reviewer_contracts.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add assertions that `ExecutionPacket.from_dict(...)` can carry:

- `review_contract`
- `reviewer_ready_required`
- `resume_anchor`

and that packet summaries preserve reviewer presence flags.

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_reviewer_contracts.py tests/test_product_workflows.py -q
```

Expected:

- FAIL because Workbench packet models do not yet include reviewer fields

**Step 3: Write minimal implementation**

Update:

- `ExecutionPacket`
- `ExecutionPacketSummary`

Add:

- nested reviewer contract parsing
- `reviewer_ready_required: bool`
- `resume_anchor`
- summary booleans like `review_contract_present`

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/execution_packet.py tests/test_reviewer_contracts.py tests/test_product_workflows.py
git commit -m "feat: add reviewer fields to execution packet"
```

## Task 3: Persist reviewer substrate in session state

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add a session persistence test asserting:

- reviewer contract survives save/load
- resume anchor survives save/load
- review-pack summary survives save/load

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -q
```

Expected:

- FAIL because session serialization drops reviewer substrate

**Step 3: Write minimal implementation**

Update `SessionState` and its serialization helpers so reviewer contract objects become stable persisted state.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/session.py src/aionis_workbench/session_service.py tests/test_product_workflows.py
git commit -m "feat: persist reviewer substrate in sessions"
```

## Task 4: Build reviewer-aware execution packets in runtime

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add assertions that `_build_execution_packet(...)` now produces reviewer-aware packet fields when:

- a correction or validation context implies review
- rollback semantics are active
- continuity carries reviewer hints

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -q
```

Expected:

- FAIL because runtime packet builder does not yet populate reviewer data

**Step 3: Write minimal implementation**

Populate:

- `review_contract`
- `reviewer_ready_required`
- `resume_anchor`

Keep this conservative:

- derive from current validation/recovery state first
- do not invent autonomous evaluator logic here

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime.py tests/test_product_workflows.py
git commit -m "feat: build reviewer-aware execution packets"
```

## Task 5: Surface reviewer expectations in inspect and shell views

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`

**Step 1: Write the failing test**

Add assertions that `/work`, `/plan`, and `/review` include:

- reviewer standard
- required outputs
- acceptance checks
- rollback requirement

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py -q
```

Expected:

- FAIL because shell surfaces do not yet render reviewer details

**Step 3: Write minimal implementation**

Expose reviewer info in:

- inspection payloads
- shell render helpers
- recommended command summaries when review is required

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/evaluation_service.py src/aionis_workbench/shell.py src/aionis_workbench/shell_dispatch.py tests/test_cli_shell.py tests/test_shell_dispatch.py
git commit -m "feat: surface reviewer contract in workbench views"
```

## Task 6: Add reviewer gating to workflow fix and validation paths

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/workflow_surface_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add assertions that:

- when `reviewer_ready_required` is true, `workflow_fix` and validate paths preserve reviewer expectations
- resume/fix does not silently drop reviewer contract
- validation override still replaces stale command chains

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -q
```

Expected:

- FAIL because reviewer gating is not enforced yet

**Step 3: Write minimal implementation**

Implement conservative rules:

- preserve reviewer contract across fix/resume
- if reviewer gating is active, keep acceptance checks visible in next action
- do not regress the existing `resume --validation-command` override behavior

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/workflow_surface_service.py src/aionis_workbench/orchestrator.py tests/test_product_workflows.py
git commit -m "feat: add reviewer gating to workflow paths"
```

## Task 7: Introduce continuity and evolution review-pack summaries

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/evaluation_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add assertions that a session inspect payload now carries:

- `continuity_review_pack`
- `evolution_review_pack`

at least as summary objects, not raw runtime blobs.

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -q
```

Expected:

- FAIL because Workbench does not yet project review-pack summaries

**Step 3: Write minimal implementation**

Build thin summary objects only:

- source
- contract
- selected tool
- target files
- next action
- artifact refs

Do not implement a new remote route client in this task unless needed.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime.py src/aionis_workbench/evaluation_service.py src/aionis_workbench/session_service.py tests/test_product_workflows.py
git commit -m "feat: project review pack summaries into workbench"
```

## Task 8: Make reviewer substrate visible in family and dream evidence

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add assertions that reviewer-backed sessions contribute stable evidence such as:

- reviewer standard
- acceptance check count
- rollback requirement

into learning paths without inventing new dream policy yet.

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_product_workflows.py -q
```

Expected:

- FAIL because reviewer substrate is not yet reflected in learning evidence

**Step 3: Write minimal implementation**

Thread reviewer evidence into existing learning summaries conservatively.

Do not yet create a dedicated evaluator promotion policy.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add src/aionis_workbench/session_service.py src/aionis_workbench/dream_service.py tests/test_product_workflows.py
git commit -m "feat: thread reviewer evidence into learning signals"
```

## Task 9: Add bridge and contract regression coverage

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_runtime_bridge_contracts.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

Add regression tests asserting:

- malformed reviewer contract payloads fail clearly
- missing optional reviewer fields remain backward compatible
- old sessions without reviewer substrate still load

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_runtime_bridge_contracts.py tests/test_product_workflows.py -q
```

Expected:

- FAIL until compatibility and validation behavior are explicit

**Step 3: Write minimal implementation**

Harden packet/session parsing and keep compatibility with historical sessions.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_runtime_bridge_contracts.py tests/test_product_workflows.py src/aionis_workbench/execution_packet.py src/aionis_workbench/session.py
git commit -m "test: lock reviewer substrate compatibility"
```

## Task 10: Document the new reviewer substrate layer

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-04-aionispro-reviewer-substrate-status.md`

**Step 1: Write the failing doc checklist**

Checklist:

- README mentions reviewer-aware packet and review loop
- status doc explains what was ported from Pro
- status doc clearly states what still is **not** implemented:
  - no standalone evaluator agent
  - no full planner-generator-evaluator harness yet

**Step 2: Run manual verification**

Open the doc files and verify the checklist is not yet satisfied.

**Step 3: Write minimal documentation**

Document:

- the new packet fields
- reviewer-aware shell surfaces
- gating behavior
- review-pack summaries
- remaining gap to a full evaluator harness

**Step 4: Run final targeted tests**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_reviewer_contracts.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_product_workflows.py tests/test_runtime_bridge_contracts.py -q
```

Expected:

- PASS

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-04-04-aionispro-reviewer-substrate-status.md
git commit -m "docs: record reviewer substrate integration status"
```

## Acceptance Checklist

The plan is complete only when all of the following are true:

- Workbench execution packets carry reviewer contract fields
- session save/load preserves reviewer substrate
- `/work`, `/plan`, and `/review` render reviewer expectations
- reviewer gating survives fix/resume/validate flows
- continuity/evolution review-pack summaries are inspectable
- compatibility with old sessions remains intact
- docs clearly state this is reviewer substrate parity, not a full evaluator agent

## Execution Notes

- Prefer copying the runtime contract shape, not inventing Workbench-only field names.
- Keep the first pass summary-oriented. Do not overbuild review-pack retrieval.
- Do not block on a full evaluator agent design.
- Treat this plan as the substrate layer for a later long-running app harness.

Plan complete and saved to `workbench/docs/plans/2026-04-04-aionispro-reviewer-substrate-workbench-integration-plan.md`. Two execution options:

1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
