from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any


VITE_DIST_VALIDATION_COMMAND = (
    'python3 -c "from pathlib import Path; p=Path(\'dist/index.html\'); '
    "print('vite dist ok' if p.exists() else 'missing dist/index.html'); "
    'raise SystemExit(0 if p.exists() else 1)"'
)

NEXTJS_BUILD_VALIDATION_COMMAND = (
    'python3 -c "from pathlib import Path; p=Path(\'.next/BUILD_ID\'); '
    "print('next build ok' if p.exists() else 'missing .next/BUILD_ID'); "
    'raise SystemExit(0 if p.exists() else 1)"'
)

PYTHON_FASTAPI_MANIFEST_VALIDATION_COMMAND = (
    'python3 -c "from pathlib import Path; s=Path(\'requirements.txt\').read_text(encoding=\'utf-8\').lower(); '
    "required=('fastapi', 'uvicorn'); missing=[item for item in required if item not in s]; "
    "print('python api manifest ok' if not missing else 'missing: ' + ', '.join(missing)); "
    'raise SystemExit(1 if missing else 0)"'
)

NODE_EXPRESS_MANIFEST_VALIDATION_COMMAND = (
    'node -e "const fs=require(\'fs\'); const pkg=JSON.parse(fs.readFileSync(\'package.json\',\'utf8\')); '
    "const deps={...(pkg.dependencies||{}), ...(pkg.devDependencies||{})}; const scripts=pkg.scripts||{}; "
    "const missing=[]; if(!('express' in deps)) missing.push('express dependency'); "
    "if(!(scripts.dev || scripts.start)) missing.push('dev/start script'); "
    "if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api manifest ok')}"
    '"'
)


def _web_surface_validation_command(surface_path: str, *, label: str) -> str:
    return (
        'python3 -c "from pathlib import Path; '
        f"p=Path({surface_path!r}); "
        "s=p.read_text(encoding='utf-8') if p.exists() else ''; "
        "markers=('<main', '<section', '<header', '<nav', '<aside', '<footer', '<article', '<div'); "
        "text=s.lower(); hits=sum(1 for marker in markers if marker in text); "
        f"label={label!r}; "
        "ok=bool(s.strip()) and len(s) >= 250 and hits >= 2; "
        "print(f'{label} ok' if ok else f'{label} too sparse'); "
        'raise SystemExit(0 if ok else 1)"'
    )


REACT_APP_SURFACE_VALIDATION_COMMAND = _web_surface_validation_command(
    "src/App.tsx",
    label="react app surface",
)
VUE_APP_SURFACE_VALIDATION_COMMAND = _web_surface_validation_command(
    "src/App.vue",
    label="vue app surface",
)
SVELTE_APP_SURFACE_VALIDATION_COMMAND = _web_surface_validation_command(
    "src/App.svelte",
    label="svelte app surface",
)
NEXT_PAGE_SURFACE_VALIDATION_COMMAND = _web_surface_validation_command(
    "app/page.tsx",
    label="next page surface",
)


@dataclass(frozen=True)
class DeliveryFamilySpec:
    family_id: str
    bootstrap_targets: tuple[str, ...]
    default_validation_commands: tuple[str, ...]
    delivery_targets: tuple[str, ...] = ()
    contract_instructions: tuple[str, ...] = ()
    ship_acceptance_checks: tuple[str, ...] = ()
    ship_done_definition: tuple[str, ...] = ()
    evaluator_criteria_specs: tuple[str, ...] = ()


REACT_VITE_WEB = DeliveryFamilySpec(
    family_id="react_vite_web",
    bootstrap_targets=(
        "package.json",
        "vite.config.ts",
        "tsconfig.json",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/styles.css",
    ),
    delivery_targets=(
        "package.json",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/styles.css",
    ),
    default_validation_commands=("npm run build", VITE_DIST_VALIDATION_COMMAND, REACT_APP_SURFACE_VALIDATION_COMMAND),
    contract_instructions=(
        "This is a simple web delivery task. Prioritize visible UI, working interactions, and a clean build over architecture expansion.",
        "The task workspace starts empty or near-empty. Bootstrap the app from scratch inside the current workspace before refining the UI.",
        "Create the minimal React/Vite project files yourself when they are missing, including package.json, vite.config.ts, tsconfig.json, index.html, src/main.tsx, src/App.tsx, and src/styles.css.",
        "Treat src/App.tsx, styling, and any small supporting files as the primary delivery surface unless the sprint clearly demands otherwise.",
        "Do not invent backend complexity when the sprint can be satisfied by a focused frontend artifact.",
        "In the first implementation pass, establish the project shell and core delivery files together: package.json, index.html, src/main.tsx, src/App.tsx, and src/styles.css.",
        "After reading package.json, index.html, src/App.tsx, and src/styles.css, stop discovery and move directly into write_file/edit_file calls.",
        "Do not request another discovery round after the initial file read pass unless npm run build fails and the error requires one narrow fix.",
        "In the second model response at the latest, begin writing the page implementation instead of continuing analysis.",
        "Do not stop after editing a single file if the page still lacks styling or structural sections.",
        "After the first file pass, run npm install --no-fund --no-audit and npm run build before requesting more model turns unless a blocking error forces one narrow fix.",
        "Minimum page quality bar: deliver a complete, presentation-ready page rather than a sparse shell.",
        "For landing pages and homepages, include a clear navigation/header, a strong hero section, at least two supporting content sections, and a CTA or footer area.",
        "For dashboard, explorer, editor, studio, or demo tasks, include a complete primary surface plus at least two supporting panels or sections with coherent layout and styling.",
        "Responsive behavior is required: the page should remain readable and structured on both desktop and mobile widths.",
    ),
    ship_acceptance_checks=("npm run build", VITE_DIST_VALIDATION_COMMAND, REACT_APP_SURFACE_VALIDATION_COMMAND),
    ship_done_definition=(
        "The landing page is visually complete enough to demo.",
        "The app builds successfully, emits dist/index.html, and leaves a non-sparse primary page surface.",
    ),
    evaluator_criteria_specs=("functionality:0.8", "design_quality:0.7", "code_quality:0.6"),
)

VUE_VITE_WEB = DeliveryFamilySpec(
    family_id="vue_vite_web",
    bootstrap_targets=(
        "package.json",
        "vite.config.ts",
        "tsconfig.json",
        "index.html",
        "src/main.ts",
        "src/App.vue",
        "src/styles.css",
    ),
    delivery_targets=(
        "package.json",
        "index.html",
        "src/main.ts",
        "src/App.vue",
        "src/styles.css",
    ),
    default_validation_commands=("npm run build", VITE_DIST_VALIDATION_COMMAND, VUE_APP_SURFACE_VALIDATION_COMMAND),
    contract_instructions=(
        "This is a simple Vue web delivery task. Prioritize visible UI, working interactions, and a clean build over architecture expansion.",
        "The task workspace starts empty or near-empty. Bootstrap the app from scratch inside the current workspace before refining the UI.",
        "Create the minimal Vue/Vite project files yourself when they are missing, including package.json, vite.config.ts, tsconfig.json, index.html, src/main.ts, src/App.vue, and src/styles.css.",
        "Treat src/App.vue, styling, and any small supporting files as the primary delivery surface unless the sprint clearly demands otherwise.",
        "Do not invent backend complexity when the sprint can be satisfied by a focused frontend artifact.",
        "In the first implementation pass, establish the project shell and core delivery files together: package.json, index.html, src/main.ts, src/App.vue, and src/styles.css.",
        "After reading package.json, index.html, src/App.vue, and src/styles.css, stop discovery and move directly into write_file/edit_file calls.",
        "Do not request another discovery round after the initial file read pass unless npm run build fails and the error requires one narrow fix.",
        "In the second model response at the latest, begin writing the page implementation instead of continuing analysis.",
        "Do not stop after editing a single file if the page still lacks styling or structural sections.",
        "After the first file pass, run npm install --no-fund --no-audit and npm run build before requesting more model turns unless a blocking error forces one narrow fix.",
        "Minimum page quality bar: deliver a complete, presentation-ready page rather than a sparse shell.",
        "For landing pages and homepages, include a clear navigation/header, a strong hero section, at least two supporting content sections, and a CTA or footer area.",
        "For dashboard, explorer, editor, studio, or demo tasks, include a complete primary surface plus at least two supporting panels or sections with coherent layout and styling.",
        "Responsive behavior is required: the page should remain readable and structured on both desktop and mobile widths.",
    ),
    ship_acceptance_checks=("npm run build", VITE_DIST_VALIDATION_COMMAND, VUE_APP_SURFACE_VALIDATION_COMMAND),
    ship_done_definition=(
        "The Vue app is visually complete enough to demo.",
        "The app builds successfully, emits dist/index.html, and leaves a non-sparse primary page surface.",
    ),
    evaluator_criteria_specs=("functionality:0.8", "design_quality:0.7", "code_quality:0.6"),
)

SVELTE_VITE_WEB = DeliveryFamilySpec(
    family_id="svelte_vite_web",
    bootstrap_targets=(
        "package.json",
        "vite.config.ts",
        "tsconfig.json",
        "svelte.config.js",
        "index.html",
        "src/main.ts",
        "src/App.svelte",
        "src/app.css",
    ),
    delivery_targets=(
        "package.json",
        "index.html",
        "src/main.ts",
        "src/App.svelte",
        "src/app.css",
    ),
    default_validation_commands=("npm run build", VITE_DIST_VALIDATION_COMMAND, SVELTE_APP_SURFACE_VALIDATION_COMMAND),
    contract_instructions=(
        "This is a simple Svelte web delivery task. Prioritize visible UI, working interactions, and a clean build over architecture expansion.",
        "The task workspace starts empty or near-empty. Bootstrap the app from scratch inside the current workspace before refining the UI.",
        "Create the minimal Svelte/Vite project files yourself when they are missing, including package.json, vite.config.ts, tsconfig.json, svelte.config.js, index.html, src/main.ts, src/App.svelte, and src/app.css.",
        "Treat src/App.svelte, styling, and any small supporting files as the primary delivery surface unless the sprint clearly demands otherwise.",
        "Do not invent backend complexity when the sprint can be satisfied by a focused frontend artifact.",
        "In the first implementation pass, establish the project shell and core delivery files together: package.json, index.html, src/main.ts, src/App.svelte, and src/app.css.",
        "After reading package.json, index.html, src/App.svelte, and src/app.css, stop discovery and move directly into write_file/edit_file calls.",
        "Do not request another discovery round after the initial file read pass unless npm run build fails and the error requires one narrow fix.",
        "In the second model response at the latest, begin writing the page implementation instead of continuing analysis.",
        "Do not stop after editing a single file if the page still lacks styling or structural sections.",
        "After the first file pass, run npm install --no-fund --no-audit and npm run build before requesting more model turns unless a blocking error forces one narrow fix.",
        "Minimum page quality bar: deliver a complete, presentation-ready page rather than a sparse shell.",
        "For landing pages and homepages, include a clear navigation/header, a strong hero section, at least two supporting content sections, and a CTA or footer area.",
        "For dashboard, explorer, editor, studio, or demo tasks, include a complete primary surface plus at least two supporting panels or sections with coherent layout and styling.",
        "Responsive behavior is required: the page should remain readable and structured on both desktop and mobile widths.",
    ),
    ship_acceptance_checks=("npm run build", VITE_DIST_VALIDATION_COMMAND, SVELTE_APP_SURFACE_VALIDATION_COMMAND),
    ship_done_definition=(
        "The Svelte app is visually complete enough to demo.",
        "The app builds successfully, emits dist/index.html, and leaves a non-sparse primary page surface.",
    ),
    evaluator_criteria_specs=("functionality:0.8", "design_quality:0.7", "code_quality:0.6"),
)

