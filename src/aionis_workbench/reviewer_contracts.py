from __future__ import annotations

from dataclasses import dataclass, field


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dict_or_none(value: object) -> dict | None:
    return value if isinstance(value, dict) else None


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def _normalized_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _has_continuity_contract_payload(value: dict | None) -> bool:
    if not isinstance(value, dict):
        return False
    return any(
        [
            _string_list(value.get("target_files")),
            _string_list(value.get("acceptance_checks")),
            _first_string(value.get("next_action")),
            value.get("rollback_required") is True,
        ]
    )


def _has_evolution_contract_payload(value: dict | None) -> bool:
    if not isinstance(value, dict):
        return False
    return any(
        [
            _first_string(value.get("selected_tool")),
            _first_string(value.get("file_path")),
            _string_list(value.get("target_files")),
            _first_string(value.get("next_action")),
        ]
    )


@dataclass
class ReviewerContract:
    standard: str = ""
    required_outputs: list[str] = field(default_factory=list)
    acceptance_checks: list[str] = field(default_factory=list)
    rollback_required: bool = False

    @classmethod
    def from_dict(cls, value: dict | None) -> "ReviewerContract | None":
        if not isinstance(value, dict):
            return None
        standard = str(value.get("standard") or "").strip()
        required_outputs = _string_list(value.get("required_outputs"))
        acceptance_checks = _string_list(value.get("acceptance_checks"))
        rollback_required = value.get("rollback_required") is True
        if not standard and not required_outputs and not acceptance_checks and not rollback_required:
            return None
        return cls(
            standard=standard,
            required_outputs=required_outputs,
            acceptance_checks=acceptance_checks,
            rollback_required=rollback_required,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "standard": self.standard,
            "required_outputs": list(self.required_outputs),
            "acceptance_checks": list(self.acceptance_checks),
            "rollback_required": self.rollback_required,
        }


@dataclass
class ResumeAnchor:
    anchor: str = ""
    file_path: str | None = None
    symbol: str | None = None
    repo_root: str | None = None

    @classmethod
    def from_dict(cls, value: dict | None) -> "ResumeAnchor | None":
        if not isinstance(value, dict):
            return None
        anchor = str(value.get("anchor") or "").strip()
        if not anchor:
            return None
        file_path = str(value.get("file_path") or "").strip() or None
        symbol = str(value.get("symbol") or "").strip() or None
        repo_root = str(value.get("repo_root") or "").strip() or None
        return cls(anchor=anchor, file_path=file_path, symbol=symbol, repo_root=repo_root)

    def to_dict(self) -> dict[str, object]:
        return {
            "anchor": self.anchor,
            "file_path": self.file_path,
            "symbol": self.symbol,
            "repo_root": self.repo_root,
        }


