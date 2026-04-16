from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Callable

from .delivery_families import (
    NODE_EXPRESS_API,
    NEXTJS_WEB,
    PYTHON_FASTAPI_API,
    REACT_VITE_WEB,
    SVELTE_VITE_WEB,
    VUE_VITE_WEB,
    infer_artifact_kind_from_artifact_paths,
    infer_delivery_family_from_artifact_paths,
    delivery_family_workspace_preview_command,
)


def _default_app_tsx(title: str) -> str:
    safe_title = title or "Aionis Delivery Starter"
    return f"""import {{ useEffect, useMemo, useState }} from "react";

type FeatureCard = {{
  id: string;
  eyebrow: string;
  title: string;
  body: string;
}};

const STORAGE_KEY = "aionis-web-delivery-state";

const features: FeatureCard[] = [
  {{
    id: "launch-fast",
    eyebrow: "Execution",
    title: "Launch fast without design debt",
    body: "Start from a clean, calm shell that can become a landing page, homepage, dashboard, or product demo without fighting old layout decisions.",
  }},
  {{
    id: "ship-proof",
    eyebrow: "Product",
    title: "Ship proof before complexity",
    body: "Anchor the page around one sharp promise, a small proof band, and a single high-confidence conversion path.",
  }},
  {{
    id: "keep-focus",
    eyebrow: "Delivery",
    title: "Keep the sprint scope narrow",
    body: "Use one polished hero, one supporting band, and one conversion rail before expanding into a full site.",
  }},
];

const themeOptions = ["zen", "midnight", "stone"] as const;
type ThemeOption = (typeof themeOptions)[number];

type PersistedState = {{
  selectedFeatureId?: string;
  theme?: ThemeOption;
}};

function readPersistedState(): PersistedState {{
  if (typeof window === "undefined") {{
    return {{}};
  }}
  try {{
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {{
      return {{}};
    }}
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed ? (parsed as PersistedState) : {{}};
  }} catch {{
    return {{}};
  }}
}}

export default function App() {{
  const persisted = readPersistedState();
  const [theme, setTheme] = useState<ThemeOption>(persisted.theme ?? "zen");
  const [selectedFeatureId, setSelectedFeatureId] = useState(persisted.selectedFeatureId ?? features[0]?.id ?? "");

  const selectedFeature = useMemo(() => {{
    return features.find((feature) => feature.id === selectedFeatureId) ?? features[0];
  }}, [selectedFeatureId]);

  useEffect(() => {{
    document.documentElement.dataset.theme = theme;
  }}, [theme]);

  useEffect(() => {{
    if (typeof window === "undefined") {{
      return;
    }}
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({{ selectedFeatureId, theme }}),
    );
  }}, [selectedFeatureId, theme]);

  const persistenceStatus = selectedFeature ? `Saved focus: ${{selectedFeature.title}}` : "Saved focus: none";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Aionis Delivery Starter</p>
          <h1>{safe_title}</h1>
          <p className="subtitle">
            A minimal, buildable web shell that can be reshaped into a landing page,
            homepage, dashboard, or simple product demo.
          </p>
        </div>
        <div className="status-strip">
          <div className="status-pill">
            <span>Theme</span>
            <strong>{{theme}}</strong>
          </div>
          <div className="status-pill">
            <span>Persistence</span>
            <strong>{{persistenceStatus}}</strong>
          </div>
        </div>
      </header>

      <section className="controls-panel">
        <label className="control-field">
          <span>Theme</span>
          <select value={{theme}} onChange={{(event) => setTheme(event.target.value as ThemeOption)}}>
            {{themeOptions.map((option) => (
              <option key={{option}} value={{option}}>
                {{option}}
              </option>
            ))}}
          </select>
        </label>
        <button type="button" className="ghost-button" onClick={{() => setTheme("zen")}}>
          Reset theme
        </button>
      </section>

      <main className="workspace">
        <section className="graph-panel">
          <div className="panel-heading">
            <h2>Featured Value Props</h2>
            <p>Choose a card to update the hero emphasis and supporting copy.</p>
          </div>
          <div className="graph-grid">
            {{features.map((feature) => {{
              const active = selectedFeature?.id === feature.id;
              return (
                <button
                  key={{feature.id}}
                  type="button"
                  className={{active ? "graph-card active" : "graph-card"}}
                  onClick={{() => setSelectedFeatureId(feature.id)}}
                >
                  <small>{{feature.eyebrow}}</small>
                  <strong>{{feature.title}}</strong>
                  <p>{{feature.body}}</p>
                  <span className="card-meta">Primary message</span>
                </button>
              );
            }})}}
          </div>
        </section>

        <aside className="detail-panel">
          <div className="panel-heading">
            <h2>Hero Copy</h2>
            <p>Selected state persists across refresh so the shell behaves like a real app.</p>
          </div>
          {{selectedFeature ? (
            <div className="detail-stack">
              <div className="detail-hero">
                <span>{{selectedFeature.eyebrow}}</span>
                <h3>{{selectedFeature.title}}</h3>
                <p>{{selectedFeature.body}}</p>
              </div>
              <div className="detail-grid">
                <section>
                  <h4>Primary CTA</h4>
                  <p>Book a guided walkthrough</p>
                </section>
                <section>
                  <h4>Secondary CTA</h4>
                  <p>View the product brief</p>
                </section>
                <section>
                  <h4>Proof band</h4>
                  <ul>
                    <li>Delivery-first runtime</li>
                    <li>Structured continuity</li>
                    <li>Reviewer-aware recovery</li>
                  </ul>
                </section>
                <section>
                  <h4>Shipping status</h4>
                  <ul>
                    <li>Buildable shell</li>
                    <li>Theme persistence</li>
                    <li>Editable feature focus</li>
                  </ul>
                </section>
              </div>
            </div>
          ) : null}}
        </aside>
      </main>

      <section className="timeline-panel">
        <div className="panel-heading">
          <h2>Delivery Notes</h2>
          <p>Use this section for social proof, metrics, pricing, roadmap, or any supporting block.</p>
        </div>
        {{selectedFeature ? (
          <ol className="timeline-list">
            <li>
              <div className="timeline-phase">Promise</div>
              <div>
                <strong>{{selectedFeature.title}}</strong>
                <p>{{selectedFeature.body}}</p>
              </div>
            </li>
            <li>
              <div className="timeline-phase">Visual</div>
              <div>
                <strong>High-contrast headline and quiet proof panel.</strong>
                <p>Keep the page spacious, calm, and easy to adapt.</p>
              </div>
            </li>
            <li>
              <div className="timeline-phase">Conversion</div>
              <div>
                <strong>One primary CTA, one supportive CTA.</strong>
                <p>Start with a believable conversion path before expanding the site.</p>
              </div>
            </li>
          </ol>
        ) : null}}
      </section>
    </div>
  );
}}
"""