NEXTJS_WEB = DeliveryFamilySpec(
    family_id="nextjs_web",
    bootstrap_targets=(
        "package.json",
        "next.config.mjs",
        "tsconfig.json",
        "next-env.d.ts",
        "app/layout.tsx",
        "app/page.tsx",
        "app/globals.css",
    ),
    delivery_targets=(
        "package.json",
        "app/layout.tsx",
        "app/page.tsx",
        "app/globals.css",
    ),
    default_validation_commands=("npm run build", NEXTJS_BUILD_VALIDATION_COMMAND, NEXT_PAGE_SURFACE_VALIDATION_COMMAND),
    contract_instructions=(
        "This is a Next.js web delivery task. Prioritize visible UI, working interactions, and a clean build over architecture expansion.",
        "The task workspace starts empty or near-empty. Bootstrap the app from scratch inside the current workspace before refining the UI.",
        "Create the minimal Next.js project files yourself when they are missing, including package.json, next.config.mjs, tsconfig.json, next-env.d.ts, app/layout.tsx, app/page.tsx, and app/globals.css.",
        "Treat app/page.tsx, app/globals.css, and the layout shell as the primary delivery surface unless the sprint clearly demands otherwise.",
        "Do not invent backend complexity when the sprint can be satisfied by a focused frontend artifact.",
        "In the first implementation pass, establish the project shell and core delivery files together: package.json, app/layout.tsx, app/page.tsx, and app/globals.css.",
        "After reading package.json, app/page.tsx, and app/globals.css, stop discovery and move directly into write_file/edit_file calls.",
        "Do not request another discovery round after the initial file read pass unless npm run build fails and the error requires one narrow fix.",
        "In the second model response at the latest, begin writing the page implementation instead of continuing analysis.",
        "After the first file pass, run npm install --no-fund --no-audit and npm run build before requesting more model turns unless a blocking error forces one narrow fix.",
        "Minimum page quality bar: deliver a complete, presentation-ready page rather than a sparse shell.",
        "For landing pages and dashboards, include a clear hero or page header, a complete primary surface, and at least two supporting sections or panels.",
        "Responsive behavior is required: the page should remain readable and structured on both desktop and mobile widths.",
    ),
    ship_acceptance_checks=("npm run build", NEXTJS_BUILD_VALIDATION_COMMAND, NEXT_PAGE_SURFACE_VALIDATION_COMMAND),
    ship_done_definition=(
        "The Next.js app is visually complete enough to demo.",
        "The app builds successfully, emits a .next build artifact, and leaves a non-sparse primary page surface.",
    ),
    evaluator_criteria_specs=("functionality:0.8", "design_quality:0.7", "code_quality:0.6"),
)

PYTHON_FASTAPI_API = DeliveryFamilySpec(
    family_id="python_fastapi_api",
    bootstrap_targets=("requirements.txt", "main.py"),
    delivery_targets=("requirements.txt", "main.py"),
    default_validation_commands=(
        "python3 -m py_compile main.py",
        PYTHON_FASTAPI_MANIFEST_VALIDATION_COMMAND,
        "python3 -c \"from pathlib import Path; s=Path('main.py').read_text(encoding='utf-8'); required=('FastAPI(', 'app =', '/health', '/features'); missing=[item for item in required if item not in s]; print('python api structure ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
    ),
    contract_instructions=(
        "This is a Python API delivery task. Prioritize a runnable FastAPI service with a narrow, coherent endpoint surface.",
        "The task workspace starts empty or near-empty. Bootstrap the API service from scratch inside the current workspace before refining the endpoint behavior.",
        "Create the minimal FastAPI project files yourself when they are missing, including requirements.txt and main.py.",
        "Treat main.py as the primary delivery surface unless the sprint clearly demands one small supporting module.",
        "Do not invent frontend files when the sprint can be satisfied by a focused API artifact.",
        "In the first implementation pass, establish the service shell and core delivery files together: requirements.txt and main.py.",
        "After reading requirements.txt and main.py, stop discovery and move directly into write_file/edit_file calls.",
        "Do not request another discovery round after the initial file read pass unless Python validation fails and the error requires one narrow fix.",
        "In the second model response at the latest, begin writing the API implementation instead of continuing analysis.",
        "After the first file pass, run syntax validation, verify requirements.txt includes FastAPI and Uvicorn, and verify that main.py defines a FastAPI app surface with both health and domain routes before requesting more model turns unless a blocking error forces one narrow fix.",
        "Minimum API quality bar: expose a clear app object plus at least two meaningful endpoints or one health endpoint and one domain endpoint.",
    ),
    ship_acceptance_checks=(
        "python3 -m py_compile main.py",
        PYTHON_FASTAPI_MANIFEST_VALIDATION_COMMAND,
        "python3 -c \"from pathlib import Path; s=Path('main.py').read_text(encoding='utf-8'); required=('FastAPI(', 'app =', '/health', '/features'); missing=[item for item in required if item not in s]; print('python api structure ok' if not missing else 'missing: ' + ', '.join(missing)); raise SystemExit(1 if missing else 0)\"",
    ),
    ship_done_definition=(
        "The API service exposes a runnable FastAPI app object.",
        "The service passes syntax, dependency-manifest, and route-structure validation.",
    ),
    evaluator_criteria_specs=("functionality:0.8", "code_quality:0.7"),
)

