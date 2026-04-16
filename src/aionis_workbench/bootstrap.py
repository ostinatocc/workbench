from __future__ import annotations

from pathlib import Path
from typing import Any
import subprocess

from .consolidation import describe_family_prior_seed
from .consolidation_state import load_consolidation_summary
from .session import load_auto_learning_snapshot


SOURCE_ROOT_CANDIDATES = ("src", "app", "lib")
TEST_ROOT_CANDIDATES = ("tests", "test")
MANIFEST_CANDIDATES = (
    "pyproject.toml",
    "pytest.ini",
    "tox.ini",
    "setup.py",
    "requirements.txt",
    "package.json",
    "README.md",
)
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".aionis-workbench",
    "dist",
    "build",
}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}
TEST_FILE_MARKERS = ("test_", "_test", ".spec.", ".test.")


def _relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _existing_named_paths(repo_root: Path, names: tuple[str, ...]) -> list[str]:
    return [
        _relative(repo_root / name, repo_root)
        for name in names
        if (repo_root / name).exists()
    ]


def _looks_like_test_file(path: Path) -> bool:
    name = path.name.lower()
    return any(marker in name for marker in TEST_FILE_MARKERS)


def _collect_examples(repo_root: Path, roots: list[str], *, want_tests: bool, limit: int = 4) -> list[str]:
    examples: list[str] = []
    for root_name in roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if len(examples) >= limit:
                return examples
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            suffix = path.suffix.lower()
            if want_tests:
                if not (_looks_like_test_file(path) or root_name in TEST_ROOT_CANDIDATES):
                    continue
            elif suffix not in SOURCE_SUFFIXES:
                continue
            examples.append(_relative(path, repo_root))
    return examples


def _detect_language(manifests: list[str], source_examples: list[str], test_examples: list[str]) -> str:
    manifest_names = {Path(item).name for item in manifests}
    sample_names = source_examples + test_examples
    if {"pyproject.toml", "pytest.ini", "tox.ini", "setup.py", "requirements.txt"} & manifest_names:
        return "python"
    if "package.json" in manifest_names:
        return "node"
    if any(item.endswith(".py") for item in sample_names):
        return "python"
    if any(item.endswith((".ts", ".tsx", ".js", ".jsx")) for item in sample_names):
        return "node"
    return "unknown"


def _bootstrap_validation_commands(
    *,
    language: str,
    source_roots: list[str],
    test_roots: list[str],
) -> list[str]:
    if language == "python" and test_roots:
        if "src" in source_roots:
            return ["PYTHONPATH=src python3 -m pytest -q"]
        return ["python3 -m pytest -q"]
    if language == "node" and test_roots:
        return ["npm test"]
    return []


def _bootstrap_working_set(
    *,
    source_roots: list[str],
    test_roots: list[str],
    source_examples: list[str],
    test_examples: list[str],
    manifests: list[str],
    history_files: list[str],
    learning_files: list[str],
) -> list[str]:
    ranked = [
        *learning_files[:3],
        *history_files[:2],
        *source_examples[:2],
        *test_examples[:2],
        *source_roots[:1],
        *test_roots[:1],
        *manifests[:2],
    ]
    return list(dict.fromkeys(item for item in ranked if item))[:8]


def _bootstrap_focus(working_set: list[str], source_roots: list[str], test_roots: list[str], manifests: list[str]) -> list[str]:
    preferred = [item for item in working_set if "/" in item][:3]
    if preferred:
        return preferred[:3]
    fallback = [*source_roots[:1], *test_roots[:1], *manifests[:1]]
    return [item for item in fallback if item][:3]