def _default_styles_css() -> str:
    return """:root { color-scheme: light; font-family: 'Segoe UI', 'Inter', sans-serif; --bg: #efe6db; --surface: rgba(255,255,255,0.9); --surface-strong: rgba(255,250,244,0.96); --text: #17324d; --muted: #6b7785; --accent: #9f4e26; --accent-soft: rgba(159,78,38,0.12); }
:root[data-theme='midnight'] { --bg: #0f1724; --surface: rgba(20,30,46,0.9); --surface-strong: rgba(18,26,40,0.96); --text: #f3efe8; --muted: #94a3b8; --accent: #f59e0b; --accent-soft: rgba(245,158,11,0.16); }
:root[data-theme='stone'] { --bg: #d9d0c3; --surface: rgba(247,242,235,0.92); --surface-strong: rgba(255,251,245,0.98); --text: #2b241e; --muted: #6f655c; --accent: #7c5b2d; --accent-soft: rgba(124,91,45,0.14); }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; background: radial-gradient(circle at top, color-mix(in srgb, var(--bg) 84%, white 16%), var(--bg) 55%, color-mix(in srgb, var(--bg) 92%, black 8%) 100%); color: var(--text); }
button, input, select { font: inherit; }
button { cursor: pointer; }
.app-shell { min-height: 100vh; padding: 24px; display: grid; gap: 18px; }
.topbar, .controls-panel, .graph-panel, .detail-panel, .timeline-panel { background: var(--surface); border: 1px solid rgba(133, 115, 93, 0.24); border-radius: 24px; box-shadow: 0 18px 36px rgba(23,50,77,0.12); }
.topbar { padding: 24px; display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.eyebrow { margin: 0 0 8px; text-transform: uppercase; letter-spacing: .12em; font-size: 12px; color: var(--muted); }
.subtitle { margin-top: 10px; max-width: 720px; color: var(--muted); line-height: 1.5; }
.status-strip { display: grid; gap: 10px; min-width: 240px; }
.status-pill { border-radius: 16px; padding: 14px 16px; background: linear-gradient(180deg, var(--surface-strong), color-mix(in srgb, var(--surface) 84%, var(--bg) 16%)); border: 1px solid var(--accent-soft); }
.status-pill span, .control-field span, .panel-heading p { color: var(--muted); }
.status-pill span, .control-field span { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
.status-pill strong { display: block; margin-top: 4px; font-size: 15px; color: var(--text); }
.controls-panel { padding: 18px; display: grid; grid-template-columns: minmax(220px, .7fr) auto; gap: 12px; align-items: end; }
.control-field { display: grid; gap: 8px; }
.control-field select { border-radius: 14px; border: 1px solid rgba(127, 144, 160, 0.32); background: var(--surface-strong); padding: 12px 14px; color: var(--text); }
.ghost-button { border-radius: 14px; border: 1px solid var(--accent-soft); background: color-mix(in srgb, var(--surface-strong) 82%, var(--bg) 18%); color: var(--accent); padding: 12px 16px; }
.workspace { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(300px, .9fr); gap: 18px; }
.graph-panel, .detail-panel, .timeline-panel { padding: 20px; }
.panel-heading { display: grid; gap: 6px; margin-bottom: 14px; }
.panel-heading h2, .detail-hero h3 { margin: 0; }
.panel-heading p, .detail-hero p, .timeline-list p, .detail-grid p, .graph-card p { margin: 0; line-height: 1.5; }
.graph-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; }
.graph-card { min-height: 180px; border-radius: 18px; padding: 16px; border: 1px solid rgba(127, 144, 160, 0.2); background: linear-gradient(180deg, var(--surface-strong), color-mix(in srgb, var(--surface) 85%, var(--bg) 15%)); display: grid; align-content: start; gap: 10px; text-align: left; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease; }
.graph-card:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--accent) 50%, transparent 50%); }
.graph-card.active { border-color: var(--accent); box-shadow: 0 16px 28px rgba(23,50,77,0.16); }
.graph-card small, .card-meta, .timeline-phase, .detail-hero span { text-transform: uppercase; letter-spacing: .08em; font-size: 12px; color: var(--muted); }
.graph-card strong { font-size: 18px; color: var(--text); }
.card-meta { margin-top: auto; }
.detail-stack { display: grid; gap: 16px; }
.detail-hero { border-radius: 18px; padding: 18px; background: linear-gradient(180deg, color-mix(in srgb, var(--surface-strong) 88%, white 12%), color-mix(in srgb, var(--surface) 86%, var(--bg) 14%)); border: 1px solid var(--accent-soft); display: grid; gap: 8px; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.detail-grid section { border-radius: 16px; padding: 14px; background: var(--surface-strong); border: 1px solid rgba(127, 144, 160, 0.18); }
.detail-grid h4 { margin: 0 0 8px; font-size: 14px; }
.detail-grid ul { margin: 0; padding-left: 18px; display: grid; gap: 6px; }
.timeline-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 12px; }
.timeline-list li { display: grid; grid-template-columns: 90px 1fr; gap: 14px; padding: 14px 0; border-top: 1px solid rgba(127, 144, 160, 0.18); }
.timeline-list li:first-child { border-top: 0; padding-top: 0; }
.timeline-list strong { display: block; margin-bottom: 6px; }
@media (max-width: 980px) { .topbar, .controls-panel, .workspace { grid-template-columns: 1fr; } .topbar { flex-direction: column; } .status-strip { width: 100%; min-width: 0; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); } }
@media (max-width: 720px) { .app-shell { padding: 16px; } .detail-grid { grid-template-columns: 1fr; } .timeline-list li { grid-template-columns: 1fr; } }
"""


