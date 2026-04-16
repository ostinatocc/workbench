from __future__ import annotations

import sys
import json
from types import SimpleNamespace

from aionis_workbench import cli
from aionis_workbench.provider_profiles import SAFE_CREDENTIALS_HINT
from aionis_workbench.shell import _render_result_payload, run_shell


def test_parser_accepts_shell_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["shell"])
    assert args.command == "shell"


def test_parser_help_groups_commands_by_tier() -> None:
    parser = cli.build_parser()
    help_text = parser.format_help()
    normalized_help = " ".join(help_text.split())

    assert "Recommended stable path:" in help_text
    assert "Stable commands: init, doctor, ready, status, run, resume, session" in help_text
    assert "Beta commands: setup, shell, live-profile, compare-family, recent-tasks, dashboard, consolidate" in help_text
    assert "Internal commands: start, stop, ship, ingest, evaluate, hosts, dream, ab-test, app, doc, backfill" in help_text
    assert "[stable] Start a new workbench session." in help_text
    assert "[beta] Show a project-level live instrumentation dashboard grouped by task family." in normalized_help
    assert "[internal] Inspect the persisted app harness state for a task." in normalized_help


def test_parser_defaults_app_sprint_to_approved() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "app",
            "sprint",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--goal",
            "Ship the first runnable landing page.",
        ]
    )
    assert args.approved is True


def test_parser_accepts_launcher_status_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["status"])
    assert args.command == "status"


def test_parser_accepts_launcher_start_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["start"])
    assert args.command == "start"


def test_parser_accepts_launcher_stop_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["stop"])
    assert args.command == "stop"


def test_parser_keeps_existing_subcommands() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["dashboard", "--repo-root", "/tmp/repo"])
    assert args.command == "dashboard"
    assert args.repo_root == "/tmp/repo"


def test_parser_accepts_recent_tasks_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["recent-tasks", "--repo-root", "/tmp/repo", "--limit", "12"])
    assert args.command == "recent-tasks"
    assert args.repo_root == "/tmp/repo"
    assert args.limit == 12


def test_parser_accepts_consolidate_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["consolidate", "--repo-root", "/tmp/repo", "--limit", "12"])
    assert args.command == "consolidate"
    assert args.repo_root == "/tmp/repo"
    assert args.limit == 12


def test_parser_accepts_dream_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["dream", "--repo-root", "/tmp/repo", "--status", "trial"])
    assert args.command == "dream"
    assert args.repo_root == "/tmp/repo"
    assert args.status == "trial"


def test_parser_accepts_ab_test_compare_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "ab-test",
            "--repo-root",
            "/tmp/repo",
            "compare",
            "--task-id",
            "task-123",
            "--scenario-id",
            "scenario-1",
            "--baseline-ended-in",
            "escalate",
            "--baseline-duration-seconds",
            "120.5",
            "--baseline-retry-count",
            "1",
            "--baseline-escalated",
        ]
    )
    assert args.command == "ab-test"
    assert args.ab_test_command == "compare"
    assert args.task_id == "task-123"
    assert args.scenario_id == "scenario-1"
    assert args.baseline_duration_seconds == 120.5
    assert args.baseline_retry_count == 1
    assert args.baseline_escalated is True


def test_parser_accepts_ab_test_compare_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "ab-test",
            "--repo-root",
            "/tmp/repo",
            "compare",
            "--task-id",
            "task-123",
            "--scenario-id",
            "scenario-1",
            "--baseline-ended-in",
            "escalate",
            "--baseline-duration-seconds",
            "120.5",
            "--baseline-retry-count",
            "1",
            "--baseline-escalated",
        ]
    )
    assert args.command == "ab-test"
    assert args.ab_test_command == "compare"
    assert args.task_id == "task-123"
    assert args.scenario_id == "scenario-1"
    assert args.baseline_duration_seconds == 120.5
    assert args.baseline_retry_count == 1
    assert args.baseline_escalated is True


def test_parser_accepts_app_show_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["app", "--repo-root", "/tmp/repo", "show", "--task-id", "task-123"])
    assert args.command == "app"
    assert args.repo_root == "/tmp/repo"
    assert args.app_command == "show"
    assert args.task_id == "task-123"


def test_parser_accepts_app_ship_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "ship",
            "--task-id",
            "task-123",
            "--prompt",
            "Build a modern landing page for an AI agent platform.",
            "--output-dir",
            "/tmp/exported-app",
            "--use-live-planner",
            "--use-live-generator",
        ]
    )
    assert args.command == "app"
    assert args.app_command == "ship"
    assert args.task_id == "task-123"
    assert args.prompt == "Build a modern landing page for an AI agent platform."
    assert args.output_dir == "/tmp/exported-app"
    assert args.use_live_planner is True
    assert args.use_live_generator is True


def test_parser_accepts_ship_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "ship",
            "--repo-root",
            "/tmp/repo",
            "--task-id",
            "task-123",
            "--task",
            "Build a modern landing page for an AI agent platform.",
            "--output-dir",
            "/tmp/exported-app",
            "--use-live-planner",
            "--use-live-generator",
        ]
    )
    assert args.command == "ship"
    assert args.task_id == "task-123"
    assert args.task == "Build a modern landing page for an AI agent platform."
    assert args.output_dir == "/tmp/exported-app"
    assert args.use_live_planner is True
    assert args.use_live_generator is True


def test_parser_accepts_app_plan_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "plan",
            "--task-id",
            "task-123",
            "--prompt",
            "Build a pixel editor.",
            "--title",
            "Pixel Forge",
            "--type",
            "full_stack_app",
            "--stack",
            "React",
            "--feature",
            "canvas",
            "--criterion",
            "functionality:0.8",
        ]
    )
    assert args.command == "app"
    assert args.app_command == "plan"
    assert args.task_id == "task-123"
    assert args.prompt == "Build a pixel editor."
    assert args.title == "Pixel Forge"
    assert args.type == "full_stack_app"
    assert args.stack == ["React"]
    assert args.feature == ["canvas"]
    assert args.criterion == ["functionality:0.8"]
    assert args.use_live_planner is False


def test_parser_accepts_app_plan_live_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "plan",
            "--task-id",
            "task-123",
            "--prompt",
            "Build a pixel editor.",
            "--use-live-planner",
        ]
    )
    assert args.command == "app"
    assert args.app_command == "plan"
    assert args.use_live_planner is True


def test_parser_accepts_app_sprint_and_qa_modes() -> None:
    parser = cli.build_parser()
    sprint_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "sprint",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--goal",
            "Ship the editor shell.",
            "--scope",
            "shell",
            "--acceptance-check",
            "pytest tests/test_editor.py -q",
            "--approved",
        ]
    )
    qa_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "qa",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--status",
            "failed",
            "--summary",
            "Palette persistence still fails.",
            "--score",
            "functionality=0.61",
            "--blocker",
            "palette resets on refresh",
        ]
    )
    assert sprint_args.app_command == "sprint"
    assert sprint_args.sprint_id == "sprint-1"
    assert sprint_args.goal == "Ship the editor shell."
    assert sprint_args.scope == ["shell"]
    assert sprint_args.acceptance_check == ["pytest tests/test_editor.py -q"]
    assert sprint_args.approved is True
    assert qa_args.app_command == "qa"
    assert qa_args.sprint_id == "sprint-1"
    assert qa_args.status == "failed"
    assert qa_args.score == ["functionality=0.61"]
    assert qa_args.blocker == ["palette resets on refresh"]

    qa_auto_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "qa",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
        ]
    )
    assert qa_auto_args.status == "auto"

    qa_live_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "qa",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--use-live-evaluator",
        ]
    )
    assert qa_live_args.use_live_evaluator is True

    negotiate_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "negotiate",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--objection",
            "timeline entries reset on refresh",
        ]
    )
    assert negotiate_args.app_command == "negotiate"
    assert negotiate_args.sprint_id == "sprint-1"
    assert negotiate_args.objection == ["timeline entries reset on refresh"]


def test_parser_accepts_app_generate_advance_replan_and_escalate_modes() -> None:
    parser = cli.build_parser()
    generate_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "generate",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--summary",
            "Apply the narrowed persistence fix before re-running QA.",
            "--target",
            "src/editor.tsx",
        ]
    )
    assert generate_args.command == "app"
    assert generate_args.app_command == "generate"
    assert generate_args.task_id == "task-123"
    assert generate_args.sprint_id == "sprint-1"
    assert generate_args.summary == "Apply the narrowed persistence fix before re-running QA."
    assert generate_args.target == ["src/editor.tsx"]
    assert generate_args.use_live_generator is False

    generate_live_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "generate",
            "--task-id",
            "task-123",
            "--use-live-generator",
        ]
    )
    assert generate_live_args.use_live_generator is True

    advance_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "advance",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-2",
        ]
    )
    assert advance_args.command == "app"
    assert advance_args.app_command == "advance"
    assert advance_args.task_id == "task-123"
    assert advance_args.sprint_id == "sprint-2"

    replan_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "replan",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--note",
            "narrow the sprint around persistence",
            "--use-live-planner",
        ]
    )
    assert replan_args.command == "app"
    assert replan_args.app_command == "replan"
    assert replan_args.task_id == "task-123"
    assert replan_args.sprint_id == "sprint-1"
    assert replan_args.note == "narrow the sprint around persistence"
    assert replan_args.use_live_planner is True

    escalate_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "escalate",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--note",
            "retry budget exhausted",
        ]
    )
    assert escalate_args.command == "app"
    assert escalate_args.app_command == "escalate"
    assert escalate_args.task_id == "task-123"
    assert escalate_args.sprint_id == "sprint-1"
    assert escalate_args.note == "retry budget exhausted"

    negotiate_live_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "negotiate",
            "--task-id",
            "task-123",
            "--use-live-planner",
        ]
    )
    assert negotiate_live_args.use_live_planner is True

    retry_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "retry",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--revision-note",
            "fix timeline persistence",
        ]
    )
    assert retry_args.app_command == "retry"
    assert retry_args.sprint_id == "sprint-1"
    assert retry_args.revision_note == ["fix timeline persistence"]
    assert retry_args.use_live_planner is False

    export_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "export",
            "--task-id",
            "task-123",
            "--output-dir",
            "/tmp/dependency-explorer-export",
        ]
    )
    assert export_args.command == "app"
    assert export_args.app_command == "export"
    assert export_args.task_id == "task-123"
    assert export_args.output_dir == "/tmp/dependency-explorer-export"

    retry_live_args = parser.parse_args(
        [
            "app",
            "--repo-root",
            "/tmp/repo",
            "retry",
            "--task-id",
            "task-123",
            "--use-live-planner",
        ]
    )
    assert retry_live_args.use_live_planner is True


def test_parser_accepts_doc_compile_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        ["doc", "--repo-root", "/tmp/repo", "compile", "--input", "workflow.aionis.md", "--task-id", "task-123", "--strict"]
    )
    assert args.command == "doc"
    assert args.repo_root == "/tmp/repo"
    assert args.doc_command == "compile"
    assert args.input == "workflow.aionis.md"
    assert args.task_id == "task-123"
    assert args.strict is True


def test_parser_accepts_doc_resume_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "doc",
            "--repo-root",
            "/tmp/repo",
            "resume",
            "--input",
            "recover-result.json",
            "--task-id",
            "task-123",
            "--input-kind",
            "recover-result",
            "--query-text",
            "resume workflow",
            "--candidate",
            "read",
            "--candidate",
            "bash",
        ]
    )
    assert args.command == "doc"
    assert args.doc_command == "resume"
    assert args.input == "recover-result.json"
    assert args.task_id == "task-123"
    assert args.input_kind == "recover-result"
    assert args.query_text == "resume workflow"
    assert args.candidate == ["read", "bash"]


def test_parser_accepts_doc_event_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "doc",
            "--repo-root",
            "/tmp/repo",
            "event",
            "--task-id",
            "task-123",
            "--event",
            "editor-event.json",
        ]
    )
    assert args.command == "doc"
    assert args.doc_command == "event"
    assert args.task_id == "task-123"
    assert args.event == "editor-event.json"


def test_parser_accepts_hosts_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["hosts", "--repo-root", "/tmp/repo"])
    assert args.command == "hosts"
    assert args.repo_root == "/tmp/repo"


def test_parser_accepts_doctor_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor", "--repo-root", "/tmp/repo", "--summary"])
    assert args.command == "doctor"
    assert args.repo_root == "/tmp/repo"
    assert args.summary is True


def test_parser_accepts_doctor_one_line_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor", "--repo-root", "/tmp/repo", "--one-line"])
    assert args.command == "doctor"
    assert args.one_line is True


def test_parser_accepts_ready_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["ready", "--repo-root", "/tmp/repo"])
    assert args.command == "ready"
    assert args.repo_root == "/tmp/repo"


def test_parser_accepts_live_profile_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["live-profile", "--repo-root", "/tmp/repo"])
    assert args.command == "live-profile"
    assert args.repo_root == "/tmp/repo"


def test_parser_accepts_setup_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["setup", "--repo-root", "/tmp/repo", "--pending-only", "--check", "bootstrap_initialized"])
    assert args.command == "setup"
    assert args.repo_root == "/tmp/repo"
    assert args.pending_only is True
    assert args.check == "bootstrap_initialized"


def test_parser_accepts_setup_one_line_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["setup", "--repo-root", "/tmp/repo", "--one-line"])
    assert args.command == "setup"
    assert args.one_line is True


def test_parser_accepts_run_preflight_only() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only"])
    assert args.command == "run"
    assert args.preflight_only is True
    assert args.task is None


def test_parser_accepts_run_preflight_one_line() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only", "--one-line"])
    assert args.command == "run"
    assert args.preflight_only is True
    assert args.one_line is True


