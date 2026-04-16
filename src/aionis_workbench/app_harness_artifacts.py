from __future__ import annotations

import json
import shlex
from pathlib import Path

from .app_harness_models import AppHarnessState, SprintContract, SprintExecutionAttempt, SprintRevision
from .session import ArtifactReference, SessionState, artifact_dir, project_artifact_dir


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "artifact"


def _seed_nodes(
    *,
    sprint: SprintContract,
    revision: SprintRevision | None,
    attempt: SprintExecutionAttempt,
) -> list[dict[str, object]]:
    labels: list[str] = []
    labels.extend(sprint.scope[:4])
    labels.extend(sprint.acceptance_checks[:2])
    labels.extend(attempt.changed_target_hints[:4])
    if revision is not None:
        labels.extend(revision.must_fix[:3])
        labels.extend(revision.must_keep[:2])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in labels:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    if not deduped:
        deduped = [sprint.goal.strip() or sprint.sprint_id]
    nodes: list[dict[str, object]] = []
    for index, label in enumerate(deduped[:8]):
        category = "workflow"
        lowered = label.lower()
        if "/" in label or "." in Path(label).name:
            category = "target"
        elif "pytest" in lowered or "check" in lowered:
            category = "check"
        elif revision is not None and label in revision.must_fix:
            category = "risk"
        nodes.append(
            {
                "id": f"node-{index + 1}",
                "label": label,
                "category": category,
                "detail": f"{label} is part of {sprint.sprint_id} and feeds the bounded execution attempt.",
                "timeline": [
                    f"planned: {sprint.goal}",
                    f"attempt: {attempt.execution_summary}",
                    f"focus: {label}",
                ],
            }
        )
    return nodes


