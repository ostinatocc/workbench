from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


ZAI_CODING_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
PROVIDER_SETUP_GUIDE_PATH = "docs/product/2026-04-03-aionis-provider-setup-guide.md"
SAFE_CREDENTIALS_HINT = (
    f"load model credentials from local env or .env (see {PROVIDER_SETUP_GUIDE_PATH})"
)


@dataclass(frozen=True)
class ProviderProfile:
    provider_id: str
    label: str
    provider: str
    base_url: str | None
    model: str
    timeout_seconds: int
    max_completion_tokens: int
    supports_live: bool
    release_tier: str
    env_var_names: tuple[str, ...]


_BUILTIN_PROFILES: dict[str, ProviderProfile] = {
    "zai_glm51_coding": ProviderProfile(
        provider_id="zai_glm51_coding",
        label="Z.AI GLM-5.1 Coding",
        provider="openai",
        base_url=ZAI_CODING_BASE_URL,
        model="glm-5.1",
        timeout_seconds=15,
        max_completion_tokens=256,
        supports_live=True,
        release_tier="manual_verified",
        env_var_names=("OPENAI_API_KEY", "OPENAI_BASE_URL", "WORKBENCH_MODEL"),
    ),
    "openai_default": ProviderProfile(
        provider_id="openai_default",
        label="OpenAI Default",
        provider="openai",
        base_url=None,
        model="gpt-5",
        timeout_seconds=45,
        max_completion_tokens=8192,
        supports_live=True,
        release_tier="experimental",
        env_var_names=("OPENAI_API_KEY", "WORKBENCH_MODEL"),
    ),
    "openrouter_default": ProviderProfile(
        provider_id="openrouter_default",
        label="OpenRouter Default",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-5.4",
        timeout_seconds=45,
        max_completion_tokens=8192,
        supports_live=True,
        release_tier="experimental",
        env_var_names=("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "OPENROUTER_MODEL"),
    ),
}


def list_provider_profiles() -> list[ProviderProfile]:
    return list(_BUILTIN_PROFILES.values())


def get_provider_profile(provider_id: str) -> ProviderProfile:
    try:
        return _BUILTIN_PROFILES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Unknown provider profile: {provider_id}") from exc


def infer_provider_profile_id(env: Mapping[str, str] | None = None) -> str | None:
    values = env or os.environ
    explicit = str(values.get("AIONIS_PROVIDER_PROFILE") or "").strip()
    if explicit:
        return explicit

    openai_key = bool(str(values.get("OPENAI_API_KEY") or "").strip())
    openrouter_key = bool(str(values.get("OPENROUTER_API_KEY") or "").strip())
    base_url = str(values.get("OPENAI_BASE_URL") or "").strip()
    model = str(values.get("WORKBENCH_MODEL") or "").strip()

    if openai_key and base_url == ZAI_CODING_BASE_URL:
        return "zai_glm51_coding"

    if openai_key and model == "glm-5.1" and not base_url:
        return "zai_glm51_coding"

    if openai_key and (base_url or model):
        return "openai_default"

    if openrouter_key:
        return "openrouter_default"

    if openai_key:
        if base_url == ZAI_CODING_BASE_URL:
            return "zai_glm51_coding"
        return "openai_default"

    return None


def resolve_provider_profile(env: Mapping[str, str] | None = None) -> ProviderProfile | None:
    provider_id = infer_provider_profile_id(env)
    if not provider_id:
        return None
    return get_provider_profile(provider_id)


def provider_profile_has_required_credentials(
    profile: ProviderProfile | None,
    env: Mapping[str, str] | None = None,
) -> bool:
    if profile is None:
        return False
    values = env or os.environ
    if profile.provider == "openrouter":
        return bool(str(values.get("OPENROUTER_API_KEY") or "").strip())
    if profile.provider == "openai":
        return bool(str(values.get("OPENAI_API_KEY") or "").strip())
    return False