def test_parser_accepts_resume_preflight_only() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["resume", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only"])
    assert args.command == "resume"
    assert args.preflight_only is True


def test_parser_accepts_resume_preflight_one_line() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["resume", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only", "--one-line"])
    assert args.command == "resume"
    assert args.preflight_only is True
    assert args.one_line is True


def test_main_defaults_to_shell(monkeypatch) -> None:
    called: dict[str, object] = {}

    class StubWorkbench:
        def __init__(self, repo_root: str | None = None) -> None:
            self.repo_root = repo_root

    class StubRuntimeManager:
        def status(self):
            called["runtime_status"] = True
            return {"mode": "stopped", "health_status": "degraded", "health_reason": "runtime_health_unreachable"}

        def start(self):
            called["runtime_start"] = True
            return {
                "mode": "running",
                "health_status": "available",
                "health_reason": None,
                "base_url": "http://127.0.0.1:3101",
                "pid": 4321,
                "action": "started_runtime",
            }

    def fake_create_workbench(repo_root: str | None):
        called["repo_root"] = repo_root
        return StubWorkbench(repo_root)

    def fake_create_runtime_manager():
        return StubRuntimeManager()

    def fake_run_shell(workbench, initial_task_id=None) -> int:
        called["shell"] = True
        called["task_id"] = initial_task_id
        called["workbench_type"] = type(workbench).__name__
        return 0

    monkeypatch.setattr(cli, "create_workbench", fake_create_workbench)
    monkeypatch.setattr(cli, "create_runtime_manager", fake_create_runtime_manager)
    import aionis_workbench.shell as shell

    monkeypatch.setattr(shell, "run_shell", fake_run_shell)
    monkeypatch.setattr(sys, "argv", ["aionis"])

    assert cli.main() == 0
    assert called["runtime_status"] is True
    assert called["runtime_start"] is True


def test_create_workbench_loads_env_files_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class StubWorkbench:
        def __init__(self, *, repo_root: str | None = None, load_env: bool = False) -> None:
            captured["repo_root"] = repo_root
            captured["load_env"] = load_env

    import aionis_workbench.runtime as runtime

    monkeypatch.delenv("AIONIS_LOAD_ENV_FILES", raising=False)
    monkeypatch.setattr(runtime, "AionisWorkbench", StubWorkbench)

    cli.create_workbench("/tmp/repo")

    assert captured == {"repo_root": "/tmp/repo", "load_env": True}


def test_create_workbench_can_disable_env_file_loading(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class StubWorkbench:
        def __init__(self, *, repo_root: str | None = None, load_env: bool = False) -> None:
            captured["repo_root"] = repo_root
            captured["load_env"] = load_env

    import aionis_workbench.runtime as runtime

    monkeypatch.setenv("AIONIS_LOAD_ENV_FILES", "0")
    monkeypatch.setattr(runtime, "AionisWorkbench", StubWorkbench)

    cli.create_workbench("/tmp/repo")

    assert captured == {"repo_root": "/tmp/repo", "load_env": False}


def test_main_shell_skips_runtime_boot_when_runtime_is_already_healthy(monkeypatch) -> None:
    called: dict[str, object] = {}

    class StubWorkbench:
        def __init__(self, repo_root: str | None = None) -> None:
            self.repo_root = repo_root

    class StubRuntimeManager:
        def status(self):
            called["runtime_status"] = True
            return {"mode": "running", "health_status": "available", "health_reason": None}

        def start(self):
            called["runtime_start"] = True
            return {"mode": "running", "health_status": "available", "health_reason": None}

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench(repo_root))
    monkeypatch.setattr(cli, "create_runtime_manager", lambda: StubRuntimeManager())
    import aionis_workbench.shell as shell

    monkeypatch.setattr(shell, "run_shell", lambda workbench, initial_task_id=None: 0)
    monkeypatch.setattr(sys, "argv", ["aionis", "shell"])

    assert cli.main() == 0
    assert called["runtime_status"] is True
    assert "runtime_start" not in called


def test_main_shell_attempts_runtime_boot_before_launch(monkeypatch) -> None:
    called: dict[str, object] = {}

    class StubWorkbench:
        def __init__(self, repo_root: str | None = None) -> None:
            self.repo_root = repo_root

    class StubRuntimeManager:
        def status(self):
            called["runtime_status"] = True
            return {"mode": "stopped", "health_status": "degraded", "health_reason": "runtime_health_unreachable"}

        def start(self):
            called["runtime_start"] = True
            return {
                "mode": "running",
                "health_status": "available",
                "health_reason": None,
                "base_url": "http://127.0.0.1:3101",
                "pid": 4321,
                "action": "started_runtime",
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench(repo_root))
    monkeypatch.setattr(cli, "create_runtime_manager", lambda: StubRuntimeManager())
    import aionis_workbench.shell as shell

    def fake_run_shell(workbench, initial_task_id=None) -> int:
        called["shell"] = True
        return 0

    monkeypatch.setattr(shell, "run_shell", fake_run_shell)
    monkeypatch.setattr(sys, "argv", ["aionis", "shell"])

    assert cli.main() == 0
    assert called["runtime_status"] is True
    assert called["runtime_start"] is True
    assert called["shell"] is True


def test_main_shell_falls_back_to_inspect_mode_when_runtime_boot_fails(monkeypatch) -> None:
    called: dict[str, object] = {}

    class StubWorkbench:
        def __init__(self, repo_root: str | None = None) -> None:
            self.repo_root = repo_root

    class StubRuntimeManager:
        def status(self):
            called["runtime_status"] = True
            return {"mode": "stopped", "health_status": "degraded", "health_reason": "runtime_health_unreachable"}

        def start(self):
            called["runtime_start"] = True
            return {
                "mode": "stopped",
                "health_status": "degraded",
                "health_reason": "runtime_health_unreachable",
                "base_url": "http://127.0.0.1:3101",
                "pid": None,
                "action": "runtime_exit_before_healthy",
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench(repo_root))
    monkeypatch.setattr(cli, "create_runtime_manager", lambda: StubRuntimeManager())
    import aionis_workbench.shell as shell

    def fake_run_shell(workbench, initial_task_id=None) -> int:
        called["shell"] = True
        return 0

    monkeypatch.setattr(shell, "run_shell", fake_run_shell)
    monkeypatch.setattr(sys, "argv", ["aionis", "shell"])

    assert cli.main() == 0
    assert called["runtime_status"] is True
    assert called["runtime_start"] is True
    assert called["shell"] is True


def test_main_prints_launcher_status(monkeypatch, capsys) -> None:
    class StubRuntimeManager:
        def status(self):
            return {
                "mode": "stopped",
                "health_status": "degraded",
                "health_reason": "runtime_health_unreachable",
                "base_url": "http://127.0.0.1:3101",
                "pid": None,
            }

    monkeypatch.setattr(cli, "create_runtime_manager", lambda: StubRuntimeManager())
    monkeypatch.setattr(sys, "argv", ["aionis", "status"])

    exit_code = cli.main()

    assert exit_code == 0
    output = capsys.readouterr().out.strip()
    assert output == (
        "launcher-status: mode=stopped health=degraded reason=runtime_health_unreachable "
        "base_url=http://127.0.0.1:3101 pid=none"
    )


def test_main_calls_runtime_manager_start(monkeypatch, capsys) -> None:
    called: dict[str, object] = {}

    class StubRuntimeManager:
        def start(self):
            called["start"] = True
            return {
                "mode": "running",
                "health_status": "available",
                "health_reason": None,
                "base_url": "http://127.0.0.1:3101",
                "pid": 4321,
                "action": "started_runtime",
            }

    monkeypatch.setattr(cli, "create_runtime_manager", lambda: StubRuntimeManager())
    monkeypatch.setattr(sys, "argv", ["aionis", "start"])

    exit_code = cli.main()

    assert exit_code == 0
    assert called["start"] is True
    output = capsys.readouterr().out.strip()
    assert "launcher-status: mode=running health=available" in output
    assert "action=started_runtime" in output


def test_main_calls_runtime_manager_stop(monkeypatch, capsys) -> None:
    called: dict[str, object] = {}

    class StubRuntimeManager:
        def stop(self):
            called["stop"] = True
            return {
                "mode": "stopped",
                "health_status": "degraded",
                "health_reason": "runtime_stopped",
                "base_url": "http://127.0.0.1:3101",
                "pid": None,
                "action": "stopped_runtime",
            }

    monkeypatch.setattr(cli, "create_runtime_manager", lambda: StubRuntimeManager())
    monkeypatch.setattr(sys, "argv", ["aionis", "stop"])

    exit_code = cli.main()

    assert exit_code == 0
    assert called["stop"] is True
    output = capsys.readouterr().out.strip()
    assert "launcher-status: mode=stopped health=degraded reason=runtime_stopped" in output
    assert "action=stopped_runtime" in output


def test_main_prints_doctor_one_line(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "shell_view": "doctor_one_line",
                "summary_line": f"doctor-summary: inspect-only: missing credentials | pending=1 | recovery=configure model credentials before retrying live execution | next={SAFE_CREDENTIALS_HINT}",
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "doctor", "--repo-root", "/tmp/repo", "--one-line"])

    exit_code = cli.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 0
    assert output == f"doctor-summary: inspect-only: missing credentials | pending=1 | recovery=configure model credentials before retrying live execution | next={SAFE_CREDENTIALS_HINT}"
    assert "sk-" not in output


def test_main_prints_setup_one_line(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def setup(self, *, pending_only: bool = False, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "shell_view": "setup_one_line",
                "summary_line": "setup-summary: inspect-only: missing runtime | pending=1 | recovery=restore runtime availability before retrying live execution | next=curl -fsS http://127.0.0.1:3101/health",
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "setup", "--repo-root", "/tmp/repo", "--one-line"])

    exit_code = cli.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 0
    assert output == "setup-summary: inspect-only: missing runtime | pending=1 | recovery=restore runtime availability before retrying live execution | next=curl -fsS http://127.0.0.1:3101/health"


def test_main_prints_ready_surface(monkeypatch, capsys) -> None:
    class StubWorkbench:
        repo_root = "/tmp/repo"

        def setup(self):
            return {
                "repo_root": "/tmp/repo",
                "pending_count": 3,
                "pending_items": [
                    {"name": "bootstrap_initialized", "command_hint": "aionis init --repo-root /tmp/repo"},
                    {"name": "credentials_configured", "command_hint": SAFE_CREDENTIALS_HINT},
                ],
                "live_ready_summary": "inspect-only: missing credentials + runtime",
                "mode": "inspect-only",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "recovery_summary": "configure model credentials and restore runtime availability before retrying live execution",
            }

        def doctor(self):
            return {
                "repo_root": "/tmp/repo",
                "live_ready": False,
                "live_ready_summary": "inspect-only: missing credentials + runtime",
                "mode": "inspect-only",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "checks": [
                    {"name": "repo_root", "status": "available"},
                    {"name": "bootstrap", "status": "missing"},
                    {"name": "execution_host", "status": "offline"},
                    {"name": "runtime_host", "status": "degraded"},
                ],
                "setup_checklist": [
                    {"name": "bootstrap_initialized", "status": "pending", "command_hint": "aionis init --repo-root /tmp/repo"},
                    {"name": "credentials_configured", "status": "pending", "command_hint": SAFE_CREDENTIALS_HINT},
                    {"name": "runtime_available", "status": "pending", "command_hint": "curl -fsS http://127.0.0.1:3101/health"},
                ],
                "recovery_summary": "configure model credentials and restore runtime availability before retrying live execution",
            }

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {"name": "deepagents_local_shell"},
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "ready", "--repo-root", "/tmp/repo"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "ready: inspect-only: missing credentials + runtime live_ready=False" in output
    assert "first=aionis init --repo-root /tmp/repo" in output
    assert f"then={SAFE_CREDENTIALS_HINT}" in output
    assert "launch=aionis --repo-root /tmp/repo" in output


def test_main_prints_live_profile_surface(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def live_profile(self):
            return {
                "shell_view": "live_profile",
                "provider_id": "zai_glm51_coding",
                "provider_label": "Z.AI GLM-5.1 Coding",
                "release_tier": "manual_verified",
                "supports_live": True,
                "model": "glm-5.1",
                "timeout_seconds": 15,
                "max_completion_tokens": 256,
                "live_mode": "targeted_fix",
                "latest_recorded_at": "2026-04-04T10:00:00Z",
                "latest_scenario_id": "live-resume-complete",
                "latest_ready_duration_seconds": 3.25,
                "latest_run_duration_seconds": 57.66,
                "latest_resume_duration_seconds": 106.87,
                "latest_total_duration_seconds": 167.78,
                "latest_timing_summary": "task=click-live-1 ready=3.250s run=57.660s resume=106.870s total=167.780s",
                "latest_snapshot": {"version": "aionis_live_profile_v1"},
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "live-profile", "--repo-root", "/tmp/repo"])

    exit_code = cli.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 0
    assert "live-profile: provider=zai_glm51_coding mode=targeted_fix model=glm-5.1" in output
    assert "budget=timeout:15s max_tokens:256 live=True tier=manual_verified" in output
    assert "latest=live-resume-complete ready=3.250s run=57.660s resume=106.870s total=167.780s at=2026-04-04T10:00:00Z" in output


def test_main_prints_ab_test_compare_surface(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def ab_test_compare(self, **_: object):
            return {
                "shell_view": "ab_test_compare",
                "task_id": "task-123",
                "scenario_id": "scenario-1",
                "benchmark_summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
                "baseline": {
                    "ended_in": "escalate",
                    "total_duration_seconds": 120.5,
                    "retry_count": 1,
                    "replan_depth": 0,
                    "final_execution_gate": "qa_failed",
                    "latest_convergence_signal": "baseline:needs_qa->qa_failed@qa:failed",
                },
                "aionis": {
                    "ended_in": "advance",
                    "total_duration_seconds": 150.0,
                    "retry_count": 1,
                    "replan_depth": 2,
                    "final_execution_gate": "ready",
                    "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
                },
                "comparison": {
                    "winner": "aionis",
                    "duration_delta_seconds": 29.5,
                    "retry_delta": 0,
                    "replan_delta": 2,
                },
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "ab-test",
            "--repo-root",
            "/tmp/repo",
            "compare",
            "--task-id",
            "task-123",
            "--scenario-id",
            "scenario-1",
            "--baseline-ended-in",
            "escalate",
        ],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 0
    assert "ab-test: scenario-1 task=task-123 winner=aionis" in output


def test_main_prints_dream_surface(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def dream(self, *, limit: int = 48, family_limit: int = 8, status_filter: str | None = None):
            return {
                "shell_view": "dream",
                "dream_status_filter": status_filter or "all",
                "dream_summary": {
                    "seed_ready_count": 1,
                    "trial_count": 2,
                    "candidate_count": 1,
                    "deprecated_count": 0,
                },
                "dream_promotion_count": 2,
                "dream_candidate_count": 1,
                "dream_promotions": [
                    {
                        "task_family": "task:termui",
                        "promotion_status": "trial",
                        "confidence": 0.74,
                        "dominant_source_doc_id": "workflow-001",
                        "dominant_doc_action": "resume",
                        "dominant_selected_tool": "read",
                        "promotion_reason": "candidate has enough support to enter trial but is not yet seed-ready",
                    }
                ],
                "dream_candidates": [
                    {
                        "task_family": "task:termui",
                        "strategy_profile": "interactive_reuse_loop",
                        "sample_count": 3,
                    }
                ],
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "dream", "--repo-root", "/tmp/repo", "--status", "trial"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "dream-detail: seed_ready=1 trial=2 candidate=1 deprecated=0" in output
    assert "filter=trial promotions=2 candidates=1" in output
    assert "top_docs=task:termui:workflow-001:resume:read" in output
    assert "reasons=task:termui:trial:candidate has enough support to enter trial but is not yet seed-ready" in output


def test_main_prints_app_show_surface(monkeypatch, capsys) -> None:
    controller_action_bar = {
        "task_id": "task-123",
        "status": "active",
        "recommended_command": "/next task-123",
        "allowed_commands": ["/next task-123", "/show task-123", "/session task-123"],
    }

    class StubWorkbench:
        def app_show(self, *, task_id: str):
            assert task_id == "task-123"
            return {
                "shell_view": "app_show",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 3,
                        },
                        "active_sprint_contract": {
                            "sprint_id": "sprint-1",
                            "approved": True,
                        },
                        "latest_sprint_evaluation": {
                            "status": "failed",
                            "summary": "Palette persistence still fails.",
                            "evaluator_mode": "contract_driven",
                            "failing_criteria": ["functionality"],
                        },
                        "latest_negotiation_round": {
                            "recommended_action": "revise_current_sprint",
                            "objections": ["Resolve failing criterion: functionality."],
                        },
                        "evaluator_criteria_count": 2,
                        "loop_status": "needs_revision",
                    }
                },
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "app", "--repo-root", "/tmp/repo", "show", "--task-id", "task-123"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "app_show: task-123 title=Pixel Forge sprint=sprint-1 status=failed loop=needs_revision" in output
    assert "planner=deterministic type=full_stack_app features=3 groups=none criteria=2 proposed_by=unknown approved=true next=none evaluator=contract_driven failing=functionality negotiation=revise_current_sprint objections=Resolve failing criterion: functionality. revision=none execution=none@none/none artifact=none@none execution_count=0 current_execution_count=0 stage=base replan=0@none exec_ready=false exec_gate=no_execution gate_flow=none@none retry=0/0 retry_available=false retry_remaining=0 next_ready=false next_candidate=none action=none rationale=0 negotiation_notes=0 summary=Palette persistence still fails." in output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in output


def test_render_result_payload_includes_execution_failure_reason() -> None:
    payload = {
        "shell_view": "app_show",
        "task_id": "task-123",
        "canonical_views": {
            "app_harness": {
                "product_spec": {
                    "title": "Modern Landing Page",
                    "app_type": "full_stack_app",
                    "feature_count": 3,
                    "feature_groups": [],
                },
                "active_sprint_contract": {
                    "sprint_id": "sprint-1",
                    "approved": True,
                },
                "latest_sprint_evaluation": {
                    "status": "unknown",
                    "summary": "no evaluator summary",
                    "evaluator_mode": "unknown",
                },
                "planner_mode": "deterministic",
                "evaluator_criteria_count": 0,
                "latest_execution_attempt": {
                    "attempt_id": "sprint-1-attempt-1",
                    "execution_mode": "live",
                    "execution_target_kind": "sprint",
                    "artifact_kind": "workspace_app",
                    "artifact_path": "index.html",
                    "failure_reason": "Error code: 429 - rate limit reached",
                    "failure_class": "provider_transient_error",
                    "trace_path": "/tmp/task-123/.aionis-delivery-trace.json",
                },
                "loop_status": "execution_recorded",
                "execution_history_count": 1,
                "current_sprint_execution_count": 1,
                "policy_stage": "base",
                "replan_depth": 0,
                "replan_root_sprint_id": "sprint-1",
                "execution_outcome_ready": False,
                "execution_gate": "needs_qa",
                "last_execution_gate_transition": "no_execution->needs_qa",
                "last_policy_action": "generate:live",
                "retry_count": 0,
                "retry_budget": 1,
                "retry_available": False,
                "retry_remaining": 1,
                "next_sprint_ready": False,
                "next_sprint_candidate_id": "none",
                "recommended_next_action": "none",
                "planning_rationale": [],
                "sprint_negotiation_notes": [],
            }
        },
    }

    rendered = _render_result_payload(payload)

    assert any("failure=Error code: 429 - rate limit reached" in line for line in rendered)
    assert any("failure_class=provider_transient_error" in line for line in rendered)
    assert any("trace=/tmp/task-123/.aionis-delivery-trace.json" in line for line in rendered)


def test_render_result_payload_includes_first_turn_stall_failure_class_for_app_ship() -> None:
    payload = {
        "shell_view": "app_ship",
        "task_id": "task-ship-1",
        "status": "failed",
        "phase": "generate",
        "active_sprint_id": "sprint-1",
        "route_summary": "task_intake->context_scan->plan->sprint->generate",
        "context_summary": "repo=/tmp/repo",
        "entrypoint": "none",
        "preview_command": "none",
        "validation_summary": "none",
        "failure_reason": "Delivery failed after 3/3 first-response timeouts. Last error: provider_first_turn_stall: Delivery agent did not produce a first model/tool step within 60 seconds.",
        "failure_class": "provider_first_turn_stall",
        "live_provider_id": "openrouter_default",
        "live_model": "z-ai/glm-5.1",
    }

    rendered = _render_result_payload(payload)

    assert any("failure_class=provider_first_turn_stall" in line for line in rendered)


def test_main_prints_app_plan_sprint_and_qa_surfaces(monkeypatch, capsys) -> None:
    controller_action_bar = {
        "task_id": "task-123",
        "status": "active",
        "recommended_command": "/next task-123",
        "allowed_commands": ["/next task-123", "/show task-123", "/session task-123"],
    }

    class StubWorkbench:
        def app_plan(
            self,
            *,
            task_id: str,
            prompt: str,
            title: str = "",
            app_type: str = "",
            stack: list[str] | None = None,
            features: list[str] | None = None,
            design_direction: str = "",
            criteria: list[str] | None = None,
            use_live_planner: bool = False,
        ):
            assert task_id == "task-123"
            assert prompt == "Build a pixel editor."
            assert title == "Pixel Forge"
            assert app_type == "full_stack_app"
            assert stack == ["React"]
            assert features == ["canvas"]
            assert criteria == ["functionality:0.8"]
            assert use_live_planner is False
            return {
                "shell_view": "app_plan",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "planner_mode": "deterministic",
                        "active_sprint_contract": {"sprint_id": "", "approved": False},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": [],
                        "latest_sprint_evaluation": {"status": "", "summary": ""},
                        "evaluator_criteria_count": 1,
                        "loop_status": "planned",
                    }
                },
            }

        def app_sprint(
            self,
            *,
            task_id: str,
            sprint_id: str,
            goal: str,
            scope: list[str] | None = None,
            acceptance_checks: list[str] | None = None,
            done_definition: list[str] | None = None,
            proposed_by: str = "",
            approved: bool = False,
        ):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert goal == "Ship the editor shell."
            assert scope == ["shell"]
            assert acceptance_checks == ["pytest tests/test_editor.py -q"]
            assert approved is True
            return {
                "shell_view": "app_sprint",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": [],
                        "latest_sprint_evaluation": {"status": "", "summary": ""},
                        "evaluator_criteria_count": 1,
                        "loop_status": "in_sprint",
                    }
                },
            }

        def app_qa(
            self,
            *,
            task_id: str,
            sprint_id: str,
            status: str,
            summary: str = "",
            scores: list[str] | None = None,
            blocker_notes: list[str] | None = None,
            use_live_evaluator: bool = False,
        ):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert status == "failed"
            assert summary == "Palette persistence still fails."
            assert scores == ["functionality=0.61"]
            assert blocker_notes == ["palette resets on refresh"]
            assert use_live_evaluator is False
            return {
                "shell_view": "app_qa",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": [],
                        "latest_sprint_evaluation": {
                            "status": "failed",
                            "summary": "Palette persistence still fails.",
                            "evaluator_mode": "contract_driven",
                            "failing_criteria": ["functionality"],
                        },
                        "evaluator_criteria_count": 1,
                        "loop_status": "needs_revision",
                    }
                },
            }

        def app_negotiate(
            self,
            *,
            task_id: str,
            sprint_id: str = "",
            objections: list[str] | None = None,
            use_live_planner: bool = False,
        ):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert objections == ["timeline entries reset on refresh"]
            assert use_live_planner is False
            return {
                "shell_view": "app_negotiate",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": ["Keep sprint-1 narrow until the evaluator objections are cleared."],
                        "latest_negotiation_round": {
                            "planner_mode": "deterministic",
                            "recommended_action": "revise_current_sprint",
                            "objections": [
                                "Resolve failing criterion: functionality.",
                                "timeline entries reset on refresh",
                            ],
                        },
                        "latest_sprint_evaluation": {
                            "status": "failed",
                            "summary": "Palette persistence still fails.",
                            "evaluator_mode": "contract_driven",
                            "failing_criteria": ["functionality"],
                        },
                        "evaluator_criteria_count": 1,
                        "loop_status": "negotiation_pending",
                    }
                },
            }

        def app_generate(
            self,
            *,
            task_id: str,
            sprint_id: str = "",
            execution_summary: str = "",
            changed_target_hints: list[str] | None = None,
            use_live_generator: bool = False,
        ):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert execution_summary == "Apply the narrowed persistence fix before re-running QA."
            assert changed_target_hints == ["src/editor.tsx"]
            assert use_live_generator is False
            return {
                "shell_view": "app_generate",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": [],
                        "latest_sprint_evaluation": {},
                        "latest_revision": {
                            "revision_id": "sprint-1-revision-1",
                        },
                        "latest_execution_attempt": {
                            "attempt_id": "sprint-1-attempt-1",
                            "execution_mode": "live" if use_live_generator else "deterministic",
                            "execution_target_kind": "revision",
                            "artifact_kind": "static_html_demo",
                            "artifact_path": ".aionis-workbench/artifacts/task-123/sprint-1-attempt-1/index.html",
                        },
                        "execution_history_count": 1,
                        "current_sprint_execution_count": 1,
                        "policy_stage": "base",
                        "execution_outcome_ready": False,
                        "execution_gate": "needs_qa",
                        "last_execution_gate_transition": "no_execution->needs_qa",
                        "last_policy_action": "generate:deterministic",
                        "retry_budget": 1,
                        "retry_count": 1,
                        "evaluator_criteria_count": 1,
                        "loop_status": "execution_recorded",
                    }
                },
            }

        def app_retry(
            self,
            *,
            task_id: str,
            sprint_id: str = "",
            revision_notes: list[str] | None = None,
            use_live_planner: bool = False,
        ):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert revision_notes == ["fix timeline persistence"]
            assert use_live_planner is False
            return {
                "shell_view": "app_retry",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": ["Keep sprint-1 narrow until the evaluator objections are cleared."],
                        "latest_negotiation_round": {
                            "planner_mode": "deterministic",
                            "recommended_action": "revise_current_sprint",
                            "objections": [
                                "Resolve failing criterion: functionality.",
                                "timeline entries reset on refresh",
                            ],
                        },
                        "latest_sprint_evaluation": {
                            "status": "failed",
                            "summary": "Palette persistence still fails.",
                            "evaluator_mode": "contract_driven",
                            "failing_criteria": ["functionality"],
                        },
                        "latest_revision": {
                            "revision_id": "sprint-1-revision-1",
                        },
                        "replan_depth": 0,
                        "replan_root_sprint_id": "",
                        "policy_stage": "base",
                        "execution_outcome_ready": False,
                        "execution_gate": "no_execution",
                        "last_execution_gate_transition": "qa_failed->qa_failed",
                        "last_policy_action": "qa:failed",
                        "retry_budget": 1,
                        "retry_count": 1,
                        "evaluator_criteria_count": 1,
                        "loop_status": "revision_recorded",
                    }
                },
            }

        def app_advance(self, *, task_id: str, sprint_id: str = ""):
            assert task_id == "task-123"
            assert sprint_id == "sprint-2"
            return {
                "shell_view": "app_advance",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-2", "approved": False},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": [],
                        "latest_sprint_evaluation": {},
                        "latest_revision": {},
                        "replan_depth": 0,
                        "replan_root_sprint_id": "",
                        "policy_stage": "base",
                        "execution_outcome_ready": False,
                        "execution_gate": "no_execution",
                        "last_execution_gate_transition": "ready->no_execution",
                        "last_policy_action": "advance",
                        "retry_budget": 1,
                        "retry_count": 1,
                        "retry_available": False,
                        "retry_remaining": 0,
                        "next_sprint_ready": False,
                        "next_sprint_candidate_id": "",
                        "recommended_next_action": "",
                        "evaluator_criteria_count": 1,
                        "loop_status": "in_sprint",
                    }
                },
            }

        def app_replan(self, *, task_id: str, sprint_id: str = "", note: str = "", use_live_planner: bool = False):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert note == "narrow the sprint around persistence"
            assert use_live_planner is False
            return {
                "shell_view": "app_replan",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1-replan-1", "approved": False},
                        "planned_sprint_contracts": [{"sprint_id": "sprint-2"}],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": ["narrow the sprint around persistence"],
                        "latest_sprint_evaluation": {},
                        "latest_revision": {},
                        "replan_depth": 1,
                        "replan_root_sprint_id": "sprint-1",
                        "policy_stage": "replanned",
                        "execution_outcome_ready": False,
                        "execution_gate": "no_execution",
                        "last_execution_gate_transition": "qa_failed->no_execution",
                        "last_policy_action": "replan",
                        "retry_budget": 1,
                        "retry_count": 0,
                        "retry_available": False,
                        "retry_remaining": 1,
                        "next_sprint_ready": False,
                        "next_sprint_candidate_id": "",
                        "recommended_next_action": "run_current_sprint",
                        "evaluator_criteria_count": 1,
                        "loop_status": "sprint_replanned",
                    }
                },
            }

        def app_escalate(self, *, task_id: str, sprint_id: str = "", note: str = ""):
            assert task_id == "task-123"
            assert sprint_id == "sprint-2"
            assert note == "retry budget exhausted"
            return {
                "shell_view": "app_escalate",
                "task_id": task_id,
                "controller_action_bar": controller_action_bar,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": ["retry budget exhausted"],
                        "latest_sprint_evaluation": {
                            "status": "failed",
                            "summary": "Palette persistence still fails.",
                            "evaluator_mode": "contract_driven",
                            "failing_criteria": ["functionality"],
                        },
                        "retry_budget": 1,
                        "retry_count": 1,
                        "policy_stage": "base",
                        "execution_outcome_ready": False,
                        "execution_gate": "no_execution",
                        "last_execution_gate_transition": "qa_failed->qa_failed",
                        "last_policy_action": "escalate",
                        "retry_available": False,
                        "retry_remaining": 0,
                        "next_sprint_ready": False,
                        "next_sprint_candidate_id": "",
                        "recommended_next_action": "replan_or_escalate",
                        "evaluator_criteria_count": 1,
                        "loop_status": "escalated",
                    }
                },
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "plan",
            "--task-id",
            "task-123",
            "--prompt",
            "Build a pixel editor.",
            "--title",
            "Pixel Forge",
            "--type",
            "full_stack_app",
            "--stack",
            "React",
            "--feature",
            "canvas",
            "--criterion",
            "functionality:0.8",
        ],
    )
    assert cli.main() == 0
    plan_output = capsys.readouterr().out
    assert "app_plan: task-123 title=Pixel Forge sprint=none status=unknown loop=planned" in plan_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in plan_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "sprint",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--goal",
            "Ship the editor shell.",
            "--scope",
            "shell",
            "--acceptance-check",
            "pytest tests/test_editor.py -q",
            "--approved",
        ],
    )
    assert cli.main() == 0
    sprint_output = capsys.readouterr().out
    assert "app_sprint: task-123 title=Pixel Forge sprint=sprint-1 status=unknown loop=in_sprint" in sprint_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in sprint_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "qa",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--status",
            "failed",
            "--summary",
            "Palette persistence still fails.",
            "--score",
            "functionality=0.61",
            "--blocker",
            "palette resets on refresh",
        ],
    )
    assert cli.main() == 0
    qa_output = capsys.readouterr().out
    assert "app_qa: task-123 title=Pixel Forge sprint=sprint-1 status=failed loop=needs_revision" in qa_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in qa_output


    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "generate",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--summary",
            "Apply the narrowed persistence fix before re-running QA.",
            "--target",
            "src/editor.tsx",
        ],
    )
    assert cli.main() == 0
    generate_output = capsys.readouterr().out
    assert "app_generate: task-123 title=Pixel Forge sprint=sprint-1 status=unknown loop=execution_recorded" in generate_output
    assert "execution=sprint-1-attempt-1@deterministic/revision artifact=static_html_demo@.aionis-workbench/artifacts/task-123/sprint-1-attempt-1/index.html execution_count=1 current_execution_count=1 stage=base replan=0@none exec_ready=false exec_gate=needs_qa gate_flow=no_execution->needs_qa@generate:deterministic" in generate_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in generate_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "retry",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--revision-note",
            "fix timeline persistence",
        ],
    )
    assert cli.main() == 0
    retry_output = capsys.readouterr().out
    assert "app_retry: task-123 title=Pixel Forge sprint=sprint-1 status=failed loop=revision_recorded" in retry_output
    assert "revision=sprint-1-revision-1 execution=none@none/none artifact=none@none execution_count=0 current_execution_count=0 stage=base replan=0@none exec_ready=false exec_gate=no_execution gate_flow=qa_failed->qa_failed@qa:failed retry=1/1" in retry_output
    assert "retry_available=false retry_remaining=0 next_ready=false next_candidate=none action=none" in retry_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in retry_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "advance",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-2",
        ],
    )
    assert cli.main() == 0
    advance_output = capsys.readouterr().out
    assert "app_advance: task-123 title=Pixel Forge sprint=sprint-2 status=unknown loop=in_sprint" in advance_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in advance_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "replan",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--note",
            "narrow the sprint around persistence",
        ],
    )
    assert cli.main() == 0
    replan_output = capsys.readouterr().out
    assert "app_replan: task-123 title=Pixel Forge sprint=sprint-1-replan-1 status=unknown loop=sprint_replanned" in replan_output
    assert "stage=replanned replan=1@sprint-1 exec_ready=false exec_gate=no_execution gate_flow=qa_failed->no_execution@replan" in replan_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in replan_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "--repo-root",
            "/tmp/repo",
            "escalate",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-2",
            "--note",
            "retry budget exhausted",
        ],
    )
    assert cli.main() == 0
    escalate_output = capsys.readouterr().out
    assert "app_escalate: task-123 title=Pixel Forge sprint=sprint-1 status=failed loop=escalated" in escalate_output
    assert "controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123" in escalate_output


