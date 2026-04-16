from __future__ import annotations

import json
import shutil

from aionis_workbench.delivery_workspace import DeliveryWorkspaceAdapter


def test_delivery_workspace_infers_artifact_paths_and_preview_command(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite"}}),
        encoding="utf-8",
    )
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: ["src/App.tsx", "index.html"],
    )

    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["src/App.tsx"],
        workspace_root=tmp_path,
    )

    assert artifact_paths[:3] == ["index.html", "package.json", "src/App.tsx"]
    assert "src/App.tsx" in artifact_paths
    assert adapter.infer_artifact_kind(artifact_paths=artifact_paths) == "workspace_app"
    assert adapter.infer_preview_command(artifact_paths=artifact_paths) == (
        "npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173"
    )


def test_delivery_workspace_scaffolds_task_workspace_and_uses_workspace_preview_command(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.ensure_react_app_workspace(
        task_id="artifact-trial-1",
        title="Stateful Visual Dependency Explorer",
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["src/App.tsx"],
        workspace_root=workspace_root,
    )

    assert workspace_root == tmp_path / ".aionis-workbench" / "delivery-workspaces" / "artifact-trial-1"
    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "src" / "App.tsx").exists()
    assert artifact_paths[:3] == ["index.html", "package.json", "src/main.tsx"]
    assert adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=workspace_root,
    ) == (
        f"cd {workspace_root} && npm install --no-fund --no-audit "
        "&& npm run dev -- --host 0.0.0.0 --port 4173"
    )


def test_delivery_workspace_can_prepare_empty_task_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.ensure_empty_task_workspace(task_id="empty-bootstrap-1")

    assert workspace_root == tmp_path / ".aionis-workbench" / "delivery-workspaces" / "empty-bootstrap-1"
    assert workspace_root.exists()
    assert list(workspace_root.iterdir()) == []


def test_delivery_workspace_reset_task_workspace_recovers_when_rmtree_leaves_hidden_cache(tmp_path, monkeypatch) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.ensure_empty_task_workspace(task_id="reset-hidden-cache-1")
    cache_dir = workspace_root / ".vite" / "deps"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "chunk.js").write_text("console.log('cached')", encoding="utf-8")

    original_rmtree = shutil.rmtree
    call_state = {"count": 0}

    def _failing_rmtree(path, *args, **kwargs):
        call_state["count"] += 1
        if call_state["count"] == 1:
            raise OSError(66, "Directory not empty")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("aionis_workbench.delivery_workspace.shutil.rmtree", _failing_rmtree)

    reset_root = adapter.reset_task_workspace(task_id="reset-hidden-cache-1")

    assert reset_root == workspace_root
    assert not reset_root.exists()


def test_delivery_workspace_can_bootstrap_minimal_empty_web_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.bootstrap_empty_web_workspace(
        task_id="empty-bootstrap-2",
        title="Empty Bootstrap",
    )

    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "index.html").exists()
    assert (workspace_root / "src" / "main.tsx").exists()
    assert (workspace_root / "src" / "App.tsx").exists()
    assert (workspace_root / "src" / "styles.css").exists()


def test_delivery_workspace_can_bootstrap_minimal_vue_web_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.bootstrap_empty_vue_web_workspace(
        task_id="empty-vue-web-1",
        title="Vue Empty Bootstrap",
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["src/App.vue"],
        workspace_root=workspace_root,
    )

    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "index.html").exists()
    assert (workspace_root / "src" / "main.ts").exists()
    assert (workspace_root / "src" / "App.vue").exists()
    assert (workspace_root / "src" / "styles.css").exists()
    assert adapter.infer_artifact_kind(artifact_paths=artifact_paths) == "workspace_app"
    assert adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=workspace_root,
    ) == (
        f"cd {workspace_root} && npm install --no-fund --no-audit "
        "&& npm run dev -- --host 0.0.0.0 --port 4173"
    )


