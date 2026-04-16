from __future__ import annotations

from aionis_workbench.aionisdoc_service import AionisdocService


class _FakeBridge:
    def compile(self, *, input_path: str, **kwargs):
        assert input_path == "workflow.aionis.md"
        return {
            "compile_result_version": "aionis_doc_compile_result_v1",
            "summary": {"has_errors": False},
            "diagnostics": [],
        }

    def run(self, *, input_path: str, registry_path: str, **kwargs):
        assert input_path == "workflow.aionis.md"
        assert registry_path == "module-registry.json"
        return {"status": "succeeded", "outputs": {"out.hero": "Hero copy"}}

    def publish(self, *, input_path: str, **kwargs):
        assert input_path == "workflow.aionis.md"
        return {"status": "published", "handoff_id": "handoff-1"}

    def recover(self, *, input_path: str, **kwargs):
        assert input_path == "publish-result.json"
        return {"status": "recovered", "handoff": {"summary": "Resume workflow"}}

    def resume(self, *, input_path: str, **kwargs):
        assert input_path == "recover-result.json"
        return {"status": "completed", "selected_tool": "read"}


class _FailingCompileBridge(_FakeBridge):
    def compile(self, *, input_path: str, **kwargs):
        return {
            "compile_result_version": "aionis_doc_compile_result_v1",
            "summary": {"has_errors": True},
            "diagnostics": [{"severity": "error", "message": "Bad directive"}],
        }


def test_compile_payload_exposes_shell_view() -> None:
    service = AionisdocService(repo_root="/tmp/demo", bridge=_FakeBridge())

    payload = service.compile(input_path="workflow.aionis.md")

    assert payload["shell_view"] == "doc_compile"
    assert payload["doc_action"] == "compile"
    assert payload["doc_input"] == "workflow.aionis.md"
    assert payload["status"] == "ok"
    assert payload["compile_result"]["compile_result_version"] == "aionis_doc_compile_result_v1"


def test_run_payload_exposes_registry_and_result() -> None:
    service = AionisdocService(repo_root="/tmp/demo", bridge=_FakeBridge())

    payload = service.run(input_path="workflow.aionis.md", registry_path="module-registry.json")

    assert payload["shell_view"] == "doc_run"
    assert payload["doc_action"] == "run"
    assert payload["doc_registry"] == "module-registry.json"
    assert payload["status"] == "succeeded"
    assert payload["run_result"]["outputs"]["out.hero"] == "Hero copy"


def test_publish_recover_resume_payloads_use_stable_keys() -> None:
    service = AionisdocService(repo_root="/tmp/demo", bridge=_FakeBridge())

    publish_payload = service.publish(input_path="workflow.aionis.md")
    recover_payload = service.recover(input_path="publish-result.json")
    resume_payload = service.resume(input_path="recover-result.json")

    assert publish_payload["publish_result"]["handoff_id"] == "handoff-1"
    assert recover_payload["recover_result"]["handoff"]["summary"] == "Resume workflow"
    assert resume_payload["resume_result"]["selected_tool"] == "read"


def test_compile_payload_marks_error_diagnostics_as_failed() -> None:
    service = AionisdocService(repo_root="/tmp/demo", bridge=_FailingCompileBridge())

    payload = service.compile(input_path="workflow.aionis.md")

    assert payload["status"] == "failed"