def test_main_prints_live_generate_progress_to_stderr(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def app_generate(
            self,
            *,
            task_id: str,
            sprint_id: str = "",
            execution_summary: str = "",
            changed_target_hints: list[str] | None = None,
            use_live_generator: bool = False,
        ):
            assert task_id == "task-123"
            assert sprint_id == "sprint-1"
            assert use_live_generator is True
            return {
                "shell_view": "app_generate",
                "task_id": task_id,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Pixel Forge",
                            "app_type": "full_stack_app",
                            "feature_count": 1,
                        },
                        "active_sprint_contract": {"sprint_id": "sprint-1", "approved": True},
                        "planned_sprint_contracts": [],
                        "planning_rationale": [],
                        "sprint_negotiation_notes": [],
                        "latest_revision": {},
                        "latest_execution_attempt": {
                            "attempt_id": "sprint-1-attempt-1",
                            "execution_mode": "live",
                            "execution_target_kind": "sprint",
                            "artifact_kind": "workspace_app",
                            "artifact_path": "index.html",
                        },
                        "execution_history_count": 1,
                        "current_sprint_execution_count": 1,
                        "policy_stage": "base",
                        "execution_outcome_ready": False,
                        "execution_gate": "needs_qa",
                        "last_execution_gate_transition": "no_execution->needs_qa",
                        "last_policy_action": "generate:live",
                        "retry_budget": 1,
                        "retry_count": 0,
                        "evaluator_criteria_count": 1,
                        "loop_status": "execution_recorded",
                    }
                },
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root=None: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "generate",
            "--task-id",
            "task-123",
            "--sprint-id",
            "sprint-1",
            "--use-live-generator",
        ],
    )

    assert cli.main() == 0
    captured = capsys.readouterr()
    assert "app_generate running: task_id=task-123 sprint_id=sprint-1 mode=live" in captured.err
    assert "app_generate: task-123" in captured.out


def test_main_prints_app_ship_surface(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def app_ship(
            self,
            *,
            task_id: str,
            prompt: str,
            output_dir: str = "",
            use_live_planner: bool = False,
            use_live_generator: bool = False,
        ):
            assert task_id == "task-123"
            assert prompt == "Build a modern landing page for an AI agent platform."
            assert output_dir == "/tmp/exported-app"
            assert use_live_planner is True
            assert use_live_generator is True
            return {
                "shell_view": "app_ship",
                "task_id": task_id,
                "status": "completed",
                "phase": "complete",
                "route_summary": "task_intake->context_scan->plan->sprint->generate->export",
                "context_summary": "repo=/tmp/repo | top=README.md, src/",
                "active_sprint_id": "sprint-1",
                "entrypoint": "/tmp/exported-app/dist/index.html",
                "preview_command": "cd /tmp/exported-app && npm run dev -- --host 0.0.0.0 --port 4173",
                "validation_summary": "Validation commands passed.",
                "live_provider_id": "zai_glm51_coding",
                "live_model": "glm-5.1",
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root=None: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "app",
            "ship",
            "--task-id",
            "task-123",
            "--prompt",
            "Build a modern landing page for an AI agent platform.",
            "--output-dir",
            "/tmp/exported-app",
            "--use-live-planner",
            "--use-live-generator",
        ],
    )

    assert cli.main() == 0
    captured = capsys.readouterr()
    assert "app_ship running: task_id=task-123 mode=live" in captured.err
    assert "app_ship: task-123 status=completed phase=complete sprint=sprint-1" in captured.out
    assert "provider=zai_glm51_coding/glm-5.1" in captured.out


def test_main_prints_ship_surface(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def ship(
            self,
            *,
            task_id: str,
            task: str,
            target_files: list[str] | None = None,
            validation_commands: list[str] | None = None,
            output_dir: str = "",
            use_live_planner: bool = False,
            use_live_generator: bool = False,
        ):
            assert task_id == "task-123"
            assert task == "Build a modern landing page for an AI agent platform."
            assert target_files == []
            assert validation_commands == []
            assert output_dir == "/tmp/exported-app"
            assert use_live_planner is True
            assert use_live_generator is True
            return {
                "shell_view": "ship",
                "task_id": task_id,
                "ship_mode": "app_delivery",
                "delegated_shell_view": "app_ship",
                "status": "completed",
                "phase": "complete",
                "route_summary": "task_intake->context_scan->plan->sprint->generate->qa->export->advance",
                "route_reason": "explicit output directory requested",
                "context_summary": "repo=/tmp/repo | top=README.md, src/",
                "active_sprint_id": "sprint-1",
                "entrypoint": "/tmp/exported-app/dist/index.html",
                "preview_command": "cd /tmp/exported-app && npm run dev -- --host 0.0.0.0 --port 4173",
                "validation_summary": "Validation commands passed.",
                "live_provider_id": "zai_glm51_coding",
                "live_model": "glm-5.1",
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root=None: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "ship",
            "--task-id",
            "task-123",
            "--task",
            "Build a modern landing page for an AI agent platform.",
            "--output-dir",
            "/tmp/exported-app",
            "--use-live-planner",
            "--use-live-generator",
        ],
    )

    assert cli.main() == 0
    captured = capsys.readouterr()
    assert "ship running: task_id=task-123 mode=live" in captured.err
    assert "ship: task-123 mode=app_delivery delegate=app_ship status=completed phase=complete sprint=sprint-1" in captured.out
    assert "provider=zai_glm51_coding/glm-5.1" in captured.out


def test_main_prints_doc_compile_payload(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doc_compile(self, *, input_path: str, emit: str = "all", strict: bool = False):
            assert input_path == "workflow.aionis.md"
            assert emit == "all"
            assert strict is True
            return {
                "shell_view": "doc_compile",
                "doc_action": "compile",
                "doc_input": input_path,
                "status": "ok",
                "compile_result": {"compile_result_version": "aionis_doc_compile_result_v1"},
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "doc", "--repo-root", "/tmp/repo", "compile", "--input", "workflow.aionis.md", "--strict"],
    )

    exit_code = cli.main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["shell_view"] == "doc_compile"
    assert output["status"] == "ok"


def test_main_prints_doc_resume_payload(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doc_resume(
            self,
            *,
            input_path: str,
            input_kind: str = "recover-result",
            query_text: str | None = None,
            candidates: list[str] | None = None,
            event_source: str | None = None,
            event_origin: str | None = None,
            recorded_at: str | None = None,
        ):
            assert input_path == "recover-result.json"
            assert input_kind == "recover-result"
            assert query_text == "resume workflow"
            assert candidates == ["read", "bash"]
            assert event_source == "vscode_extension"
            assert event_origin == "editor_extension"
            assert recorded_at == "2026-04-03T12:00:00Z"
            return {
                "shell_view": "doc_resume",
                "doc_action": "resume",
                "doc_input": input_path,
                "status": "completed",
                "resume_result": {"selected_tool": "read"},
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "doc",
            "--repo-root",
            "/tmp/repo",
            "resume",
            "--input",
            "recover-result.json",
            "--input-kind",
            "recover-result",
            "--query-text",
            "resume workflow",
            "--candidate",
            "read",
            "--candidate",
            "bash",
            "--event-source",
            "vscode_extension",
            "--event-origin",
            "editor_extension",
            "--recorded-at",
            "2026-04-03T12:00:00Z",
        ],
    )

    exit_code = cli.main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["shell_view"] == "doc_resume"
    assert output["status"] == "completed"


def test_main_prints_doc_event_payload(monkeypatch, capsys, tmp_path) -> None:
    event_path = tmp_path / "editor-event.json"
    event_path.write_text(
        json.dumps(
            {
                "event_version": "aionisdoc_workbench_event_v1",
                "event_source": "cursor_extension",
                "task_id": "task-123",
                "doc_action": "publish",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
                "payload": {
                    "shell_view": "doc_publish",
                    "doc_action": "publish",
                    "doc_input": "flows/workflow.aionis.md",
                    "status": "completed",
                    "publish_result": {"source_doc_id": "workflow-001"},
                },
            }
        ),
        encoding="utf-8",
    )

    class StubWorkbench:
        def doc_event(self, *, task_id: str, event: dict[str, object]):
            assert task_id == "task-123"
            assert event["event_source"] == "cursor_extension"
            return {
                "shell_view": "doc_publish",
                "doc_action": "publish",
                "doc_input": "flows/workflow.aionis.md",
                "status": "completed",
                "event_origin": "editor_extension",
                "task_id": task_id,
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "doc",
            "--repo-root",
            "/tmp/repo",
            "event",
            "--task-id",
            "task-123",
            "--event",
            str(event_path),
        ],
    )

    exit_code = cli.main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["shell_view"] == "doc_publish"
    assert output["event_origin"] == "editor_extension"


def test_main_returns_nonzero_for_failed_doc_payload(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doc_run(self, *, input_path: str, registry_path: str, input_kind: str = "source"):
            return {
                "shell_view": "doc_run",
                "doc_action": "run",
                "doc_input": input_path,
                "status": "failed",
                "run_result": {"status": "failed", "errors": ["module_missing"]},
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aionis",
            "doc",
            "--repo-root",
            "/tmp/repo",
            "run",
            "--input",
            "workflow.aionis.md",
            "--registry",
            "module-registry.json",
        ],
    )

    assert cli.main() == 1


