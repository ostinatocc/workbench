from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["AionisWorkbench", "WorkbenchRunResult", "ShellCommand", "get_shell_commands", "find_shell_command"]

if TYPE_CHECKING:
    from .runtime import AionisWorkbench, WorkbenchRunResult
    from .shell_commands import ShellCommand


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .runtime import AionisWorkbench, WorkbenchRunResult
        from .shell_commands import ShellCommand, find_shell_command, get_shell_commands

        exports = {
            "AionisWorkbench": AionisWorkbench,
            "WorkbenchRunResult": WorkbenchRunResult,
            "ShellCommand": ShellCommand,
            "get_shell_commands": get_shell_commands,
            "find_shell_command": find_shell_command,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
