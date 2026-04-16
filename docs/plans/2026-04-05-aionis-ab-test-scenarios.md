# Aionis Workbench A/B Test Scenarios

Last updated: 2026-04-05

## Scenario family 1: persistence and hydration bug

**Repo-backed shape**

- repo: app harness real-e2e fixture repo
- prompt: fix a state persistence or hydration regression without widening the sprint too early
- expected path:
  - `plan`
  - `qa`
  - `negotiate`
  - `retry`
  - possibly `replan`
- minimum success:
  - reaches `advance`
  - or proves a lower replan/escalate rate than baseline

**Why it is fair**

This scenario rewards continuity and structured convergence. It is a bad benchmark for one-shot code generation and a good benchmark for retry/replan state handling.

## Scenario family 2: stateful UI workflow refinement

**Repo-backed shape**

- repo: app harness real-e2e fixture repo
- prompt: complete a UI workflow that requires evaluator feedback before the scope is stable
- expected path:
  - `plan`
  - `generate`
  - `qa`
  - `negotiate`
  - `retry`
  - maybe `advance`

**Why it is fair**

The value is not in raw markup output. The value is in whether the system preserves execution focus, converges after feedback, and avoids losing scope across iterations.

## Scenario family 3: follow-up sprint completion

**Repo-backed shape**

- repo: app harness real-e2e fixture repo
- prompt: complete a first sprint, then enter a follow-up sprint or second replanned sprint
- expected path:
  - `advance` into `sprint-2`
  - or `replan_depth >= 2`
- minimum success:
  - reaches a stable second-cycle policy ending

**Why it is fair**

This is where Aionis should separate clearly from a thin loop. The benchmark checks whether the system can keep structured state across multiple turns and still produce a meaningful ending.

## Benchmark recommendation

Phase 1 should start with family 1.

It already has the strongest current harness support:

- retry
- replan
- second-cycle coverage
- live convergence signals

That makes it the cleanest first proof of Aionis value.