def test_render_result_payload_summarizes_doc_compile() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "doc_compile",
            "doc_action": "compile",
            "doc_input": "workflow.aionis.md",
            "status": "ok",
            "controller_action_bar": {
                "task_id": "task-123",
                "status": "active",
                "recommended_command": "/next task-123",
                "allowed_commands": ["/next task-123", "/show task-123", "/session task-123"],
            },
            "compile_result": {
                "selected_artifact": "plan",
                "summary": {"error_count": 0, "warning_count": 1},
                "diagnostics": [{"severity": "warning"}],
            },
        }
    )

    assert lines[0] == "doc: compile status=ok"
    assert "input=workflow.aionis.md" in lines[1]
    assert "diagnostics=1 errors=0 warnings=1 artifact=plan" in lines[2]
    assert lines[3] == "  controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123"


def test_render_result_payload_summarizes_doc_run() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "doc_run",
            "doc_action": "run",
            "doc_input": "workflow.aionis.md",
            "doc_registry": "module-registry.json",
            "status": "succeeded",
            "run_result": {
                "status": "succeeded",
                "outputs": {"out.hero": "Hero copy"},
            },
        }
    )

    assert lines[0] == "doc: run status=succeeded"
    assert "registry=module-registry.json" in lines[2]
    assert "outputs=1" in lines[3]


def test_main_returns_nonzero_for_blocked_doctor_check(monkeypatch) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "shell_view": "doctor_check",
                "check_name": check,
                "found": True,
                "item": {
                    "name": "runtime_host",
                    "status": "degraded",
                    "reason": "runtime_health_unreachable",
                },
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "doctor", "--repo-root", "/tmp/repo", "--check", "runtime_host"])

    assert cli.main() == 1


def test_main_returns_zero_for_ready_setup_check(monkeypatch) -> None:
    class StubWorkbench:
        def setup(self, *, pending_only: bool = False, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "shell_view": "setup_check",
                "check_name": check,
                "found": True,
                "item": {
                    "name": "bootstrap_initialized",
                    "status": "done",
                    "reason": "bootstrap ready",
                },
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "setup", "--repo-root", "/tmp/repo", "--check", "bootstrap_initialized"])

    assert cli.main() == 0


def test_main_returns_two_for_unknown_setup_check(monkeypatch) -> None:
    class StubWorkbench:
        def setup(self, *, pending_only: bool = False, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "shell_view": "setup_check",
                "check_name": check,
                "found": False,
                "item": {},
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "setup", "--repo-root", "/tmp/repo", "--check", "unknown_check"])

    assert cli.main() == 2


def test_main_returns_host_error_payload_for_run_failure(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def run(self, **kwargs):
            raise RuntimeError("live execution blocked by host preflight")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--task", "fix it"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "run failed: click-1 mode=inspect_only" in output
    assert "recovery=missing_credentials_and_runtime" in output
    assert "now=continue in inspect-only mode via shell -> /work, /review, /validate, or /ingest" in output
    assert "repair=configure model credentials to enable live execution" in output


def test_main_returns_host_error_payload_for_resume_failure(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def resume(self, **kwargs):
            raise RuntimeError("live execution blocked by host preflight")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(sys, "argv", ["aionis", "resume", "--repo-root", "/tmp/repo", "--task-id", "click-1"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "resume failed: click-1 mode=inspect_only" in output
    assert "now=continue in inspect-only mode via shell -> /work, /review, /validate, or /ingest" in output


def test_main_returns_blocked_live_preflight_payload_for_run(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None):
            return {
                "mode": "inspect-only",
                "live_ready": False,
                "live_ready_summary": "inspect-only: missing credentials + runtime",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "recommendations": [
                    "configure model credentials to enable live execution",
                    "start or configure Aionis Runtime via AIONIS_BASE_URL",
                ],
            }

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only"],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "run preflight: click-1 ready=False mode=inspect_only" in output
    assert "now=continue in inspect-only mode via shell -> /work, /review, /validate, or /ingest" in output
    assert "repair=configure model credentials to enable live execution" in output


def test_main_prints_run_preflight_one_line(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "mode": "inspect-only",
                "live_ready": False,
                "live_ready_summary": "inspect-only: missing credentials + runtime",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "setup_checklist": [
                    {
                        "name": "credentials_configured",
                        "status": "pending",
                        "command_hint": SAFE_CREDENTIALS_HINT,
                    }
                ],
                "recommendations": [
                    "configure model credentials to enable live execution",
                ],
            }

        def host_contract(self):
            return {
                "contract": {
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only", "--one-line"],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 1
    assert output == f"run-preflight: click-1 | blocked | inspect-only: missing credentials + runtime | recovery=both model credentials and runtime availability must be restored | hint={SAFE_CREDENTIALS_HINT}"


def test_main_returns_ready_live_preflight_payload_for_resume(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None):
            return {
                "mode": "live",
                "live_ready": True,
                "live_ready_summary": "live-ready",
                "capability_state": "live_ready",
                "capability_summary": "can run live tasks, inspect, validate, and ingest",
                "recommendations": [],
            }

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "available",
                        "health_reason": "",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "resume", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only"],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "resume preflight: click-1 ready=True mode=live_enabled" in output
    assert "recovery=ready" in output
    assert "next=start live execution with `aionis resume ...`" in output


def test_main_prints_resume_preflight_one_line(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "mode": "live",
                "live_ready": True,
                "live_ready_summary": "live-ready",
                "capability_state": "live_ready",
                "capability_summary": "can run live tasks, inspect, validate, and ingest",
                "recommendations": [],
            }

        def host_contract(self):
            return {
                "contract": {
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "available",
                        "health_reason": "",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "resume", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only", "--one-line"],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out.strip()

    assert exit_code == 0
    assert output == "resume-preflight: click-1 | ready | live-ready | recovery=live preflight is green"


def test_main_returns_runtime_degraded_recovery_for_run(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def doctor(self, *, summary: bool = False, check: str | None = None):
            return {
                "mode": "inspect-only",
                "live_ready": False,
                "live_ready_summary": "inspect-only: degraded",
                "capability_state": "inspect_only_degraded",
                "capability_summary": "can inspect, validate, and ingest; live tasks are currently degraded",
                "setup_checklist": [
                    {
                        "name": "runtime_available",
                        "status": "pending",
                        "command_hint": "curl -fsS http://127.0.0.1:3101/health",
                    }
                ],
                "recommendations": ["inspect the runtime health endpoint and restore connectivity"],
            }

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_http_503",
                    },
                }
            }

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only"],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "run preflight: click-1 ready=False mode=live_enabled" in output
    assert "recovery=runtime_degraded hint=curl -fsS http://127.0.0.1:3101/health" in output
    assert "repair=inspect the runtime health endpoint and restore connectivity" in output


def test_main_returns_blocked_live_preflight_when_doctor_cannot_confirm_readiness(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def host_contract(self):
            return {"contract": {}}

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "resume", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--preflight-only"],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "resume preflight: click-1 ready=False" in output


def test_main_returns_nonzero_for_run_result_needing_attention(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def run(self, **kwargs):
            return SimpleNamespace(
                task_id="click-1",
                runner="run",
                content="content",
                session_path="/tmp/repo/.aionis-workbench/sessions/click-1.json",
                session={"status": "needs_attention"},
                canonical_surface={},
                canonical_views={},
                controller_action_bar=None,
                aionis={},
                trace_summary={},
            )

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--task", "fix it"],
    )

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["session"]["status"] == "needs_attention"


def test_main_includes_structured_controller_action_bar_for_run_results(monkeypatch, capsys) -> None:
    class StubWorkbench:
        def run(self, **kwargs):
            return SimpleNamespace(
                task_id="click-1",
                runner="run",
                content="content",
                session_path="/tmp/repo/.aionis-workbench/sessions/click-1.json",
                session={"status": "completed"},
                canonical_surface={},
                canonical_views={
                    "controller": {
                        "status": "completed",
                        "allowed_actions": ["inspect_context"],
                    }
                },
                controller_action_bar={
                    "task_id": "click-1",
                    "status": "completed",
                    "recommended_command": "/show click-1",
                    "allowed_commands": ["/show click-1"],
                },
                aionis={},
                trace_summary={},
            )

    monkeypatch.setattr(cli, "create_workbench", lambda repo_root: StubWorkbench())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aionis", "run", "--repo-root", "/tmp/repo", "--task-id", "click-1", "--task", "fix it"],
    )

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["controller_action_bar"] == {
        "task_id": "click-1",
        "status": "completed",
        "recommended_command": "/show click-1",
        "allowed_commands": ["/show click-1"],
    }


def test_run_shell_help_status_exit_flow() -> None:
    outputs: list[str] = []
    inputs = iter(["/help", "/status", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def inspect_session(self, *, task_id: str):
            return {
                "canonical_views": {
                    "controller": {
                        "status": "paused",
                        "allowed_actions": ["list_events", "inspect_context", "resume"],
                        "blocked_actions": ["record_event", "plan_start", "complete"],
                    }
                }
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {"dashboard_summary": {"session_count": 4}}

    exit_code = run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert exit_code == 0
    assert "Aionis shell" in joined
    assert "Use /help to see available commands." in joined
    assert "interactive_reuse_loop" in joined
    assert "Available commands:" in joined
    assert "Current task controller: latest-task status=paused" in joined
    assert "controller_actions: recommended=/resume latest-task allowed=/resume latest-task | /show latest-task | /session latest-task" in joined
    assert "Exiting Aionis shell." in joined


def test_run_shell_surfaces_controller_action_hints() -> None:
    outputs: list[str] = []
    inputs = iter(["/status", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match | controller:paused[list_events,inspect_context,resume]",
                "controller": {
                    "status": "paused",
                    "allowed_actions": ["list_events", "inspect_context", "resume"],
                    "blocked_actions": ["record_event", "plan_start", "complete"],
                    "last_transition_kind": "paused",
                },
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {"dashboard_summary": {"session_count": 4}}

    exit_code = run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert exit_code == 0
    assert "controller_actions: recommended=/resume latest-task allowed=/resume latest-task | /show latest-task | /session latest-task" in joined


def test_run_shell_prompt_surfaces_primary_controller_action() -> None:
    outputs: list[str] = []
    prompts: list[str] = []
    inputs = iter(["/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match | controller:paused[list_events,inspect_context,resume]",
                "controller": {
                    "status": "paused",
                    "allowed_actions": ["list_events", "inspect_context", "resume"],
                    "blocked_actions": ["record_event", "plan_start", "complete"],
                    "last_transition_kind": "paused",
                },
            }

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    exit_code = run_shell(
        ShellWorkbench(),
        input_fn=fake_input,
        write_fn=outputs.append,
    )

    assert exit_code == 0
    assert prompts[0] == "aionis[latest-task|resume]> "


def test_run_shell_consumes_structured_controller_action_bar() -> None:
    outputs: list[str] = []
    prompts: list[str] = []
    inputs = iter(["/status", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match | controller:paused[list_events,inspect_context,resume]",
                "controller_action_bar": {
                    "task_id": task_id or "latest-task",
                    "status": "paused",
                    "recommended_command": f"/resume {task_id or 'latest-task'}",
                    "allowed_commands": [
                        f"/resume {task_id or 'latest-task'}",
                        f"/show {task_id or 'latest-task'}",
                        f"/session {task_id or 'latest-task'}",
                    ],
                },
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {"dashboard_summary": {"session_count": 4}}

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    exit_code = run_shell(
        ShellWorkbench(),
        input_fn=fake_input,
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert exit_code == 0
    assert prompts[0] == "aionis[latest-task|resume]> "
    assert "controller_actions: recommended=/resume latest-task allowed=/resume latest-task | /show latest-task | /session latest-task" in joined


def test_run_shell_shows_startup_mode_hint_when_doctor_is_available() -> None:
    outputs: list[str] = []
    inputs = iter(["/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def doctor(self):
            return {
                "shell_view": "doctor",
                "mode": "inspect-only",
                "live_ready_summary": "inspect-only: missing credentials",
                "recovery_summary": "configure model credentials before retrying live execution",
                "capability_state": "inspect_only_missing_credentials",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials",
                "setup_checklist": [
                    {
                        "name": "credentials_configured",
                        "status": "pending",
                        "next_step": "configure model credentials for live execution",
                        "command_hint": SAFE_CREDENTIALS_HINT,
                    }
                ],
                "recommendations": [
                    "configure model credentials to enable live execution",
                ],
            }

    exit_code = run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert exit_code == 0
    assert f"mode: inspect-only: missing credentials | state: inspect_only_missing_credentials | capabilities: can inspect, validate, and ingest; live tasks blocked by missing credentials | recovery: configure model credentials before retrying live execution | next: {SAFE_CREDENTIALS_HINT}" in joined


def test_render_result_payload_summarizes_dashboard() -> None:
    lines = _render_result_payload(
        {
            "dashboard_summary": {
                "session_count": 24,
                "family_count": 7,
                "strong_match_count": 19,
                "usable_match_count": 4,
                "weak_match_count": 1,
                "prior_seed_ready_count": 1,
                "prior_seed_blocked_count": 1,
                "blocked_family_recommendations": [
                    {
                        "task_family": "task:completion-shell",
                        "gate": "confidence",
                        "recommendation": "add one more high-trust success path",
                    }
                ],
                "proof_summary": "some families are seed-ready, but blocked priors still need strengthening",
            },
            "background": {"status_line": "completed"},
            "family_rows": [
                {"task_family": "task:termui", "status": "strong_family", "prior_seed_ready": True},
                {"task_family": "task:completion-shell", "status": "strong_family", "prior_seed_ready": False},
            ],
        }
    )
    assert lines[0] == (
        "dashboard: sessions=24 families=7 strong=19 usable=4 weak=1 seed_ready=1 blocked=1 consolidation=completed "
        "top=task:termui:strong_family:ready, task:completion-shell:strong_family:blocked blockers=task:completion-shell:confidence"
    )
    assert lines[1] == "  proof=some families are seed-ready, but blocked priors still need strengthening"


def test_render_result_payload_summarizes_consolidation() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "consolidate",
            "sessions_reviewed": 12,
            "families_reviewed": 3,
            "patterns_merged": 4,
            "patterns_suppressed": 1,
            "continuity_cleaned": 2,
            "artifacts_reviewed": 9,
            "recovery_samples_reviewed": 1,
            "dream_summary": {
                "seed_ready_count": 1,
                "trial_count": 2,
                "candidate_count": 0,
                "deprecated_count": 1,
            },
            "family_rows": [
                {"task_family": "task:termui", "status": "strong_family"},
                {"task_family": "task:testing", "status": "strong_family"},
            ],
            "consolidation_path": "/tmp/repo/.aionis-workbench/consolidation.json",
        }
    )
    assert lines[0] == "dream: sessions=12 families=3 merged=4 suppressed=1 continuity_cleaned=2"
    assert "artifacts=9" in lines[1]
    assert "task:termui:strong_family" in lines[1]
    assert "dream=seed_ready:1 trial:2 candidate:0 deprecated:1" in lines[1]
    assert lines[2] == "  path=/tmp/repo/.aionis-workbench/consolidation.json"


def test_render_result_payload_summarizes_dream_detail() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "dream",
            "dream_status_filter": "trial",
            "dream_summary": {
                "seed_ready_count": 1,
                "trial_count": 2,
                "candidate_count": 1,
                "deprecated_count": 1,
            },
            "dream_promotion_count": 4,
            "dream_candidate_count": 5,
            "dream_promotions": [
                {
                    "task_family": "task:termui",
                    "promotion_status": "seed_ready",
                    "confidence": 0.92,
                    "dominant_source_doc_id": "workflow-001",
                    "dominant_doc_action": "resume",
                    "dominant_selected_tool": "read",
                    "dominant_event_source": "vscode_extension",
                    "editor_sync_count": 3,
                    "latest_recorded_at": "2026-04-03T12:02:00Z",
                    "dominant_reviewer_standard": "strict_review",
                    "dominant_reviewer_pack_source": "continuity",
                    "reviewer_sample_count": 3,
                    "promotion_reason": "candidate passed held-out verification and met seed thresholds",
                },
                {
                    "task_family": "task:testing",
                    "promotion_status": "trial",
                    "confidence": 0.71,
                    "dominant_doc_input": "flows/testing.aionis.md",
                    "dominant_doc_action": "publish",
                    "dominant_event_source": "cursor_extension",
                    "editor_sync_count": 1,
                    "latest_recorded_at": "2026-04-03T12:03:00Z",
                    "dominant_reviewer_standard": "strict_review",
                    "dominant_reviewer_pack_source": "evolution",
                    "reviewer_sample_count": 1,
                    "verification_summary": "candidate has enough support but no held-out slice yet",
                },
            ],
            "dream_candidates": [
                {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "sample_count": 3,
                },
                {
                    "task_family": "task:testing",
                    "strategy_profile": "family_reuse_loop",
                    "sample_count": 2,
                },
            ],
        }
    )
    assert lines[0] == "dream-detail: seed_ready=1 trial=2 candidate=1 deprecated=1"
    assert "filter=trial" in lines[1]
    assert "promotions=4" in lines[1]
    assert "top_promotions=task:termui:seed_ready:0.92" in lines[1]
    assert "top_candidates=task:termui:interactive_reuse_loop:3" in lines[2]
    assert "top_docs=task:termui:workflow-001:resume:read, task:testing:flows/testing.aionis.md:publish:none" in lines[3]
    assert "top_doc_syncs=task:termui:vscode_extension:3:2026-04-03T12:02:00Z, task:testing:cursor_extension:1:2026-04-03T12:03:00Z" in lines[4]
    assert "top_reviewers=task:termui:strict_review:continuity:3, task:testing:strict_review:evolution:1" in lines[5]
    assert "task:termui:seed_ready:candidate passed held-out verification" in lines[6]


def test_render_result_payload_summarizes_live_profile() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "live_profile",
            "provider_id": "zai_glm51_coding",
            "release_tier": "manual_verified",
            "supports_live": True,
            "model": "glm-5.1",
            "timeout_seconds": 15,
            "max_completion_tokens": 256,
            "live_mode": "targeted_fix",
            "latest_recorded_at": "2026-04-04T10:00:00Z",
            "latest_scenario_id": "live-resume-complete",
            "latest_ready_duration_seconds": 3.25,
            "latest_run_duration_seconds": 57.66,
            "latest_resume_duration_seconds": 106.87,
            "latest_total_duration_seconds": 167.78,
            "latest_timing_summary": "task=click-live-1 ready=3.250s run=57.660s resume=106.870s total=167.780s",
            "latest_execution_focus": "Patch the final hydration edge before advancing.",
            "latest_execution_gate": "ready",
            "latest_execution_gate_transition": "needs_qa->ready",
            "latest_execution_outcome_ready": True,
            "latest_last_policy_action": "qa:passed",
            "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            "recent_convergence_signals": [
                "live-app-advance:needs_qa->ready@qa:passed",
                "live-app-escalate:needs_qa->qa_failed@qa:failed",
                "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            ],
        }
    )
    assert lines[0] == "live-profile: provider=zai_glm51_coding mode=targeted_fix model=glm-5.1"
    assert lines[1] == "  budget=timeout:15s max_tokens:256 live=True tier=manual_verified"
    assert lines[2] == "  latest=live-resume-complete ready=3.250s run=57.660s resume=106.870s total=167.780s at=2026-04-04T10:00:00Z"
    assert lines[3] == "  policy=gate:ready flow=needs_qa->ready@qa:passed outcome_ready:true focus=Patch the final hydration edge before advancing."
    assert lines[4] == "  signal=live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed"
    assert lines[5] == "  recent_signals=live-app-advance:needs_qa->ready@qa:passed, live-app-escalate:needs_qa->qa_failed@qa:failed, live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed"


def test_render_result_payload_summarizes_app_export() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "app_export",
            "task_id": "task-123",
            "export_root": "/tmp/dependency-explorer-export",
            "entrypoint": "/tmp/dependency-explorer-export/index.html",
            "preview_command": "cd /tmp/dependency-explorer-export && npm run dev -- --host 0.0.0.0 --port 4173",
            "validation_summary": "Validation commands passed.",
            "changed_files": ["src/App.tsx"],
            "controller_action_bar": {
                "task_id": "task-123",
                "status": "active",
                "recommended_command": "/next task-123",
                "allowed_commands": ["/next task-123", "/show task-123", "/session task-123"],
            },
        }
    )

    assert lines[0] == "app_export: task-123 export_root=/tmp/dependency-explorer-export"
    assert "entrypoint=/tmp/dependency-explorer-export/index.html" in lines[1]
    assert "changed=src/App.tsx" in lines[1]
    assert lines[2] == "  controller_actions: recommended=/next task-123 allowed=/next task-123 | /show task-123 | /session task-123"


def test_render_result_payload_summarizes_ab_test_compare() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "ab_test_compare",
            "task_id": "task-123",
            "scenario_id": "scenario-1",
            "benchmark_summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
            "baseline": {
                "ended_in": "escalate",
                "total_duration_seconds": 120.5,
                "retry_count": 1,
                "replan_depth": 0,
                "final_execution_gate": "qa_failed",
                "latest_convergence_signal": "baseline:needs_qa->qa_failed@qa:failed",
            },
            "aionis": {
                "ended_in": "advance",
                "total_duration_seconds": 150.0,
                "retry_count": 1,
                "replan_depth": 2,
                "final_execution_gate": "ready",
                "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            },
            "comparison": {
                "winner": "aionis",
                "duration_delta_seconds": 29.5,
                "retry_delta": 0,
                "replan_delta": 2,
            },
        }
    )
    assert lines[0] == "ab-test: scenario-1 task=task-123 winner=aionis"
    assert lines[1] == "  baseline=end:escalate duration:120.500s retry:1 replan:0 gate:qa_failed signal=baseline:needs_qa->qa_failed@qa:failed"
    assert lines[2] == "  aionis=end:advance duration:150.000s retry:1 replan:2 gate:ready signal=live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed"
    assert lines[3] == "  delta=duration:29.500s retry:0 replan:2"
    assert lines[4] == "  summary=Aionis converged to advance; baseline escalated before reaching the next sprint."


def test_render_result_payload_summarizes_ab_test_compare() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "ab_test_compare",
            "task_id": "task-123",
            "scenario_id": "scenario-1",
            "benchmark_summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
            "baseline": {
                "ended_in": "escalate",
                "total_duration_seconds": 120.5,
                "retry_count": 1,
                "replan_depth": 0,
                "final_execution_gate": "qa_failed",
                "latest_convergence_signal": "baseline:needs_qa->qa_failed@qa:failed",
            },
            "aionis": {
                "ended_in": "advance",
                "total_duration_seconds": 150.0,
                "retry_count": 1,
                "replan_depth": 2,
                "final_execution_gate": "ready",
                "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            },
            "comparison": {
                "winner": "aionis",
                "duration_delta_seconds": 29.5,
                "retry_delta": 0,
                "replan_delta": 2,
            },
        }
    )
    assert lines[0] == "ab-test: scenario-1 task=task-123 winner=aionis"
    assert lines[1] == "  baseline=end:escalate duration:120.500s retry:1 replan:0 gate:qa_failed signal=baseline:needs_qa->qa_failed@qa:failed"
    assert lines[2] == "  aionis=end:advance duration:150.000s retry:1 replan:2 gate:ready signal=live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed"
    assert lines[3] == "  delta=duration:29.500s retry:0 replan:2"
    assert lines[4] == "  summary=Aionis converged to advance; baseline escalated before reaching the next sprint."


def test_render_result_payload_summarizes_background() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "background",
            "status": "completed",
            "enabled": True,
            "lock_active": False,
            "last_trigger": "backfill",
            "last_reason": None,
            "last_new_session_count": 3,
            "summary": {
                "sessions_reviewed": 12,
                "families_reviewed": 3,
                "patterns_merged": 4,
                "patterns_suppressed": 1,
                "continuity_cleaned": 2,
            },
        }
    )
    assert lines[0] == "background: status=completed enabled=True lock=False"
    assert "trigger=backfill" in lines[1]
    assert "sessions=12" in lines[2]


def test_render_result_payload_summarizes_hosts() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "hosts",
            "recommended_entrypoint": "aionis --repo-root /tmp/repo",
            "contract": {
                "product_shell": {
                    "name": "aionis_cli",
                    "mode": "shell_first",
                    "health_status": "available",
                    "default_workflow": ["/plan", "/work", "/review", "/next", "/fix"],
                    "inspection_commands": ["/show", "/family", "/dashboard", "/background", "/hosts"],
                },
                "learning_engine": {
                    "name": "workbench_engine",
                    "health_status": "available",
                    "cold_start_bootstrap": True,
                    "auto_learning": True,
                    "passive_observation": True,
                    "consolidation": True,
                    "canonical_surfaces": [
                        "execution_packet",
                        "planner_packet",
                        "strategy_summary",
                        "workflow_signal_summary",
                    ],
                },
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "supports_live_tasks": True,
                    "execution_runtime": "deepagents",
                    "backend": "LocalShellBackend",
                    "model_provider": "openrouter",
                    "mode": "live_enabled",
                    "health_status": "available",
                    "health_reason": None,
                    "degraded_reason": None,
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "base_url": "http://127.0.0.1:3101",
                    "bridge_configured": True,
                    "replay_mode": "configured",
                    "health_status": "available",
                    "health_reason": None,
                    "degraded_reason": None,
                },
            },
        }
    )
    assert lines[0] == "hosts: shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell runtime=aionis_runtime_host"
    assert "entrypoint=aionis --repo-root /tmp/repo" in lines[1]
    assert "workflow=/plan, /work, /review, /next, /fix" in lines[2]
    assert lines[4] == "  health=shell:available learning:available execution:available runtime:available"


def test_render_result_payload_summarizes_host_error() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "host_error",
            "operation": "run",
            "task_id": "click-1",
            "error": "runtime unavailable",
            "execution_mode": "inspect_only",
            "recovery_class": "missing_credentials_and_runtime",
            "recovery_summary": "both model credentials and runtime availability must be restored",
            "recovery_command_hint": SAFE_CREDENTIALS_HINT,
            "recommendations": [
                "configure model credentials to enable live execution",
                "continue in inspect-only mode via /plan, /work, /review, /validate, or /ingest",
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "run failed: click-1 mode=inspect_only"
    assert lines[1] == "  error=runtime unavailable"
    assert lines[2] == f"  recovery=missing_credentials_and_runtime hint={SAFE_CREDENTIALS_HINT}"
    assert lines[4] == "  recovery_note=both model credentials and runtime availability must be restored"
    assert lines[5] == "  now=continue in inspect-only mode via /plan, /work, /review, /validate, or /ingest"
    assert lines[6] == (
        "  host_mode=inspect_only execution=offline(model_credentials_missing) "
        "runtime=degraded(runtime_health_unreachable)"
    )
    assert lines[7] == "  repair=configure model credentials to enable live execution"


def test_render_result_payload_summarizes_live_preflight() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "live_preflight",
            "operation": "resume",
            "task_id": "click-1",
            "ready": False,
            "status": "blocked",
            "execution_mode": "inspect_only",
            "execution_health": "offline",
            "runtime_health": "degraded",
            "recovery_class": "missing_credentials_and_runtime",
            "recovery_summary": "both model credentials and runtime availability must be restored",
            "recovery_command_hint": SAFE_CREDENTIALS_HINT,
            "recommendations": [
                "configure model credentials to enable live execution",
                "continue in inspect-only mode via /plan, /work, /review, /validate, or /ingest",
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "resume preflight: click-1 ready=False mode=inspect_only"
    assert lines[1] == "  status=blocked execution=offline runtime=degraded"
    assert lines[2] == f"  recovery=missing_credentials_and_runtime hint={SAFE_CREDENTIALS_HINT}"
    assert lines[4] == "  recovery_note=both model credentials and runtime availability must be restored"
    assert lines[5] == "  now=continue in inspect-only mode via /plan, /work, /review, /validate, or /ingest"
    assert lines[7] == "  repair=configure model credentials to enable live execution"


def test_render_result_payload_distinguishes_runtime_degraded_recovery() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "live_preflight",
            "operation": "run",
            "task_id": "click-1",
            "ready": False,
            "status": "blocked",
            "execution_mode": "live_enabled",
            "execution_health": "available",
            "runtime_health": "degraded",
            "recovery_class": "runtime_degraded",
            "recovery_summary": "runtime is configured but unhealthy; inspect the health endpoint before retrying",
            "recovery_command_hint": "curl -fsS http://127.0.0.1:3101/health",
            "recommendations": [
                "inspect the runtime health endpoint and restore connectivity",
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "live_enabled",
                    "health_status": "available",
                    "health_reason": "",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_http_503",
                },
            },
        }
    )
    assert lines[2] == "  recovery=runtime_degraded hint=curl -fsS http://127.0.0.1:3101/health"
    assert lines[4] == "  recovery_note=runtime is configured but unhealthy; inspect the health endpoint before retrying"
    assert lines[6] == "  repair=inspect the runtime health endpoint and restore connectivity"


def test_render_result_payload_summarizes_doctor() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "doctor",
            "repo_root": "/tmp/repo",
            "mode": "inspect-only",
            "live_ready": False,
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
            "setup_checklist": [
                {
                    "name": "bootstrap_initialized",
                    "status": "pending",
                    "next_step": "initialize bootstrap state for this repo",
                    "command_hint": "aionis init --repo-root /tmp/repo",
                },
                {
                    "name": "credentials_configured",
                    "status": "pending",
                    "next_step": "configure model credentials for live execution",
                    "command_hint": SAFE_CREDENTIALS_HINT,
                },
                {
                    "name": "runtime_available",
                    "status": "pending",
                    "next_step": "start or restore the configured Aionis Runtime",
                    "command_hint": "curl -fsS http://127.0.0.1:3101/health",
                },
            ],
            "checks": [
                {"name": "repo_root", "status": "available"},
                {"name": "bootstrap", "status": "missing"},
                {"name": "execution_host", "status": "offline"},
                {"name": "runtime_host", "status": "degraded"},
            ],
            "recommendations": [
                "run `aionis init --repo-root /tmp/repo` to create bootstrap state",
                "configure model credentials to enable live execution",
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "doctor: inspect-only live_ready=False"
    assert lines[2] == "  state=inspect_only_missing_credentials_and_runtime"
    assert lines[3] == "  capabilities=can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime"
    assert lines[4] == "  checks=repo_root:available, bootstrap:missing, execution_host:offline, runtime_host:degraded"
    assert lines[5] == "  checklist=bootstrap_initialized:pending, credentials_configured:pending, runtime_available:pending"
    assert lines[6] == f"  fixes=bootstrap_initialized->aionis init --repo-root /tmp/repo; credentials_configured->{SAFE_CREDENTIALS_HINT}; runtime_available->curl -fsS http://127.0.0.1:3101/health"
    assert lines[8] == "  now=inspect-only path remains usable via shell -> /work, /review, /validate, or /ingest"
    assert lines[10] == "  recommendation=run `aionis init --repo-root /tmp/repo` to create bootstrap state"


def test_render_result_payload_summarizes_ready() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "ready",
            "repo_root": "/tmp/repo",
            "mode": "inspect-only",
            "live_ready": False,
            "live_ready_summary": "inspect-only: missing credentials + runtime",
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
            "pending_count": 3,
            "pending_items": [
                {"name": "bootstrap_initialized"},
                {"name": "credentials_configured"},
                {"name": "runtime_available"},
            ],
            "checks": [
                {"name": "repo_root", "status": "available"},
                {"name": "bootstrap", "status": "missing"},
                {"name": "execution_host", "status": "offline"},
                {"name": "runtime_host", "status": "degraded"},
            ],
            "recovery_summary": "configure model credentials and restore runtime availability before retrying live execution",
            "next_steps": [
                "aionis init --repo-root /tmp/repo",
                SAFE_CREDENTIALS_HINT,
                "curl -fsS http://127.0.0.1:3101/health",
            ],
            "launch_command": "aionis --repo-root /tmp/repo",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "ready: inspect-only: missing credentials + runtime live_ready=False"
    assert lines[4] == "  pending=3 items=bootstrap_initialized, credentials_configured, runtime_available"
    assert lines[7] == "  now=inspect-only path remains usable via shell -> /work, /review, /validate, or /ingest"
    assert lines[8] == "  recovery=configure model credentials and restore runtime availability before retrying live execution"
    assert lines[9] == "  first=aionis init --repo-root /tmp/repo"
    assert lines[10] == f"  then={SAFE_CREDENTIALS_HINT}"
    assert lines[11] == "  then_after=curl -fsS http://127.0.0.1:3101/health"
    assert lines[12] == "  launch=aionis --repo-root /tmp/repo"


def test_render_result_payload_summarizes_doctor_summary() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "doctor_summary",
            "mode": "inspect-only",
            "live_ready": False,
            "live_ready_summary": "inspect-only: missing credentials + runtime",
            "recovery_summary": "configure model credentials and restore runtime availability before retrying live execution",
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
            "pending_checklist_count": 3,
            "recommendation": "run `aionis init --repo-root /tmp/repo` to create bootstrap state",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "doctor-summary: inspect-only: missing credentials + runtime live_ready=False"
    assert lines[3] == "  pending=3"
    assert lines[5] == "  now=inspect-only path remains usable via shell -> /work, /review, /validate, or /ingest"
    assert lines[6] == "  recovery=configure model credentials and restore runtime availability before retrying live execution"
    assert lines[8] == "  next=run `aionis init --repo-root /tmp/repo` to create bootstrap state"


def test_render_result_payload_summarizes_doctor_one_line() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "doctor_one_line",
            "summary_line": "doctor-summary: inspect-only: missing credentials + runtime | pending=3 | recovery=configure model credentials and restore runtime availability before retrying live execution | next=run `aionis init --repo-root /tmp/repo` to create bootstrap state",
        }
    )
    assert lines[0] == "doctor-summary: inspect-only: missing credentials + runtime | pending=3 | recovery=configure model credentials and restore runtime availability before retrying live execution | next=run `aionis init --repo-root /tmp/repo` to create bootstrap state"


