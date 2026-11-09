"""Thermal time calculators: GDD, chilling, and photothermal units.

Primary literature:
- McMaster & Wilhelm 1997, Agric. For. Meteorol. 87(4), 291-300
  (GDD methods 1 and 2; photothermal units).
- Weinberger 1950 (chill hours: 0 < T <= 7.2 degC).
- Richardson et al. 1974 (Utah chill units; weighted accumulation).
- Cooper 1969 (daylength; used in PTU).

No pack is read; ``provenance`` is empty and ``evidence`` is ``[]``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal

from agri_core.models import (
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    insufficient_input,
    ok,
)

__all__ = [
    "chill_hours",
    "gdd_method_1",
    "gdd_method_2",
    "gdd_series",
    "photothermal_units",
    "utah_chill_units",
]

_CALC_VERSION = "0.1.0"
_CHILL_LOW_C = 0.0
_CHILL_HIGH_C = 7.2


# ─── helpers ──────────────────────────────────────────────────────────


def _gdd_scalar(
    temp_max_c: float,
    temp_min_c: float,
    tbase_c: float,
    tupper_c: float | None,
    method: Literal["method_1", "method_2"],
) -> float:
    """Single-day GDD.

    ``method_1``: GDD = max(0, min((Tmax + Tmin) / 2, Tupper) - Tbase).

    ``method_2``: Tmin floored at Tbase, Tmax capped at Tupper (if
    supplied); GDD = max(0, (Tmin_c + Tmax_c) / 2 - Tbase). When the
    capped Tmax is at or below Tbase, GDD = 0. When the floored Tmin
    exceeds the capped Tmax (whole day above Tupper), GDD is capped at
    Tupper - Tbase.
    """
    if temp_max_c < temp_min_c:
        raise ValueError(f"temp_max_c must be >= temp_min_c, got {temp_max_c} < {temp_min_c}")
    if tupper_c is not None and tupper_c <= tbase_c:
        raise ValueError(
            f"tupper_c must be > tbase_c, got tupper_c={tupper_c} <= tbase_c={tbase_c}"
        )

    if method == "method_1":
        tmean = (temp_max_c + temp_min_c) / 2.0
        if tupper_c is not None and tmean > tupper_c:
            tmean = tupper_c
        return max(0.0, tmean - tbase_c)

    if method == "method_2":
        tmin_c = max(temp_min_c, tbase_c)
        tmax_c = temp_max_c
        if tupper_c is not None and tmax_c > tupper_c:
            tmax_c = tupper_c
        if tmax_c <= tbase_c:
            return 0.0
        if tmin_c > tmax_c:
            return max(0.0, tmax_c - tbase_c)
        tmean = (tmin_c + tmax_c) / 2.0
        return max(0.0, tmean - tbase_c)

    raise ValueError(f"unknown method: {method!r}")


def _check_consecutive_dates(dates: Sequence[date]) -> list[str]:
    problems: list[str] = []
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        if delta != 1:
            problems.append(f"gap_between_{dates[i - 1].isoformat()}_and_{dates[i].isoformat()}")
    return problems


def _check_hourly_timestamps(timestamps: Sequence[datetime]) -> list[str]:
    problems: list[str] = []
    for i in range(1, len(timestamps)):
        delta = (timestamps[i] - timestamps[i - 1]).total_seconds()
        if delta != 3600.0:
            problems.append(
                f"gap_between_{timestamps[i - 1].isoformat()}_and_{timestamps[i].isoformat()}"
            )
    return problems


def _utah_u_for_temp(t: float) -> float:
    """Richardson et al. 1974 Utah Chill Unit table (per hour).

    Buckets are [lo, hi):
      T < 1.4 -> 0; [1.4, 2.4) -> +0.5; [2.4, 9.1) -> +1.0;
      [9.1, 12.4) -> +0.5; [12.4, 15.9) -> 0;
      [15.9, 18.0) -> -0.5; T >= 18.0 -> -1.0.
    """
    if t < 1.4:
        return 0.0
    if t < 2.4:
        return 0.5
    if t < 9.1:
        return 1.0
    if t < 12.4:
        return 0.5
    if t < 15.9:
        return 0.0
    if t < 18.0:
        return -0.5
    return -1.0


# ─── public ───────────────────────────────────────────────────────────


def gdd_method_1(
    *,
    temp_max_c: float,
    temp_min_c: float,
    tbase_c: float,
    tupper_c: float | None = None,
) -> Outcome:
    """Growing degree days (degree_day) via McMaster & Wilhelm 1997 method 1.

    ``GDD = max(0, min((Tmax + Tmin) / 2, Tupper) - Tbase)``.
    Method 1 uses the daily mean and caps it at Tupper (if supplied).
    """
    value = _gdd_scalar(temp_max_c, temp_min_c, tbase_c, tupper_c, "method_1")
    subject = Subject(calculation="gdd_method_1", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "temp_max_c": temp_max_c,
            "temp_min_c": temp_min_c,
            "tbase_c": tbase_c,
            "tupper_c": tupper_c,
        },
    )
    return ok(
        value=value,
        unit="degree_day",
        method="mcmaster_wilhelm_1997_method_1",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def gdd_method_2(
    *,
    temp_max_c: float,
    temp_min_c: float,
    tbase_c: float,
    tupper_c: float | None = None,
) -> Outcome:
    """Growing degree days (degree_day) via McMaster & Wilhelm 1997 method 2.

    Tmin floored at Tbase; Tmax capped at Tupper (if supplied);
    ``GDD = max(0, (Tmin_c + Tmax_c) / 2 - Tbase)``. Gives higher values
    than method 1 on days with ``Tmin < Tbase < Tmax``.
    """
    value = _gdd_scalar(temp_max_c, temp_min_c, tbase_c, tupper_c, "method_2")
    subject = Subject(calculation="gdd_method_2", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "temp_max_c": temp_max_c,
            "temp_min_c": temp_min_c,
            "tbase_c": tbase_c,
            "tupper_c": tupper_c,
        },
    )
    return ok(
        value=value,
        unit="degree_day",
        method="mcmaster_wilhelm_1997_method_2",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def gdd_series(
    *,
    dates: Sequence[date],
    temp_max_c: Sequence[float],
    temp_min_c: Sequence[float],
    tbase_c: float,
    tupper_c: float | None = None,
    method: Literal["method_1", "method_2"] = "method_1",
) -> Outcome:
    """Total GDD over a daily series.

    ``dates`` must be consecutive (one day apart, no gaps). A gap
    returns ``insufficient_input`` with the gap description; nothing is
    interpolated.
    """
    n = len(dates)
    if n == 0:
        raise ValueError("series must be non-empty")
    if len(temp_max_c) != n:
        raise ValueError(f"length mismatch: dates={n}, temp_max_c={len(temp_max_c)}")
    if len(temp_min_c) != n:
        raise ValueError(f"length mismatch: dates={n}, temp_min_c={len(temp_min_c)}")

    problems = _check_consecutive_dates(dates)
    inputs = {
        "n": n,
        "first_date": dates[0].isoformat(),
        "last_date": dates[-1].isoformat(),
        "tbase_c": tbase_c,
        "tupper_c": tupper_c,
        "method": method,
    }
    subject = Subject(calculation="gdd_series", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=inputs)
    if problems:
        return insufficient_input(missing=problems, subject=subject, request_id=request_id)

    total = 0.0
    for tmax, tmin in zip(temp_max_c, temp_min_c, strict=True):
        total += _gdd_scalar(tmax, tmin, tbase_c, tupper_c, method)
    return ok(
        value=total,
        unit="degree_day",
        method=f"mcmaster_wilhelm_1997_{method}",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def chill_hours(
    *,
    timestamps: Sequence[datetime],
    temps_c: Sequence[float],
) -> Outcome:
    """Weinberger 1950 chill hours (count of hours in (0, 7.2] degC).

    Hourly only: ``timestamps`` must be consecutive 1-hour increments.
    A gap returns ``insufficient_input``; nothing is interpolated.
    """
    n = len(timestamps)
    if n == 0:
        raise ValueError("series must be non-empty")
    if len(temps_c) != n:
        raise ValueError(f"length mismatch: timestamps={n}, temps_c={len(temps_c)}")

    problems = _check_hourly_timestamps(timestamps)
    inputs = {
        "n": n,
        "first_ts": timestamps[0].isoformat(),
        "last_ts": timestamps[-1].isoformat(),
    }
    subject = Subject(calculation="chill_hours", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=inputs)
    if problems:
        return insufficient_input(missing=problems, subject=subject, request_id=request_id)

    count = sum(1 for t in temps_c if _CHILL_LOW_C < t <= _CHILL_HIGH_C)
    return ok(
        value=float(count),
        unit="hour",
        method="weinberger_1950",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def utah_chill_units(
    *,
    timestamps: Sequence[datetime],
    temps_c: Sequence[float],
) -> Outcome:
    """Richardson et al. 1974 Utah Chill Units from hourly temperature.

    Each hour contributes per the Utah table; warm hours (> 15.9 degC)
    subtract. Hourly only; a gap returns ``insufficient_input``.
    """
    n = len(timestamps)
    if n == 0:
        raise ValueError("series must be non-empty")
    if len(temps_c) != n:
        raise ValueError(f"length mismatch: timestamps={n}, temps_c={len(temps_c)}")

    problems = _check_hourly_timestamps(timestamps)
    inputs = {
        "n": n,
        "first_ts": timestamps[0].isoformat(),
        "last_ts": timestamps[-1].isoformat(),
    }
    subject = Subject(calculation="utah_chill_units", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=inputs)
    if problems:
        return insufficient_input(missing=problems, subject=subject, request_id=request_id)

    total = sum(_utah_u_for_temp(t) for t in temps_c)
    return ok(
        value=total,
        unit="dimensionless",
        method="richardson_1974",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def photothermal_units(
    *,
    gdd: float,
    daylength_hours: float,
) -> Outcome:
    """Photothermal units (PTU) = GDD x daylength; dimensionless.

    ``PTU = GDD * daylength_hours``. Relative index; no canonical unit.
    The caller supplies ``gdd`` (for example from :func:`gdd_method_1` or
    :func:`gdd_series`) and ``daylength_hours`` (for example from
    :func:`agri_core.climate.daylength`).
    """
    if gdd < 0.0:
        raise ValueError(f"gdd must be >= 0, got {gdd}")
    if not (0.0 <= daylength_hours <= 24.0):
        raise ValueError(f"daylength_hours must be in [0, 24], got {daylength_hours}")
    value = gdd * daylength_hours
    subject = Subject(calculation="photothermal_units", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={"gdd": gdd, "daylength_hours": daylength_hours},
    )
    return ok(
        value=value,
        unit="dimensionless",
        method="mcmaster_wilhelm_1997_cooper_1969",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )
