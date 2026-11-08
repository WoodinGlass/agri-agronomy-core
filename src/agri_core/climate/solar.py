"""Solar geometry: daylength, extraterrestrial radiation, clearness index.

Primary literature (per catalog ``method_ref``):

- Cooper 1969 (daylength approximation).
- Allen 1996, J. Irrig. Drain. Eng. 122(2), 97-106 (eqs 21-25).

Every public function returns :data:`Outcome`. No pack is read, so
``provenance`` is empty and ``evidence`` is ``[]``.
"""

from __future__ import annotations

import math

from agri_core.models import (
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    not_applicable,
    ok,
)

__all__ = ["clearness_index", "daylength", "extraterrestrial_radiation"]

_CALC_VERSION = "0.1.0"
_GSC_MJ_M2_MIN = 0.0820  # solar constant, MJ m-2 min-1 (Allen 1996)


def _check_latitude(latitude_deg: float) -> float:
    if not (-90.0 <= latitude_deg <= 90.0):
        raise ValueError(f"latitude_deg must be in [-90, 90], got {latitude_deg}")
    return math.radians(latitude_deg)


def _check_day_of_year(day_of_year: int) -> None:
    if not (1 <= day_of_year <= 366):
        raise ValueError(f"day_of_year must be in [1, 366], got {day_of_year}")


def _declination(day_of_year: int) -> float:
    """Solar declination (rad); Allen 1996 eq 24 (Spencer form)."""
    return 0.409 * math.sin(2.0 * math.pi * day_of_year / 365.0 - 1.39)


def _sunset_hour_angle(lat_rad: float, day_of_year: int) -> float:
    """Sunset hour angle (rad); clamped to [0, pi] for polar day/night."""
    decl = _declination(day_of_year)
    arg = -math.tan(lat_rad) * math.tan(decl)
    arg = max(-1.0, min(1.0, arg))
    return math.acos(arg)


def daylength(*, latitude_deg: float, day_of_year: int) -> Outcome:
    """Daylength in hours; ``method = "cooper_1969"``.

    Polar night returns ``0.0``; polar day returns ``24.0``.
    """
    lat_rad = _check_latitude(latitude_deg)
    _check_day_of_year(day_of_year)
    omega_s = _sunset_hour_angle(lat_rad, day_of_year)
    value = 24.0 / math.pi * omega_s
    subject = Subject(calculation="daylength", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={"latitude_deg": latitude_deg, "day_of_year": day_of_year},
    )
    return ok(
        value=value,
        unit="hour",
        method="cooper_1969",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def extraterrestrial_radiation(*, latitude_deg: float, day_of_year: int) -> Outcome:
    """Extraterrestrial radiation Ra (MJ m-2 day-1); Allen 1996 eq 21."""
    lat_rad = _check_latitude(latitude_deg)
    _check_day_of_year(day_of_year)
    decl = _declination(day_of_year)
    dr = 1.0 + 0.033 * math.cos(2.0 * math.pi * day_of_year / 365.0)
    omega_s = _sunset_hour_angle(lat_rad, day_of_year)
    value = (
        (24.0 * 60.0 / math.pi)
        * _GSC_MJ_M2_MIN
        * dr
        * (
            omega_s * math.sin(lat_rad) * math.sin(decl)
            + math.cos(lat_rad) * math.cos(decl) * math.sin(omega_s)
        )
    )
    subject = Subject(
        calculation="extraterrestrial_radiation",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={"latitude_deg": latitude_deg, "day_of_year": day_of_year},
    )
    return ok(
        value=value,
        unit="megajoule/meter**2/day",
        method="allen_1996",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def clearness_index(
    *,
    solar_radiation_mj: float,
    extraterrestrial_radiation_mj: float,
) -> Outcome:
    """Clearness index ``Kt = Rs / Ra`` (dimensionless); Allen 1996.

    Returns ``not_applicable`` when ``Ra == 0`` (polar night; Kt
    undefined). ``method = "allen_1996"``.
    """
    if solar_radiation_mj < 0.0:
        raise ValueError(f"solar_radiation_mj must be >= 0, got {solar_radiation_mj}")
    inputs = {
        "solar_radiation_mj": solar_radiation_mj,
        "extraterrestrial_radiation_mj": extraterrestrial_radiation_mj,
    }
    subject = Subject(
        calculation="clearness_index",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(subject=subject, inputs=inputs)
    if extraterrestrial_radiation_mj <= 0.0:
        return not_applicable(
            reason=(
                "extraterrestrial radiation is zero (polar night); the clearness index is undefined"
            ),
            subject=subject,
            request_id=request_id,
        )
    value = solar_radiation_mj / extraterrestrial_radiation_mj
    return ok(
        value=value,
        unit="dimensionless",
        method="allen_1996",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )
