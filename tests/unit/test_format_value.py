"""format_value display formatting (M8-3a)."""

from __future__ import annotations

import pytest

from agri_core.models.fact import (
    BoolValue,
    EnumSetValue,
    EnumValue,
    RangeValue,
    RuleValue,
    ScalarValue,
    TrapezoidValue,
    UnknownValue,
    format_value,
)

pytestmark = pytest.mark.unit


# ---- scalar ----------------------------------------------------------------


def test_format_scalar() -> None:
    v = ScalarValue(shape="scalar", unit="C", value=2.5)
    assert format_value(v) == "2.5 C"


def test_format_scalar_negative() -> None:
    v = ScalarValue(shape="scalar", unit="C", value=-1.5)
    assert format_value(v) == "-1.5 C"


def test_format_scalar_zero() -> None:
    # 0.0 must not render as "0" -- float repr is stable in Python.
    v = ScalarValue(shape="scalar", unit="C", value=0.0)
    assert format_value(v) == "0.0 C"


# ---- range -----------------------------------------------------------------


def test_format_range() -> None:
    v = RangeValue(shape="range", unit="C", min=2.0, max=4.0)
    assert format_value(v) == "2.0\u20134.0 C"


# ---- trapezoid -------------------------------------------------------------


def test_format_trapezoid() -> None:
    v = TrapezoidValue(shape="trapezoid", unit="C", pts=(0.0, 2.0, 4.0, 6.0))
    assert format_value(v) == "[0.0, 2.0, 4.0, 6.0] C"


# ---- enum ------------------------------------------------------------------


def test_format_enum() -> None:
    v = EnumValue(shape="enum", value="annual")
    assert format_value(v) == "annual"


def test_format_enum_set_sorted() -> None:
    v = EnumSetValue(shape="enum_set", values=("perennial", "annual", "biennial"))
    assert format_value(v) == "{annual, biennial, perennial}"


def test_format_enum_set_single() -> None:
    v = EnumSetValue(shape="enum_set", values=("annual",))
    assert format_value(v) == "{annual}"


# ---- bool ------------------------------------------------------------------


def test_format_bool_true_false() -> None:
    assert format_value(BoolValue(shape="bool", value=True)) == "true"
    assert format_value(BoolValue(shape="bool", value=False)) == "false"


# ---- rule ------------------------------------------------------------------


def test_format_rule() -> None:
    v = RuleValue(shape="rule", data={"a": 1, "b": 2})
    assert format_value(v) == "<rule 2 keys>"


def test_format_rule_empty() -> None:
    v = RuleValue(shape="rule", data={})
    assert format_value(v) == "<rule 0 keys>"


# ---- unknown ---------------------------------------------------------------


def test_format_unknown() -> None:
    v = UnknownValue(shape="unknown", reason="site-specific")
    assert format_value(v) == "unknown (site-specific)"
