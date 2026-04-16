#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"
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
  tests/test_launcher_state.py \
  tests/test_runtime_manager.py \
  tests/test_cli_shell.py \
  tests/test_product_workflows.py \
  -q "$@"
