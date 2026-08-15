#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = ROOT / "templates" / "review-swarm" / "checks" / "review-swarm.py"

spec = importlib.util.spec_from_file_location("review_swarm_check", CHECK_PATH)
review_swarm_check = importlib.util.module_from_spec(spec)
sys.modules["review_swarm_check"] = review_swarm_check
spec.loader.exec_module(review_swarm_check)

validate_report = review_swarm_check.validate_report


VALID_FINDING = """### Finding: SQL injection in login handler
Evidence: app/auth.py:42 concatenates user input into a query
Impact: an attacker can bypass authentication
Fix: use parameterized queries
Priority: P0
Confidence: high"""

VALID_REPORT = f"""# Review Report

## Summary
Reviewed the login surface for auth and data-access issues.

## Findings
{VALID_FINDING}

## Clean
- CSRF handling looked correct.

## Assumptions
- Session store config was out of scope.
"""

NO_FINDINGS_REPORT = """# Review Report

## Summary
Reviewed the login surface; nothing to report.

## Findings
No findings for this surface.

## Clean
- Auth, data access, and CSRF handling were all reviewed with no issues.

## Assumptions
- None.
"""


class ReviewSwarmCheckTests(unittest.TestCase):
    def write_report(self, body: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "report.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_valid_report_passes(self) -> None:
        failures = validate_report(self.write_report(VALID_REPORT), "login surface")
        self.assertEqual([], failures, failures)

    def test_no_findings_report_is_valid(self) -> None:
        failures = validate_report(self.write_report(NO_FINDINGS_REPORT), "login surface")
        self.assertEqual([], failures, failures)

    def test_numbered_heading_with_priority_high_yields_both_errors(self) -> None:
        # A prior local-model attempt hid these defects entirely: the checker
        # only ever looked for the exact literal '### Finding:' heading, so a
        # numbered heading like '### Finding 1:' made the whole block invisible
        # and its Priority: High defect never surfaced in the same run.
        report = VALID_REPORT.replace(
            "### Finding: SQL injection in login handler",
            "### Finding 1: SQL injection in login handler",
        ).replace("Priority: P0", "Priority: High")
        failures = validate_report(self.write_report(report), "login surface")
        self.assertTrue(
            any("finding_bad_heading" in item for item in failures),
            f"expected a bad-heading failure, got: {failures}",
        )
        self.assertTrue(
            any("finding_bad_priority" in item for item in failures),
            f"expected a bad-priority failure, got: {failures}",
        )
        # Priority: High must never be silently accepted as a valid P0-P3 value.
        self.assertFalse(any("P0" in item and "priority" not in item.lower() for item in failures))

    def test_multiple_malformed_blocks_yield_all_defects(self) -> None:
        block_one = """1. Finding: missing input validation
Evidence: app/api.py:10 accepts unsanitized input
Impact: downstream crash
Fix: validate input before use
Priority: Critical
Confidence: high"""
        block_two = """#### Finding: stale cache entry
Evidence: app/cache.py:88 never invalidates
Fix: add TTL
Priority: P2
Confidence: maybe"""
        findings_body = f"{block_one}\n\n{block_two}"
        report = VALID_REPORT.replace(VALID_FINDING, findings_body)
        failures = validate_report(self.write_report(report), "login surface")

        block_one_failures = [item for item in failures if "finding 1" in item]
        block_two_failures = [item for item in failures if "finding 2" in item]

        self.assertTrue(any("finding_bad_heading" in item for item in block_one_failures))
        self.assertTrue(any("finding_bad_priority" in item for item in block_one_failures))

        self.assertTrue(any("finding_bad_heading" in item for item in block_two_failures))
        self.assertTrue(any("finding_missing_field" in item and "Impact:" in item for item in block_two_failures))
        self.assertTrue(any("finding_bad_confidence" in item for item in block_two_failures))

    def test_placeholder_surface_fails(self) -> None:
        failures = validate_report(self.write_report(VALID_REPORT), "{{SURFACE_DESCRIPTION}}")
        self.assertTrue(
            any("placeholder_unfilled" in item for item in failures),
            f"expected placeholder failure, got: {failures}",
        )

    def test_word_limit_enforced(self) -> None:
        padding = " padding" * 1250
        report = VALID_REPORT.replace(
            "Reviewed the login surface for auth and data-access issues.",
            f"Reviewed the login surface for auth and data-access issues.{padding}",
        )
        failures = validate_report(self.write_report(report), "login surface")
        self.assertTrue(
            any("too_long" in item for item in failures),
            f"expected too_long failure, got: {failures}",
        )

    def test_missing_report_fails(self) -> None:
        missing_path = Path(tempfile.mkdtemp()) / "does-not-exist.md"
        failures = validate_report(missing_path, "login surface")
        self.assertTrue(any("missing_report" in item for item in failures))


if __name__ == "__main__":
    unittest.main(verbosity=2)
