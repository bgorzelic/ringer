#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import contextlib
import io
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ringer import (  # noqa: E402
    AppConfig,
    ArtifactConfig,
    EngineConfig,
    EvalConfig,
    Manifest,
    RingerRunner,
    StateWriter,
    TaskRuntime,
    TaskSpec,
    aggregate_model_scoreboard_rows,
    load_engines,
    model_scoreboard_tier,
    proven_model_group,
    print_summary,
    render_final_report_html,
)


LONG_SPEC = (
    "Create the requested output in the current working directory and keep the change "
    "scoped to this test task."
)


class AccountabilityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def engine(
        self,
        *,
        name: str = "mock",
        bin_path: str | None = None,
        access_class: str | None = "local",
        access_label: str | None = "Local fixture",
    ) -> EngineConfig:
        return EngineConfig(
            name=name,
            bin=bin_path or sys.executable,
            args_template=("-c", "pass"),
            full_access_args=(),
            sandbox_args=(),
            token_regex=None,
            access_class=access_class,
            access_label=access_label,
        )

    def runtime(self, key: str = "task-one", *, engine: str = "mock") -> TaskRuntime:
        taskdir = self.root / "work" / key
        taskdir.mkdir(parents=True, exist_ok=True)
        log_path = taskdir / "worker.log"
        log_path.write_text("", encoding="utf-8")
        return TaskRuntime(
            task=TaskSpec(
                key=key,
                spec=LONG_SPEC,
                check="true",
                engine=engine,
            ),
            taskdir=taskdir,
            log_path=log_path,
            attempts=1,
        )

    def writer(
        self,
        runtimes: list[TaskRuntime],
        engines: dict[str, EngineConfig] | None = None,
    ) -> StateWriter:
        return StateWriter(
            "accountability-run",
            "Accountability Run",
            "tester",
            self.root / "state",
            engines or {"mock": self.engine()},
            datetime(2026, 8, 15, tzinfo=timezone.utc),
            runtimes,
            threading.RLock(),
            artifact=ArtifactConfig(
                enabled=False,
                out_template=str(self.root / "live.html"),
                report_template=str(self.root / "report.html"),
                index_out=self.root / "index.html",
            ),
        )

    def config(self, engines: dict[str, EngineConfig]) -> AppConfig:
        return AppConfig(
            path=None,
            identity_default=None,
            state_dir=self.root / "state",
            dashboard_port_base=8787,
            hud_port=8700,
            hud_app_path=None,
            allow_full_access=False,
            eval=EvalConfig(backend="jsonl", jsonl_path=self.root / "eval.jsonl"),
            engines=engines,
            artifact=ArtifactConfig(
                enabled=False,
                out_template=str(self.root / "live.html"),
                report_template=str(self.root / "report.html"),
                index_out=self.root / "index.html",
            ),
        )

    def manifest(self, *, engine: str) -> Manifest:
        return Manifest.from_obj(
            {
                "run_name": "accountability-test",
                "workdir": str(self.root / "runner-work"),
                "tasks": [
                    {
                        "key": "task-one",
                        "spec": LONG_SPEC,
                        "check": "true",
                        "engine": engine,
                    }
                ],
            }
        )

    def test_zero_known_tokens_stay_fully_unknown_for_task_and_run(self) -> None:
        runtime = self.runtime()
        runtime.record_tokens(None)

        state = self.writer([runtime]).snapshot()
        task = state["tasks"][0]

        self.assertIsNone(task["tokens"])
        self.assertIsNone(task["tokens_known_total"])
        self.assertFalse(task["tokens_exact"])
        self.assertFalse(task["tokens_partial"])
        self.assertTrue(task["tokens_unknown"])
        self.assertIsNone(state["totals"]["tokens"])
        self.assertTrue(state["totals"]["tokens_unknown"])

    def test_partial_known_tokens_keep_labeled_subtotal_not_numeric_total(self) -> None:
        runtime = self.runtime()
        runtime.attempts = 2
        runtime.record_tokens(40)
        runtime.record_tokens(None)

        state = self.writer([runtime]).snapshot()
        task = state["tasks"][0]

        self.assertIsNone(task["tokens"])
        self.assertEqual(40, task["tokens_known_total"])
        self.assertFalse(task["tokens_exact"])
        self.assertTrue(task["tokens_partial"])
        self.assertFalse(task["tokens_unknown"])
        self.assertIsNone(state["totals"]["tokens"])
        self.assertEqual(40, state["totals"]["tokens_known_total"])
        self.assertTrue(state["totals"]["tokens_partial"])

    def test_all_known_tokens_emit_exact_task_and_run_totals(self) -> None:
        runtime = self.runtime()
        runtime.attempts = 2
        runtime.record_tokens(40)
        runtime.record_tokens(2)

        state = self.writer([runtime]).snapshot()
        task = state["tasks"][0]

        self.assertEqual(42, task["tokens"])
        self.assertEqual(42, task["tokens_known_total"])
        self.assertTrue(task["tokens_exact"])
        self.assertFalse(task["tokens_partial"])
        self.assertFalse(task["tokens_unknown"])
        self.assertEqual(42, state["totals"]["tokens"])
        self.assertTrue(state["totals"]["tokens_exact"])

    def test_access_parsing_defaults_validation_and_state_emission(self) -> None:
        default_codex = load_engines(None)["codex"]
        self.assertIsNone(default_codex.access_class)
        self.assertIsNone(default_codex.access_label)

        for allowed in ("subscription", "managed-oauth", "local", "metered", "unavailable"):
            with self.subTest(access_class=allowed):
                self.assertEqual(
                    allowed,
                    load_engines({"codex": {"access_class": allowed}})["codex"].access_class,
                )

        configured = load_engines(
            {
                "codex": {
                    "access_class": " managed-oauth ",
                    "access_label": "Company SSO",
                }
            }
        )["codex"]
        self.assertEqual("managed-oauth", configured.access_class)
        self.assertEqual("Company SSO", configured.access_label)

        with self.assertRaisesRegex(ValueError, "access_class must be one of"):
            load_engines({"codex": {"access_class": "auto-detected"}})
        with self.assertRaisesRegex(ValueError, "access_label must be a string"):
            load_engines({"codex": {"access_label": ["not", "plain"]}})

        runtime = self.runtime(engine="codex")
        runtime.record_tokens(None)
        state = self.writer([runtime], {"codex": configured}).snapshot()
        self.assertEqual("managed-oauth", state["tasks"][0]["access_class"])
        self.assertEqual("Company SSO", state["tasks"][0]["access_label"])
        self.assertEqual(
            {
                "access_class": "managed-oauth",
                "access_label": "Company SSO",
            },
            state["configured_access"]["codex"],
        )

    def test_final_report_shows_retry_tokens_access_and_blocked_reason(self) -> None:
        state = {
            "run_id": "run-1",
            "run_name": "Accountability",
            "identity": "tester",
            "elapsed_s": 3,
            "finished": True,
            "configured_access": {
                "codex": {
                    "access_class": "subscription",
                    "access_label": "Team plan",
                }
            },
            "totals": {
                "tokens": None,
                "tokens_known_total": 40,
                "tokens_exact": False,
                "tokens_partial": True,
                "tokens_unknown": False,
            },
            "tasks": [
                {
                    "key": "retry-pass",
                    "status": "pass",
                    "attempts": 2,
                    "elapsed_s": 2,
                    "tokens": None,
                    "tokens_known_total": 40,
                    "tokens_exact": False,
                    "tokens_partial": True,
                    "tokens_unknown": False,
                    "access_class": "subscription",
                    "access_label": "Team plan",
                },
                {
                    "key": "blocked",
                    "status": "fail",
                    "attempts": 1,
                    "elapsed_s": 1,
                    "tokens": None,
                    "tokens_known_total": None,
                    "tokens_exact": False,
                    "tokens_partial": False,
                    "tokens_unknown": True,
                    "access_class": "unavailable",
                    "access_label": "Offline",
                    "blocked_kind": "spawn",
                    "blocked_reason": "Worker process could not be started.",
                },
            ],
        }

        html = render_final_report_html(state)

        self.assertIn("Attempts: 2 attempts", html)
        self.assertIn("Passed after retry", html)
        self.assertIn("Tokens: partial (40 known; at least one attempt unknown)", html)
        self.assertIn("Configured access: subscription (Team plan)", html)
        self.assertIn("Blocked (spawn): Worker process could not be started.", html)
        self.assertIn("Token accounting: partial", html)

    def test_failure_paths_set_concise_non_secret_blocked_reasons(self) -> None:
        preparation_runner = RingerRunner(
            self.manifest(engine="mock"),
            self.config({"mock": self.engine()}),
            "tester",
            dashboard_enabled=False,
        )
        preparation_runtime = preparation_runner.runtimes[0]
        preparation_error_kinds: list[str | None] = []
        original_log_attempt = preparation_runner._log_attempt

        def capture_prepare_attempt(*args: object) -> None:
            preparation_error_kinds.append(getattr(args[3], "error_kind", None))

        preparation_runner._log_attempt = capture_prepare_attempt  # type: ignore[method-assign]
        asyncio.run(
            preparation_runner._record_prepare_error(
                preparation_runtime,
                "private detail secret=do-not-emit",
            )
        )
        preparation_runner._log_attempt = original_log_attempt  # type: ignore[method-assign]
        self.assertEqual("Task preparation failed.", preparation_runtime.blocked_reason)
        self.assertEqual("preparation", preparation_runtime.blocked_kind)
        self.assertEqual(["preparation"], preparation_error_kinds)
        self.assertNotIn("secret", preparation_runtime.blocked_reason or "")
        preparation_runner.logger.close()

        config_runner = RingerRunner(
            self.manifest(engine="missing"),
            self.config({}),
            "tester",
            dashboard_enabled=False,
        )
        asyncio.run(config_runner._run_task(config_runner.runtimes[0]))
        self.assertEqual(
            "Worker configuration prevented this task from starting.",
            config_runner.runtimes[0].blocked_reason,
        )
        self.assertEqual("configuration", config_runner.runtimes[0].blocked_kind)
        config_runner.logger.close()

        spawn_engine = self.engine(name="broken", bin_path=str(self.root / "missing-worker"))
        spawn_runner = RingerRunner(
            self.manifest(engine="broken"),
            self.config({"broken": spawn_engine}),
            "tester",
            dashboard_enabled=False,
        )
        asyncio.run(spawn_runner._run_task(spawn_runner.runtimes[0]))
        self.assertEqual(
            "Worker process could not be started.",
            spawn_runner.runtimes[0].blocked_reason,
        )
        self.assertEqual("spawn", spawn_runner.runtimes[0].blocked_kind)
        spawn_runner.logger.close()

        runner_runtime = self.runtime("runner-failure")
        runner_writer = self.writer([runner_runtime])
        runner = RingerRunner(
            self.manifest(engine="mock"),
            self.config({"mock": self.engine()}),
            "tester",
            dashboard_enabled=False,
        )
        runner.runtimes = [runner_runtime]
        runner._mark_unfinished_tasks_failed("unexpected private detail")
        self.assertEqual("Runner stopped before task completion.", runner_runtime.blocked_reason)
        self.assertEqual("runner", runner_runtime.blocked_kind)
        self.assertEqual("Runner stopped before task completion.", runner_writer.snapshot()["tasks"][0]["blocked_reason"])
        self.assertEqual("runner", runner_writer.snapshot()["tasks"][0]["blocked_kind"])
        for blocked_runtime in (
            preparation_runtime,
            config_runner.runtimes[0],
            spawn_runner.runtimes[0],
            runner_runtime,
        ):
            with self.subTest(blocked_kind=blocked_runtime.blocked_kind):
                reason = (blocked_runtime.blocked_reason or "").lower()
                self.assertNotIn("secret", reason)
                self.assertNotIn("private", reason)
        runner.logger.close()

    def test_cancelled_path_sets_closed_kind_and_secret_free_reason(self) -> None:
        runner = RingerRunner(
            self.manifest(engine="mock"),
            self.config({"mock": self.engine()}),
            "tester",
            dashboard_enabled=False,
        )

        async def cancel_worker(
            _runtime: TaskRuntime,
            _spec: str,
            _attempt: int,
        ) -> object:
            raise asyncio.CancelledError("private cancellation detail")

        runner._run_worker = cancel_worker  # type: ignore[method-assign]
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(runner._run_task(runner.runtimes[0]))
        runtime = runner.runtimes[0]
        self.assertEqual("cancelled", runtime.blocked_kind)
        self.assertEqual("Task was cancelled before completion.", runtime.blocked_reason)
        self.assertNotIn("private", runtime.blocked_reason or "")
        runner.logger.close()

    def test_state_and_report_keep_legacy_null_blocked_kind_safe(self) -> None:
        runtime = self.runtime("legacy")
        runtime.blocked_reason = "Legacy blocked detail."
        state = self.writer([runtime]).snapshot()
        self.assertIsNone(state["tasks"][0]["blocked_kind"])

        task_state = state["tasks"][0]
        task_state.pop("blocked_kind")
        state["finished"] = True
        state["elapsed_s"] = 0
        html = render_final_report_html(state)
        self.assertIn("Blocked: Legacy blocked detail.", html)

    def test_terminal_summary_matches_accountability_fields_without_auth_claims(self) -> None:
        passed = self.runtime("retry-pass")
        passed.status = "pass"
        passed.final_verdict = "PASS"
        passed.attempts = 2
        passed.record_tokens(None)
        passed.record_tokens(None)

        blocked = self.runtime("blocked")
        blocked.status = "fail"
        blocked.final_verdict = "ERROR"
        blocked.blocked_kind = "spawn"
        blocked.blocked_reason = "Worker process could not be started."
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            print_summary(
                "run-1",
                [passed, blocked],
                {"mock": self.engine(access_class="subscription", access_label="Team plan")},
            )
        rendered = output.getvalue()
        self.assertIn("Passed after retry", rendered)
        self.assertIn("Configured access: subscription (Team plan)", rendered)
        self.assertIn("Blocked (spawn): Worker process could not be started.", rendered)
        self.assertNotIn("authenticated", rendered.lower())
        self.assertNotIn("exact", rendered.lower())

    def test_cli_and_web_tiers_share_exact_threshold_policy(self) -> None:
        two_of_three = 2 / 3
        self.assertEqual("probation", model_scoreboard_tier(3, two_of_three))
        self.assertFalse(
            proven_model_group({"tasks": 3, "first_try_pass_rate": two_of_three})
        )
        self.assertEqual("proven", model_scoreboard_tier(3, 0.67))
        self.assertTrue(proven_model_group({"tasks": 3, "first_try_pass_rate": 0.67}))

        rows = [
            {
                "run_id": f"run-{index}",
                "task_key": f"task-{index}",
                "worker_engine": "opencode",
                "model": "openrouter/example",
                "task_type": "code-fix",
                "verdict": "PASS" if index < 2 else "FAIL",
                "retry": False,
                "logged_at": f"2026-08-15T00:00:0{index}+00:00",
            }
            for index in range(3)
        ]
        scoreboard = aggregate_model_scoreboard_rows(rows)
        self.assertAlmostEqual(two_of_three, scoreboard[0]["first_try_pass_rate"])
        self.assertEqual("probation", scoreboard[0]["tier"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