NODE_EXPRESS_API = DeliveryFamilySpec(
    family_id="node_express_api",
    bootstrap_targets=("package.json", "main.js"),
    delivery_targets=("package.json", "main.js"),
    default_validation_commands=(
        "node --check main.js",
        NODE_EXPRESS_MANIFEST_VALIDATION_COMMAND,
        "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
    ),
    contract_instructions=(
        "This is a Node API delivery task. Prioritize a runnable Express service with a narrow, coherent endpoint surface.",
        "The task workspace starts empty or near-empty. Bootstrap the API service from scratch inside the current workspace before refining the endpoint behavior.",
        "Create the minimal Node/Express project files yourself when they are missing, including package.json and main.js.",
        "Treat main.js as the primary delivery surface unless the sprint clearly demands one small supporting module.",
        "Do not invent frontend files when the sprint can be satisfied by a focused API artifact.",
        "In the first implementation pass, establish the service shell and core delivery files together: package.json and main.js.",
        "After reading package.json and main.js, stop discovery and move directly into write_file/edit_file calls.",
        "Do not request another discovery round after the initial file read pass unless Node validation fails and the error requires one narrow fix.",
        "In the second model response at the latest, begin writing the API implementation instead of continuing analysis.",
        "After the first file pass, run syntax validation, verify package.json declares the Express dependency and a dev/start script, and verify that main.js defines an Express route surface with both health and domain routes before requesting more model turns unless a blocking error forces one narrow fix.",
        "Minimum API quality bar: expose a clear Express app with at least two meaningful endpoints or one health endpoint and one domain endpoint.",
    ),
    ship_acceptance_checks=(
        "node --check main.js",
        NODE_EXPRESS_MANIFEST_VALIDATION_COMMAND,
        "node -e \"const fs=require('fs'); const s=fs.readFileSync('main.js','utf8'); const required=['express','app.get(','/health','/features']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('missing: '+missing.join(', ')); process.exit(1)} else {console.log('node api structure ok')}\"",
    ),
    ship_done_definition=(
        "The API service exposes a runnable Express app entrypoint.",
        "The service passes syntax, dependency-manifest, and route-structure validation.",
    ),
    evaluator_criteria_specs=("functionality:0.8", "code_quality:0.7"),
)


def _normalize_string_items(value: object) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        cleaned = str(item).strip()
        if cleaned:
            items.append(cleaned)
    return items


def identify_delivery_family(product_spec: object) -> str:
    if not isinstance(product_spec, dict):
        return ""
    app_type = str(product_spec.get("app_type") or "").strip().lower()
    stack = {item.strip().lower() for item in _normalize_string_items(product_spec.get("stack"))}
    prompt = str(product_spec.get("prompt") or "").strip().lower()
    title = str(product_spec.get("title") or "").strip().lower()
    text = " ".join(part for part in [prompt, title] if part)

    if "express" in text or "node api" in text or "node backend" in text or "node service" in text:
        return NODE_EXPRESS_API.family_id
    if "next.js" in text or "nextjs" in text or "next app" in text:
        return NEXTJS_WEB.family_id
    if "svelte" in text or "sveltekit" in text or "svelte app" in text:
        return SVELTE_VITE_WEB.family_id
    if "vue" in text or "vue.js" in text or "vue app" in text:
        return VUE_VITE_WEB.family_id
    if "fastapi" in text:
        return PYTHON_FASTAPI_API.family_id

    backend_markers = {"fastapi", "django", "flask", "rails", "spring", "laravel", "express", "postgres", "mysql"}
    if app_type == "desktop_like_web_app" and ("next.js" in stack or "nextjs" in stack):
        return NEXTJS_WEB.family_id
    if app_type == "desktop_like_web_app" and "svelte" in stack:
        return SVELTE_VITE_WEB.family_id
    if app_type == "desktop_like_web_app" and "vue" in stack:
        return VUE_VITE_WEB.family_id
    if app_type == "desktop_like_web_app" and "react" in stack:
        return REACT_VITE_WEB.family_id
    if ("svelte" in stack or "sveltekit" in stack) and "vite" in stack and not (stack & backend_markers):
        return SVELTE_VITE_WEB.family_id
    if ("vue" in stack or "vue.js" in stack) and "vite" in stack and not (stack & backend_markers):
        return VUE_VITE_WEB.family_id
    if ("react" in stack or "vite" in stack) and not (stack & backend_markers):
        return REACT_VITE_WEB.family_id
    if any(
        token in text
        for token in ("landing page", "homepage", "site", "dashboard", "explorer", "editor", "studio", "demo")
    ):
        return REACT_VITE_WEB.family_id

    api_markers = ("api", "backend", "service", "endpoint", "server", "webhook")
    if "fastapi" in stack and any(marker in text for marker in api_markers):
        return PYTHON_FASTAPI_API.family_id
    if app_type == "api_service" and "fastapi" in stack:
        return PYTHON_FASTAPI_API.family_id
    if ("express" in stack or "node" in stack) and any(marker in text for marker in api_markers):
        return NODE_EXPRESS_API.family_id
    if app_type == "api_service" and ("express" in stack or "node" in stack):
        return NODE_EXPRESS_API.family_id
    return ""


