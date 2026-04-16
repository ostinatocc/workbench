from __future__ import annotations

import json

from aionis_workbench.e2e.real_e2e.result_models import ScenarioResult, SuiteResult


def test_scenario_result_serializes_to_json() -> None:
    result = ScenarioResult(
        scenario_id="editor-to-dream",
        status="passed",
        repo_id="vitepress-docs",
        details={"proof": "live"},
    )

    payload = json.loads(result.to_json())

    assert payload["scenario_id"] == "editor-to-dream"
    assert payload["status"] == "passed"
    assert payload["repo_id"] == "vitepress-docs"


def test_suite_result_summarizes_pass_fail_counts() -> None:
    suite = SuiteResult(
        results=[
            ScenarioResult(scenario_id="one", status="passed", repo_id="repo-a"),
            ScenarioResult(scenario_id="two", status="failed", repo_id="repo-b"),
            ScenarioResult(scenario_id="three", status="passed", repo_id="repo-c"),
        ]
    )

    assert suite.passed_count == 2
    assert suite.failed_count == 1
    assert suite.total_count == 3
