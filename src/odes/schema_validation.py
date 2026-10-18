from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .common import load_json, parse_instant


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def schema_path() -> Path:
    return repository_root() / "schema" / "pder-v0.1.schema.json"


def load_schema() -> dict[str, Any]:
    return load_json(schema_path())


_INSTANT_FIELDS = (("decision_timestamp",), ("authority", "authority_valid_from"), ("authority", "authority_valid_until"),
                   ("consumption_conditions", "expires_at"), ("status", "revoked_at"))


def _instant_errors(record: Any) -> list[str]:
    """The schema pattern is ECMA-anchored with ``$``; Python's ``re`` lets ``$`` match before a trailing line break, so check that here."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return errors
    for path in _INSTANT_FIELDS:
        value: Any = record
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, str) and parse_instant(value) is None:
            errors.append(f"{'.'.join(path)}: {value!r} is not a record instant (RFC 3339 with an explicit offset)")
    return errors


def schema_errors(record: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    errors = [error.message for error in sorted(validator.iter_errors(record), key=lambda item: item.path)]
    for message in _instant_errors(record):
        if not any(message.split(": ")[1].split(" is not")[0] in e for e in errors):
            errors.append(message)
    return errors


def validate_record(record: dict[str, Any]) -> None:
    errors = schema_errors(record)
    if errors:
        raise ValueError("ODES schema validation failed: " + "; ".join(errors))
