# Aionisdoc -> Workbench Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate `Aionisdoc` into `Aionis Workbench` as a structured workflow sidecar so Workbench can compile, run, publish, recover, and resume `.aionis.md` workflows while preserving the current session/memory/dream product surfaces.

**Architecture:** Do not merge `Aionisdoc` into the existing Python execution host. Phase 1 should treat `Aionisdoc` as an external Node-backed workflow toolchain accessed through a thin Python bridge and surfaced through new Workbench shell/CLI commands. The first slice should keep `Aionisdoc` execution isolated, then project its results into Workbench session artifacts, continuity, and later AutoDream.

**Tech Stack:** Python 3.11+, existing `aionis_workbench` shell/runtime services, `subprocess`, Node-based `@aionis/doc` CLI/runtime, existing Aionis runtime handoff/recover routes, `pytest`.

## Implementation Status

As of 2026-04-03, Phase 1 has been implemented end-to-end.

Completed:

- Task 1: `AionisdocBridge`
- Task 2: `AionisdocService`
- Task 3: Workbench runtime facade methods
- Task 4: `aionis doc ...` non-interactive CLI
- Task 5: `/doc ...` shell dispatch and rendering
- Task 6: session artifact + continuity persistence for doc results
- Task 7: publish -> recover -> resume product-path regression
- Task 8: operator guidance in README + dedicated product guide

Latest broad regression used during this rollout:

```text
205 passed
```

---

## Product Thesis

`Workbench` is already good at:

- session continuity
- family reuse
- recovery
- AutoDream and deprecation

`Aionisdoc` adds a missing asset class:

- executable workflow documents
- module-registry-backed deterministic execution
- structured runtime handoff / publish / recover / resume

The integration should therefore treat `.aionis.md` files as:

- first-class workflow artifacts
- resumable execution assets
- learnable reusable patterns

The goal is not “add doc support” in a superficial sense. The goal is:

- let Workbench remember, inspect, execute, publish, recover, and later promote document-shaped workflows

## Explicit Phase 1 Scope

Phase 1 should deliver:

- a Python bridge from Workbench to `@aionis/doc`
- standalone compile/run/execute surfaces in Workbench
- runtime publish/recover/resume surfaces in Workbench
- shell/CLI entrypoints for doc workflows
- session artifact persistence for doc results

Phase 1 should not deliver:

- replacing the existing DeepAgents execution host
- automatic AutoDream promotion from doc workflows
- inline editor integration work
- registry authoring UX inside Workbench

## Existing Source of Truth

The plan assumes these components remain authoritative:

- `Aionisdoc` package:
  - `/Users/lucio/Desktop/Aionis/packages/aionis-doc`
- `Aionisdoc` VS Code / Cursor extension:
  - `/Users/lucio/Desktop/Aionis/packages/aionis-doc-vscode`
- Workbench:
  - `/Volumes/ziel/Aioniscli/Aionis/workbench`

Primary references:

- `/Users/lucio/Desktop/Aionis/packages/aionis-doc/src/run.ts`
- `/Users/lucio/Desktop/Aionis/packages/aionis-doc/src/runtime-handoff.ts`
- `/Users/lucio/Desktop/Aionis/packages/aionis-doc/src/publish.ts`
- `/Users/lucio/Desktop/Aionis/packages/aionis-doc/src/recover.ts`
- `/Users/lucio/Desktop/Aionis/packages/aionis-doc/src/resume.ts`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/ops_service.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`

## Phase 1 Command Shape

After this plan lands, the target shell surface should look like:

```text
/doc compile ./workflow.aionis.md
/doc run ./workflow.aionis.md --registry ./module-registry.json
/doc publish ./workflow.aionis.md
/doc recover ./workflow.aionis.md
/doc resume ./recover-result.json --input-kind recover-result
```

And the non-interactive CLI should look like:

```bash
aionis doc compile --repo-root /absolute/path/to/repo --input ./workflow.aionis.md
aionis doc run --repo-root /absolute/path/to/repo --input ./workflow.aionis.md --registry ./module-registry.json
aionis doc publish --repo-root /absolute/path/to/repo --input ./workflow.aionis.md
aionis doc recover --repo-root /absolute/path/to/repo --input ./workflow.aionis.md
aionis doc resume --repo-root /absolute/path/to/repo --input ./recover-result.json --input-kind recover-result
```

## Task 1: Add a minimal bridge that invokes `@aionis/doc` CLIs from Workbench

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionisdoc_bridge.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_aionisdoc_bridge.py`

**Step 1: Write the failing test**

