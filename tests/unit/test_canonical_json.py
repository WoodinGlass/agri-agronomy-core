"""canonical_json: golden vectors and invariance."""

from __future__ import annotations

import math

import pytest

from agri_core.models.canonical import canonical_json

pytestmark = pytest.mark.unit


def test_empty_object() -> None:
    assert canonical_json({}) == b"{}"


def test_empty_array() -> None:
    assert canonical_json([]) == b"[]"


def test_golden_nested() -> None:
    obj = {"b": 2, "a": 1, "c": [3, 1, 2]}
    assert canonical_json(obj) == b'{"a":1,"b":2,"c":[3,1,2]}'


def test_sorted_keys() -> None:
    a = canonical_json({"z": 1, "a": 2, "m": 3})
    b = canonical_json({"a": 2, "m": 3, "z": 1})
    assert a == b


def test_no_whitespace() -> None:
    out = canonical_json({"a": [1, 2], "b": {"c": 3}})
    assert b" " not in out
    assert b"\n" not in out


def test_utf8_encoding() -> None:
    out = canonical_json({"n": "tomato", "id": "ID"})
    assert b"tomato" in out


def test_float_representation() -> None:
    out = canonical_json({"v": 1.5})
    assert out == b'{"v":1.5}'


def test_negative_zero_normalized_by_json() -> None:
    a = canonical_json({"v": 0.0})
    b = canonical_json({"v": -0.0})
    assert a == b


def test_nan_rejected() -> None:
    with pytest.raises(ValueError, match="not JSON compliant"):
        canonical_json({"v": math.nan})


def test_infinity_rejected() -> None:
    with pytest.raises(ValueError, match="not JSON compliant"):
        canonical_json({"v": math.inf})


def test_negative_infinity_rejected() -> None:
    with pytest.raises(ValueError, match="not JSON compliant"):
        canonical_json({"v": -math.inf})


def test_deterministic_repeat() -> None:
    obj = {"nested": {"x": [1, 2, 3]}, "y": "v"}
    assert canonical_json(obj) == canonical_json(obj)
