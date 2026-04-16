# Aionis Unified Host Contract

## Goal

Make the product boundary explicit:

- `aionis CLI` is the user-facing product shell.
- `Workbench engine` is the learning and control layer.
- `deepagents` is the execution host.

The user should experience one product entrypoint, not three separate systems.

## Contract

### 1. Product shell

The shell owns:

- task navigation
- default workflow
- project and family inspection
- status and background views

Current default workflow:

- `/plan`
- `/work`
- `/review`
- `/next`
- `/fix`

### 2. Learning engine

The Workbench engine owns:

- cold-start bootstrap
- automatic learning
- passive observation
- consolidation
- family prior strengthening
- canonical surfaces

It should remain the place where continuity, priors, and workflow recommendations are computed.

### 3. Execution host

The execution host owns:

- model-backed live task execution
- local shell backend access
- runtime bridge integration

Today this is the `deepagents + LocalShellBackend + AionisWorkbenchBridge` stack.

## First implementation slice

The first slice does not change behavior. It only makes the contract visible and queryable.

It adds:

- a dedicated host-contract module
- `aionis hosts`
- shell `/hosts`

This is enough to make the architecture explicit without destabilizing the live path.

## Current code boundary

The execution layer is now thinly adapterized:

- product shell remains in the CLI and shell modules
- learning/control remains in `runtime.py` and the Workbench surfaces
- execution-specific model, backend, agent, and invoke wiring now lives in:
  - [execution_host.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/execution_host.py)
- runtime bridge wiring now lives in:
  - [runtime_bridge_host.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime_bridge_host.py)

This keeps `deepagents` and runtime-bridge details out of most of the Workbench runtime while preserving the same behavior.

## Next slices

1. Route more shell status and debug surfaces through this contract.
2. Move execution-host wiring behind a thinner adapter.
3. Let the shell reason in terms of product capabilities instead of runtime-specific classes.
