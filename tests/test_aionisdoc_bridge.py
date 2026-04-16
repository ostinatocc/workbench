from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aionis_workbench.aionisdoc_bridge import (
    AionisdocBridge,
    AionisdocBridgeError,
    AionisdocInvocationError,
    resolve_aionisdoc_fixture_source,
    resolve_aionisdoc_package_root,
)


def _make_fake_aionisdoc_workspace(tmp_path):
    dist = tmp_path / "DesktopAionis" / "packages" / "aionis-doc" / "dist"
    dist.mkdir(parents=True)
    for filename in (
        "cli.js",
        "run-cli.js",
        "execute-cli.js",
        "runtime-handoff-cli.js",
        "handoff-store-cli.js",
        "publish-cli.js",
        "recover-cli.js",
        "resume-cli.js",
    ):
        (dist / filename).write_text("// stub\n")
    (dist.parent / "package.json").write_text('{"name":"@aionis/doc"}\n')
    return tmp_path / "DesktopAionis"


def _make_fake_aionisdoc_package_root(root: Path) -> Path:
    dist = root / "dist"
    fixtures = root / "fixtures"
    dist.mkdir(parents=True)
    fixtures.mkdir(parents=True)
    for filename in (
        "cli.js",
        "run-cli.js",
        "execute-cli.js",
        "runtime-handoff-cli.js",
        "handoff-store-cli.js",
        "publish-cli.js",
        "recover-cli.js",
        "resume-cli.js",
    ):
        (dist / filename).write_text("// stub\n")
    (root / "package.json").write_text('{"name":"@aionis/doc"}\n')
    (fixtures / "valid-workflow.aionis.md").write_text("@doc { id: \"fixture\" version: \"1.0\" kind: \"task\" }\n")
    return root


def test_bridge_builds_compile_command(tmp_path) -> None:
    desktop_root = _make_fake_aionisdoc_workspace(tmp_path)
    bridge = AionisdocBridge(workspace_root=tmp_path, aionis_workspace_root=desktop_root, node_executable="node")

    command = bridge.build_compile_command(input_path="workflow.aionis.md")

    assert command[0] == "node"
    assert command[1].endswith("packages/aionis-doc/dist/cli.js")
    assert command[2:] == ["workflow.aionis.md", "--emit", "all", "--compact"]


def test_bridge_builds_run_command_with_registry_and_input_kind(tmp_path) -> None:
    desktop_root = _make_fake_aionisdoc_workspace(tmp_path)
    bridge = AionisdocBridge(workspace_root=tmp_path, aionis_workspace_root=desktop_root)

    command = bridge.build_run_command(
        input_path="workflow.aionis.md",
        registry_path="module-registry.json",
        input_kind="compile-envelope",
    )

    assert command[1].endswith("packages/aionis-doc/dist/run-cli.js")
    assert command[2:] == [
        "workflow.aionis.md",
        "--input-kind",
        "compile-envelope",
        "--registry",
        "module-registry.json",
        "--compact",
    ]


def test_bridge_builds_resume_command_with_candidates_and_filters(tmp_path) -> None:
    desktop_root = _make_fake_aionisdoc_workspace(tmp_path)
    bridge = AionisdocBridge(workspace_root=tmp_path, aionis_workspace_root=desktop_root)

    command = bridge.build_resume_command(
        input_path="recover-result.json",
        query_text="resume workflow",
        candidates=["read", "bash"],
        include_rules=True,
        rules_limit=5,
        strict=False,
    )

    assert command[1].endswith("packages/aionis-doc/dist/resume-cli.js")
    assert "--candidate" in command
    assert command.count("--candidate") == 2
    assert "--include-rules" in command
    assert "--no-strict" in command
    assert "--rules-limit" in command


def test_bridge_rejects_missing_entrypoint(tmp_path) -> None:
    desktop_root = tmp_path / "DesktopAionis"
    bridge = AionisdocBridge(workspace_root=tmp_path, aionis_workspace_root=desktop_root)

    with pytest.raises(AionisdocBridgeError, match="Aionisdoc entrypoint is missing"):
        bridge.build_compile_command(input_path="workflow.aionis.md")


def test_bridge_parses_json_stdout_even_when_process_exits_non_zero(tmp_path, monkeypatch) -> None:
    desktop_root = _make_fake_aionisdoc_workspace(tmp_path)
    bridge = AionisdocBridge(workspace_root=tmp_path, aionis_workspace_root=desktop_root)

    def fake_run(command, **kwargs):
        assert kwargs["cwd"] == str(tmp_path)
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout='{"status":"failed","errors":["module_missing"]}\n',
            stderr="execution failed",
        )

    monkeypatch.setattr("aionis_workbench.aionisdoc_bridge.subprocess.run", fake_run)

    result = bridge.run(input_path="workflow.aionis.md", registry_path="registry.json")

    assert result["status"] == "failed"
    assert result["errors"] == ["module_missing"]


def test_bridge_raises_when_command_produces_no_json(tmp_path, monkeypatch) -> None:
    desktop_root = _make_fake_aionisdoc_workspace(tmp_path)
    bridge = AionisdocBridge(workspace_root=tmp_path, aionis_workspace_root=desktop_root)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(args=command, returncode=2, stdout="", stderr="usage error")

    monkeypatch.setattr("aionis_workbench.aionisdoc_bridge.subprocess.run", fake_run)

    with pytest.raises(AionisdocInvocationError, match="produced no JSON output"):
        bridge.compile(input_path="workflow.aionis.md")


def test_bridge_prefers_explicit_package_root_over_workspace_root(tmp_path) -> None:
    workspace_root = _make_fake_aionisdoc_workspace(tmp_path)
    package_root = _make_fake_aionisdoc_package_root(tmp_path / "CustomPackageRoot")

    bridge = AionisdocBridge(
        workspace_root=tmp_path,
        aionis_workspace_root=workspace_root,
        aionis_package_root=package_root,
    )

    assert bridge.package_root == package_root.resolve()
    assert bridge.entrypoint_path("compile") == package_root.resolve() / "dist" / "cli.js"


def test_resolve_package_root_prefers_sibling_official_repo_before_legacy_desktop(tmp_path, monkeypatch) -> None:
    workbench_root = tmp_path / "sandbox" / "workbench"
    workbench_root.mkdir(parents=True)
    sibling_package_root = _make_fake_aionisdoc_package_root(tmp_path / "sandbox" / "AionisRuntime" / "packages" / "aionis-doc")
    legacy_workspace_root = _make_fake_aionisdoc_workspace(tmp_path)

    monkeypatch.setattr("aionis_workbench.aionisdoc_bridge._workbench_repo_root", lambda: workbench_root)
    monkeypatch.setenv("HOME", str(tmp_path))

    resolved = resolve_aionisdoc_package_root()

    assert resolved == sibling_package_root.resolve()
    assert resolved != legacy_workspace_root / "packages" / "aionis-doc"


def test_resolve_fixture_source_prefers_sibling_package_fixture(tmp_path, monkeypatch) -> None:
    workbench_root = tmp_path / "sandbox" / "workbench"
    workbench_root.mkdir(parents=True)
    sibling_package_root = _make_fake_aionisdoc_package_root(tmp_path / "sandbox" / "AionisCore" / "packages" / "aionis-doc")
    _make_fake_aionisdoc_workspace(tmp_path)

    monkeypatch.setattr("aionis_workbench.aionisdoc_bridge._workbench_repo_root", lambda: workbench_root)
    monkeypatch.setenv("HOME", str(tmp_path))

    resolved = resolve_aionisdoc_fixture_source()

    assert resolved == sibling_package_root / "fixtures" / "valid-workflow.aionis.md"
