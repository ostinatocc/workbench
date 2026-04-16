from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    status: str
    repo_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


@dataclass(frozen=True)
class SuiteResult:
    results: list[ScenarioResult]

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.status == "passed")

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if result.status == "failed")
