from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpcore
import httpx

from .session import ArtifactReference, SessionState, save_artifact_payload


@dataclass
class ValidationResult:
    ok: bool
    command: str | None
    exit_code: int | None
    summary: str
    output: str
    changed_files: list[str]


@dataclass
class RecoveryDecision:
    should_pause: bool
    next_action: str
    summary: str
    evidence: list[dict[str, object]]


def _compact_output(output: str, *, limit: int = 1200) -> str:
    cleaned = output.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n...[truncated]"


def _first_signal_line(output: str) -> str:
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return ""


def _extract_pytest_failure_name(output: str) -> str:
    match = re.search(r"^_{4,}\s+(.+?)\s+_{4,}$", output, flags=re.MULTILINE)
    if match:
        candidate = match.group(1).strip()[:240]
        if "::" in candidate or (candidate and not candidate.endswith(".py")):
            return candidate
    match = re.search(r"^FAILED\s+(.+)$", output, flags=re.MULTILINE)
    if match:
        candidate = match.group(1).strip()[:240]
        if " - " in candidate:
            candidate = candidate.split(" - ", 1)[0].strip()
        if "::" in candidate:
            return candidate
    return ""


def _extract_pytest_failure_names(output: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"^_{4,}\s+(.+?)\s+_{4,}$", output, flags=re.MULTILINE):
        name = match.group(1).strip()[:240]
        if not name or (name.endswith(".py") and "::" not in name):
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)
    for match in re.finditer(r"^FAILED\s+(.+)$", output, flags=re.MULTILINE):
        name = match.group(1).strip()[:240]
        if " - " in name:
            name = name.split(" - ", 1)[0].strip()
        if not name or "::" not in name:
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names[:32]


def _extract_pytest_error_line(output: str) -> str:
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("E "):
            return cleaned[:240]
    return _first_signal_line(output)


def _build_exact_pytest_command(command: str, failure_name: str) -> str:
    cleaned = command.strip()
    exact = failure_name.strip()
    if not cleaned or not exact:
        return cleaned
    if "pytest" not in cleaned:
        return cleaned
    if re.search(r"\s-k\s+", cleaned):
        cleaned = re.sub(r"""(\s-k\s+)(?:"[^"]*"|'[^']*'|[^\s]+)""", rf"\1'{exact}'", cleaned, count=1)
    else:
        cleaned = cleaned + f" -k '{exact}'"
    return cleaned


def _parse_rollback_spans(*, suspicious_file: str, revert_spans: list[Any]) -> list[tuple[int, int, int, int, str]]:
    parsed_spans: list[tuple[int, int, int, int, str]] = []
    hunk_pattern = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    prefix = suspicious_file + " "
    for item in revert_spans:
        if not isinstance(item, str) or not item.startswith(prefix):
            continue
        match = hunk_pattern.search(item[len(prefix) :])
        if not match:
            continue
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        parsed_spans.append((old_start, old_count, new_start, new_count, item))
    return parsed_spans


def _extract_focus_tokens(*values: str) -> list[str]:
    stopwords = {
        "test",
        "with",
        "uses",
        "use",
        "latest",
        "result",
        "value",
        "args",
        "main",
        "click",
        "option",
        "command",
        "workbench",
        "narrowly",
        "scoped",
        "keep",
        "fix",
    }
    seen: set[str] = set()
    tokens: list[str] = []
    for value in values:
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", value.lower()):
            normalized = token.strip("_")
            if len(normalized) < 4 or normalized in stopwords or normalized in seen:
                continue
            seen.add(normalized)
            tokens.append(normalized)
    return tokens[:12]


