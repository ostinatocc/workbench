# Aionis AutoDream Prior Compiler Status

Date: `2026-04-03`

## Outcome

The AutoDream prior-compiler plan is functionally complete for phase 1.

Workbench no longer treats `dream` as only a consolidation alias in practice. The system now extracts structured learning samples from sessions, distills strategy candidates, verifies them deterministically, promotes only trusted priors, and uses those promoted priors to seed future sessions.

That phase-1 compiler now also absorbs `Aionisdoc` workflow evidence when it exists in task continuity.

## What Exists Now

- [dream_models.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_models.py)
  - `DreamSample`
  - `StrategyCandidate`
  - `CandidateVerification`
  - `PromotedPrior`
- [dream_state.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_state.py)
  - local and project-scoped persistence for candidates and promotions
  - `.aionis-workbench/dream_candidates.json`
  - `.aionis-workbench/dream_promotions.json`
- [dream_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/dream_service.py)
  - session sample extraction
  - candidate distillation
  - held-out verification
  - promotion / deprecation lifecycle
  - persisted `run_cycle()`
  - doc workflow evidence now rides along in dream samples, candidates, and promotions
- [ops_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py)
  - `consolidate()` now runs the dream cycle
  - consolidation payloads now expose `dream_summary`
  - family rows now include best-known dream promotion annotations
- [session_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py)
  - new sessions now prefer `seed_ready` promoted priors over raw consolidation rows
  - promoted priors can seed strategy profile, validation style, validation command, and working set
  - dream-promoted doc prior annotations now also flow into loaded family priors when present
- [surface_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py)
  - strategy refresh now preserves strong promoted-prior guidance instead of overwriting it on save
- [session.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session.py)
  - forgetting signals are now available as stable summary counts for dream deprecation

## Current Lifecycle

Phase-1 AutoDream now behaves like this:

1. validated / ingested / workflow-close sessions emit structured learning samples
2. AutoDream groups compatible samples into strategy candidates
3. candidates are verified against held-out same-family evidence
4. passing candidates become `trial` or `seed_ready`
5. contradictory or stale candidates become `deprecated`
6. `seed_ready` promotions are used to seed future sessions

When doc workflow continuity exists, the same lifecycle now also retains:

- dominant doc input
- dominant source doc id
- dominant doc action
- dominant selected tool
- doc sample count

## What It Can Prove

The current implementation can now prove:

- a task family has repeated, reusable validation structure
- a strategy candidate holds across more than one task
- the candidate still matches held-out family evidence
- the candidate has not been materially superseded by newer successful guidance

This is the important threshold change from the old consolidation-only behavior:

- prior promotion is no longer only `confidence + sample_count`
- prior promotion now includes verification and deprecation

## User-Visible Effects

Today, the product-facing effect is:

- `consolidate` produces both consolidation summary and dream summary
- `/dream` now exposes a dedicated detail surface with top promotion and candidate rows
- `/dream --status seed_ready|trial|candidate|deprecated` can narrow the surface to one lifecycle slice
- `/dream` now also shows the top promotion reasons, so `trial` and `deprecated` are not only labels
- `/dream` now also shows `top_docs=...` when promoted priors carry doc workflow evidence
- `/dream` now also shows `top_doc_syncs=...` when promoted priors carry editor-originated doc continuity evidence
- `/family` now exposes blocked-prior `dream_reason` when a family is still below seed-ready
- `/dashboard` now exposes the leading `blocker_reason` so the top blocked family is easier to interpret at project scope
- `/dashboard` can now elevate proof text when editor-driven doc reuse is live
- new sessions can inherit promoted family defaults
- those defaults survive the normal save/refresh path
- stale priors can be downgraded when linked guidance keeps landing in `suppressed` or `evicted`

This means AutoDream is no longer only “remember what happened recently.” It now materially influences the next session.

## Verification

New dream-related regression coverage now includes:

- [test_dream_models.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_models.py)
- [test_dream_state.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_state.py)
- [test_dream_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_dream_service.py)
- [test_product_workflows.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py)
- [test_bootstrap.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_bootstrap.py)

Latest high-signal regression run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_bootstrap.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_recovery_service.py tests/test_runtime_bridge_contracts.py tests/test_product_workflows.py tests/test_dream_models.py tests/test_dream_state.py tests/test_dream_service.py -q
```

Result:

- `230 passed`

## Phase-1 Limits

This is still a conservative compiler, not an autonomous strategy learner.

Current limits:

- verification is deterministic and heuristic, not learned
- deprecation is driven by held-out contradiction plus forgetting signals, not deeper semantic replacement
- promotions are family-scoped defaults, not executable reusable programs
- doc evidence is promoted as reusable metadata, not as synthesized `.aionis.md` programs
- the current `/dream` surface is intentionally compact; it supports lifecycle filtering, but still shows only the top rows rather than a full interactive candidate browser
- `family` and `dashboard` currently surface only the leading dream explanation, not a fuller ranked blocker analysis
- auto-consolidation triggers dream generation indirectly through `consolidate()`, but there is no separate background dream policy yet

## Most Important Remaining Debt

- add filtering / pagination if the dream candidate set becomes large enough that the compact `/dream` surface is no longer sufficient
- consider a richer blocker browser if multiple blocked families need simultaneous diagnosis
- separate dream background policy from consolidation policy if the two cadences diverge
- consider richer verification features from runtime-side memory salience / lifecycle signals later

## Notes

- The workspace used for implementation was not a git repository, so the plan's commit steps could not be executed here.
- For now, this status doc and [2026-04-03-aionis-autodream-prior-compiler-plan.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-03-aionis-autodream-prior-compiler-plan.md) are the authoritative references for AutoDream phase-1 behavior.
