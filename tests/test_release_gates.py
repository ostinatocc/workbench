from __future__ import annotations

from aionis_workbench.release_gates import evaluate_release_gates


def test_release_gates_fail_when_deterministic_suite_fails() -> None:
    result = evaluate_release_gates(
        deterministic_exit_code=1,
        live_exit_code=0,
        provider_profile="zai_glm51_coding",
    )

    assert result.passed is False
    assert "deterministic_suite_failed" in result.failures


def test_release_gates_fail_when_live_suite_fails() -> None:
    result = evaluate_release_gates(
        deterministic_exit_code=0,
        live_exit_code=2,
        provider_profile="zai_glm51_coding",
    )

    assert result.passed is False
    assert "live_suite_failed" in result.failures


def test_release_gates_fail_when_provider_profile_is_not_release_approved() -> None:
    result = evaluate_release_gates(
        deterministic_exit_code=0,
        live_exit_code=0,
        provider_profile="openai_default",
    )

    assert result.passed is False
    assert "provider_not_approved_for_release" in result.failures


def test_release_gates_pass_when_all_inputs_are_present() -> None:
    result = evaluate_release_gates(
        deterministic_exit_code=0,
        live_exit_code=0,
        provider_profile="zai_glm51_coding",
    )

    assert result.passed is True
    assert result.provider_profile == "zai_glm51_coding"
    assert result.provider_release_tier == "manual_verified"
    assert result.summary().startswith("release-gates: passed")
