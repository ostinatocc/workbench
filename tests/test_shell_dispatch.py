from __future__ import annotations

from aionis_workbench.provider_profiles import SAFE_CREDENTIALS_HINT
from aionis_workbench.shell_dispatch import dispatch_shell_input, parse_shell_input


class DispatchWorkbench:
    def doc_compile(self, *, input_path: str, emit: str = "all", strict: bool = False):
        return {
            "shell_view": "doc_compile",
            "doc_action": "compile",
            "doc_input": input_path,
            "status": "ok",
            "compile_result": {
                "selected_artifact": emit,
                "summary": {"error_count": 0, "warning_count": 0},
                "diagnostics": [],
            },
        }

    def doc_run(self, *, input_path: str, registry_path: str, input_kind: str = "source"):
        return {
            "shell_view": "doc_run",
            "doc_action": "run",
            "doc_input": input_path,
            "doc_registry": registry_path,
            "status": "succeeded",
            "run_result": {"status": "succeeded", "outputs": {"out.hero": "Hero copy"}},
        }

    def doc_publish(self, *, input_path: str, input_kind: str = "source"):
        return {
            "shell_view": "doc_publish",
            "doc_action": "publish",
            "doc_input": input_path,
            "status": "published",
            "publish_result": {"status": "published", "handoff_id": "handoff-1"},
        }

    def doc_recover(self, *, input_path: str, input_kind: str = "source"):
        return {
            "shell_view": "doc_recover",
            "doc_action": "recover",
            "doc_input": input_path,
            "status": "recovered",
            "recover_result": {"status": "recovered", "handoff": {"id": "handoff-1"}},
        }

    def doc_resume(
        self,
        *,
        input_path: str,
        input_kind: str = "recover-result",
        query_text: str | None = None,
        candidates: list[str] | None = None,
    ):
        return {
            "shell_view": "doc_resume",
            "doc_action": "resume",
            "doc_input": input_path,
            "status": "completed",
            "resume_result": {"status": "completed", "selected_tool": (candidates or ["read"])[0]},
        }

    def doc_list(self, *, limit: int = 24):
        return {
            "shell_view": "doc_list",
            "doc_count": min(limit, 2),
            "docs": [
                {
                    "path": "flows/workflow.aionis.md",
                    "has_evidence": True,
                    "latest_action": "resume",
                },
                {
                    "path": "flows/landing.aionis.md",
                    "has_evidence": False,
                    "latest_action": None,
                },
            ][:limit],
        }

    def setup(self, *, pending_only: bool = False, summary: bool = False, check: str | None = None, one_line: bool = False):
        if check:
            return {
                "shell_view": "setup_check",
                "check_name": check,
                "found": check == "bootstrap_initialized",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "item": (
                    {
                        "name": "bootstrap_initialized",
                        "status": "pending",
                        "reason": "bootstrap missing",
                        "command_hint": "aionis init --repo-root /tmp/repo",
                    }
                    if check == "bootstrap_initialized"
                    else {}
                ),
                "available_checks": [
                    "bootstrap_initialized",
                    "credentials_configured",
                    "runtime_available",
                ],
                "host_contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                },
            }
        if one_line:
            return {
                "shell_view": "setup_one_line",
                "summary_line": "setup-summary: inspect-only: missing credentials + runtime | pending=3 | recovery=configure model credentials and restore runtime availability before retrying live execution | next=aionis init --repo-root /tmp/repo",
                "mode": "inspect-only",
                "live_ready": False,
            }
        if summary:
            return {
                "shell_view": "setup_summary",
                "mode": "inspect-only",
                "live_ready": False,
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "pending_count": 3,
                "completed_count": 0,
                "next_step": "aionis init --repo-root /tmp/repo",
                "host_contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                },
            }
        return {
            "shell_view": "setup",
            "repo_root": "/tmp/repo",
            "mode": "inspect-only",
            "live_ready": False,
            "capability_state": "inspect_only_missing_credentials_and_runtime",
            "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
            "pending_only": pending_only,
            "pending_count": 3,
            "pending_items": [
                {
                    "name": "bootstrap_initialized",
                    "status": "pending",
                    "command_hint": "aionis init --repo-root /tmp/repo",
                },
                {
                    "name": "credentials_configured",
                    "status": "pending",
                    "command_hint": SAFE_CREDENTIALS_HINT,
                },
            ],
            "next_steps": [
                "aionis init --repo-root /tmp/repo",
                SAFE_CREDENTIALS_HINT,
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }

    def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
        if check:
            return {
                "shell_view": "doctor_check",
                "check_name": check,
                "found": check == "runtime_host",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "source": "checks",
                "item": (
                    {
                        "name": "runtime_host",
                        "status": "degraded",
                        "reason": "runtime_health_unreachable",
                    }
                    if check == "runtime_host"
                    else {}
                ),
                "available_checks": [
                    "bootstrap_initialized",
                    "credentials_configured",
                    "runtime_available",
                    "repo_root",
                    "git",
                    "bootstrap",
                    "execution_host",
                    "runtime_host",
                ],
                "host_contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                },
            }
        if one_line:
            return {
                "shell_view": "doctor_one_line",
                "summary_line": "doctor-summary: inspect-only: missing credentials + runtime | pending=3 | recovery=configure model credentials and restore runtime availability before retrying live execution | next=run `aionis init --repo-root /tmp/repo` to create bootstrap state",
                "mode": "inspect-only",
                "live_ready": False,
            }
        if summary:
            return {
                "shell_view": "doctor_summary",
                "mode": "inspect-only",
                "live_ready": False,
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "pending_checklist_count": 3,
                "recommendation": "run `aionis init --repo-root /tmp/repo` to create bootstrap state",
                "host_contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                },
            }
        return {
            "shell_view": "doctor",
            "repo_root": "/tmp/repo",
            "mode": "inspect-only",
            "live_ready": False,
            "checks": [
                {"name": "repo_root", "status": "available"},
                {"name": "bootstrap", "status": "missing"},
                {"name": "execution_host", "status": "offline"},
                {"name": "runtime_host", "status": "degraded"},
            ],
            "recommendations": [
                "run `aionis init --repo-root /tmp/repo` to create bootstrap state",
                "configure model credentials to enable live execution",
            ],
            "host_contract": {
                "product_shell": {"name": "aionis_cli"},
                "learning_engine": {"name": "workbench_engine"},
                "execution_host": {
                    "name": "deepagents_local_shell",
                    "mode": "inspect_only",
                    "health_status": "offline",
                    "health_reason": "model_credentials_missing",
                },
                "runtime_host": {
                    "name": "aionis_runtime_host",
                    "health_status": "degraded",
                    "health_reason": "runtime_health_unreachable",
                },
            },
        }

    def initialize_project(self):
        return {
            "initialized": True,
            "bootstrap_path": "/tmp/repo/.aionis-workbench/bootstrap.json",
            "bootstrap_snapshot": {
                "bootstrap_working_set": ["src", "tests", "pyproject.toml"],
                "bootstrap_validation_commands": ["PYTHONPATH=src python3 -m pytest -q"],
                "recent_commit_subjects": ["Add initial parser tests"],
                "notes": ["Detected source roots: src", "Detected test roots: tests"],
            },
            "canonical_views": {
                "task_state": {"status": "bootstrap_ready"},
                "strategy": {
                    "task_family": "task:cold-start",
                    "strategy_profile": "bootstrap_first_loop",
                },
                "planner": {"next_action": "Create one narrow first task inside the bootstrap working set, then run the first suggested validation command."},
                "instrumentation": {"status": "cold_start"},
            },
            "evaluation": {"status": "bootstrap_ready"},
        }

    def bootstrap_overview(self):
        return {
            "bootstrap_snapshot": {
                "bootstrap_working_set": ["src", "tests", "pyproject.toml"],
                "bootstrap_validation_commands": ["PYTHONPATH=src python3 -m pytest -q"],
                "notes": ["Detected source roots: src", "Detected test roots: tests"],
            },
            "canonical_views": {
                "task_state": {"status": "bootstrap_ready"},
                "strategy": {
                    "task_family": "task:cold-start",
                    "strategy_profile": "bootstrap_first_loop",
                },
                "planner": {"next_action": "Create one narrow first task inside the bootstrap working set, then run the first suggested validation command."},
                "instrumentation": {"status": "cold_start"},
            },
            "evaluation": {"status": "bootstrap_ready"},
        }

    def run(self, *, task_id: str, task: str, target_files: list[str], validation_commands: list[str]):
        return {
            "task_id": task_id,
            "task": task,
            "target_files": target_files,
            "validation_commands": validation_commands,
        }

    def resume(self, *, task_id: str, fallback_task: str | None, target_files: list[str], validation_commands: list[str]):
        return {
            "task_id": task_id,
            "fallback_task": fallback_task,
            "target_files": target_files,
            "validation_commands": validation_commands,
        }

    def ingest(
        self,
        *,
        task_id: str,
        task: str,
        summary: str,
        target_files: list[str],
        changed_files: list[str],
        validation_commands: list[str],
        validation_summary: str | None,
        validation_ok: bool,
    ):
        return {
            "task_id": task_id,
            "task": task,
            "summary": summary,
            "target_files": target_files,
            "changed_files": changed_files,
            "validation_commands": validation_commands,
            "validation_summary": validation_summary,
            "validation_ok": validation_ok,
        }

    def shell_status(self, task_id: str | None = None):
        return {
            "task_id": task_id or "latest-task",
            "text": "project:pallets/click | task:termui | interactive_reuse_loop | strong_match",
            "background": {"status": "completed", "status_line": "completed"},
        }

    def background_status(self):
        return {
            "shell_view": "background",
            "status": "completed",
            "enabled": True,
            "lock_active": False,
            "last_trigger": "backfill",
            "last_reason": None,
            "last_new_session_count": 3,
            "summary": {
                "sessions_reviewed": 12,
                "families_reviewed": 3,
                "patterns_merged": 4,
                "patterns_suppressed": 1,
                "continuity_cleaned": 2,
            },
        }

    def dashboard(self, *, limit: int = 24, family_limit: int = 8):
        return {
            "dashboard_summary": {
                "session_count": 12,
            },
            "family_rows": [
                {
                    "task_family": "task:termui",
                    "status": "strong_family",
                    "trend_status": "stable",
                    "avg_artifact_hit_rate": 1.0,
                }
            ],
            "limit": limit,
            "family_limit": family_limit,
        }

    def consolidate(self, *, limit: int = 48, family_limit: int = 8):
        return {
            "shell_view": "consolidate",
            "sessions_reviewed": limit,
            "families_reviewed": family_limit,
            "patterns_merged": 3,
            "patterns_suppressed": 1,
            "continuity_cleaned": 2,
            "artifacts_reviewed": 7,
            "recovery_samples_reviewed": 1,
            "family_rows": [
                {"task_family": "task:termui", "status": "strong_family"},
            ],
            "consolidation_path": "/tmp/repo/.aionis-workbench/consolidation.json",
        }

    def dream(self, *, limit: int = 48, family_limit: int = 8, status_filter: str | None = None):
        return {
            "shell_view": "dream",
            "dream_status_filter": status_filter or "all",
            "dream_summary": {
                "seed_ready_count": 1,
                "trial_count": 2,
                "candidate_count": 1,
                "deprecated_count": 0,
            },
            "dream_promotion_count": 3,
            "dream_candidate_count": 4,
            "dream_promotions": [
                {
                    "task_family": "task:termui",
                    "promotion_status": "seed_ready",
                    "confidence": 0.92,
                }
            ],
            "dream_candidates": [
                {
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "sample_count": 3,
                }
            ],
        }

    def doc_inspect(self, *, target: str, limit: int = 8):
        return {
            "shell_view": "doc_inspect",
            "inspect_kind": "workflow",
            "resolved_target": target,
            "evidence_count": 1,
            "exists": True,
            "latest_record": {
                "latest_action": "resume",
                "latest_status": "completed",
                "source_doc_id": "workflow-001",
                "handoff_anchor": "doc-anchor-1",
                "selected_tool": "read",
            },
            "recent_records": [],
        }

    def recent_tasks(self, *, limit: int = 8):
        return {
            "task_count": min(limit, 2),
            "tasks": [
                {
                    "index": 1,
                    "task_id": "click-2403-ingest-1",
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "instrumentation_status": "strong_match",
                },
                {
                    "index": 2,
                    "task_id": "click-2869-ingest-1",
                    "task_family": "task:termui",
                    "strategy_profile": "interactive_reuse_loop",
                    "instrumentation_status": "strong_match",
                },
            ][:limit],
        }

    def inspect_session(self, *, task_id: str):
        return {
            "session_path": f"/tmp/{task_id}.json",
            "controller_action_bar": {
                "task_id": task_id,
                "status": "paused",
                "recommended_command": f"/resume {task_id}",
                "allowed_commands": [
                    f"/resume {task_id}",
                    f"/show {task_id}",
                    f"/session {task_id}",
                ],
            },
            "canonical_views": {
                "task_state": {"task_id": task_id, "status": "paused"},
                "strategy": {"task_family": "task:termui", "strategy_profile": "interactive_reuse_loop"},
                "planner": {"next_action": "Verify the patch against the reviewer contract."},
                "controller": {
                    "status": "paused",
                    "allowed_actions": ["list_events", "inspect_context", "resume"],
                    "blocked_actions": ["record_event", "plan_start", "complete"],
                    "last_transition_kind": "paused",
                },
                "app_harness": {
                    "product_spec": {
                        "title": "Pixel Forge",
                        "app_type": "full_stack_app",
                        "feature_count": 3,
                    },
                    "active_sprint_contract": {
                        "sprint_id": "sprint-1",
                        "approved": True,
                    },
                    "latest_sprint_evaluation": {
                        "status": "failed",
                        "summary": "Palette persistence still fails.",
                    },
                    "latest_negotiation_round": {
                        "recommended_action": "revise_current_sprint",
                        "objections": ["Resolve failing criterion: functionality."],
                    },
                    "evaluator_criteria_count": 2,
                    "loop_status": "needs_revision",
                },
                "reviewer": {
                    "standard": "strict_review",
                    "required_outputs": ["patch", "tests"],
                    "acceptance_checks": ["pytest tests/test_termui.py -q"],
                    "rollback_required": False,
                    "ready_required": True,
                    "resume_anchor": "resume:src/termui.py",
                },
                "review_packs": {
                    "continuity": {
                        "pack_version": "continuity_review_pack_v1",
                        "source": "continuity",
                        "standard": "strict_review",
                        "selected_tool": "read",
                        "next_action": "Verify the patch against the reviewer contract.",
                    },
                    "evolution": {
                        "pack_version": "evolution_review_pack_v1",
                        "source": "evolution",
                        "standard": "strict_review",
                        "selected_tool": "edit",
                        "next_action": "Patch the focused file and rerun tests.",
                    },
                },
            },
            "doc_learning": {
                "task_id": task_id,
                "latest_action": "resume",
                "latest_status": "completed",
                "source_doc_id": "workflow-001",
                "handoff_anchor": "doc-anchor-1",
                "selected_tool": "read",
                "history": [
                    {"action": "resume"},
                    {"action": "recover"},
                    {"action": "publish"},
                ],
            },
        }

    def app_show(self, *, task_id: str):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_show"
        payload["task_id"] = task_id
        return payload

    def ab_test_compare(
        self,
        *,
        task_id: str,
        scenario_id: str,
        baseline_ended_in: str = "",
        baseline_duration_seconds: float = 0.0,
        baseline_retry_count: int = 0,
        baseline_replan_depth: int = 0,
        baseline_convergence_signal: str = "",
        baseline_final_execution_gate: str = "",
        baseline_gate_flow: str = "",
        baseline_notes: list[str] | None = None,
        baseline_advance_reached: bool = False,
        baseline_escalated: bool = False,
    ):
        return {
            "shell_view": "ab_test_compare",
            "task_id": task_id,
            "scenario_id": scenario_id,
            "baseline": {
                "ended_in": baseline_ended_in,
                "total_duration_seconds": baseline_duration_seconds,
                "retry_count": baseline_retry_count,
                "replan_depth": baseline_replan_depth,
                "latest_convergence_signal": baseline_convergence_signal,
                "final_execution_gate": baseline_final_execution_gate,
                "gate_flow": baseline_gate_flow,
                "notes": list(baseline_notes or []),
                "advance_reached": baseline_advance_reached,
                "escalated": baseline_escalated,
            },
            "aionis": {
                "ended_in": "advance",
                "total_duration_seconds": 150.0,
                "retry_count": 1,
                "replan_depth": 2,
                "final_execution_gate": "ready",
                "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            },
            "comparison": {
                "winner": "aionis",
                "duration_delta_seconds": 29.5,
                "retry_delta": 0,
                "replan_delta": 2,
                "summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
            },
            "benchmark_summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
        }

    def ab_test_compare(
        self,
        *,
        task_id: str,
        scenario_id: str,
        baseline_ended_in: str = "",
        baseline_duration_seconds: float = 0.0,
        baseline_retry_count: int = 0,
        baseline_replan_depth: int = 0,
        baseline_convergence_signal: str = "",
        baseline_final_execution_gate: str = "",
        baseline_gate_flow: str = "",
        baseline_notes: list[str] | None = None,
        baseline_advance_reached: bool = False,
        baseline_escalated: bool = False,
    ):
        return {
            "shell_view": "ab_test_compare",
            "task_id": task_id,
            "scenario_id": scenario_id,
            "baseline": {
                "ended_in": baseline_ended_in,
                "total_duration_seconds": baseline_duration_seconds,
                "retry_count": baseline_retry_count,
                "replan_depth": baseline_replan_depth,
                "latest_convergence_signal": baseline_convergence_signal,
                "final_execution_gate": baseline_final_execution_gate,
                "gate_flow": baseline_gate_flow,
                "notes": list(baseline_notes or []),
                "advance_reached": baseline_advance_reached,
                "escalated": baseline_escalated,
            },
            "aionis": {
                "ended_in": "advance",
                "total_duration_seconds": 150.0,
                "retry_count": 1,
                "replan_depth": 2,
                "final_execution_gate": "ready",
                "latest_convergence_signal": "live-app-second-replan-generate-qa-advance:needs_qa->ready@qa:passed",
            },
            "comparison": {
                "winner": "aionis",
                "duration_delta_seconds": 29.5,
                "retry_delta": 0,
                "replan_delta": 2,
                "summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
            },
            "benchmark_summary": "Aionis converged to advance; baseline escalated before reaching the next sprint.",
        }

    def app_plan(
        self,
        *,
        task_id: str,
        prompt: str,
        title: str = "",
        app_type: str = "",
        stack: list[str] | None = None,
        features: list[str] | None = None,
        design_direction: str = "",
        criteria: list[str] | None = None,
        use_live_planner: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_plan"
        payload["task_id"] = task_id
        payload["app_prompt"] = prompt
        payload["app_plan_inputs"] = {
            "title": title,
            "app_type": app_type,
            "stack": list(stack or []),
            "features": list(features or []),
            "design_direction": design_direction,
            "criteria": list(criteria or []),
            "use_live_planner": use_live_planner,
        }
        return payload

    def app_ship(
        self,
        *,
        task_id: str,
        prompt: str,
        output_dir: str = "",
        use_live_planner: bool = False,
        use_live_generator: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_ship"
        payload["task_id"] = task_id
        payload["status"] = "completed"
        payload["phase"] = "complete"
        payload["route_summary"] = "task_intake->context_scan->plan->sprint->generate->export"
        payload["context_summary"] = "repo=/tmp/repo | top=README.md, src/"
        payload["active_sprint_id"] = "sprint-1"
        payload["entrypoint"] = f"{output_dir or '/tmp/exported-app'}/dist/index.html"
        payload["preview_command"] = f"cd {output_dir or '/tmp/exported-app'} && npm run dev -- --host 0.0.0.0 --port 4173"
        payload["validation_summary"] = "Validation commands passed."
        payload["app_ship_inputs"] = {
            "prompt": prompt,
            "output_dir": output_dir,
            "use_live_planner": use_live_planner,
            "use_live_generator": use_live_generator,
        }
        return payload

    def ship(
        self,
        *,
        task_id: str,
        task: str,
        target_files: list[str] | None = None,
        validation_commands: list[str] | None = None,
        output_dir: str = "",
        use_live_planner: bool = False,
        use_live_generator: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "ship"
        payload["task_id"] = task_id
        payload["ship_mode"] = "app_delivery" if output_dir else "project_workflow"
        payload["delegated_shell_view"] = "app_ship" if output_dir else "run"
        payload["status"] = "completed"
        payload["phase"] = "complete"
        payload["route_summary"] = (
            "task_intake->context_scan->plan->sprint->generate->qa->export->advance"
            if output_dir
            else "task_intake->context_scan->route->run"
        )
        payload["route_reason"] = "explicit output directory requested" if output_dir else "target files explicitly provided"
        payload["context_summary"] = "repo=/tmp/repo | top=README.md, src/"
        payload["active_sprint_id"] = "sprint-1"
        payload["entrypoint"] = f"{output_dir or '/tmp/exported-app'}/dist/index.html"
        payload["preview_command"] = f"cd {output_dir or '/tmp/exported-app'} && npm run dev -- --host 0.0.0.0 --port 4173"
        payload["validation_summary"] = "Validation commands passed."
        payload["ship_inputs"] = {
            "task": task,
            "target_files": list(target_files or []),
            "validation_commands": list(validation_commands or []),
            "output_dir": output_dir,
            "use_live_planner": use_live_planner,
            "use_live_generator": use_live_generator,
        }
        return payload

    def app_sprint(
        self,
        *,
        task_id: str,
        sprint_id: str,
        goal: str,
        scope: list[str] | None = None,
        acceptance_checks: list[str] | None = None,
        done_definition: list[str] | None = None,
        proposed_by: str = "",
        approved: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_sprint"
        payload["task_id"] = task_id
        payload["app_sprint_inputs"] = {
            "sprint_id": sprint_id,
            "goal": goal,
            "scope": list(scope or []),
            "acceptance_checks": list(acceptance_checks or []),
            "done_definition": list(done_definition or []),
            "proposed_by": proposed_by,
            "approved": approved,
        }
        return payload

    def app_qa(
        self,
        *,
        task_id: str,
        sprint_id: str,
        status: str,
        summary: str = "",
        scores: list[str] | None = None,
        blocker_notes: list[str] | None = None,
        use_live_evaluator: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_qa"
        payload["task_id"] = task_id
        payload["app_qa_inputs"] = {
            "sprint_id": sprint_id,
            "status": status,
            "summary": summary,
            "scores": list(scores or []),
            "blocker_notes": list(blocker_notes or []),
            "use_live_evaluator": use_live_evaluator,
        }
        return payload

    def app_negotiate(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        objections: list[str] | None = None,
        use_live_planner: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_negotiate"
        payload["task_id"] = task_id
        payload["app_negotiate_inputs"] = {
            "sprint_id": sprint_id,
            "objections": list(objections or []),
            "use_live_planner": use_live_planner,
        }
        return payload

    def app_generate(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        execution_summary: str = "",
        changed_target_hints: list[str] | None = None,
        use_live_generator: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_generate"
        payload["task_id"] = task_id
        payload["app_generate_inputs"] = {
            "sprint_id": sprint_id,
            "execution_summary": execution_summary,
            "changed_target_hints": list(changed_target_hints or []),
            "use_live_generator": use_live_generator,
        }
        payload.setdefault("canonical_views", {}).setdefault("app_harness", {}).update(
            {
                "latest_execution_attempt": {
                    "attempt_id": "sprint-1-attempt-1",
                    "execution_mode": "live" if use_live_generator else "deterministic",
                    "execution_target_kind": "revision",
                    "artifact_kind": "static_html_demo",
                    "artifact_path": ".aionis-workbench/artifacts/task-123/sprint-1-attempt-1/index.html",
                },
                "execution_history_count": 1,
                "loop_status": "execution_recorded",
            }
        )
        return payload

    def app_export(
        self,
        *,
        task_id: str,
        output_dir: str = "",
    ):
        return {
            "shell_view": "app_export",
            "task_id": task_id,
            "export_root": output_dir or "/tmp/exported-app",
            "entrypoint": f"{output_dir or '/tmp/exported-app'}/index.html",
            "preview_command": f"cd {output_dir or '/tmp/exported-app'} && npm run dev -- --host 0.0.0.0 --port 4173",
            "validation_summary": "Validation commands passed.",
            "changed_files": ["src/App.tsx"],
            "app_export_inputs": {
                "output_dir": output_dir,
            },
        }

    def app_retry(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        revision_notes: list[str] | None = None,
        use_live_planner: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_retry"
        payload["task_id"] = task_id
        payload["app_retry_inputs"] = {
            "sprint_id": sprint_id,
            "revision_notes": list(revision_notes or []),
            "use_live_planner": use_live_planner,
        }
        payload.setdefault("canonical_views", {}).setdefault("app_harness", {}).update(
            {
                "retry_count": 1,
                "retry_budget": 1,
                "latest_revision": {
                    "revision_id": "sprint-1-revision-1",
                    "planner_mode": "live" if use_live_planner else "deterministic",
                },
                "loop_status": "revision_recorded",
            }
        )
        return payload

    def app_advance(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_advance"
        payload["task_id"] = task_id
        payload["app_advance_inputs"] = {"sprint_id": sprint_id}
        payload.setdefault("canonical_views", {}).setdefault("app_harness", {}).update(
            {
                "active_sprint_contract": {
                    "sprint_id": sprint_id or "sprint-2",
                    "approved": False,
                },
                "planned_sprint_contracts": [],
                "latest_sprint_evaluation": {},
                "latest_revision": {},
                "loop_status": "in_sprint",
                "next_sprint_ready": False,
                "next_sprint_candidate_id": "",
                "recommended_next_action": "",
            }
        )
        return payload

    def app_replan(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        note: str = "",
        use_live_planner: bool = False,
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_replan"
        payload["task_id"] = task_id
        payload["app_replan_inputs"] = {
            "sprint_id": sprint_id,
            "note": note,
            "use_live_planner": use_live_planner,
        }
        payload.setdefault("canonical_views", {}).setdefault("app_harness", {}).update(
            {
                "active_sprint_contract": {
                    "sprint_id": "sprint-1-replan-1",
                    "approved": False,
                },
                "planned_sprint_contracts": [{"sprint_id": "sprint-2"}],
                "latest_sprint_evaluation": {},
                "latest_revision": {},
                "retry_count": 0,
                "loop_status": "sprint_replanned",
                "retry_available": False,
                "retry_remaining": 1,
                "recommended_next_action": "run_current_sprint",
                "sprint_negotiation_notes": [note or "Replanned after escalation."],
            }
        )
        return payload

    def app_escalate(
        self,
        *,
        task_id: str,
        sprint_id: str = "",
        note: str = "",
    ):
        payload = self.inspect_session(task_id=task_id)
        payload["shell_view"] = "app_escalate"
        payload["task_id"] = task_id
        payload["app_escalate_inputs"] = {
            "sprint_id": sprint_id,
            "note": note,
        }
        payload.setdefault("canonical_views", {}).setdefault("app_harness", {}).update(
            {
                "loop_status": "escalated",
                "recommended_next_action": "replan_or_escalate",
                "sprint_negotiation_notes": [note or "Retry budget exhausted; escalate or replan before continuing."],
            }
        )
        return payload

    def evaluate_session(self, *, task_id: str):
        return {"evaluation": {"task_id": task_id, "status": "ready"}}

    def validate_session(self, *, task_id: str):
        return {
            "session_path": f"/tmp/{task_id}.json",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
                "summary": "Validation commands passed.",
            },
            "canonical_views": {"task_state": {"task_id": task_id}},
        }

    def workflow_next(self, *, task_id: str):
        return {
            "shell_view": "next",
            "session_path": f"/tmp/{task_id}.json",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {"task_state": {"task_id": task_id}},
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
        }

    def workflow_fix(self, *, task_id: str):
        return {
            "shell_view": "fix",
            "session_path": f"/tmp/{task_id}.json",
            "validation": {
                "ok": True,
                "command": "pytest tests/test_termui.py -q",
                "exit_code": 0,
            },
            "canonical_views": {"task_state": {"task_id": task_id}},
            "workflow_next": {
                "action": "validate",
                "reason": "Run the first targeted validation command and keep the working set narrow.",
            },
        }

    def compare_family(self, *, task_id: str, limit: int = 6):
        return {
            "task_id": task_id,
            "task_family": "task:termui",
            "peer_count": limit,
            "peer_summary": {
                "strong_match_count": limit,
                "usable_match_count": 0,
                "weak_match_count": 0,
            },
            "peers": [{"task_id": "click-2869-ingest-1"}, {"task_id": "click-3242-ingest-1"}][:limit],
            "background": {"status_line": "completed"},
            "family_prior": {
                "dominant_strategy_profile": "interactive_reuse_loop",
                "dominant_validation_style": "targeted_first",
            },
        }


def test_parse_shell_input_handles_slash_commands() -> None:
    command_name, args = parse_shell_input("/dashboard --limit 5")
    assert command_name == "dashboard"
    assert args == "--limit 5"


def test_dispatch_routes_dashboard() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/dashboard --limit 5 --family-limit 3")
    assert result["kind"] == "result"
    assert result["payload"]["dashboard_summary"]["session_count"] == 12
    assert result["payload"]["limit"] == 5
    assert result["payload"]["family_limit"] == 3


def test_dispatch_routes_status() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/status")
    assert result["kind"] == "status"
    assert "interactive_reuse_loop" in result["text"]


def test_dispatch_routes_background() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/background")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "background"
    assert result["payload"]["status"] == "completed"


def test_dispatch_routes_init() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/init")
    assert result["kind"] == "show"
    assert result["should_refresh_status"] is True
    assert result["payload"]["shell_view"] == "init"
    assert result["payload"]["bootstrap_path"].endswith("bootstrap.json")


def test_dispatch_routes_doctor() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doctor")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doctor"
    assert result["payload"]["mode"] == "inspect-only"


def test_dispatch_routes_doctor_summary() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doctor --summary")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doctor_summary"
    assert result["payload"]["pending_checklist_count"] == 3


def test_dispatch_routes_doctor_one_line() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doctor --one-line")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doctor_one_line"
    assert "doctor-summary:" in result["payload"]["summary_line"]


def test_dispatch_routes_doctor_check() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doctor --check runtime_host")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doctor_check"
    assert result["payload"]["found"] is True


def test_dispatch_routes_setup() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/setup")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "setup"
    assert result["payload"]["pending_count"] == 3


def test_dispatch_routes_setup_pending_only() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/setup --pending-only")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "setup"
    assert result["payload"]["pending_only"] is True


def test_dispatch_routes_setup_summary() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/setup --summary")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "setup_summary"
    assert result["payload"]["pending_count"] == 3


def test_dispatch_routes_setup_one_line() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/setup --one-line")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "setup_one_line"
    assert "setup-summary:" in result["payload"]["summary_line"]


def test_dispatch_routes_setup_check() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/setup --check bootstrap_initialized")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "setup_check"
    assert result["payload"]["found"] is True


def test_dispatch_routes_tasks_and_latest() -> None:
    workbench = DispatchWorkbench()
    tasks_result = dispatch_shell_input(workbench, "/tasks --limit 1")
    latest_result = dispatch_shell_input(workbench, "/latest")
    assert tasks_result["kind"] == "result"
    assert tasks_result["payload"]["task_count"] == 1
    assert tasks_result["payload"]["tasks"][0]["task_id"] == "click-2403-ingest-1"
    assert latest_result["kind"] == "setting"
    assert latest_result["payload"]["setting"] == "current_task"
    assert latest_result["payload"]["value"] == "latest-task"


def test_dispatch_routes_family() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/family", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "family"
    assert result["payload"]["task_family"] == "task:termui"
    assert result["payload"]["family_row"]["status"] == "strong_family"
    assert result["payload"]["background"]["status_line"] == "completed"
    assert "no reusable family prior yet" in result["payload"]["value_summary"]
    assert "seed_blocked" in result["payload"]["reuse_summary"]


def test_dispatch_routes_dream_alias() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/dream --limit 12 --family-limit 4")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "dream"
    assert result["payload"]["dream_summary"]["seed_ready_count"] == 1
    assert result["payload"]["dream_promotion_count"] == 3


def test_dispatch_routes_dream_with_status_filter() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/dream --status trial")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "dream"
    assert result["payload"]["dream_status_filter"] == "trial"


def test_dispatch_routes_doc_compile() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doc compile workflow.aionis.md --emit plan --strict")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doc_compile"
    assert result["payload"]["doc_input"] == "workflow.aionis.md"
    assert result["payload"]["compile_result"]["selected_artifact"] == "plan"


def test_dispatch_routes_doc_run_and_resume() -> None:
    workbench = DispatchWorkbench()
    run_result = dispatch_shell_input(workbench, "/doc run workflow.aionis.md --registry module-registry.json --input-kind compile-envelope")
    resume_result = dispatch_shell_input(
        workbench,
        "/doc resume recover-result.json --input-kind recover-result --query-text 'resume workflow' --candidate read --candidate bash",
    )
    assert run_result["kind"] == "show"
    assert run_result["payload"]["shell_view"] == "doc_run"
    assert run_result["payload"]["doc_registry"] == "module-registry.json"
    assert resume_result["kind"] == "show"
    assert resume_result["payload"]["shell_view"] == "doc_resume"
    assert resume_result["payload"]["resume_result"]["selected_tool"] == "read"


def test_dispatch_routes_doc_show() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doc show", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doc_show"
    assert result["payload"]["task_id"] == "click-2403-ingest-1"
    assert result["payload"]["doc_learning"]["latest_action"] == "resume"


def test_dispatch_routes_app_show() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/app show", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_show"
    assert result["payload"]["task_id"] == "click-2403-ingest-1"
    assert result["payload"]["canonical_views"]["app_harness"]["product_spec"]["title"] == "Pixel Forge"


def test_dispatch_routes_ab_test_compare() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/ab-test compare click-2403-ingest-1 --scenario-id scenario-1 --baseline-ended-in escalate --baseline-duration-seconds 120.5 --baseline-retry-count 1 --baseline-escalated",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "ab_test_compare"
    assert result["payload"]["task_id"] == "click-2403-ingest-1"
    assert result["payload"]["scenario_id"] == "scenario-1"
    assert result["payload"]["baseline"]["ended_in"] == "escalate"


def test_dispatch_routes_app_plan() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app plan --prompt 'Build a pixel editor' --title 'Pixel Forge' --type full_stack_app --stack React --feature canvas --criterion functionality:0.8",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_plan"
    assert result["payload"]["app_prompt"] == "Build a pixel editor"
    assert result["payload"]["app_plan_inputs"]["criteria"] == ["functionality:0.8"]


def test_dispatch_routes_app_ship() -> None:
    result = dispatch_shell_input(
        DispatchWorkbench(),
        "/app ship task-123 --prompt \"Build a modern landing page for an AI agent platform.\" --output-dir /tmp/exported-app --live-plan --live",
        current_task_id=None,
    )

    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_ship"
    assert result["payload"]["app_ship_inputs"]["prompt"] == "Build a modern landing page for an AI agent platform."
    assert result["payload"]["app_ship_inputs"]["output_dir"] == "/tmp/exported-app"
    assert result["payload"]["app_ship_inputs"]["use_live_planner"] is True
    assert result["payload"]["app_ship_inputs"]["use_live_generator"] is True


def test_dispatch_routes_ship_to_unified_entry() -> None:
    result = dispatch_shell_input(
        DispatchWorkbench(),
        "/ship task-123 \"Build a modern landing page for an AI agent platform.\" --output-dir /tmp/exported-app --live-plan --live",
        current_task_id=None,
    )

    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "ship"
    assert result["payload"]["ship_mode"] == "app_delivery"
    assert result["payload"]["delegated_shell_view"] == "app_ship"
    assert result["payload"]["ship_inputs"]["task"] == "Build a modern landing page for an AI agent platform."
    assert result["payload"]["ship_inputs"]["output_dir"] == "/tmp/exported-app"
    assert result["payload"]["ship_inputs"]["use_live_planner"] is True
    assert result["payload"]["ship_inputs"]["use_live_generator"] is True


def test_dispatch_shows_help_when_ship_args_missing() -> None:
    result = dispatch_shell_input(
        DispatchWorkbench(),
        "/ship task-123",
        current_task_id=None,
    )

    assert result["kind"] == "help"
    assert "Usage: /ship TASK_ID \"task\"" in result["text"]


def test_dispatch_help_includes_controller_context_when_available() -> None:
    class ControllerHelpWorkbench(DispatchWorkbench):
        def inspect_session(self, *, task_id: str):
            return {
                "canonical_views": {
                    "controller": {
                        "status": "paused",
                        "allowed_actions": ["list_events", "inspect_context", "resume"],
                        "blocked_actions": ["record_event", "plan_start", "complete"],
                    }
                }
            }

    result = dispatch_shell_input(
        ControllerHelpWorkbench(),
        "/help",
        current_task_id="click-2403-ingest-1",
    )

    assert result["kind"] == "help"
    assert "Available commands:" in result["text"]
    assert "Current task controller: click-2403-ingest-1 status=paused" in result["text"]
    assert (
        "controller_actions: recommended=/resume click-2403-ingest-1 "
        "allowed=/resume click-2403-ingest-1 | /show click-2403-ingest-1 | /session click-2403-ingest-1"
    ) in result["text"]


def test_dispatch_shows_help_when_app_ship_prompt_missing() -> None:
    result = dispatch_shell_input(
        DispatchWorkbench(),
        "/app ship task-123",
        current_task_id=None,
    )

    assert result["kind"] == "help"
    assert "Usage: /app ship [TASK_ID] --prompt TEXT" in result["text"]


def test_dispatch_routes_app_plan_live_flag() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app plan --prompt 'Build a pixel editor' --live",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_plan"
    assert result["payload"]["app_plan_inputs"]["use_live_planner"] is True


def test_dispatch_routes_app_sprint_and_qa() -> None:
    workbench = DispatchWorkbench()
    sprint_result = dispatch_shell_input(
        workbench,
        "/app sprint --sprint-id sprint-1 --goal 'Ship the editor shell' --scope shell --acceptance-check 'pytest tests/test_editor.py -q' --approved",
        current_task_id="click-2403-ingest-1",
    )
    qa_result = dispatch_shell_input(
        workbench,
        "/app qa --sprint-id sprint-1 --status failed --summary 'Palette persistence still fails.' --score functionality=0.61 --blocker 'palette resets on refresh'",
        current_task_id="click-2403-ingest-1",
    )
    assert sprint_result["kind"] == "show"
    assert sprint_result["payload"]["shell_view"] == "app_sprint"
    assert sprint_result["payload"]["app_sprint_inputs"]["approved"] is True
    assert qa_result["kind"] == "show"
    assert qa_result["payload"]["shell_view"] == "app_qa"
    assert qa_result["payload"]["app_qa_inputs"]["scores"] == ["functionality=0.61"]


def test_dispatch_routes_app_negotiate() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app negotiate --sprint-id sprint-1 --objection 'timeline entries reset on refresh'",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_negotiate"
    assert result["payload"]["app_negotiate_inputs"]["sprint_id"] == "sprint-1"
    assert result["payload"]["app_negotiate_inputs"]["objections"] == ["timeline entries reset on refresh"]
    assert result["payload"]["app_negotiate_inputs"]["use_live_planner"] is False


def test_dispatch_routes_app_negotiate_live_flag() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app negotiate --sprint-id sprint-1 --live",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_negotiate"
    assert result["payload"]["app_negotiate_inputs"]["use_live_planner"] is True


def test_dispatch_routes_app_generate() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app generate --sprint-id sprint-1 --summary 'Apply the narrowed persistence fix before re-running QA.' --target src/editor.tsx",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_generate"
    assert result["payload"]["app_generate_inputs"]["sprint_id"] == "sprint-1"
    assert result["payload"]["app_generate_inputs"]["execution_summary"] == "Apply the narrowed persistence fix before re-running QA."
    assert result["payload"]["app_generate_inputs"]["changed_target_hints"] == ["src/editor.tsx"]
    assert result["payload"]["app_generate_inputs"]["use_live_generator"] is False
    assert result["payload"]["canonical_views"]["app_harness"]["latest_execution_attempt"]["attempt_id"] == "sprint-1-attempt-1"


def test_dispatch_routes_app_generate_live() -> None:
    workbench = DispatchWorkbench()

    result = dispatch_shell_input(
        workbench,
        "/app generate --sprint-id sprint-1 --target src/editor.tsx --live",
        current_task_id="click-2403-ingest-1",
    )

    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_generate"
    assert result["payload"]["app_generate_inputs"]["use_live_generator"] is True
    assert result["payload"]["canonical_views"]["app_harness"]["latest_execution_attempt"]["execution_mode"] == "live"


def test_dispatch_routes_app_export() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app export --output-dir /tmp/dependency-explorer-export",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_export"
    assert result["payload"]["export_root"] == "/tmp/dependency-explorer-export"
    assert result["payload"]["app_export_inputs"]["output_dir"] == "/tmp/dependency-explorer-export"


def test_dispatch_routes_app_retry() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app retry --sprint-id sprint-1 --revision-note 'fix timeline persistence'",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_retry"
    assert result["payload"]["app_retry_inputs"]["sprint_id"] == "sprint-1"
    assert result["payload"]["app_retry_inputs"]["revision_notes"] == ["fix timeline persistence"]
    assert result["payload"]["app_retry_inputs"]["use_live_planner"] is False
    assert result["payload"]["canonical_views"]["app_harness"]["latest_revision"]["revision_id"] == "sprint-1-revision-1"


def test_dispatch_routes_app_retry_live_flag() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app retry --sprint-id sprint-1 --live",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_retry"
    assert result["payload"]["app_retry_inputs"]["use_live_planner"] is True
    assert result["payload"]["canonical_views"]["app_harness"]["latest_revision"]["planner_mode"] == "live"


def test_dispatch_routes_app_advance() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app advance --sprint-id sprint-2",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_advance"
    assert result["payload"]["app_advance_inputs"]["sprint_id"] == "sprint-2"
    assert result["payload"]["canonical_views"]["app_harness"]["active_sprint_contract"]["sprint_id"] == "sprint-2"


def test_dispatch_routes_app_replan() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app replan --sprint-id sprint-1 --note 'narrow the sprint around persistence'",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_replan"
    assert result["payload"]["app_replan_inputs"]["sprint_id"] == "sprint-1"
    assert result["payload"]["app_replan_inputs"]["note"] == "narrow the sprint around persistence"
    assert result["payload"]["app_replan_inputs"]["use_live_planner"] is False
    assert result["payload"]["canonical_views"]["app_harness"]["active_sprint_contract"]["sprint_id"] == "sprint-1-replan-1"
    assert result["payload"]["canonical_views"]["app_harness"]["loop_status"] == "sprint_replanned"


def test_dispatch_routes_app_replan_live() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app replan --sprint-id sprint-1 --note 'narrow the sprint around persistence' --live",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_replan"
    assert result["payload"]["app_replan_inputs"]["use_live_planner"] is True


def test_dispatch_routes_app_escalate() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        "/app escalate --sprint-id sprint-1 --note 'retry budget exhausted'",
        current_task_id="click-2403-ingest-1",
    )
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "app_escalate"
    assert result["payload"]["app_escalate_inputs"]["sprint_id"] == "sprint-1"
    assert result["payload"]["app_escalate_inputs"]["note"] == "retry budget exhausted"
    assert result["payload"]["canonical_views"]["app_harness"]["loop_status"] == "escalated"


def test_dispatch_routes_app_qa_defaults_to_auto_status() -> None:
    workbench = DispatchWorkbench()
    qa_result = dispatch_shell_input(
        workbench,
        "/app qa --sprint-id sprint-1 --blocker 'palette resets on refresh'",
        current_task_id="click-2403-ingest-1",
    )
    assert qa_result["kind"] == "show"
    assert qa_result["payload"]["shell_view"] == "app_qa"
    assert qa_result["payload"]["app_qa_inputs"]["status"] == "auto"


def test_dispatch_routes_app_qa_live_flag() -> None:
    workbench = DispatchWorkbench()
    qa_result = dispatch_shell_input(
        workbench,
        "/app qa --sprint-id sprint-1 --live",
        current_task_id="click-2403-ingest-1",
    )
    assert qa_result["kind"] == "show"
    assert qa_result["payload"]["shell_view"] == "app_qa"
    assert qa_result["payload"]["app_qa_inputs"]["use_live_evaluator"] is True


def test_dispatch_routes_doc_list() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doc list --limit 1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doc_list"
    assert result["payload"]["doc_count"] == 1
    assert result["payload"]["docs"][0]["path"] == "flows/workflow.aionis.md"


def test_dispatch_routes_doc_inspect() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/doc inspect flows/workflow.aionis.md")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "doc_inspect"
    assert result["payload"]["inspect_kind"] == "workflow"
    assert result["payload"]["latest_record"]["latest_action"] == "resume"


def test_dispatch_routes_work() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/work", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "work"
    assert result["payload"]["task_family"] == "task:termui"
    assert result["payload"]["family_row"]["status"] == "strong_family"
    assert "no reusable family prior yet" in result["payload"]["value_summary"]
    assert "seed_blocked" in result["payload"]["reuse_summary"]
    assert result["payload"]["workflow_path"] == "/work -> /next -> /fix -> /validate"
    assert result["payload"]["recommended_command"] == "/review click-2403-ingest-1"
    assert result["payload"]["controller_action_bar"]["recommended_command"] == "/resume click-2403-ingest-1"
    assert result["payload"]["reviewer"]["standard"] == "strict_review"
    assert result["payload"]["review_packs"]["continuity"]["pack_version"] == "continuity_review_pack_v1"


def test_dispatch_routes_work_bootstrap_without_current_task() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/work")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "work"
    assert result["payload"]["bootstrap_snapshot"]["bootstrap_working_set"][0] == "src"


def test_dispatch_routes_review() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/review", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "review"
    assert result["payload"]["task_family"] == "task:termui"
    assert result["payload"]["evaluation"]["status"] == "ready"
    assert result["payload"]["family_row"]["status"] == "strong_family"
    assert "no reusable family prior yet" in result["payload"]["value_summary"]
    assert "seed_blocked" in result["payload"]["reuse_summary"]
    assert result["payload"]["workflow_path"] == "/review -> /fix -> /validate"
    assert result["payload"]["recommended_command"] == "/next click-2403-ingest-1"
    assert result["payload"]["controller_action_bar"]["allowed_commands"][0] == "/resume click-2403-ingest-1"
    assert result["payload"]["reviewer"]["resume_anchor"] == "resume:src/termui.py"
    assert result["payload"]["review_packs"]["evolution"]["selected_tool"] == "edit"


def test_dispatch_routes_next() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/next", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["should_refresh_status"] is True
    assert result["payload"]["shell_view"] == "next"
    assert result["payload"]["workflow_next"]["action"] == "validate"
    assert result["payload"]["canonical_views"]["task_state"]["task_id"] == "click-2403-ingest-1"


def test_dispatch_routes_fix() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/fix", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["should_refresh_status"] is True
    assert result["payload"]["shell_view"] == "fix"
    assert result["payload"]["workflow_next"]["action"] == "validate"
    assert result["payload"]["canonical_views"]["task_state"]["task_id"] == "click-2403-ingest-1"


def test_dispatch_blocks_next_when_controller_requires_resume() -> None:
    class GuardedWorkbench(DispatchWorkbench):
        def inspect_session(self, *, task_id: str):
            payload = super().inspect_session(task_id=task_id)
            payload.setdefault("canonical_views", {})["controller"] = {
                "status": "paused",
                "allowed_actions": ["list_events", "inspect_context", "resume"],
                "guard_reasons": [
                    {
                        "action": "plan_start",
                        "reason": "task session is paused; resume before planning the next start",
                    }
                ],
            }
            return payload

        def workflow_next(self, *, task_id: str):
            raise AssertionError("workflow_next should not be invoked when controller preflight blocks")

    result = dispatch_shell_input(GuardedWorkbench(), "/next", current_task_id="click-2403-ingest-1")

    assert result["kind"] == "show"
    assert result["should_refresh_status"] is False
    assert result["payload"]["shell_view"] == "controller_preflight"
    assert result["payload"]["command"] == "next"
    assert result["payload"]["required_action"] == "plan_start"
    assert result["payload"]["recommended_command"] == "/resume click-2403-ingest-1"


def test_dispatch_blocks_fix_when_controller_requires_resume() -> None:
    class GuardedWorkbench(DispatchWorkbench):
        def inspect_session(self, *, task_id: str):
            payload = super().inspect_session(task_id=task_id)
            payload.setdefault("canonical_views", {})["controller"] = {
                "status": "paused",
                "allowed_actions": ["list_events", "inspect_context", "resume"],
                "guard_reasons": [
                    {
                        "action": "plan_start",
                        "reason": "task session is paused; resume before planning the next start",
                    }
                ],
            }
            return payload

        def workflow_fix(self, *, task_id: str):
            raise AssertionError("workflow_fix should not be invoked when controller preflight blocks")

    result = dispatch_shell_input(GuardedWorkbench(), "/fix", current_task_id="click-2403-ingest-1")

    assert result["kind"] == "show"
    assert result["should_refresh_status"] is False
    assert result["payload"]["shell_view"] == "controller_preflight"
    assert result["payload"]["command"] == "fix"
    assert result["payload"]["required_action"] == "plan_start"
    assert result["payload"]["recommended_command"] == "/resume click-2403-ingest-1"


def test_dispatch_routes_plan() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/plan", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "plan"
    assert result["payload"]["task_family"] == "task:termui"
    assert result["payload"]["evaluation"]["status"] == "ready"
    assert result["payload"]["workflow_next"]["action"] == "validate"
    assert "no strong family prior yet" in result["payload"]["value_summary"]
    assert "seed_blocked" in result["payload"]["reuse_summary"]
    assert result["payload"]["workflow_path"] == "/plan -> /review -> /fix -> /validate"
    assert result["payload"]["recommended_command"] == "/review click-2403-ingest-1"
    assert result["payload"]["controller_action_bar"]["status"] == "paused"
    assert result["payload"]["reviewer"]["ready_required"] is True
    assert result["payload"]["review_packs"]["continuity"]["standard"] == "strict_review"


def test_dispatch_routes_plan_bootstrap_without_current_task() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/plan")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "plan"
    assert result["payload"]["canonical_views"]["strategy"]["task_family"] == "task:cold-start"


def test_dispatch_routes_validate() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/validate", current_task_id="click-2403-ingest-1")
    assert result["kind"] == "result"
    assert result["should_refresh_status"] is True
    assert result["payload"]["validation"]["ok"] is True
    assert result["payload"]["canonical_views"]["task_state"]["task_id"] == "click-2403-ingest-1"


def test_dispatch_routes_pick() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/pick 2")
    assert result["kind"] == "setting"
    assert result["payload"]["setting"] == "current_task"
    assert result["payload"]["value"] == "click-2869-ingest-1"


def test_dispatch_plain_text_falls_back_to_help() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "fix the current task")
    assert result["kind"] == "help"
    assert "Use /run, /resume, /ingest, or /help." == result["text"]


def test_dispatch_exit_alias_sets_should_exit() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/quit")
    assert result["should_exit"] is True


def test_dispatch_routes_raw_setting() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(workbench, "/raw on")
    assert result["kind"] == "setting"
    assert result["payload"]["setting"] == "raw_mode"
    assert result["payload"]["value"] == "on"


def test_dispatch_routes_current_task_settings() -> None:
    workbench = DispatchWorkbench()
    use_result = dispatch_shell_input(workbench, "/use click-2403-ingest-1")
    clear_result = dispatch_shell_input(workbench, "/clear", current_task_id="click-2403-ingest-1")
    assert use_result["kind"] == "setting"
    assert use_result["payload"]["setting"] == "current_task"
    assert use_result["payload"]["value"] == "click-2403-ingest-1"
    assert clear_result["kind"] == "setting"
    assert clear_result["payload"]["setting"] == "current_task"
    assert clear_result["payload"]["value"] is None


def test_dispatch_routes_session_and_compare_family() -> None:
    workbench = DispatchWorkbench()
    session_result = dispatch_shell_input(workbench, "/session click-2403-ingest-1")
    compare_result = dispatch_shell_input(workbench, "/compare-family click-2403-ingest-1 --limit 4")
    assert session_result["payload"]["session_path"].endswith("click-2403-ingest-1.json")
    assert compare_result["payload"]["peer_count"] == 4


def test_dispatch_uses_current_task_context() -> None:
    workbench = DispatchWorkbench()
    show_result = dispatch_shell_input(workbench, "/show", current_task_id="click-2403-ingest-1")
    session_result = dispatch_shell_input(workbench, "/session", current_task_id="click-2403-ingest-1")
    evaluate_result = dispatch_shell_input(workbench, "/evaluate", current_task_id="click-2403-ingest-1")
    compare_result = dispatch_shell_input(workbench, "/compare-family --limit 2", current_task_id="click-2403-ingest-1")
    status_result = dispatch_shell_input(workbench, "/status", current_task_id="click-2403-ingest-1")
    resume_result = dispatch_shell_input(workbench, "/resume", current_task_id="click-2403-ingest-1")

    assert show_result["kind"] == "show"
    assert session_result["payload"]["session_path"].endswith("click-2403-ingest-1.json")
    assert evaluate_result["payload"]["evaluation"]["task_id"] == "click-2403-ingest-1"
    assert compare_result["payload"]["task_id"] == "click-2403-ingest-1"
    assert status_result["payload"]["task_id"] == "click-2403-ingest-1"
    assert resume_result["payload"]["task_id"] == "click-2403-ingest-1"


def test_dispatch_routes_run_and_resume() -> None:
    workbench = DispatchWorkbench()
    run_result = dispatch_shell_input(
        workbench,
        '/run click-5555 "fix prompt defaults" --target-file src/click/termui.py --validation-command "pytest tests/test_termui.py -q"',
    )
    resume_result = dispatch_shell_input(
        workbench,
        '/resume click-5555 "fallback task" --validation-command "pytest tests/test_termui.py -q"',
    )
    assert run_result["payload"]["task_id"] == "click-5555"
    assert run_result["payload"]["task"] == "fix prompt defaults"
    assert run_result["payload"]["target_files"] == ["src/click/termui.py"]
    assert resume_result["payload"]["fallback_task"] == "fallback task"
    assert resume_result["payload"]["validation_commands"] == ["pytest tests/test_termui.py -q"]


def test_dispatch_blocks_resume_when_controller_disallows_resume() -> None:
    class GuardedWorkbench(DispatchWorkbench):
        def inspect_session(self, *, task_id: str):
            payload = super().inspect_session(task_id=task_id)
            payload.setdefault("canonical_views", {})["controller"] = {
                "status": "completed",
                "allowed_actions": ["inspect_context"],
                "guard_reasons": [
                    {
                        "action": "resume",
                        "reason": "task session is completed and cannot resume",
                    }
                ],
            }
            return payload

        def resume(self, **kwargs):
            raise AssertionError("resume should not be invoked when controller preflight blocks")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "available",
                        "health_reason": "",
                    },
                }
            }

    result = dispatch_shell_input(GuardedWorkbench(), "/resume click-5555")

    assert result["kind"] == "show"
    assert result["should_refresh_status"] is False
    assert result["payload"]["shell_view"] == "controller_preflight"
    assert result["payload"]["command"] == "resume"
    assert result["payload"]["required_action"] == "resume"
    assert result["payload"]["controller_status"] == "completed"
    assert result["payload"]["recommended_command"] == "/show click-5555"


def test_dispatch_routes_ingest() -> None:
    workbench = DispatchWorkbench()
    result = dispatch_shell_input(
        workbench,
        '/ingest click-7777 "record fix" "stored validated fix" --target-file src/click/termui.py --changed-file tests/test_termui.py --validation-command "pytest tests/test_termui.py -q" --validation-summary "green" --validation-ok true',
    )
    assert result["payload"]["task_id"] == "click-7777"
    assert result["payload"]["summary"] == "stored validated fix"
    assert result["payload"]["changed_files"] == ["tests/test_termui.py"]
    assert result["payload"]["validation_ok"] is True


def test_dispatch_returns_error_without_exiting_on_run_failure() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def run(self, **kwargs):
            raise RuntimeError("runtime unavailable")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), '/run click-1 "task"')
    assert result["kind"] == "error"
    assert result["should_exit"] is False
    assert result["text"] == ""
    assert result["payload"]["shell_view"] == "host_error"
    assert result["payload"]["operation"] == "run"
    assert result["payload"]["execution_mode"] == "inspect_only"
    assert result["payload"]["error"] == "live execution blocked by host preflight"


def test_dispatch_preflights_run_before_invoking_broken_live_path() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def run(self, **kwargs):
            raise AssertionError("run should not be invoked when host preflight is unhealthy")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), '/run click-1 "task"')
    assert result["kind"] == "error"
    assert result["payload"]["shell_view"] == "host_error"
    assert result["payload"]["operation"] == "run"
    assert result["payload"]["error"] == "live execution blocked by host preflight"
    assert result["payload"]["recovery_class"] == "missing_credentials_and_runtime"
    assert result["payload"]["recovery_summary"] == "both model credentials and runtime availability must be restored"


def test_dispatch_returns_run_preflight_payload_without_invoking_live_path() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def doctor(self, *, summary: bool = False, check: str | None = None):
            return {
                "mode": "inspect-only",
                "live_ready": False,
                "live_ready_summary": "inspect-only: missing credentials + runtime",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "recommendations": [
                    "configure model credentials to enable live execution",
                    "start or configure Aionis Runtime via AIONIS_BASE_URL",
                ],
            }

        def run(self, **kwargs):
            raise AssertionError("run should not be invoked during preflight-only")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/run click-1 --preflight-only")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "live_preflight"
    assert result["payload"]["operation"] == "run"
    assert result["payload"]["ready"] is False
    assert result["payload"]["recovery_class"] == "missing_credentials_and_runtime"


def test_dispatch_returns_run_preflight_one_line_payload() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "mode": "inspect-only",
                "live_ready": False,
                "live_ready_summary": "inspect-only: missing credentials + runtime",
                "capability_state": "inspect_only_missing_credentials_and_runtime",
                "capability_summary": "can inspect, validate, and ingest; live tasks blocked by missing credentials and runtime",
                "setup_checklist": [
                    {
                        "name": "credentials_configured",
                        "status": "pending",
                        "command_hint": SAFE_CREDENTIALS_HINT,
                    }
                ],
                "recommendations": ["configure model credentials to enable live execution"],
            }

        def host_contract(self):
            return {
                "contract": {
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/run click-1 --preflight-only --one-line")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "live_preflight_one_line"
    assert result["payload"]["summary_line"] == f"run-preflight: click-1 | blocked | inspect-only: missing credentials + runtime | recovery=both model credentials and runtime availability must be restored | hint={SAFE_CREDENTIALS_HINT}"


def test_dispatch_returns_structured_resume_error_when_host_is_degraded() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def resume(self, **kwargs):
            raise RuntimeError("bridge unavailable")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/resume click-1")
    assert result["kind"] == "error"
    assert result["payload"]["shell_view"] == "host_error"
    assert result["payload"]["operation"] == "resume"
    assert result["payload"]["task_id"] == "click-1"


def test_dispatch_preflights_resume_before_invoking_broken_live_path() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def resume(self, **kwargs):
            raise AssertionError("resume should not be invoked when host preflight is unhealthy")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "inspect_only",
                        "health_status": "offline",
                        "health_reason": "model_credentials_missing",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_unreachable",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/resume click-1")
    assert result["kind"] == "error"
    assert result["payload"]["shell_view"] == "host_error"
    assert result["payload"]["operation"] == "resume"
    assert result["payload"]["error"] == "live execution blocked by host preflight"


def test_dispatch_returns_resume_preflight_payload_without_invoking_live_path() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def doctor(self, *, summary: bool = False, check: str | None = None):
            return {
                "mode": "live",
                "live_ready": True,
                "live_ready_summary": "live-ready",
                "capability_state": "live_ready",
                "capability_summary": "can run live tasks, inspect, validate, and ingest",
                "recommendations": [],
            }

        def resume(self, **kwargs):
            raise AssertionError("resume should not be invoked during preflight-only")

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "available",
                        "health_reason": "",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/resume click-1 --preflight-only")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "live_preflight"
    assert result["payload"]["operation"] == "resume"
    assert result["payload"]["ready"] is True
    assert result["payload"]["recovery_class"] == "ready"


def test_dispatch_returns_resume_preflight_one_line_payload() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def doctor(self, *, summary: bool = False, check: str | None = None, one_line: bool = False):
            return {
                "mode": "live",
                "live_ready": True,
                "live_ready_summary": "live-ready",
                "capability_state": "live_ready",
                "capability_summary": "can run live tasks, inspect, validate, and ingest",
                "recommendations": [],
            }

        def host_contract(self):
            return {
                "contract": {
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "available",
                        "health_reason": "",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/resume click-1 --preflight-only --one-line")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "live_preflight_one_line"
    assert result["payload"]["summary_line"] == "resume-preflight: click-1 | ready | live-ready | recovery=live preflight is green"


def test_dispatch_returns_runtime_degraded_recovery_for_run_preflight() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def doctor(self, *, summary: bool = False, check: str | None = None):
            return {
                "mode": "inspect-only",
                "live_ready": False,
                "live_ready_summary": "inspect-only: degraded",
                "capability_state": "inspect_only_degraded",
                "capability_summary": "can inspect, validate, and ingest; live tasks are currently degraded",
                "setup_checklist": [
                    {
                        "name": "runtime_available",
                        "status": "pending",
                        "command_hint": "curl -fsS http://127.0.0.1:3101/health",
                    }
                ],
                "recommendations": ["inspect the runtime health endpoint and restore connectivity"],
            }

        def host_contract(self):
            return {
                "contract": {
                    "product_shell": {"name": "aionis_cli"},
                    "learning_engine": {"name": "workbench_engine"},
                    "execution_host": {
                        "name": "deepagents_local_shell",
                        "mode": "live_enabled",
                        "health_status": "available",
                        "health_reason": "",
                    },
                    "runtime_host": {
                        "name": "aionis_runtime_host",
                        "health_status": "degraded",
                        "health_reason": "runtime_health_http_503",
                    },
                }
            }

    result = dispatch_shell_input(BrokenWorkbench(), "/run click-1 --preflight-only")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "live_preflight"
    assert result["payload"]["ready"] is False
    assert result["payload"]["recovery_class"] == "runtime_degraded"
    assert result["payload"]["recovery_summary"] == "runtime is configured but unhealthy; inspect the health endpoint before retrying"
    assert result["payload"]["recovery_command_hint"] == "curl -fsS http://127.0.0.1:3101/health"


def test_dispatch_blocks_preflight_when_doctor_cannot_confirm_readiness() -> None:
    class BrokenWorkbench(DispatchWorkbench):
        def host_contract(self):
            return {"contract": {}}

    result = dispatch_shell_input(BrokenWorkbench(), "/resume click-1 --preflight-only")
    assert result["kind"] == "show"
    assert result["payload"]["shell_view"] == "live_preflight"
    assert result["payload"]["ready"] is False
