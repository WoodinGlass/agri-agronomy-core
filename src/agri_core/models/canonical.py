"""Deterministic JSON encoding used by dictionary and pack hashing."""

from __future__ import annotations

import json
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
