"""ET0 calculators: Penman-Monteith, Hargreaves-Samani, dispatcher."""

from __future__ import annotations

import pytest

from agri_core.climate import (
    et0,
    et0_hargreaves_samani,
    et0_penman_monteith,
)
from agri_core.models import InsufficientInput, Result, is_success

pytestmark = pytest.mark.unit


# ─── Penman-Monteith ───


def test_pm_typical() -> None:
    out = et0_penman_monteith(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=2.0,
    )
    assert isinstance(out, Result)
    assert out.unit == "millimeter/day"
    assert out.method == "penman_monteith_1965"
    # Hand derivation: see golden fixture. ~5.29 mm/day.
    assert out.value == pytest.approx(5.29, abs=0.1)


def test_pm_assumption() -> None:
    out = et0_penman_monteith(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=2.0,
    )
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "psychrometric_constant_sea_level" in codes


def test_pm_rejects_bad_rh() -> None:
    with pytest.raises(ValueError, match="rh_pct"):
        et0_penman_monteith(
            net_radiation_mj=14.07,
            temp_mean_c=25.0,
            rh_pct=0.0,
            wind_speed_2m_ms=2.0,
        )


def test_pm_rejects_negative_wind() -> None:
    with pytest.raises(ValueError, match="wind_speed_2m_ms"):
        et0_penman_monteith(
            net_radiation_mj=14.07,
            temp_mean_c=25.0,
            rh_pct=60.0,
            wind_speed_2m_ms=-1.0,
        )


def test_pm_zero_wind() -> None:
    out = et0_penman_monteith(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=0.0,
    )
    assert isinstance(out, Result)
    # u2=0 removes the aerodynamic term; value is smaller than with wind.
    assert out.value < 5.29
    assert out.value > 0.0


# ─── Hargreaves-Samani ───


def test_hs_typical() -> None:
    out = et0_hargreaves_samani(
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        extraterrestrial_radiation_mj=20.0,
    )
    assert isinstance(out, Result)
    assert out.unit == "millimeter/day"
    assert out.method == "hargreaves_samani_1985"
    # 0.0023 * 41.8 * sqrt(12) * 20 = 6.66
    assert out.value == pytest.approx(6.66, abs=0.05)


def test_hs_zero_ra() -> None:
    out = et0_hargreaves_samani(
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        extraterrestrial_radiation_mj=0.0,
    )
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_hs_rejects_inverted_temps() -> None:
    with pytest.raises(ValueError, match="temp_max_c"):
        et0_hargreaves_samani(
            temp_max_c=18.0,
            temp_min_c=30.0,
            temp_mean_c=24.0,
            extraterrestrial_radiation_mj=20.0,
        )


# ─── Dispatcher et0() ───


def test_et0_uses_pm_when_complete() -> None:
    out = et0(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=2.0,
    )
    assert isinstance(out, Result)
    assert out.method == "penman_monteith_1965"
    assert out.subject is not None
    assert out.subject.calculation == "et0"
    codes = {w.code for w in out.warnings}
    assert "used_hargreaves_fallback" not in codes


def test_et0_falls_back_to_hs_when_pm_incomplete() -> None:
    out = et0(
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        extraterrestrial_radiation_mj=20.0,
    )
    assert isinstance(out, Result)
    assert out.method == "hargreaves_samani_1985"
    assert out.subject is not None
    assert out.subject.calculation == "et0"
    codes = {w.code for w in out.warnings}
    assert "used_hargreaves_fallback" in codes


def test_et0_prefers_pm_when_both_sets_complete() -> None:
    out = et0(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=2.0,
        temp_max_c=30.0,
        temp_min_c=18.0,
        extraterrestrial_radiation_mj=20.0,
    )
    assert isinstance(out, Result)
    assert out.method == "penman_monteith_1965"


def test_et0_insufficient_when_neither_complete() -> None:
    out = et0(temp_max_c=30.0)
    assert isinstance(out, InsufficientInput)
    assert out.status == "insufficient_input"
    assert out.subject is not None
    assert out.subject.calculation == "et0"
    # missing includes both PM and HS fields not supplied.
    assert "net_radiation_mj" in out.missing
    assert "rh_pct" in out.missing
    assert "wind_speed_2m_ms" in out.missing
    assert "temp_min_c" in out.missing
    assert "extraterrestrial_radiation_mj" in out.missing


def test_et0_insufficient_with_no_args() -> None:
    out = et0()
    assert isinstance(out, InsufficientInput)
    assert len(out.missing) > 0


def test_et0_success_via_pm() -> None:
    out = et0(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=2.0,
    )
    assert is_success(out)


def test_et0_success_via_hs() -> None:
    out = et0(
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        extraterrestrial_radiation_mj=20.0,
    )
    assert is_success(out)