def _bootstrap_reuse_summary(
    *,
    recent_family_priors: list[dict[str, Any]],
    learning_samples: list[dict[str, Any]],
) -> str:
    if recent_family_priors:
        prior = recent_family_priors[0]
        family = str(prior.get("task_family") or "task:unknown")
        strategy = str(prior.get("dominant_strategy_profile") or "unknown")
        validation = str(prior.get("dominant_validation_command") or "").strip()
        if validation:
            return f"recent prior: {family} via {strategy}; keep the first task close to {validation}"
        return f"recent prior: {family} via {strategy}; keep the first task close to that family slice"
    if learning_samples:
        sample = learning_samples[0]
        task_id = str(sample.get("task_id") or "recent task")
        validation = str(sample.get("validation_command") or "").strip()
        if validation:
            return f"recent learning: {task_id} validated with {validation}"
        return f"recent learning: {task_id} can seed the first narrow loop"
    return "no reusable prior yet; the first validated success will seed future family reuse"


def _collect_recent_git_history(repo_root: Path, *, limit: int = 6) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"-n{limit}",
                "--date=short",
                "--format=%H%x1f%ad%x1f%s",
                "--name-only",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return [], [], []

    commits: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                commits.append(current)
                current = None
            continue
        if "\x1f" in line:
            if current:
                commits.append(current)
            sha, date, subject = (part.strip() for part in line.split("\x1f", 2))
            current = {
                "commit": sha[:12],
                "date": date,
                "subject": subject,
                "files": [],
            }
            continue
        if current is None:
            continue
        candidate = Path(line)
        if any(part in SKIP_DIRS for part in candidate.parts):
            continue
        current["files"].append(candidate.as_posix())
    if current:
        commits.append(current)

    commit_subjects = [item["subject"] for item in commits[:limit] if item.get("subject")]
    changed_files = list(
        dict.fromkeys(
            file_path
            for commit in commits[:limit]
            for file_path in commit.get("files", [])[:4]
            if file_path
        )
    )[:8]
    return commits[:limit], commit_subjects[:limit], changed_files


