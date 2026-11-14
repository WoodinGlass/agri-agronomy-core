"""Deterministic JSON encoding used by dictionary and pack hashing.

Two canonicalizers live in this module:

- ``canonical_json`` (legacy): pre-RFC 8785 form. Uses Python's
  ``json.dumps`` with sorted keys, compact separators, and only the
  ``-0.0`` to ``0.0`` normalization. Byte-stable across platforms and
  Python versions, but NOT RFC 8785 compliant (float repr like ``1.0``
  -> ``"1.0"``, exponent ``1e-07``, Unicode code-point key sort instead
  of UTF-16).

- ``canonical_json_rfc8785``: full RFC 8785 (JCS) compliance. Numbers
  per ECMA-262 section 7.1.12.1 (``1.0`` -> ``"1"``, ``1e-07`` ->
  ``"1e-7"``, ``-0.0`` -> ``"0"``), UTF-16 code-unit key sort, minimal
  string escaping. See ADR-020.

Callers select via the ``hash_alg`` argument on ``hash_pack_files``
and ``compute_pack_hash``."""

from __future__ import annotations

import json
import math
from typing import Any


def _normalize(obj: Any) -> Any:
    """Recursively normalize values that would otherwise produce different bytes.

    Only one normalization is applied today: ``-0.0`` becomes ``0.0``.
    Python's ``json.dumps`` preserves the sign of negative zero, so without
    this step the same mathematical value would produce different hash input.
    RFC 8785 (JCS) requires ``-0`` to be serialized as ``0``.

    Containers are rebuilt (dict, list, tuple). Pydantic models should be
    serialized to ``mode="json"`` before calling ``canonical_json``; this
    function does not know about them.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float) and obj == 0.0:
        return 0.0
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_normalize(v) for v in obj)
    return obj


def canonical_json(obj: Any) -> bytes:
    """Return canonical JSON bytes for a Python object.

    Sorted keys, no whitespace, UTF-8 encoding, no trailing newline. Two equal
    objects always produce equal bytes. Negative zero (``-0.0``) is normalized
    to ``0.0`` because Python's ``json`` preserves the sign but RFC 8785 (JCS)
    requires the canonical form to serialize ``-0`` as ``0``. Floats must be
    finite; ``json.dumps(..., allow_nan=False)`` rejects NaN and infinity.
    """
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


# ============================================================================
# RFC 8785 (JCS) canonical JSON
# ============================================================================
# See ADR-020. This is the production canonicalizer for packs that
# declare ``hash_alg = "rfc8785"``. The legacy ``canonical_json`` above
# remains for ``hash_alg = "pre-rfc8785"`` (default for old packs).
#
# Cross-checked against Node.js ``JSON.stringify`` on 101 boundary cases
# (see ``tests/vectors/canonical_rfc8785.json`` and ``ORACLE.md``).


def _utf16_sort_key(s: str) -> bytes:
    """Sort key for UTF-16 code unit comparison (RFC 8785 section 3.2.3)."""
    try:
        return s.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise ValueError(f"RFC 8785: string contains lone surrogate: {exc}") from exc


def _serialize_string(s: str) -> str:
    """Escape a string per RFC 8785 section 3.2.2.2.

    Uses Python's ``json.dumps(..., ensure_ascii=False)`` which already
    matches the RFC: quote and backslash escaped, control chars U+0000
    through U+001F as 2-char sequences for the known set and ``\\u00XX``
    (lowercase) for the rest, non-ASCII literal UTF-8.
    """
    try:
        s.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"RFC 8785: string contains lone surrogate: {exc}") from exc
    return json.dumps(s, ensure_ascii=False)


def _serialize_float(f: float) -> str:
    """ECMA-262 section 7.1.12.1 Number.prototype.toString (RFC 8785 section 3.2.2.3)."""
    if math.isnan(f):
        raise ValueError("RFC 8785: NaN is not valid JSON")
    if math.isinf(f):
        raise ValueError("RFC 8785: Infinity is not valid JSON")
    if f == 0.0:
        return "0"

    s = repr(f)
    sign = ""
    if s.startswith("-"):
        sign = "-"
        s = s[1:]

    if "e" in s.lower():
        mant, exp_str = s.lower().split("e")
        exp = int(exp_str)
    else:
        mant = s
        exp = 0

    if "." in mant:
        int_part, frac_part = mant.split(".")
    else:
        int_part = mant
        frac_part = ""

    if int_part == "":
        int_part = "0"

    D = int(int_part) * (10 ** len(frac_part)) + (int(frac_part) if frac_part else 0)
    efexp = exp - len(frac_part)

    if D == 0:
        return "0"

    D_str = str(D)
    stripped = D_str.rstrip("0")
    zeros = len(D_str) - len(stripped)
    k = len(stripped)
    efexp_adj = efexp + zeros
    n = k + efexp_adj

    if 0 < n <= 21:
        if n >= k:
            return sign + stripped + "0" * (n - k)
        return sign + stripped[:n] + "." + stripped[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + stripped

    exp_val = n - 1
    mantissa = stripped if k == 1 else stripped[0] + "." + stripped[1:]
    exp_sign = "+" if exp_val >= 0 else "-"
    return sign + mantissa + "e" + exp_sign + str(abs(exp_val))


def _serialize(obj: Any) -> str:
    """Recursive RFC 8785 serializer (returns str; caller encodes to UTF-8)."""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        # bool is subclass of int; handled above.
        # RFC 8785 numbers serialize as ECMAScript Number.toString.
        # Integers exact as IEEE 754 double format via _serialize_float;
        # integers that lose precision are rejected.
        if abs(obj) >= 2**53:
            try:
                f = float(obj)
            except OverflowError as exc:
                raise ValueError(
                    f"RFC 8785: integer magnitude too large for double: {obj}"
                ) from exc
            if int(f) != obj:
                raise ValueError(f"RFC 8785: integer {obj} loses precision as IEEE 754 double")
            return _serialize_float(f)
        return str(obj)
    if isinstance(obj, float):
        return _serialize_float(obj)
    if isinstance(obj, str):
        return _serialize_string(obj)
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_serialize(x) for x in obj) + "]"
    if isinstance(obj, dict):
        for k in obj:
            if not isinstance(k, str):
                raise TypeError(f"RFC 8785: object keys must be str, got {type(k).__name__}")
        sorted_keys = sorted(obj.keys(), key=_utf16_sort_key)
        items = [_serialize_string(k) + ":" + _serialize(obj[k]) for k in sorted_keys]
        return "{" + ",".join(items) + "}"
    raise TypeError(f"RFC 8785: object of type {type(obj).__name__} is not JSON serializable")


def canonical_json_rfc8785(obj: Any) -> bytes:
    """Return RFC 8785 (JCS) canonical JSON bytes for a Python object.

    Implements:

    - Number serialization per ECMA-262 section 7.1.12.1
      (``1.0`` -> ``"1"``, ``1e-7`` -> ``"1e-7"``, ``-0.0`` -> ``"0"``).
    - Object key sort by UTF-16 code units (not code points).
    - Minimal string escaping (control chars per section 3.2.2.2,
      non-ASCII literal).
    - Reject: NaN, Infinity, integers above ``2^53 - 1``, lone surrogates.

    Cross-checked against Node.js ``JSON.stringify`` on 101 boundary
    cases (see ``tests/vectors/canonical_rfc8785.json``).
    """
    return _serialize(obj).encode("utf-8")
