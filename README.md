# Aionis Workbench

`Aionis Workbench` is a product shell for experiencing the largest value of Aionis Core:

- multi-agent continuity
- delegation packets
- reusable collaboration patterns
- shared and private memory lanes
- promotion and forgetting
- replay of effective execution patterns

This repo uses:

- `deepagents` as the current default execution substrate
- `Aionis Core` as the continuity and memory kernel

Execution-host migration toward `openai-agents-python` is planned behind a replaceable host adapter boundary. The current default remains `deepagents`.

Experimental `openai-agents-python` wiring has started behind:

- `WORKBENCH_EXECUTION_HOST=openai_agents`
- `pip install -e .[openai_agents]`
- `.github/workflows/workbench-live-openai-agents.yml` for a narrow real-live experimental lane

Current scope is intentionally narrow:

- host selection
- host metadata
- auth probe wiring
- experimental single-agent local tool loop for `build_agent + invoke`
- experimental delivery loop for `build_delivery_agent + invoke_delivery_task`
- experimental JSON app-harness live methods for planner/evaluator/negotiator/revisor/replanner/generator

The default execution substrate still remains `deepagents`.

## Product shape

Workbench treats every task as a **session** with:

- a shared memory lane for durable, reusable task knowledge
- a working lane for the current active context
- a delegation ledger that records what the orchestrator should send to specialist agents
- a collaboration memory layer that distills specialist returns into reusable patterns
- a promotion/forgetting policy that keeps high-signal knowledge while shedding noise

Memory boundaries:

- `tenant`: who owns the knowledge space
- `project scope`: the durable memory boundary for one repo or project
- `session`: the current task instance
- `lane`: shared vs private visibility inside one project scope

Built-in agent roles:

- `investigator`
- `implementer`
- `verifier`

## Learning contracts

Workbench is moving toward four explicit product contracts:

- `trust-shaped strategy affinity`
  - strategy selection is no longer only path-matched
  - it now prefers `exact_task_signature`, `same_task_family`, then `same_error_family` before falling back to broader similarity
- `execution packet`
  - correction, rollback, timeout, and delegation intent are being unified into one stable execution-state surface
- `planner/provenance summaries`
  - strategy and maintenance decisions are being surfaced as stable summaries instead of scattered prompt fragments
- `artifact-first memory`
  - artifacts and their references are first-class memory objects, not just long summaries

Contract docs:

- `docs/contracts/workbench-execution-packet-v1.md`
- `docs/contracts/workbench-planner-provenance-v1.md`

## Internal architecture

Workbench now uses a split control plane internally:

- [runtime.py](src/aionis_workbench/runtime.py)
  - thin facade
  - config and dependency wiring
  - execution packet and instrumentation assembly that still belongs to the core runtime boundary
- [ops_service.py](src/aionis_workbench/ops_service.py)
  - doctor/setup
  - host contract
  - dashboard/background/consolidation surfaces
- [session_service.py](src/aionis_workbench/session_service.py)
  - session initialization
  - bootstrap seeding
  - path and validation normalization
- [recovery_service.py](src/aionis_workbench/recovery_service.py)
  - validation failure handling
  - correction packets
  - rollback and timeout recovery decisions
- [orchestrator.py](src/aionis_workbench/orchestrator.py)
  - `run`
  - `resume`
  - `ingest`
  - live execution flow and runtime host coordination
- [surface_service.py](src/aionis_workbench/surface_service.py)
  - canonical surface/views
  - bootstrap/status/evaluation shell flows
  - session persistence and auto-learning writeback
- [runtime_contracts.py](src/aionis_workbench/runtime_contracts.py)
  - local validation/parsing for Workbench-to-Runtime responses

This keeps the external `aionis` product contract stable while letting ops, orchestration, recovery, shell surfaces, and runtime bridge behavior evolve independently.

## Setup

Shortest local developer install from the workspace root:

```bash
bash ./scripts/install-local-aionis.sh
```

The local install script now treats this repository as the root. It always installs the Workbench CLI into `.venv`, and will also install runtime dependencies if it can find a local Aionis Core checkout through one of:

- `AIONIS_RUNTIME_ROOT`
- `AIONIS_CORE_DIR`
- `../AionisCore`
- `../AionisRuntime`
- `../runtime-mainline`

Launcher guide:

- [2026-04-03-aionis-launcher-guide.md](docs/product/2026-04-03-aionis-launcher-guide.md)
- [2026-04-03-aionis-provider-setup-guide.md](docs/product/2026-04-03-aionis-provider-setup-guide.md)
- [2026-04-15-aionis-external-positioning.md](docs/product/2026-04-15-aionis-external-positioning.md)

## Recommended External Beta Path

The external beta workflow should lead with the stable command path:

- `aionis ready --repo-root /absolute/path/to/repo`
- `aionis run --repo-root /absolute/path/to/repo --task-id task-1 --task "..."`
- `aionis resume --repo-root /absolute/path/to/repo --task-id task-1`
- `aionis session --repo-root /absolute/path/to/repo --task-id task-1`

Current stable commands:

- `init`
- `doctor`
- `ready`
- `status`
- `run`
- `resume`
- `session`

Current beta commands:

- `setup`
- `shell`
- `live-profile`
- `compare-family`
- `recent-tasks`
- `dashboard`
- `consolidate`