def _default_vue_app_vue(title: str) -> str:
    safe_title = title or "Aionis Delivery Starter"
    return f"""<script setup lang="ts">
const highlights = [
  "Focused execution surface",
  "Calm visual hierarchy",
  "Build-first delivery loop",
];
</script>

<template>
  <main class="app-shell">
    <header class="hero">
      <p class="eyebrow">Aionis Delivery Starter</p>
      <h1>{safe_title}</h1>
      <p class="subtitle">
        A minimal Vue/Vite shell that can quickly become a landing page, dashboard,
        explorer, or product demo without inheriting template noise.
      </p>
    </header>

    <section class="proof-grid">
      <article v-for="item in highlights" :key="item" class="proof-card">
        <strong>{{{{ item }}}}</strong>
        <p>Ready for the next bounded implementation pass.</p>
      </article>
    </section>
  </main>
</template>
"""


def _default_svelte_app_svelte(title: str) -> str:
    safe_title = title or "Aionis Delivery Starter"
    return f"""<script lang="ts">
  const highlights = [
    "Focused execution surface",
    "Calm visual hierarchy",
    "Build-first delivery loop",
  ];
</script>

<main class="app-shell">
  <header class="hero">
    <p class="eyebrow">Aionis Delivery Starter</p>
    <h1>{safe_title}</h1>
    <p class="subtitle">
      A minimal Svelte/Vite shell that can quickly become a landing page, dashboard,
      explorer, or product demo without inheriting template noise.
    </p>
  </header>

  <section class="proof-grid">
    {{#each highlights as item}}
      <article class="proof-card">
        <h2>{{item}}</h2>
        <p>Use this starter to anchor one strong primary surface before expanding the app.</p>
      </article>
    {{/each}}
  </section>
</main>
"""


