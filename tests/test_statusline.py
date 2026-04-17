from __future__ import annotations

from aionis_workbench.statusline import build_statusline_input, render_statusline


def test_statusline_renders_canonical_fields() -> None:
    payload = build_statusline_input(
        project_identity="pallets/click",
        project_scope="project:pallets/click",
        task_id="click-2403-ingest-1",
        canonical_views={
            "strategy": {
                "task_family": "task:termui",
                "strategy_profile": "interactive_reuse_loop",
                "validation_style": "targeted_first",
            },
            "instrumentation": {
                "status": "strong_match",
            },
        },
        dashboard_payload={
            "family_rows": [
                {
                    "task_family": "task:termui",
                    "trend_status": "stable",
                }
            ]
        },
    )
    text = render_statusline(payload)
    assert "project:pallets/click" in text
    assert "task:termui" in text
    assert "interactive_reuse_loop" in text
    assert "strong_match" in text
    assert "stable" in text


def test_statusline_renders_consolidation_status() -> None:
    payload = build_statusline_input(
        project_identity="pallets/click",
        project_scope="project:pallets/click",
        task_id="click-2403-ingest-1",
        canonical_views={
            "strategy": {
                "task_family": "task:termui",
                "strategy_profile": "interactive_reuse_loop",
                "validation_style": "targeted_first",
            },
            "instrumentation": {
                "status": "strong_match",
            },
        },
        dashboard_payload={},
        background_payload={"status_line": "completed"},
    )
    text = render_statusline(payload)
    assert "consolidate:completed" in text


def test_statusline_renders_host_summary() -> None:
    payload = build_statusline_input(
        project_identity="pallets/click",
        project_scope="project:pallets/click",
        task_id="click-2403-ingest-1",
        canonical_views={
            "strategy": {
                "task_family": "task:termui",
                "strategy_profile": "interactive_reuse_loop",
                "validation_style": "targeted_first",
            },
            "instrumentation": {
                "status": "strong_match",
            },
        },
        host_payload={
            "contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {"name": "openai_agents_local_shell"},
            }
        },
    )
    text = render_statusline(payload)
    assert "hosts:aionis_cli/workbench_engine/openai_agents_local_shell" in text


def test_statusline_renders_controller_actions() -> None:
    payload = build_statusline_input(
        project_identity="pallets/click",
        project_scope="project:pallets/click",
        task_id="click-2403-ingest-1",
        canonical_views={
            "strategy": {
                "task_family": "task:termui",
                "strategy_profile": "interactive_reuse_loop",
                "validation_style": "targeted_first",
            },
            "instrumentation": {
                "status": "strong_match",
            },
            "controller": {
                "status": "paused",
                "allowed_actions": ["list_events", "inspect_context", "resume"],
                "blocked_actions": ["record_event", "plan_start", "complete"],
                "last_transition_kind": "paused",
            },
        },
    )
    text = render_statusline(payload)
    assert "controller:paused[list_events,inspect_context,resume]" in text
    assert "blocked:record_event,plan_start" in text
    assert "transition:paused" in text
