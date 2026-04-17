# Workbench Execution Host Migration Plan

**Date:** 2026-04-16  
**Status:** completed host cutover, cleanup in progress  
**Owner:** Workbench

## Summary

`Workbench` has now moved from `deepagents` to [`openai-agents-python`](https://github.com/openai/openai-agents-python), and the remaining work is cleanup/documentation rather than kernel rewrites.

The right boundary is:

- `AionisCore` stays the continuity and memory kernel
- `Workbench` owns the execution host and controller shell
- the execution host becomes a replaceable adapter behind one stable contract

That adapter boundary now exists, the default host has switched to `openai-agents-python`, and the legacy `deepagents` execution path has now been removed from the runtime selection surface.

## Why this migration happened

`deepagents` had become the main remaining substrate lock-in in the product shell across:

- live task execution
- local shell-backed tool use
- direct/delivery agent loops
- execution-host naming and health metadata

`openai-agents-python` is now a credible replacement candidate because the official surface includes:

- agents and handoffs
- sessions
- tracing
- guardrails
- sandbox agents
- shell and patch-oriented tooling

That makes it realistic to replace the execution host without changing `AionisCore`.

## Decision

`Workbench` should migrate to a host-adapter architecture with two phases of compatibility:

1. establish a generic `ExecutionHost` contract
2. land `openai-agents-python` as a second host implementation
3. switch the default host to `openai-agents-python` once deterministic and live confidence are in place
4. remove the legacy `deepagents` execution path once delivery/runtime parity is preserved

That cutover is now complete:

- `openai-agents-python` is the default and only runtime-selected host
- `deepagents` has been removed from the dependency surface
- deterministic and live evidence exist for the migrated host

## Non-goals

This migration should **not** have:

- move execution-host logic into `AionisCore`
- rewrite continuity, replay, handoff, or review-pack flows
- change `Workbench` controller semantics
- change shell/status/controller payload contracts as part of phase 1
- removed `deepagents` before parity exists

## Current dependency surface

Today the deepest coupling is concentrated in:

- `src/aionis_workbench/execution_host.py`
- `src/aionis_workbench/runtime.py`
- `src/aionis_workbench/orchestrator.py`
- `src/aionis_workbench/delivery_executor.py`
- `src/aionis_workbench/host_contract.py`

The execution host currently provides three groups of behavior:

1. host description
   - `describe()`
   - `supports_live_tasks()`
   - runtime/backend/provider metadata
2. agent execution
   - `build_agent()`
   - `invoke()`
   - `build_delivery_agent()`
   - `invoke_delivery_task()`
3. live app-harness planning/evaluation/generation
   - `plan_app_live()`
   - `evaluate_sprint_live()`
   - `negotiate_sprint_live()`
   - `revise_sprint_live()`
   - `replan_sprint_live()`
   - `generate_app_live()`

That is the contract we need to preserve during migration.

## Target architecture

```mermaid
flowchart LR
    WB["Workbench Runtime"] --> FAC["Execution Host Factory"]
    FAC --> O["OpenAI Agents Host Adapter"]
    O --> C
    WB --> RK["AionisCore Runtime Kernel"]
```

Key rule:

- `Workbench Runtime` depends on the contract
- concrete host adapters depend on their own substrate SDKs
- `AionisCore` remains unaffected

## Recommended execution-host contract

Phase 1 contract shape:

- host description
- live capability probe
- task agent build/invoke
- delivery build/invoke
- live app harness planning/evaluation/generation methods
- timeout and token budget introspection

This is intentionally broader than a minimal `run(task)` interface because `Workbench` already exposes live app harness operations that would otherwise leak substrate details back up into runtime code.

## Migration phases

### Phase 1: decouple runtime from the concrete deepagents type

Deliverables:

- add a generic `ExecutionHost` protocol
- add host metadata defaults in one place
- instantiate hosts through a factory
- make `runtime.py`, `orchestrator.py`, and `delivery_executor.py` depend on the protocol, not `DeepagentsExecutionHost`
- add `WORKBENCH_EXECUTION_HOST` config with a replaceable host default

Exit criteria:

- no product behavior changes
- deterministic tests stay green
- runtime/orchestrator/delivery no longer depend on a concrete deepagents type

### Phase 2: add `OpenAIAgentsExecutionHost`

Deliverables:

- new adapter module backed by `openai-agents-python`
- parity for:
  - `describe`
  - `supports_live_tasks`
  - `build_agent`/`invoke`
  - `build_delivery_agent`/`invoke_delivery_task`
- explicit capability gaps documented for app harness methods that are still pending

Exit criteria:

- `run`/`resume`/delivery paths work behind the new host
- deterministic contract suite passes on both substrates where supported

### Phase 3: close app-harness parity

Deliverables:

- parity for:
  - `plan_app_live`
  - `evaluate_sprint_live`
  - `negotiate_sprint_live`
  - `revise_sprint_live`
  - `replan_sprint_live`
  - `generate_app_live`
- host metadata clearly distinguishes:
  - `execution_runtime`
  - `backend`
  - `sandbox_mode`

Exit criteria:

- app/doc flows no longer assume `deepagents`
- live e2e has passing coverage on the new host

### Phase 4: make `openai_agents` the only host

Deliverables:

- remove `deepagents` from the dependency and runtime selection surface
- port delivery retry/timeout behavior to the `openai_agents` host
- remove the legacy execution-host factory branch
- keep the shared delivery timeout and trace helpers substrate-agnostic

Exit criteria:

- install path works without `deepagents`
- deterministic CI and live gate pass on the only supported host

## Risks

### Risk: local shell semantics drift

`deepagents + LocalShellBackend` currently define a lot of implicit behavior around filesystem scope, shell invocation, and patch application.

Mitigation:

- keep the delivery contract fixed
- port delivery tests first
- compare workspace traces and changed-file evidence before cutover

### Risk: app-harness parity takes longer than expected

The app-harness live methods are more specialized than the main `run`/`resume` path.

Mitigation:

- migrate core execution first
- keep app-harness on `deepagents` until parity exists
- allow host-level feature flags during the overlap window

### Risk: controller surfaces accidentally absorb substrate details

Mitigation:

- preserve `controller_action_bar`, session state, and host contract schemas
- expose substrate only via `execution_host` metadata

## Testing plan

Phase 1 must keep these green:

- `tests/test_delivery_executor.py`
- `tests/test_bootstrap.py`
- `tests/test_product_workflows.py`
- `scripts/run-controller-contract-suite.sh`
- `scripts/run-real-e2e.sh`

Phase 2 and Phase 3 should add:

- substrate-agnostic execution host contract tests
- one shared fixture suite run against both adapters where feature parity exists

## Immediate implementation order

1. add execution-host contract module
2. add execution-host factory
3. thread the contract through runtime/orchestrator/delivery paths
4. add config selector with a replaceable default
5. keep behavior and docs honest about which host is currently primary

## Current status

Started:

- phase 1 contract/factory extraction
- phase 2 host skeleton, selection, and auth-probe wiring
- experimental single-agent local tool loop for `build_agent + invoke`
- experimental delivery loop for `build_delivery_agent + invoke_delivery_task`
- experimental JSON app-harness live methods for planner/evaluator/negotiator/revisor/replanner/generator
- OpenRouter-compatible model resolution now uses an explicit `OpenAIChatCompletionsModel` path instead of raw prefixed model ids
- auth probes on the `openai_agents` host now use a slightly wider timeout and retry transient `OpenAIAgentsModelInvokeTimeout` failures instead of failing readiness on the first slow response
- live evaluator prompts now treat `requested_status` and explicit `criteria_scores` as high-signal operator input, instead of letting sparse narrative evidence dominate by default
- real auth probe passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_plan.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_qa.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_negotiate.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_retry.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_replan.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_generate.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_escalate.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_replan_generate_qa.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- `tests_real_live_e2e/test_live_app_replan_generate_qa_advance.py` passed with `WORKBENCH_EXECUTION_HOST=openai_agents`
- phase 4 default switch started:
  - `openai-agents-python` moved into the default dependency set
  - `deepagents` removed from the dependency list and runtime selector
  - `WORKBENCH_EXECUTION_HOST` now defaults to `openai_agents`
  - delivery retry/timeout behavior is being ported onto the `openai_agents` host so the legacy execution-host implementation can be deleted
- a dedicated manual workflow now exists at `.github/workflows/workbench-live-openai-agents.yml`
- the narrow experimental live slice is codified in `scripts/run-real-live-openai-agents-e2e.sh`

Not started:

- optional dependency split
- app-harness parity on the new substrate
