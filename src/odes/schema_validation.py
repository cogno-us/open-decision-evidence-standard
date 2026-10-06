from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .common import load_json


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def schema_path() -> Path:
    return repository_root() / "schema" / "pder-v0.1.schema.json"


def load_schema() -> dict[str, Any]:
    return load_json(schema_path())


def schema_errors(record: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(record), key=lambda item: item.path)]


def validate_record(record: dict[str, Any]) -> None:
    errors = schema_errors(record)
    if errors:
        raise ValueError("ODES schema validation failed: " + "; ".join(errors))
