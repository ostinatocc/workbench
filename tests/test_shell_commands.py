from __future__ import annotations

from aionis_workbench.shell_commands import find_shell_command, get_shell_commands


def test_shell_registry_contains_expected_commands() -> None:
    names = {command.name for command in get_shell_commands()}
    assert names >= {
        "init",
        "run",
        "resume",
        "ingest",
        "work",
        "next",
        "fix",
        "plan",
        "review",
        "show",
        "family",
        "hosts",
        "validate",
        "session",
        "evaluate",
        "compare-family",
        "dashboard",
        "status",
        "tasks",
        "latest",
        "pick",
        "use",
        "clear",
        "raw",
        "help",
        "exit",
    }


def test_shell_registry_resolves_aliases() -> None:
    assert find_shell_command("/quit").name == "exit"
    assert find_shell_command("q").name == "exit"
    assert find_shell_command("/compare-family").name == "compare-family"
    assert find_shell_command("/host").name == "hosts"