class RecoveryService:
    def __init__(
        self,
        *,
        repo_root: str,
        trace_summary_fn: Callable[[list[Any]], dict[str, Any]],
        extract_target_files_fn: Callable[..., list[str]],
        run_validation_commands_fn: Callable[[list[str]], ValidationResult],
        model_timeout_type: type[BaseException],
    ) -> None:
        self._repo_root = repo_root
        self._trace_summary = trace_summary_fn
        self._extract_target_files = extract_target_files_fn
        self._run_validation_commands = run_validation_commands_fn
        self._model_timeout_type = model_timeout_type

    def failure_artifact_payload(
        self,
        *,
        session: SessionState,
        exc: Exception,
        trace_steps: list[Any],
        changed_files: list[str] | None = None,
    ) -> dict[str, Any]:
        message = str(exc).strip() or exc.__class__.__name__
        return {
            "kind": "timeout_artifact"
            if isinstance(exc, (self._model_timeout_type, httpx.ReadTimeout, httpcore.ReadTimeout))
            else "exception_artifact",
            "role": "orchestrator",
            "summary": f"Workbench execution failed: {message}",
            "message": message,
            "trace_summary": self._trace_summary(trace_steps),
            "working_set": session.target_files[:8],
            "changed_files": (changed_files or [])[:8],
            "evidence": [f"{step.tool_name} [{step.status}]" for step in trace_steps[-8:]],
        }

    def load_rollback_payload(self, session: SessionState) -> dict[str, Any]:
        artifact = next((item for item in session.artifacts if item.kind == "rollback_hint_artifact"), None)
        if artifact is None:
            return {}
        artifact_path = Path(session.repo_root) / artifact.path
        if artifact_path.exists():
            try:
                payload = json.loads(artifact_path.read_text())
                if isinstance(payload, dict):
                    return payload
            except Exception:
                return {}
        return {}

    def load_correction_working_set(self, session: SessionState) -> list[str]:
        artifact = next((item for item in session.artifacts if item.kind == "correction_packet_artifact"), None)
        if artifact is None:
            return session.target_files[:6]
        artifact_path = Path(session.repo_root) / artifact.path
        if artifact_path.exists():
            try:
                payload = json.loads(artifact_path.read_text())
                working_set = payload.get("working_set")
                if isinstance(working_set, list):
                    cleaned = [item for item in working_set if isinstance(item, str) and item.strip()]
                    if cleaned:
                        return cleaned[:6]
            except Exception:
                pass
        return session.target_files[:6]

    def load_correction_failure_name(self, session: SessionState) -> str:
        packet = session.execution_packet
        if packet:
            for candidate in packet.accepted_facts:
                if not isinstance(candidate, str):
                    continue
                match = re.search(r"baseline failing test is\s+(.+)", candidate, re.IGNORECASE)
                if match and match.group(1).strip():
                    return match.group(1).strip()[:240]
        for candidate in (session.context_layers_snapshot or {}).get("facts", []):
            if not isinstance(candidate, str):
                continue
            match = re.search(r"Baseline failing test:\s*(.+)", candidate)
            if match and match.group(1).strip():
                return match.group(1).strip()[:240]
        rollback_artifact = next((item for item in session.artifacts if item.kind == "rollback_hint_artifact"), None)
        if rollback_artifact is not None:
            artifact_path = Path(session.repo_root) / rollback_artifact.path
            if artifact_path.exists():
                try:
                    payload = json.loads(artifact_path.read_text())
                    command = payload.get("command")
                    if isinstance(command, str):
                        match = re.search(r"""\s-k\s+(?:"([^"]+)"|'([^']+)'|([^\s]+))""", command)
                        if match:
                            exact = next((group for group in match.groups() if isinstance(group, str) and group.strip()), "")
                            if exact:
                                return exact.strip()[:240]
                    for candidate in (
                        *((payload.get("evidence") or []) if isinstance(payload.get("evidence"), list) else []),
                        payload.get("summary"),
                        payload.get("message"),
                    ):
                        if not isinstance(candidate, str):
                            continue
                        match = re.search(r"Baseline failing test:\s*(.+)", candidate)
                        if match and match.group(1).strip():
                            return match.group(1).strip()[:240]
                except Exception:
                    pass
        artifact = next((item for item in session.artifacts if item.kind == "correction_packet_artifact"), None)
        if artifact is None:
            return ""
        failure_name = artifact.metadata.get("failure_name")
        if isinstance(failure_name, str) and failure_name.strip():
            return failure_name.strip()
        artifact_path = Path(session.repo_root) / artifact.path
        if artifact_path.exists():
            try:
                payload = json.loads(artifact_path.read_text())
                failure_name = payload.get("failure_name")
                if isinstance(failure_name, str) and failure_name.strip():
                    return failure_name.strip()
                command = payload.get("command")
                if isinstance(command, str):
                    match = re.search(r"""\s-k\s+(?:"([^"]+)"|'([^']+)'|([^\s]+))""", command)
                    if match:
                        exact = next((group for group in match.groups() if isinstance(group, str) and group.strip()), "")
                        if exact:
                            return exact.strip()[:240]
                for candidate in (
                    payload.get("message"),
                    payload.get("summary"),
                    *((payload.get("evidence") or []) if isinstance(payload.get("evidence"), list) else []),
                ):
                    if not isinstance(candidate, str):
                        continue
                    match = re.search(r"Baseline failing test:\s*(.+)", candidate)
                    if match and match.group(1).strip():
                        return match.group(1).strip()[:240]
            except Exception:
                pass
        validation_output = (session.last_validation_result or {}).get("output")
        if isinstance(validation_output, str):
            match = re.search(r"Baseline failing test:\s*(.+)", validation_output)
            if match and match.group(1).strip():
                return match.group(1).strip()[:240]
        return ""

    def build_existing_rollback_recovery(self, session: SessionState) -> dict[str, Any] | None:
        payload = self.load_rollback_payload(session)
        if not payload:
            return None
        spans = [
            value.strip()
            for value in payload.get("revert_spans", [])
            if isinstance(value, str) and value.strip()
        ]
        suspicious_file = payload.get("suspicious_file")
        if not spans:
            return None
        return {
            "attempted": True,
            "applied": False,
            "suspicious_file": suspicious_file if isinstance(suspicious_file, str) else "",
            "revert_spans": spans,
        }

    def build_correction_packet(self, session: SessionState) -> dict[str, Any] | None:
        validation = session.last_validation_result or {}
        command = validation.get("command")
        output = validation.get("output")
        ok = validation.get("ok")
        if ok is True or not isinstance(command, str) or not command.strip():
            return None
        output_text = output if isinstance(output, str) else ""
        failure_name = self.load_correction_failure_name(session) or _extract_pytest_failure_name(output_text)
        error_line = _extract_pytest_error_line(output_text)
        changed_files = validation.get("changed_files")
        changed = [item for item in changed_files if isinstance(item, str) and item.strip()] if isinstance(changed_files, list) else []
        focused_files = [item for item in session.target_files if item in changed] or session.target_files[:4] or changed[:4]
        narrowed_changed = focused_files[:]
        summary_bits = ["Deterministic correction packet prepared from the latest validation failure."]
        if failure_name:
            summary_bits.append(f"Primary failing test: {failure_name}.")
        if error_line:
            summary_bits.append(f"Primary error: {error_line}")
        return {
            "kind": "correction_packet_artifact",
            "role": "orchestrator",
            "summary": " ".join(summary_bits)[:240],
            "message": error_line or "Validation failed and requires direct correction.",
            "trace_summary": session.last_trace_summary,
            "working_set": focused_files[:6],
            "changed_files": narrowed_changed[:8],
            "evidence": [
                *(["Failing test: " + failure_name] if failure_name else []),
                *(["Failing command: " + command.strip()] if command else []),
                *(["Primary error: " + error_line] if error_line else []),
            ],
            "command": command.strip(),
            "failure_name": failure_name,
        }

    def apply_narrow_scope_guard(
        self,
        *,
        session: SessionState,
        trace_steps: list[Any],
        validation: ValidationResult,
    ) -> ValidationResult:
        allowed = self.load_correction_working_set(session)
        if not allowed:
            return validation
        observed = self._extract_target_files(trace_steps, repo_root=session.repo_root, limit=24)
        extras = [item for item in observed if item not in allowed]
        if not extras:
            return validation
        summary = "Scope drift detected: touched files outside the correction packet working set."
        details = [
            "Allowed working set: " + ", ".join(allowed[:6]),
            "Observed out-of-scope files: " + ", ".join(extras[:8]),
        ]
        if validation.command:
            details.append("Validation command: " + validation.command)
        if validation.summary:
            details.append("Prior validation summary: " + validation.summary)
        return ValidationResult(
            ok=False,
            command=validation.command,
            exit_code=validation.exit_code if validation.exit_code is not None else 2,
            summary=summary,
            output=_compact_output("\n".join(details)),
            changed_files=[*allowed[:6], *extras[:8]],
        )

    def apply_regression_expansion_guard(
        self,
        *,
        session: SessionState,
        validation: ValidationResult,
    ) -> ValidationResult:
        baseline_failure = self.load_correction_failure_name(session)
        if not baseline_failure or validation.ok or not validation.output:
            return validation
        current_failures = _extract_pytest_failure_names(validation.output)
        if not current_failures:
            return validation
        extras = [item for item in current_failures if item != baseline_failure]
        if not extras:
            return validation
        allowed = self.load_correction_working_set(session)
        details = [
            "Baseline failing test: " + baseline_failure,
            "Current failing tests: " + ", ".join(current_failures[:12]),
            "Correction working set: " + ", ".join(allowed[:6]),
        ]
        if validation.command:
            details.append("Validation command: " + validation.command)
        return ValidationResult(
            ok=False,
            command=validation.command,
            exit_code=validation.exit_code if validation.exit_code is not None else 3,
            summary="Regression expansion detected: the failing set broadened beyond the baseline correction target.",
            output=_compact_output("\n".join(details)),
            changed_files=allowed[:6],
        )

    def build_rollback_hint(
        self,
        *,
        session: SessionState,
        validation: ValidationResult | None,
        recovery_result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if validation is None or validation.ok:
            return None
        recovery_failed = bool(
            isinstance(recovery_result, dict)
            and recovery_result.get("attempted")
            and not recovery_result.get("applied")
        )
        if not (
            validation.summary.startswith("Regression expansion detected:")
            or validation.summary.startswith("Scope drift detected:")
            or recovery_failed
        ):
            return None
        working_set = self.load_correction_working_set(session)
        if not working_set:
            return None
        baseline_failure = self.load_correction_failure_name(session)
        suspicious_file = working_set[0]
        if isinstance(recovery_result, dict):
            candidate_file = recovery_result.get("suspicious_file")
            if isinstance(candidate_file, str) and candidate_file.strip():
                suspicious_file = candidate_file.strip()
        hunk_hints: list[str] = []
        try:
            completed = subprocess.run(
                ["git", "diff", "--unified=0", "--", *working_set[:4]],
                cwd=session.repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            current_file = ""
            for line in completed.stdout.splitlines():
                if line.startswith("+++ b/"):
                    current_file = line[len("+++ b/") :].strip()
                elif line.startswith("@@") and current_file:
                    hunk_hints.append(f"{current_file} {line.strip()}")
        except Exception:
            hunk_hints = []

        ranked_spans = self._rank_rollback_spans(
            session=session,
            suspicious_file=suspicious_file,
            parsed_spans=_parse_rollback_spans(suspicious_file=suspicious_file, revert_spans=hunk_hints),
        )
        ranked_hints = [item for *_, item in ranked_spans]
        preferred_hints = []
        if isinstance(recovery_result, dict):
            preferred_hints = [
                item.strip()
                for item in recovery_result.get("revert_spans", [])
                if isinstance(item, str) and item.strip()
            ]
        if preferred_hints:
            merged_hints: list[str] = []
            seen_hints: set[str] = set()
            for item in [*preferred_hints, *ranked_hints]:
                if item in seen_hints:
                    continue
                seen_hints.add(item)
                merged_hints.append(item)
            ranked_hints = merged_hints
        summary = f"Rollback hint: revert the latest narrow edit in {suspicious_file} before revalidating."
        if recovery_failed:
            summary = f"Rollback hint: retry the strongest deterministic rollback candidate in {suspicious_file} before broadening scope."
        evidence = []
        if validation.summary:
            evidence.append("Validation summary: " + validation.summary)
        if validation.command:
            evidence.append("Validation command: " + validation.command)
        if baseline_failure:
            evidence.append("Baseline failing test: " + baseline_failure)
        if preferred_hints:
            evidence.append("Best rollback candidate: " + " | ".join(preferred_hints[:3]))
        evidence.extend("Revert span hint: " + item for item in ranked_hints[:3])
        rollback_command = validation.command or ""
        if session.validation_commands:
            rollback_command = session.validation_commands[0]
        if baseline_failure:
            rollback_command = _build_exact_pytest_command(rollback_command, baseline_failure)
        return {
            "kind": "rollback_hint_artifact",
            "role": "orchestrator",
            "summary": summary,
            "message": validation.summary,
            "trace_summary": session.last_trace_summary,
            "working_set": working_set[:6],
            "changed_files": working_set[:6],
            "evidence": evidence[:6],
            "command": rollback_command,
            "suspicious_file": suspicious_file,
            "revert_spans": ranked_hints[:6],
        }

    def _rank_rollback_spans(
        self,
        *,
        session: SessionState,
        suspicious_file: str,
        parsed_spans: list[tuple[int, int, int, int, str]],
    ) -> list[tuple[int, int, int, int, str]]:
        file_path = Path(session.repo_root) / suspicious_file
        try:
            lines = file_path.read_text().splitlines()
        except Exception:
            return parsed_spans
        focus_tokens = _extract_focus_tokens(
            self.load_correction_failure_name(session),
            session.goal,
            str((session.last_validation_result or {}).get("summary") or ""),
            str((session.last_validation_result or {}).get("output") or ""),
        )
        if not focus_tokens:
            return parsed_spans

        ranked: list[tuple[int, int, int, int, str, tuple[int, int, int]]] = []
        for old_start, old_count, new_start, new_count, raw_span in parsed_spans:
            start_index = max(new_start - 6, 0)
            end_index = min(new_start + max(new_count, 1) + 6, len(lines))
            snippet = "\n".join(lines[start_index:end_index]).lower()
            token_hits = sum(1 for token in focus_tokens if token in snippet)
            callback_bonus = 2 if "callback" in snippet else 0
            flag_bonus = 1 if "flag_value" in snippet or "parser_name" in snippet else 0
            scope_penalty = 1 if "help_option" in snippet or "format_help" in snippet else 0
            ranked.append(
                (
                    old_start,
                    old_count,
                    new_start,
                    new_count,
                    raw_span,
                    (token_hits + callback_bonus + flag_bonus - scope_penalty, token_hits, -new_start),
                )
            )
        ranked.sort(key=lambda item: item[5], reverse=True)
        return [(a, b, c, d, e) for a, b, c, d, e, _ in ranked]

    def attempt_rollback_recovery(
        self,
        session: SessionState,
        *,
        max_single_candidates: int = 4,
        max_pair_candidates: int = 6,
        max_triple_candidates: int = 4,
    ) -> dict[str, Any] | None:
        rollback = self.load_rollback_payload(session)
        if not rollback:
            return None

        suspicious_file = rollback.get("suspicious_file")
        revert_spans = rollback.get("revert_spans")
        if not isinstance(suspicious_file, str) or not suspicious_file.strip():
            return None
        if not isinstance(revert_spans, list) or not revert_spans:
            return None

        target_path = Path(self._repo_root) / suspicious_file
        if not target_path.exists():
            return None

        try:
            head = subprocess.run(
                ["git", "show", f"HEAD:{suspicious_file}"],
                cwd=self._repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            return {
                "attempted": False,
                "reason": f"Could not load HEAD content for rollback: {exc}",
            }

        original_text = target_path.read_text()
        current_lines = original_text.splitlines(keepends=True)
        head_lines = head.stdout.splitlines(keepends=True)
        parsed_spans = _parse_rollback_spans(suspicious_file=suspicious_file, revert_spans=revert_spans)
        if not parsed_spans:
            return {
                "attempted": False,
                "reason": "Rollback hint did not contain any parseable revert spans.",
            }

        baseline_failure = self.load_correction_failure_name(session)
        attempted_details: list[str] = []
        last_validation: ValidationResult | None = None
        best_candidate: tuple[tuple[int, int, int, int], list[str], ValidationResult] | None = None

        def candidate_score(validation: ValidationResult) -> tuple[int, int, int, int]:
            failures = _extract_pytest_failure_names(validation.output)
            extras = [item for item in failures if item != baseline_failure]
            baseline_missing = 0 if (not baseline_failure or baseline_failure in failures or not failures) else 1
            syntax_penalty = 1 if "syntax error" in validation.summary.lower() else 0
            return (
                syntax_penalty,
                len(extras),
                baseline_missing,
                len(failures) if failures else 1,
            )

        def evaluate_candidate(
            candidate_spans: list[tuple[int, int, int, int, str]],
        ) -> tuple[ValidationResult | None, str]:
            updated_lines = current_lines[:]
            for old_start, old_count, new_start, new_count, _raw_span in sorted(
                candidate_spans,
                key=lambda item: item[2],
                reverse=True,
            ):
                replacement = head_lines[max(old_start - 1, 0) : max(old_start - 1, 0) + old_count]
                start_index = max(new_start - 1, 0)
                end_index = start_index + max(new_count, 0)
                updated_lines[start_index:end_index] = replacement
            updated_text = "".join(updated_lines)
            if updated_text == original_text:
                return None, "no-op"

            target_path.write_text(updated_text)
            syntax_check = subprocess.run(
                ["python3", "-m", "py_compile", suspicious_file],
                cwd=self._repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            if syntax_check.returncode != 0:
                syntax_output = "\n".join(
                    part for part in [syntax_check.stdout, syntax_check.stderr] if isinstance(part, str) and part.strip()
                ).strip()
                validation = ValidationResult(
                    ok=False,
                    command=f"python3 -m py_compile {suspicious_file}",
                    exit_code=syntax_check.returncode,
                    summary="Rollback recovery produced a syntax error and was reverted.",
                    output=_compact_output(syntax_output),
                    changed_files=[suspicious_file],
                )
                target_path.write_text(original_text)
                return validation, "syntax_error"

            if baseline_failure and session.validation_commands:
                exact_command = _build_exact_pytest_command(session.validation_commands[0], baseline_failure)
                validation = self._run_validation_commands([exact_command])
                if validation.ok and exact_command != session.validation_commands[0]:
                    validation = self._run_validation_commands(session.validation_commands)
            else:
                validation = self._run_validation_commands(session.validation_commands)
            validation = self.apply_regression_expansion_guard(session=session, validation=validation)
            if not validation.ok:
                target_path.write_text(original_text)
            return validation, "validated"

        top_spans = parsed_spans[:max(1, max_single_candidates)]
        syntax_safe_spans: list[tuple[int, int, int, int, str]] = []

        for candidate in [[item] for item in top_spans]:
            validation, mode = evaluate_candidate(candidate)
            span_labels = [raw_span for *_rest, raw_span in candidate]
            if validation is None:
                attempted_details.append("No-op rollback candidate skipped: " + " | ".join(span_labels))
                continue
            last_validation = validation
            if validation.ok:
                return {
                    "attempted": True,
                    "applied": True,
                    "suspicious_file": suspicious_file,
                    "revert_spans": span_labels,
                    "summary": f"Rollback recovery succeeded after reverting {len(candidate)} narrow span(s) in {suspicious_file}.",
                    "baseline_failure": baseline_failure,
                    "validation": validation,
                }
            if mode == "syntax_error":
                attempted_details.append("Syntax check failed for candidate: " + " | ".join(span_labels))
            else:
                syntax_safe_spans.extend(candidate)
                attempted_details.append("Rollback candidate did not resolve baseline failure: " + " | ".join(span_labels))
            score = candidate_score(validation)
            if best_candidate is None or score < best_candidate[0]:
                best_candidate = (score, span_labels, validation)

        deduped_safe: list[tuple[int, int, int, int, str]] = []
        seen_safe: set[str] = set()
        for item in syntax_safe_spans:
            if item[4] in seen_safe:
                continue
            seen_safe.add(item[4])
            deduped_safe.append(item)
        combo_spans = deduped_safe[:max(1, max_single_candidates)]

        candidate_groups: list[list[tuple[int, int, int, int, str]]] = []
        for left in range(len(combo_spans)):
            for right in range(left + 1, len(combo_spans)):
                candidate_groups.append([combo_spans[left], combo_spans[right]])
        if max_pair_candidates >= 0:
            candidate_groups = candidate_groups[:max_pair_candidates]
        triple_groups: list[list[tuple[int, int, int, int, str]]] = []
        if len(combo_spans) >= 3:
            for first in range(len(combo_spans)):
                for second in range(first + 1, len(combo_spans)):
                    for third in range(second + 1, len(combo_spans)):
                        triple_groups.append([combo_spans[first], combo_spans[second], combo_spans[third]])
        if max_triple_candidates >= 0:
            triple_groups = triple_groups[:max_triple_candidates]
        candidate_groups.extend(triple_groups)

        for candidate in candidate_groups:
            validation, mode = evaluate_candidate(candidate)
            span_labels = [raw_span for *_rest, raw_span in candidate]
            if validation is None:
                attempted_details.append("No-op rollback candidate skipped: " + " | ".join(span_labels))
                continue
            last_validation = validation
            if validation.ok:
                return {
                    "attempted": True,
                    "applied": True,
                    "suspicious_file": suspicious_file,
                    "revert_spans": span_labels,
                    "summary": f"Rollback recovery succeeded after reverting {len(candidate)} narrow span(s) in {suspicious_file}.",
                    "baseline_failure": baseline_failure,
                    "validation": validation,
                }
            if mode == "syntax_error":
                attempted_details.append("Syntax check failed for candidate: " + " | ".join(span_labels))
            else:
                attempted_details.append("Rollback candidate did not resolve baseline failure: " + " | ".join(span_labels))
            score = candidate_score(validation)
            if best_candidate is None or score < best_candidate[0]:
                best_candidate = (score, span_labels, validation)

        if last_validation is None:
            return {
                "attempted": False,
                "reason": "Rollback hint matched no effective local changes.",
            }
        best_spans = best_candidate[1] if best_candidate else [item for *_, item in parsed_spans[:4]]
        best_validation = best_candidate[2] if best_candidate else last_validation
        combined_output = "\n".join(attempted_details[:8])
        return {
            "attempted": True,
            "applied": False,
            "suspicious_file": suspicious_file,
            "revert_spans": best_spans,
            "summary": f"Rollback recovery did not fully resolve the issue in {suspicious_file}.",
            "baseline_failure": baseline_failure,
            "validation": ValidationResult(
                ok=False,
                command=best_validation.command,
                exit_code=best_validation.exit_code,
                summary=best_validation.summary,
                output=_compact_output("\n".join(part for part in [combined_output, best_validation.output] if part)),
                changed_files=best_validation.changed_files,
            ),
        }

    def persist_artifacts(
        self,
        *,
        session: SessionState,
        validation: ValidationResult | None = None,
        failure: dict[str, Any] | None = None,
        correction: dict[str, Any] | None = None,
        rollback: dict[str, Any] | None = None,
    ) -> None:
        references: list[ArtifactReference] = []
        role_kind = {
            "investigator": "investigation_artifact",
            "implementer": "implementation_artifact",
            "verifier": "validation_artifact",
        }
        for item in session.delegation_returns:
            artifact_kind = role_kind.get(item.role, "delegation_artifact")
            artifact_name = f"{item.role}.json"
            payload = {
                "task_id": session.task_id,
                "project_scope": session.project_scope,
                "kind": artifact_kind,
                "role": item.role,
                "summary": item.summary,
                "working_set": item.working_set,
                "acceptance_checks": item.acceptance_checks,
                "evidence": item.evidence,
                "collaboration_patterns": [
                    {
                        "kind": pattern.kind,
                        "summary": pattern.summary,
                        "reuse_hint": pattern.reuse_hint,
                        "confidence": pattern.confidence,
                    }
                    for pattern in session.collaboration_patterns
                    if pattern.role == item.role
                ],
            }
            path = save_artifact_payload(
                repo_root=session.repo_root,
                project_scope=session.project_scope,
                task_id=session.task_id,
                artifact_name=artifact_name,
                payload=payload,
            )
            references.append(
                ArtifactReference(
                    artifact_id=f"{session.task_id}:{item.role}",
                    kind=artifact_kind,
                    role=item.role,
                    summary=item.summary,
                    path=path,
                    metadata={
                        "working_set": item.working_set[:6],
                        "acceptance_checks": item.acceptance_checks[:4],
                    },
                )
            )
        if validation and validation.command:
            payload = {
                "task_id": session.task_id,
                "project_scope": session.project_scope,
                "kind": "validation_result",
                "role": "verifier",
                "summary": validation.summary,
                "command": validation.command,
                "ok": validation.ok,
                "exit_code": validation.exit_code,
                "changed_files": validation.changed_files,
                "output": validation.output,
            }
            path = save_artifact_payload(
                repo_root=session.repo_root,
                project_scope=session.project_scope,
                task_id=session.task_id,
                artifact_name="validation.json",
                payload=payload,
            )
            references.append(
                ArtifactReference(
                    artifact_id=f"{session.task_id}:validation",
                    kind="validation_result",
                    role="verifier",
                    summary=validation.summary,
                    path=path,
                    metadata={
                        "command": validation.command,
                        "ok": validation.ok,
                        "changed_files": validation.changed_files[:6],
                    },
                )
            )
        if failure:
            failure_kind = failure.get("kind") or "exception_artifact"
            failure_role = failure.get("role") or "orchestrator"
            failure_name = "timeout.json" if failure_kind == "timeout_artifact" else "failure.json"
            payload = {
                "task_id": session.task_id,
                "project_scope": session.project_scope,
                "kind": failure_kind,
                "role": failure_role,
                "summary": failure.get("summary") or "Workbench execution failed.",
                "message": failure.get("message") or "",
                "trace_summary": failure.get("trace_summary") or {},
                "working_set": failure.get("working_set") or session.target_files,
                "changed_files": failure.get("changed_files") or [],
                "evidence": failure.get("evidence") or [],
            }
            path = save_artifact_payload(
                repo_root=session.repo_root,
                project_scope=session.project_scope,
                task_id=session.task_id,
                artifact_name=failure_name,
                payload=payload,
            )
            references.append(
                ArtifactReference(
                    artifact_id=f"{session.task_id}:{failure_kind}",
                    kind=failure_kind,
                    role=failure_role,
                    summary=payload["summary"],
                    path=path,
                    metadata={
                        "message": payload["message"],
                        "changed_files": payload["changed_files"][:6],
                    },
                )
            )
        if correction:
            payload = {
                "task_id": session.task_id,
                "project_scope": session.project_scope,
                "kind": correction.get("kind") or "correction_packet_artifact",
                "role": correction.get("role") or "orchestrator",
                "summary": correction.get("summary") or "Deterministic correction packet prepared from the latest validation failure.",
                "message": correction.get("message") or "",
                "trace_summary": correction.get("trace_summary") or session.last_trace_summary,
                "working_set": correction.get("working_set") or session.target_files[:6],
                "changed_files": correction.get("changed_files") or [],
                "evidence": correction.get("evidence") or [],
                "command": correction.get("command") or "",
                "failure_name": correction.get("failure_name") or "",
            }
            path = save_artifact_payload(
                repo_root=session.repo_root,
                project_scope=session.project_scope,
                task_id=session.task_id,
                artifact_name="correction.json",
                payload=payload,
            )
            references.append(
                ArtifactReference(
                    artifact_id=f"{session.task_id}:correction",
                    kind="correction_packet_artifact",
                    role=payload["role"],
                    summary=payload["summary"],
                    path=path,
                    metadata={
                        "command": payload["command"],
                        "failure_name": payload["failure_name"],
                        "changed_files": payload["changed_files"][:6],
                    },
                )
            )
        if rollback:
            payload = {
                "task_id": session.task_id,
                "project_scope": session.project_scope,
                "kind": rollback.get("kind") or "rollback_hint_artifact",
                "role": rollback.get("role") or "orchestrator",
                "summary": rollback.get("summary") or "Rollback hint prepared from the latest guarded validation failure.",
                "message": rollback.get("message") or "",
                "trace_summary": rollback.get("trace_summary") or session.last_trace_summary,
                "working_set": rollback.get("working_set") or session.target_files[:6],
                "changed_files": rollback.get("changed_files") or [],
                "evidence": rollback.get("evidence") or [],
                "command": rollback.get("command") or "",
                "suspicious_file": rollback.get("suspicious_file") or "",
                "revert_spans": rollback.get("revert_spans") or [],
            }
            path = save_artifact_payload(
                repo_root=session.repo_root,
                project_scope=session.project_scope,
                task_id=session.task_id,
                artifact_name="rollback.json",
                payload=payload,
            )
            references.append(
                ArtifactReference(
                    artifact_id=f"{session.task_id}:rollback",
                    kind="rollback_hint_artifact",
                    role=payload["role"],
                    summary=payload["summary"],
                    path=path,
                    metadata={
                        "command": payload["command"],
                        "suspicious_file": payload["suspicious_file"],
                        "changed_files": payload["changed_files"][:6],
                    },
                )
            )

        deduped: dict[tuple[str, str], ArtifactReference] = {}
        for item in [*session.artifacts, *references]:
            deduped[(item.role, item.kind)] = item
        session.artifacts = list(deduped.values())[:8]
        self.apply_timeout_strategy(session)

    def apply_timeout_strategy(self, session: SessionState) -> None:
        if not any(item.kind == "timeout_artifact" for item in session.artifacts):
            return
        prioritized: list[ArtifactReference] = []
        seen: set[tuple[str, str, str]] = set()
        for artifact in session.artifacts:
            if artifact.kind == "timeout_artifact":
                key = (artifact.role, artifact.kind, artifact.path)
                if key not in seen:
                    seen.add(key)
                    prioritized.append(artifact)
        for artifact in session.artifacts:
            if artifact.kind == "correction_packet_artifact":
                key = (artifact.role, artifact.kind, artifact.path)
                if key not in seen:
                    seen.add(key)
                    prioritized.append(artifact)
        for artifact in session.artifacts:
            if artifact.kind == "rollback_hint_artifact":
                key = (artifact.role, artifact.kind, artifact.path)
                if key not in seen:
                    seen.add(key)
                    prioritized.append(artifact)
        for artifact in session.artifacts:
            if artifact.kind in {"investigation_artifact", "implementation_artifact", "validation_result"}:
                key = (artifact.role, artifact.kind, artifact.path)
                if key not in seen:
                    seen.add(key)
                    prioritized.append(artifact)
            if len(prioritized) >= 5:
                break
        session.artifacts = prioritized[:5]
        session.validation_commands = session.validation_commands[:1]

    def apply_validation_feedback(self, session: SessionState, validation: ValidationResult) -> None:
        session.last_validation_result = dict(validation.__dict__)
        if validation.ok:
            if validation.command:
                success_line = f"Validation passed: {validation.command}"
                if success_line not in session.promoted_insights:
                    session.promoted_insights.append(success_line)
            session.status = "validated"
            session.working_memory = [entry for entry in [validation.summary, *session.working_memory] if entry][:8]
            return

        failure_lines = []
        if validation.command:
            failure_lines.append(f"Validation failed command: {validation.command}")
        if validation.summary:
            failure_lines.append(validation.summary)
        if validation.output:
            signal = _first_signal_line(validation.output)
            if signal:
                failure_lines.append("Validation signal: " + signal)
        if validation.changed_files:
            failure_lines.append("Current changed files: " + ", ".join(validation.changed_files[:8]))
        session.working_memory = [*failure_lines[:3], *session.working_memory][:8]
        session.status = "needs_attention"

    def validation_decision(self, validation: ValidationResult) -> RecoveryDecision:
        if validation.ok:
            return RecoveryDecision(
                should_pause=False,
                next_action="Continue the current flow.",
                summary=validation.summary or "Validation passed.",
                evidence=[],
            )
        return RecoveryDecision(
            should_pause=True,
            next_action="Correct the validation failure using the failing command, changed files, and latest output as the primary signals.",
            summary=validation.summary or "Validation failed.",
            evidence=[
                {
                    "kind": "validation_failure",
                    "command": validation.command,
                    "exit_code": validation.exit_code,
                    "summary": validation.summary,
                    "output": validation.output,
                }
            ],
        )