def build_bootstrap_snapshot(
    *,
    repo_root: str,
    project_identity: str,
    project_scope: str,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    auto_learning = load_auto_learning_snapshot(str(root), project_scope=project_scope)
    consolidation = load_consolidation_summary(repo_root=str(root), project_scope=project_scope)
    learning_samples = auto_learning.get("recent_samples") if isinstance(auto_learning, dict) else []
    family_rows = consolidation.get("family_rows") if isinstance(consolidation, dict) else []
    if not isinstance(learning_samples, list):
        learning_samples = []
    if not isinstance(family_rows, list):
        family_rows = []
    learning_files = list(
        dict.fromkeys(
            item
            for sample in learning_samples[:3]
            if isinstance(sample, dict)
            for item in (sample.get("working_set") or [])[:3]
            if isinstance(item, str) and item.strip()
        )
    )[:6]
    learning_validation_commands = list(
        dict.fromkeys(
            str(sample.get("validation_command") or "").strip()
            for sample in learning_samples[:3]
            if isinstance(sample, dict) and str(sample.get("validation_command") or "").strip()
        )
    )[:2]
    recent_family_priors = [
        {
            "task_family": str(row.get("task_family") or "task:unknown"),
            "status": str(row.get("status") or "unknown"),
            "confidence": float(row.get("confidence") or 0.0),
            "sample_count": int(row.get("sample_count") or 0),
            "recent_success_count": int(row.get("recent_success_count") or 0),
            "manual_ingest_count": int(row.get("manual_ingest_count") or 0),
            "workflow_closure_count": int(row.get("workflow_closure_count") or 0),
            "run_resume_count": int(row.get("run_resume_count") or 0),
            "validate_count": int(row.get("validate_count") or 0),
            "passive_observation_count": int(row.get("passive_observation_count") or 0),
            "dominant_strategy_profile": str(row.get("dominant_strategy_profile") or "unknown"),
            "dominant_validation_style": str(row.get("dominant_validation_style") or "unknown"),
            "dominant_validation_command": str(row.get("dominant_validation_command") or "").strip(),
            "dominant_working_set": list(row.get("dominant_working_set") or [])[:4],
        }
        for row in family_rows[:3]
        if isinstance(row, dict) and str(row.get("task_family") or "").strip()
    ]
    for prior in recent_family_priors:
        prior.update(describe_family_prior_seed(prior))
    source_roots = _existing_named_paths(root, SOURCE_ROOT_CANDIDATES)
    test_roots = _existing_named_paths(root, TEST_ROOT_CANDIDATES)
    manifests = _existing_named_paths(root, MANIFEST_CANDIDATES)
    source_examples = _collect_examples(root, source_roots, want_tests=False)
    test_examples = _collect_examples(root, test_roots, want_tests=True)
    recent_commits, recent_commit_subjects, recent_changed_files = _collect_recent_git_history(root)
    language = _detect_language(manifests, source_examples, test_examples)
    validation_commands = _bootstrap_validation_commands(
        language=language,
        source_roots=source_roots,
        test_roots=test_roots,
    )
    validation_commands = list(dict.fromkeys([*learning_validation_commands, *validation_commands]))[:3]
    working_set = _bootstrap_working_set(
        source_roots=source_roots,
        test_roots=test_roots,
        source_examples=source_examples,
        test_examples=test_examples,
        manifests=manifests,
        history_files=recent_changed_files,
        learning_files=learning_files,
    )
    bootstrap_focus = _bootstrap_focus(working_set, source_roots, test_roots, manifests)
    if validation_commands:
        next_action = "Create one narrow first task inside the bootstrap working set, then run the first suggested validation command."
    elif working_set:
        next_action = "Create one narrow first task inside the bootstrap working set and define the first runnable validation command."
    else:
        next_action = "Create the first narrow task, establish a source area, a test location, and one runnable validation command."
    if bootstrap_focus:
        bootstrap_first_step = (
            "Start with "
            + ", ".join(bootstrap_focus[:2])
            + " and keep the first task inside that slice."
        )
    else:
        bootstrap_first_step = "Pick one small source area and one matching test surface before widening scope."
    if validation_commands:
        bootstrap_validation_step = f"Run {validation_commands[0]} before expanding the working set."
    else:
        bootstrap_validation_step = "Define one runnable validation command before expanding the working set."
    bootstrap_reuse_summary = _bootstrap_reuse_summary(
        recent_family_priors=recent_family_priors,
        learning_samples=learning_samples,
    )
    notes: list[str] = []
    if source_roots:
        notes.append("Detected source roots: " + ", ".join(source_roots[:3]))
    if test_roots:
        notes.append("Detected test roots: " + ", ".join(test_roots[:3]))
    if manifests:
        notes.append("Detected manifests: " + ", ".join(manifests[:3]))
    if recent_commit_subjects:
        notes.append("Imported recent history: " + "; ".join(recent_commit_subjects[:2]))
    if learning_samples:
        notes.append(
            "Loaded recent auto-learning: "
            + "; ".join(
                str(sample.get("task_id") or "").strip()
                for sample in learning_samples[:2]
                if isinstance(sample, dict) and str(sample.get("task_id") or "").strip()
            )
        )
    if recent_family_priors:
        notes.append(
            "Loaded family priors: "
            + "; ".join(
                f"{item['task_family']} -> {item['dominant_strategy_profile']}"
                for item in recent_family_priors[:2]
            )
        )
    return {
        "project_identity": project_identity,
        "project_scope": project_scope,
        "language": language,
        "source_roots": source_roots[:4],
        "test_roots": test_roots[:4],
        "manifest_files": manifests[:6],
        "source_examples": source_examples[:4],
        "test_examples": test_examples[:4],
        "recent_commits": recent_commits[:4],
        "recent_commit_subjects": recent_commit_subjects[:4],
        "recent_changed_files": recent_changed_files[:8],
        "recent_auto_learning": learning_samples[:4],
        "recent_family_priors": recent_family_priors,
        "bootstrap_working_set": working_set,
        "bootstrap_focus": bootstrap_focus,
        "bootstrap_validation_commands": validation_commands[:3],
        "next_action": next_action,
        "bootstrap_first_step": bootstrap_first_step,
        "bootstrap_validation_step": bootstrap_validation_step,
        "bootstrap_reuse_summary": bootstrap_reuse_summary,
        "notes": notes[:4],
        "history_status": "imported" if recent_commit_subjects else "unavailable",
        "status": "bootstrap_ready" if working_set or validation_commands else "bootstrap_minimal",
    }
