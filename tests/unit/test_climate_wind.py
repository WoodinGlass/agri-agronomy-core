"""Wind: speed, direction, height adjustment, run."""

from __future__ import annotations

import pytest

from agri_core.climate import (
    wind_direction_from_uv,
    wind_height_adjust,
    wind_run,
    wind_speed_from_uv,
)
from agri_core.models import NotApplicable, Result, is_success

pytestmark = pytest.mark.unit


def test_wind_speed_from_uv_3_4() -> None:
    out = wind_speed_from_uv(u_ms=3.0, v_ms=4.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(5.0, abs=1e-9)
    assert out.unit == "meter/second"
    assert out.method == "wmo_2018"


def test_wind_speed_calm() -> None:
    out = wind_speed_from_uv(u_ms=0.0, v_ms=0.0)
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_wind_speed_negative_components() -> None:
    out = wind_speed_from_uv(u_ms=-3.0, v_ms=-4.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(5.0, abs=1e-9)


def test_wind_direction_from_north() -> None:
    # Wind FROM north: blowing south; u=0, v=-1.
    out = wind_direction_from_uv(u_ms=0.0, v_ms=-1.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.0, abs=1e-6)
    assert out.unit == "degree"


def test_wind_direction_from_east() -> None:
    # Wind FROM east: blowing west; u=-1, v=0.
    out = wind_direction_from_uv(u_ms=-1.0, v_ms=0.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(90.0, abs=1e-6)


def test_wind_direction_from_south() -> None:
    out = wind_direction_from_uv(u_ms=0.0, v_ms=1.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(180.0, abs=1e-6)


def test_wind_direction_from_west() -> None:
    out = wind_direction_from_uv(u_ms=1.0, v_ms=0.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(270.0, abs=1e-6)


def test_wind_direction_calm_is_not_applicable() -> None:
    out = wind_direction_from_uv(u_ms=0.0, v_ms=0.0)
    assert isinstance(out, NotApplicable)
    assert out.status == "not_applicable"
    assert "calm" in out.reason.lower()


def test_wind_height_adjust_from_10m_to_2m() -> None:
    out = wind_height_adjust(speed_ms=5.0, measurement_height_m=10.0)
    assert isinstance(out, Result)
    # u2 = 5 * 4.87 / ln(67.8*10 - 5.42) = 5 * 4.87 / 6.511 = 3.74
    assert out.value == pytest.approx(3.74, abs=0.02)
    assert out.unit == "meter/second"
    assert out.method == "allen_1996"


def test_wind_height_adjust_at_2m_is_identity() -> None:
    out = wind_height_adjust(speed_ms=5.0, measurement_height_m=2.0)
    assert isinstance(out, Result)
    # u2 ~= uz when z = 2m (Allen 1996 eq 47 is calibrated for that).
    assert out.value == pytest.approx(5.0, abs=0.01)


def test_wind_height_adjust_assumption() -> None:
    out = wind_height_adjust(speed_ms=5.0, measurement_height_m=10.0)
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "allen_1996_2m_reference" in codes


def test_wind_height_adjust_rejects_low_height() -> None:
    with pytest.raises(ValueError, match="measurement_height_m"):
        wind_height_adjust(speed_ms=5.0, measurement_height_m=0.05)


def test_wind_height_adjust_rejects_negative_speed() -> None:
    with pytest.raises(ValueError, match="speed_ms"):
        wind_height_adjust(speed_ms=-1.0, measurement_height_m=10.0)


def test_wind_run_24h_default() -> None:
    out = wind_run(speed_ms=5.0)
    assert isinstance(out, Result)
    # 5 * 24 * 3.6 = 432 km/day
    assert out.value == pytest.approx(432.0, abs=1e-6)
    assert out.unit == "kilometer/day"


def test_wind_run_custom_duration() -> None:
    out = wind_run(speed_ms=5.0, duration_hours=12.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(216.0, abs=1e-6)


def test_wind_run_assumption() -> None:
    out = wind_run(speed_ms=5.0)
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "assumed_steady_wind" in codes


def test_wind_run_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="duration_hours"):
        wind_run(speed_ms=5.0, duration_hours=-1.0)


def test_wind_run_rejects_negative_speed() -> None:
    with pytest.raises(ValueError, match="speed_ms"):
        wind_run(speed_ms=-1.0)


def test_wind_success() -> None:
    assert is_success(wind_speed_from_uv(u_ms=1.0, v_ms=1.0))