```python
from aionis_workbench.aionisdoc_bridge import AionisdocBridge


def test_bridge_builds_compile_command(tmp_path):
    bridge = AionisdocBridge(workspace_root=tmp_path)
    command = bridge.build_compile_command(input_path="workflow.aionis.md")
    assert command[-2:] == ["compile-aionis-doc", "workflow.aionis.md"]
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_aionisdoc_bridge.py -q`
Expected: FAIL because `aionisdoc_bridge.py` does not exist

**Step 3: Write minimal implementation**

Create a bridge that knows:

- where the external Aionis workspace lives
- where `packages/aionis-doc/dist/*.js` live
- how to construct subprocess commands for:
  - compile
  - run
  - execute
  - publish
  - recover
  - resume

Keep it dumb:

- no product logic
- only path resolution, invocation, and JSON parsing

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_aionisdoc_bridge.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/aionisdoc_bridge.py tests/test_aionisdoc_bridge.py
git commit -m "feat: add aionisdoc bridge"
```

## Task 2: Add a service layer that maps bridge results into Workbench-friendly payloads

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/aionisdoc_service.py`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_aionisdoc_service.py`

**Step 1: Write the failing test**

```python
from aionis_workbench.aionisdoc_service import AionisdocService


def test_compile_payload_exposes_shell_view():
    service = AionisdocService(bridge=...)
    payload = service.compile(input_path="workflow.aionis.md")
    assert payload["shell_view"] == "doc_compile"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_aionisdoc_service.py -q`
Expected: FAIL because `AionisdocService` does not exist

**Step 3: Write minimal implementation**

Add methods:

- `compile(...)`
- `run(...)`
- `publish(...)`
- `recover(...)`
- `resume(...)`

Each method should return a Workbench payload with:

- `shell_view`
- `doc_input`
- `doc_action`
- `status`
- parsed JSON result under a stable key

This is the boundary between raw `Aionisdoc` JSON and Workbench product surfaces.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_aionisdoc_service.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/aionisdoc_service.py tests/test_aionisdoc_service.py
git commit -m "feat: add aionisdoc service"
```

## Task 3: Wire `AionisdocService` into Workbench runtime as a sidecar capability

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/runtime.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

```python
def test_workbench_exposes_doc_compile_surface():
    workbench = AionisWorkbench(repo_root="/tmp/repo")
    payload = workbench.doc_compile(input_path="workflow.aionis.md")
    assert payload["shell_view"] == "doc_compile"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
Expected: FAIL because the Workbench runtime has no doc methods

**Step 3: Write minimal implementation**

Add thin runtime facade methods:

- `doc_compile`
- `doc_run`
- `doc_publish`
- `doc_recover`
- `doc_resume`

Runtime should not own `Aionisdoc` logic. It should only delegate to `AionisdocService`.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/runtime.py tests/test_product_workflows.py
git commit -m "feat: expose aionisdoc surfaces from runtime"
```

## Task 4: Add non-interactive CLI commands for doc compile/run/publish/recover/resume

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/cli.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

```python
def test_parser_accepts_doc_compile_mode():
    parser = build_parser()
    args = parser.parse_args(["doc", "compile", "--repo-root", "/tmp/repo", "--input", "workflow.aionis.md"])
    assert args.command == "doc"
    assert args.doc_command == "compile"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py -q`
Expected: FAIL because nested `doc` subcommands do not exist

**Step 3: Write minimal implementation**

Add:

- `aionis doc compile`
- `aionis doc run`
- `aionis doc publish`
- `aionis doc recover`
- `aionis doc resume`

Required flags:

- `--input`
- `--registry` for `run`
- `--input-kind` for `resume`

Keep output structured and shell-friendly.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_cli_shell.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/cli.py tests/test_cli_shell.py
git commit -m "feat: add aionis doc cli commands"
```

## Task 5: Add shell dispatch and rendering for `/doc ...`

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell_dispatch.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/shell.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_shell_dispatch.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_cli_shell.py`

**Step 1: Write the failing test**

```python
def test_dispatch_routes_doc_compile():
    payload = dispatch_shell_command(workbench, "/doc compile ./workflow.aionis.md")
    assert payload["shell_view"] == "doc_compile"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_shell_dispatch.py tests/test_cli_shell.py -q`
Expected: FAIL because `/doc` is unknown

**Step 3: Write minimal implementation**

Add `/doc` subcommands:

- `/doc compile PATH`
- `/doc run PATH --registry PATH`
- `/doc publish PATH`
- `/doc recover PATH`
- `/doc resume PATH --input-kind KIND`

Rendering should show:

- action
- input path
- status
- summary line

