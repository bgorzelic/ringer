#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = ROOT / "templates" / "fix-swarm" / "checks" / "fix-swarm.py"


VALID_FIX_SUMMARY = """# Fix Summary

## Summary
Patched the login handler to parameterize the SQL query.

## Files Changed
- app/auth.py: use parameterized queries

## Verification
Ran the test suite; all tests passed.

## Assumptions
- None.
"""


class FixSwarmCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        self.repo = root / "repo"
        self.repo.mkdir()
        self._run_git(["init", "-q"])
        self._run_git(["config", "user.email", "test@example.com"])
        self._run_git(["config", "user.name", "Test"])

        self.owned_file = self.repo / "app" / "auth.py"
        self.owned_file.parent.mkdir(parents=True)
        self.owned_file.write_text("def login():\n    pass\n", encoding="utf-8")
        self._run_git(["add", "-A"])
        self._run_git(["commit", "-q", "-m", "initial"])

        export_dir = root / "exports"
        export_dir.mkdir()
        self.patch_path = export_dir / "fix.patch"
        self.exported_summary_path = export_dir / "fix-summary.exported.md"

    def _run_git(self, args: list[str]) -> None:
        result = subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def write_summary(self, body: str) -> None:
        (self.repo / "fix-summary.md").write_text(body, encoding="utf-8")

    def modify_owned_file(self) -> None:
        self.owned_file.write_text("def login():\n    return authenticate()\n", encoding="utf-8")

    def run_check(
        self, verify_command: str = "true", owned_files: str = "app/auth.py"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CHECK_PATH),
                "--verify-command",
                verify_command,
                "--patch",
                str(self.patch_path),
                "--summary",
                "fix-summary.md",
                "--exported-summary",
                str(self.exported_summary_path),
                "--owned-files",
                owned_files,
            ],
            cwd=self.repo,
            text=True,
            capture_output=True,
        )

    def test_valid_contract_passes_and_publishes_both(self) -> None:
        self.write_summary(VALID_FIX_SUMMARY)
        self.modify_owned_file()

        result = self.run_check()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.patch_path.is_file())
        self.assertTrue(self.exported_summary_path.is_file())
        patch_content = self.patch_path.read_text(encoding="utf-8")
        self.assertIn("app/auth.py", patch_content)
        self.assertNotIn("fix-summary.md", patch_content)
        self.assertEqual(VALID_FIX_SUMMARY, self.exported_summary_path.read_text(encoding="utf-8"))

    def test_empty_verification_body_fails(self) -> None:
        summary = VALID_FIX_SUMMARY.replace("Ran the test suite; all tests passed.\n", "")
        self.write_summary(summary)
        self.modify_owned_file()

        result = self.run_check()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("empty_summary_section", result.stdout)
        self.assertIn("Verification", result.stdout)
        self.assertFalse(self.patch_path.exists())
        self.assertFalse(self.exported_summary_path.exists())

    def test_failed_verification_does_not_publish(self) -> None:
        sentinel_patch = "sentinel patch\n"
        sentinel_summary = "sentinel summary\n"
        self.patch_path.write_text(sentinel_patch, encoding="utf-8")
        self.exported_summary_path.write_text(sentinel_summary, encoding="utf-8")

        self.write_summary(VALID_FIX_SUMMARY)
        self.modify_owned_file()

        result = self.run_check(verify_command="false")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("verify_command_failed", result.stdout)
        self.assertEqual(sentinel_patch, self.patch_path.read_text(encoding="utf-8"))
        self.assertEqual(sentinel_summary, self.exported_summary_path.read_text(encoding="utf-8"))

    def test_ownership_escape_does_not_publish(self) -> None:
        sentinel_patch = "sentinel patch\n"
        sentinel_summary = "sentinel summary\n"
        self.patch_path.write_text(sentinel_patch, encoding="utf-8")
        self.exported_summary_path.write_text(sentinel_summary, encoding="utf-8")

        self.write_summary(VALID_FIX_SUMMARY)
        (self.repo / "unowned.txt").write_text("sneaky\n", encoding="utf-8")

        result = self.run_check(owned_files="app/auth.py")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside_owned_files", result.stdout)
        self.assertEqual(sentinel_patch, self.patch_path.read_text(encoding="utf-8"))
        self.assertEqual(sentinel_summary, self.exported_summary_path.read_text(encoding="utf-8"))

    def test_missing_summary_file_fails_and_does_not_publish(self) -> None:
        self.modify_owned_file()

        result = self.run_check()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing_summary", result.stdout)
        self.assertFalse(self.patch_path.exists())
        self.assertFalse(self.exported_summary_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