@dataclass
class ReviewPackSummary:
    pack_version: str = ""
    source: str = ""
    review_contract: ReviewerContract | None = None
    selected_tool: str | None = None
    file_path: str | None = None
    target_files: list[str] = field(default_factory=list)
    next_action: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    latest_handoff: dict | None = None
    latest_resume: dict | None = None
    latest_terminal_run: dict | None = None
    recovered_handoff: dict | None = None
    stable_workflow: dict | None = None
    promotion_ready_workflow: dict | None = None
    trusted_pattern: dict | None = None
    contested_pattern: dict | None = None

    @classmethod
    def from_dict(cls, value: dict | None) -> "ReviewPackSummary | None":
        if not isinstance(value, dict):
            return None
        pack_version = str(value.get("pack_version") or "").strip()
        source = str(value.get("source") or "").strip()
        selected_tool = str(value.get("selected_tool") or "").strip() or None
        file_path = str(value.get("file_path") or "").strip() or None
        next_action = str(value.get("next_action") or "").strip() or None
        target_files = _string_list(value.get("target_files"))
        artifact_refs = _string_list(value.get("artifact_refs"))
        review_contract = ReviewerContract.from_dict(_dict_or_none(value.get("review_contract")))
        latest_handoff = _dict_or_none(value.get("latest_handoff"))
        latest_resume = _dict_or_none(value.get("latest_resume"))
        latest_terminal_run = _dict_or_none(value.get("latest_terminal_run"))
        recovered_handoff = _dict_or_none(value.get("recovered_handoff"))
        stable_workflow = _dict_or_none(value.get("stable_workflow"))
        promotion_ready_workflow = _dict_or_none(value.get("promotion_ready_workflow"))
        trusted_pattern = _dict_or_none(value.get("trusted_pattern"))
        contested_pattern = _dict_or_none(value.get("contested_pattern"))
        if not any(
            [
                pack_version,
                source,
                review_contract,
                selected_tool,
                file_path,
                next_action,
                target_files,
                artifact_refs,
                latest_handoff,
                latest_resume,
                latest_terminal_run,
                recovered_handoff,
                stable_workflow,
                promotion_ready_workflow,
                trusted_pattern,
                contested_pattern,
            ]
        ):
            return None
        return cls(
            pack_version=pack_version,
            source=source,
            review_contract=review_contract,
            selected_tool=selected_tool,
            file_path=file_path,
            target_files=target_files,
            next_action=next_action,
            artifact_refs=artifact_refs,
            latest_handoff=latest_handoff,
            latest_resume=latest_resume,
            latest_terminal_run=latest_terminal_run,
            recovered_handoff=recovered_handoff,
            stable_workflow=stable_workflow,
            promotion_ready_workflow=promotion_ready_workflow,
            trusted_pattern=trusted_pattern,
            contested_pattern=contested_pattern,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "pack_version": self.pack_version,
            "source": self.source,
            "review_contract": self.review_contract.to_dict() if self.review_contract else None,
            "selected_tool": self.selected_tool,
            "file_path": self.file_path,
            "target_files": list(self.target_files),
            "next_action": self.next_action,
            "artifact_refs": list(self.artifact_refs),
            "latest_handoff": self.latest_handoff,
            "latest_resume": self.latest_resume,
            "latest_terminal_run": self.latest_terminal_run,
            "recovered_handoff": self.recovered_handoff,
            "stable_workflow": self.stable_workflow,
            "promotion_ready_workflow": self.promotion_ready_workflow,
            "trusted_pattern": self.trusted_pattern,
            "contested_pattern": self.contested_pattern,
        }


def continuity_review_pack_summary_from_runtime(payload: dict | None) -> ReviewPackSummary | None:
    if not isinstance(payload, dict):
        return None
    pack = _dict_or_none(payload.get("continuity_review_pack"))
    if not pack:
        return None
    review_contract_raw = _dict_or_none(pack.get("review_contract")) or {}
    target_files = _string_list(review_contract_raw.get("target_files"))
    latest_handoff = _dict_or_none(pack.get("latest_handoff"))
    recovered_handoff = _dict_or_none(pack.get("recovered_handoff"))
    file_path = _first_string(
        (latest_handoff or {}).get("file_path"),
        (recovered_handoff or {}).get("file_path"),
    )
    review_contract = None
    if _has_continuity_contract_payload(review_contract_raw):
        required_outputs: list[str] = ["patch"] if (target_files or file_path) else []
        if _string_list(review_contract_raw.get("acceptance_checks")):
            required_outputs.append("tests")
        if review_contract_raw.get("rollback_required") is True:
            required_outputs.append("rollback_plan")
        review_contract = ReviewerContract(
            standard="continuity_review",
            required_outputs=list(dict.fromkeys(required_outputs)),
            acceptance_checks=_string_list(review_contract_raw.get("acceptance_checks")),
            rollback_required=review_contract_raw.get("rollback_required") is True,
        )
    return ReviewPackSummary(
        pack_version=str(pack.get("pack_version") or "").strip(),
        source="continuity",
        review_contract=review_contract,
        file_path=file_path,
        target_files=target_files,
        next_action=_first_string(review_contract_raw.get("next_action")),
        latest_handoff=latest_handoff,
        latest_resume=_dict_or_none(pack.get("latest_resume")),
        latest_terminal_run=_dict_or_none(pack.get("latest_terminal_run")),
        recovered_handoff=recovered_handoff,
    )


