# Aionis Workbench A/B Test Status

Updated: 2026-04-05

## Goal

Prove Aionis Workbench's value with a real, complex, multi-turn application-development A/B test.

The benchmark compares:

- `A`: a thin baseline loop with the same provider, model family, repo, and task family
- `B`: the same task family running through Aionis Workbench

This benchmark is not trying to prove that Aionis writes better one-shot code. It is trying to prove that Aionis converges more reliably across longer loops because it preserves state, structures retries, and carries forward richer execution signals.

## Current Scope

Phase-1 benchmark coverage now includes:

- benchmark result models
- thin-loop baseline normalization
- Aionis task-state extraction
- compact comparison summary and winner selection
- `aionis ab-test compare`
- deterministic real-e2e benchmark coverage
- three narrow credential-gated live A/B scenarios

## Current Status

Completed:

- `ab_test_models.py`
- `ab_test_baseline.py`
- `ab_test_runner.py`
- `ab_test_report.py`
- runtime `ab_test_compare(...)`
- CLI and shell surface
- `BenchmarkRun` markdown renderer
- deterministic real-e2e benchmark:
  - `tests_real_e2e/test_real_ab_test_report.py`
- narrow live A/B benchmarks:
  - `tests_real_live_e2e/test_live_ab_test_report.py`
  - `tests_real_live_e2e/test_live_ab_test_second_cycle_report.py`
  - `tests_real_live_e2e/test_live_ab_test_ui_refinement_report.py`

Current live A/B shape:

- Aionis arms:
  - first-cycle `live-app-replan-generate-qa-advance`
  - second-cycle `live-app-second-replan-generate-qa-advance`
  - stateful UI refinement `live-app-replan-generate-qa-advance`
- baseline arm:
  - normalized thin-loop ending in `escalate`

The live compare currently measures:

- ending difference
- timing delta
- retry/replan shape
- final execution gate
- compact convergence signal

Current compact report shape:

| Scenario | Winner | Baseline | Aionis | Duration Δ (s) | Retry Δ | Replan Δ |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `persistence-and-hydration` | `aionis` | `escalate` | `advance` | `+30.00` | `0` | `+1` |

## Verification

Deterministic benchmark/report coverage:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest \
  tests/test_ab_test_models.py \
  tests/test_ab_test_baseline.py \
  tests/test_ab_test_runner.py \
  tests/test_ab_test_report.py \
  tests/test_cli_shell.py \
  tests/test_shell_dispatch.py \
  tests_real_e2e/test_real_ab_test_report.py \
  -q
```

Latest result:

- `205 passed in 8.15s`

Credential-gated live benchmark:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests_real_live_e2e/test_live_ab_test_report.py -q -rs
```

Current shell result:

- `1 skipped in 6.82s`
- gate reason: missing live credentials

First credentialed live A/B result:

- `tests_real_live_e2e/test_live_ab_test_report.py`
- `1 passed in 202.92s (0:03:22)`
- winner: `aionis`
- baseline ending: `escalate`
- Aionis ending: `advance`
- Aionis live arm: `live-app-replan-generate-qa-advance`

Second credentialed live A/B result:

- `tests_real_live_e2e/test_live_ab_test_second_cycle_report.py`
- `1 passed in 377.44s (0:06:17)`
- winner: `aionis`
- baseline ending: `escalate`
- Aionis ending: `advance`
- Aionis live arm: `live-app-second-replan-generate-qa-advance`

Third credentialed live A/B result:

- `tests_real_live_e2e/test_live_ab_test_ui_refinement_report.py`
- `1 passed in 222.08s (0:03:42)`
- winner: `aionis`
- baseline ending: `escalate`
- Aionis ending: `advance`
- Aionis live arm: `live-app-replan-generate-qa-advance`
- benchmark family: `stateful-ui-workflow-refinement`

## What This Benchmark Already Proves

- Aionis can be compared against a thin baseline with a stable contract
- the comparison can be rendered from current task state without replaying raw logs
- convergence signals and execution-gate summaries survive into the benchmark layer
- the benchmark surface is already usable in deterministic and credentialed-live form
- the benchmark already spans first-cycle, second-cycle, and stateful-UI live convergence paths

## What Is Still Missing

- a proof-facing report table that aggregates multiple live runs
- a less UI-heavy live scenario family so the benchmark is not dominated by graph/persistence app flows

## Next Step

Add a third live A/B scenario family and record:

- winner
- ending delta
- timing delta
- convergence signal delta
