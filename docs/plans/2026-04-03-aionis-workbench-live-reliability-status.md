# Aionis Workbench Live Reliability And Provider Hygiene Status

Date: 2026-04-04

## Current State

The live reliability and provider hygiene track has moved from ad hoc bring-up into an explicit operating model.

Workbench now has:

- measurable live timing records
- explicit provider profiles
- safer credential guidance
- machine-evaluable release gates
- dedicated deterministic and live runner scripts

This means the current live path is no longer only "working on one machine." It is now partially standardized, inspectable, and gated for release use.

## Landed Reliability Pieces

### Live timing records

Workbench now records named live phases through `LiveTimingRecord`:

- `ready`
- `run`
- `resume`

Scenario results can now expose:

- `ready_duration_seconds`
- `run_duration_seconds`
- `resume_duration_seconds`
- `total_duration_seconds`
- `timing_summary`

This is the first stable timing surface for `real-live-e2e`.

That timing state is now also readable through the product CLI:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
aionis live-profile --repo-root /absolute/path/to/repo
```

The command reports:

- active provider profile
- active live mode
- current timeout and token budget
- latest recorded live timing snapshot when one exists

### Explicit provider profiles

Provider configuration is now standardized through explicit profiles in
[provider_profiles.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/provider_profiles.py).

Current built-in profiles:

- `zai_glm51_coding`
- `openai_default`
- `openrouter_default`

Each profile now captures:

- provider id
- base URL
- model
- timeout
- max completion tokens
- whether live is supported
- release tier

### Safer provider and secret guidance

Doctor/setup/preflight flows no longer encourage raw `export ...API_KEY=...` copy-paste in recovery hints.

They now point users toward the safer setup guide:

- [2026-04-03-aionis-provider-setup-guide.md](/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionis-provider-setup-guide.md)

That guide now standardizes:

- local `.env`-style loading
- shell-local env files
- secret-manager-friendly setup
- provider-profile-based verification

### Release gates

Release-time validation is now standardized through:

- [release_gates.py](/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/release_gates.py)
- [run-real-e2e.sh](/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-real-e2e.sh)
- [run-release-gates.sh](/Volumes/ziel/Aioniscli/Aionis/workbench/scripts/run-release-gates.sh)

The release gate evaluator now checks:

- deterministic suite result
- live suite result
- provider supports live
- provider release tier is approved

## Current Timing Baseline

Latest verified Z.AI / GLM-5.1 timing numbers:

- `live-run-pause`: `57.66s`
- `live-resume-complete`: `106.87s`
- split live script total: `158.31s`

These numbers are good enough to prove live correctness, but they are still slower than the desired release posture. Live speed remains an open hardening topic.

## Current Provider Posture

### Approved for release gating

- `zai_glm51_coding`
  - `supports_live=True`
  - `release_tier=manual_verified`

### Not yet approved for release gating

- `openai_default`
  - `release_tier=experimental`
- `openrouter_default`
  - `release_tier=experimental`

This means release gates will currently pass provider policy only on the manually verified Z.AI profile.

## Current Verification

Latest targeted reliability regression:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_release_gates.py tests/test_provider_profiles.py -q
```

Latest result:

- `173 passed in 2.30s`

Latest release-gate runner behavior on a shell without live credentials:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
bash ./scripts/run-release-gates.sh
```

Latest result:

- deterministic suite: green
- live suite: failed due to missing live credentials
- provider gate: failed when inferred profile is not release-approved

Representative gate summary:

```text
release-gates: failed deterministic=ok live=failed provider=openai_default tier=experimental failures=live_suite_failed; provider_not_approved_for_release
```

This is the correct current behavior.

## Product Issues Closed By This Track

This track also locked one real live behavior bug into deterministic regression coverage:

- explicit `resume --validation-command ...` now overrides the old failed validation chain
- Workbench no longer appends new validation commands to the previous failing `false`

This was first exposed by real model-backed bring-up and is now protected by deterministic product tests.

## Remaining Risks

- live timing is still slow for release confidence loops
- only one provider profile is currently approved for release verification
- release gates still fail by design in shells without live credentials
- there is still no user-facing CLI surface for inspecting stored live timing reports directly

## Judgment

The live reliability track is now credible.

Workbench can now:

- say which provider profile is active
- record where live time is being spent
- distinguish experimental providers from release-approved ones
- fail release validation with explicit, machine-readable reasons

The remaining work is no longer "make live real." It is "make live faster, more repeatable, and easier to release safely."
