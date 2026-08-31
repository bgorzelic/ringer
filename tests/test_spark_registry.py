#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ringer import load_model_identity_registry  # noqa: E402


class SparkRegistryTests(unittest.TestCase):
    def test_spark_resolves_to_codex_subscription_identity(self) -> None:
        identity = load_model_identity_registry().resolve(
            "codex", "gpt-5.3-codex-spark"
        )

        self.assertEqual("GPT-5.3 Codex Spark", identity.model_display)
        self.assertEqual("Codex CLI", identity.harness)
        self.assertEqual("OAuth plan", identity.access)
        self.assertEqual("verified", identity.confidence)
        self.assertIn("spark-subscription-preflight.md", identity.source)


if __name__ == "__main__":
    unittest.main()
