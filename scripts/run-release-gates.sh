#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DETERMINISTIC_EXIT=0
LIVE_EXIT=0
CONTROLLER_CONTRACT_EXIT=0

bash ./scripts/run-controller-contract-suite.sh "$@" || CONTROLLER_CONTRACT_EXIT=$?
bash ./scripts/run-real-e2e.sh "$@" || DETERMINISTIC_EXIT=$?
bash ./scripts/run-real-live-e2e.sh "$@" || LIVE_EXIT=$?

if [[ ${DETERMINISTIC_EXIT} -eq 0 && ${CONTROLLER_CONTRACT_EXIT} -ne 0 ]]; then
  DETERMINISTIC_EXIT=${CONTROLLER_CONTRACT_EXIT}
fi

PROVIDER_PROFILE="${AIONIS_PROVIDER_PROFILE:-}"
if [[ -z "$PROVIDER_PROFILE" ]]; then
  PROVIDER_PROFILE="$(.venv/bin/python - <<'PY'
from aionis_workbench.provider_profiles import infer_provider_profile_id
print(infer_provider_profile_id() or "openai_default")
PY
)"
fi

.venv/bin/python - <<PY
from aionis_workbench.release_gates import evaluate_release_gates
result = evaluate_release_gates(
    deterministic_exit_code=${DETERMINISTIC_EXIT},
    live_exit_code=${LIVE_EXIT},
    provider_profile="${PROVIDER_PROFILE}",
)
print(result.summary())
raise SystemExit(0 if result.passed else 1)
PY
