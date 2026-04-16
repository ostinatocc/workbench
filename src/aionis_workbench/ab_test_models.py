from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: object) -> bool:
    return value is True


@dataclass
class BenchmarkScenarioResult:
    scenario_id: str
    arm: str
    provider_id: str = ""
    model: str = ""
    ended_in: str = ""
    total_duration_seconds: float = 0.0
    retry_count: int = 0
    replan_depth: int = 0
    latest_convergence_signal: str = ""
    final_execution_gate: str = ""
    gate_flow: str = ""
    policy_stage: str = ""
    advance_reached: bool = False
    escalated: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "BenchmarkScenarioResult | None":
        if not isinstance(value, dict):
            return None
        scenario_id = _string(value.get("scenario_id"))
        arm = _string(value.get("arm"))
        if not scenario_id or not arm:
            return None
        return cls(
            scenario_id=scenario_id,
            arm=arm,
            provider_id=_string(value.get("provider_id")),
            model=_string(value.get("model")),
            ended_in=_string(value.get("ended_in")),
            total_duration_seconds=_float(value.get("total_duration_seconds")),
            retry_count=_int(value.get("retry_count")),
            replan_depth=_int(value.get("replan_depth")),
            latest_convergence_signal=_string(value.get("latest_convergence_signal")),
            final_execution_gate=_string(value.get("final_execution_gate")),
            gate_flow=_string(value.get("gate_flow")),
            policy_stage=_string(value.get("policy_stage")),
            advance_reached=_bool(value.get("advance_reached")),
            escalated=_bool(value.get("escalated")),
            notes=_string_list(value.get("notes")),
        )


@dataclass
class BenchmarkComparison:
    scenario_id: str
    baseline: BenchmarkScenarioResult
    aionis: BenchmarkScenarioResult
    duration_delta_seconds: float = 0.0
    retry_delta: int = 0
    replan_delta: int = 0
    convergence_delta: str = ""
    winner: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["baseline"] = self.baseline.to_dict()
        payload["aionis"] = self.aionis.to_dict()
        return payload

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "BenchmarkComparison | None":
        if not isinstance(value, dict):
            return None
        scenario_id = _string(value.get("scenario_id"))
        baseline = BenchmarkScenarioResult.from_dict(value.get("baseline"))
        aionis = BenchmarkScenarioResult.from_dict(value.get("aionis"))
        if not scenario_id or baseline is None or aionis is None:
            return None
        return cls(
            scenario_id=scenario_id,
            baseline=baseline,
            aionis=aionis,
            duration_delta_seconds=_float(value.get("duration_delta_seconds")),
            retry_delta=_int(value.get("retry_delta")),
            replan_delta=_int(value.get("replan_delta")),
            convergence_delta=_string(value.get("convergence_delta")),
            winner=_string(value.get("winner")),
            summary=_string(value.get("summary")),
        )


@dataclass
class BenchmarkRun:
    benchmark_id: str
    scenario_family: str = ""
    provider_id: str = ""
    model: str = ""
    results: list[BenchmarkScenarioResult] = field(default_factory=list)
    comparisons: list[BenchmarkComparison] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "scenario_family": self.scenario_family,
            "provider_id": self.provider_id,
            "model": self.model,
            "results": [result.to_dict() for result in self.results],
            "comparisons": [comparison.to_dict() for comparison in self.comparisons],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "BenchmarkRun | None":
        if not isinstance(value, dict):
            return None
        benchmark_id = _string(value.get("benchmark_id"))
        if not benchmark_id:
            return None
        results = [
            result
            for raw in (value.get("results") or [])
            if (result := BenchmarkScenarioResult.from_dict(raw)) is not None
        ]
        comparisons = [
            comparison
            for raw in (value.get("comparisons") or [])
            if (comparison := BenchmarkComparison.from_dict(raw)) is not None
        ]
        return cls(
            benchmark_id=benchmark_id,
            scenario_family=_string(value.get("scenario_family")),
            provider_id=_string(value.get("provider_id")),
            model=_string(value.get("model")),
            results=results,
            comparisons=comparisons,
        )
