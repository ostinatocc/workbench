from __future__ import annotations

from aionis_workbench.e2e.real_e2e.manifest import load_real_repo_manifest


def test_real_repo_manifest_loads() -> None:
    repos = load_real_repo_manifest()

    assert repos


def test_real_repo_manifest_entries_have_required_fields() -> None:
    repos = load_real_repo_manifest()

    for repo in repos:
        assert repo.id
        assert repo.repo_url
        assert repo.commit_sha


def test_real_repo_manifest_entries_have_scenario_tags() -> None:
    repos = load_real_repo_manifest()

    for repo in repos:
        assert repo.scenario_tags
