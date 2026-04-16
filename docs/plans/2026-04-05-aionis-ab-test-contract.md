# Aionis Workbench A/B Test Contract

Last updated: 2026-04-05

## Purpose

This benchmark does not measure which system produces the prettiest single-turn output.

It measures whether a long-running application-development task can converge more reliably under the same model and provider when run through Aionis Workbench.

## A/B arms

- `baseline`
  - same provider
  - same model
  - same repo
  - same task prompt
  - same timeout and token budget
  - thin loop
  - no Aionis continuity, retry lineage, reviewer substrate, or replan state
- `aionis`
  - same provider
  - same model
  - same repo
  - same task prompt
  - same timeout and token budget
  - full Aionis Workbench app harness and control plane

## Required controls

Every valid benchmark run must hold these constant across both arms:

- `provider_id`
- `model`
- `timeout_seconds`
- `max_completion_tokens`
- repo checkout
- scenario prompt
- validation target / evaluator target

## Required outputs

Every scenario result must expose at least:

- `scenario_id`
- `arm`
- `provider_id`
- `model`
- `ended_in`
- `total_duration_seconds`
- `retry_count`
- `replan_depth`
- `latest_convergence_signal`
- `final_execution_gate`
- `advance_reached`
- `escalated`

Every comparison must expose at least:

- `duration_delta_seconds`
- `retry_delta`
- `replan_delta`
- `convergence_delta`
- `winner`
- `summary`

## Valid endings

Benchmark endings should be normalized to a compact set:

- `advance`
- `escalate`
- `replan`
- `stalled`

## Fairness rules

- No hidden model/provider differences between arms.
- No hidden extra retry budget in Aionis unless surfaced in the report.
- No manual intervention in one arm unless the same intervention is allowed in the other.
- No narrative overclaim beyond the recorded endings and convergence signals.

## Out of scope

This benchmark does not claim to measure:

- general coding intelligence
- cross-model superiority
- browser-grade UX quality
- team collaboration throughput
- editor latency
