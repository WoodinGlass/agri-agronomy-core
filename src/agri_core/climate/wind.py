"""Wind: speed and direction from U/V, height adjustment, run.

Primary literature:
- WMO 2018, Guide to Instruments and Methods of Observation (speed,
  direction, run conventions).
- Allen 1996, J. Irrig. Drain. Eng. 122(2), 97-106 (log-profile
  adjustment to 2 m).

No pack is read; ``provenance`` is empty and ``evidence`` is ``[]``.
"""

from __future__ import annotations

import math

from agri_core.models import (
    Notice,
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    not_applicable,
    ok,
)

__all__ = [
    "wind_direction_from_uv",
    "wind_height_adjust",
    "wind_run",
    "wind_speed_from_uv",
]

_CALC_VERSION = "0.1.0"


def wind_speed_from_uv(*, u_ms: float, v_ms: float) -> Outcome:
    """Wind speed (m s-1) from U (eastward) and V (northward) components.

    ``speed = sqrt(u^2 + v^2)``; ``method = "wmo_2018"``.
    """
    value = math.hypot(u_ms, v_ms)
    subject = Subject(calculation="wind_speed_from_uv", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs={"u_ms": u_ms, "v_ms": v_ms})
    return ok(
        value=value,
        unit="meter/second",
        method="wmo_2018",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def wind_direction_from_uv(*, u_ms: float, v_ms: float) -> Outcome:
    """Meteorological wind direction FROM (degrees, 0=N, 90=E).

    ``dir = (270 - atan2(v, u) * 180/pi) mod 360``; ``method = "wmo_2018"``.

    Returns ``not_applicable`` when ``u_ms == v_ms == 0`` (calm; the
    direction is undefined, not 0).
    """
    inputs = {"u_ms": u_ms, "v_ms": v_ms}
    subject = Subject(
        calculation="wind_direction_from_uv",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(subject=subject, inputs=inputs)
    if u_ms == 0.0 and v_ms == 0.0:
        return not_applicable(
            reason="wind is calm (u = v = 0); direction is undefined",
            subject=subject,
            request_id=request_id,
        )
    angle = 270.0 - math.degrees(math.atan2(v_ms, u_ms))
    value = angle % 360.0
    return ok(
        value=value,
        unit="degree",
        method="wmo_2018",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def wind_height_adjust(*, speed_ms: float, measurement_height_m: float) -> Outcome:
    """Adjust wind speed to the 2 m reference height (Allen 1996 eq 47).

    ``u2 = uz * 4.87 / ln(67.8 * z - 5.42)``.

    The Allen 1996 formula is defined for the 2 m target only; it assumes
    a grass reference with standard roughness. For a different target
    height, use a full log-profile model with explicit roughness length
    and displacement height (out of scope for M11).

    Assumption: ``allen_1996_2m_reference`` (always).
    """
    if measurement_height_m <= 0.08:
        raise ValueError(
            f"measurement_height_m must be > 0.08 (log argument), got {measurement_height_m}"
        )
    if speed_ms < 0.0:
        raise ValueError(f"speed_ms must be >= 0, got {speed_ms}")
    log_arg = 67.8 * measurement_height_m - 5.42
    if log_arg <= 0.0:
        raise ValueError(f"log argument 67.8*z - 5.42 <= 0 (z = {measurement_height_m})")
    value = speed_ms * 4.87 / math.log(log_arg)
    assumptions = [
        Notice(
            code="allen_1996_2m_reference",
            message=(
                "wind adjusted to 2 m using Allen 1996 eq 47 (grass reference); "
                "different target heights need a full log-profile model"
            ),
        )
    ]
    subject = Subject(calculation="wind_height_adjust", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "speed_ms": speed_ms,
            "measurement_height_m": measurement_height_m,
        },
    )
    return ok(
        value=value,
        unit="meter/second",
        method="allen_1996",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )


def wind_run(*, speed_ms: float, duration_hours: float = 24.0) -> Outcome:
    """Wind run (km) over ``duration_hours`` at a steady ``speed_ms``.

    ``run_km = speed_ms * duration_hours * 3.6``. For the default
    ``duration_hours = 24`` the result is km day-1.

    Assumption: ``assumed_steady_wind`` (always: the integral treats
    the speed as constant over the interval).
    """
    if speed_ms < 0.0:
        raise ValueError(f"speed_ms must be >= 0, got {speed_ms}")
    if duration_hours <= 0.0:
        raise ValueError(f"duration_hours must be > 0, got {duration_hours}")
    value = speed_ms * duration_hours * 3.6
    assumptions = [
        Notice(
            code="assumed_steady_wind",
            message=(
                "wind run assumes a constant speed over the interval; "
                "measured series must be integrated by the caller"
            ),
        )
    ]
    subject = Subject(calculation="wind_run", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={"speed_ms": speed_ms, "duration_hours": duration_hours},
    )
    return ok(
        value=value,
        unit="kilometer/day",
        method="wmo_2018",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )
