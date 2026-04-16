# Aionis Workbench Collaboration Memory Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn Aionis Workbench from a system that records agent returns into a system that learns reusable multi-agent collaboration patterns at the project scope.

**Architecture:** Keep `tenant -> project scope -> session -> lane` as the core boundary model, but add a new memory layer for reusable collaboration patterns. These patterns are distilled from investigator / implementer / verifier returns, persisted in sessions and project-scoped storage, and re-seeded into later tasks so Workbench can choose better working sets and validation paths earlier.

**Tech Stack:** Python 3.11, dataclasses, JSON session persistence, Aionis Core replay integration, Deep Agents host flow.

---

### Task 1: Add collaboration pattern state to sessions

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py`

**Step 1: Add the data model**

Add a `CollaborationPattern` dataclass with fields for:
- `kind`
- `role`
- `summary`
- `reuse_hint`
- `confidence`
- `evidence`

Add `collaboration_patterns` to `SessionState`.

**Step 2: Load and save the new field**

Update session load/save helpers so:
- old sessions still load
- new sessions persist `collaboration_patterns`

**Step 3: Raise signal for high-quality patterns**

Update `session_signal_score()` so sessions with reusable collaboration patterns rank above empty bootstrap sessions.

**Step 4: Verify**

Run:
```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
PYTHONPATH=src python3 -m compileall src
```

Expected:
- compile succeeds

### Task 2: Distill delegation returns into reusable collaboration memory

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/policies.py`

**Step 1: Build a classifier**

Add a helper that converts delegation returns into collaboration patterns:
- investigator -> working-set discovery pattern
- implementer -> change-shape / patch-scope pattern
- verifier -> validation strategy pattern

Only promote high-signal successful returns.

**Step 2: Attach patterns during promotion**

Update `promote_insights()` so:
- `delegation_returns` still exist
- `collaboration_patterns` are generated from them
- low-value duplicates are skipped

**Step 3: Seed later tasks with patterns**

Update `seed_shared_memory()` to inject the strongest prior collaboration patterns from the same `project_scope`.

**Step 4: Verify**

Run a small Python probe that creates a session with delegation returns and confirms:
- `collaboration_patterns` are created
- later session seeding reads them

### Task 3: Document collaboration memory as a product capability

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`

**Step 1: Add product explanation**

Document:
- `delegation_packets`
- `delegation_returns`
- `collaboration_patterns`
- how project-scoped memory reuses collaboration strategies

**Step 2: Clarify what this means**

Explain that Workbench now learns:
- which working sets narrow fastest
- which validation paths pay off
- which agent roles are producing reusable results

### Task 4: Validate against the Click project memory

**Files:**
- No code required unless blocked

**Step 1: Inspect current `project:pallets/click` sessions**

Confirm recent sessions already contain the raw ingredients needed for pattern distillation.

**Step 2: Re-load or ingest one recent task if needed**

Use an existing session from the Click project to confirm the new pattern layer appears in persisted memory.

**Step 3: Verify**

Check that a later task sees:
- prior insights
- collaboration patterns
- narrowed validation strategy

### Task 5: Next milestone after this slice

**Files:**
- Follow-up work, not part of this patch

**Step 1: Artifact/reference packets**

Design the next layer so subagent outputs can persist as references instead of only summaries.

**Step 2: Strategy selection**

Use collaboration patterns to influence:
- role sequencing
- working-set prioritization
- validation-path defaults

**Step 3: Continue real-project evaluation**

Keep using `project:pallets/click` and measure whether later issues converge faster than early issues.
