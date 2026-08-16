from __future__ import annotations

import importlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn


MANIFEST_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "manifest.schema.json"

_MANIFEST_KEYS = frozenset(
    {
        "run_name",
        "workdir",
        "max_parallel",
        "worktrees",
        "repo",
        "external_expect_roots",
        "tasks",
    }
)
_TASK_KEYS = frozenset(
    {
        "key",
        "spec",
        "check",
        "engine",
        "expect_files",
        "timeout_s",
        "full_access",
        "engine_args",
        "verified",
        "model",
        "task_type",
    }
)


class ManifestSchemaError(ValueError):
    """A manifest does not satisfy Ringer's published JSON Schema."""


def load_manifest_schema() -> dict[str, Any]:
    """Load the bundled Draft 2020-12 schema without network access."""
    try:
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load manifest schema: {MANIFEST_SCHEMA_PATH}") from exc
    if not isinstance(schema, dict):
        raise RuntimeError(f"manifest schema root must be an object: {MANIFEST_SCHEMA_PATH}")
    return schema


def _load_draft202012_validator() -> type[Any] | None:
    """Return jsonschema's validator, or None only when jsonschema is absent."""
    try:
        module = importlib.import_module("jsonschema")
    except ModuleNotFoundError as exc:
        if exc.name == "jsonschema":
            return None
        raise RuntimeError("the optional jsonschema installation is incomplete") from exc
    validator = getattr(module, "Draft202012Validator", None)
    if validator is None:
        raise RuntimeError("the installed jsonschema package lacks Draft202012Validator")
    return validator


def validate_manifest_data(data: Any) -> str:
    """Validate raw manifest data and return the backend used.

    python-jsonschema is optional and imported only when a manifest is loaded.
    Without it, the standard-library validator enforces Ringer's manifest
    contract so the default installation remains functional.
    """
    schema = load_manifest_schema()
    validator_class = _load_draft202012_validator()
    if validator_class is None:
        _validate_with_stdlib(data)
        return "stdlib"

    validator_class.check_schema(schema)
    validator = validator_class(schema)
    errors = sorted(validator.iter_errors(data), key=_jsonschema_error_sort_key)
    if errors:
        error = errors[0]
        path = _json_path(error.absolute_path)
        raise ManifestSchemaError(
            f"manifest schema validation failed at {path}: {_describe_jsonschema_error(error)}"
        )
    return "jsonschema"


def _jsonschema_error_sort_key(error: Any) -> tuple[str, str]:
    return (_json_path(error.absolute_path), str(error.validator))


def _json_path(parts: Sequence[Any]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _describe_jsonschema_error(error: Any) -> str:
    """Describe the rule failure without echoing manifest values."""
    if error.validator == "required":
        missing = sorted(set(error.validator_value) - set(error.instance))
        return f"required property missing: {missing[0]}"
    if error.validator == "additionalProperties":
        allowed = set(error.schema.get("properties", {}))
        unknown = sorted(set(error.instance) - allowed)
        return f"unknown property: {unknown[0]}"
    if error.validator == "type":
        return f"expected {error.validator_value}"
    if error.validator == "minLength":
        return "must not be empty"
    if error.validator == "minItems":
        return f"must contain at least {error.validator_value} item(s)"
    if error.validator == "minimum":
        return f"must be at least {error.validator_value}"
    return f"failed {error.validator} rule"


def _validate_with_stdlib(data: Any) -> None:
    root = _require_mapping(data, "$")
    _reject_unknown(root, _MANIFEST_KEYS, "$")
    _require_properties(root, ("run_name", "workdir", "tasks"), "$")
    _require_nonempty_string(root["run_name"], "$.run_name")
    _require_nonempty_string(root["workdir"], "$.workdir")

    if "max_parallel" in root:
        _require_positive_integer(root["max_parallel"], "$.max_parallel")
    if "worktrees" in root:
        _require_boolean(root["worktrees"], "$.worktrees")
    if "repo" in root:
        _require_nonempty_string(root["repo"], "$.repo")
    if root.get("worktrees") is True and "repo" not in root:
        _fail("$", "required property missing: repo")
    if "external_expect_roots" in root:
        roots = _require_array(root["external_expect_roots"], "$.external_expect_roots")
        for index, item in enumerate(roots):
            _require_nonempty_string(item, f"$.external_expect_roots[{index}]")

    tasks = _require_array(root["tasks"], "$.tasks")
    if not tasks:
        _fail("$.tasks", "must contain at least 1 item(s)")
    for index, item in enumerate(tasks):
        _validate_task(item, index)


def _validate_task(data: Any, index: int) -> None:
    path = f"$.tasks[{index}]"
    task = _require_mapping(data, path)
    _reject_unknown(task, _TASK_KEYS, path)
    _require_properties(task, ("key", "spec", "check"), path)
    for key in ("key", "spec", "check"):
        _require_nonempty_string(task[key], f"{path}.{key}")
    if "engine" in task:
        _require_nonempty_string(task["engine"], f"{path}.engine")
    if "expect_files" in task:
        values = _require_array(task["expect_files"], f"{path}.expect_files")
        for item_index, item in enumerate(values):
            _require_string(item, f"{path}.expect_files[{item_index}]")
    if "timeout_s" in task:
        _require_positive_integer(task["timeout_s"], f"{path}.timeout_s")
    if "full_access" in task:
        _require_boolean(task["full_access"], f"{path}.full_access")
    if "engine_args" in task:
        values = _require_array(task["engine_args"], f"{path}.engine_args")
        for item_index, item in enumerate(values):
            _require_string(item, f"{path}.engine_args[{item_index}]")
    for key in ("verified", "model", "task_type"):
        if key in task:
            _require_string(task[key], f"{path}.{key}")


def _require_mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        _fail(path, "expected object")
    return data


def _require_array(data: Any, path: str) -> Sequence[Any]:
    if not isinstance(data, list):
        _fail(path, "expected array")
    return data


def _require_string(data: Any, path: str) -> None:
    if not isinstance(data, str):
        _fail(path, "expected string")


def _require_nonempty_string(data: Any, path: str) -> None:
    _require_string(data, path)
    if not data:
        _fail(path, "must not be empty")


def _require_positive_integer(data: Any, path: str) -> None:
    is_json_integer = (
        not isinstance(data, bool)
        and isinstance(data, (int, float))
        and (not isinstance(data, float) or data.is_integer())
    )
    if not is_json_integer:
        _fail(path, "expected integer")
    if data < 1:
        _fail(path, "must be at least 1")


def _require_boolean(data: Any, path: str) -> None:
    if not isinstance(data, bool):
        _fail(path, "expected boolean")


def _require_properties(data: Mapping[str, Any], required: Sequence[str], path: str) -> None:
    for name in required:
        if name not in data:
            _fail(path, f"required property missing: {name}")


def _reject_unknown(data: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(path, f"unknown property: {unknown[0]}")


def _fail(path: str, message: str) -> NoReturn:
    raise ManifestSchemaError(f"manifest schema validation failed at {path}: {message}")
