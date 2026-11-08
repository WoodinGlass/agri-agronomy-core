"""Psychrometric calculators: VPD, dew point, wet-bulb."""

from __future__ import annotations

import math

import pytest

from agri_core.climate import dew_point, vpd, wet_bulb
from agri_core.models import Result, is_success

pytestmark = pytest.mark.unit


def _value(outcome: object) -> float:
    assert isinstance(outcome, Result)
    return outcome.value


def test_vpd_typical() -> None:
    out = vpd(temp_c=25.0, rh_pct=60.0)
    assert is_success(out)
    assert out.status == "ok"
    assert isinstance(out, Result)
    assert out.unit == "kilopascal"
    assert out.method == "tetens_1930"
    assert out.value == pytest.approx(1.267, rel=1e-2)


def test_vpd_saturated_is_zero() -> None:
    out = vpd(temp_c=25.0, rh_pct=100.0)
    assert is_success(out)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.0, abs=1e-9)


def test_vpd_dry_equals_es() -> None:
    out = vpd(temp_c=25.0, rh_pct=0.0)
    assert isinstance(out, Result)
    expected_es = 0.6108 * math.exp(17.27 * 25.0 / (25.0 + 237.3))
    assert out.value == pytest.approx(expected_es, rel=1e-6)


def test_vpd_rejects_rh_out_of_range() -> None:
    with pytest.raises(ValueError, match="rh_pct"):
        vpd(temp_c=25.0, rh_pct=110.0)
    with pytest.raises(ValueError, match="rh_pct"):
        vpd(temp_c=25.0, rh_pct=-1.0)


def test_dew_point_saturated_is_t() -> None:
    out = dew_point(temp_c=20.0, rh_pct=100.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(20.0, abs=1e-6)


def test_dew_point_typical() -> None:
    out = dew_point(temp_c=25.0, rh_pct=50.0)
    assert isinstance(out, Result)
    assert out.unit == "degree_Celsius"
    assert out.value == pytest.approx(13.86, abs=0.05)


def test_dew_point_rejects_zero_rh() -> None:
    with pytest.raises(ValueError, match="rh_pct"):
        dew_point(temp_c=25.0, rh_pct=0.0)


def test_wet_bulb_typical() -> None:
    out = wet_bulb(temp_c=25.0, rh_pct=60.0)
    assert isinstance(out, Result)
    assert out.unit == "degree_Celsius"
    assert out.method == "stull_2011"
    assert out.value == pytest.approx(19.49, abs=0.1)
    assert out.warnings == []


def test_wet_bulb_low_rh_warns() -> None:
    out = wet_bulb(temp_c=25.0, rh_pct=2.0)
    assert isinstance(out, Result)
    codes = {w.code for w in out.warnings}
    assert "outside_stull_rh_range" in codes


def test_wet_bulb_low_temp_warns() -> None:
    out = wet_bulb(temp_c=-30.0, rh_pct=50.0)
    assert isinstance(out, Result)
    codes = {w.code for w in out.warnings}
    assert "outside_stull_temp_range" in codes