def evolution_review_pack_summary_from_runtime(payload: dict | None) -> ReviewPackSummary | None:
    if not isinstance(payload, dict):
        return None
    pack = _dict_or_none(payload.get("evolution_review_pack"))
    if not pack:
        return None
    review_contract_raw = _dict_or_none(pack.get("review_contract")) or {}
    selected_tool = _first_string(review_contract_raw.get("selected_tool"))
    file_path = _first_string(review_contract_raw.get("file_path"))
    target_files = _string_list(review_contract_raw.get("target_files"))
    review_contract = None
    if _has_evolution_contract_payload(review_contract_raw):
        required_outputs: list[str] = []
        if selected_tool in {"edit", "write", "bash"} or file_path or target_files:
            required_outputs.append("patch")
        review_contract = ReviewerContract(
            standard="evolution_review",
            required_outputs=list(dict.fromkeys(required_outputs)),
            acceptance_checks=[],
            rollback_required=False,
        )
    return ReviewPackSummary(
        pack_version=str(pack.get("pack_version") or "").strip(),
        source="evolution",
        review_contract=review_contract,
        selected_tool=selected_tool,
        file_path=file_path,
        target_files=target_files,
        next_action=_first_string(review_contract_raw.get("next_action")),
        stable_workflow=_dict_or_none(pack.get("stable_workflow")),
        promotion_ready_workflow=_dict_or_none(pack.get("promotion_ready_workflow")),
        trusted_pattern=_dict_or_none(pack.get("trusted_pattern")),
        contested_pattern=_dict_or_none(pack.get("contested_pattern")),
    )


def build_effective_reviewer_contract(
    *,
    packet: object | None,
    continuity_pack: ReviewPackSummary | None,
    evolution_pack: ReviewPackSummary | None,
) -> ReviewerContract | None:
    continuity_contract = continuity_pack.review_contract if continuity_pack is not None else None
    evolution_contract = evolution_pack.review_contract if evolution_pack is not None else None
    packet_contract = getattr(packet, "review_contract", None) if packet is not None else None
    if continuity_contract is not None or evolution_contract is not None:
        packet_contract = None
    standard = _first_string(
        getattr(evolution_contract, "standard", None),
        getattr(continuity_contract, "standard", None),
        getattr(packet_contract, "standard", None),
    ) or ""
    required_outputs = _normalized_string_list(
        list(getattr(continuity_contract, "required_outputs", []) or [])
        + list(getattr(evolution_contract, "required_outputs", []) or [])
        + list(getattr(packet_contract, "required_outputs", []) or [])
    )
    acceptance_checks = _normalized_string_list(
        list(getattr(continuity_contract, "acceptance_checks", []) or [])
        + list(getattr(evolution_contract, "acceptance_checks", []) or [])
        + list(getattr(packet_contract, "acceptance_checks", []) or [])
    )
    rollback_required = any(
        getattr(contract, "rollback_required", False) is True
        for contract in (continuity_contract, evolution_contract, packet_contract)
        if contract is not None
    )
    if not (standard or required_outputs or acceptance_checks or rollback_required):
        return None
    return ReviewerContract(
        standard=standard,
        required_outputs=required_outputs,
        acceptance_checks=acceptance_checks,
        rollback_required=rollback_required,
    )


def resolve_reviewer_evidence(
    *,
    packet: object | None,
    continuity_pack: ReviewPackSummary | None,
    evolution_pack: ReviewPackSummary | None,
) -> dict[str, object]:
    continuity_contract = continuity_pack.review_contract if continuity_pack is not None else None
    evolution_contract = evolution_pack.review_contract if evolution_pack is not None else None
    review_contract = build_effective_reviewer_contract(
        packet=packet,
        continuity_pack=continuity_pack,
        evolution_pack=evolution_pack,
    )
    if review_contract is None:
        return {}

    if continuity_contract and evolution_contract:
        pack_source = "continuity+evolution"
    elif evolution_contract:
        pack_source = str(evolution_pack.source or "").strip() or "evolution"
    elif continuity_contract:
        pack_source = str(continuity_pack.source or "").strip() or "continuity"
    else:
        pack_source = "packet"

    selected_tool = _first_string(
        getattr(evolution_pack, "selected_tool", None),
        getattr(continuity_pack, "selected_tool", None),
    ) or ""
    resume_anchor = ""
    resume_anchor_obj = getattr(packet, "resume_anchor", None) if packet is not None else None
    if resume_anchor_obj is not None:
        resume_anchor = str(getattr(resume_anchor_obj, "anchor", "") or "").strip()
    ready_required = getattr(packet, "reviewer_ready_required", False) is True if packet is not None else False
    return {
        "reviewer_standard": str(getattr(review_contract, "standard", "") or "").strip(),
        "reviewer_required_outputs": list(getattr(review_contract, "required_outputs", []) or []),
        "reviewer_acceptance_checks": list(getattr(review_contract, "acceptance_checks", []) or []),
        "reviewer_pack_source": pack_source,
        "reviewer_selected_tool": selected_tool,
        "reviewer_resume_anchor": resume_anchor,
        "reviewer_ready_required": ready_required,
        "reviewer_rollback_required": getattr(review_contract, "rollback_required", False) is True,
    }
