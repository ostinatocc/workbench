from __future__ import annotations

from .session import DelegationPacket


def builtin_subagents() -> list[dict[str, str]]:
    return [
        {
            "name": "investigator",
            "description": "Use this role to isolate repo inspection, bug localization, and codepath analysis.",
            "system_prompt": (
                "You are the investigator. Read code, inspect tests, narrow the failure surface, "
                "and return a concise diagnosis with file-level evidence."
            ),
        },
        {
            "name": "implementer",
            "description": "Use this role to make precise code changes in a narrow working set.",
            "system_prompt": (
                "You are the implementer. Edit only the intended files, keep changes minimal, "
                "and return a crisp patch summary with touched files."
            ),
        },
        {
            "name": "verifier",
            "description": "Use this role to run targeted validation and judge whether the fix actually holds.",
            "system_prompt": (
                "You are the verifier. Run the narrowest relevant checks, report exact commands and results, "
                "and call out residual risks."
            ),
        },
    ]


def default_delegation_packets(
    *,
    task: str,
    target_files: list[str],
    validation_commands: list[str],
) -> list[DelegationPacket]:
    working_set = target_files[:8]
    checks = validation_commands[:6]
    return [
        DelegationPacket(
            role="investigator",
            mission=f"Localize the problem and explain the likely cause for: {task}",
            working_set=working_set,
            acceptance_checks=checks,
            output_contract="Return root cause, impacted files, and the narrowest safe implementation scope.",
        ),
        DelegationPacket(
            role="implementer",
            mission=f"Implement the smallest correct fix for: {task}",
            working_set=working_set,
            acceptance_checks=checks,
            output_contract="Return touched files, code-level summary, and any follow-up validation needed.",
        ),
        DelegationPacket(
            role="verifier",
            mission=f"Validate the proposed fix for: {task}",
            working_set=working_set,
            acceptance_checks=checks,
            output_contract="Return exact commands executed, pass/fail result, and residual risks.",
        ),
    ]