def infer_delivery_family_from_prompt(prompt: str) -> str:
    normalized_prompt = prompt.strip().lower()
    if any(
        token in normalized_prompt
        for token in ("express", "node api", "node backend", "node service")
    ):
        return NODE_EXPRESS_API.family_id
    if any(
        token in normalized_prompt
        for token in ("next.js", "nextjs", "next app")
    ):
        return NEXTJS_WEB.family_id
    if any(
        token in normalized_prompt
        for token in ("svelte", "sveltekit", "svelte app")
    ):
        return SVELTE_VITE_WEB.family_id
    if any(
        token in normalized_prompt
        for token in ("vue", "vue.js", "vue app")
    ):
        return VUE_VITE_WEB.family_id
    if any(
        token in normalized_prompt
        for token in ("api", "backend", "service", "endpoint", "server", "webhook", "fastapi")
    ):
        return PYTHON_FASTAPI_API.family_id
    if any(
        token in normalized_prompt
        for token in ("landing page", "homepage", "site", "dashboard", "explorer", "editor", "studio", "demo", "app")
    ):
        return REACT_VITE_WEB.family_id
    return REACT_VITE_WEB.family_id


def get_delivery_family_spec(family_id: str) -> DeliveryFamilySpec | None:
    normalized = str(family_id or "").strip()
    if normalized == REACT_VITE_WEB.family_id:
        return REACT_VITE_WEB
    if normalized == NEXTJS_WEB.family_id:
        return NEXTJS_WEB
    if normalized == SVELTE_VITE_WEB.family_id:
        return SVELTE_VITE_WEB
    if normalized == VUE_VITE_WEB.family_id:
        return VUE_VITE_WEB
    if normalized == PYTHON_FASTAPI_API.family_id:
        return PYTHON_FASTAPI_API
    if normalized == NODE_EXPRESS_API.family_id:
        return NODE_EXPRESS_API
    return None


def delivery_family_targets(family_id: str, product_spec: dict[str, Any]) -> list[str]:
    spec = get_delivery_family_spec(family_id)
    if spec is None:
        return []
    targets = list(spec.delivery_targets or spec.bootstrap_targets)
    if family_id == REACT_VITE_WEB.family_id:
        title = str(product_spec.get("title") or "").strip()
        if title:
            import re

            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            if slug:
                targets.append(f"src/{slug}.ts")
    return targets


def delivery_family_validation_commands(family_id: str) -> list[str]:
    spec = get_delivery_family_spec(family_id)
    if spec is None:
        return []
    return list(spec.default_validation_commands)


