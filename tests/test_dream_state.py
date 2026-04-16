from __future__ import annotations

from aionis_workbench.dream_state import (
    load_dream_candidates,
    load_dream_promotions,
    save_dream_candidates,
    save_dream_promotions,
)


def test_save_and_load_dream_candidates(tmp_path) -> None:
    _, project_path = save_dream_candidates(
        repo_root=str(tmp_path),
        project_scope="project:test/demo",
        payload={"candidates": []},
    )

    loaded = load_dream_candidates(repo_root=str(tmp_path), project_scope="project:test/demo")

    assert project_path.exists()
    assert loaded["candidates"] == []


def test_save_and_load_dream_promotions(tmp_path) -> None:
    local_path, _ = save_dream_promotions(
        repo_root=str(tmp_path),
        project_scope="project:test/demo",
        payload={"promotions": [{"prior_id": "prior-1"}]},
    )

    loaded = load_dream_promotions(repo_root=str(tmp_path), project_scope="project:test/demo")

    assert local_path.exists()
    assert loaded["promotions"][0]["prior_id"] == "prior-1"
