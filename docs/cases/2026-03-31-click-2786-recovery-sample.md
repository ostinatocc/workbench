# Click #2786 Recovery Sample

**Purpose:** Freeze `click-2786-workbench-2` as a deterministic recovery stress case for Aionis Workbench instead of continuing to treat it as a normal feature-fix task.

## Why This Sample Exists

`#2786` is a `flag_value + callback + shared parameter name` state/timing bug in Click. It exposed a class of failures where a narrow correction can easily broaden into regressions inside the same file. That made it a good pressure sample for:

- `timeout_artifact`
- `correction_packet_artifact`
- `rollback_hint_artifact`
- baseline-failing-test-first validation
- deterministic no-model rollback recovery
- lightweight `backfill` refresh

## Current Canonical Task

- Session:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth/.aionis-workbench/sessions/click-2786-workbench-2.json`
- Correction artifact:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth/.aionis-workbench/artifacts/click-2786-workbench-2/correction.json`
- Rollback artifact:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth/.aionis-workbench/artifacts/click-2786-workbench-2/rollback.json`
- Timeout artifact:
  - `/Volumes/ziel/Aioniscli/Aionis/samples/click-project-scope-fourth/.aionis-workbench/artifacts/click-2786-workbench-2/timeout.json`

## Recovery Contract

- Baseline failing test:
  - `test_flag_value_callback_with_shared_name_uses_latest_callback_result`
- Focused working set:
  - `src/click/core.py`
  - `tests/test_options.py`
- Preferred rollback validation command:
  - `PYTHONPATH=src python3 -m pytest tests/test_options.py -q -k 'test_flag_value_callback_with_shared_name_uses_latest_callback_result'`

## Product Reading

This sample is no longer the main Click fix target. Its job is to prove Workbench recovery behavior stays narrow, deterministic, and syntax-safe under pressure. Future changes should use it to verify:

- recovery artifacts stay consistent
- rollback hints stay best-candidate-first
- correction packets keep the failing set narrow
- `backfill` can refresh artifacts without opening a heavy run
