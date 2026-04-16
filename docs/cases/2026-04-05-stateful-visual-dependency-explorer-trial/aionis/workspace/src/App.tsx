import { useEffect, useMemo, useState } from "react";

type ExplorerNode = {
  id: string;
  label: string;
  kind: string;
  status: string;
  category: string;
  description: string;
  dependencies: string[];
  owners: string[];
  timeline: { phase: string; note: string; emphasis?: string }[];
};

const STORAGE_KEY = "aionis-dependency-explorer-state";

const nodes: ExplorerNode[] = [
  {
    id: "scheduler",
    label: "Task Scheduler",
    kind: "service",
    status: "ready",
    category: "control-plane",
    description: "Coordinates intake, task family routing, and sprint cadence for the active delivery loop.",
    dependencies: ["reviewer", "executor"],
    owners: ["planner", "operator"],
    timeline: [
      { phase: "Plan", note: "Derives the active sprint scope and validation pressure.", emphasis: "Sets the initial execution lane." },
      { phase: "Retry", note: "Re-opens the lane with narrower scope after QA pressure." },
      { phase: "Advance", note: "Hands the contract forward once the execution gate is ready." },
    ],
  },
  {
    id: "executor",
    label: "Delivery Executor",
    kind: "runtime",
    status: "active",
    category: "delivery",
    description: "Runs bounded implementation attempts inside the task workspace and records changed files.",
    dependencies: ["workspace", "reviewer"],
    owners: ["generator"],
    timeline: [
      { phase: "Generate", note: "Touches the task workspace and emits changed-file evidence.", emphasis: "Primary delivery edge." },
      { phase: "Validate", note: "Collects preview and validation commands for the latest attempt." },
      { phase: "Recover", note: "Feeds execution evidence back into retry and replan." },
    ],
  },
  {
    id: "reviewer",
    label: "Reviewer Gate",
    kind: "policy",
    status: "watching",
    category: "quality",
    description: "Tracks acceptance checks, blocker notes, and the policy transition from needs_qa to ready.",
    dependencies: ["executor"],
    owners: ["evaluator", "reviewer"],
    timeline: [
      { phase: "QA", note: "Scores the latest execution attempt against the sprint contract.", emphasis: "Controls the execution gate." },
      { phase: "Negotiate", note: "Produces objections and sharpens the next revision focus." },
      { phase: "Escalate", note: "Ends the sprint when retry budget is exhausted." },
    ],
  },
  {
    id: "workspace",
    label: "Task Workspace",
    kind: "artifact",
    status: "persisted",
    category: "delivery",
    description: "Stores the runnable app, preview command, and changed files for the active task id.",
    dependencies: ["scheduler"],
    owners: ["generator", "operator"],
    timeline: [
      { phase: "Bootstrap", note: "Scaffolds a Vite app even when the live model is unavailable." },
      { phase: "Export", note: "Copies the current artifact into a reviewable case directory.", emphasis: "Turns session state into a visible app." },
      { phase: "Persist", note: "Restores selection, filter, and timeline focus after refresh." },
    ],
  },
  {
    id: "timeline",
    label: "Sprint Timeline",
    kind: "surface",
    status: "tracking",
    category: "visibility",
    description: "Shows how the current node moves from planning to delivery and policy resolution.",
    dependencies: ["scheduler", "reviewer"],
    owners: ["operator"],
    timeline: [
      { phase: "Inspect", note: "Highlights the current node and recent gate transition." },
      { phase: "Compare", note: "Makes first-cycle and second-cycle convergence visible." },
      { phase: "Decide", note: "Shows whether the path is ready to advance or needs replan." },
    ],
  },
];

const categoryOptions = ["all", "control-plane", "delivery", "quality", "visibility"];

type PersistedState = {
  selectedNodeId?: string;
  query?: string;
  category?: string;
};

function readPersistedState(): PersistedState {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed ? parsed as PersistedState : {};
  } catch {
    return {};
  }
}