def test_render_result_payload_summarizes_live_preflight_one_line() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "live_preflight_one_line",
            "summary_line": f"run-preflight: click-1 | blocked | inspect-only: missing credentials + runtime | recovery=both model credentials and runtime availability must be restored | hint={SAFE_CREDENTIALS_HINT}",
        }
    )
    assert lines[0] == f"run-preflight: click-1 | blocked | inspect-only: missing credentials + runtime | recovery=both model credentials and runtime availability must be restored | hint={SAFE_CREDENTIALS_HINT}"


def test_render_result_payload_summarizes_doctor_check() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "doctor_check",
            "check_name": "runtime_host",
            "found": True,
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "source": "checks",
            "item": {
                "name": "runtime_host",
                "status": "degraded",
                "reason": "runtime_health_unreachable",
            },
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "doctor-check: runtime_host found=True"
    assert lines[2] == "  source=checks"
    assert lines[3] == "  status=degraded reason=runtime_health_unreachable"


def test_render_result_payload_summarizes_setup() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "setup",
            "repo_root": "/tmp/repo",
            "mode": "inspect-only",
            "live_ready": False,
            "live_ready_summary": "inspect-only: missing credentials + runtime",
            "recovery_summary": "configure model credentials and restore runtime availability before retrying live execution",
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
            "pending_only": True,
            "pending_count": 3,
            "pending_items": [
                {
                    "name": "bootstrap_initialized",
                    "command_hint": "aionis init --repo-root /tmp/repo",
                },
                {
                    "name": "credentials_configured",
                    "command_hint": SAFE_CREDENTIALS_HINT,
                },
            ],
            "next_steps": [
                "aionis init --repo-root /tmp/repo",
                SAFE_CREDENTIALS_HINT,
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "setup: inspect-only: missing credentials + runtime live_ready=False pending=3"
    assert lines[4] == "  view=pending_only"
    assert "bootstrap_initialized->aionis init --repo-root /tmp/repo" in lines[5]
    assert lines[7] == "  now=inspect-only path remains usable via shell -> /work, /review, /validate, or /ingest"
    assert lines[9] == "  next=aionis init --repo-root /tmp/repo"


def test_render_result_payload_summarizes_setup_summary() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "setup_summary",
            "mode": "inspect-only",
            "live_ready": False,
            "live_ready_summary": "inspect-only: missing credentials + runtime",
            "recovery_summary": "configure model credentials and restore runtime availability before retrying live execution",
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
            "pending_count": 3,
            "completed_count": 0,
            "next_step": "aionis init --repo-root /tmp/repo",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "setup-summary: inspect-only: missing credentials + runtime live_ready=False"
    assert lines[3] == "  counts=pending:3 completed:0"
    assert lines[5] == "  now=inspect-only path remains usable via shell -> /work, /review, /validate, or /ingest"
    assert lines[6] == "  recovery=configure model credentials and restore runtime availability before retrying live execution"
    assert lines[7] == "  next=aionis init --repo-root /tmp/repo"


def test_render_result_payload_summarizes_setup_check() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "setup_check",
            "check_name": "bootstrap_initialized",
            "found": True,
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "item": {
                "name": "bootstrap_initialized",
                "status": "pending",
                "reason": "bootstrap missing",
                "command_hint": "aionis init --repo-root /tmp/repo",
            },
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "setup-check: bootstrap_initialized found=True"
    assert lines[2] == "  status=pending reason=bootstrap missing"
    assert lines[3] == "  next=aionis init --repo-root /tmp/repo"


def test_render_result_payload_summarizes_tasks() -> None:
    lines = _render_result_payload(
        {
            "task_count": 2,
            "tasks": [
                {"index": 1, "task_id": "click-2403-ingest-1", "instrumentation_status": "strong_match"},
                {"index": 2, "task_id": "click-2869-ingest-1", "instrumentation_status": "strong_match"},
            ],
        }
    )
    assert lines[0] == "tasks: count=2 top=1) click-2403-ingest-1:strong_match, 2) click-2869-ingest-1:strong_match"


def test_render_result_payload_show_view_is_multiline() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "show",
            "session_path": "/tmp/click-2403-ingest-1.json",
            "controller_action_bar": {
                "task_id": "click-2403-ingest-1",
                "status": "completed",
                "recommended_command": "/show click-2403-ingest-1",
                "allowed_commands": ["/show click-2403-ingest-1"],
            },
            "canonical_views": {
                "task_state": {
                    "task_id": "click-2403-ingest-1",
                    "status": "completed",
                    "validation_ok": True,
                },
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "trust_signal": "same_task_family",
                    "role_sequence": ["implementer", "verifier", "investigator"],
                },
                "planner": {"next_action": "Reuse the interactive family artifacts."},
                "maintenance": {
                    "auto_learning_status": "auto_absorbed",
                    "last_learning_source": "validate",
                    "observed_changed_file_count": 2,
                },
                "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                "instrumentation": {"status": "strong_match"},
                "controller": {
                    "status": "completed",
                    "allowed_actions": ["inspect_context"],
                    "blocked_actions": ["record_event", "pause"],
                    "last_transition_kind": "completed",
                },
            },
        }
    )
    assert lines[0] == "show: click-2403-ingest-1"
    assert "strategy=interactive_reuse_loop" in lines[1]
    assert "instrumentation=strong_match" in lines[2]
    assert "routed_roles=3" in lines[3]
    assert "learning=auto_absorbed" in lines[4]
    assert "observed=2" in lines[4]
    assert "controller=completed allowed=inspect_context blocked=record_event, pause transition=completed" in lines[5]
    assert "controller_actions: recommended=/show click-2403-ingest-1 allowed=/show click-2403-ingest-1" in lines[6]