def _default_nextjs_page_tsx(title: str) -> str:
    safe_title = title or "Aionis Delivery Starter"
    return f"""export default function Page() {{
  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">Aionis Delivery Starter</p>
        <h1>{safe_title}</h1>
        <p className="subtitle">
          A minimal Next.js shell that can quickly become a landing page, dashboard,
          explorer, or product demo without inheriting template noise.
        </p>
      </header>

      <section className="proof-grid">
        <article className="proof-card">
          <strong>Focused execution surface</strong>
          <p>Ready for the next bounded implementation pass.</p>
        </article>
        <article className="proof-card">
          <strong>Calm visual hierarchy</strong>
          <p>Use a small, coherent page before widening the app.</p>
        </article>
        <article className="proof-card">
          <strong>Build-first delivery loop</strong>
          <p>Stay runnable while improving the product surface.</p>
        </article>
      </section>
    </main>
  );
}}
"""


def _python_service_title(title: str) -> str:
    return title.strip() or "Aionis Delivery API"


def _default_fastapi_main_py(title: str) -> str:
    safe_title = _python_service_title(title).replace('"', '\\"')
    return f"""from fastapi import FastAPI

app = FastAPI(title="{safe_title}")


@app.get("/health")
def health() -> dict[str, str]:
    return {{"status": "ok"}}


@app.get("/features")
def list_features() -> dict[str, list[dict[str, str]]]:
    return {{
        "items": [
            {{
                "id": "orchestration",
                "title": "Agent orchestration",
                "summary": "Coordinate multi-step agent workflows with shared execution context.",
            }},
            {{
                "id": "observability",
                "title": "Execution observability",
                "summary": "Expose task health, latency, and runtime status through one service surface.",
            }},
            {{
                "id": "safety",
                "title": "Policy guard rails",
                "summary": "Keep model actions bounded with runtime policies and review signals.",
            }},
        ]
    }}
"""


def _node_service_title(title: str) -> str:
    return title.strip() or "Aionis Delivery Node API"


def _default_node_express_main_js(title: str) -> str:
    safe_title = _node_service_title(title).replace('"', '\\"')
    return f"""import express from "express";

const app = express();
const port = Number(process.env.PORT || 4173);

app.use(express.json());

app.get("/health", (_req, res) => {{
  res.json({{ status: "ok", service: "{safe_title}" }});
}});

app.get("/features", (_req, res) => {{
  res.json({{
    items: [
      {{
        id: "orchestration",
        title: "Agent orchestration",
        summary: "Coordinate multi-step agent workflows through one API surface.",
      }},
      {{
        id: "observability",
        title: "Execution observability",
        summary: "Expose runtime status, artifacts, and recovery signals.",
      }},
    ],
  }});
}});

app.listen(port, () => {{
  console.log("{safe_title} listening on port " + port);
}});
"""


