#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import signal
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
    check_may_fail_silently,
    lint_manifest,
    load_engines,
    preflight_engine_bins,
    process_group_exists,
)

LONG_SPEC = (
    "Create the requested artifact in the current working directory, keep the change scoped, "
    "and make the check command report a useful reason when verification fails."
)
GOOD_CHECK = (
    "test -s output.txt || "
    "{ echo 'FAIL: output.txt is missing or empty'; exit 1; }"
)


def task_obj(
    key: str = "one",
    *,
    check: str = GOOD_CHECK,
    expect_files: list[str] | None = None,
    engine: str = "test",
    timeout_s: int = 30,
) -> dict[str, object]:
    return {
        "key": key,
        "spec": LONG_SPEC,
        "check": check,
        "engine": engine,
        "expect_files": ["output.txt"] if expect_files is None else expect_files,
        "timeout_s": timeout_s,
        "verified": "the expected output exists and satisfies the executable check",
    }


def manifest_obj(
    root: Path,
    tasks: list[dict[str, object]],
    *,
    external_expect_roots: list[str] | None = None,
) -> dict[str, object]:
    obj: dict[str, object] = {
        "run_name": "runtime-safety-closure-test",
        "workdir": str(root / "work"),
        "max_parallel": max(1, len(tasks)),
        "tasks": tasks,
    }
    if external_expect_roots is not None:
        obj["external_expect_roots"] = external_expect_roots
    return obj


def make_config(root: Path, engine: EngineConfig) -> AppConfig:
    return AppConfig(
        path=None,
        identity_default=None,
        state_dir=root / "state",
        dashboard_port_base=8787,
        hud_port=8700,
        hud_app_path=None,
        allow_full_access=False,
        eval=EvalConfig(backend="jsonl", jsonl_path=root / "eval.jsonl"),
        engines={engine.name: engine},
        artifact=ArtifactConfig(
            enabled=False,
            out_template=str(root / "live.html"),
            report_template=str(root / "report.html"),
            index_out=root / "index.html",
        ),
    )


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def wait_for_pid_file(path: Path) -> int:
    for _ in range(300):
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return int(path.read_text(encoding="utf-8").strip())
        await asyncio.sleep(0.01)
    raise AssertionError(f"process did not publish pid file: {path}")


async def wait_for_pid_exit(pid: int) -> None:
    for _ in range(300):
        if not pid_exists(pid):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"process leaked after cleanup: {pid}")


class ExpectedPathConfinementTests(unittest.TestCase):
    def test_rejects_parent_and_symlink_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "must not contain '..'"):
                Manifest.from_obj(
                    manifest_obj(root, [task_obj(expect_files=["../escape.txt"])])
                )

            taskdir = root / "work" / "one"
            outside = root / "outside"
            taskdir.mkdir(parents=True)
            outside.mkdir()
            (taskdir / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "escapes task directory"):
                Manifest.from_obj(
                    manifest_obj(root, [task_obj(expect_files=["link/escape.txt"])])
                )

    def test_absolute_outputs_require_workdir_or_canonical_external_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workdir_export = root / "work" / "exports" / "fix.patch"
            manifest = Manifest.from_obj(
                manifest_obj(root, [task_obj(expect_files=[str(workdir_export)])])
            )
            self.assertEqual((str(workdir_export),), manifest.tasks[0].expect_files)

            fix_swarm_obj = manifest_obj(
                root,
                [task_obj(expect_files=[str(workdir_export)])],
            )
            fix_swarm_obj["worktrees"] = True
            fix_swarm_obj["repo"] = str(root)
            fix_swarm = Manifest.from_obj(fix_swarm_obj)
            self.assertFalse(
                any("deliverable would be deleted" in item for item in lint_manifest(fix_swarm))
            )

            outside = root / "outside" / "report.md"
            with self.assertRaisesRegex(ValueError, "escapes manifest workdir"):
                Manifest.from_obj(
                    manifest_obj(root, [task_obj(expect_files=[str(outside)])])
                )

            external_root = root / "external"
            external_root.mkdir()
            external_manifest = Manifest.from_obj(
                manifest_obj(
                    root,
                    [task_obj(expect_files=[str(external_root / "report.md")])],
                    external_expect_roots=[str(external_root)],
                )
            )
            self.assertEqual((external_root.resolve(),), external_manifest.external_expect_roots)

            with self.assertRaisesRegex(ValueError, "entries must be absolute"):
                Manifest.from_obj(
                    manifest_obj(
                        root,
                        [task_obj()],
                        external_expect_roots=["relative/export-root"],
                    )
                )


class WorkerVerdictTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonzero_worker_retries_even_when_check_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = EngineConfig(
                name="test",
                bin=sys.executable,
                args_template=("-c", "pass"),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
            )
            manifest = Manifest.from_obj(
                manifest_obj(
                    root,
                    [
                        task_obj(
                            check=(
                                "test -s output.txt && echo 'check evidence: output is present' || "
                                "{ echo 'FAIL: output missing'; exit 1; }"
                            )
                        )
                    ],
                )
            )
            runner = RingerRunner(
                manifest,
                make_config(root, engine),
                identity="worker-verdict-test",
                dashboard_enabled=False,
            )
            runtime = runner.runtimes[0]

            async def worker_attempt(_runtime, _spec, attempt):
                (runtime.taskdir / "output.txt").write_text(
                    f"attempt {attempt}\n",
                    encoding="utf-8",
                )
                return WorkerResult(
                    returncode=9 if attempt == 1 else 0,
                    timed_out=False,
                    tokens=None,
                )

            try:
                with (
                    patch.object(runner, "_run_worker", side_effect=worker_attempt),
                    patch.object(runner, "_log_attempt", wraps=runner._log_attempt) as log_attempt,
                ):
                    await runner._run_task(runtime)
            finally:
                runner.logger.close()

            self.assertEqual("pass", runtime.status)
            self.assertEqual(2, runtime.attempts)
            first_call = log_attempt.call_args_list[0].args
            self.assertEqual("FAIL", first_call[5])
            self.assertTrue(first_call[4].ok)
            self.assertIn("check evidence", first_call[4].raw_output_excerpt)


class ProcessGroupCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_kills_term_ignoring_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pid_path = root / "descendant.pid"
            child_code = (
                "import os, signal, time; from pathlib import Path; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"Path({str(pid_path)!r}).write_text(str(os.getpid()), encoding='utf-8'); "
                "time.sleep(30)"
            )
            parent_code = (
                "import subprocess, time; "
                f"subprocess.Popen([{sys.executable!r}, '-c', {child_code!r}]); "
                "time.sleep(30)"
            )
            engine = EngineConfig(
                name="test",
                bin=sys.executable,
                args_template=("-c", parent_code),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
            )
            manifest = Manifest.from_obj(
                manifest_obj(
                    root,
                    [task_obj(expect_files=[], check="true", timeout_s=1)],
                )
            )
            runner = RingerRunner(
                manifest,
                make_config(root, engine),
                identity="timeout-cleanup-test",
                dashboard_enabled=False,
            )
            runtime = runner.runtimes[0]
            runtime.taskdir.mkdir(parents=True)
            descendant_pid: int | None = None
            try:
                worker_task = asyncio.create_task(
                    runner._run_worker(runtime, runtime.task.spec, 1)
                )
                descendant_pid = await wait_for_pid_file(pid_path)
                result = await worker_task
                self.assertTrue(result.timed_out)
                await wait_for_pid_exit(descendant_pid)
            finally:
                runner.logger.close()
                if descendant_pid is not None and pid_exists(descendant_pid):
                    os.kill(descendant_pid, signal.SIGKILL)

    async def test_global_cleanup_uses_group_after_leader_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pid_path = root / "global-descendant.pid"
            child_code = (
                "import os, signal, time; from pathlib import Path; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"Path({str(pid_path)!r}).write_text(str(os.getpid()), encoding='utf-8'); "
                "time.sleep(30)"
            )
            parent_code = (
                "import subprocess; "
                f"subprocess.Popen([{sys.executable!r}, '-c', {child_code!r}], "
                "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
            )
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                parent_code,
                start_new_session=True,
            )
            descendant_pid = await wait_for_pid_file(pid_path)
            await proc.wait()
            self.assertTrue(process_group_exists(proc.pid))

            engine = EngineConfig(
                name="test",
                bin=sys.executable,
                args_template=("-c", "pass"),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
            )
            runner = RingerRunner(
                Manifest.from_obj(manifest_obj(root, [task_obj()])),
                make_config(root, engine),
                identity="global-cleanup-test",
                dashboard_enabled=False,
            )
            runner.active_process_groups[proc.pid] = proc
            try:
                await runner.kill_all_workers()
                await wait_for_pid_exit(descendant_pid)
                self.assertFalse(process_group_exists(proc.pid))
            finally:
                runner.logger.close()
                if pid_exists(descendant_pid):
                    os.kill(descendant_pid, signal.SIGKILL)


