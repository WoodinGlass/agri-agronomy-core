"""Pressure and temperature from elevation."""

from __future__ import annotations

import pytest

from agri_core.climate import pressure_from_elevation, temp_from_elevation
from agri_core.models import Result, is_success

pytestmark = pytest.mark.unit


def test_pressure_sea_level() -> None:
    out = pressure_from_elevation(elevation_m=0.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(101.3, abs=0.01)
    assert out.unit == "kilopascal"
    assert out.method == "allen_1996"


def test_pressure_1000m() -> None:
    out = pressure_from_elevation(elevation_m=1000.0)
    assert isinstance(out, Result)
    # P = 101.3 * ((293 - 6.5) / 293)^5.26 = 101.3 * 0.9778^5.26 = 90.1
    assert out.value == pytest.approx(90.1, abs=0.5)


def test_pressure_2000m() -> None:
    out = pressure_from_elevation(elevation_m=2000.0)
    assert isinstance(out, Result)
    # ~ 79.5 kPa
    assert out.value == pytest.approx(79.5, abs=1.0)


def test_pressure_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="elevation_m"):
        pressure_from_elevation(elevation_m=15000.0)
    with pytest.raises(ValueError, match="elevation_m"):
        pressure_from_elevation(elevation_m=-1000.0)


def test_temp_from_elevation_sea_level() -> None:
    out = temp_from_elevation(temp_c_at_sea_level=28.0, elevation_m=0.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(28.0, abs=1e-9)
    assert out.unit == "degree_Celsius"
    assert out.method == "allen_1996"


def test_temp_from_elevation_1000m() -> None:
    out = temp_from_elevation(temp_c_at_sea_level=28.0, elevation_m=1000.0)
    assert isinstance(out, Result)
    # 28 - 6.5 = 21.5
    assert out.value == pytest.approx(21.5, abs=0.01)


def test_temp_from_elevation_2000m() -> None:
    out = temp_from_elevation(temp_c_at_sea_level=28.0, elevation_m=2000.0)
    assert isinstance(out, Result)
    # 28 - 13 = 15.0
    assert out.value == pytest.approx(15.0, abs=0.01)


def test_temp_from_elevation_assumption() -> None:
    out = temp_from_elevation(temp_c_at_sea_level=28.0, elevation_m=1000.0)
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "standard_atmosphere_lapse_rate" in codes


def test_temp_from_elevation_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="elevation_m"):
        temp_from_elevation(temp_c_at_sea_level=28.0, elevation_m=15000.0)


def test_elevation_success() -> None:
    assert is_success(pressure_from_elevation(elevation_m=500.0))
    assert is_success(temp_from_elevation(temp_c_at_sea_level=20.0, elevation_m=500.0))
