#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

export WORKBENCH_EXECUTION_HOST="openai_agents"

if ! "$ROOT_DIR/.venv/bin/python" - <<'PY'
from aionis_workbench.provider_profiles import provider_profile_has_required_credentials, resolve_provider_profile
profile = resolve_provider_profile()
raise SystemExit(0 if provider_profile_has_required_credentials(profile) else 1)
PY
then
  echo "openai-agents live e2e requires credentials for the selected provider profile" >&2
  exit 2
fi

cd "$ROOT_DIR"
.venv/bin/python -m pytest \
  tests_real_live_e2e/test_live_app_plan.py \
  tests_real_live_e2e/test_live_app_qa.py \
  tests_real_live_e2e/test_live_app_negotiate.py \
  tests_real_live_e2e/test_live_app_retry.py \
  tests_real_live_e2e/test_live_app_replan.py \
  tests_real_live_e2e/test_live_app_generate.py \
  tests_real_live_e2e/test_live_app_escalate.py \
  tests_real_live_e2e/test_live_app_replan_generate_qa.py \
  tests_real_live_e2e/test_live_app_replan_generate_qa_advance.py \
  -q "$@"
