# Aionis Workbench Runtime Decomposition Status

Date: `2026-04-03`

## Outcome

The runtime decomposition plan is functionally complete.

Workbench no longer depends on one oversized control file for product ops, session policy, recovery, orchestration, shell surfaces, and runtime bridge handling. The external `aionis` contract stayed stable while the internal boundary was split into focused services.

## What moved

- [ops_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py)
  - `doctor`
  - `setup`
  - `host_contract`
  - `background_status`
  - `recent_tasks`
  - `compare_family`
  - `dashboard`
  - `consolidate`
  - auto-consolidation gating
- [session_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py)
  - session initialization
  - bootstrap snapshot seeding
  - target file normalization
  - validation command normalization
- [recovery_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/recovery_service.py)
  - validation feedback handling
  - correction packet assembly
  - rollback hint assembly
  - rollback recovery attempts
  - timeout strategy
- [orchestrator.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/orchestrator.py)
  - `run`
  - `resume`
  - `ingest`
  - runtime host kickoff/handoff/replay coordination
  - live execution flow
- [surface_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py)
  - bootstrap surfaces
  - canonical surface/views
  - session evaluation
  - `validate_session`
  - `workflow_next`
  - `workflow_fix`
  - `shell_status`
  - `backfill`
  - auto-learning writeback
- [runtime_contracts.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime_contracts.py)
  - local payload parsing and validation for runtime bridge responses

## Final shape

- [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py) is now a thin facade plus packet/instrumentation builders that still belong to the runtime boundary.
- Final line count for [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py): `879`
- `AionisWorkbench` primarily wires dependencies and delegates public product methods to services.
- Workbench-to-Runtime responses are no longer consumed as unchecked `response.json()` payloads.

## Test and verification changes

New tests added during the decomposition:

- [test_test_bootstrap.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_test_bootstrap.py)
- [test_recovery_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_recovery_service.py)
- [test_runtime_bridge_contracts.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_runtime_bridge_contracts.py)

Developer setup/test bootstrap changes:

- [pyproject.toml](/Volumes/ziel/Aioniscli/Aionis/workbench/pyproject.toml) now exposes a `dev` extra with `pytest`
- [conftest.py](/Volumes/ziel/Aioniscli/Aionis/workbench/tests/conftest.py) injects `src/` for test imports

Latest high-signal regression run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_bootstrap.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_recovery_service.py tests/test_runtime_bridge_contracts.py -q
```

Result:

- `166 passed`

## Remaining debt

- [surface_service.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py) is now the next large module and can later be split into `evaluation/status/backfill` slices if needed.
- Execution packet and instrumentation assembly still live in [runtime.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py); that is acceptable for now, but it remains a dense core surface.
- More direct service-level tests would still help, especially around `SurfaceService` flows.
- Some older historical design docs still reference `runtime.py` as the operational center; this status doc and the updated README/overview are the authoritative current boundary.

## Notes

- The workspace used for implementation was not a git repository, so the plan's commit steps could not be executed here.