Avoid raw JSON unless shell raw mode is enabled.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_shell_dispatch.py tests/test_cli_shell.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/shell_dispatch.py src/aionis_workbench/shell.py tests/test_shell_dispatch.py tests/test_cli_shell.py
git commit -m "feat: add aionisdoc shell commands"
```

## Task 6: Persist doc execution outputs as session artifacts and continuity evidence

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/session_service.py`
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/src/aionis_workbench/surface_service.py`
- Test: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

```python
def test_doc_publish_result_is_recorded_as_session_artifact():
    ...
    assert any(item["kind"] == "doc_runtime_handoff" for item in session["artifacts"])
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
Expected: FAIL because doc results are not persisted into session artifacts

**Step 3: Write minimal implementation**

When a doc action succeeds, persist:

- source doc path
- compile/run/publish/recover/resume output
- runtime handoff anchor when present
- artifact refs and evidence refs when present

Store them as structured artifacts, not only summary text.

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/aionis_workbench/session_service.py src/aionis_workbench/surface_service.py tests/test_product_workflows.py
git commit -m "feat: persist aionisdoc outputs as session artifacts"
```

## Task 7: Add a product-path scenario for doc publish -> recover -> resume

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/tests/test_product_workflows.py`

**Step 1: Write the failing test**

```python
def test_product_doc_workflow_supports_publish_recover_resume():
    ...
    assert publish_payload["status"] == "ok"
    assert recover_payload["status"] == "ok"
    assert resume_payload["status"] == "ok"
```

**Step 2: Run test to verify it fails**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
Expected: FAIL because the end-to-end workflow is not yet wired

**Step 3: Write minimal implementation**

Use bridge/service stubs first.
The acceptance is the Workbench contract:

- compile result is surfaced
- publish result is surfaced
- recover result is surfaced
- resume result is surfaced
- session continuity includes the doc workflow chain

**Step 4: Run test to verify it passes**

Run: `cd /Volumes/ziel/Aioniscli/Aionis/workbench && .venv/bin/python -m pytest tests/test_product_workflows.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_product_workflows.py
git commit -m "test: cover aionisdoc workflow lifecycle"
```

## Task 8: Add documentation and operator guidance

**Files:**
- Modify: `/Volumes/ziel/Aioniscli/Aionis/workbench/README.md`
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/product/2026-04-03-aionisdoc-workbench-guide.md`

**Step 1: Write the docs checklist**

Document:

- what `Aionisdoc` is
- why it is a sidecar in phase 1
- which commands exist
- where module registries come from
- what data is persisted back into Workbench

**Step 2: Run CLI sanity checks**

Run:

```bash
cd /Volumes/ziel/Aioniscli/Aionis/workbench
.venv/bin/python -m pytest tests/test_aionisdoc_bridge.py tests/test_aionisdoc_service.py tests/test_cli_shell.py tests/test_shell_dispatch.py tests/test_product_workflows.py -q
```

Expected: PASS

**Step 3: Write minimal implementation**

Add:

- one README section
- one dedicated product guide
- one example `.aionis.md` flow

**Step 4: Run final sanity again**

Run the same command and verify it stays green.

**Step 5: Commit**

```bash
git add README.md docs/product/2026-04-03-aionisdoc-workbench-guide.md
git commit -m "docs: add aionisdoc workbench guide"
```

## Phase 2 Follow-Up

Only after Phase 1 lands should Workbench consider:

- indexing doc workflow outcomes into AutoDream
- promoting successful `.aionis.md` flows into reusable family workflow assets
- using `Aionisdoc` workflows as candidate playbooks in runtime replay/promotion
- tighter Cursor / VS Code integration between the existing `aionis-doc-vscode` extension and Workbench shell state

## Acceptance Criteria

Phase 1 is complete when all of these are true:

- Workbench can compile, run, publish, recover, and resume `Aionisdoc` workflows through a stable sidecar bridge
- shell and non-interactive CLI both expose doc workflow operations
- doc results are persisted as structured session artifacts
- a publish -> recover -> resume product path is covered by tests
- existing Workbench execution host boundaries remain intact

## Risks

- external desktop Aionis workspace path may need to be configurable instead of hardcoded
- Node-side CLI output shape may drift if `@aionis/doc` changes
- bridge subprocess behavior may be slower or noisier than a future direct library integration
- registry discovery needs care; phase 1 should prefer explicit `--registry`

## Non-Goals

- replacing Workbench's DeepAgents path
- embedding the VS Code / Cursor extension into Workbench
- building a full registry authoring UI
- making `Aionisdoc` the only workflow representation in Aionis