def test_render_result_payload_session_surface_uses_structured_controller_action_bar() -> None:
    lines = _render_result_payload(
        {
            "session_path": "/tmp/click-2403-ingest-1.json",
            "controller_action_bar": {
                "task_id": "click-2403-ingest-1",
                "status": "paused",
                "recommended_command": "/resume click-2403-ingest-1",
                "allowed_commands": [
                    "/resume click-2403-ingest-1",
                    "/show click-2403-ingest-1",
                    "/session click-2403-ingest-1",
                ],
            },
            "canonical_views": {
                "task_state": {
                    "task_id": "click-2403-ingest-1",
                    "status": "paused",
                    "validation_ok": False,
                },
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "trust_signal": "same_task_family",
                },
                "controller": {
                    "status": "paused",
                    "allowed_actions": ["list_events", "inspect_context", "resume"],
                    "blocked_actions": ["record_event", "plan_start", "complete"],
                    "last_transition_kind": "paused",
                },
            },
        }
    )
    assert lines[0] == "session: click-2403-ingest-1 status=paused family=task:termui strategy=interactive_reuse_loop trust=same_task_family validation=failed"
    assert "controller=paused allowed=list_events, inspect_context, resume blocked=record_event, plan_start, complete transition=paused" in lines[1]
    assert "controller_actions: recommended=/resume click-2403-ingest-1 allowed=/resume click-2403-ingest-1 | /show click-2403-ingest-1 | /session click-2403-ingest-1" in lines[2]


def test_render_result_payload_evaluation_surface_uses_structured_controller_action_bar() -> None:
    lines = _render_result_payload(
        {
            "task_id": "click-2403-ingest-1",
            "controller_action_bar": {
                "task_id": "click-2403-ingest-1",
                "status": "paused",
                "recommended_command": "/resume click-2403-ingest-1",
                "allowed_commands": [
                    "/resume click-2403-ingest-1",
                    "/show click-2403-ingest-1",
                    "/session click-2403-ingest-1",
                ],
            },
            "evaluation": {
                "task_id": "click-2403-ingest-1",
                "status": "in_progress",
                "score": 87.5,
            },
        }
    )
    assert lines[0] == "evaluation: click-2403-ingest-1 in_progress score=87.5"
    assert "controller_actions: recommended=/resume click-2403-ingest-1 allowed=/resume click-2403-ingest-1 | /show click-2403-ingest-1 | /session click-2403-ingest-1" in lines[1]


def test_render_result_payload_summarizes_controller_preflight() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "controller_preflight",
            "task_id": "click-2403-ingest-1",
            "command": "next",
            "controller_status": "paused",
            "required_action": "plan_start",
            "reason": "task session is paused; resume before planning the next start",
            "recommended_command": "/resume click-2403-ingest-1",
            "canonical_views": {
                "controller": {
                    "status": "paused",
                    "allowed_actions": ["list_events", "inspect_context", "resume"],
                    "blocked_actions": ["plan_start", "record_event", "complete"],
                    "last_transition_kind": "paused",
                }
            },
        }
    )
    assert lines[0] == "next controller preflight: click-2403-ingest-1 status=paused required=plan_start"
    assert lines[1] == "  reason=task session is paused; resume before planning the next start"
    assert lines[2] == "  recommended=/resume click-2403-ingest-1"
    assert "controller=paused allowed=list_events, inspect_context, resume blocked=plan_start, record_event, complete transition=paused" in lines[3]


def test_render_result_payload_bootstrap_shows_family_priors() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "plan",
            "bootstrap_snapshot": {
                "bootstrap_focus": ["src/demo.py", "tests/test_demo.py"],
                "bootstrap_working_set": ["src", "tests", "pyproject.toml"],
                "bootstrap_validation_commands": ["PYTHONPATH=src python3 -m pytest -q"],
                "bootstrap_first_step": "Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice.",
                "bootstrap_validation_step": "Run PYTHONPATH=src python3 -m pytest -q before expanding the working set.",
                "bootstrap_reuse_summary": "recent prior: task:termui via interactive_reuse_loop; keep the first task close to PYTHONPATH=src python3 -m pytest tests/test_termui.py -q",
                "recent_commit_subjects": ["Add initial parser tests"],
                "notes": ["Detected source roots: src", "Detected test roots: tests"],
                "recent_family_priors": [
                    {
                        "task_family": "task:termui",
                        "dominant_strategy_profile": "interactive_reuse_loop",
                    }
                ],
            },
            "canonical_views": {
                "task_state": {"status": "bootstrap_ready"},
                "strategy": {
                    "task_family": "task:cold-start",
                    "strategy_profile": "bootstrap_first_loop",
                },
                "planner": {"next_action": "Create one narrow first task."},
                "instrumentation": {"status": "cold_start"},
            },
            "evaluation": {"status": "bootstrap_ready"},
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "plan: bootstrap"
    assert lines[2] == "  focus=src/demo.py, tests/test_demo.py"
    assert lines[3] == "  first_step=Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice."
    assert lines[4] == "  validate_first=Run PYTHONPATH=src python3 -m pytest -q before expanding the working set."
    assert "recent prior: task:termui via interactive_reuse_loop" in lines[5]
    assert "  priors=task:termui:interactive_reuse_loop" in lines
    assert "  hosts=shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell" in lines
    assert "  workflow=/init -> /doctor -> /run -> /work -> /next -> /fix -> /validate" in lines


def test_render_result_payload_family_view_is_multiline() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "family",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "peer_count": 2,
            "peer_summary": {
                "strong_match_count": 2,
                "usable_match_count": 0,
                "weak_match_count": 0,
            },
            "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}],
            "family_row": {
                "status": "strong_family",
                "trend_status": "stable",
                "avg_artifact_hit_rate": 1.0,
            },
            "background": {"status_line": "completed"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "value_summary": "family reuse is available; validate the focused path before widening scope",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=none",
            "prior_seed_summary": "seed-ready prior with confidence 0.91 across 4 samples",
        }
    )
    assert lines[0] == "family: task:termui anchor=click-2403-ingest-1"
    assert "family_status=strong_family" in lines[1]
    assert "artifact_hit_rate=1.0" in lines[2]
    assert lines[3] == "  consolidation=completed"
    assert "family reuse is available" in lines[4]
    assert "seed_ready family=strong_family" in lines[5]
    assert lines[6] == "  prior_strategy=interactive_reuse_loop prior_validation=targeted_first"
    assert lines[7] == "  prior_stats=confidence=0.91 samples=4 recent_success=3"
    assert "prior_seed=ready gate=ready" in lines[8]
    assert "top_peers=click-2869-ingest-1, click-3242-ingest-1" in lines[9]


def test_render_result_payload_family_view_shows_blocked_recommendation() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "family",
            "task_id": "click-3043-ingest-1",
            "task_family": "task:completion-shell",
            "peer_count": 1,
            "peer_summary": {
                "strong_match_count": 0,
                "usable_match_count": 1,
                "weak_match_count": 0,
            },
            "peers": [{"task_id": "click-2184-ingest-1"}],
            "family_row": {
                "status": "stable_family",
                "trend_status": "flat",
                "avg_artifact_hit_rate": 0.6,
            },
            "background": {"status_line": "completed"},
            "family_prior": {
                "dominant_strategy_profile": "completion_family_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.58,
                "sample_count": 2,
                "recent_success_count": 1,
                "seed_ready": False,
                "seed_gate": "confidence",
                "seed_reason": "confidence 0.58 is below the 0.70 seed threshold",
                "seed_recommendation": "add one more high-trust success path, ideally via manual ingest or workflow closure",
                "dream_promotion_reason": "candidate has enough support to enter trial but is not yet seed-ready",
                "family_reviewer_prior": {
                    "dominant_standard": "strict_review",
                    "dominant_required_outputs": ["patch", "tests"],
                    "dominant_acceptance_checks": ["true"],
                    "dominant_pack_source": "continuity",
                    "dominant_selected_tool": "read",
                    "dominant_resume_anchor": "resume:src/termui.py",
                    "sample_count": 2,
                    "ready_required_count": 2,
                    "rollback_required_count": 0,
                    "seed_ready": True,
                },
            },
            "value_summary": "reuse signals exist but the prior is still blocked; add one more high-trust success path, ideally via manual ingest or workflow closure",
            "reuse_summary": "seed_blocked family=stable_family strong=0 usable=1 gate=confidence validation=none",
            "prior_seed_summary": "seed blocked at confidence; add one more high-trust success path, ideally via manual ingest or workflow closure",
        }
    )
    assert "reuse signals exist but the prior is still blocked" in lines[4]
    assert "seed_blocked family=stable_family" in lines[5]
    assert lines[8] == "  prior_seed=blocked gate=confidence reason=confidence 0.58 is below the 0.70 seed threshold"
    assert lines[9] == "  reviewer_prior=strict_review source=continuity outputs=patch|tests checks=true samples=2 seed=ready"
    assert lines[10] == "  reviewer_usage=ready_required:2 rollback_required:0 anchor=resume:src/termui.py tool=read"
    assert lines[11] == "  recommendation=add one more high-trust success path, ideally via manual ingest or workflow closure"
    assert lines[12] == "  dream_reason=candidate has enough support to enter trial but is not yet seed-ready"
    assert "top_peers=click-2184-ingest-1" in lines[13]


def test_render_result_payload_dashboard_shows_blocker_reason() -> None:
    lines = _render_result_payload(
        {
            "dashboard_summary": {
                "session_count": 24,
                "family_count": 7,
                "strong_match_count": 19,
                "usable_match_count": 4,
                "weak_match_count": 1,
                "prior_seed_ready_count": 1,
                "prior_seed_blocked_count": 1,
                "blocked_family_recommendations": [
                    {
                        "task_family": "task:completion-shell",
                        "gate": "confidence",
                        "recommendation": "add one more high-trust success path",
                        "reason": "candidate has enough support to enter trial but is not yet seed-ready",
                    }
                ],
                "proof_summary": "some families are seed-ready, but blocked priors still need strengthening",
            },
            "background": {"status_line": "completed"},
            "family_rows": [
                {"task_family": "task:termui", "status": "strong_family", "prior_seed_ready": True},
                {"task_family": "task:completion-shell", "status": "strong_family", "prior_seed_ready": False},
            ],
        }
    )
    assert lines[1] == "  proof=some families are seed-ready, but blocked priors still need strengthening"
    assert lines[2] == "  blocker_reason=candidate has enough support to enter trial but is not yet seed-ready"


def test_render_result_payload_dashboard_shows_doc_prior_summary() -> None:
    lines = _render_result_payload(
        {
            "dashboard_summary": {
                "session_count": 24,
                "family_count": 7,
                "strong_match_count": 19,
                "usable_match_count": 4,
                "weak_match_count": 1,
                "prior_seed_ready_count": 1,
                "prior_seed_blocked_count": 1,
                "doc_prior_ready_count": 1,
                "doc_prior_blocked_count": 1,
                "doc_editor_sync_family_count": 1,
                "doc_editor_sync_event_count": 2,
                "top_doc_editor_sync_family": "task:docs",
                "top_doc_editor_sync_source": "vscode_extension",
                "top_doc_editor_sync_at": "2026-04-03T12:02:00Z",
                "blocked_family_recommendations": [],
                "proof_summary": "some families are seed-ready, but blocked priors still need strengthening",
            },
            "background": {"status_line": "completed"},
            "family_rows": [
                {
                    "task_family": "task:docs",
                    "status": "strong_family",
                    "prior_seed_ready": True,
                    "prior_doc_sample_count": 2,
                    "prior_doc_source_doc_id": "workflow-001",
                },
                {"task_family": "task:completion-shell", "status": "strong_family", "prior_seed_ready": False},
            ],
        }
    )
    assert lines[1] == "  proof=some families are seed-ready, but blocked priors still need strengthening"
    assert lines[2] == "  doc_priors=1 ready / 1 blocked top=task:docs:workflow-001"
    assert lines[3] == "  editor_syncs=2 across 1 families top=task:docs:vscode_extension at=2026-04-03T12:02:00Z"


def test_render_result_payload_compare_family_summary_includes_consolidation() -> None:
    lines = _render_result_payload(
        {
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "anchor": {"task_id": "click-2403-ingest-1"},
            "peer_count": 2,
            "peer_summary": {
                "strong_match_count": 2,
                "usable_match_count": 0,
                "weak_match_count": 0,
            },
            "background": {"status_line": "completed"},
            "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}],
        }
    )
    assert lines[0] == (
        "compare-family: click-2403-ingest-1 family=task:termui peers=2 "
        "strong=2 usable=0 weak=0 consolidation=completed top=click-2869-ingest-1, click-3242-ingest-1"
    )


def test_render_result_payload_validate_summary() -> None:
    lines = _render_result_payload(
        {
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1"},
            },
        }
    )
    assert lines[0] == "validate: click-2403-ingest-1 ok exit=0 command=pytest tests/test_termui.py -q"


def test_render_result_payload_next_summary() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "next",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1"},
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
        }
    )
    assert lines[0] == "next: click-2403-ingest-1 executed validate"
    assert "reason=Run the first targeted validation command and keep the working set narrow." in lines[1]
    assert "validation=ok exit=0 command=pytest tests/test_termui.py -q" in lines[2]


def test_render_result_payload_next_summary_shows_blocked_prior_recommendation() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "next",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {
                "task_state": {"task_id": "click-3043-ingest-1"},
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Refresh the shell completion loop.",
                "recommendation": "add one more high-trust success path, ideally via manual ingest or workflow closure",
            },
        }
    )
    assert lines[0] == "next: click-3043-ingest-1 executed validate"
    assert lines[2] == "  recommendation=add one more high-trust success path, ideally via manual ingest or workflow closure"
    assert "validation=ok exit=0 command=pytest tests/test_termui.py -q" in lines[3]


def test_render_result_payload_fix_summary() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "fix",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1"},
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
        }
    )
    assert lines[0] == "fix: click-2403-ingest-1 executed validate"
    assert "reason=Run the first targeted validation command and keep the working set narrow." in lines[1]
    assert "validation=ok exit=0 command=pytest tests/test_termui.py -q" in lines[2]


def test_render_result_payload_fix_summary_shows_blocked_prior_recommendation() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "fix",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {
                "task_state": {"task_id": "click-3043-ingest-1"},
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Refresh the shell completion loop.",
                "recommendation": "add one more high-trust success path, ideally via manual ingest or workflow closure",
            },
        }
    )
    assert lines[0] == "fix: click-3043-ingest-1 executed validate"
    assert lines[2] == "  recommendation=add one more high-trust success path, ideally via manual ingest or workflow closure"
    assert "validation=ok exit=0 command=pytest tests/test_termui.py -q" in lines[3]


def test_render_result_payload_plan_summary() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "plan",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                },
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                "reviewer": {
                    "standard": "strict_review",
                    "required_outputs": ["patch", "tests"],
                    "acceptance_checks": ["pytest tests/test_termui.py -q"],
                    "rollback_required": False,
                    "ready_required": True,
                    "resume_anchor": "resume:src/termui.py",
                },
                "review_packs": {
                    "continuity": {
                        "pack_version": "continuity_review_pack_v1",
                        "standard": "strict_review",
                        "selected_tool": "read",
                        "next_action": "Verify the patch against the reviewer contract.",
                    },
                    "evolution": {
                        "pack_version": "evolution_review_pack_v1",
                        "standard": "strict_review",
                        "selected_tool": "edit",
                        "next_action": "Patch the focused file and rerun tests.",
                    },
                },
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
            "next_validation": "pytest tests/test_termui.py -q",
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "plan: click-2403-ingest-1"
    assert "strategy=interactive_reuse_loop" in lines[1]
    assert "next_action=validate" in lines[2]
    assert "validate=pytest tests/test_termui.py -q" in lines[3]
    assert "ready family reuse is available" in lines[4]
    assert "seed_ready family=strong_family" in lines[5]
    assert "family_status=strong_family" in lines[6]
    assert lines[7] == "  prior_strategy=interactive_reuse_loop prior_validation=targeted_first"
    assert lines[8] == "  prior_stats=confidence=0.91 samples=4 recent_success=3"
    assert "prior_seed=ready gate=ready" in lines[9]
    assert "hosts=shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell" in lines[10]
    assert "reviewer=strict_review outputs=patch|tests" in lines[11]
    assert "acceptance=pytest tests/test_termui.py -q" in lines[11]
    assert any("review_packs=continuity:strict_review/read" in line for line in lines)
    assert any("workflow=/plan -> /review -> /fix -> /validate" in line for line in lines)
    assert any("recommended=/review click-2403-ingest-1" in line for line in lines)
    assert any("suggested=/review -> /fix" in line for line in lines)


def test_render_result_payload_plan_shows_blocked_prior_recommendation() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "plan",
            "task_id": "click-3043-ingest-1",
            "task_family": "task:completion-shell",
            "canonical_views": {
                "task_state": {"task_id": "click-3043-ingest-1", "status": "validated"},
                "strategy": {
                    "task_family": "task:completion-shell",
                    "strategy_profile": "completion_family_loop",
                },
                "planner": {"next_action": "Refresh the shell completion loop."},
            },
            "evaluation": {"status": "ready", "score": 88.0},
            "peer_summary": {"strong_match_count": 1, "usable_match_count": 1, "weak_match_count": 0},
            "family_row": {"status": "stable_family", "trend_status": "flat"},
            "family_prior": {
                "dominant_strategy_profile": "completion_family_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.58,
                "sample_count": 2,
                "recent_success_count": 1,
                "seed_ready": False,
                "seed_gate": "confidence",
                "seed_reason": "confidence 0.58 is below the 0.70 seed threshold",
                "seed_recommendation": "add one more high-trust success path, ideally via manual ingest or workflow closure",
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Refresh the shell completion loop.",
                "recommendation": "add one more high-trust success path, ideally via manual ingest or workflow closure",
            },
            "next_validation": "pytest tests/test_shell_completion.py -q",
            "value_summary": "reuse signals exist but the prior is still blocked; add one more high-trust success path, ideally via manual ingest or workflow closure",
            "reuse_summary": "seed_blocked family=stable_family strong=1 usable=1 gate=confidence validation=pytest tests/test_shell_completion.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert "reuse signals exist but the prior is still blocked" in lines[4]
    assert "seed_blocked family=stable_family" in lines[5]
    assert lines[9] == "  prior_seed=blocked gate=confidence reason=confidence 0.58 is below the 0.70 seed threshold"
    assert lines[10] == "  hosts=shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell"
    assert lines[11] == "  workflow=/plan -> /review -> /fix -> /validate"
    assert lines[12] == "  recommendation=add one more high-trust success path, ideally via manual ingest or workflow closure"
    assert lines[13] == "  recommended=/review click-3043-ingest-1"
    assert lines[14] == "  suggested=/review -> /fix"


