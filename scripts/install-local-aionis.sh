#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKBENCH_DIR="${ROOT_DIR}"
VENV_DIR="${WORKBENCH_DIR}/.venv"

require_bin() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "install-local-aionis: missing required command: ${name}" >&2
    exit 1
  fi
}

resolve_runtime_root() {
  local candidates=()
  if [[ -n "${AIONIS_RUNTIME_ROOT:-}" ]]; then
    candidates+=("${AIONIS_RUNTIME_ROOT}")
  fi
  if [[ -n "${AIONIS_CORE_DIR:-}" ]]; then
    candidates+=("${AIONIS_CORE_DIR}")
  fi
  candidates+=(
    "${WORKBENCH_DIR}/../AionisCore"
    "${WORKBENCH_DIR}/../AionisRuntime"
    "${WORKBENCH_DIR}/../runtime-mainline"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}/package.json" ]]; then
      cd "${candidate}" && pwd
      return 0
    fi
  done
  return 1
}

require_bin python3

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install -U pip
(
  cd "${WORKBENCH_DIR}"
  "${VENV_DIR}/bin/pip" install -e .[dev]
)

RUNTIME_ROOT=""
if RUNTIME_ROOT="$(resolve_runtime_root 2>/dev/null)"; then
  require_bin node
  require_bin npm
  (
    cd "${RUNTIME_ROOT}"
    npm install
  )
fi

cat <<EOF
local Aionis Workbench install complete.

Recommended next steps:

  export PATH="${VENV_DIR}/bin:\$PATH"

If you already have a running Aionis Core runtime:

  export AIONIS_BASE_URL="http://127.0.0.1:3001"
  aionis status

EOF

if [[ -n "${RUNTIME_ROOT}" ]]; then
  cat <<EOF
Detected runtime workspace:

  ${RUNTIME_ROOT}

You can now run:

  aionis status
  aionis --repo-root /absolute/path/to/repo

Without modifying PATH:

  ${VENV_DIR}/bin/aionis status
  ${VENV_DIR}/bin/aionis --repo-root /absolute/path/to/repo
EOF
else
  cat <<EOF
No local Aionis Core checkout was detected.

Either:
  1. start Aionis Core separately and set AIONIS_BASE_URL
  2. export AIONIS_RUNTIME_ROOT or AIONIS_CORE_DIR to your local Aionis Core checkout, then rerun this script

Without modifying PATH:

  ${VENV_DIR}/bin/aionis status
  ${VENV_DIR}/bin/aionis --repo-root /absolute/path/to/repo
EOF
fi