Advanced operator and research surfaces still exist, but should not define the default external product story.

Current platform status:

- [2026-04-03-aionis-workbench-platform-status.md](docs/plans/2026-04-03-aionis-workbench-platform-status.md)
- [2026-04-03-aionis-workbench-real-e2e-status.md](docs/plans/2026-04-03-aionis-workbench-real-e2e-status.md)
- [2026-04-03-aionis-workbench-live-reliability-status.md](docs/plans/2026-04-03-aionis-workbench-live-reliability-status.md)
- [2026-04-03-aionis-workbench-live-reliability-provider-hygiene-plan.md](docs/plans/2026-04-03-aionis-workbench-live-reliability-provider-hygiene-plan.md)
- [2026-04-04-aionis-long-running-app-harness-status.md](docs/plans/2026-04-04-aionis-long-running-app-harness-status.md)
- [2026-04-15-aionis-external-release-productization-plan.md](docs/plans/2026-04-15-aionis-external-release-productization-plan.md)

Current app harness operator surfaces:

- `aionis app show --task-id ...`
- `aionis app plan --task-id ... --prompt ... [--use-live-planner]`
- `aionis app sprint --task-id ... --sprint-id ... --goal ...`
- `aionis app qa --task-id ... --sprint-id ... [--status auto] [--use-live-evaluator]`
- `aionis app negotiate --task-id ... [--sprint-id ...] [--objection ...] [--use-live-planner]`
- `aionis app generate --task-id ... [--sprint-id ...] [--summary ...] [--target ...] [--use-live-generator]`
- `aionis app retry --task-id ... [--sprint-id ...] [--revision-note ...] [--use-live-planner]`
- `aionis app advance --task-id ... [--sprint-id ...]`
- `aionis app replan --task-id ... [--sprint-id ...] [--note ...]`
- `aionis app escalate --task-id ... [--sprint-id ...] [--note ...]`

Current A/B benchmark surface:

- `aionis ab-test compare --task-id ... --scenario-id ... --baseline-ended-in ...`

Current narrow live app harness coverage includes:

- `tests_real_live_e2e/test_live_app_plan.py`
- `tests_real_live_e2e/test_live_app_generate.py`
- `tests_real_live_e2e/test_live_app_qa.py`
- `tests_real_live_e2e/test_live_app_negotiate.py`
- `tests_real_live_e2e/test_live_app_retry.py`
- `tests_real_live_e2e/test_live_app_retry_compare.py`
- `tests_real_live_e2e/test_live_app_advance.py`
- `tests_real_live_e2e/test_live_app_escalate.py`
- `tests_real_live_e2e/test_live_app_replan.py`
- `tests_real_live_e2e/test_live_app_replan_generate_qa.py`
- `tests_real_live_e2e/test_live_app_replan_generate_qa_advance.py`
- `tests_real_live_e2e/test_live_app_second_replan.py`
- `tests_real_live_e2e/test_live_app_second_replan_generate_qa_advance.py`
- `tests_real_live_e2e/test_live_app_second_replan_generate_qa_escalate.py`
- `tests_real_live_e2e/test_live_ab_test_report.py`
- `tests_real_live_e2e/test_live_ab_test_second_cycle_report.py`
- `tests_real_live_e2e/test_live_ab_test_ui_refinement_report.py`

Current experimental `openai_agents` live coverage includes:

- `tests_real_live_e2e/test_live_app_plan.py`
- `tests_real_live_e2e/test_live_app_qa.py`
- `tests_real_live_e2e/test_live_app_negotiate.py`
- `tests_real_live_e2e/test_live_app_retry.py`
- `tests_real_live_e2e/test_live_app_replan.py`
- `tests_real_live_e2e/test_live_app_generate.py`
- `tests_real_live_e2e/test_live_app_escalate.py`
- `tests_real_live_e2e/test_live_app_replan_generate_qa.py`
- `tests_real_live_e2e/test_live_app_replan_generate_qa_advance.py`

Manual experimental lane:

- `./scripts/run-real-live-openai-agents-e2e.sh`

Current app harness contract flow now includes:

- planner-backed `app plan`
- evaluator-backed `app qa`
- bounded `app generate`
- bounded revision `app retry`
- `app qa` consuming the latest execution attempt when deriving the next evaluator result
- compact `execution_focus` propagation across live planner, live generator, and live evaluator paths
- explicit app-harness policy projection via `policy_stage`, `execution_gate`, and `execution_outcome_ready`

Manual editable-install path inside `workbench`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Environment

For a safer live-provider setup path, use:

- [2026-04-03-aionis-provider-setup-guide.md](docs/product/2026-04-03-aionis-provider-setup-guide.md)

The examples below are reference values. Prefer loading them from a local `.env`-style file instead of typing secrets directly into long-lived shell history.

```bash
export OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_MODEL="openai/gpt-5.4"
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
export WORKBENCH_MAX_COMPLETION_TOKENS="8192"
export WORKBENCH_MODEL_TIMEOUT_SECONDS="45"
export WORKBENCH_MODEL_MAX_RETRIES="1"

export AIONIS_TENANT_ID="default"
export AIONIS_ACTOR="aionis-workbench"
```

