from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ShellCommand:
    name: str
    description: str
    aliases: tuple[str, ...] = ()
    immediate: bool = False
    expects_args: bool = False


@dataclass
class ShellCommandContext:
    repo_root: str | None
    current_task_id: str | None = None
    metadata: dict[str, Any] | None = None


_SHELL_COMMANDS: tuple[ShellCommand, ...] = (
    ShellCommand("init", "Initialize bootstrap state for the current repo."),
    ShellCommand("setup", "Show the current onboarding setup checklist and command hints."),
    ShellCommand("doctor", "Check whether the current repo is ready for live or inspect-only Aionis usage."),
    ShellCommand("run", "Start a new workbench task.", expects_args=True),
    ShellCommand("ship", "Route one task through the best current Workbench product entry.", expects_args=True),
    ShellCommand("resume", "Resume an existing workbench task.", expects_args=True),
    ShellCommand("ingest", "Record an externally completed validated task.", expects_args=True),
    ShellCommand("work", "Show the default workflow surface for the current task.", expects_args=True),
    ShellCommand("next", "Execute the default next step for the current task.", expects_args=True),
    ShellCommand("fix", "Run the default execution step for the current task.", expects_args=True),
    ShellCommand("plan", "Show the short action plan for the current task.", expects_args=True),
    ShellCommand("review", "Review the current task, family, and readiness in one surface.", expects_args=True),
    ShellCommand("show", "Show the current task summary surface.", aliases=("open",), expects_args=True),
    ShellCommand("family", "Show the current task family summary surface.", expects_args=True),
    ShellCommand("hosts", "Show the unified Aionis CLI, Workbench engine, and execution host contract.", aliases=("host",)),
    ShellCommand("validate", "Re-run the primary validation command for the current task.", expects_args=True),
    ShellCommand("session", "Inspect a persisted workbench session.", expects_args=True),
    ShellCommand("evaluate", "Evaluate a persisted session against the canonical surfaces.", expects_args=True),
    ShellCommand("compare-family", "Compare a task against recent sessions from the same task family.", expects_args=True),
    ShellCommand("dashboard", "Show a project-level family instrumentation dashboard."),
    ShellCommand("consolidate", "Run a conservative project-scoped consolidation pass.", aliases=("dream",), expects_args=True),
    ShellCommand("app", "Inspect the current app harness state.", expects_args=True),
    ShellCommand("ab-test", "Compare a thin baseline loop against the current Aionis task state.", expects_args=True),
    ShellCommand("doc", "Compile, run, publish, recover, or resume an Aionisdoc workflow.", expects_args=True),
    ShellCommand("background", "Show the current consolidation/background maintenance status."),
    ShellCommand("status", "Show the current Aionis shell status."),
    ShellCommand("tasks", "List recent tasks for the current project scope.", expects_args=True),
    ShellCommand("latest", "Switch the shell to the most recent task in this project scope."),
    ShellCommand("pick", "Select a recent task by its /tasks index.", expects_args=True),
    ShellCommand("use", "Select the current task context for follow-up shell commands.", expects_args=True),
    ShellCommand("clear", "Clear the current task context."),
    ShellCommand("raw", "Toggle raw JSON output in the shell.", aliases=("json",), expects_args=True),
    ShellCommand("help", "Show the available shell commands.", aliases=("?",)),
    ShellCommand("exit", "Exit the Aionis shell.", aliases=("quit", "q", ":q")),
)


def _normalize_command_name(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized.strip()


def get_shell_commands() -> tuple[ShellCommand, ...]:
    return _SHELL_COMMANDS


def find_shell_command(value: str) -> ShellCommand | None:
    normalized = _normalize_command_name(value)
    if not normalized:
        return None
    for command in _SHELL_COMMANDS:
        if normalized == command.name or normalized in command.aliases:
            return command
    return None
