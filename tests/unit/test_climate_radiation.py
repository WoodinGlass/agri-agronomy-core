"""Radiation calculators: solar_radiation and net_radiation."""

from __future__ import annotations

import pytest

from agri_core.climate import net_radiation, solar_radiation
from agri_core.models import Result, is_success

pytestmark = pytest.mark.unit


def test_solar_radiation_hargreaves_default() -> None:
    out = solar_radiation(temp_max_c=30.0, temp_min_c=18.0, extraterrestrial_radiation_mj=41.88)
    assert isinstance(out, Result)
    assert out.unit == "megajoule/meter**2/day"
    assert out.method == "hargreaves_samani_1985"
    # Rs = 0.16 * sqrt(12) * 41.88 = 23.21
    assert out.value == pytest.approx(23.21, abs=0.05)


def test_solar_radiation_custom_krs() -> None:
    out = solar_radiation(
        temp_max_c=30.0,
        temp_min_c=18.0,
        extraterrestrial_radiation_mj=41.88,
        krs=0.19,
    )
    assert isinstance(out, Result)
    # Rs = 0.19 * sqrt(12) * 41.88 = 27.56
    assert out.value == pytest.approx(27.56, abs=0.05)


def test_solar_radiation_default_krs_assumption() -> None:
    out = solar_radiation(temp_max_c=30.0, temp_min_c=18.0, extraterrestrial_radiation_mj=41.88)
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "hargreaves_estimate_rs" in codes
    assert "hargreaves_default_krs_0_16" in codes


def test_solar_radiation_supplied_krs_no_default_notice() -> None:
    out = solar_radiation(
        temp_max_c=30.0,
        temp_min_c=18.0,
        extraterrestrial_radiation_mj=41.88,
        krs=0.19,
    )
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "hargreaves_estimate_rs" in codes
    assert "hargreaves_default_krs_0_16" not in codes


def test_solar_radiation_rejects_inverted_temps() -> None:
    with pytest.raises(ValueError, match="temp_max_c"):
        solar_radiation(temp_max_c=18.0, temp_min_c=30.0, extraterrestrial_radiation_mj=41.88)


def test_solar_radiation_rejects_bad_krs() -> None:
    with pytest.raises(ValueError, match="krs"):
        solar_radiation(
            temp_max_c=30.0,
            temp_min_c=18.0,
            extraterrestrial_radiation_mj=41.88,
            krs=1.5,
        )


def test_net_radiation_typical() -> None:
    out = net_radiation(
        solar_radiation_mj=23.21,
        extraterrestrial_radiation_mj=41.88,
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        rh_pct=60.0,
    )
    assert isinstance(out, Result)
    assert out.unit == "megajoule/meter**2/day"
    assert out.method == "allen_1996"
    # Hand derivation ~ 14.08 MJ m-2 day-1; see golden fixture.
    assert out.value == pytest.approx(14.07, abs=0.3)


def test_net_radiation_emits_assumptions() -> None:
    out = net_radiation(
        solar_radiation_mj=23.21,
        extraterrestrial_radiation_mj=41.88,
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        rh_pct=60.0,
    )
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "albedo_default_0_23" in codes
    assert "rso_sea_level" in codes


def test_net_radiation_no_albedo_notice_when_overridden() -> None:
    out = net_radiation(
        solar_radiation_mj=23.21,
        extraterrestrial_radiation_mj=41.88,
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        rh_pct=60.0,
        albedo=0.20,
    )
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "albedo_default_0_23" not in codes
    # rso_sea_level is unconditional
    assert "rso_sea_level" in codes


def test_net_radiation_rejects_zero_ra() -> None:
    with pytest.raises(ValueError, match="extraterrestrial"):
        net_radiation(
            solar_radiation_mj=0.0,
            extraterrestrial_radiation_mj=0.0,
            temp_max_c=30.0,
            temp_min_c=18.0,
            temp_mean_c=24.0,
            rh_pct=60.0,
        )


def test_net_radiation_rejects_bad_albedo() -> None:
    with pytest.raises(ValueError, match="albedo"):
        net_radiation(
            solar_radiation_mj=20.0,
            extraterrestrial_radiation_mj=40.0,
            temp_max_c=30.0,
            temp_min_c=18.0,
            temp_mean_c=24.0,
            rh_pct=60.0,
            albedo=1.5,
        )


def test_net_radiation_rejects_bad_rh() -> None:
    with pytest.raises(ValueError, match="rh_pct"):
        net_radiation(
            solar_radiation_mj=20.0,
            extraterrestrial_radiation_mj=40.0,
            temp_max_c=30.0,
            temp_min_c=18.0,
            temp_mean_c=24.0,
            rh_pct=0.0,
        )


def test_net_radiation_success() -> None:
    out = net_radiation(
        solar_radiation_mj=23.21,
        extraterrestrial_radiation_mj=41.88,
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        rh_pct=60.0,
    )
    assert is_success(out)
