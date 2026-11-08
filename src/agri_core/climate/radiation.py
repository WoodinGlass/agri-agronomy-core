"""Solar and net radiation: Hargreaves-Samani Rs and Allen 1996 Rn.

Primary literature:
- Hargreaves & Samani 1985, J. Irrig. Drain. Eng. 111(2), 113-124.
- Allen 1996, J. Irrig. Drain. Eng. 122(2), 97-106 (eqs 21, 37-40).

No pack is read; ``provenance`` is empty and ``evidence`` is ``[]``.
Every estimated input is reported as an assumption (README).
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

__all__ = ["net_radiation", "solar_radiation"]

_CALC_VERSION = "0.1.0"
_SIGMA = 4.903e-9  # MJ m-2 day-1 K-4 (Stefan-Boltzmann, Allen 1996)


def solar_radiation(
    *,
    temp_max_c: float,
    temp_min_c: float,
    extraterrestrial_radiation_mj: float,
    krs: float | None = None,
) -> Outcome:
    """Hargreaves-Samani 1985 Rs estimate (MJ m-2 day-1).

    ``Rs = kRs * sqrt(Tmax - Tmin) * Ra``.

    ``krs`` default is ``0.16`` (inland reference value from the paper);
    coastal sites typically use ``0.19``. Callers with a site-specific
    calibration pass ``krs`` directly. When ``krs`` is ``None`` the
    default is applied and reported as an assumption.

    Assumptions:
    - ``hargreaves_estimate_rs`` (always: Rs is estimated, not measured)
    - ``hargreaves_default_krs_0_16`` (only when ``krs is None``)
    """
    if temp_max_c < temp_min_c:
        raise ValueError(f"temp_max_c must be >= temp_min_c, got {temp_max_c} < {temp_min_c}")
    if extraterrestrial_radiation_mj < 0.0:
        raise ValueError(
            f"extraterrestrial_radiation_mj must be >= 0, got {extraterrestrial_radiation_mj}"
        )
    if krs is not None and not (0.0 < krs <= 1.0):
        raise ValueError(f"krs must be in (0, 1], got {krs}")

    assumptions: list[Notice] = [
        Notice(
            code="hargreaves_estimate_rs",
            message=(
                "Rs estimated from Tmax-Tmin using Hargreaves-Samani 1985; Rs is not measured"
            ),
        )
    ]
    if krs is None:
        effective_krs = 0.16
        assumptions.append(
            Notice(
                code="hargreaves_default_krs_0_16",
                message=(
                    "kRs default 0.16 (inland reference) applied; coastal sites typically use 0.19"
                ),
            )
        )
    else:
        effective_krs = krs

    dt = temp_max_c - temp_min_c
    value = effective_krs * math.sqrt(dt) * extraterrestrial_radiation_mj

    subject = Subject(calculation="solar_radiation", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "temp_max_c": temp_max_c,
            "temp_min_c": temp_min_c,
            "extraterrestrial_radiation_mj": extraterrestrial_radiation_mj,
            "krs": krs,
        },
    )
    return ok(
        value=value,
        unit="megajoule/meter**2/day",
        method="hargreaves_samani_1985",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )


def net_radiation(
    *,
    solar_radiation_mj: float,
    extraterrestrial_radiation_mj: float,
    temp_max_c: float,
    temp_min_c: float,
    temp_mean_c: float,
    rh_pct: float,
    albedo: float = 0.23,
) -> Outcome:
    """Net radiation Rn (MJ m-2 day-1); Allen 1996 eqs 37-40.

    ``Rns = (1 - albedo) * Rs``
    ``Rso = 0.75 * Ra`` (sea-level clear-sky radiation)
    ``Rnl = sigma * ((Tmax_K^4 + Tmin_K^4) / 2) * (0.34 - 0.14*sqrt(ea)) *
            (1.35 * Rs / Rso - 0.35)``
    ``Rn = Rns - Rnl``

    Assumptions:
    - ``albedo_default_0_23`` (only when ``albedo == 0.23``)
    - ``rso_sea_level`` (always: Rso is computed at sea level)

    ``elevation_m`` is not accepted: the Rso correction (``+ 2e-5 z``)
    is out of scope for M11. A future milestone may add it.
    """
    if solar_radiation_mj < 0.0:
        raise ValueError(f"solar_radiation_mj must be >= 0, got {solar_radiation_mj}")
    if extraterrestrial_radiation_mj <= 0.0:
        raise ValueError(
            f"extraterrestrial_radiation_mj must be > 0 (polar night has "
            f"no meaningful Rn), got {extraterrestrial_radiation_mj}"
        )
    if temp_max_c < temp_min_c:
        raise ValueError(f"temp_max_c must be >= temp_min_c, got {temp_max_c} < {temp_min_c}")
    if not (0.0 < rh_pct <= 100.0):
        raise ValueError(f"rh_pct must be in (0, 100], got {rh_pct}")
    if not (0.0 <= albedo <= 1.0):
        raise ValueError(f"albedo must be in [0, 1], got {albedo}")

    # ea (kPa) from Tmean and RH; Tetens (consistent with psychrometry.py).
    es = 0.6108 * math.exp(17.27 * temp_mean_c / (temp_mean_c + 237.3))
    ea = es * rh_pct / 100.0

    rns = (1.0 - albedo) * solar_radiation_mj
    rso = 0.75 * extraterrestrial_radiation_mj
    if rso <= 0.0:
        raise ValueError(f"Rso computed to {rso}; check solar and extraterrestrial inputs")

    tmax_k = temp_max_c + 273.15
    tmin_k = temp_min_c + 273.15
    t4_mean = (tmax_k**4 + tmin_k**4) / 2.0
    rnl = (
        _SIGMA
        * t4_mean
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * (solar_radiation_mj / rso) - 0.35)
    )
    value = rns - rnl

    assumptions: list[Notice] = []
    if albedo == 0.23:
        assumptions.append(
            Notice(
                code="albedo_default_0_23",
                message=("albedo 0.23 (grass reference) applied; override via albedo"),
            )
        )
    assumptions.append(
        Notice(
            code="rso_sea_level",
            message=(
                "Rso computed at sea level (0.75 * Ra); elevation correction "
                "is out of scope for M11"
            ),
        )
    )

    subject = Subject(calculation="net_radiation", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "solar_radiation_mj": solar_radiation_mj,
            "extraterrestrial_radiation_mj": extraterrestrial_radiation_mj,
            "temp_max_c": temp_max_c,
            "temp_min_c": temp_min_c,
            "temp_mean_c": temp_mean_c,
            "rh_pct": rh_pct,
            "albedo": albedo,
        },
    )
    return ok(
        value=value,
        unit="megajoule/meter**2/day",
        method="allen_1996",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )
