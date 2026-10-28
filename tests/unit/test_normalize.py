"""Unit tests for pack/normalize.py (M8-1)."""

from __future__ import annotations

import pytest

from agri_core.pack.normalize import normalize_name, normalize_scope_value

pytestmark = pytest.mark.unit

# Fullwidth A, B, C (U+FF21..U+FF23) and digits (U+FF11..U+FF13), written
# as escapes so ruff's RUF001 ambiguity check is not tripped by the
# source file itself. The runtime value is the fullwidth character.
_FW_ABC = "\uff21\uff22\uff23"
_FW_123 = "\uff11\uff12\uff13"
_HYBRID = "\u00d7"  # MULTIPLICATION SIGN


# ---- normalize_name --------------------------------------------------------


def test_empty_returns_empty() -> None:
    assert normalize_name("") == ""


def test_ascii_passthrough() -> None:
    assert normalize_name("Testus annualis") == "testus annualis"


def test_casefold_uppercase() -> None:
    assert normalize_name("TESTUS ANNUALIS") == "testus annualis"


def test_casefold_eszett() -> None:
    assert normalize_name("Stra\u00dfe") == "strasse"


@pytest.mark.parametrize(
    ("input_s", "expected"),
    [
        ("n\u0303", "\u00f1"),
        ("\u00f1", "\u00f1"),
        ("e\u0301", "\u00e9"),
        ("\u00e9", "\u00e9"),
    ],
)
def test_nfkc_decomposes(input_s: str, expected: str) -> None:
    assert normalize_name(input_s) == expected


@pytest.mark.parametrize(
    ("input_s", "expected"),
    [
        (_FW_ABC, "abc"),
        (_FW_123, "123"),
        ("\u2460", "1"),
    ],
)
def test_nfkc_full_width(input_s: str, expected: str) -> None:
    assert normalize_name(input_s) == expected


@pytest.mark.parametrize(
    ("input_s", "expected"),
    [
        ("a\u00a0b", "a b"),
        ("a  b", "a b"),
        ("a\tb", "a b"),
        ("a\nb", "a b"),
        ("a\r\nb", "a b"),
        ("  a  b  ", "a b"),
    ],
)
def test_whitespace_collapse(input_s: str, expected: str) -> None:
    assert normalize_name(input_s) == expected


@pytest.mark.parametrize(
    ("input_s", "expected"),
    [
        (_HYBRID, "x"),
        (f"Testus {_HYBRID} hybridus", "testus x hybridus"),
        (f"TESTUS {_HYBRID} HYBRIDUS", "testus x hybridus"),
        ("testus x hybridus", "testus x hybridus"),
    ],
)
def test_hybrid_lift(input_s: str, expected: str) -> None:
    assert normalize_name(input_s) == expected


def test_hybrid_lift_does_not_touch_existing_x() -> None:
    assert normalize_name("Xylos xylus") == "xylos xylus"


def test_normalize_is_idempotent() -> None:
    s = normalize_name(f"Testus {_HYBRID} Hybridus")
    assert normalize_name(s) == s


# ---- normalize_scope_value -------------------------------------------------


def test_scope_value_casefold() -> None:
    assert normalize_scope_value("Field") == "field"


def test_scope_value_whitespace() -> None:
    assert normalize_scope_value("  field  ") == "field"
    assert normalize_scope_value("a\u00a0b") == "a b"


def test_scope_value_preserves_hybrid_sign() -> None:
    assert normalize_scope_value(_HYBRID) == _HYBRID
    assert normalize_scope_value(f"Testus {_HYBRID} Hybridus") == (f"testus {_HYBRID} hybridus")


def test_scope_value_empty() -> None:
    assert normalize_scope_value("") == ""
