"""RFC 8785 (JCS) canonical JSON tests.

Two layers:

1. ``test_vector_match`` iterates ``tests/vectors/canonical_rfc8785.json``,
   which is generated from Node.js ``JSON.stringify`` on 101 boundary
   inputs. Every vector case must match byte-for-byte.

2. Explicit named tests for behaviors the vector cannot cover (because
   Node normalizes the input during serialization):
   - float 1.0 -> "1" (vector stores int 1, not float 1.0)
   - float -0.0 -> "0" (vector stores int 0)
   - whole-float expansion (1e16 -> "10000000000000000")
   - reject: NaN, Infinity, integers above 2^53 - 1, lone surrogates
   - UTF-16 code-unit key sort (differs from Unicode code-point sort)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from agri_core.models.canonical import canonical_json_rfc8785

pytestmark = pytest.mark.unit

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "canonical_rfc8785.json"
_VECTOR_CASES = json.loads(VECTORS.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# 1. Vector parity with Node oracle
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    _VECTOR_CASES,
    ids=[f"case-{i:03d}" for i in range(len(_VECTOR_CASES))],
)
def test_vector_match(case: dict) -> None:
    """Canonical bytes match Node's JSON.stringify on this input."""
    actual = canonical_json_rfc8785(case["input"])
    expected = case["expected"].encode()
    assert actual == expected, f"case {case['input']!r}"


# ----------------------------------------------------------------------------
# 2. Explicit float cases (vector normalizes input, cannot test these)
# ----------------------------------------------------------------------------


def test_negative_zero() -> None:
    """-0.0 -> b'{"v":0}' (RFC 8785 section 3.2.2.3)."""
    assert canonical_json_rfc8785({"v": -0.0}) == b'{"v":0}'


def test_positive_zero() -> None:
    assert canonical_json_rfc8785({"v": 0.0}) == b'{"v":0}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, b'{"v":1}'),
        (-1.0, b'{"v":-1}'),
        (100.0, b'{"v":100}'),
        (1000.0, b'{"v":1000}'),
        (1.5, b'{"v":1.5}'),
        (-1.5, b'{"v":-1.5}'),
        (0.1, b'{"v":0.1}'),
        (0.0001, b'{"v":0.0001}'),
        (1e-5, b'{"v":0.00001}'),
        (1e-6, b'{"v":0.000001}'),
        (1e-7, b'{"v":1e-7}'),
        (1e-100, b'{"v":1e-100}'),
        (1e15, b'{"v":1000000000000000}'),
        (1e16, b'{"v":10000000000000000}'),
        (1e20, b'{"v":100000000000000000000}'),
        (1e21, b'{"v":1e+21}'),
        (1e100, b'{"v":1e+100}'),
        (5e-324, b'{"v":5e-324}'),
        (1.7976931348623157e308, b'{"v":1.7976931348623157e+308}'),
    ],
)
def test_float_ecma_form(value: float, expected: bytes) -> None:
    """ECMA-262 section 7.1.12.1 float form (RFC 8785 section 3.2.2.3)."""
    assert canonical_json_rfc8785({"v": value}) == expected


# ----------------------------------------------------------------------------
# 3. Rejections
# ----------------------------------------------------------------------------


def test_reject_nan() -> None:
    with pytest.raises(ValueError, match="NaN"):
        canonical_json_rfc8785({"v": math.nan})


def test_reject_pos_inf() -> None:
    with pytest.raises(ValueError, match="Infinity"):
        canonical_json_rfc8785({"v": math.inf})


def test_reject_neg_inf() -> None:
    with pytest.raises(ValueError, match="Infinity"):
        canonical_json_rfc8785({"v": -math.inf})


@pytest.mark.parametrize(
    "n",
    [2**53 + 1, -(2**53) - 1, 10**100, 10**100 + 1],
)
def test_reject_int_loses_precision(n: int) -> None:
    """Integers that lose precision as IEEE 754 double are rejected."""
    with pytest.raises(ValueError, match=r"loses precision"):
        canonical_json_rfc8785({"v": n})


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (2**53, b'{"v":9007199254740992}'),
        (-(2**53), b'{"v":-9007199254740992}'),
        (2**53 - 1, b'{"v":9007199254740991}'),
        (-(2**53) + 1, b'{"v":-9007199254740991}'),
        (10**20, b'{"v":100000000000000000000}'),
        (10**21, b'{"v":1e+21}'),
        (10**22, b'{"v":1e+22}'),
    ],
)
def test_accept_int_exact_as_double(n: int, expected: bytes) -> None:
    """Integers exact as IEEE 754 double are accepted."""
    assert canonical_json_rfc8785({"v": n}) == expected


