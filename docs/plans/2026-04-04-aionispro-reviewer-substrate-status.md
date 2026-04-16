# AionisPro Reviewer Substrate In Workbench Status

Date: 2026-04-04

## Current State

The reviewer substrate is now first-class across the current Aionis mainline.

This did **not** add a second runtime dependency.

The architecture is now:

- `AionisPro` as design donor only
- `runtime-mainline` as the only runtime substrate
- `Workbench` as the product layer that now carries reviewer contract, review-pack, gating, and reviewer-backed learning evidence

## What Landed

### Runtime parity

`runtime-mainline` now exposes reviewer-oriented pack routes:

- `POST /v1/memory/continuity/review-pack`
- `POST /v1/memory/evolution/review-pack`

Those are the minimal parity patch needed for Workbench to consume reviewer-oriented continuity and evolution context without pulling in `AionisPro` as a runtime dependency.

### Workbench packet and session parity

Workbench now has first-class reviewer models in:

- [reviewer_contracts.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/reviewer_contracts.py)
- [execution_packet.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_packet.py)
- [session.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py)

Landed substrate:

- `ReviewerContract`
- `ResumeAnchor`
- `ReviewPackSummary`
- `review_contract`
- `reviewer_ready_required`
- `resume_anchor`
- `continuity_review_pack`
- `evolution_review_pack`

### Reviewer-aware surfaces

Workbench surfaces now show reviewer expectations directly in:

- `/work`
- `/plan`
- `/review`
- `/next`
- `/fix`

These surfaces can now show:

- reviewer standard
- required outputs
- acceptance checks
- rollback requirement
- ready flag
- resume anchor
- continuity/evolution review-pack summaries
- reviewer gate summary

### Reviewer-aware orchestration

Reviewer substrate is no longer passive state only.

Workbench now:

- prefers reviewer acceptance checks during `validate`
- carries reviewer gate data into `workflow_fix` and `workflow_next`
- hydrates `continuity_review_pack` on resume-facing flows
- hydrates `evolution_review_pack` after successful run/resume completion

### Reviewer evidence in learning

Reviewer substrate is now part of the learning and reuse story.

It now appears in:

- `family_reviewer_prior` during consolidation
- `family` shell surface
- `AutoDream` sample/candidate/promotion state
- `/dream` detail surface

Reviewer-backed family evidence now includes:

- dominant reviewer standard
- dominant reviewer pack source
- dominant required outputs
- dominant acceptance checks
- dominant resume anchor
- selected tool
- ready-required count
- rollback-required count
- reviewer sample count

## What Users Can See Now

### Family surface

`/family` can now show reviewer-backed reuse lines such as:

- `reviewer_prior=strict_review source=continuity outputs=patch|tests ...`
- `reviewer_usage=ready_required:2 rollback_required:0 anchor=resume:src/demo.py tool=read`

This means reviewer expectations are now visible as reusable family evidence, not only task-local packet state.

### Dream surface

`/dream` can now show reviewer-backed promotion evidence through:

- `top_reviewers=task:termui:strict_review:continuity:3`

This makes reviewer substrate visible as part of promotion evidence rather than an internal execution-only detail.

## Verification

Latest targeted reviewer regression:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_dream_service.py tests/test_product_workflows.py tests/test_cli_shell.py -q
```

Latest result:

- `148 passed in 3.53s`

Additional substrate compatibility regression:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_dream_models.py tests/test_reviewer_contracts.py tests/test_shell_dispatch.py -q
```

Latest result:

- `57 passed in 0.10s`

Runtime parity regression:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/runtime-mainline
npx tsx --test scripts/ci/lite-continuity-review-pack-route.test.ts scripts/ci/lite-evolution-review-pack-route.test.ts
```

Latest result:

- `2 pass`

## What This Still Is Not

This is still **not** a full standalone evaluator agent.

What landed is reviewer substrate parity:

- contract
- packet
- persistence
- gating
- review-pack hydration
- family evidence
- dream evidence

What has **not** landed yet:

- a distinct evaluator agent loop
- sprint contract negotiation
- product-grade `planner -> generator -> evaluator` harness
- hard-threshold QA agent like the Anthropic long-running app harness article describes

## Judgment

The reviewer substrate track is now complete for phase 1.

Workbench no longer just has reviewer-like language in the runtime substrate. It now:

- persists reviewer state
- surfaces reviewer expectations
- gates validation on reviewer checks
- learns from reviewer-backed workflows

That is enough to support a future evaluator agent or long-running app harness layer on top of stable ground.