def infer_delivery_family_from_artifact_paths(artifact_paths: list[str]) -> str:
    normalized = [str(path).strip() for path in artifact_paths if str(path).strip()]
    if any(path.endswith("dist/index.html") for path in normalized):
        return REACT_VITE_WEB.family_id
    if "next.config.mjs" in normalized and "app/page.tsx" in normalized:
        return NEXTJS_WEB.family_id
    if "src/App.svelte" in normalized and "package.json" in normalized:
        return SVELTE_VITE_WEB.family_id
    if "src/App.vue" in normalized and "package.json" in normalized:
        return VUE_VITE_WEB.family_id
    if "main.js" in normalized and "package.json" in normalized:
        return NODE_EXPRESS_API.family_id
    if "main.py" in normalized and "requirements.txt" in normalized:
        return PYTHON_FASTAPI_API.family_id
    if "package.json" in normalized or any(path.endswith("index.html") for path in normalized):
        return REACT_VITE_WEB.family_id
    return ""


def infer_delivery_family_from_workspace(workspace_root: Path) -> str:
    if (workspace_root / "requirements.txt").exists() and (workspace_root / "main.py").exists():
        return PYTHON_FASTAPI_API.family_id
    if (workspace_root / "next.config.mjs").exists() and (workspace_root / "app" / "page.tsx").exists():
        return NEXTJS_WEB.family_id
    if (workspace_root / "package.json").exists() and (workspace_root / "src" / "App.svelte").exists():
        return SVELTE_VITE_WEB.family_id
    if (workspace_root / "package.json").exists() and (workspace_root / "src" / "App.vue").exists():
        return VUE_VITE_WEB.family_id
    if (workspace_root / "package.json").exists() and (workspace_root / "main.js").exists():
        return NODE_EXPRESS_API.family_id
    if (workspace_root / "package.json").exists():
        return REACT_VITE_WEB.family_id
    if (workspace_root / "index.html").exists():
        return REACT_VITE_WEB.family_id
    return ""


def infer_artifact_kind_from_artifact_paths(artifact_paths: list[str]) -> str:
    normalized = [str(path).strip() for path in artifact_paths if str(path).strip()]
    if any(path.endswith("dist/index.html") for path in normalized):
        return "vite_dist"
    family_id = infer_delivery_family_from_artifact_paths(normalized)
    if family_id == PYTHON_FASTAPI_API.family_id:
        return "python_api_workspace"
    if family_id == NODE_EXPRESS_API.family_id:
        return "node_api_workspace"
    if family_id == NEXTJS_WEB.family_id:
        return "nextjs_workspace"
    if family_id == SVELTE_VITE_WEB.family_id:
        return "workspace_app"
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id} and any(path.endswith("index.html") for path in normalized):
        return "workspace_app"
    return "delivery_output"


def delivery_family_contract_instructions(family_id: str) -> list[str]:
    spec = get_delivery_family_spec(family_id)
    if spec is None:
        return []
    return list(spec.contract_instructions)


def delivery_family_ship_acceptance_checks(family_id: str) -> list[str]:
    spec = get_delivery_family_spec(family_id)
    if spec is None:
        return []
    return list(spec.ship_acceptance_checks)


def delivery_family_ship_done_definition(family_id: str) -> list[str]:
    spec = get_delivery_family_spec(family_id)
    if spec is None:
        return []
    return list(spec.ship_done_definition)


def delivery_family_evaluator_criteria_specs(family_id: str) -> list[str]:
    spec = get_delivery_family_spec(family_id)
    if spec is None:
        return []
    return list(spec.evaluator_criteria_specs)


def delivery_family_export_entrypoint(
    family_id: str,
    *,
    destination: Path,
    artifact_path: str = "",
) -> Path:
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id} and (destination / "dist" / "index.html").exists():
        return destination / "dist" / "index.html"
    if family_id == NEXTJS_WEB.family_id and (destination / "app" / "page.tsx").exists():
        return destination / "app" / "page.tsx"
    if family_id == PYTHON_FASTAPI_API.family_id and (destination / "main.py").exists():
        return destination / "main.py"
    if family_id == NODE_EXPRESS_API.family_id and (destination / "main.js").exists():
        return destination / "main.js"
    normalized_artifact_path = Path(artifact_path) if artifact_path else Path("index.html")
    exact_path = destination / normalized_artifact_path
    if exact_path.exists():
        return exact_path
    basename_path = destination / normalized_artifact_path.name
    if basename_path.exists():
        return basename_path
    return exact_path