If you prefer the OpenAI-compatible path instead of OpenRouter:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export WORKBENCH_MODEL="gpt-5"
export WORKBENCH_MODEL_TIMEOUT_SECONDS="45"
export WORKBENCH_MODEL_MAX_RETRIES="1"
```

For the current manually verified Z.AI live profile:

```bash
export AIONIS_PROVIDER_PROFILE="zai_glm51_coding"
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.z.ai/api/coding/paas/v4"
export WORKBENCH_MODEL="glm-5.1"
```

Current manually verified live timing baseline for that profile:

- `live-run-pause`: `57.66s`
- `live-resume-complete`: `106.87s`
- split live script total: `158.31s`
- `live-app-plan`: `71.85s`
- `live-app-generate`: pending first credentialed reference pass
- `live-app-qa`: `65.48s`
- `live-app-retry-compare`: `140.88s`
- `live-app-advance + live-app-escalate`: `287.05s`
- `live-app-replan-generate-qa-advance`: `245.11s`
- `live-app-second-replan`: `336.05s`
- `live-app-second-replan-generate-qa-advance`: `381.92s`
- `live-app-second-replan-generate-qa-escalate`: `390.00s`

The second-cycle live endings now also expose compact execution-state details in
their scenario results:

- `second_replanned_execution_focus`
- `second_replanned_execution_gate`
- `second_replanned_execution_outcome_ready`

The first-cycle live endings now expose the same kind of compact pre-ending
execution-state details:

- `pre_advance_execution_focus`
- `pre_advance_execution_gate`
- `pre_advance_execution_outcome_ready`
- `pre_escalate_execution_focus`
- `pre_escalate_execution_gate`
- `pre_escalate_execution_outcome_ready`

Those compact execution-state fields are now also projected into the repo-local
`live-profile` snapshot and surface:

- `latest_execution_focus`
- `latest_execution_gate`
- `latest_execution_gate_transition`
- `latest_execution_outcome_ready`
- `latest_last_policy_action`
- `latest_convergence_signal`
- `recent_convergence_signals`

Example:

- `live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed`

`aionis live-profile` now also keeps a short repo-local history of those compact
signals, so first-cycle and second-cycle endings can be compared directly from the
surface without replaying individual scenario payloads.

The A/B benchmark surface uses those same compact convergence signals and execution
gates to compare:

- a thin baseline loop
- the current Aionis app-harness task

The current narrow live A/B scenarios now wired into the live suite are:

- `test_live_ab_test_report.py`
- `test_live_ab_test_second_cycle_report.py`
- `test_live_ab_test_ui_refinement_report.py`

They currently reuse:

- `live-app-replan-generate-qa-advance`
- `live-app-second-replan-generate-qa-advance`

as Aionis arms and compare them against a normalized thin-loop baseline ending in `escalate`.

Credentialed live A/B passes now recorded:

- `test_live_ab_test_report.py`: `202.92s`
- winner: `aionis`
- baseline ending: `escalate`
- Aionis ending: `advance`
- Aionis live arm: `live-app-replan-generate-qa-advance`
- `test_live_ab_test_second_cycle_report.py`: `377.44s`
- winner: `aionis`
- baseline ending: `escalate`
- Aionis ending: `advance`
- Aionis live arm: `live-app-second-replan-generate-qa-advance`
- `test_live_ab_test_ui_refinement_report.py`: `222.08s`
- winner: `aionis`
- baseline ending: `escalate`
- Aionis ending: `advance`
- Aionis live arm: `live-app-replan-generate-qa-advance`
- benchmark family: `stateful-ui-workflow-refinement`

The app harness summary now also keeps a compact execution-only gate trail:

- `last_execution_gate_from`
- `last_execution_gate_to`
- `last_execution_gate_transition`
- `last_policy_action`

That trail only tracks concrete execution attempts. Evaluator-only paths that
never produced a bounded execution attempt will remain at `no_execution`.

`run` and `resume` need model credentials. Offline product operations such as `ingest`, `backfill`, and `session` do not.

`AIONIS_BASE_URL` is optional. If you leave it unset, Workbench probes `http://127.0.0.1:3101` first, then `http://127.0.0.1:3001`, and binds to the first healthy local Aionis runtime.

By default, Workbench derives the Aionis project scope from the bound repo, for example:

```bash
project:pallets/click
```

You can override the detected project identity if needed:

```bash
export WORKBENCH_PROJECT_IDENTITY="my-org/my-repo"
```

Only override `AIONIS_SCOPE` if you intentionally want a custom memory namespace.

Optional:

```bash
export WORKBENCH_SYSTEM_PROMPT="You are a rigorous multi-agent software engineering orchestrator."
```

Launcher state for the upcoming unified `aionis` entrypoint is standardized under:

```text
~/.aionis/
  config.json
  runtime/
    pid
    stdout.log
    stderr.log
  workbench/
    last_repo_root
```

If you are running through OpenRouter, keep a bounded completion budget so long-lived multi-agent runs do not request an oversized default completion window:

```bash
export WORKBENCH_MAX_COMPLETION_TOKENS="8192"
```

You must bind each run to a real working repo. Pass it explicitly:

```bash
--repo-root /absolute/path/to/repo
```

or set:

```bash
export WORKBENCH_REPO_ROOT="/absolute/path/to/repo"
```

## Run

Open the thin interactive terminal shell:

```bash
aionis --repo-root /absolute/path/to/repo
```

Shell workflow guide:

- [docs/product/2026-04-01-aionis-shell-guide.md](docs/product/2026-04-01-aionis-shell-guide.md)

Inside the shell, the first-pass commands are:

- `/init`
- `/setup`
- `/doctor`
- `/status [TASK_ID]`
- `/latest`

App harness phase-1 surfaces:

```bash
aionis app show --repo-root /absolute/path/to/repo --task-id TASK_ID
aionis app plan --repo-root /absolute/path/to/repo --task-id TASK_ID --prompt "Build a visual dependency explorer for async task orchestration."
aionis app plan --repo-root /absolute/path/to/repo --task-id TASK_ID --prompt "Build a visual dependency explorer for async task orchestration." --use-live-planner
aionis app plan --repo-root /absolute/path/to/repo --task-id TASK_ID --prompt "Build a visual editor." --title "Editor" --type full_stack_app --stack React --feature canvas --criterion functionality:0.8
aionis app sprint --repo-root /absolute/path/to/repo --task-id TASK_ID --sprint-id sprint-1 --goal "Ship the editor shell." --scope shell --acceptance-check "pytest tests/test_editor.py -q" --approved
aionis app negotiate --repo-root /absolute/path/to/repo --task-id TASK_ID --sprint-id sprint-1 --objection "timeline entries reset on refresh"
aionis app negotiate --repo-root /absolute/path/to/repo --task-id TASK_ID --sprint-id sprint-1 --objection "timeline entries reset on refresh" --use-live-planner
aionis app qa --repo-root /absolute/path/to/repo --task-id TASK_ID --sprint-id sprint-1 --status auto --score functionality=0.61 --blocker "palette resets on refresh"
aionis app qa --repo-root /absolute/path/to/repo --task-id TASK_ID --sprint-id sprint-1 --use-live-evaluator --status auto --blocker "timeline entries reset on refresh"
```
- `/pick N`
- `/tasks [--limit N]`
- `/show [TASK_ID]`
- `/family [TASK_ID] [--limit N]`
- `/hosts`

## Real E2E

Deterministic real-repo suite:

```bash
cd /path/to/workbench
.venv/bin/python -m pytest tests_real_e2e -q
```

Model-backed live slice:

```bash
cd /path/to/workbench
./scripts/run-real-live-e2e.sh
```

GitHub Actions also exposes a manual [workbench-live-e2e.yml](.github/workflows/workbench-live-e2e.yml) workflow. It lets you choose a provider profile, runs a live credential preflight, then publishes JUnit/log artifacts and a compact live summary for the model-backed slice.

Release-gated deterministic + live check:

```bash
cd /path/to/workbench
./scripts/run-release-gates.sh
```

Read the current active provider profile and latest recorded live timing snapshot:

```bash
cd /path/to/workbench
aionis live-profile --repo-root /absolute/path/to/repo
```

`real-live-e2e` is intentionally gated. It skips when live model credentials are unavailable and only runs actual model-backed checks when `OPENAI_API_KEY` or `OPENROUTER_API_KEY` is configured. The live slice currently includes:

- `live-run-pause`
- `live-resume-complete`
- `live-app-plan`

The release gate currently treats only `zai_glm51_coding` as release-approved. `openai_default` and `openrouter_default` remain experimental until separately verified.

Deterministic real-e2e runner:

```bash
./scripts/run-real-e2e.sh
```

Controller-guidance contract suite:

```bash
./scripts/run-controller-contract-suite.sh
```

GitHub Actions now also runs this suite through [workbench-controller-contracts.yml](.github/workflows/workbench-controller-contracts.yml) as the fast `controller-contracts` job, and then fans into a heavier `deterministic-real-e2e` job. Both jobs now share the same local [setup-workbench composite action](.github/actions/setup-workbench/action.yml), both upload `tmp/ci/*.log` plus JUnit XML artifacts, and both publish a compact Markdown summary generated by [summarize-junit.py](scripts/summarize-junit.py) into the Actions step summary.

Release gate runner:

```bash
./scripts/run-release-gates.sh
```

`run-release-gates.sh` now replays the controller-guidance contract suite before the broader deterministic real-e2e and live slices, so cross-surface controller parity is part of the release gate instead of a manual preflight.

The current credentialed reference runs completed successfully with:

- `2 passed in 158.31s`
- `1 passed in 69.54s` for `tests_real_live_e2e/test_live_app_plan.py` on `zai_glm51_coding`
- `1 passed in 65.48s` for `tests_real_live_e2e/test_live_app_qa.py` on `zai_glm51_coding`
- `live-app-negotiate` is now wired into `run-real-live-e2e.sh` and ready for the same provider profile
- `/validate [TASK_ID]`
- `/work [TASK_ID]`
- `/next [TASK_ID]`
- `/fix [TASK_ID]`
- `/plan [TASK_ID]`
- `/review [TASK_ID]`
- `/use TASK_ID`
- `/clear`
- `/dashboard [--limit N] [--family-limit N]`
- `/consolidate [--limit N] [--family-limit N]`
- `/background`
- `/session [TASK_ID]`
- `/evaluate [TASK_ID]`
- `/compare-family [TASK_ID] [--limit N]`
- `/doc compile PATH [--emit MODE] [--strict]`
- `/doc run PATH --registry PATH [--input-kind KIND]`
- `/doc publish PATH [--input-kind KIND]`
- `/doc recover PATH [--input-kind KIND]`
- `/doc resume PATH [--input-kind KIND] [--query-text TEXT] [--candidate TOOL]`
- `/run TASK_ID ["task description"] [--target-file PATH] [--validation-command CMD] [--preflight-only]`
- `/resume [TASK_ID] ["fallback task"] [--target-file PATH] [--validation-command CMD] [--preflight-only]`
- `/ingest TASK_ID "task description" "summary" [--target-file PATH] [--changed-file PATH] [--validation-command CMD]`
- `/raw [on|off|toggle]`
- `/help`
- `/exit`

Example:

```text
/status
/init
/plan
/work
/latest
/tasks --limit 5
/pick 2
/show
/family
/validate
/dream
/background
/work
/next
/fix
/plan
/review
/use task-123
/compare-family task-123 --limit 3
/doc compile ./workflow.aionis.md --emit plan
/doc run ./workflow.aionis.md --registry ./module-registry.json
/doc publish ./workflow.aionis.md
/doc recover ./publish-result.json --input-kind publish-result
/doc resume ./recover-result.json --input-kind recover-result --candidate read
/clear
/run task-456 "Fix the parser regression" --target-file src/parser.py --validation-command "PYTHONPATH=src python3 -m pytest tests/test_parser.py -q"
/run task-456 --preflight-only
/resume task-456 --preflight-only
/exit
```

The shell is intentionally thin:

- it reuses the existing Workbench engine and canonical surfaces
- it keeps track of the current task in the prompt, so `/status`, `/session`, `/evaluate`, `/compare-family`, and `/resume` can reuse that task context
- `/latest` jumps to the most recent task; `/tasks` gives a short recent-task list; `/pick N` lets you select directly from that list
- `/show` expands the current task into a compact multi-line canonical summary without turning raw JSON on
- `/family` expands the current task family into a compact multi-line reuse summary with peer strength and trend
- `/family` now also exposes the blocked-prior `dream_reason` when AutoDream has enough evidence to explain why the family is still below `seed_ready`
- `/hosts` shows the current unified host contract for the `aionis` shell, the Workbench learning engine, and the underlying execution host
- `/doctor` gives a compact onboarding and environment check for the current repo, including whether the product is currently in `live` or `inspect-only` mode
- `/setup` gives the shortest setup-focused surface for the current repo, including pending checklist items and exact command hints
- `doctor`, `setup`, and the shell startup hint now all carry a short `live_ready_summary`, plus a human-readable `recovery_summary` when live execution is blocked or degraded
- `/setup --pending-only` keeps that surface focused on only the remaining setup blockers
- `aionis doctor --summary` and `aionis setup --summary` give compact script-friendly onboarding surfaces
- `aionis doctor --one-line` and `aionis setup --one-line` give a single-line onboarding summary for shell startup hooks and lightweight scripts
- `aionis doctor --check NAME` and `aionis setup --check NAME` let scripts ask for one named checklist item directly
- `/hosts` now also shows capability state for the execution host and runtime host, including whether live tasks are enabled and any current degraded-mode reason
- `/hosts` now distinguishes host health states directly:
  - `available`
  - `degraded`
  - `offline`
- `/status` now also carries a compact `hosts:` summary in the status line so the current shell, learning, and execution layers are visible from the default prompt surface
- `/family`, `/plan`, `/work`, and `/review` now also show consolidated prior confidence, sample count, recent success count, source-tier hints (`manual_ingest`, `workflow_closure`, `validate`, `passive`), and the current `prior_seed` gate/reason so the shell can explain why a prior is or is not allowed to influence seed behavior
- when a family prior is blocked, `/family` now also shows the concrete recommendation for unblocking that prior
- when the current task is sitting on a blocked family prior, `/plan`, `/next`, and `/fix` now surface the same recommendation so the default workflow can help close that learning gap
- `/plan`, `/work`, and `/review` now also show a one-line host summary so the default workflow stays tied to the unified CLI / Workbench / execution-host contract
- `/validate` reruns the primary validation command for the current task and refreshes the shell status
- `/consolidate` (alias `/dream`) runs a conservative project-scoped consolidation pass and writes `.aionis-workbench/consolidation.json`
- `/dream` now has its own compact detail surface:
  - top promoted priors
  - top remaining candidates
  - leading promotion / verification reasons
  - `--status seed_ready|trial|candidate|deprecated` filtering
- `/doc` exposes `Aionisdoc` as a structured workflow sidecar instead of pushing it through the default DeepAgents live loop
- successful `/doc publish`, `/doc recover`, and `/doc resume` runs now persist structured artifacts and `continuity.doc_workflow` history into the current task session when a task is selected
- `/dashboard` now also surfaces the leading blocked-family reason, not just the blocked gate name
- `/background` shows the current consolidation maintenance state; `/status` now also includes a compact consolidation summary in the status line
- `/init` materializes the repo bootstrap record and stores it under `.aionis-workbench/bootstrap.json`
- `/init` now also returns a compact setup summary:
  - current mode (`live` or `inspect-only`)
  - whether live execution is ready yet
  - the next concrete setup step
- on a repo with no recorded sessions yet, `/status`, `/plan`, `/work`, and `/review` fall back to a bootstrap surface inferred from the repo layout
- `/work` is the default workflow surface: current task summary, family reuse state, next action, and primary validation in one view
- `/next` executes the default next step for the current task; right now it prefers validation whenever a primary validation path exists
- `/fix` is the default execution action for the current task; when that narrow step succeeds, Workbench records it as a workflow-closure learning signal
- `/run` and `/resume` now perform a host preflight first, so an obviously unhealthy execution/runtime host is blocked before the shell tries to enter the live path
- `/run --preflight-only` and `/resume --preflight-only` let scripts and users check live readiness without starting the task; `/run --preflight-only` only needs the `TASK_ID`
- add `--one-line` to those preflight checks when you want a single stdout line for scripts and startup hooks
- `/run` and `/resume` now fail through a structured degraded-mode surface that explains the current host mode and the next recovery step instead of only returning a raw runtime-shaped error
- both surfaces now also carry stable recovery metadata:
  - `recovery_class`
  - `recovery_summary`
  - `recovery_command_hint`
- shell summaries now distinguish:
  - `missing_runtime`: runtime is missing or unreachable
  - `runtime_degraded`: runtime is configured but unhealthy
- `/plan` gives a short action plan for the current task: current status, next step, primary validation, family strength, and the recommended `/review -> /fix` path
- `/review` combines the current task summary, family reuse state, and evaluation status into one compact readiness view
- `/use TASK_ID` pins the current task explicitly; `/clear` returns the shell to project-level context
- it keeps the JSON-producing non-interactive commands intact
- it does not yet try to be a heavy TUI or a full-screen terminal app
- it defaults to short summaries; use `/raw on` when you want the full JSON payloads

Cold-start path on a fresh repo:

```text
/init
/status
/plan
/work
/run task-001 "Create the first narrow task" --target-file src/... --validation-command "..."
```

You can also initialize from outside the shell:

```bash
aionis init --repo-root /absolute/path/to/repo
```

Recommended first-time path:

```bash
.venv/bin/aionis status
.venv/bin/aionis --repo-root /absolute/path/to/repo
```

If your `PATH` already includes `workbench/.venv/bin`, the same path is:

```bash
aionis ready --repo-root /absolute/path/to/repo
aionis --repo-root /absolute/path/to/repo
```

If you want the old explicit path instead:

```bash
aionis init --repo-root /absolute/path/to/repo
aionis setup --repo-root /absolute/path/to/repo
aionis doctor --repo-root /absolute/path/to/repo
```

`aionis ready` now combines the first-pass `init/setup/doctor` guidance into one place:

- current live vs inspect-only state
- pending setup blockers
- the first concrete fix command
- the shell launch command once the repo is ready enough to enter the product surface

If you want the shortest fix-oriented setup surface:

```bash
aionis setup --repo-root /absolute/path/to/repo
```

If you only want the remaining setup blockers:

```bash
aionis setup --repo-root /absolute/path/to/repo --pending-only
```

If you want a compact script-friendly summary:

```bash
aionis doctor --repo-root /absolute/path/to/repo --summary
aionis setup --repo-root /absolute/path/to/repo --summary
aionis run --repo-root /absolute/path/to/repo --task-id task-1 --preflight-only --one-line
aionis resume --repo-root /absolute/path/to/repo --task-id task-1 --preflight-only --one-line
```

If you want one named check directly:

```bash
aionis doctor --repo-root /absolute/path/to/repo --check runtime_host
aionis setup --repo-root /absolute/path/to/repo --check credentials_configured
```

For `--check NAME`, the CLI now uses stable exit codes:

- `0`: the named check is satisfied
- `1`: the named check exists but is not satisfied yet
- `2`: the named check was not found

Structured workflow guide:

- [2026-04-03-aionisdoc-workbench-guide.md](docs/product/2026-04-03-aionisdoc-workbench-guide.md)

Historical plan and case documents under `docs/plans` and `docs/cases` still preserve some original workspace-local paths from the monorepo phase. They are archival references, not the default onboarding path for this standalone repository.

Use `Aionisdoc` through Workbench when you want `.aionis.md` workflows to stay tied to the current task session:

```bash
aionis doc --repo-root /absolute/path/to/repo compile --input ./workflow.aionis.md
aionis doc --repo-root /absolute/path/to/repo run --input ./workflow.aionis.md --registry ./module-registry.json
aionis doc --repo-root /absolute/path/to/repo publish --input ./workflow.aionis.md --task-id task-123
aionis doc --repo-root /absolute/path/to/repo recover --input ./publish-result.json --task-id task-123 --input-kind publish-result
aionis doc --repo-root /absolute/path/to/repo resume --input ./recover-result.json --task-id task-123 --input-kind recover-result --candidate read
```

By default, the bridge now prefers the official package roots in this order:

```text
$AIONISDOC_PACKAGE_ROOT
$AIONISDOC_WORKSPACE_ROOT/packages/aionis-doc
../AionisCore/packages/aionis-doc
../AionisRuntime/packages/aionis-doc
~/Desktop/Aionis/packages/aionis-doc
```

Override it explicitly when needed:

```bash
export AIONISDOC_PACKAGE_ROOT="/absolute/path/to/AionisCore/packages/aionis-doc"
```

Legacy workspace-root override still works:

```bash
export AIONISDOC_WORKSPACE_ROOT="/absolute/path/to/Aionis"
```

```bash
aionis-workbench run \
  --repo-root /absolute/path/to/repo \
  --task-id task-123 \
  --task "Fix the parser regression and keep the CLI behavior unchanged." \
  --target-file src/parser.py \
  --target-file tests/test_parser.py \
  --validation-command "PYTHONPATH=src python3 -m pytest tests/test_parser.py -q"
```

Resume a prior session:

```bash
aionis-workbench resume \
  --repo-root /absolute/path/to/repo \
  --task-id task-123 \
  --target-file src/parser.py \
  --target-file tests/test_parser.py \
  --validation-command "PYTHONPATH=src python3 -m pytest tests/test_parser.py -q"
```

`resume` first restores the persisted session for the same project and task. If Aionis also has a stored handoff for that task, Workbench merges it in; if not, resume still continues from the session’s shared memory, promoted insights, delegation packets, and working set.

Record already-completed, already-validated work into project continuity without rerunning the model:

```bash
aionis-workbench ingest \
  --repo-root /absolute/path/to/repo \
  --task-id task-123-ingest \
  --task "Fix the parser regression and keep the CLI behavior unchanged." \
  --summary "Recorded the validated parser fix and the regression coverage." \
  --target-file src/parser.py \
  --target-file tests/test_parser.py \
  --changed-file src/parser.py \
  --changed-file tests/test_parser.py \
  --validation-command "PYTHONPATH=src python3 -m pytest tests/test_parser.py -q" \
  --validation-summary "Validated with the focused parser pytest slice."
```

Use `ingest` when the task was completed outside Workbench but should still become part of the project's durable memory, delegation returns, and replay history.

Successful normal-product paths now also auto-absorb a narrow learning signal:

- successful `run`
- successful `resume`
- successful `/validate`
- successful `/fix`

That automatic absorption records the last successful validation path, working set, task family, strategy profile, role sequence, and artifact references into the canonical continuity / maintenance surfaces. `ingest` remains the right operator path for externally completed work, but it is no longer the only clean learning path.

Those successful paths now also refresh a lightweight project-level sample store:

- repo-local: `.aionis-workbench/auto_learning.json`
- project-scoped: `~/.aionis-workbench/projects/<project-scope>/auto_learning.json`

Cold-start bootstrap and `aionis init` reuse those recent auto-learned samples so a fresh clone or a session-less repo can still inherit the latest narrow working set and validation path.

Successful `/validate` now also records a light passive-observation signal when the current repo diff shows changed files. That means a user can:

- `/use task-123`
- edit files manually
- run `/validate`

and Workbench will capture the observed changed files and the successful validation path without requiring a separate `ingest`.

The current slice reads both `git status --porcelain` and `git diff --name-only`, so staged, unstaged, and untracked changed files can all feed that passive-observation path.

When that passive path succeeds, Workbench now also promotes:

- the latest successful validation command to the current default validation path
- the observed changed files to the front of the current task working set

So `/plan`, `/work`, `/next`, and `/fix` start to follow the most recent successful manual-edit loop instead of staying pinned to stale target files or stale validation commands.

Workbench persists sessions in two places:

- repo-local state under `.aionis-workbench/sessions`
- project-scoped durable state under `~/.aionis-workbench/projects/<project-scope>/sessions`

That means continuity is shared by project, not only by one checkout path. A second clone or worktree of the same repo can reuse recent sessions and promoted insights from the same `project scope`.

Inspect the persisted session:

```bash
aionis-workbench session --repo-root /absolute/path/to/repo --task-id task-123
```

Evaluate whether a session is already running on the canonical packet/provenance/continuity surfaces cleanly:

```bash
aionis-workbench evaluate --repo-root /absolute/path/to/repo --task-id task-123
```

Compare the current session against recent sessions from the same task family:

```bash
aionis-workbench compare-family --repo-root /absolute/path/to/repo --task-id task-123
```

Show a project-level live instrumentation dashboard grouped by task family:

```bash
aionis-workbench dashboard --repo-root /absolute/path/to/repo
```

The dashboard uses a recent time-ordered slice and reports, per family:

- reuse quality (`strong_family`, `stable_family`, `mixed_family`)
- a short trend (`improving`, `stable`, `flat`, `regressing`, `emerging`)
- average artifact hit rate
- average pattern hit count
- sample tasks behind the current family summary

Both `dashboard` and `compare-family` now also carry the latest consolidation maintenance status, so you can tell whether those family-level summaries are being read alongside a recent `completed`, `running`, `disabled`, or `skipped:<reason>` maintenance state.

Run a conservative project-scoped consolidation pass manually:

```bash
aionis-workbench consolidate --repo-root /absolute/path/to/repo
```

This writes:

- repo-local: `.aionis-workbench/consolidation.json`
- project-scoped: `~/.aionis-workbench/projects/<project-scope>/consolidation.json`

and summarizes:

- recent sessions reviewed
- families reviewed
- duplicate family patterns merged
- weak broader-similarity patterns suppressed
- continuity dedupe opportunities found

Inspect the current AutoDream prior-compiler surface directly:

```bash
aionis-workbench dream --repo-root /absolute/path/to/repo
```

You can also filter the output to one lifecycle slice:

```bash
aionis-workbench dream --repo-root /absolute/path/to/repo --status trial
```

The `dream` CLI surfaces:

- top promoted priors
- top remaining candidates
- leading promotion / verification reasons
- lifecycle-filtered slices for `seed_ready`, `trial`, `candidate`, or `deprecated`

Auto-consolidation is now available behind explicit gates. When enabled, successful task-ending flows:

- `run`
- `resume`
- `ingest`
- `backfill`

attempt a conservative consolidation pass after the session is saved.

Environment flags:

```bash
export AIONIS_AUTO_CONSOLIDATE=true
export AIONIS_AUTO_CONSOLIDATE_MIN_HOURS=24
export AIONIS_AUTO_CONSOLIDATE_MIN_NEW_SESSIONS=5
export AIONIS_AUTO_CONSOLIDATE_SCAN_THROTTLE_MINUTES=10
```

The gate is conservative:

- disabled by default
- requires usable project sessions
- respects a time gate since the last completed consolidation
- respects a new-session gate since the last completed consolidation
- throttles repeated skipped scans
- uses a project-scoped lock to prevent duplicate runs

Upgrade an older persisted session to the latest collaboration-memory schema:

```bash
aionis-workbench backfill --repo-root /absolute/path/to/repo --task-id task-123
```

`run`, `resume`, `ingest`, `session`, and `backfill` now all return:

- `canonical_surface`: the full structured contract
- `canonical_views`: the shorter inspect/debug view
- `evaluation`: a compact readiness check for the current session state

`canonical_views.routing` shows the current agent-to-agent artifact routing surface:

- which roles received routed artifacts
- which evidence was inherited into each role packet
- why each route was selected

`canonical_views.instrumentation` shows the current strategy-quality surface:

- whether the chosen family scope actually hit the current task family
- how many selected patterns came from the same family versus another family
- how many routed artifacts resolved to same-family prior sessions
- the routed artifact hit rate and the concrete prior task ids behind those hits
- a top-level status (`strong_match`, `usable_match`, or `weak_match`) plus a short explanation

Treat those as the default explanation surfaces for the product instead of reading raw session memory directly.

Example:

```bash
aionis-workbench session --repo-root /absolute/path/to/repo --task-id task-123 \
  | jq '.canonical_views.strategy'
```

## What this product surfaces

- Aionis kickoff becomes the starting operating posture for the orchestrator.
- Delegation packets give specialist agents a tighter, structured mission.
- Delegation returns are distilled into reusable collaboration patterns, so Workbench can carry forward working-set, implementation-scope, and validation strategies across the same project.
- Shared memory lanes preserve durable findings across runs.
- Working memory is trimmed by a forgetting policy instead of growing without bound.
- Replay is written back as execution evidence and promoted insights, not only as a completion marker.
- Successful normal task flow now auto-absorbs a narrow learning signal, so validated `run`, `resume`, and `/validate` outcomes strengthen project memory even when the user never calls `ingest`.
- Those successful paths also refresh a lightweight project-level auto-learning store, which cold-start bootstrap can reuse before a new repo has accumulated fresh sessions.
- Target files are normalized to repo-relative paths so Deep Agents can operate on the actual working set instead of host-specific absolute paths.
- Validation commands are normalized against the bound repo root, so the verifier sees workspace-local commands instead of host-specific `cd /abs/path && ...` wrappers.
- New sessions automatically absorb high-signal insights from the most recent successful work in the same repo, so the product does not restart from zero every time.
- Recent project memory is quality-ranked, so signal-rich validated sessions outrank empty or partial bootstraps when Workbench seeds a new task.
- Collaboration patterns are also quality-ranked, so later tasks can inherit not only file hints but also reusable agent strategies from the same project scope.
- Workbench now uses those collaboration patterns for strategy selection, so later tasks can start with a narrower working set and a better default validation path before the model expands scope.
- Strategy selection is now trust-shaped, so the product prefers `exact_task_signature`, `same_task_family`, and `same_error_family` before it falls back to broader module similarity.
- Delegation results are now persisted as artifact references under `.aionis-workbench/artifacts/<task-id>/`, mirrored into the project store, and re-seeded as references instead of only long summaries.
- When newer durable insights supersede older ones, Workbench moves the older versions into a structured forgetting backlog. Repeatedly superseded entries progress from `backlog` to `suppressed` to `evicted`, so obsolete guidance stops reseeding future sessions.
- Repo identity is explicit, so sessions, memory, and replay stay attached to the actual working repo instead of the host shell.
- Aionis scope now defaults to the project identity, so durable memory is isolated by project at the kernel level, not only by product-side filtering.
- Durable sessions are mirrored into a project-scoped store, so continuity survives new clones and alternate worktrees of the same project.
- Execution now has a packet-first contract, and provenance summaries plus layered context snapshots are persisted alongside the session so inspect/debug surfaces do not need to reconstruct meaning from raw memory lines.
