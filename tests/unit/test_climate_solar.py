"""Solar geometry: daylength, extraterrestrial radiation, clearness index."""

from __future__ import annotations

import pytest

from agri_core.climate import (
    clearness_index,
    daylength,
    extraterrestrial_radiation,
)
from agri_core.models import NotApplicable, Result

pytestmark = pytest.mark.unit


def test_daylength_equator_is_twelve() -> None:
    out = daylength(latitude_deg=0.0, day_of_year=172)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(12.0, abs=1e-6)
    assert out.unit == "hour"
    assert out.method == "cooper_1969"


def test_daylength_polar_day() -> None:
    out = daylength(latitude_deg=80.0, day_of_year=172)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(24.0, abs=1e-6)


def test_daylength_polar_night() -> None:
    out = daylength(latitude_deg=80.0, day_of_year=355)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.0, abs=1e-6)


def test_daylength_equinox_40n() -> None:
    # Around day 80 (spring equinox) at 40 degN, daylength ~ 12.1 h.
    out = daylength(latitude_deg=40.0, day_of_year=80)
    assert isinstance(out, Result)
    assert 11.9 <= out.value <= 12.3


def test_daylength_rejects_bad_latitude() -> None:
    with pytest.raises(ValueError, match="latitude_deg"):
        daylength(latitude_deg=100.0, day_of_year=172)


def test_daylength_rejects_bad_day_of_year() -> None:
    with pytest.raises(ValueError, match="day_of_year"):
        daylength(latitude_deg=0.0, day_of_year=0)


def test_ra_summer_solstice_40n() -> None:
    out = extraterrestrial_radiation(latitude_deg=40.0, day_of_year=172)
    assert isinstance(out, Result)
    assert out.unit == "megajoule/meter**2/day"
    assert out.method == "allen_1996"
    # Hand derivation (Allen 1996 eq 21): ~41.88 MJ m-2 day-1.
    assert out.value == pytest.approx(41.88, abs=0.5)


def test_ra_equator_equinox() -> None:
    out = extraterrestrial_radiation(latitude_deg=0.0, day_of_year=80)
    assert isinstance(out, Result)
    # Hand derivation (Allen 1996 eq 21) at lat=0, day 80 (decl ~ 0):
    #   omega_s = acos(-tan(0)*tan(0)) = pi/2
    #   dr      = 1 + 0.033*cos(2*pi*80/365) ~= 1.00635
    #   Ra      = 458.366 * 0.0820 * dr * cos(decl) * sin(omega_s)
    #           ~= 37.82 MJ m-2 day-1
    # Note: at the equator Ra is *highest* at the equinoxes (~37.8) and
    # drops to ~33.4 at the solstices, because cos(decl) < 1 while the
    # daylength remains 12 h all year.
    assert out.value == pytest.approx(37.82, abs=0.3)


def test_ra_equator_equinox_exceeds_solstice() -> None:
    """At the equator, Ra peaks at the equinoxes (cos(decl) term dominates)."""
    equinox = extraterrestrial_radiation(latitude_deg=0.0, day_of_year=80)
    solstice = extraterrestrial_radiation(latitude_deg=0.0, day_of_year=172)
    assert isinstance(equinox, Result)
    assert isinstance(solstice, Result)
    assert equinox.value > solstice.value
    # Typical values: equinox ~ 37.8, solstice ~ 33.4.
    assert equinox.value == pytest.approx(37.8, abs=0.5)
    assert solstice.value == pytest.approx(33.4, abs=0.5)


def test_ra_polar_night_is_zero() -> None:
    out = extraterrestrial_radiation(latitude_deg=80.0, day_of_year=355)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.0, abs=1e-6)


def test_clearness_index_normal() -> None:
    out = clearness_index(solar_radiation_mj=25.0, extraterrestrial_radiation_mj=41.88)
    assert isinstance(out, Result)
    assert out.unit == "dimensionless"
    assert out.value == pytest.approx(25.0 / 41.88, rel=1e-6)


def test_clearness_index_polar_night_is_not_applicable() -> None:
    out = clearness_index(solar_radiation_mj=0.0, extraterrestrial_radiation_mj=0.0)
    assert isinstance(out, NotApplicable)
    assert out.status == "not_applicable"
    assert "polar night" in out.reason.lower()


def test_clearness_index_rejects_negative_rs() -> None:
    with pytest.raises(ValueError, match="solar_radiation_mj"):
        clearness_index(solar_radiation_mj=-1.0, extraterrestrial_radiation_mj=40.0)
