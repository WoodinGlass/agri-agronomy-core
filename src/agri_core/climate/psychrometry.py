"""Psychrometric calculators: VPD, dew point, wet-bulb.

Primary literature (per catalog ``method_ref``):

- Tetens 1930, Z. Geophys. 6, 297-309 -- saturation vapor pressure.
- Allen 1996, J. Irrig. Drain. Eng. 122(2), 97-106 -- standard VPD form.
- Stull 2011, J. Appl. Meteor. Climatol. 50, 2267-2269 -- wet-bulb.

Every public function returns :data:`Outcome` (per ADR-009). No pack is
read, so ``provenance`` is empty and ``evidence`` is ``[]``.
"""

from __future__ import annotations

import math

from agri_core.models import (
    Notice,
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    ok,
)

__all__ = ["dew_point", "vpd", "wet_bulb"]

_CALC_VERSION = "0.1.0"
_STULL_T_MIN = -20.0
_STULL_T_MAX = 50.0
_STULL_RH_MIN = 5.0
_STULL_RH_MAX = 99.0


def _saturation_vapor_pressure(temp_c: float) -> float:
    """Tetens 1930: es(T) in kPa over liquid water."""
    return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))


def vpd(*, temp_c: float, rh_pct: float) -> Outcome:
    """Vapor pressure deficit (kPa).

    ``vpd = es(T) * (1 - RH/100)``; ``method = "tetens_1930"``.
    """
    if not (0.0 <= rh_pct <= 100.0):
        raise ValueError(f"rh_pct must be in [0, 100], got {rh_pct}")
    es = _saturation_vapor_pressure(temp_c)
    value = es * (1.0 - rh_pct / 100.0)
    subject = Subject(calculation="vpd", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={"temp_c": temp_c, "rh_pct": rh_pct},
    )
    return ok(
        value=value,
        unit="kilopascal",
        method="tetens_1930",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def dew_point(*, temp_c: float, rh_pct: float) -> Outcome:
    """Dew-point temperature (degC); ``RH > 0`` required.

    Inverse Tetens; ``method = "tetens_1930"``.
    """
    if not (0.0 < rh_pct <= 100.0):
        raise ValueError(f"rh_pct must be in (0, 100], got {rh_pct}")
    es = _saturation_vapor_pressure(temp_c)
    ea = es * rh_pct / 100.0
    gamma = math.log(ea / 0.6108)
    value = 237.3 * gamma / (17.27 - gamma)
    subject = Subject(calculation="dew_point", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={"temp_c": temp_c, "rh_pct": rh_pct},
    )
    return ok(
        value=value,
        unit="degree_Celsius",
        method="tetens_1930",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def wet_bulb(*, temp_c: float, rh_pct: float) -> Outcome:
    """Wet-bulb temperature (degC) from Stull 2011 empirical fit.

    Validated for RH in [5, 99]% and T in [-20, 50] C. Outside that
    range, returns a warning (``outside_stull_rh_range`` /
    ``outside_stull_temp_range``). ``method = "stull_2011"``.
    """
    if not (0.0 <= rh_pct <= 100.0):
        raise ValueError(f"rh_pct must be in [0, 100], got {rh_pct}")
    rh = rh_pct
    value = (
        temp_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(temp_c + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh**1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    warnings: list[Notice] = []
    if not (_STULL_RH_MIN <= rh <= _STULL_RH_MAX):
        warnings.append(
            Notice(
                code="outside_stull_rh_range",
                message=(
                    f"RH {rh}% is outside the Stull 2011 validated range "
                    f"[{_STULL_RH_MIN}, {_STULL_RH_MAX}]%"
                ),
            )
        )
    if not (_STULL_T_MIN <= temp_c <= _STULL_T_MAX):
        warnings.append(
            Notice(
                code="outside_stull_temp_range",
                message=(
                    f"T {temp_c}C is outside the Stull 2011 validated range "
                    f"[{_STULL_T_MIN}, {_STULL_T_MAX}]C"
                ),
            )
        )
    subject = Subject(calculation="wet_bulb", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={"temp_c": temp_c, "rh_pct": rh_pct},
    )
    return ok(
        value=value,
        unit="degree_Celsius",
        method="stull_2011",
        provenance=Provenance(),
        evidence=[],
        warnings=warnings,
        subject=subject,
        request_id=request_id,
    )