def test_render_result_payload_plan_shows_host_health_hint_when_degraded() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "plan",
            "task_id": "click-3043-ingest-1",
            "task_family": "task:completion-shell",
            "canonical_views": {
                "task_state": {"task_id": "click-3043-ingest-1", "status": "validated"},
                "strategy": {
                    "task_family": "task:completion-shell",
                    "strategy_profile": "completion_family_loop",
                },
                "planner": {"next_action": "Refresh the shell completion loop."},
            },
            "evaluation": {"status": "ready", "score": 88.0},
            "peer_summary": {"strong_match_count": 1, "usable_match_count": 1, "weak_match_count": 0},
            "family_row": {"status": "stable_family", "trend_status": "flat"},
            "family_prior": {
                "dominant_strategy_profile": "completion_family_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.58,
                "sample_count": 2,
                "recent_success_count": 1,
                "seed_ready": False,
                "seed_gate": "confidence",
                "seed_reason": "confidence 0.58 is below the 0.70 seed threshold",
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Refresh the shell completion loop.",
            },
            "next_validation": "pytest tests/test_shell_completion.py -q",
            "value_summary": "reuse is plausible on this task; validate the focused path to strengthen the family prior",
            "reuse_summary": "seed_blocked family=stable_family strong=1 usable=1 gate=confidence validation=pytest tests/test_shell_completion.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert (
        "  host_mode=inspect_only execution=offline(model_credentials_missing) "
        "runtime=degraded(runtime_health_unreachable)"
    ) in lines
    assert "  workflow=/plan -> /review -> /fix -> /validate" in lines
    assert "  recommended=/review click-3043-ingest-1" in lines
    assert "  suggested=/review -> /fix" in lines


def test_render_result_payload_plan_uses_family_prior_validation_fallback() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "plan",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                },
                "planner": {"next_action": "Reuse the interactive family artifacts."},
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "dominant_validation_command": "pytest tests/test_termui.py -q",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "workflow_next": {
                "action": "show",
                "reason": "Reuse the interactive family artifacts.",
            },
            "next_validation": "pytest tests/test_termui.py -q",
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[3] == "  validate=pytest tests/test_termui.py -q"


def test_render_result_payload_plan_uses_structured_controller_action_bar() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "plan",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "controller_action_bar": {
                "task_id": "click-2403-ingest-1",
                "status": "paused",
                "recommended_command": "/resume click-2403-ingest-1",
                "allowed_commands": [
                    "/resume click-2403-ingest-1",
                    "/show click-2403-ingest-1",
                    "/session click-2403-ingest-1",
                ],
            },
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {"task_family": "task:termui", "strategy_profile": "interactive_reuse_loop"},
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {"dominant_strategy_profile": "interactive_reuse_loop", "dominant_validation_style": "targeted_first"},
            "workflow_next": {"action": "validate", "reason": "Run the first targeted validation command and keep the working set narrow."},
            "next_validation": "pytest tests/test_termui.py -q",
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert any(
        "controller_actions: recommended=/resume click-2403-ingest-1 allowed=/resume click-2403-ingest-1 | /show click-2403-ingest-1 | /session click-2403-ingest-1"
        in line
        for line in lines
    )


def test_render_result_payload_review_shows_auto_learning() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "review",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "validated"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "trust_signal": "same_task_family",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Reuse the interactive family artifacts."},
                "reviewer": {
                    "standard": "strict_review",
                    "required_outputs": ["patch", "tests"],
                    "acceptance_checks": ["pytest tests/test_termui.py -q"],
                    "rollback_required": False,
                    "ready_required": True,
                    "resume_anchor": "resume:src/termui.py",
                },
                "review_packs": {
                    "continuity": {
                        "pack_version": "continuity_review_pack_v1",
                        "standard": "strict_review",
                        "selected_tool": "read",
                        "next_action": "Verify the patch against the reviewer contract.",
                    }
                },
                "maintenance": {
                    "auto_learning_status": "auto_absorbed",
                    "last_learning_source": "validate",
                    "observed_changed_file_count": 3,
                },
                "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                "instrumentation": {"status": "strong_match"},
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "peers": [{"task_id": "click-2869-ingest-1"}],
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "review: click-2403-ingest-1"
    assert "ready family reuse is available" in lines[3]
    assert "seed_ready family=strong_family" in lines[4]
    assert lines[6] == "  prior_strategy=interactive_reuse_loop prior_validation=targeted_first"
    assert lines[7] == "  prior_stats=confidence=0.91 samples=4 recent_success=3"
    assert "prior_seed=ready gate=ready" in lines[8]
    assert "hosts=shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell" in lines[9]
    assert "reviewer=strict_review outputs=patch|tests" in lines[10]
    assert any("review_packs=continuity:strict_review/read" in line for line in lines)
    assert any("learning=auto_absorbed" in line and "source=validate" in line and "observed=3" in line for line in lines)
    assert any("workflow=/review -> /fix -> /validate" in line for line in lines)
    assert any("recommended=/fix click-2403-ingest-1" in line for line in lines)


def test_render_result_payload_review_uses_structured_controller_action_bar() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "review",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "controller_action_bar": {
                "task_id": "click-2403-ingest-1",
                "status": "paused",
                "recommended_command": "/resume click-2403-ingest-1",
                "allowed_commands": [
                    "/resume click-2403-ingest-1",
                    "/show click-2403-ingest-1",
                    "/session click-2403-ingest-1",
                ],
            },
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "validated"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "trust_signal": "same_task_family",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Reuse the interactive family artifacts."},
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {"dominant_strategy_profile": "interactive_reuse_loop", "dominant_validation_style": "targeted_first"},
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert any(
        "controller_actions: recommended=/resume click-2403-ingest-1 allowed=/resume click-2403-ingest-1 | /show click-2403-ingest-1 | /session click-2403-ingest-1"
        in line
        for line in lines
    )


def test_render_result_payload_work_view_is_multiline() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "work",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                "reviewer": {
                    "standard": "strict_review",
                    "required_outputs": ["patch", "tests"],
                    "acceptance_checks": ["pytest tests/test_termui.py -q"],
                    "rollback_required": False,
                    "ready_required": True,
                    "resume_anchor": "resume:src/termui.py",
                },
                "review_packs": {
                    "continuity": {
                        "pack_version": "continuity_review_pack_v1",
                        "standard": "strict_review",
                        "selected_tool": "read",
                        "next_action": "Verify the patch against the reviewer contract.",
                    }
                },
                "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                "instrumentation": {"status": "strong_match"},
            },
            "evaluation": {"score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}],
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "work: click-2403-ingest-1"
    assert "strategy=interactive_reuse_loop" in lines[1]
    assert "validation=pytest tests/test_termui.py -q" in lines[2]
    assert "ready family reuse is available" in lines[3]
    assert "seed_ready family=strong_family" in lines[4]
    assert "family_status=strong_family" in lines[5]
    assert lines[6] == "  prior_strategy=interactive_reuse_loop prior_validation=targeted_first"
    assert lines[7] == "  prior_stats=confidence=0.91 samples=4 recent_success=3"
    assert "prior_seed=ready gate=ready" in lines[8]
    assert "hosts=shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell" in lines[9]
    assert "reviewer=strict_review outputs=patch|tests" in lines[10]
    assert any("review_packs=continuity:strict_review/read" in line for line in lines)
    assert any("instrumentation=strong_match" in line for line in lines)
    assert any("learning=manual_only" in line for line in lines)
    assert any("top_peers=click-2869-ingest-1, click-3242-ingest-1" in line for line in lines)
    assert any("workflow=/work -> /next -> /fix -> /validate" in line for line in lines)
    assert any("recommended=/next click-2403-ingest-1" in line for line in lines)


def test_render_result_payload_work_shows_host_health_hint_when_degraded() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "work",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                "instrumentation": {"status": "strong_match"},
            },
            "evaluation": {"score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "peers": [{"task_id": "click-2869-ingest-1"}],
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[8] == (
        "  host_mode=inspect_only execution=offline(model_credentials_missing) "
        "runtime=degraded(runtime_health_unreachable)"
    )


def test_render_result_payload_work_uses_structured_controller_action_bar() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "work",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "controller_action_bar": {
                "task_id": "click-2403-ingest-1",
                "status": "paused",
                "recommended_command": "/resume click-2403-ingest-1",
                "allowed_commands": [
                    "/resume click-2403-ingest-1",
                    "/show click-2403-ingest-1",
                    "/session click-2403-ingest-1",
                ],
            },
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
            },
            "evaluation": {"score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {"dominant_strategy_profile": "interactive_reuse_loop", "dominant_validation_style": "targeted_first"},
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert any(
        "controller_actions: recommended=/resume click-2403-ingest-1 allowed=/resume click-2403-ingest-1 | /show click-2403-ingest-1 | /session click-2403-ingest-1"
        in line
        for line in lines
    )


def test_render_result_payload_review_view_is_multiline() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "review",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "trust_signal": "same_task_family",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                "instrumentation": {"status": "strong_match"},
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}],
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "deepagents_local_shell"},
            },
        }
    )
    assert lines[0] == "review: click-2403-ingest-1"
    assert "strategy=interactive_reuse_loop" in lines[1]
    assert "evaluation=ready score=100.0" in lines[2]
    assert "ready family reuse is available" in lines[3]
    assert "seed_ready family=strong_family" in lines[4]
    assert "family_status=strong_family" in lines[5]
    assert lines[6] == "  prior_strategy=interactive_reuse_loop prior_validation=targeted_first"
    assert lines[7] == "  prior_stats=confidence=0.91 samples=4 recent_success=3"
    assert "prior_seed=ready gate=ready" in lines[8]
    assert "hosts=shell=aionis_cli learning=workbench_engine execution=deepagents_local_shell" in lines[9]
    assert "instrumentation=strong_match" in lines[10]
    assert "learning=manual_only" in lines[11]
    assert "top_peers=click-2869-ingest-1, click-3242-ingest-1" in lines[12]
    assert "workflow=/review -> /fix -> /validate" in lines[13]
    assert "recommended=/fix click-2403-ingest-1" in lines[14]


def test_render_result_payload_review_shows_host_health_hint_when_degraded() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "review",
            "task_id": "click-2403-ingest-1",
            "task_family": "task:termui",
            "canonical_views": {
                "task_state": {"task_id": "click-2403-ingest-1", "status": "ingested"},
                "strategy": {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "trust_signal": "same_task_family",
                    "validation_paths": ["pytest tests/test_termui.py -q"],
                },
                "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                "instrumentation": {"status": "strong_match"},
            },
            "evaluation": {"status": "ready", "score": 100.0},
            "peer_summary": {"strong_match_count": 2, "usable_match_count": 0, "weak_match_count": 0},
            "peers": [{"task_id": "click-2869-ingest-1"}],
            "family_row": {"status": "strong_family", "trend_status": "stable"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
                "confidence": 0.91,
                "sample_count": 4,
                "recent_success_count": 3,
                "seed_ready": True,
                "seed_gate": "ready",
                "seed_reason": "strong prior from 4 samples, confidence 0.91, recent_success=3",
            },
            "value_summary": "ready family reuse is available with a trusted prior and a focused validation path",
            "reuse_summary": "seed_ready family=strong_family strong=2 usable=0 strategy=interactive_reuse_loop validation=pytest tests/test_termui.py -q",
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[8] == (
        "  host_mode=inspect_only execution=offline(model_credentials_missing) "
        "runtime=degraded(runtime_health_unreachable)"
    )


