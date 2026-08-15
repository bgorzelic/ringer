#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ringer import (  # noqa: E402
    AppConfig,
    ArtifactConfig,
    EngineConfig,
    EvalConfig,
    Manifest,
    RingerRunner,
    TaskSpec,
    Verifier,
    WorkerResult,
)

LONG_SPEC = (
    "Create the requested output in the current task directory and ensure the executable "
    "check reports a useful reason if the output cannot be verified."
)


def test_config(root: Path) -> AppConfig:
    engine = EngineConfig(
        name="test",
        bin=sys.executable,
        args_template=("-c", "pass"),
        full_access_args=(),
        sandbox_args=(),
        token_regex=None,
    )
    return AppConfig(
        path=None,
        identity_default=None,
        state_dir=root / "state",
        dashboard_port_base=8787,
        hud_port=8700,
        hud_app_path=None,
        allow_full_access=False,
        eval=EvalConfig(backend="jsonl", jsonl_path=root / "eval.jsonl"),
        engines={"test": engine},
        artifact=ArtifactConfig(
            enabled=False,
            out_template=str(root / "live.html"),
            report_template=str(root / "report.html"),
            index_out=root / "index.html",
        ),
    )


def test_manifest(root: Path, keys: tuple[str, ...] = ("one",)) -> Manifest:
    return Manifest.from_obj(
        {
            "run_name": "runner-lifecycle-test",
            "workdir": str(root / "work"),
            "max_parallel": len(keys),
            "tasks": [
                {
                    "key": key,
                    "spec": LONG_SPEC,
                    "check": "test -s output.txt || { echo 'FAIL: output missing'; exit 1; }",
                    "engine": "test",
                    "expect_files": ["output.txt"],
                    "verified": "the current attempt created or updated output.txt",
                }
                for key in keys
            ],
        }
    )


class CheckCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_cancellation_terminates_and_reaps_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            taskdir = Path(temp)
            pid_path = taskdir / "check.pid"
            command = f"echo $$ > {shlex.quote(str(pid_path))}; sleep 30"
            check_task = asyncio.create_task(Verifier._run_check(command, taskdir))
            for _ in range(100):
                if pid_path.exists():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(pid_path.exists(), "check process did not start")
            pid = int(pid_path.read_text(encoding="utf-8").strip())

            check_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await check_task

            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


class ExpectedFileFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_expected_output_is_rejected_and_fresh_output_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            taskdir = Path(temp)
            output = taskdir / "output.txt"
            output.write_text("old\n", encoding="utf-8")
            task = TaskSpec(
                key="freshness",
                spec=LONG_SPEC,
                check="test -s output.txt",
                expect_files=("output.txt",),
            )
            verifier = Verifier()

            before = verifier.snapshot_expected_files(task, taskdir)
            stale = await verifier.verify(task, taskdir, before)
            self.assertFalse(stale.ok)
            self.assertEqual(("output.txt",), stale.stale_files)

            before = verifier.snapshot_expected_files(task, taskdir)
            output.write_text("new material\n", encoding="utf-8")
            fresh = await verifier.verify(task, taskdir, before)
            self.assertTrue(fresh.ok, fresh.raw_output_excerpt)
            self.assertEqual((), fresh.stale_files)

    async def test_runner_snapshots_each_attempt_before_worker_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stale_runner = RingerRunner(
                test_manifest(root / "stale"),
                test_config(root / "stale"),
                identity="freshness-test",
                dashboard_enabled=False,
            )
            stale_runtime = stale_runner.runtimes[0]
            stale_runtime.taskdir.mkdir(parents=True)
            (stale_runtime.taskdir / "output.txt").write_text("old\n", encoding="utf-8")
            try:
                with patch.object(
                    stale_runner,
                    "_run_worker",
                    return_value=WorkerResult(returncode=0, timed_out=False, tokens=None),
                ):
                    await stale_runner._run_task(stale_runtime)
            finally:
                stale_runner.logger.close()
            self.assertEqual("fail", stale_runtime.status)
            self.assertEqual(2, stale_runtime.attempts)
            self.assertIn("stale expected files", stale_runtime.last_check_output)

            fresh_runner = RingerRunner(
                test_manifest(root / "fresh"),
                test_config(root / "fresh"),
                identity="freshness-test",
                dashboard_enabled=False,
            )
            fresh_runtime = fresh_runner.runtimes[0]
            fresh_runtime.taskdir.mkdir(parents=True)
            (fresh_runtime.taskdir / "output.txt").write_text("old\n", encoding="utf-8")

            async def write_fresh_output(_runtime, _spec, _attempt):
                (fresh_runtime.taskdir / "output.txt").write_text(
                    "new material\n",
                    encoding="utf-8",
                )
                return WorkerResult(returncode=0, timed_out=False, tokens=None)

            try:
                with patch.object(fresh_runner, "_run_worker", side_effect=write_fresh_output):
                    await fresh_runner._run_task(fresh_runtime)
            finally:
                fresh_runner.logger.close()
            self.assertEqual("pass", fresh_runtime.status)
            self.assertEqual(1, fresh_runtime.attempts)

    async def test_check_created_absolute_expected_output_is_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            taskdir = root / "task"
            taskdir.mkdir()
            exported = root / "exported.patch"
            task = TaskSpec(
                key="export",
                spec=LONG_SPEC,
                check=f"printf 'patch data\\n' > {shlex.quote(str(exported))}",
                expect_files=(str(exported),),
            )
            verifier = Verifier(workdir=root)
            before = verifier.snapshot_expected_files(task, taskdir)

            result = await verifier.verify(task, taskdir, before)

            self.assertTrue(result.ok, result.raw_output_excerpt)
            self.assertEqual("patch data\n", exported.read_text(encoding="utf-8"))

    async def test_identical_absolute_export_rewritten_by_check_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            taskdir = root / "task"
            taskdir.mkdir()
            exported = root / "exported.patch"
            exported.write_text("same patch\n", encoding="utf-8")
            task = TaskSpec(
                key="export-retry",
                spec=LONG_SPEC,
                check=(
                    "python3 -c "
                    + shlex.quote(
                        "from pathlib import Path; "
                        + f"Path({str(exported)!r}).write_text('same patch\\n', encoding='utf-8')"
                    )
                ),
                expect_files=(str(exported),),
            )
            verifier = Verifier(workdir=root)
            before = verifier.snapshot_expected_files(task, taskdir)

            result = await verifier.verify(task, taskdir, before)

            self.assertFalse(result.ok)
            self.assertEqual((str(exported),), result.stale_files)


class UnexpectedRunnerFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_task_failure_finalizes_siblings_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = RingerRunner(
                test_manifest(root, ("broken", "sibling")),
                test_config(root),
                identity="lifecycle-test",
                dashboard_enabled=False,
            )
            sibling_cancelled = asyncio.Event()

            async def fail_one(runtime):
                if runtime.task.key == "broken":
                    await asyncio.sleep(0)
                    raise RuntimeError("sensitive internal detail")
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    sibling_cancelled.set()
                    raise

            with (
                patch.object(runner, "_run_task", side_effect=fail_one),
                patch.object(runner, "kill_all_workers", wraps=runner.kill_all_workers) as kill_workers,
            ):
                with self.assertRaisesRegex(RuntimeError, "sensitive internal detail"):
                    await runner.run()

            self.assertTrue(sibling_cancelled.is_set())
            kill_workers.assert_awaited_once()
            self.assertTrue(runner.state_writer.finished)
            self.assertTrue(all(runtime.status == "fail" for runtime in runner.runtimes))
            self.assertTrue(all(runtime.final_verdict == "ERROR" for runtime in runner.runtimes))
            self.assertTrue(
                all("sensitive internal detail" not in runtime.last_check_output for runtime in runner.runtimes)
            )
            state = json.loads(runner.state_writer.path.read_text(encoding="utf-8"))
            self.assertTrue(state["finished"])
            self.assertEqual(2, state["summary"]["fail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