class DeliveryWorkspaceAdapter:
    def __init__(
        self,
        *,
        repo_root: str,
        collect_changed_files_fn: Callable[[], list[str]],
    ) -> None:
        self._repo_root = Path(repo_root)
        self._collect_changed_files = collect_changed_files_fn

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def task_workspace_root(self, *, task_id: str) -> Path:
        return self._repo_root / ".aionis-workbench" / "delivery-workspaces" / task_id.strip()

    def reset_task_workspace(self, *, task_id: str) -> Path:
        root = self.task_workspace_root(task_id=task_id)
        if root.exists():
            try:
                shutil.rmtree(root)
            except OSError:
                for current_root, dirs, files in os.walk(root, topdown=False):
                    current_path = Path(current_root)
                    for name in files:
                        file_path = current_path / name
                        try:
                            file_path.unlink()
                        except FileNotFoundError:
                            continue
                    for name in dirs:
                        dir_path = current_path / name
                        try:
                            dir_path.rmdir()
                        except FileNotFoundError:
                            continue
                try:
                    root.rmdir()
                except FileNotFoundError:
                    pass
        return root

    def ensure_empty_task_workspace(self, *, task_id: str) -> Path:
        root = self.task_workspace_root(task_id=task_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def bootstrap_empty_web_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.ensure_empty_task_workspace(task_id=task_id)
        src = root / "src"
        src.mkdir(parents=True, exist_ok=True)
        files: dict[Path, str] = {
            root / "package.json": json.dumps(
                {
                    "name": task_id.strip() or "aionis-empty-web-app",
                    "private": True,
                    "version": "0.0.0",
                    "type": "module",
                    "scripts": {
                        "dev": "vite",
                        "build": "vite build",
                        "preview": "vite preview",
                    },
                    "dependencies": {
                        "react": "^18.3.1",
                        "react-dom": "^18.3.1",
                    },
                    "devDependencies": {
                        "@types/react": "^18.3.3",
                        "@types/react-dom": "^18.3.0",
                        "@vitejs/plugin-react": "^4.3.1",
                        "typescript": "^5.6.2",
                        "vite": "^5.4.8",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2020",
                        "useDefineForClassFields": True,
                        "lib": ["ES2020", "DOM", "DOM.Iterable"],
                        "allowJs": False,
                        "skipLibCheck": True,
                        "esModuleInterop": True,
                        "allowSyntheticDefaultImports": True,
                        "strict": True,
                        "forceConsistentCasingInFileNames": True,
                        "module": "ESNext",
                        "moduleResolution": "Node",
                        "resolveJsonModule": True,
                        "isolatedModules": True,
                        "noEmit": True,
                        "jsx": "react-jsx",
                    },
                    "include": ["src"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "vite.config.ts": (
                'import { defineConfig } from "vite";\n'
                'import react from "@vitejs/plugin-react";\n\n'
                "export default defineConfig({\n"
                "  plugins: [react()],\n"
                "  server: {\n"
                '    host: "0.0.0.0",\n'
                "    port: 4173,\n"
                "  },\n"
                "});\n"
            ),
            root / "index.html": (
                "<!doctype html>\n"
                '<html lang="en">\n'
                "  <head>\n"
                '    <meta charset="UTF-8" />\n'
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
                f"    <title>{title}</title>\n"
                "  </head>\n"
                "  <body>\n"
                '    <div id="root"></div>\n'
                '    <script type="module" src="/src/main.tsx"></script>\n'
                "  </body>\n"
                "</html>\n"
            ),
            src / "main.tsx": (
                'import React from "react";\n'
                'import ReactDOM from "react-dom/client";\n'
                'import App from "./App";\n'
                'import "./styles.css";\n\n'
                'ReactDOM.createRoot(document.getElementById("root")!).render(\n'
                "  <React.StrictMode>\n"
                "    <App />\n"
                "  </React.StrictMode>,\n"
                ");\n"
            ),
            src / "App.tsx": (
                "export default function App() {\n"
                "  return <main />;\n"
                "}\n"
            ),
            src / "styles.css": (
                ":root { color-scheme: light; }\n"
                "* { box-sizing: border-box; }\n"
                "body { margin: 0; }\n"
            ),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def bootstrap_empty_vue_web_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.ensure_empty_task_workspace(task_id=task_id)
        src = root / "src"
        src.mkdir(parents=True, exist_ok=True)
        files: dict[Path, str] = {
            root / "package.json": json.dumps(
                {
                    "name": task_id.strip() or "aionis-empty-vue-app",
                    "private": True,
                    "version": "0.0.0",
                    "type": "module",
                    "scripts": {
                        "dev": "vite",
                        "build": "vite build",
                        "preview": "vite preview",
                    },
                    "dependencies": {
                        "vue": "^3.5.13",
                    },
                    "devDependencies": {
                        "@vitejs/plugin-vue": "^5.2.1",
                        "typescript": "^5.6.2",
                        "vite": "^5.4.8",
                        "vue-tsc": "^2.1.6",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2020",
                        "useDefineForClassFields": True,
                        "module": "ESNext",
                        "moduleResolution": "Node",
                        "strict": True,
                        "jsx": "preserve",
                        "resolveJsonModule": True,
                        "isolatedModules": True,
                        "noEmit": True,
                        "lib": ["ES2020", "DOM", "DOM.Iterable"],
                    },
                    "include": ["src/**/*.ts", "src/**/*.vue"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "vite.config.ts": (
                'import { defineConfig } from "vite";\n'
                'import vue from "@vitejs/plugin-vue";\n\n'
                "export default defineConfig({\n"
                "  plugins: [vue()],\n"
                "  server: {\n"
                '    host: "0.0.0.0",\n'
                "    port: 4173,\n"
                "  },\n"
                "});\n"
            ),
            root / "index.html": (
                "<!doctype html>\n"
                '<html lang="en">\n'
                "  <head>\n"
                '    <meta charset="UTF-8" />\n'
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
                f"    <title>{title}</title>\n"
                "  </head>\n"
                "  <body>\n"
                '    <div id="app"></div>\n'
                '    <script type="module" src="/src/main.ts"></script>\n'
                "  </body>\n"
                "</html>\n"
            ),
            src / "main.ts": (
                'import { createApp } from "vue";\n'
                'import App from "./App.vue";\n'
                'import "./styles.css";\n\n'
                "createApp(App).mount(\"#app\");\n"
            ),
            src / "App.vue": _default_vue_app_vue(title),
            src / "styles.css": (
                ":root { color-scheme: light; }\n"
                "* { box-sizing: border-box; }\n"
                "body { margin: 0; font-family: Inter, system-ui, sans-serif; }\n"
                ".app-shell { min-height: 100vh; padding: 32px; display: grid; gap: 20px; }\n"
                ".hero { display: grid; gap: 10px; }\n"
                ".eyebrow { margin: 0; text-transform: uppercase; letter-spacing: .12em; font-size: 12px; }\n"
                ".subtitle { margin: 0; max-width: 720px; line-height: 1.5; }\n"
                ".proof-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }\n"
                ".proof-card { border: 1px solid rgba(0,0,0,.08); border-radius: 18px; padding: 18px; }\n"
            ),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def bootstrap_empty_svelte_web_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.ensure_empty_task_workspace(task_id=task_id)
        src = root / "src"
        src.mkdir(parents=True, exist_ok=True)
        files: dict[Path, str] = {
            root / "package.json": json.dumps(
                {
                    "name": task_id.strip() or "aionis-empty-svelte-app",
                    "private": True,
                    "version": "0.0.0",
                    "type": "module",
                    "scripts": {
                        "dev": "vite",
                        "build": "vite build",
                        "preview": "vite preview",
                    },
                    "dependencies": {
                        "svelte": "^4.2.19",
                    },
                    "devDependencies": {
                        "@sveltejs/vite-plugin-svelte": "^3.1.2",
                        "svelte-check": "^3.8.6",
                        "typescript": "^5.6.2",
                        "vite": "^5.4.8",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2020",
                        "useDefineForClassFields": True,
                        "module": "ESNext",
                        "moduleResolution": "Node",
                        "strict": True,
                        "resolveJsonModule": True,
                        "isolatedModules": True,
                        "noEmit": True,
                        "lib": ["ES2020", "DOM", "DOM.Iterable"],
                    },
                    "include": ["src/**/*.ts", "src/**/*.js", "src/**/*.svelte"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "svelte.config.js": (
                "import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';\n\n"
                "export default {\n"
                "  preprocess: vitePreprocess(),\n"
                "};\n"
            ),
            root / "vite.config.ts": (
                'import { defineConfig } from "vite";\n'
                'import { svelte } from "@sveltejs/vite-plugin-svelte";\n\n'
                "export default defineConfig({\n"
                "  plugins: [svelte()],\n"
                "  server: {\n"
                '    host: "0.0.0.0",\n'
                "    port: 4173,\n"
                "  },\n"
                "});\n"
            ),
            root / "index.html": (
                "<!doctype html>\n"
                '<html lang="en">\n'
                "  <head>\n"
                '    <meta charset="UTF-8" />\n'
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
                f"    <title>{title}</title>\n"
                "  </head>\n"
                "  <body>\n"
                '    <div id="app"></div>\n'
                '    <script type="module" src="/src/main.ts"></script>\n'
                "  </body>\n"
                "</html>\n"
            ),
            src / "main.ts": (
                'import App from "./App.svelte";\n'
                'import "./app.css";\n\n'
                'const app = new App({ target: document.getElementById("app")! });\n\n'
                "export default app;\n"
            ),
            src / "App.svelte": _default_svelte_app_svelte(title),
            src / "app.css": (
                ":root { color-scheme: light; }\n"
                "* { box-sizing: border-box; }\n"
                "body { margin: 0; font-family: Inter, system-ui, sans-serif; }\n"
                ".app-shell { min-height: 100vh; padding: 32px; display: grid; gap: 20px; }\n"
                ".hero { display: grid; gap: 10px; }\n"
                ".eyebrow { margin: 0; text-transform: uppercase; letter-spacing: .12em; font-size: 12px; }\n"
                ".subtitle { margin: 0; max-width: 720px; line-height: 1.5; }\n"
                ".proof-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }\n"
                ".proof-card { border: 1px solid rgba(0,0,0,.08); border-radius: 18px; padding: 18px; }\n"
                ".proof-card h2 { margin: 0 0 8px; font-size: 20px; }\n"
                ".proof-card p { margin: 0; line-height: 1.5; }\n"
            ),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def bootstrap_empty_nextjs_web_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.ensure_empty_task_workspace(task_id=task_id)
        app = root / "app"
        app.mkdir(parents=True, exist_ok=True)
        files: dict[Path, str] = {
            root / "package.json": json.dumps(
                {
                    "name": task_id.strip() or "aionis-empty-next-app",
                    "private": True,
                    "version": "0.0.0",
                    "scripts": {
                        "dev": "next dev",
                        "build": "next build",
                        "start": "next start",
                    },
                    "dependencies": {
                        "next": "^15.1.0",
                        "react": "^18.3.1",
                        "react-dom": "^18.3.1",
                    },
                    "devDependencies": {
                        "@types/node": "^22.10.1",
                        "@types/react": "^18.3.3",
                        "@types/react-dom": "^18.3.0",
                        "typescript": "^5.6.2",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "next.config.mjs": "/** @type {import('next').NextConfig} */\nconst nextConfig = {};\n\nexport default nextConfig;\n",
            root / "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2020",
                        "lib": ["DOM", "DOM.Iterable", "ES2020"],
                        "allowJs": False,
                        "skipLibCheck": True,
                        "strict": True,
                        "noEmit": True,
                        "esModuleInterop": True,
                        "module": "ESNext",
                        "moduleResolution": "Bundler",
                        "resolveJsonModule": True,
                        "isolatedModules": True,
                        "jsx": "preserve",
                        "incremental": True,
                        "plugins": [{"name": "next"}],
                    },
                    "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
                    "exclude": ["node_modules"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "next-env.d.ts": '/// <reference types="next" />\n/// <reference types="next/image-types/global" />\n\n// This file is auto-generated by Next.js.\n',
            app / "layout.tsx": (
                'import "./globals.css";\n'
                'import type { Metadata } from "next";\n\n'
                "export const metadata: Metadata = {\n"
                f'  title: "{title}",\n'
                '  description: "Aionis Workbench Next.js delivery starter.",\n'
                "};\n\n"
                "export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {\n"
                "  return (\n"
                '    <html lang="en">\n'
                "      <body>{children}</body>\n"
                "    </html>\n"
                "  );\n"
                "}\n"
            ),
            app / "page.tsx": _default_nextjs_page_tsx(title),
            app / "globals.css": (
                ":root { color-scheme: light; }\n"
                "* { box-sizing: border-box; }\n"
                "body { margin: 0; font-family: Inter, system-ui, sans-serif; }\n"
                ".app-shell { min-height: 100vh; padding: 32px; display: grid; gap: 20px; }\n"
                ".hero { display: grid; gap: 10px; }\n"
                ".eyebrow { margin: 0; text-transform: uppercase; letter-spacing: .12em; font-size: 12px; }\n"
                ".subtitle { margin: 0; max-width: 720px; line-height: 1.5; }\n"
                ".proof-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }\n"
                ".proof-card { border: 1px solid rgba(0,0,0,.08); border-radius: 18px; padding: 18px; }\n"
            ),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def bootstrap_delivery_family_workspace(self, *, task_id: str, title: str, family_id: str) -> Path:
        if family_id == REACT_VITE_WEB.family_id:
            return self.bootstrap_empty_web_workspace(task_id=task_id, title=title)
        if family_id == NEXTJS_WEB.family_id:
            return self.bootstrap_empty_nextjs_web_workspace(task_id=task_id, title=title)
        if family_id == SVELTE_VITE_WEB.family_id:
            return self.bootstrap_empty_svelte_web_workspace(task_id=task_id, title=title)
        if family_id == VUE_VITE_WEB.family_id:
            return self.bootstrap_empty_vue_web_workspace(task_id=task_id, title=title)
        if family_id == PYTHON_FASTAPI_API.family_id:
            return self.bootstrap_empty_python_api_workspace(task_id=task_id, title=title)
        if family_id == NODE_EXPRESS_API.family_id:
            return self.bootstrap_empty_node_api_workspace(task_id=task_id, title=title)
        return self.ensure_empty_task_workspace(task_id=task_id)

    def bootstrap_empty_python_api_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.ensure_empty_task_workspace(task_id=task_id)
        files: dict[Path, str] = {
            root / "requirements.txt": "fastapi==0.116.1\nuvicorn==0.35.0\n",
            root / "main.py": _default_fastapi_main_py(title),
            root / "README.md": (
                f"# {_python_service_title(title)}\n\n"
                "Run locally after installing dependencies:\n\n"
                "```bash\n"
                "python3 -m pip install -r requirements.txt\n"
                "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173\n"
                "```\n"
            ),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def bootstrap_empty_node_api_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.ensure_empty_task_workspace(task_id=task_id)
        files: dict[Path, str] = {
            root / "package.json": json.dumps(
                {
                    "name": task_id.strip() or "aionis-node-api",
                    "private": True,
                    "version": "0.0.0",
                    "type": "module",
                    "scripts": {
                        "dev": "node main.js",
                        "start": "node main.js",
                    },
                    "dependencies": {
                        "express": "^4.21.2",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "main.js": _default_node_express_main_js(title),
            root / "README.md": (
                f"# {_node_service_title(title)}\n\n"
                "Run locally after installing dependencies:\n\n"
                "```bash\n"
                "npm install --no-fund --no-audit\n"
                "npm run dev\n"
                "```\n"
            ),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def ensure_react_app_workspace(self, *, task_id: str, title: str) -> Path:
        root = self.task_workspace_root(task_id=task_id)
        src = root / "src"
        src.mkdir(parents=True, exist_ok=True)
        files: dict[Path, str] = {
            root / "package.json": json.dumps(
                {
                    "name": task_id.strip() or "aionis-delivery-app",
                    "private": True,
                    "version": "0.0.0",
                    "type": "module",
                    "scripts": {
                        "dev": "vite",
                        "build": "vite build",
                        "preview": "vite preview",
                    },
                    "dependencies": {
                        "react": "^18.3.1",
                        "react-dom": "^18.3.1",
                    },
                    "devDependencies": {
                        "@types/react": "^18.3.3",
                        "@types/react-dom": "^18.3.0",
                        "@vitejs/plugin-react": "^4.3.1",
                        "typescript": "^5.6.2",
                        "vite": "^5.4.8",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2020",
                        "useDefineForClassFields": True,
                        "lib": ["ES2020", "DOM", "DOM.Iterable"],
                        "allowJs": False,
                        "skipLibCheck": True,
                        "esModuleInterop": True,
                        "allowSyntheticDefaultImports": True,
                        "strict": True,
                        "forceConsistentCasingInFileNames": True,
                        "module": "ESNext",
                        "moduleResolution": "Node",
                        "resolveJsonModule": True,
                        "isolatedModules": True,
                        "noEmit": True,
                        "jsx": "react-jsx",
                    },
                    "include": ["src"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            root / "vite.config.ts": (
                'import { defineConfig } from "vite";\n'
                'import react from "@vitejs/plugin-react";\n\n'
                "export default defineConfig({\n"
                "  plugins: [react()],\n"
                "  server: {\n"
                '    host: "0.0.0.0",\n'
                "    port: 4173,\n"
                "  },\n"
                "});\n"
            ),
            root / "index.html": (
                "<!doctype html>\n"
                '<html lang="en">\n'
                "  <head>\n"
                '    <meta charset="UTF-8" />\n'
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
                f"    <title>{title}</title>\n"
                "  </head>\n"
                "  <body>\n"
                '    <div id="root"></div>\n'
                '    <script type="module" src="/src/main.tsx"></script>\n'
                "  </body>\n"
                "</html>\n"
            ),
            src / "main.tsx": (
                'import React from "react";\n'
                'import ReactDOM from "react-dom/client";\n'
                'import App from "./App";\n'
                'import "./styles.css";\n\n'
                'ReactDOM.createRoot(document.getElementById("root")!).render(\n'
                "  <React.StrictMode>\n"
                "    <App />\n"
                "  </React.StrictMode>,\n"
                ");\n"
            ),
            src / "App.tsx": _default_app_tsx(title),
            src / "styles.css": _default_styles_css(),
        }
        for path, content in files.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return root

    def snapshot_workspace_state(self, *, workspace_root: Path) -> dict[str, str]:
        state: dict[str, str] = {}
        for path in sorted(workspace_root.rglob("*")):
            if not path.is_file():
                continue
            if "node_modules" in path.parts:
                continue
            relative = path.relative_to(workspace_root).as_posix()
            state[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return state

    def changed_workspace_files(
        self,
        *,
        before: dict[str, str],
        after: dict[str, str],
    ) -> list[str]:
        return sorted(path for path, digest in after.items() if before.get(path) != digest)

    def infer_artifact_paths(
        self,
        *,
        changed_files: list[str],
        workspace_root: Path | None = None,
    ) -> list[str]:
        ordered = list(dict.fromkeys(changed_files))
        baseline: list[str] = []
        if workspace_root is not None:
            candidate_paths = [
                "dist/index.html",
                "index.html",
                "package.json",
                "svelte.config.js",
                "next.config.mjs",
                "next-env.d.ts",
                "requirements.txt",
                "main.py",
                "main.js",
                "app/layout.tsx",
                "app/page.tsx",
                "app/globals.css",
                "src/main.ts",
                "src/App.svelte",
                "src/app.css",
                "src/main.tsx",
                "src/App.vue",
                "src/App.tsx",
                "src/styles.css",
            ]
            for candidate in candidate_paths:
                if (workspace_root / candidate).exists():
                    baseline.append(candidate)
        artifact_paths: list[str] = []
        for item in baseline + ordered:
            cleaned = str(item).strip()
            if cleaned and cleaned not in artifact_paths:
                artifact_paths.append(cleaned)
        return artifact_paths[:8]

    def infer_artifact_kind(self, *, artifact_paths: list[str]) -> str:
        return infer_artifact_kind_from_artifact_paths(artifact_paths)

    def infer_preview_command(
        self,
        *,
        artifact_paths: list[str],
        workspace_root: Path | None = None,
    ) -> str:
        family_id = infer_delivery_family_from_artifact_paths(artifact_paths)
        return delivery_family_workspace_preview_command(
            family_id,
            artifact_paths=artifact_paths,
            workspace_root=workspace_root,
        )