def _render_html(
    *,
    session: SessionState,
    state: AppHarnessState,
    sprint: SprintContract,
    revision: SprintRevision | None,
    attempt: SprintExecutionAttempt,
) -> str:
    nodes = _seed_nodes(sprint=sprint, revision=revision, attempt=attempt)
    filters = sorted({str(item.get("category") or "workflow") for item in nodes})
    title = (state.product_spec.title if state.product_spec else "").strip() or "Stateful Visual Dependency Explorer"
    payload = {
        "title": title,
        "task_id": session.task_id,
        "sprint_id": sprint.sprint_id,
        "goal": sprint.goal,
        "summary": attempt.execution_summary,
        "filters": filters,
        "nodes": nodes,
    }
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3efe7;
      --panel: #fffaf2;
      --ink: #10243d;
      --muted: #6f7d8c;
      --line: #d8c8ab;
      --accent: #c95f2d;
      --accent-soft: #fde2d6;
      --graph: #174e77;
      --timeline: #214f44;
      --shadow: 0 16px 42px rgba(16, 36, 61, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(201, 95, 45, 0.14), transparent 30%),
        linear-gradient(180deg, #f8f3eb, var(--bg));
      color: var(--ink);
    }}
    .app {{
      min-height: 100vh;
      padding: 24px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 18px;
    }}
    .hero, .panel {{
      background: rgba(255, 250, 242, 0.9);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }}
    .hero {{
      padding: 22px 24px 18px;
      display: grid;
      gap: 12px;
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      font-size: 12px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(28px, 5vw, 52px);
      line-height: 0.98;
      max-width: 12ch;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .chip {{
      border: 1px solid var(--line);
      background: white;
      padding: 7px 11px;
      border-radius: 999px;
      font-size: 13px;
    }}
    .workspace {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(280px, 0.9fr);
      gap: 18px;
      min-height: 540px;
    }}
    .graph-panel {{
      padding: 18px;
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 14px;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .toolbar input, .toolbar select {{
      border-radius: 12px;
      border: 1px solid var(--line);
      background: white;
      padding: 12px 14px;
      font: inherit;
      min-width: 0;
    }}
    .toolbar input {{ flex: 1 1 220px; }}
    .legend {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 13px;
    }}
    .graph {{
      border-radius: 18px;
      border: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(23, 78, 119, 0.07), rgba(23, 78, 119, 0.01)),
        repeating-linear-gradient(
          0deg,
          transparent 0,
          transparent 24px,
          rgba(16, 36, 61, 0.04) 24px,
          rgba(16, 36, 61, 0.04) 25px
        );
      padding: 16px;
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      align-content: start;
    }}
    .node {{
      border: 1px solid rgba(23, 78, 119, 0.18);
      background: white;
      border-radius: 16px;
      min-height: 110px;
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
      text-align: left;
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
    }}
    .node:hover, .node:focus-visible {{
      transform: translateY(-2px);
      border-color: var(--accent);
      box-shadow: 0 12px 20px rgba(23, 78, 119, 0.12);
      outline: none;
    }}
    .node[data-selected="true"] {{
      border-color: var(--accent);
      background: linear-gradient(180deg, white, var(--accent-soft));
    }}
    .node small {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-size: 11px;
    }}
    .detail-panel {{
      padding: 18px;
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 14px;
    }}
    .detail-panel h2, .timeline-panel h2 {{
      margin: 0;
      font-size: 18px;
    }}
    .detail-card, .timeline-panel {{
      padding: 18px;
    }}
    .detail-copy {{
      color: var(--muted);
      line-height: 1.5;
      white-space: pre-wrap;
    }}
    .timeline-panel {{
      min-height: 180px;
      display: grid;
      gap: 14px;
    }}
    .timeline-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .timeline-list li {{
      border-left: 3px solid var(--timeline);
      padding: 0 0 0 12px;
      color: var(--ink);
    }}
    .empty {{
      color: var(--muted);
      font-style: italic;
    }}
    @media (max-width: 900px) {{
      .workspace {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <section class="hero">
      <div class="eyebrow">Artifact Trial Demo</div>
      <h1>{title}</h1>
      <div class="hero-meta">
        <span class="chip">task={session.task_id}</span>
        <span class="chip">sprint={sprint.sprint_id}</span>
        <span class="chip">mode={attempt.execution_mode}</span>
        <span class="chip">summary={attempt.execution_summary}</span>
      </div>
    </section>
    <section class="workspace">
      <section class="hero panel graph-panel">
        <div class="toolbar">
          <input id="search" type="search" placeholder="Filter nodes, files, or checks" />
          <select id="category"></select>
        </div>
        <div class="legend" id="legend"></div>
        <div class="graph" id="graph"></div>
      </section>
      <section class="panel detail-panel">
        <div>
          <div class="eyebrow">Selected Node</div>
          <h2 id="detail-title">Choose a graph node</h2>
        </div>
        <div class="detail-card">
          <div class="detail-copy" id="detail-copy">The detail panel and timeline will update together. Selection and filters persist across refresh.</div>
        </div>
        <div class="panel timeline-panel">
          <div class="eyebrow">Timeline Focus</div>
          <h2 id="timeline-title">No selection yet</h2>
          <ul class="timeline-list" id="timeline"></ul>
        </div>
      </section>
    </section>
  </div>
  <script id="seed" type="application/json">{_json_script(payload)}</script>
  <script>
    const seed = JSON.parse(document.getElementById("seed").textContent);
    const storageKey = "aionis-artifact-demo:" + seed.task_id + ":" + seed.sprint_id;
    const graph = document.getElementById("graph");
    const search = document.getElementById("search");
    const category = document.getElementById("category");
    const legend = document.getElementById("legend");
    const detailTitle = document.getElementById("detail-title");
    const detailCopy = document.getElementById("detail-copy");
    const timelineTitle = document.getElementById("timeline-title");
    const timeline = document.getElementById("timeline");

    const initial = (() => {{
      try {{
        return JSON.parse(localStorage.getItem(storageKey) || "{{}}");
      }} catch (error) {{
        return {{}};
      }}
    }})();

    const state = {{
      search: typeof initial.search === "string" ? initial.search : "",
      category: typeof initial.category === "string" ? initial.category : "all",
      selectedNodeId: typeof initial.selectedNodeId === "string" ? initial.selectedNodeId : "",
    }};

    function persist() {{
      localStorage.setItem(storageKey, JSON.stringify(state));
    }}

    function visibleNodes() {{
      const query = state.search.trim().toLowerCase();
      return seed.nodes.filter((node) => {{
        const label = String(node.label || "").toLowerCase();
        const categoryMatch = state.category === "all" || node.category === state.category;
        const queryMatch = !query || label.includes(query);
        return categoryMatch && queryMatch;
      }});
    }}

    function ensureSelection(nodes) {{
      if (!nodes.length) {{
        state.selectedNodeId = "";
        return null;
      }}
      const current = nodes.find((node) => node.id === state.selectedNodeId);
      if (current) {{
        return current;
      }}
      state.selectedNodeId = String(nodes[0].id);
      persist();
      return nodes[0];
    }}

    function renderDetail(selected) {{
      if (!selected) {{
        detailTitle.textContent = "No matching node";
        detailCopy.textContent = "Adjust the search or filter to recover a visible graph path.";
        timelineTitle.textContent = "No timeline focus";
        timeline.innerHTML = '<li class="empty">No timeline entries are visible.</li>';
        return;
      }}
      detailTitle.textContent = String(selected.label || "Selected node");
      detailCopy.textContent = String(selected.detail || "No detail available.");
      timelineTitle.textContent = String(selected.label || "Selected node") + " timeline";
      const items = Array.isArray(selected.timeline) ? selected.timeline : [];
      timeline.innerHTML = items.map((item) => "<li>" + item + "</li>").join("") || '<li class="empty">No timeline entries.</li>';
    }}

    function renderLegend() {{
      legend.innerHTML = seed.filters.map((item) => "<span class=\\"chip\\">" + item + "</span>").join("");
      category.innerHTML = ['<option value="all">All categories</option>']
        .concat(seed.filters.map((item) => "<option value=\\"" + item + "\\">" + item + "</option>"))
        .join("");
      category.value = seed.filters.includes(state.category) ? state.category : "all";
    }}

    function renderGraph() {{
      const nodes = visibleNodes();
      const selected = ensureSelection(nodes);
      graph.innerHTML = nodes.map((node) => {{
        const selectedFlag = node.id === state.selectedNodeId ? "true" : "false";
        return `
          <button class="node" type="button" data-node-id="${{node.id}}" data-selected="${{selectedFlag}}">
            <small>${{node.category}}</small>
            <strong>${{node.label}}</strong>
            <span>${{(node.timeline || [])[0] || seed.goal}}</span>
          </button>
        `;
      }}).join("") || '<div class="empty">No nodes match the current filter.</div>';
      graph.querySelectorAll("[data-node-id]").forEach((button) => {{
        button.addEventListener("click", () => {{
          state.selectedNodeId = button.getAttribute("data-node-id") || "";
          persist();
          renderGraph();
        }});
      }});
      renderDetail(selected);
    }}

    search.value = state.search;
    search.addEventListener("input", (event) => {{
      state.search = event.target.value;
      persist();
      renderGraph();
    }});
    category.addEventListener("change", (event) => {{
      state.category = event.target.value;
      persist();
      renderGraph();
    }});

    renderLegend();
    renderGraph();
  </script>
</body>
</html>
"""


def materialize_static_demo_artifact(
    *,
    session: SessionState,
    state: AppHarnessState,
    sprint: SprintContract,
    revision: SprintRevision | None,
    attempt: SprintExecutionAttempt,
) -> tuple[str, str, str, ArtifactReference]:
    artifact_root = artifact_dir(session.repo_root, session.task_id) / _slug(attempt.attempt_id)
    artifact_root.mkdir(parents=True, exist_ok=True)
    local_path = artifact_root / "index.html"
    local_path.write_text(
        _render_html(
            session=session,
            state=state,
            sprint=sprint,
            revision=revision,
            attempt=attempt,
        ),
        encoding="utf-8",
    )
    if session.project_scope:
        project_root = project_artifact_dir(session.project_scope, session.task_id) / _slug(attempt.attempt_id)
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "index.html").write_text(local_path.read_text(encoding="utf-8"), encoding="utf-8")
    rel_path = local_path.relative_to(Path(session.repo_root)).as_posix()
    preview_command = f"python3 -m http.server 4173 --directory {shlex.quote(str(local_path.parent))}"
    artifact = ArtifactReference(
        artifact_id=f"{session.task_id}:{attempt.attempt_id}:demo",
        kind="app_harness_demo_artifact",
        role="generator",
        summary=f"Static demo scaffold for {attempt.attempt_id}",
        path=rel_path,
        metadata={
            "sprint_id": sprint.sprint_id,
            "attempt_id": attempt.attempt_id,
            "preview_command": preview_command,
            "artifact_kind": "static_html_demo",
        },
    )
    return ("static_html_demo", rel_path, preview_command, artifact)
