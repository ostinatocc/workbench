from __future__ import annotations

from aionis_workbench.policies import _artifact_routing_for_role
from aionis_workbench.runtime import _build_execution_packet
from aionis_workbench.session import (
    ArtifactReference,
    DelegationReturn,
    SessionState,
)


def _arc_session() -> SessionState:
    session = SessionState(
        task_id="arc-ls20-trial",
        goal="ARC AGI 3 benchmark game ls20",
        repo_root="/tmp/arc-exp",
        project_identity="arc-agi-3-experiment",
        project_scope="project:local/arc-agi-3-experiment",
        status="paused",
        target_files=["arc_games/ls20.arc"],
        selected_task_family="task:games-ls20-arc",
        selected_pattern_summaries=[
            "[investigator/artifact_routing_strategy] Route ARC analysis through the step digest before widening context."
        ],
        last_validation_result={
            "ok": False,
            "summary": "ARC benchmark result: state=NOT_FINISHED score=0.0 levels_completed=0 actions=80",
        },
        continuity_snapshot={
            "task_family": "task:games-ls20-arc",
            "arc_bridge": {
                "score": 0.0,
                "levels_completed": 0,
                "scorecard_url": "https://three.arcprize.org/scorecards/test",
                "recent_actions": ["ACTION4", "ACTION1", "ACTION2"],
                "action_distribution": {
                    "ACTION4": 54,
                    "ACTION1": 15,
                    "ACTION2": 11,
                    "RESET": 1,
                },
                "blocked_action_counts": {
                    "ACTION5": 81,
                    "ACTION6": 81,
                },
            },
        },
        artifacts=[
            ArtifactReference(
                artifact_id="arc_step_digest",
                kind="arc_step_digest_artifact",
                role="investigator",
                summary="ARC step digest",
                path=".aionis-workbench/artifacts/arc-ls20-trial/arc_step_digest.json",
                metadata={},
            ),
            ArtifactReference(
                artifact_id="arc_step_packets",
                kind="arc_step_packets_artifact",
                role="investigator",
                summary="ARC step packets",
                path=".aionis-workbench/artifacts/arc-ls20-trial/arc_step_packets.json",
                metadata={},
            ),
            ArtifactReference(
                artifact_id="arc_plan_summary",
                kind="arc_plan_artifact",
                role="implementer",
                summary="ARC local plan summary",
                path=".aionis-workbench/artifacts/arc-ls20-trial/arc_plan_summary.json",
                metadata={},
            ),
        ],
        delegation_returns=[
            DelegationReturn(
                role="investigator",
                status="success",
                summary="Captured ARC step digest.",
                evidence=["Top actions: ACTION4=54, ACTION1=15, ACTION2=11"],
                working_set=["arc_games/ls20.arc"],
            ),
            DelegationReturn(
                role="implementer",
                status="success",
                summary="Executed ARC action chain.",
                evidence=["Recent chain: ACTION4 -> ACTION1 -> ACTION2"],
                working_set=["arc_games/ls20.arc"],
            ),
        ],
    )
    return session


def test_arc_execution_packet_uses_arc_native_next_action() -> None:
    packet, summary = _build_execution_packet(_arc_session())
    assert packet.current_stage == "verifying"
    assert "ARC step digest" in packet.next_action
    assert "dominant ARC actions are ACTION4=54, ACTION1=15, ACTION2=11, RESET=1" in packet.accepted_facts
    assert summary.current_stage == "verifying"


def test_arc_routing_reason_uses_arc_specific_language() -> None:
    session = _arc_session()
    refs, evidence, reason = _artifact_routing_for_role(session, "verifier")
    assert refs
    assert any("ARC blocked actions: ACTION5=81, ACTION6=81" == item for item in evidence)
    assert "scorecard outcome" in reason