class ExecutableDeclarationTests(unittest.TestCase):
    def test_rejects_relative_slash_and_accepts_bare_or_absolute(self) -> None:
        with self.assertRaisesRegex(ValueError, "slash-containing relative paths"):
            load_engines(
                {
                    "bad": {
                        "bin": "bin/worker",
                        "args_template": ["{spec}"],
                    }
                }
            )
        engines = load_engines(
            {
                "bare": {"bin": "sh", "args_template": ["-c", "{spec}"]},
                "absolute": {
                    "bin": sys.executable,
                    "args_template": ["-c", "{spec}"],
                },
            }
        )
        self.assertEqual("sh", engines["bare"].bin)
        self.assertEqual(sys.executable, engines["absolute"].bin)

    def test_preflight_rejects_relative_slash_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = EngineConfig(
                name="test",
                bin=sys.executable,
                args_template=("-c", "pass"),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
                preflight_executables=("tools/worker",),
            )
            manifest = Manifest.from_obj(manifest_obj(root, [task_obj()]))
            with self.assertRaisesRegex(ValueError, "slash-containing relative paths"):
                preflight_engine_bins(manifest, make_config(root, engine))

    def test_env_declaration_uses_inline_path_from_task_engine_args(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bin_dir = root / "inline-bin"
            bin_dir.mkdir()
            (bin_dir / "declared-worker").symlink_to("/bin/sh")
            (bin_dir / "selected-worker").symlink_to("/bin/sh")
            engine = EngineConfig(
                name="test",
                bin="/usr/bin/env",
                args_template=("{engine_args}", "{spec}"),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
                env_allowlist=(),
                worker_executable="declared-worker",
            )
            task = task_obj()
            task["engine_args"] = [f"PATH={bin_dir}", "selected-worker"]
            manifest = Manifest.from_obj(manifest_obj(root, [task]))

            preflight_engine_bins(manifest, make_config(root, engine))

    def test_env_preflight_checks_multiple_tasks_in_key_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bin_dir = root / "inline-bin"
            bin_dir.mkdir()
            (bin_dir / "inline-worker").symlink_to("/bin/sh")
            engine = EngineConfig(
                name="test",
                bin="/usr/bin/env",
                args_template=("{engine_args}", "{spec}"),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
                env_allowlist=(),
                worker_executable="inline-worker",
            )
            later_mismatch = task_obj("z-mismatched")
            later_mismatch["engine_args"] = [f"PATH={bin_dir}", "/usr/bin/false"]
            mismatched = task_obj("a-mismatched")
            mismatched["engine_args"] = [f"PATH={bin_dir}", "/usr/bin/true"]
            manifest = Manifest.from_obj(manifest_obj(root, [later_mismatch, mismatched]))

            with self.assertRaisesRegex(
                ValueError,
                r"task 'a-mismatched' worker executable mismatch",
            ):
                preflight_engine_bins(manifest, make_config(root, engine))


class ContentFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_touch_and_identical_rewrite_stay_stale_but_new_bytes_are_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            taskdir = Path(temp)
            output = taskdir / "output.txt"
            output.write_text("same bytes\n", encoding="utf-8")
            task = TaskSpec(
                key="freshness",
                spec=LONG_SPEC,
                check="true",
                expect_files=("output.txt",),
            )
            verifier = Verifier()

            before = verifier.snapshot_expected_files(task, taskdir)
            os.utime(output, None)
            touched = await verifier.verify(task, taskdir, before)
            self.assertFalse(touched.ok)
            self.assertEqual(("output.txt",), touched.stale_files)

            before = verifier.snapshot_expected_files(task, taskdir)
            output.write_text("same bytes\n", encoding="utf-8")
            rewritten = await verifier.verify(task, taskdir, before)
            self.assertFalse(rewritten.ok)
            self.assertEqual(("output.txt",), rewritten.stale_files)

            before = verifier.snapshot_expected_files(task, taskdir)
            output.write_text("different bytes\n", encoding="utf-8")
            changed = await verifier.verify(task, taskdir, before)
            self.assertTrue(changed.ok, changed.raw_output_excerpt)


class SilentCheckLintTests(unittest.TestCase):
    def test_rejects_silent_failure_branches_and_hidden_output(self) -> None:
        for check in (
            "test -s output.txt || exit 1",
            "test -s output.txt || false",
            "test -s output.txt || { echo 'FAIL: missing' >/dev/null; exit 1; }",
            "test -s missing.txt || { echo 'FAIL: missing'; exit 1; } >/dev/null",
            "grep -q ready output.txt || { printf 'FAIL: missing\\n' >failure.log; exit 1; }",
            "test -s output.txt || { exit 1; echo 'FAIL: unreachable'; }",
        ):
            with self.subTest(check=check):
                self.assertTrue(check_may_fail_silently(check))

    def test_accepts_visible_useful_failure_output(self) -> None:
        for check in (
            "test -s output.txt || { echo 'FAIL: output.txt missing'; exit 1; }",
            "grep -q ready output.txt || { printf 'FAIL: ready marker missing\\n' >&2; exit 1; }",
            "test -s output.txt || { echo 'FAIL: output.txt missing' >&2; exit 1; } >/dev/null",
        ):
            with self.subTest(check=check):
                self.assertFalse(check_may_fail_silently(check))


class CanonicalCollisionTests(unittest.TestCase):
    def test_absolute_aliases_collide_after_canonical_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workdir = root / "work"
            alias = workdir / "exports" / ".." / "shared.patch"
            canonical = workdir / "shared.patch"
            manifest = Manifest.from_obj(
                manifest_obj(
                    root,
                    [
                        task_obj("one", expect_files=[str(alias)]),
                        task_obj("two", expect_files=[str(canonical)]),
                    ],
                )
            )
            findings = lint_manifest(manifest)
            self.assertIn(
                f"manifest: write collision on {canonical.resolve()}: listed by one, two.",
                findings,
            )

    def test_distinct_canonical_outputs_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workdir = root / "work"
            manifest = Manifest.from_obj(
                manifest_obj(
                    root,
                    [
                        task_obj("one", expect_files=[str(workdir / "one.patch")]),
                        task_obj("two", expect_files=[str(workdir / "two.patch")]),
                    ],
                )
            )
            self.assertFalse(any("write collision" in item for item in lint_manifest(manifest)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
