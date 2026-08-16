#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import manifest_validation  # noqa: E402
from manifest_validation import (  # noqa: E402
    ManifestSchemaError,
    load_manifest_schema,
    validate_manifest_data,
)
from ringer import Manifest  # noqa: E402


def valid_manifest() -> dict[str, object]:
    return {
        "run_name": "schema-test",
        "workdir": "/tmp/ringer-schema-test",
        "max_parallel": 1,
        "tasks": [
            {
                "key": "worker",
                "spec": "Create a scoped artifact and record the evidence needed to verify it.",
                "check": "test -s output.txt || { echo 'FAIL: output missing'; exit 1; }",
                "expect_files": ["output.txt"],
                "timeout_s": 60,
                "full_access": False,
                "engine_args": [],
                "verified": "output.txt exists and is not empty",
            }
        ],
    }


class ManifestSchemaTests(unittest.TestCase):
    def validate_with_fallback(self, data: object) -> str:
        with mock.patch.object(
            manifest_validation,
            "_load_draft202012_validator",
            return_value=None,
        ):
            return validate_manifest_data(data)

    def test_schema_declares_draft_2020_12(self) -> None:
        schema = load_manifest_schema()
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(manifest_validation._MANIFEST_KEYS, set(schema["properties"]))
        self.assertEqual(
            manifest_validation._TASK_KEYS,
            set(schema["$defs"]["task"]["properties"]),
        )

    def test_stdlib_fallback_accepts_valid_manifest(self) -> None:
        self.assertEqual("stdlib", self.validate_with_fallback(valid_manifest()))

    def test_stdlib_fallback_rejects_unknown_task_property(self) -> None:
        data = valid_manifest()
        task = data["tasks"][0]  # type: ignore[index]
        task["timeot_s"] = 60  # type: ignore[index]
        with self.assertRaisesRegex(
            ManifestSchemaError,
            r"manifest schema validation failed at \$\.tasks\[0\]: unknown property: timeot_s",
        ):
            self.validate_with_fallback(data)

    def test_stdlib_fallback_rejects_boolean_as_integer(self) -> None:
        data = valid_manifest()
        data["max_parallel"] = True
        with self.assertRaisesRegex(ManifestSchemaError, r"at \$\.max_parallel: expected integer"):
            self.validate_with_fallback(data)

    def test_stdlib_fallback_accepts_json_integer_float(self) -> None:
        data = valid_manifest()
        data["max_parallel"] = 1.0
        self.assertEqual("stdlib", self.validate_with_fallback(data))

    def test_stdlib_fallback_requires_repo_for_worktrees(self) -> None:
        data = valid_manifest()
        data["worktrees"] = True
        with self.assertRaisesRegex(ManifestSchemaError, r"at \$: required property missing: repo"):
            self.validate_with_fallback(data)

    def test_manifest_from_path_validates_before_parsing(self) -> None:
        data = valid_manifest()
        data["unexpected"] = "value"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with mock.patch.object(
                manifest_validation,
                "_load_draft202012_validator",
                return_value=None,
            ):
                with self.assertRaisesRegex(
                    ManifestSchemaError,
                    r"at \$: unknown property: unexpected",
                ):
                    Manifest.from_path(path)

    def test_incomplete_optional_installation_does_not_fall_back(self) -> None:
        missing_dependency = ModuleNotFoundError(
            "No module named 'referencing'",
            name="referencing",
        )
        with mock.patch.object(
            manifest_validation.importlib,
            "import_module",
            side_effect=missing_dependency,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "optional jsonschema installation is incomplete",
            ):
                validate_manifest_data(valid_manifest())

    @unittest.skipUnless(
        manifest_validation._load_draft202012_validator() is not None,
        "optional jsonschema dependency is not installed",
    )
    def test_jsonschema_backend_uses_draft_2020_12(self) -> None:
        self.assertEqual("jsonschema", validate_manifest_data(valid_manifest()))
        data = valid_manifest()
        data["tasks"] = []
        with self.assertRaisesRegex(
            ManifestSchemaError,
            r"at \$\.tasks: must contain at least 1 item",
        ):
            validate_manifest_data(data)


if __name__ == "__main__":
    unittest.main()
