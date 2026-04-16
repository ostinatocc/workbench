# Aionis Provider Setup Guide

Date: `2026-04-03`

## Goal

Configure live model providers for `Aionis Workbench` without pasting secrets into shared docs, screenshots, or long-lived shell history.

## Recommended Rule

Prefer one of these patterns:

1. load credentials from a local `.env`-style file
2. load credentials from a shell-local file that is not committed
3. inject credentials from a secret manager

Avoid putting full API keys directly into:

- screenshots
- chat logs
- committed scripts
- reusable shell history snippets

## Option 1: Local `.env.workbench`

Create a local file that is ignored by git, for example:

```bash
cat > .env.workbench <<'EOF'
OPENAI_API_KEY=your-provider-key
OPENAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
WORKBENCH_MODEL=glm-5.1
AIONIS_PROVIDER_PROFILE=zai_glm51_coding
EOF
```

Load it only for the current shell:

```bash
set -a
source ./.env.workbench
set +a
```

Then run:

```bash
aionis ready --repo-root /absolute/path/to/repo
```

## Option 2: Shell-local env file

If you do not want a repo-local file, keep one outside the repo:

```bash
set -a
source ~/.config/aionis/workbench.env
set +a
```

This keeps secrets out of the repository while still making local runs easy.

## Option 3: Secret manager

If you already use a secret manager, inject into the shell immediately before running Workbench.

The requirement is simple:

- credentials enter the environment
- Workbench reads them
- the values are not hard-coded into scripts or docs

## Supported Provider Profiles

### Z.AI GLM-5.1

Recommended for the currently verified live profile:

```bash
OPENAI_API_KEY=your-provider-key
OPENAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
WORKBENCH_MODEL=glm-5.1
AIONIS_PROVIDER_PROFILE=zai_glm51_coding
```

### OpenAI Default

```bash
OPENAI_API_KEY=your-provider-key
WORKBENCH_MODEL=gpt-5
AIONIS_PROVIDER_PROFILE=openai_default
```

### OpenRouter Default

```bash
OPENROUTER_API_KEY=your-provider-key
OPENROUTER_MODEL=openai/gpt-5.4
AIONIS_PROVIDER_PROFILE=openrouter_default
```

## Verification

After loading credentials, check:

```bash
aionis ready --repo-root /absolute/path/to/repo
```

Expected:

- `live_ready=True` when both provider credentials and runtime availability are healthy

For the full live gate:

```bash
./scripts/run-real-live-e2e.sh
```

For the full release gate:

```bash
./scripts/run-release-gates.sh
```

## Hygiene Checklist

- keep provider env files out of git
- do not paste full keys into screenshots or chat
- rotate any key that was exposed in terminal output
- prefer profile-based setup over ad hoc env combinations

## Current Recommendation

For daily use, prefer:

- one local env file
- one explicit provider profile
- one `aionis ready` check before long live runs
