# Aionis Execution and Onboarding Productization Plan

## Goal

Turn the current strong internal product core into a smoother external product by closing the last two visible gaps:

1. execution failure paths still feel too runtime-shaped
2. install / onboarding still feels operator-shaped

The next phase should make `aionis` feel more like one product that can explain:

- what mode it is in
- why a live task cannot run
- what the user should do next
- what the minimum setup path is

---

## Why This Phase Now

The current product already has:

- unified CLI shell
- cold start bootstrap
- automatic learning
- passive observation
- consolidation and family priors
- host contract and health surfaces
- degraded-mode awareness in the default workflow

So the next highest-leverage work is no longer adding more shell commands. It is making the remaining rough edges product-grade:

- `/run` and `/resume` should fail like a product, not like a stack
- setup should be discoverable and testable from a cold machine

---

## Problem 1: Execution Failure Paths Still Leak Runtime Details

Today the product can already tell the user:

- execution host is `available`, `degraded`, or `offline`
- runtime host is `available`, `degraded`, or `offline`
- current mode is `live_enabled` or `inspect_only`

But when `/run` or `/resume` actually fails, the experience is still too raw:

- generic error string
- runtime connection failure details
- no structured recovery path

That is acceptable internally but weak externally.

### Product requirement

When live execution is not available, `aionis` should clearly explain:

- whether the problem is execution, runtime, or both
- whether the product is currently `inspect-only`
- what the user can still do right now
- what exact next step would move them back to `live`

---

## Problem 2: Onboarding Is Still Too Operator-Oriented

Current onboarding is already much better than before because:

- `aionis init` exists
- bootstrap exists
- shell can explain current mode

But new-user onboarding still needs a tighter product path.

### Product requirement

The user should be able to answer:

- is my environment healthy?
- can I run live tasks yet?
- if not, what is missing?
- what command should I run next?

without needing to read internals.

---

## Phase Plan

## Phase 1: Productize `/run` and `/resume` Failure Paths

### Goal

Turn run/resume failures into structured degraded-mode product responses.

### Deliverables

- structured `host_error` payloads for `/run` and `/resume`
- shell rendering for these payloads
- mode-aware guidance:
  - execution offline
  - runtime offline
  - inspect-only mode
  - missing credentials
- compact recommendation lines instead of generic failure strings

### Acceptance

When execution credentials are missing or runtime is unreachable:

- `/run` does not just say `run failed: ...`
- shell shows:
  - current host mode
  - failing capability
  - inspect-only fallback
  - concrete next steps

---

## Phase 2: Add `aionis doctor`

### Goal

Provide a single environment health command for onboarding and support.

### Doctor should check

- Python availability
- repo-root validity
- bootstrap presence
- execution host status
- runtime host status
- model credentials presence
- whether current mode is `live` or `inspect-only`

### Output should answer

- what is healthy
- what is missing
- what mode the product is currently in
- what to do next

### Acceptance

`aionis doctor --repo-root /path/to/repo` should be enough to tell a new user whether they can use:

- inspect-only workflow
- live workflow

and why.

---

## Phase 3: Tighten `init` into a Setup Path

### Goal

Reduce setup ambiguity for a first-time repo.

### Deliverables

- stronger `aionis init` messaging
- clearer bootstrap output
- explicit “next commands” after init
- optional environment hints:
  - runtime missing
  - credentials missing
  - live mode unavailable

### Acceptance

After `aionis init`, the user should know whether to:

- enter the shell
- stay in inspect-only mode
- configure credentials
- start/configure runtime

---

## Phase 4: Feed Product Health Back Into the Shell Entry

### Goal

Make the shell self-explanatory for new users.

### Deliverables

- startup line that clearly states:
  - `live`
  - `inspect-only`
  - degraded reason
- `/status` and `/hosts` remain the deeper explanation surfaces

### Acceptance

A user entering `aionis --repo-root ...` should not have to guess whether live execution is available.

---

## Design Principles

### 1. Product wording first

Prefer:

- `inspect-only mode`
- `live execution unavailable`
- `runtime unreachable`
- `configure credentials`

Avoid leaking raw implementation details unless raw mode is explicitly requested.

### 2. Structured errors, not string parsing

Error paths should produce structured payloads first, then render user-facing text from those payloads.

### 3. Keep degraded mode useful

If live execution is unavailable, the product should explicitly guide the user toward:

- `/plan`
- `/work`
- `/review`
- `/validate`
- `/ingest`

### 4. Do not overbuild onboarding UI

This phase should stay CLI-first:

- no web UI
- no heavy TUI
- no installer wizard

---

## Recommended Order

1. Phase 1: `/run` and `/resume` degraded-mode productization
2. Phase 2: `aionis doctor`
3. Phase 3: stronger `init` / setup path
4. Phase 4: lighter shell startup health guidance

---

## Bottom Line

The next phase is about converting the remaining sharp technical edges into product behavior:

- live-task failures should teach the user what mode they are in
- onboarding should tell the user what is missing
- `aionis` should feel like one product, not a thin wrapper over multiple systems