def test_run_shell_defaults_to_summary_only() -> None:
    outputs: list[str] = []
    inputs = iter(["/dashboard", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {
                "dashboard_summary": {
                    "session_count": 4,
                    "family_count": 2,
                    "strong_match_count": 3,
                    "usable_match_count": 1,
                    "weak_match_count": 0,
                "prior_seed_ready_count": 1,
                "prior_seed_blocked_count": 0,
                "doc_prior_ready_count": 1,
                "doc_prior_blocked_count": 0,
                "doc_editor_sync_family_count": 1,
                "doc_editor_sync_event_count": 2,
                "top_doc_editor_sync_family": "task:termui",
                "top_doc_editor_sync_source": "vscode_extension",
                "top_doc_editor_sync_at": "2026-04-03T12:02:00Z",
                "blocked_family_recommendations": [],
            },
                "background": {"status_line": "completed"},
                "family_rows": [
                    {
                        "task_family": "task:termui",
                        "status": "strong_family",
                        "prior_seed_ready": True,
                        "prior_doc_sample_count": 2,
                        "prior_doc_source_doc_id": "workflow-001",
                        "prior_doc_event_source": "vscode_extension",
                        "prior_doc_recorded_at": "2026-04-03T12:02:00Z",
                        "prior_doc_editor_sync_count": 2,
                    }
                ],
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "dashboard: sessions=4 families=2 strong=3 usable=1 weak=0 seed_ready=1 blocked=0 consolidation=completed top=task:termui:strong_family:ready doc_priors=1/0" in joined
    assert '"dashboard_summary"' not in joined


def test_run_shell_raw_mode_prints_json_details() -> None:
    outputs: list[str] = []
    inputs = iter(["/raw on", "/dashboard", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {
                "dashboard_summary": {
                    "session_count": 4,
                    "family_count": 2,
                    "strong_match_count": 3,
                    "usable_match_count": 1,
                    "weak_match_count": 0,
                },
                "background": {"status_line": "completed"},
                "family_rows": [{"task_family": "task:termui", "status": "strong_family"}],
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "raw mode: on" in joined
    assert '"dashboard_summary"' in joined


def test_run_shell_tracks_current_task_context() -> None:
    outputs: list[str] = []
    prompts: list[str] = []
    inputs = iter(["/status", "/evaluate", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def evaluate_session(self, *, task_id: str):
            return {"evaluation": {"task_id": task_id, "status": "ready", "score": 100.0}}

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    run_shell(
        ShellWorkbench(),
        input_fn=fake_input,
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert prompts[0] == "aionis[latest-task]> "


def test_run_shell_next_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/status", "/next", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def workflow_next(self, *, task_id: str):
            return {
                "shell_view": "next",
                "validation": {
                    "ok": True,
                    "command": "pytest tests/test_termui.py -q",
                    "exit_code": 0,
                },
                "canonical_views": {"task_state": {"task_id": task_id}},
                "workflow_next": {
                    "action": "validate",
                    "reason": "Run the first targeted validation command and keep the working set narrow.",
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "next: latest-task executed validate" in joined


def test_render_result_payload_next_shows_inspect_only_validation_closure() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "next",
            "task_id": "click-2993-ingest-1",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_testing.py -q",
                "exit_code": 0,
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
            "host_contract": {
                "execution_host": {
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "next: click-2993-ingest-1 validated via inspect_only workflow"
    assert lines[2] == (
        "  host_mode=inspect_only execution=offline(model_credentials_missing) "
        "runtime=degraded(runtime_health_unreachable)"
    )


def test_run_shell_fix_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/status", "/fix", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def workflow_fix(self, *, task_id: str):
            return {
                "shell_view": "fix",
                "validation": {
                    "ok": True,
                    "command": "pytest tests/test_termui.py -q",
                    "exit_code": 0,
                },
                "canonical_views": {"task_state": {"task_id": task_id}},
                "workflow_next": {
                    "action": "validate",
                    "reason": "Run the first targeted validation command and keep the working set narrow.",
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "fix: latest-task executed validate" in joined


def test_run_shell_renders_structured_run_error() -> None:
    outputs: list[str] = []
    inputs = iter(['/run click-1 "task"', "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def run(self, **kwargs):
            raise RuntimeError("runtime unavailable")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "run failed: click-1 mode=inspect_only" in joined
    assert "repair=configure model credentials to enable live execution" in joined


def test_render_result_payload_fix_shows_inspect_only_validation_closure() -> None:
    lines = _render_result_payload(
        {
            "shell_view": "fix",
            "task_id": "click-2993-ingest-1",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_testing.py -q",
                "exit_code": 0,
            },
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
            "host_contract": {
                "execution_host": {
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }
    )
    assert lines[0] == "fix: click-2993-ingest-1 validated via inspect_only workflow"
    assert lines[2] == (
        "  host_mode=inspect_only execution=offline(model_credentials_missing) "
        "runtime=degraded(runtime_health_unreachable)"
    )


def test_run_shell_plan_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/status", "/plan", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def inspect_session(self, *, task_id: str):
            return {
                "session_path": f"/tmp/{task_id}.json",
                "canonical_views": {
                    "task_state": {"task_id": task_id, "status": "ingested"},
                    "strategy": {
                        "task_family": "task:termui",
                        "strategy_profile": "interactive_reuse_loop",
                    },
                    "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                },
            }

        def evaluate_session(self, *, task_id: str):
            return {"evaluation": {"task_id": task_id, "status": "ready", "score": 100.0}}

        def compare_family(self, *, task_id: str, limit: int = 6):
            return {
                "task_id": task_id,
                "task_family": "task:termui",
                "peer_count": limit,
                "peer_summary": {
                    "strong_match_count": 2,
                    "usable_match_count": 0,
                    "weak_match_count": 0,
                },
                "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}][:limit],
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {
                "dashboard_summary": {"session_count": 4},
                "family_rows": [
                    {
                        "task_family": "task:termui",
                        "status": "strong_family",
                        "trend_status": "stable",
                    }
                ],
            }

        def workflow_next(self, *, task_id: str):
            return {
                "workflow_next": {
                    "action": "validate",
                    "reason": "Run the first targeted validation command and keep the working set narrow.",
                },
                "validation": {
                    "ok": True,
                    "command": "pytest tests/test_termui.py -q",
                    "exit_code": 0,
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "plan: latest-task" in joined
    assert "workflow=/plan -> /review -> /fix -> /validate" in joined
    assert "recommended=/review latest-task" in joined
    assert "suggested=/review -> /fix" in joined


def test_run_shell_review_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/status", "/review", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            }

        def inspect_session(self, *, task_id: str):
            return {
                "session_path": f"/tmp/{task_id}.json",
                "canonical_views": {
                    "task_state": {"task_id": task_id, "status": "ingested"},
                    "strategy": {
                        "task_family": "task:termui",
                        "strategy_profile": "interactive_reuse_loop",
                        "trust_signal": "same_task_family",
                        "validation_paths": ["pytest tests/test_termui.py -q"],
                    },
                    "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                    "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                    "instrumentation": {"status": "strong_match"},
                },
            }

        def evaluate_session(self, *, task_id: str):
            return {"evaluation": {"task_id": task_id, "status": "ready", "score": 100.0}}

        def compare_family(self, *, task_id: str, limit: int = 6):
            return {
                "task_id": task_id,
                "task_family": "task:termui",
                "peer_count": limit,
                "peer_summary": {
                    "strong_match_count": 2,
                    "usable_match_count": 0,
                    "weak_match_count": 0,
                },
                "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}][:limit],
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 8):
            return {
                "dashboard_summary": {"session_count": 4},
                "family_rows": [
                    {
                        "task_family": "task:termui",
                        "status": "strong_family",
                        "trend_status": "stable",
                    }
                ],
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "review: latest-task" in joined
    assert "evaluation=ready score=100.0" in joined
    assert "workflow=/review -> /fix -> /validate" in joined
    assert "recommended=/fix latest-task" in joined


def test_run_shell_use_and_clear_current_task() -> None:
    outputs: list[str] = []
    prompts: list[str] = []
    inputs = iter(["/use click-2403-ingest-1", "/clear", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": f"project:pallets/click | task:{task_id or 'latest-task'} | interactive_reuse_loop | strong_match",
            }

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    run_shell(
        ShellWorkbench(),
        input_fn=fake_input,
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert prompts[0] == "aionis[latest-task]> "
    assert prompts[1] == "aionis[click-2403-ingest-1]> "
    assert prompts[2] == "aionis> "
    assert "using task: click-2403-ingest-1" in joined
    assert "cleared current task context" in joined


def test_run_shell_latest_sets_current_task() -> None:
    outputs: list[str] = []
    prompts: list[str] = []
    inputs = iter(["/latest", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": f"project:pallets/click | task:{task_id or 'latest-task'} | interactive_reuse_loop | strong_match",
            }

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    run_shell(
        ShellWorkbench(),
        input_fn=fake_input,
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert prompts[0] == "aionis[latest-task]> "
    assert prompts[1] == "aionis[latest-task]> "
    assert "using latest task: latest-task" in joined


def test_run_shell_pick_sets_current_task() -> None:
    outputs: list[str] = []
    prompts: list[str] = []
    inputs = iter(["/pick 2", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": f"project:pallets/click | task:{task_id or 'latest-task'} | interactive_reuse_loop | strong_match",
            }

        def recent_tasks(self, *, limit: int = 8):
            return {
                "task_count": 2,
                "tasks": [
                    {"index": 1, "task_id": "click-2403-ingest-1", "instrumentation_status": "strong_match"},
                    {"index": 2, "task_id": "click-2869-ingest-1", "instrumentation_status": "strong_match"},
                ],
            }

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    run_shell(
        ShellWorkbench(),
        input_fn=fake_input,
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert prompts[0] == "aionis[latest-task]> "
    assert prompts[1] == "aionis[click-2869-ingest-1]> "
    assert "picked task 2: click-2869-ingest-1" in joined


def test_run_shell_show_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/show", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:latest-task | interactive_reuse_loop | strong_match",
            }

        def inspect_session(self, *, task_id: str):
            return {
                "shell_view": "show",
                "session_path": f"/tmp/{task_id}.json",
                "canonical_views": {
                    "task_state": {"task_id": task_id, "status": "completed", "validation_ok": True},
                    "strategy": {
                        "task_family": "task:termui",
                        "strategy_profile": "interactive_reuse_loop",
                        "trust_signal": "same_task_family",
                        "role_sequence": ["implementer", "verifier", "investigator"],
                    },
                    "planner": {"next_action": "Reuse the interactive family artifacts."},
                    "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                    "instrumentation": {"status": "strong_match"},
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "show: latest-task" in joined
    assert "strategy=interactive_reuse_loop" in joined
    assert '"canonical_views"' not in joined


def test_run_shell_doc_show_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/doc show", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:latest-task | interactive_reuse_loop | strong_match",
            }

        def inspect_session(self, *, task_id: str):
            return {
                "shell_view": "doc_show",
                "task_id": task_id,
                "session_path": f"/tmp/{task_id}.json",
                "doc_learning": {
                    "latest_action": "resume",
                    "latest_status": "completed",
                    "source_doc_id": "workflow-001",
                    "handoff_anchor": "doc-anchor-1",
                    "selected_tool": "read",
                    "event_source": "cursor_extension",
                    "recorded_at": "2026-04-03T12:00:00Z",
                    "history": [
                        {"action": "resume"},
                        {"action": "recover"},
                        {"action": "publish"},
                    ],
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "doc_show: latest-task action=resume status=completed doc=workflow-001" in joined
    assert "anchor=doc-anchor-1 tool=read sync=cursor_extension at=2026-04-03T12:00:00Z history=resume -> recover -> publish" in joined


def test_run_shell_app_show_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/app show", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:latest-task | interactive_reuse_loop | strong_match",
            }

        def app_show(self, *, task_id: str):
            return {
                "shell_view": "app_show",
                "task_id": task_id,
                "canonical_views": {
                    "app_harness": {
                        "product_spec": {
                            "title": "Storyboard Forge",
                            "app_type": "desktop_like_web_app",
                            "feature_count": 3,
                        },
                        "active_sprint_contract": {
                            "sprint_id": "sprint-1",
                            "approved": True,
                        },
                        "latest_sprint_evaluation": {
                            "status": "passed",
                            "summary": "Timeline shell and panel editor are stable.",
                        },
                        "evaluator_criteria_count": 1,
                        "loop_status": "ready_for_next_sprint",
                    }
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "app_show: latest-task title=Storyboard Forge sprint=sprint-1 status=passed loop=ready_for_next_sprint" in joined
    assert "planner=deterministic type=desktop_like_web_app features=3 groups=none criteria=1 proposed_by=unknown approved=true next=none evaluator=unknown failing=none negotiation=none objections=none revision=none execution=none@none/none artifact=none@none execution_count=0 current_execution_count=0 stage=base replan=0@none exec_ready=false exec_gate=no_execution gate_flow=none@none retry=0/0 retry_available=false retry_remaining=0 next_ready=false next_candidate=none action=none rationale=0 negotiation_notes=0 summary=Timeline shell and panel editor are stable." in joined


def test_run_shell_doc_list_renders_preview() -> None:
    outputs: list[str] = []
    inputs = iter(["/doc list", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:latest-task | interactive_reuse_loop | strong_match",
            }

        def doc_list(self, *, limit: int = 24):
            return {
                "shell_view": "doc_list",
                "doc_count": 2,
                "docs": [
                    {"path": "flows/workflow.aionis.md", "latest_action": "resume"},
                    {"path": "flows/landing.aionis.md", "latest_action": "publish"},
                ],
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "doc_list: count=2 top=flows/workflow.aionis.md:resume, flows/landing.aionis.md:publish" in joined


def test_run_shell_doc_inspect_renders_summary() -> None:
    outputs: list[str] = []
    inputs = iter(["/doc inspect flows/workflow.aionis.md", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:latest-task | interactive_reuse_loop | strong_match",
            }

        def doc_inspect(self, *, target: str, limit: int = 8):
            return {
                "shell_view": "doc_inspect",
                "controller_action_bar": {
                    "task_id": "latest-task",
                    "status": "active",
                    "recommended_command": "/next latest-task",
                    "allowed_commands": ["/next latest-task", "/show latest-task", "/session latest-task"],
                },
                "inspect_kind": "workflow",
                "resolved_target": target,
                "evidence_count": 1,
                "exists": True,
                "latest_record": {
                    "latest_action": "resume",
                    "latest_status": "completed",
                    "source_doc_id": "workflow-001",
                    "handoff_anchor": "doc-anchor-1",
                    "selected_tool": "read",
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "doc_inspect: workflow target=flows/workflow.aionis.md evidence=1 exists=yes" in joined
    assert "latest=resume/completed doc=workflow-001 anchor=doc-anchor-1 tool=read" in joined
    assert "controller_actions: recommended=/next latest-task allowed=/next latest-task | /show latest-task | /session latest-task" in joined


def test_run_shell_family_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/family", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": "project:pallets/click | task:latest-task | interactive_reuse_loop | strong_match",
            }

        def compare_family(self, *, task_id: str, limit: int = 6):
            return {
                "task_id": task_id,
                "task_family": "task:termui",
                "peer_count": 2,
                "peer_summary": {
                    "strong_match_count": 2,
                    "usable_match_count": 0,
                    "weak_match_count": 0,
                },
                "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}],
                "family_prior": {
                    "dominant_strategy_profile": "interactive_reuse_loop",
                    "dominant_validation_style": "targeted_first",
                    "confidence": 0.82,
                    "sample_count": 3,
                    "recent_success_count": 2,
                    "seed_ready": True,
                    "seed_gate": "ready",
                    "seed_reason": "strong prior",
                    "family_doc_prior": {
                        "dominant_source_doc_id": "workflow-001",
                        "dominant_action": "resume",
                        "dominant_selected_tool": "read",
                        "dominant_event_source": "vscode_extension",
                        "latest_recorded_at": "2026-04-03T12:02:00Z",
                        "editor_sync_count": 2,
                        "sample_count": 2,
                        "seed_ready": True,
                    },
                    "family_reviewer_prior": {
                        "dominant_standard": "strict_review",
                        "dominant_required_outputs": ["patch", "tests"],
                        "dominant_acceptance_checks": ["pytest tests/test_termui.py -q"],
                        "dominant_pack_source": "continuity",
                        "dominant_selected_tool": "read",
                        "dominant_resume_anchor": "resume:src/termui.py",
                        "sample_count": 2,
                        "ready_required_count": 2,
                        "rollback_required_count": 0,
                        "seed_ready": True,
                    },
                },
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 12):
            return {
                "family_rows": [
                    {
                        "task_family": "task:termui",
                        "status": "strong_family",
                        "trend_status": "stable",
                        "avg_artifact_hit_rate": 1.0,
                    }
                ]
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "family: task:termui anchor=latest-task" in joined
    assert "family_status=strong_family" in joined
    assert "doc_prior=workflow-001 action=resume tool=read samples=2 seed=ready" in joined
    assert "doc_sync=vscode_extension count=2 last=2026-04-03T12:02:00Z" in joined
    assert "reviewer_prior=strict_review source=continuity outputs=patch|tests checks=pytest tests/test_termui.py -q samples=2 seed=ready" in joined
    assert "reviewer_usage=ready_required:2 rollback_required:0 anchor=resume:src/termui.py tool=read" in joined


def test_run_shell_validate_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/validate", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": f"project:pallets/click | task:{task_id or 'latest-task'} | interactive_reuse_loop | strong_match",
            }

        def validate_session(self, *, task_id: str):
            return {
                "validation": {
                    "ok": True,
                    "command": "pytest tests/test_termui.py -q",
                    "exit_code": 0,
                },
                "canonical_views": {
                    "task_state": {"task_id": task_id},
                },
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "validate: latest-task ok exit=0 command=pytest tests/test_termui.py -q" in joined


def test_run_shell_work_uses_current_task_context() -> None:
    outputs: list[str] = []
    inputs = iter(["/work", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": task_id or "latest-task",
                "text": f"project:pallets/click | task:{task_id or 'latest-task'} | interactive_reuse_loop | strong_match",
            }

        def inspect_session(self, *, task_id: str):
            return {
                "session_path": f"/tmp/{task_id}.json",
                "canonical_views": {
                    "task_state": {"task_id": task_id, "status": "ingested"},
                    "strategy": {
                        "task_family": "task:termui",
                        "strategy_profile": "interactive_reuse_loop",
                        "validation_paths": ["pytest tests/test_termui.py -q"],
                    },
                    "planner": {"next_action": "Run the first targeted validation command and keep the working set narrow."},
                    "routing": {"summary": {"routed_role_count": 3, "routed_artifact_ref_count": 7}},
                    "instrumentation": {"status": "strong_match"},
                },
                "evaluation": {"score": 100.0},
            }

        def compare_family(self, *, task_id: str, limit: int = 6):
            return {
                "task_id": task_id,
                "task_family": "task:termui",
                "peer_count": 2,
                "peer_summary": {
                    "strong_match_count": 2,
                    "usable_match_count": 0,
                    "weak_match_count": 0,
                },
                "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}],
            }

        def dashboard(self, *, limit: int = 24, family_limit: int = 12):
            return {
                "family_rows": [
                    {
                        "task_family": "task:termui",
                        "status": "strong_family",
                        "trend_status": "stable",
                    }
                ]
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "work: latest-task" in joined
    assert "strategy=interactive_reuse_loop" in joined
    assert "family_status=strong_family" in joined
    assert "workflow=/work -> /next -> /fix -> /validate" in joined
    assert "recommended=/next latest-task" in joined


def test_run_shell_plan_bootstrap_without_current_task() -> None:
    outputs: list[str] = []
    inputs = iter(["/plan", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": None,
                "text": "project:local/demo | task:cold-start | bootstrap_first_loop | bootstrap_first | cold_start",
            }

        def bootstrap_overview(self):
            return {
                "bootstrap_snapshot": {
                    "bootstrap_focus": ["src/demo.py", "tests/test_demo.py"],
                    "bootstrap_working_set": ["src", "tests", "pyproject.toml"],
                    "bootstrap_validation_commands": ["PYTHONPATH=src python3 -m pytest -q"],
                    "bootstrap_first_step": "Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice.",
                    "bootstrap_validation_step": "Run PYTHONPATH=src python3 -m pytest -q before expanding the working set.",
                    "bootstrap_reuse_summary": "no reusable prior yet; the first validated success will seed future family reuse",
                    "recent_commit_subjects": ["Add initial parser tests"],
                    "notes": ["Detected source roots: src", "Detected test roots: tests"],
                },
                "canonical_views": {
                    "task_state": {"status": "bootstrap_ready"},
                    "strategy": {
                        "task_family": "task:cold-start",
                        "strategy_profile": "bootstrap_first_loop",
                    },
                    "planner": {
                        "next_action": "Create one narrow first task inside the bootstrap working set, then run the first suggested validation command."
                    },
                    "instrumentation": {"status": "cold_start"},
                },
                "evaluation": {"status": "bootstrap_ready"},
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "plan: bootstrap" in joined
    assert "first_step=Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice." in joined
    assert "validate_first=Run PYTHONPATH=src python3 -m pytest -q before expanding the working set." in joined
    assert "family=task:cold-start" in joined
    assert "working_set=src, tests, pyproject.toml" in joined
    assert "history=Add initial parser tests" in joined
    assert "workflow=/init -> /doctor -> /run -> /work -> /next -> /fix -> /validate" in joined


def test_run_shell_work_bootstrap_without_current_task() -> None:
    outputs: list[str] = []
    inputs = iter(["/work", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": None,
                "text": "project:local/demo | task:cold-start | bootstrap_first_loop | bootstrap_first | cold_start",
            }

        def bootstrap_overview(self):
            return {
                "bootstrap_snapshot": {
                    "bootstrap_focus": ["src/demo.py", "tests/test_demo.py"],
                    "bootstrap_working_set": ["src", "tests", "pyproject.toml"],
                    "bootstrap_validation_commands": ["PYTHONPATH=src python3 -m pytest -q"],
                    "bootstrap_first_step": "Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice.",
                    "bootstrap_validation_step": "Run PYTHONPATH=src python3 -m pytest -q before expanding the working set.",
                    "bootstrap_reuse_summary": "no reusable prior yet; the first validated success will seed future family reuse",
                    "recent_commit_subjects": ["Add initial parser tests"],
                    "notes": ["Detected source roots: src", "Detected test roots: tests"],
                },
                "canonical_views": {
                    "task_state": {"status": "bootstrap_ready"},
                    "strategy": {
                        "task_family": "task:cold-start",
                        "strategy_profile": "bootstrap_first_loop",
                    },
                    "planner": {
                        "next_action": "Create one narrow first task inside the bootstrap working set, then run the first suggested validation command."
                    },
                    "instrumentation": {"status": "cold_start"},
                },
                "evaluation": {"status": "bootstrap_ready"},
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "work: bootstrap" in joined
    assert "first_step=Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice." in joined
    assert "validate=PYTHONPATH=src python3 -m pytest -q" in joined
    assert "workflow=/init -> /doctor -> /run -> /work -> /next -> /fix -> /validate" in joined


def test_run_shell_init_bootstrap() -> None:
    outputs: list[str] = []
    inputs = iter(["/init", "/exit"])

    class ShellWorkbench:
        repo_root = "/tmp/repo"

        def shell_status(self, task_id: str | None = None):
            return {
                "task_id": None,
                "text": "project:local/demo | task:cold-start | bootstrap_first_loop | bootstrap_first | cold_start",
            }

        def initialize_project(self):
            return {
                "initialized": True,
                "bootstrap_path": "/tmp/repo/.aionis-workbench/bootstrap.json",
                "setup": {
                    "mode": "inspect-only",
                    "live_ready": False,
                    "next_steps": [
                        "run `aionis init --repo-root /tmp/repo` to create bootstrap state",
                        "configure model credentials to enable live execution",
                    ],
                },
                "host_contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                },
                "bootstrap_snapshot": {
                    "bootstrap_focus": ["src/demo.py", "tests/test_demo.py"],
                    "bootstrap_working_set": ["src", "tests", "pyproject.toml"],
                    "bootstrap_validation_commands": ["PYTHONPATH=src python3 -m pytest -q"],
                    "bootstrap_first_step": "Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice.",
                    "bootstrap_validation_step": "Run PYTHONPATH=src python3 -m pytest -q before expanding the working set.",
                    "bootstrap_reuse_summary": "no reusable prior yet; the first validated success will seed future family reuse",
                    "recent_commit_subjects": ["Add initial parser tests"],
                    "notes": ["Detected source roots: src", "Detected test roots: tests"],
                },
                "canonical_views": {
                    "task_state": {"status": "bootstrap_ready"},
                    "strategy": {
                        "task_family": "task:cold-start",
                        "strategy_profile": "bootstrap_first_loop",
                    },
                    "planner": {
                        "next_action": "Create one narrow first task inside the bootstrap working set, then run the first suggested validation command."
                    },
                    "instrumentation": {"status": "cold_start"},
                },
                "evaluation": {"status": "bootstrap_ready"},
            }

    run_shell(
        ShellWorkbench(),
        input_fn=lambda _prompt: next(inputs),
        write_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "init: bootstrap" in joined
    assert "first_step=Start with src/demo.py, tests/test_demo.py and keep the first task inside that slice." in joined
    assert "setup_mode=inspect-only live_ready=False" in joined
    assert "next=run `aionis init --repo-root /tmp/repo` to create bootstrap state" in joined
    assert "workflow=/init -> /doctor -> /run -> /work -> /next -> /fix -> /validate" in joined
    assert "bootstrap_path=/tmp/repo/.aionis-workbench/bootstrap.json" in joined
