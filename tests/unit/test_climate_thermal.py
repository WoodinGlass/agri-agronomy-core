"""Thermal time: GDD, chilling, photothermal units."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from agri_core.climate import (
    chill_hours,
    gdd_method_1,
    gdd_method_2,
    gdd_series,
    photothermal_units,
    utah_chill_units,
)
from agri_core.models import InsufficientInput, Result, is_success

pytestmark = pytest.mark.unit


# ─── GDD method 1 ───


def test_gdd_m1_basic() -> None:
    out = gdd_method_1(temp_max_c=25.0, temp_min_c=15.0, tbase_c=10.0)
    assert isinstance(out, Result)
    assert out.unit == "degree_day"
    assert out.method == "mcmaster_wilhelm_1997_method_1"
    assert out.value == pytest.approx(10.0, abs=1e-9)


def test_gdd_m1_with_tupper() -> None:
    out = gdd_method_1(temp_max_c=30.0, temp_min_c=20.0, tbase_c=10.0, tupper_c=22.0)
    assert isinstance(out, Result)
    # mean = 25; min(25, 22) = 22; GDD = 12
    assert out.value == pytest.approx(12.0, abs=1e-9)


def test_gdd_m1_below_base() -> None:
    out = gdd_method_1(temp_max_c=8.0, temp_min_c=2.0, tbase_c=10.0)
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_gdd_m1_rejects_inverted_temps() -> None:
    with pytest.raises(ValueError, match="temp_max_c"):
        gdd_method_1(temp_max_c=15.0, temp_min_c=25.0, tbase_c=10.0)


def test_gdd_m1_rejects_bad_tupper() -> None:
    with pytest.raises(ValueError, match="tupper_c"):
        gdd_method_1(temp_max_c=25.0, temp_min_c=15.0, tbase_c=10.0, tupper_c=5.0)


# ─── GDD method 2 ───


def test_gdd_m2_basic() -> None:
    out = gdd_method_2(temp_max_c=25.0, temp_min_c=15.0, tbase_c=10.0)
    assert isinstance(out, Result)
    assert out.method == "mcmaster_wilhelm_1997_method_2"
    assert out.value == pytest.approx(10.0, abs=1e-9)


def test_gdd_m2_floors_tmin() -> None:
    out = gdd_method_2(temp_max_c=30.0, temp_min_c=5.0, tbase_c=10.0)
    assert isinstance(out, Result)
    # Tmin' = 10; mean = 20; GDD = 10
    assert out.value == pytest.approx(10.0, abs=1e-9)


def test_gdd_m2_with_tupper() -> None:
    out = gdd_method_2(temp_max_c=30.0, temp_min_c=5.0, tbase_c=10.0, tupper_c=15.0)
    assert isinstance(out, Result)
    # Tmin' = 10, Tmax' = 15; mean = 12.5; GDD = 2.5
    assert out.value == pytest.approx(2.5, abs=1e-9)


def test_gdd_m1_vs_m2_when_tmin_below_base() -> None:
    a = gdd_method_1(temp_max_c=30.0, temp_min_c=5.0, tbase_c=10.0)
    b = gdd_method_2(temp_max_c=30.0, temp_min_c=5.0, tbase_c=10.0)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    # Method 1: mean = 17.5, GDD = 7.5. Method 2: GDD = 10.
    assert a.value == pytest.approx(7.5, abs=1e-9)
    assert b.value == pytest.approx(10.0, abs=1e-9)
    assert b.value > a.value


# ─── GDD series ───


def test_gdd_series_consecutive() -> None:
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    out = gdd_series(
        dates=dates,
        temp_max_c=[25.0, 30.0, 22.0],
        temp_min_c=[15.0, 20.0, 12.0],
        tbase_c=10.0,
    )
    assert isinstance(out, Result)
    # 10 + 15 + 7 = 32
    assert out.value == pytest.approx(32.0, abs=1e-9)


def test_gdd_series_gap_returns_insufficient() -> None:
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 4)]
    out = gdd_series(
        dates=dates,
        temp_max_c=[25.0, 30.0, 22.0],
        temp_min_c=[15.0, 20.0, 12.0],
        tbase_c=10.0,
    )
    assert isinstance(out, InsufficientInput)
    assert out.status == "insufficient_input"
    assert any("gap_between" in m for m in out.missing)


def test_gdd_series_length_mismatch() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        gdd_series(
            dates=[date(2026, 1, 1), date(2026, 1, 2)],
            temp_max_c=[25.0],
            temp_min_c=[15.0],
            tbase_c=10.0,
        )


def test_gdd_series_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        gdd_series(
            dates=[],
            temp_max_c=[],
            temp_min_c=[],
            tbase_c=10.0,
        )


# ─── Chill hours ───


def test_chill_hours_basic() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(8)]
    temps = [5.0] * 8
    out = chill_hours(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, Result)
    assert out.value == 8.0
    assert out.unit == "hour"
    assert out.method == "weinberger_1950"


def test_chill_hours_outside_range() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(8)]
    # 20 degC: outside (0, 7.2]
    temps = [20.0] * 8
    out = chill_hours(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_chill_hours_gap_returns_insufficient() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(12)] + [
        base + timedelta(hours=i) for i in range(13, 25)
    ]
    temps = [5.0] * 24
    out = chill_hours(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, InsufficientInput)


def test_chill_hours_length_mismatch() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(ValueError, match="length mismatch"):
        chill_hours(
            timestamps=[base, base + timedelta(hours=1)],
            temps_c=[5.0],
        )


# ─── Utah chill units ───


def test_utah_units_all_optimal() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(24)]
    temps = [5.0] * 24  # in [2.4, 9.1): +1.0/hour
    out = utah_chill_units(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, Result)
    assert out.unit == "dimensionless"
    assert out.method == "richardson_1974"
    assert out.value == pytest.approx(24.0, abs=1e-9)


def test_utah_units_warm_negative() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(24)]
    # 8h at 20 degC (-1.0), 8h at 15 degC (0), 8h at 5 degC (+1.0)
    temps = [20.0] * 8 + [15.0] * 8 + [5.0] * 8
    out = utah_chill_units(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, Result)
    # 8*(-1) + 8*0 + 8*(+1) = 0
    assert out.value == pytest.approx(0.0, abs=1e-9)


def test_utah_units_mixed() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(4)]
    temps = [1.0, 5.0, 10.0, 20.0]
    out = utah_chill_units(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, Result)
    # 1.0 (T<1.4) -> 0; 5.0 -> +1.0; 10.0 -> +0.5; 20.0 -> -1.0
    assert out.value == pytest.approx(0.5, abs=1e-9)


def test_utah_units_gap_returns_insufficient() -> None:
    base = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(hours=i) for i in range(12)] + [
        base + timedelta(hours=i) for i in range(13, 25)
    ]
    temps = [5.0] * 24
    out = utah_chill_units(timestamps=timestamps, temps_c=temps)
    assert isinstance(out, InsufficientInput)


# ─── Photothermal units ───


def test_ptu_basic() -> None:
    out = photothermal_units(gdd=30.0, daylength_hours=12.0)
    assert isinstance(out, Result)
    assert out.unit == "dimensionless"
    assert out.value == pytest.approx(360.0, abs=1e-9)
    assert out.method == "mcmaster_wilhelm_1997_cooper_1969"


def test_ptu_zero_daylength() -> None:
    out = photothermal_units(gdd=30.0, daylength_hours=0.0)
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_ptu_rejects_negative_gdd() -> None:
    with pytest.raises(ValueError, match="gdd"):
        photothermal_units(gdd=-1.0, daylength_hours=12.0)


def test_ptu_rejects_bad_daylength() -> None:
    with pytest.raises(ValueError, match="daylength_hours"):
        photothermal_units(gdd=30.0, daylength_hours=25.0)


def test_gdd_success_m1_m2() -> None:
    assert is_success(gdd_method_1(temp_max_c=25.0, temp_min_c=15.0, tbase_c=10.0))
    assert is_success(gdd_method_2(temp_max_c=25.0, temp_min_c=15.0, tbase_c=10.0))