def delivery_family_preview_command(
    family_id: str,
    *,
    destination: Path,
) -> str:
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id} and (destination / "dist" / "index.html").exists():
        return f"python3 -m http.server 4173 --directory {destination / 'dist'}"
    if family_id == NEXTJS_WEB.family_id:
        return "npm install --no-fund --no-audit && npm run dev"
    if family_id == PYTHON_FASTAPI_API.family_id:
        return "python3 -m pip install -r requirements.txt && python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
    if family_id == NODE_EXPRESS_API.family_id:
        return "npm install --no-fund --no-audit && npm run dev"
    return ""


def delivery_family_workspace_preview_command(
    family_id: str,
    *,
    artifact_paths: list[str],
    workspace_root: Path | None = None,
) -> str:
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id} and workspace_root is not None and any(
        path.endswith("dist/index.html") for path in artifact_paths
    ):
        return f"python3 -m http.server 4173 --directory {workspace_root / 'dist'}"
    if family_id == PYTHON_FASTAPI_API.family_id:
        if workspace_root is not None:
            return (
                f"cd {workspace_root} && python3 -m pip install -r requirements.txt && "
                "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
            )
        return "python3 -m pip install -r requirements.txt && python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
    if family_id == NEXTJS_WEB.family_id:
        if workspace_root is not None:
            return f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev"
        return "npm install --no-fund --no-audit && npm run dev"
    if family_id == NODE_EXPRESS_API.family_id:
        if workspace_root is not None:
            return f"cd {workspace_root} && npm install --no-fund --no-audit && npm run dev"
        return "npm install --no-fund --no-audit && npm run dev"
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id} and any(path.endswith("package.json") for path in artifact_paths):
        if workspace_root is not None:
            return (
                f"cd {workspace_root} && npm install --no-fund --no-audit "
                "&& npm run dev -- --host 0.0.0.0 --port 4173"
            )
        return "npm install --no-fund --no-audit && npm run dev -- --host 0.0.0.0 --port 4173"
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id} and any(path.endswith("index.html") for path in artifact_paths):
        return "python3 -m http.server 4173"
    return ""


def delivery_family_development_command(
    family_id: str,
    *,
    destination: Path,
) -> str:
    if family_id in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id} and (destination / "package.json").exists():
        return f"cd {destination} && npm install && npm run dev -- --host 0.0.0.0 --port 4173"
    if family_id == NEXTJS_WEB.family_id and (destination / "package.json").exists():
        return f"cd {destination} && npm install --no-fund --no-audit && npm run dev"
    if family_id == PYTHON_FASTAPI_API.family_id and (destination / "requirements.txt").exists() and (destination / "main.py").exists():
        return (
            f"cd {destination} && python3 -m pip install -r requirements.txt && "
            "python3 -m uvicorn main:app --host 0.0.0.0 --port 4173"
        )
    if family_id == NODE_EXPRESS_API.family_id and (destination / "package.json").exists() and (destination / "main.js").exists():
        return f"cd {destination} && npm install --no-fund --no-audit && npm run dev"
    return ""


def delivery_family_workspace_validation_commands(
    family_id: str,
    *,
    workspace_root: Path,
) -> list[str]:
    if family_id == PYTHON_FASTAPI_API.family_id and (workspace_root / "main.py").exists():
        return list(PYTHON_FASTAPI_API.default_validation_commands)
    if family_id == NODE_EXPRESS_API.family_id and (workspace_root / "main.js").exists():
        return list(NODE_EXPRESS_API.default_validation_commands)
    if family_id not in {REACT_VITE_WEB.family_id, VUE_VITE_WEB.family_id, SVELTE_VITE_WEB.family_id, NEXTJS_WEB.family_id} or not (workspace_root / "package.json").exists():
        return []
    try:
        payload = json.loads((workspace_root / "package.json").read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    scripts = payload.get("scripts") if isinstance(payload, dict) else {}
    if not isinstance(scripts, dict):
        return []
    if isinstance(scripts.get("build"), str) and scripts.get("build", "").strip():
        commands = ["npm install --no-fund --no-audit", "npm run build"]
        commands.extend(delivery_family_validation_commands(family_id)[1:])
        return commands
    if isinstance(scripts.get("test"), str) and scripts.get("test", "").strip():
        return ["npm install --no-fund --no-audit", "npm test"]
    return []
