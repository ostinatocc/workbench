#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

PYTHONPATH=src:tests .venv/bin/python -m pytest -q \
  tests/test_product_workflows.py::test_product_controller_action_bar_stays_consistent_across_task_scoped_surfaces \
  tests/test_product_workflows.py::test_product_paused_controller_action_bar_stays_consistent_across_task_scoped_surfaces \
  tests/test_product_workflows.py::test_product_completed_controller_action_bar_stays_consistent_across_task_scoped_surfaces \
  tests/test_shell_dispatch.py::test_dispatch_help_includes_controller_context_when_available \
  tests/test_shell_dispatch.py::test_dispatch_routes_work \
  tests/test_shell_dispatch.py::test_dispatch_routes_review \
  tests/test_shell_dispatch.py::test_dispatch_routes_plan \
  tests/test_shell_dispatch.py::test_dispatch_blocks_next_when_controller_requires_resume \
  tests/test_shell_dispatch.py::test_dispatch_blocks_fix_when_controller_requires_resume \
  tests/test_cli_shell.py::test_main_prints_app_show_surface \
  tests/test_cli_shell.py::test_main_prints_app_plan_sprint_and_qa_surfaces \
  tests/test_cli_shell.py::test_run_shell_prompt_surfaces_primary_controller_action \
  tests/test_cli_shell.py::test_run_shell_doc_inspect_renders_summary \
  "$@"

PYTHONPATH=src:tests .venv/bin/python -m compileall src/aionis_workbench
