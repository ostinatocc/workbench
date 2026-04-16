from __future__ import annotations

import pytest

from aionis_workbench.provider_profiles import (
    ZAI_CODING_BASE_URL,
    get_provider_profile,
    infer_provider_profile_id,
    provider_profile_has_required_credentials,
    resolve_provider_profile,
)


def test_zai_glm51_profile_has_expected_endpoint() -> None:
    profile = get_provider_profile("zai_glm51_coding")

    assert profile.base_url == ZAI_CODING_BASE_URL
    assert profile.model == "glm-5.1"
    assert profile.provider == "openai"
    assert profile.timeout_seconds == 15
    assert profile.max_completion_tokens == 256


def test_infer_provider_profile_prefers_explicit_profile() -> None:
    provider_id = infer_provider_profile_id(
        {
            "AIONIS_PROVIDER_PROFILE": "zai_glm51_coding",
            "OPENAI_API_KEY": "present",
            "WORKBENCH_MODEL": "gpt-5",
        }
    )

    assert provider_id == "zai_glm51_coding"


def test_infer_provider_profile_detects_openrouter() -> None:
    provider_id = infer_provider_profile_id({"OPENROUTER_API_KEY": "present"})

    assert provider_id == "openrouter_default"


def test_infer_provider_profile_prefers_openai_path_when_both_credential_families_are_present() -> None:
    provider_id = infer_provider_profile_id(
        {
            "OPENAI_API_KEY": "present",
            "OPENAI_BASE_URL": ZAI_CODING_BASE_URL,
            "OPENROUTER_API_KEY": "present",
        }
    )

    assert provider_id == "zai_glm51_coding"


def test_infer_provider_profile_does_not_bless_glm_model_without_zai_endpoint() -> None:
    provider_id = infer_provider_profile_id(
        {
            "OPENAI_API_KEY": "present",
            "OPENAI_BASE_URL": "https://example.com/v1",
            "WORKBENCH_MODEL": "glm-5.1",
        }
    )

    assert provider_id == "openai_default"


def test_infer_provider_profile_detects_zai_from_glm_model_without_explicit_base_url() -> None:
    provider_id = infer_provider_profile_id(
        {
            "OPENAI_API_KEY": "present",
            "WORKBENCH_MODEL": "glm-5.1",
        }
    )

    assert provider_id == "zai_glm51_coding"


def test_resolve_provider_profile_detects_zai_from_base_url() -> None:
    profile = resolve_provider_profile(
        {
            "OPENAI_API_KEY": "present",
            "OPENAI_BASE_URL": ZAI_CODING_BASE_URL,
        }
    )

    assert profile is not None
    assert profile.provider_id == "zai_glm51_coding"


def test_provider_profile_has_required_credentials_checks_selected_provider_family() -> None:
    openai_profile = get_provider_profile("openai_default")
    openrouter_profile = get_provider_profile("openrouter_default")

    assert provider_profile_has_required_credentials(openai_profile, {"OPENAI_API_KEY": "present"}) is True
    assert provider_profile_has_required_credentials(openai_profile, {"OPENROUTER_API_KEY": "present"}) is False
    assert provider_profile_has_required_credentials(openrouter_profile, {"OPENROUTER_API_KEY": "present"}) is True
    assert provider_profile_has_required_credentials(openrouter_profile, {"OPENAI_API_KEY": "present"}) is False


def test_unknown_provider_profile_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown provider profile"):
        get_provider_profile("missing_profile")
