from __future__ import annotations

from dataclasses import dataclass, field

from .provider_profiles import get_provider_profile


@dataclass(frozen=True)
class ReleaseGateResult:
    deterministic_ok: bool
    live_ok: bool
    provider_profile: str
    provider_release_tier: str
    provider_supports_live: bool
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        status = "passed" if self.passed else "failed"
        failures = "; ".join(self.failures) if self.failures else "none"
        return (
            f"release-gates: {status} "
            f"deterministic={'ok' if self.deterministic_ok else 'failed'} "
            f"live={'ok' if self.live_ok else 'failed'} "
            f"provider={self.provider_profile or 'unknown'} "
            f"tier={self.provider_release_tier or 'unknown'} "
            f"failures={failures}"
        )


def evaluate_release_gates(
    *,
    deterministic_exit_code: int,
    live_exit_code: int,
    provider_profile: str,
) -> ReleaseGateResult:
    deterministic_ok = deterministic_exit_code == 0
    live_ok = live_exit_code == 0

    failures: list[str] = []
    if not deterministic_ok:
        failures.append("deterministic_suite_failed")
    if not live_ok:
        failures.append("live_suite_failed")

    profile = get_provider_profile(provider_profile)
    if not profile.supports_live:
        failures.append("provider_does_not_support_live")
    if profile.release_tier not in {"manual_verified", "stable"}:
        failures.append("provider_not_approved_for_release")

    return ReleaseGateResult(
        deterministic_ok=deterministic_ok,
        live_ok=live_ok,
        provider_profile=profile.provider_id,
        provider_release_tier=profile.release_tier,
        provider_supports_live=profile.supports_live,
        failures=failures,
    )
