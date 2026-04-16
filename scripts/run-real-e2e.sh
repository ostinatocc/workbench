#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

DOC_PACKAGE_ROOT="${AIONISDOC_PACKAGE_ROOT:-}"
if [[ -z "${DOC_PACKAGE_ROOT}" && -n "${AIONIS_RUNTIME_ROOT:-}" ]]; then
  CANDIDATE_DOC_ROOT="${AIONIS_RUNTIME_ROOT}/packages/aionis-doc"
  if [[ -f "${CANDIDATE_DOC_ROOT}/package.json" ]]; then
    DOC_PACKAGE_ROOT="${CANDIDATE_DOC_ROOT}"
  fi
fi

if [[ -n "${DOC_PACKAGE_ROOT}" && -f "${DOC_PACKAGE_ROOT}/package.json" && ! -d "${DOC_PACKAGE_ROOT}/dist" ]]; then
  npm --prefix "${DOC_PACKAGE_ROOT}" run build >/dev/null
fi

.venv/bin/python -m pytest \
  tests_real_e2e/test_manifest_loader.py \
  tests_real_e2e/test_repo_cache.py \
  tests_real_e2e/test_cli_driver.py \
  tests_real_e2e/test_runtime_env.py \
  tests_real_e2e/test_result_models.py \
  tests_real_e2e/test_editor_to_dream.py \
  tests_real_e2e/test_publish_recover_resume.py \
  tests_real_e2e/test_repeated_workflow_reuse.py \
  tests_real_e2e/test_launcher_runtime_cycle.py \
  -q "$@"

env \
  -u AIONIS_RUNTIME_ROOT \
  -u AIONIS_CORE_DIR \
  -u AIONISDOC_PACKAGE_ROOT \
  -u AIONISDOC_WORKSPACE_ROOT \
  .venv/bin/python -m pytest \
    tests/test_launcher_state.py \
    tests/test_runtime_manager.py \
    tests/test_cli_shell.py \
    tests/test_product_workflows.py \
    -q "$@"
