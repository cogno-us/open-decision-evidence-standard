"""Canonicalization profiles, dispatched by declared identifier.

Two profiles exist and neither is an alias of the other:

* ``json-sort-keys-compact-utf8-no-nan`` is the legacy profile. It is ``common.canonical_bytes`` unchanged; every historical digest is
  computed with it and stays valid.
* ``rfc8785-jcs`` is RFC 8785 (JSON Canonicalization Scheme) over a restricted value domain (below).

A digest is only meaningful together with the identifier that was used to compute it. Unknown identifiers are refused here, never
mapped to a default.

Permitted value domain for ``rfc8785-jcs`` (anything else raises ``ValueError``):

* ``null``, booleans, strings, arrays (lists) and objects (dicts with string keys). Tuples, bytes, sets and other types are refused.
* Strings and member names must be valid Unicode scalar sequences: a lone surrogate is refused. Text input must be UTF-8 without a
  byte order mark.
* Object member names must be unique. A parsed document with a duplicate name (after unescaping) is refused.
* Integers are accepted only inside the exact IEEE 754 binary64 range, -(2**53 - 1) to 2**53 - 1. Larger integers are refused
  rather than rounded, because implementations that parse numbers as binary64 would disagree on the value.
* Floats must be finite. They are serialized with the ECMAScript number-to-string rules RFC 8785 requires: ``5.0`` becomes ``5``,
  ``1e-7`` stays ``1e-7``, ``1e21`` becomes ``1e+21`` and negative zero becomes ``0``. NaN and the infinities are refused, as are
  number literals that overflow to infinity.
* Nesting deeper than ``JCS_MAX_DEPTH`` is refused.
"""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

from .common import CANONICALIZATION_PROFILE as LEGACY_CANONICALIZATION_PROFILE
from .common import canonical_bytes as _legacy_canonical_bytes
from .common import sha256 as _legacy_sha256

JCS_CANONICALIZATION_PROFILE = "rfc8785-jcs"
SUPPORTED_CANONICALIZATION_PROFILES = (LEGACY_CANONICALIZATION_PROFILE, JCS_CANONICALIZATION_PROFILE)
JCS_MAX_INTEGER = 2**53 - 1
JCS_MAX_DEPTH = 64


class UnsupportedCanonicalization(ValueError):
    """The declared canonicalization identifier is not one this implementation supports."""


def _number(value: float) -> str:
    """ECMAScript Number::toString for a finite binary64 value (RFC 8785, section 3.2.2.3)."""
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    digits, exponent = Decimal(repr(abs(value))).as_tuple()[1:]
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    text = "".join(map(str, digits))
    k = len(text)
    n = k + exponent
    if k <= n <= 21:
        body = text + "0" * (n - k)
    elif 0 < n <= 21:
        body = text[:n] + "." + text[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + text
    else:
        e = n - 1
        mantissa = text[0] if k == 1 else text[0] + "." + text[1:]
        body = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


_ESCAPES = {0x22: '\\"', 0x5C: "\\\\", 0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r"}


def _string(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("string is not valid Unicode (lone surrogate)") from None
    out = []
    for char in value:
        code = ord(char)
        if code in _ESCAPES:
            out.append(_ESCAPES[code])
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _serialize(value: Any, depth: int) -> str:
    if depth > JCS_MAX_DEPTH:
        raise ValueError("nesting exceeds the supported depth")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int):
        if abs(value) > JCS_MAX_INTEGER:
            raise ValueError("integer outside the exact binary64 range is not supported")
        return str(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number is not JSON")
        return _number(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item, depth + 1) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise ValueError("object member names must be strings")
        names = sorted(value, key=lambda name: name.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(_string(name) + ":" + _serialize(value[name], depth + 1) for name in names) + "}"
    raise ValueError(f"value of type {type(value).__name__} is not supported")


def jcs_bytes(value: Any) -> bytes:
    """RFC 8785 bytes of a parsed JSON value, within the permitted domain described in the module docstring."""
    return _serialize(value, 0).encode("utf-8")


def _refuse_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate member name in JSON object")
        seen[key] = value
    return seen


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not JSON")


def _parse_float(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("number outside the finite range")
    return number


def _parse_int(text: str) -> int:
    if len(text) > 17:  # cheap bound before int(); 2**53 - 1 has 16 digits
        digits = text.lstrip("-").lstrip("0")
        if len(digits) > 16:
            raise ValueError("integer outside the exact binary64 range is not supported")
    number = int(text)
    if abs(number) > JCS_MAX_INTEGER:
        raise ValueError("integer outside the exact binary64 range is not supported")
    return number


def _check_depth(value: Any) -> None:
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, (list, dict)):
            if depth > JCS_MAX_DEPTH:
                raise ValueError("nesting exceeds the supported depth")
            stack.extend((child, depth + 1) for child in (item.values() if isinstance(item, dict) else item))


def jcs_loads(data: str | bytes) -> Any:
    """Strictly parse JSON text for JCS: UTF-8 without BOM, unique member names, finite numbers inside the permitted domain."""
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("input is not valid UTF-8") from None
    else:
        text = data
    if text.startswith("﻿"):
        raise ValueError("a byte order mark is not permitted")
    try:
        value = json.loads(text, object_pairs_hook=_refuse_duplicates, parse_constant=_refuse_constant,
                           parse_float=_parse_float, parse_int=_parse_int)
    except RecursionError:
        raise ValueError("nesting exceeds the supported depth") from None
    _check_depth(value)
    return value


def canonical_bytes_for(identifier: Any, value: Any) -> bytes:
    """Canonical bytes under the declared identifier; an unknown or non-string identifier raises ``UnsupportedCanonicalization``."""
    if identifier == LEGACY_CANONICALIZATION_PROFILE and isinstance(identifier, str):
        return _legacy_canonical_bytes(value)
    if identifier == JCS_CANONICALIZATION_PROFILE and isinstance(identifier, str):
        return jcs_bytes(value)
    raise UnsupportedCanonicalization(f"unsupported canonicalization identifier {identifier!r}")


def digest_for(identifier: Any, value: Any) -> str:
    """``sha256:<hex>`` over the canonical bytes under the declared identifier (same digest convention for both profiles)."""
    if identifier == LEGACY_CANONICALIZATION_PROFILE and isinstance(identifier, str):
        return _legacy_sha256(value)
    return "sha256:" + hashlib.sha256(canonical_bytes_for(identifier, value)).hexdigest()
