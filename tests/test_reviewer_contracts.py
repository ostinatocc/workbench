from __future__ import annotations

from aionis_workbench.execution_packet import ExecutionPacket, ExecutionPacketSummary
from aionis_workbench.reviewer_contracts import (
    ReviewPackSummary,
    ResumeAnchor,
    ReviewerContract,
    continuity_review_pack_summary_from_runtime,
    evolution_review_pack_summary_from_runtime,
    resolve_reviewer_evidence,
)


def test_reviewer_contract_from_dict_accepts_runtime_shape() -> None:
    contract = ReviewerContract.from_dict(
        {
            "standard": "strict",
            "required_outputs": ["patch", "tests"],
            "acceptance_checks": ["pytest -q"],
            "rollback_required": True,
        }
    )

    assert contract is not None
    assert contract.standard == "strict"
    assert contract.required_outputs == ["patch", "tests"]
    assert contract.acceptance_checks == ["pytest -q"]
    assert contract.rollback_required is True


def test_resume_anchor_from_dict_requires_anchor() -> None:
    assert ResumeAnchor.from_dict({"file_path": "src/demo.py"}) is None

    anchor = ResumeAnchor.from_dict(
        {
            "anchor": "resume:src/demo.py",
            "file_path": "src/demo.py",
            "symbol": "demo",
            "repo_root": "/repo",
        }
    )

    assert anchor is not None
    assert anchor.anchor == "resume:src/demo.py"
    assert anchor.file_path == "src/demo.py"


def test_review_pack_summary_round_trips_stable_review_fields() -> None:
    pack = ReviewPackSummary.from_dict(
        {
            "pack_version": "evolution_review_pack_v1",
            "source": "evolution",
            "review_contract": {
                "standard": "strict",
                "required_outputs": ["patch"],
                "acceptance_checks": ["pytest -q"],
                "rollback_required": False,
            },
            "selected_tool": "edit",
            "file_path": "src/demo.py",
            "target_files": ["src/demo.py"],
            "next_action": "Patch src/demo.py and rerun tests",
            "artifact_refs": ["aionis://artifact/1"],
        }
    )

    assert pack is not None
    assert pack.review_contract is not None
    assert pack.review_contract.standard == "strict"
    assert pack.selected_tool == "edit"
    assert pack.to_dict()["pack_version"] == "evolution_review_pack_v1"


def test_execution_packet_from_dict_parses_reviewer_fields() -> None:
    packet = ExecutionPacket.from_dict(
        {
            "packet_version": 1,
            "current_stage": "review",
            "active_role": "review",
            "task_brief": "Review the patch",
            "target_files": ["src/demo.py"],
            "next_action": "Verify the patch against the reviewer contract.",
            "pending_validations": ["pytest -q"],
            "review_contract": {
                "standard": "strict",
                "required_outputs": ["patch", "tests"],
                "acceptance_checks": ["pytest -q"],
                "rollback_required": True,
            },
            "reviewer_ready_required": True,
            "resume_anchor": {
                "anchor": "resume:src/demo.py",
                "file_path": "src/demo.py",
                "repo_root": "/repo",
            },
        }
    )

    assert packet is not None
    assert packet.review_contract is not None
    assert packet.review_contract.standard == "strict"
    assert packet.reviewer_ready_required is True
    assert packet.resume_anchor is not None
    assert packet.resume_anchor.anchor == "resume:src/demo.py"


def test_execution_packet_summary_keeps_reviewer_presence_flags() -> None:
    summary = ExecutionPacketSummary.from_dict(
        {
            "packet_version": 1,
            "current_stage": "review",
            "active_role": "review",
            "task_brief": "Review the patch",
            "review_contract_present": True,
            "reviewer_ready_required": True,
            "resume_anchor_present": True,
        }
    )

    assert summary is not None
    assert summary.review_contract_present is True
    assert summary.reviewer_ready_required is True
    assert summary.resume_anchor_present is True


def test_resolve_reviewer_evidence_merges_continuity_and_evolution_with_evolution_precedence() -> None:
    packet = ExecutionPacket.from_dict(
        {
            "review_contract": {
                "standard": "packet_review",
                "required_outputs": ["patch"],
                "acceptance_checks": ["pytest packet -q"],
                "rollback_required": False,
            },
            "reviewer_ready_required": True,
            "resume_anchor": {"anchor": "resume:src/demo.py"},
        }
    )
    continuity = ReviewPackSummary.from_dict(
        {
            "pack_version": "continuity_review_pack_v1",
            "source": "continuity",
            "review_contract": {
                "standard": "strict_review",
                "required_outputs": ["patch", "tests"],
                "acceptance_checks": ["pytest continuity -q"],
                "rollback_required": False,
            },
            "selected_tool": "read",
        }
    )
    evolution = ReviewPackSummary.from_dict(
        {
            "pack_version": "evolution_review_pack_v1",
            "source": "evolution",
            "review_contract": {
                "standard": "evolution_review",
                "required_outputs": ["snapshot"],
                "acceptance_checks": ["pytest evolution -q"],
                "rollback_required": True,
            },
            "selected_tool": "edit",
        }
    )

    merged = resolve_reviewer_evidence(packet=packet, continuity_pack=continuity, evolution_pack=evolution)

    assert merged["reviewer_standard"] == "evolution_review"
    assert merged["reviewer_pack_source"] == "continuity+evolution"
    assert merged["reviewer_selected_tool"] == "edit"
    assert merged["reviewer_resume_anchor"] == "resume:src/demo.py"
    assert merged["reviewer_required_outputs"] == ["patch", "tests", "snapshot"]
    assert merged["reviewer_acceptance_checks"] == ["pytest continuity -q", "pytest evolution -q"]
    assert merged["reviewer_ready_required"] is True
    assert merged["reviewer_rollback_required"] is True


def test_runtime_review_pack_summaries_do_not_fabricate_contracts_from_empty_payloads() -> None:
    continuity = continuity_review_pack_summary_from_runtime(
        {
            "continuity_review_pack": {
                "pack_version": "continuity_review_pack_v1",
                "review_contract": None,
                "latest_handoff": {"anchor": "resume:src/demo.py", "file_path": "src/demo.py"},
            }
        }
    )
    evolution = evolution_review_pack_summary_from_runtime(
        {
            "evolution_review_pack": {
                "pack_version": "evolution_review_pack_v1",
                "review_contract": {
                    "selected_tool": "",
                    "file_path": "",
                    "target_files": [],
                    "next_action": "",
                },
            }
        }
    )

    assert continuity is not None
    assert continuity.review_contract is None
    assert evolution is not None
    assert evolution.review_contract is None
