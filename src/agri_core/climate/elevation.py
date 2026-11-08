"""Pressure and temperature from elevation (Allen 1996 standard atmosphere).

Primary literature: Allen 1996, J. Irrig. Drain. Eng. 122(2), 97-106
(eqs 7-8, atmosphere formulas).

No pack is read; ``provenance`` is empty and ``evidence`` is ``[]``.
"""

from __future__ import annotations

from agri_core.models import (
    Notice,
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    ok,
)

__all__ = ["pressure_from_elevation", "temp_from_elevation"]

_CALC_VERSION = "0.1.0"
_LAPSE_RATE_C_PER_M = 0.0065  # 6.5 degC per km (ISA troposphere)


def _check_elevation(elevation_m: float) -> None:
    if not (-500.0 <= elevation_m <= 10000.0):
        raise ValueError(f"elevation_m must be in [-500, 10000], got {elevation_m}")


def pressure_from_elevation(*, elevation_m: float) -> Outcome:
    """Atmospheric pressure (kPa) from elevation (Allen 1996 eq 7).

    ``P = 101.3 * ((293 - 0.0065 z) / 293) ** 5.26``.

    ``method = "allen_1996"``. Standard atmosphere; assumes sea-level
    reference pressure of 101.3 kPa.
    """
    _check_elevation(elevation_m)
    ratio = (293.0 - _LAPSE_RATE_C_PER_M * elevation_m) / 293.0
    value = 101.3 * (ratio**5.26)
    subject = Subject(calculation="pressure_from_elevation", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs={"elevation_m": elevation_m})
    return ok(
        value=value,
        unit="kilopascal",
        method="allen_1996",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def temp_from_elevation(*, temp_c_at_sea_level: float, elevation_m: float) -> Outcome:
    """Temperature (degC) at ``elevation_m`` given a sea-level reference.

    ``T(z) = T0 - 0.0065 * z``; ``method = "allen_1996"``.

    Assumption: ``standard_atmosphere_lapse_rate`` (always: 6.5 degC/km
    from the International Standard Atmosphere; local lapse rates vary,
    especially in humid tropics).
    """
    _check_elevation(elevation_m)
    value = temp_c_at_sea_level - _LAPSE_RATE_C_PER_M * elevation_m
    assumptions = [
        Notice(
            code="standard_atmosphere_lapse_rate",
            message=(
                "6.5 degC/km lapse rate (ISA troposphere) applied; "
                "local lapse rates vary with humidity and season"
            ),
        )
    ]
    subject = Subject(calculation="temp_from_elevation", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "temp_c_at_sea_level": temp_c_at_sea_level,
            "elevation_m": elevation_m,
        },
    )
    return ok(
        value=value,
        unit="degree_Celsius",
        method="allen_1996",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )
