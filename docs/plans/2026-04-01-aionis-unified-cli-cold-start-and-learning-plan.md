# Aionis Unified CLI Cold Start and Learning Plan

**Goal:** Turn `Aionis Workbench` from a powerful but layered engine into a simpler product experience where the user primarily interacts with a single `aionis` CLI, while cold start and learning happen mostly by default instead of relying on manual memory curation.

**Core product idea:** The user should not need to understand `deepagents`, `Workbench`, session artifacts, or manual `ingest` in order to get value. The system should:

- expose one clear CLI product surface
- bootstrap useful project context from a repo automatically
- learn from normal task execution automatically
- retain manual `ingest` and maintenance commands as fallback / operator tools

---

## Problem

Right now, the strongest current Workbench usage pattern is:

1. do a concrete task
2. validate it
3. `ingest` it
4. do a similar next task

That is a good **internal operating model**, but it is not yet the ideal **external product model**.

For a complete `aionis` CLI product, the user should not have to think:

- "I need to manually feed the system three good tasks before it becomes useful"

Instead, the user should experience:

- "I pointed Aionis at my repo, started using it, and it began getting smarter about this project"

So the problem has three parts:

1. **Cold start**
   - A new project has no prior sessions yet.

2. **Learning**
   - Today the cleanest learning path still leans on manual `ingest`.

3. **Product simplicity**
   - The current architecture is strong, but the user can still feel the boundary between:
     - execution substrate
     - learning/memory layer
     - CLI shell

This plan solves those three together.

---

## Product Thesis

The correct product shape is:

- **`aionis` CLI** is the only user-facing product entrypoint
- **`Workbench`** becomes the hidden learning/control layer
- **`deepagents`** becomes the hidden execution substrate

The user should only think in terms of:

- project
- task
- family
- plan
- work
- fix
- review
- history
- dashboard

They should not need to think in terms of:

- session packet internals
- artifact routing objects
- collaboration pattern records
- deepagents lifecycle

Those remain real, but internal.

---

## Target User Experience

### Day 0: New repo

User runs:

```bash
aionis init --repo-root /absolute/path/to/repo
```

or simply:

```bash
aionis --repo-root /absolute/path/to/repo
```

If the repo has never been seen before, Aionis should:

- identify the project
- build a bootstrap project record
- inspect the repo structure
- infer likely validation commands
- infer likely working sets / file clusters
- optionally import a small amount of recent history

The system should not feel empty even when no prior sessions exist.

### Day 1: First few tasks

User does normal work:

- `/run`
- `/fix`
- `/validate`
- manual coding
- manual test runs

The system should automatically absorb useful task outcomes where possible.

### Week 1+: Same project gets smarter

Once several tasks exist, the system should naturally start improving:

- stronger family priors
- better default working sets
- narrower validation paths
- cleaner routed artifact preferences
- more stable default task flows

This should happen without the user needing to become a memory operator.

---

## Scope

This plan covers:

- unified CLI product model
- cold-start behavior
- automatic learning behavior
- relationship between manual `ingest` and automatic absorption
- implementation phases
- acceptance targets

This plan does **not** require:

- a web UI
- replacing `deepagents`
- eliminating manual `ingest`
- solving every autonomous project-generation use case

---

## Architecture Model

## Layer 1: Product CLI

User-facing layer:

- `aionis`
- `aionis shell`
- `aionis run`
- `aionis resume`
- `aionis ingest`
- `aionis evaluate`
- `aionis dashboard`
- future:
  - `aionis init`
  - `aionis consolidate`

This layer defines:

- command vocabulary
- workflow defaults
- task selection model
- output surfaces

## Layer 2: Learning and Control

Hidden layer:

- canonical surfaces
- continuity snapshot
- strategy selection
- family priors
- artifact routing
- evaluation
- consolidation

This is the current `Workbench` core.

## Layer 3: Execution Substrate

Hidden layer:

- model invocation
- agent execution
- tool use
- subagents
- shell backend

This is the current `deepagents` substrate.

### Bottom line

The user sees one product:

- `aionis`

The user does **not** need to understand the lower layers.

---

## Cold Start Strategy

Cold start should be treated as a first-class product problem, not as "the system is empty until enough manual ingest has happened."

The right approach is a **three-layer cold-start model**:

1. repo bootstrap
2. history import
3. low-trust priors

## Cold Start Layer 1: Repo Bootstrap

When a repo is first bound, Aionis should immediately derive a bootstrap context.

### Bootstrap outputs

- project identity
- project scope
- language / framework hints
- test framework hints
- key root directories
- likely source directories
- likely test directories
- likely entry commands
- likely validation commands
- file cluster hints
- initial task family guesses

### Example outputs

For a Python repo, bootstrap may infer:

- `src/`
- `tests/`
- `pytest`
- likely `PYTHONPATH=src`

For a JS repo, bootstrap may infer:

- `src/`
- `test/`
- `npm test` / `pnpm test`

### Why this matters

Even without prior sessions, the system can already provide:

- useful `/plan`
- plausible `/work`
- non-empty `/dashboard`
- initial working-set suggestions

This solves the "empty product" feeling.

## Cold Start Layer 2: History Import

Cold start should also use the repo’s own history.

### Candidate inputs

- recent commits
- recent changed files
- recent test file churn
- recent validation scripts
- recent bugfix clusters
- optionally linked PR / issue metadata later

### Imported signals

- recurring touched files
- recurring validation commands
- recurring family hints
- recurring source/test pairings

### Important constraint

This import should begin as **lightweight heuristic import**, not a giant retroactive ingestion project.

The first version should be:

- small
- fast
- deterministic

## Cold Start Layer 3: Low-Trust Priors

When project-local evidence is still sparse, Aionis can lean on low-trust priors.

These priors should be:

- family-level
- conservative
- clearly lower confidence than project-local evidence

### Example prior classes

- `task:termui`
- `task:testing`
- `task:completion-shell`
- `task:decorators`

### Important rule

Priority order should be:

1. exact project-local evidence
2. recent project-local family evidence
3. imported project history
4. low-trust general priors

Never let generic priors overpower project-local evidence.

---

## Automatic Learning Strategy

The long-term product should not depend on users remembering to call `ingest` after every successful task.

The system should learn automatically from normal use.

### Learning model

There should be **three learning paths**:

1. automatic absorption
2. passive observation
3. explicit ingest

## Learning Path 1: Automatic Absorption

Whenever a task completes successfully through normal Aionis usage, the system should automatically absorb it as a usable project sample.

### Candidate triggers

- successful `run`
- successful `resume`
- successful `/fix` followed by green validation
- successful validation-confirmed workflow closure

### What gets absorbed automatically

- working set
- validation path
- task family
- strategy profile
- role sequence
- artifact references
- routing feedback
- evaluation summary

### User expectation

The user should feel:

- "if Aionis solved it and validation passed, Aionis learned from it"

## Learning Path 2: Passive Observation

Even when the user works partly outside Aionis, the system should learn from observed project activity.

### Passive sources

- file diffs
- git status
- changed files
- manual validation runs
- manual test success
- current task context

### Example

If the user:

- uses `/use task-123`
- edits files manually
- runs `/validate`
- validation passes

Then Aionis should be able to infer:

- useful changed files
- useful validation path
- useful task-family evidence

without requiring a separate manual ingest step.

## Learning Path 3: Explicit Ingest

`ingest` should remain, but as a fallback and operator tool.

Use cases:

- work completed outside Aionis
- historical backfill
- manual curated task import
- high-signal replay samples

### Product positioning

`ingest` should remain important, but it should not be the only clean learning path.

---

## Unified CLI Command Model

The CLI should present a coherent lifecycle:

## Initialization

- `aionis init`
- `aionis --repo-root ...`

## Working

- `/plan`
- `/work`
- `/review`
- `/fix`
- `/next`
- `/validate`

## Inspection

- `/show`
- `/family`
- `/session`
- `/evaluate`
- `/compare-family`
- `/dashboard`

## Maintenance

- `ingest`
- `backfill`
- `consolidate`
- future:
  - `/dream`

This should feel like one product, not several layers bolted together.

---

## Relationship Between `ingest` and the Complete Product

The right relationship is:

- **now:** `ingest` is a primary practical path
- **later:** `ingest` becomes a secondary operator path

That means:

### Current phase

- `ingest` is one of the safest ways to build project memory

### Target phase

- most successful tasks are auto-absorbed
- `ingest` is only needed for:
  - external tasks
  - historical tasks
  - explicit curated memory seeding

This is how the product moves from:

- memory operator workflow

to:

- default-learning workflow

---

## Implementation Phases

## Phase 1: Unified CLI Shell As Product Entry

**Status:** substantially underway already

### Deliverables

- single `aionis` entrypoint
- shell-first usage model
- default workflow commands:
  - `/plan`
  - `/work`
  - `/review`
  - `/fix`

### Acceptance

- user can enter one shell and work through project tasks without touching low-level internals

## Phase 2: Cold Start Bootstrap

### Deliverables

- repo inspection
- bootstrap project record
- inferred validation defaults
- inferred working-set hints
- initial family hints

### Files likely involved

- `src/aionis_workbench/config.py`
- `src/aionis_workbench/runtime.py`
- new:
  - `src/aionis_workbench/bootstrap.py`
  - `src/aionis_workbench/bootstrap_inference.py`

### Acceptance

- fresh repo gets a non-empty plan/work surface before any prior sessions exist

## Phase 3: History Import

### Deliverables

- lightweight recent-commit scan
- recent changed-file cluster inference
- validation command inference from history
- project bootstrap summary persisted

### Acceptance

- cold-start repo with history feels meaningfully less empty

## Phase 4: Automatic Absorption

### Deliverables

- successful `run` and `resume` auto-absorb memory signals
- successful `/fix` + validation can produce auto-learning updates
- auto-learned samples become visible in canonical surfaces

### Acceptance

- user does not need `ingest` for every successful task

## Phase 5: Passive Observation

### Deliverables

- changed-files observation
- validation-run observation
- manual success capture
- operator-safe inferred sample updates

### Acceptance

- partially manual workflows still strengthen Aionis project memory

## Phase 6: Auto-Consolidation

### Deliverables

- follow the separate plan:
  - `2026-04-01-aionis-auto-dream-auto-consolidation-plan.md`

### Acceptance

- accumulated learning is periodically cleaned and strengthened automatically

---

## Verification Strategy

Verification should happen on real repos, not just synthetic tests.

### Layer 1: Bootstrap verification

Fresh repo with no sessions:

- does `/plan` show useful next action?
- does `/work` show plausible validation suggestions?
- does project scope resolve correctly?

### Layer 2: Learning verification

Normal task flow:

- complete one task
- validate green
- check whether family priors / artifacts updated without explicit ingest

### Layer 3: Comparative verification

Do 2-3 same-family tasks and verify:

- later tasks start narrower
- later tasks show stronger same-family reuse
- artifact routing becomes cleaner

### Layer 4: Operator verification

Explicit `ingest` still works and remains useful for:

- external work
- historical import
- curated memory injection

---

## Acceptance Targets

This plan is successful when:

1. A user can point `aionis` at a new repo and get a useful non-empty shell experience immediately.
2. A user can do several tasks without needing to manually ingest every success.
3. Aionis project memory improves through normal usage, not only explicit curation.
4. Generic priors never overpower project-local evidence.
5. `ingest` remains available, but becomes optional in the common path.
6. The full stack feels like one product:
   - `aionis` outside
   - Workbench inside
   - deepagents underneath

---

## Recommended Build Order

1. unified CLI shell stabilization
2. cold-start bootstrap
3. lightweight history import
4. automatic absorption of successful tasks
5. passive observation of manual work
6. auto-consolidation

This order matters.

Do **not** start by trying to fully automate project generation from nothing. Start by making normal project work bootstrap, learn, and consolidate automatically.

---

## Bottom Line

The complete `aionis` CLI should solve cold start and learning as default product behavior:

- bootstrap from repo structure
- import lightweight history
- lean on low-trust priors only when needed
- automatically absorb successful task outcomes
- passively learn from normal project activity
- periodically consolidate what it has learned

That is how Aionis moves from:

- "a powerful learning shell that still benefits from operator curation"

to:

- "a unified project CLI that gets smarter by default as you use it"
