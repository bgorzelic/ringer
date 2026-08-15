#!/usr/bin/env python3
"""Worker process environment and executable preflight hardening."""
from __future__ import annotations

import json
import os
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
)

LONG_SPEC = (
    "Run the configured test worker in the isolated task directory and leave its "
    "machine-readable environment observation for verification."
)
GOOD_CHECK = (
    "test -s child-env.json || "
    "{ echo 'FAIL: child-env.json was not written'; exit 1; }"
)
CHILD_SCRIPT = (
    "import json, os, pathlib, sys; "
    "payload = {"
    "'route': os.environ.get('RINGER_TEST_ROUTE'), "
    "'sentinel_present': 'RINGER_SENTINEL_CREDENTIAL' in os.environ}; "
    "pathlib.Path(sys.argv[1], 'child-env.json').write_text("
    "json.dumps(payload), encoding='utf-8')"
)


class WorkerEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_spawn_strips_sentinel_and_preserves_allowed_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = EngineConfig(
                name="test-worker",
                bin=sys.executable,
                args_template=("-c", CHILD_SCRIPT, "{taskdir}"),
                full_access_args=(),
                sandbox_args=(),
                token_regex=None,
                env_allowlist=("RINGER_TEST_ROUTE",),
                preflight_executables=(sys.executable,),
            )
            config = AppConfig(
                path=None,
                identity_default=None,
                state_dir=root / "state",
                dashboard_port_base=8787,
                hud_port=8700,
                hud_app_path=None,
                allow_full_access=False,
                eval=EvalConfig(backend="jsonl", jsonl_path=root / "eval.jsonl"),
                engines={"test-worker": engine},
                artifact=ArtifactConfig(
                    enabled=False,
                    out_template=str(root / "live.html"),
                    report_template=str(root / "report.html"),
                    index_out=root / "index.html",
                ),
            )
            manifest = Manifest.from_obj(
                {
                    "run_name": "runtime-hardening-test",
                    "workdir": str(root / "work"),
                    "tasks": [
                        {
                            "key": "inspect-environment",
                            "spec": LONG_SPEC,
                            "check": GOOD_CHECK,
                            "engine": "test-worker",
                            "expect_files": ["child-env.json"],
                            "verified": "child process reports only the declared route variable",
                        }
                    ],
                }
            )
            runner = RingerRunner(
                manifest,
                config=config,
                identity="runtime-test",
                dashboard_enabled=False,
            )
            self.addCleanup(runner.logger.close)
            runtime = runner.runtimes[0]
            runtime.taskdir.mkdir(parents=True)

            with patch.dict(
                os.environ,
                {
                    "RINGER_TEST_ROUTE": "non-secret-test-route",
                    "RINGER_SENTINEL_CREDENTIAL": "parent-only-sentinel",
                },
            ):
                result = await runner._run_worker(runtime, runtime.task.spec, attempt=1)

            self.assertEqual(0, result.returncode)
            observation = json.loads(
                (runtime.taskdir / "child-env.json").read_text(encoding="utf-8")
            )
            self.assertEqual("non-secret-test-route", observation["route"])
            self.assertIs(observation["sentinel_present"], False)

            worker_log = runtime.log_path.read_text(encoding="utf-8")
            self.assertNotIn("non-secret-test-route", worker_log)
            self.assertNotIn("parent-only-sentinel", worker_log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