export default function App() {
  const persisted = readPersistedState();
  const [query, setQuery] = useState(persisted.query ?? "");
  const [category, setCategory] = useState(persisted.category ?? "all");
  const [selectedNodeId, setSelectedNodeId] = useState(persisted.selectedNodeId ?? nodes[0]?.id ?? "");

  const filteredNodes = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return nodes.filter((node) => {
      const matchesCategory = category === "all" || node.category === category;
      const haystack = [node.label, node.kind, node.description, ...node.dependencies, ...node.owners].join(" ").toLowerCase();
      const matchesQuery = !normalized || haystack.includes(normalized);
      return matchesCategory && matchesQuery;
    });
  }, [category, query]);

  useEffect(() => {
    if (!filteredNodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(filteredNodes[0]?.id ?? "");
    }
  }, [filteredNodes, selectedNodeId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ selectedNodeId, query, category }),
    );
  }, [category, query, selectedNodeId]);

  const selectedNode = filteredNodes.find((node) => node.id === selectedNodeId) ?? filteredNodes[0] ?? nodes[0];
  const visibleCount = filteredNodes.length;
  const persistenceStatus = selectedNode ? `Saved focus: ${selectedNode.label}` : "Saved focus: none";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Aionis Trial</p>
          <h1>Stateful Visual Dependency Explorer</h1>
          <p className="subtitle">A stateful delivery map that shows how planning, execution, and review interact across a live app loop.</p>
        </div>
        <div className="status-strip">
          <div className="status-pill"><span>Visible</span><strong>{visibleCount} nodes</strong></div>
          <div className="status-pill"><span>Persistence</span><strong>{persistenceStatus}</strong></div>
        </div>
      </header>
      <section className="controls-panel">
        <label className="control-field"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search nodes, owners, or dependencies" /></label>
        <label className="control-field"><span>Filter</span><select value={category} onChange={(event) => setCategory(event.target.value)}>{categoryOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
        <button type="button" className="ghost-button" onClick={() => { setQuery(""); setCategory("all"); }}>Reset filters</button>
      </section>
      <main className="workspace">
        <section className="graph-panel">
          <div className="panel-heading"><h2>Dependency Graph</h2><p>Choose a node to inspect its dependencies, owners, and current delivery posture.</p></div>
          <div className="graph-grid">
            {filteredNodes.map((node) => {
              const active = selectedNode?.id === node.id;
              return (
                <button key={node.id} type="button" className={active ? "graph-card active" : "graph-card"} onClick={() => setSelectedNodeId(node.id)}>
                  <small>{node.kind}</small>
                  <strong>{node.label}</strong>
                  <span className="card-status">{node.status}</span>
                  <p>{node.description}</p>
                  <span className="card-meta">{node.dependencies.length} dependencies</span>
                </button>
              );
            })}
            {!filteredNodes.length ? (
              <div className="empty-state"><strong>No nodes match.</strong><p>Reset filters or search for another owner, dependency, or node kind.</p></div>
            ) : null}
          </div>
        </section>
        <aside className="detail-panel">
          <div className="panel-heading"><h2>Details</h2><p>Selected node state persists across refresh.</p></div>
          {selectedNode ? (
            <div className="detail-stack">
              <div className="detail-hero"><span>{selectedNode.kind}</span><h3>{selectedNode.label}</h3><p>{selectedNode.description}</p></div>
              <div className="detail-grid">
                <section><h4>Status</h4><p>{selectedNode.status}</p></section>
                <section><h4>Category</h4><p>{selectedNode.category}</p></section>
                <section><h4>Owners</h4><ul>{selectedNode.owners.map((owner) => <li key={owner}>{owner}</li>)}</ul></section>
                <section><h4>Dependencies</h4><ul>{selectedNode.dependencies.map((dependency) => <li key={dependency}>{dependency}</li>)}</ul></section>
              </div>
            </div>
          ) : (
            <p>Select a node to inspect workflow dependencies and persistence edges.</p>
          )}
        </aside>
      </main>
      <section className="timeline-panel">
        <div className="panel-heading"><h2>Timeline</h2><p>Timeline focus follows the currently selected node.</p></div>
        {selectedNode ? (
          <ol className="timeline-list">
            {selectedNode.timeline.map((item) => (
              <li key={`${selectedNode.id}-${item.phase}`}>
                <div className="timeline-phase">{item.phase}</div>
                <div><strong>{item.note}</strong>{item.emphasis ? <p>{item.emphasis}</p> : null}</div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="empty-copy">Select a node to reveal its delivery timeline.</p>
        )}
      </section>
    </div>
  );
}