def test_delivery_workspace_can_bootstrap_minimal_svelte_web_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.bootstrap_empty_svelte_web_workspace(
        task_id="empty-svelte-web-1",
        title="Svelte Empty Bootstrap",
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["src/App.svelte"],
        workspace_root=workspace_root,
    )

    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "svelte.config.js").exists()
    assert (workspace_root / "index.html").exists()
    assert (workspace_root / "src" / "main.ts").exists()
    assert (workspace_root / "src" / "App.svelte").exists()
    assert (workspace_root / "src" / "app.css").exists()
    assert adapter.infer_artifact_kind(artifact_paths=artifact_paths) == "workspace_app"
    assert adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=workspace_root,
    ) == (
        f"cd {workspace_root} && npm install --no-fund --no-audit "
        "&& npm run dev -- --host 0.0.0.0 --port 4173"
    )


def test_delivery_workspace_can_bootstrap_minimal_nextjs_web_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.bootstrap_empty_nextjs_web_workspace(
        task_id="empty-nextjs-web-1",
        title="Next Empty Bootstrap",
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["app/page.tsx"],
        workspace_root=workspace_root,
    )

    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "next.config.mjs").exists()
    assert (workspace_root / "next-env.d.ts").exists()
    assert (workspace_root / "app" / "layout.tsx").exists()
    assert (workspace_root / "app" / "page.tsx").exists()
    assert (workspace_root / "app" / "globals.css").exists()
    assert adapter.infer_artifact_kind(artifact_paths=artifact_paths) == "nextjs_workspace"
    assert adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=workspace_root,
    ) == f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev"


def test_delivery_workspace_can_bootstrap_minimal_python_api_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.bootstrap_empty_python_api_workspace(
        task_id="empty-python-api-1",
        title="Agent Platform API",
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["main.py"],
        workspace_root=workspace_root,
    )

    assert (workspace_root / "requirements.txt").exists()
    assert (workspace_root / "main.py").exists()
    assert adapter.infer_artifact_kind(artifact_paths=artifact_paths) == "python_api_workspace"
    assert adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=workspace_root,
    ) == (
        f"cd {workspace_root} && python3 -m pip install -r requirements.txt && "
        "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
    )


def test_delivery_workspace_can_bootstrap_minimal_node_api_workspace(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.bootstrap_empty_node_api_workspace(
        task_id="empty-node-api-1",
        title="Agent Platform Node API",
    )
    artifact_paths = adapter.infer_artifact_paths(
        changed_files=["main.js"],
        workspace_root=workspace_root,
    )

    assert (workspace_root / "package.json").exists()
    assert (workspace_root / "main.js").exists()
    assert adapter.infer_artifact_kind(artifact_paths=artifact_paths) == "node_api_workspace"
    assert adapter.infer_preview_command(
        artifact_paths=artifact_paths,
        workspace_root=workspace_root,
    ) == f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev"


def test_delivery_workspace_scaffold_includes_generic_delivery_starter(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )

    workspace_root = adapter.ensure_react_app_workspace(
        task_id="artifact-trial-3",
        title="Stateful Visual Dependency Explorer",
    )
    app_source = (workspace_root / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "useState" in app_source
    assert "localStorage" in app_source
    assert "Aionis Delivery Starter" in app_source
    assert "Featured Value Props" in app_source
    assert "Book a guided walkthrough" in app_source


def test_delivery_workspace_detects_changed_files_from_workspace_snapshot(tmp_path) -> None:
    adapter = DeliveryWorkspaceAdapter(
        repo_root=str(tmp_path),
        collect_changed_files_fn=lambda: [],
    )
    workspace_root = adapter.ensure_react_app_workspace(
        task_id="artifact-trial-2",
        title="Stateful Visual Dependency Explorer",
    )

    before = adapter.snapshot_workspace_state(workspace_root=workspace_root)
    app_file = workspace_root / "src" / "App.tsx"
    app_file.write_text(app_file.read_text(encoding="utf-8") + "\nexport const touched = true;\n", encoding="utf-8")
    after = adapter.snapshot_workspace_state(workspace_root=workspace_root)

    assert adapter.changed_workspace_files(before=before, after=after) == ["src/App.tsx"]