def test_reject_lone_surrogate_value() -> None:
    with pytest.raises(ValueError, match="lone surrogate"):
        canonical_json_rfc8785({"v": "\ud800"})


def test_reject_lone_surrogate_key() -> None:
    with pytest.raises(ValueError, match="lone surrogate"):
        canonical_json_rfc8785({"\udc00": 1})


def test_reject_non_str_dict_key() -> None:
    with pytest.raises(TypeError, match="object keys must be str"):
        canonical_json_rfc8785({1: 2})  # type: ignore[dict-item]


def test_reject_unsupported_type() -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        canonical_json_rfc8785({"v": b"bytes"})  # type: ignore[dict-item]


# ----------------------------------------------------------------------------
# 4. Structure / invariance
# ----------------------------------------------------------------------------


def test_empty_object() -> None:
    assert canonical_json_rfc8785({}) == b"{}"


def test_empty_array() -> None:
    assert canonical_json_rfc8785([]) == b"[]"


def test_sorted_keys() -> None:
    a = canonical_json_rfc8785({"b": 1, "a": 2})
    b = canonical_json_rfc8785({"a": 2, "b": 1})
    assert a == b == b'{"a":2,"b":1}'


def test_utf16_sort_differs_from_codepoint() -> None:
    """UTF-16 code-unit order differs from Unicode code-point order.

    U+FFFD (BMP, UTF-16 code unit 0xFFFD) vs U+10000 (non-BMP,
    surrogate pair 0xD800 0xDC00). In UTF-16 order, U+10000 < U+FFFD
    because 0xD800 < 0xFFFD. In code-point order, U+FFFD < U+10000.
    """
    out = canonical_json_rfc8785({"\ufffd": 1, "\U00010000": 2})
    # U+10000 sorts first; UTF-8: U+10000 = f0 90 80 80, U+FFFD = ef bf bd
    assert out == b'{"\xf0\x90\x80\x80":2,"\xef\xbf\xbd":1}'


def test_idempotent() -> None:
    cases = [
        {},
        {"b": 1, "a": 2},
        [1, 2, 3],
        {"nested": {"x": [1, 2]}},
        {"v": 1.5},
        {"v": 1e-7},
    ]
    for case in cases:
        first = canonical_json_rfc8785(case)
        parsed = json.loads(first)
        second = canonical_json_rfc8785(parsed)
        assert first == second, f"idempotence failed for {case!r}"


def test_roundtrip() -> None:
    cases = [
        {},
        {"b": 1, "a": 2},
        [1, 2, 3],
        {"nested": {"x": [1, 2]}},
        {"v": 1.5},
    ]
    for case in cases:
        assert json.loads(canonical_json_rfc8785(case)) == case


# ----------------------------------------------------------------------------
# 5. String escaping
# ----------------------------------------------------------------------------


def test_control_chars_escaped() -> None:
    assert canonical_json_rfc8785({"v": "\x00"}) == b'{"v":"\\u0000"}'
    assert canonical_json_rfc8785({"v": "\x01"}) == b'{"v":"\\u0001"}'
    assert canonical_json_rfc8785({"v": "\x1f"}) == b'{"v":"\\u001f"}'


def test_quote_and_backslash_escaped() -> None:
    assert canonical_json_rfc8785({"v": '"'}) == b'{"v":"\\""}'
    assert canonical_json_rfc8785({"v": "\\"}) == b'{"v":"\\\\"}'


def test_non_ascii_literal() -> None:
    assert canonical_json_rfc8785({"v": "caf\u00e9"}) == '{"v":"caf\u00e9"}'.encode()
    assert canonical_json_rfc8785({"v": "\u4f60\u597d"}) == '{"v":"\u4f60\u597d"}'.encode()


def test_surrogate_pair_emoji() -> None:
    assert canonical_json_rfc8785({"v": "\U0001f600"}) == '{"v":"\U0001f600"}'.encode()
