"""Reference evapotranspiration: Penman-Monteith and Hargreaves-Samani.

Primary literature:
- Monteith 1965, Symp. Soc. Exp. Biol. 19, 205-234 (Penman-Monteith form).
- Allen 1996, J. Irrig. Drain. Eng. 122(2), 97-106 (eqs 6-8, standardized
  form; sea-level psychrometric constant used).
- Hargreaves & Samani 1985, J. Irrig. Drain. Eng. 111(2), 113-124 (eq 52).

No pack is read; ``provenance`` is empty and ``evidence`` is ``[]``.
Every estimated input is reported as an assumption.
"""

from __future__ import annotations

import math

from agri_core.models import (
    Notice,
    Outcome,
    Provenance,
    Result,
    Subject,
    compute_request_id,
    insufficient_input,
    ok,
)

__all__ = ["et0", "et0_hargreaves_samani", "et0_penman_monteith"]

_CALC_VERSION = "0.1.0"
_SEA_LEVEL_P_KPA = 101.3
_GAMMA_SEA_LEVEL = 0.000665 * _SEA_LEVEL_P_KPA  # ~0.06737 kPa/degC


def et0_penman_monteith(
    *,
    net_radiation_mj: float,
    temp_mean_c: float,
    rh_pct: float,
    wind_speed_2m_ms: float,
) -> Outcome:
    """Penman-Monteith ET0 (mm day-1) per Allen 1996 eq 6.

    ``ET0 = [0.408 * Delta * Rn + gamma * (900 / (T + 273)) * u2 * VPD]
    / [Delta + gamma * (1 + 0.34 * u2)]``

    - ``Rn`` (net radiation, MJ m-2 day-1) is supplied by the caller, for
      example from :func:`agri_core.climate.net_radiation`.
    - Soil heat flux ``G`` is set to zero (Allen 1996 daily formulation).
    - The psychrometric constant ``gamma`` is computed at sea level
      (101.3 kPa); the elevation correction is out of scope for M11.
      Assumption ``psychrometric_constant_sea_level`` (always).
    """
    if temp_mean_c <= -237.3:
        raise ValueError(f"temp_mean_c must be > -237.3 (Kelvin offset), got {temp_mean_c}")
    if not (0.0 < rh_pct <= 100.0):
        raise ValueError(f"rh_pct must be in (0, 100], got {rh_pct}")
    if wind_speed_2m_ms < 0.0:
        raise ValueError(f"wind_speed_2m_ms must be >= 0, got {wind_speed_2m_ms}")

    # Saturation vapor pressure (Tetens), actual vapor pressure, VPD.
    es = 0.6108 * math.exp(17.27 * temp_mean_c / (temp_mean_c + 237.3))
    ea = es * rh_pct / 100.0
    vpd = es - ea

    # Slope of the saturation vapor pressure curve (kPa / degC).
    delta = 4098.0 * es / ((temp_mean_c + 237.3) ** 2)

    # Psychrometric constant at sea level (kPa / degC).
    gamma = _GAMMA_SEA_LEVEL

    t_k = temp_mean_c + 273.0
    u2 = wind_speed_2m_ms

    numerator = 0.408 * delta * net_radiation_mj + gamma * (900.0 / t_k) * u2 * vpd
    denominator = delta + gamma * (1.0 + 0.34 * u2)
    if denominator <= 0.0:
        raise ValueError(
            f"Penman-Monteith denominator <= 0 (delta={delta}, gamma={gamma}, u2={u2})"
        )
    value = numerator / denominator

    assumptions = [
        Notice(
            code="psychrometric_constant_sea_level",
            message=(
                "psychrometric constant 0.06737 kPa/degC (sea level) applied; "
                "elevation correction is out of scope for M11"
            ),
        )
    ]

    subject = Subject(calculation="et0_penman_monteith", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "net_radiation_mj": net_radiation_mj,
            "temp_mean_c": temp_mean_c,
            "rh_pct": rh_pct,
            "wind_speed_2m_ms": wind_speed_2m_ms,
        },
    )
    return ok(
        value=value,
        unit="millimeter/day",
        method="penman_monteith_1965",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )


def et0_hargreaves_samani(
    *,
    temp_max_c: float,
    temp_min_c: float,
    temp_mean_c: float,
    extraterrestrial_radiation_mj: float,
) -> Outcome:
    """Hargreaves-Samani ET0 (mm day-1) per Hargreaves & Samani 1985 eq 52.

    ``ET0 = 0.0023 * (Tmean + 17.8) * sqrt(Tmax - Tmin) * Ra``

    ``Ra`` (extraterrestrial radiation, MJ m-2 day-1) is supplied by the
    caller, for example from
    :func:`agri_core.climate.extraterrestrial_radiation`.
    """
    if temp_max_c < temp_min_c:
        raise ValueError(f"temp_max_c must be >= temp_min_c, got {temp_max_c} < {temp_min_c}")
    if extraterrestrial_radiation_mj < 0.0:
        raise ValueError(
            f"extraterrestrial_radiation_mj must be >= 0, got {extraterrestrial_radiation_mj}"
        )

    dt = temp_max_c - temp_min_c
    value = 0.0023 * (temp_mean_c + 17.8) * math.sqrt(dt) * extraterrestrial_radiation_mj

    subject = Subject(calculation="et0_hargreaves_samani", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "temp_max_c": temp_max_c,
            "temp_min_c": temp_min_c,
            "temp_mean_c": temp_mean_c,
            "extraterrestrial_radiation_mj": extraterrestrial_radiation_mj,
        },
    )
    return ok(
        value=value,
        unit="millimeter/day",
        method="hargreaves_samani_1985",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def _rewrap_as_et0(
    inner: Result,
    *,
    inputs: dict[str, float | None],
    extra_warnings: list[Notice] | None = None,
) -> Result:
    """Rewrite the envelope so ``subject.calculation == 'et0'``.

    ``method`` is passed through from the underlying calculator, so the
    caller can tell which method actually produced the value.
    """
    subject = Subject(calculation="et0", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=dict(inputs))
    return inner.model_copy(
        update={
            "subject": subject,
            "request_id": request_id,
            "warnings": inner.warnings + (extra_warnings or []),
        }
    )


def et0(
    *,
    net_radiation_mj: float | None = None,
    temp_mean_c: float | None = None,
    rh_pct: float | None = None,
    wind_speed_2m_ms: float | None = None,
    temp_max_c: float | None = None,
    temp_min_c: float | None = None,
    extraterrestrial_radiation_mj: float | None = None,
) -> Outcome:
    """Reference ET0 dispatcher (mm day-1).

    Prefer Penman-Monteith when all four of its inputs are provided;
    otherwise fall back to Hargreaves-Samani when all four of its inputs
    are provided. The fallback emits a ``used_hargreaves_fallback``
    warning. When neither set is complete, returns ``insufficient_input``
    whose ``missing`` lists the union of absent fields (both sets).

    ``subject.calculation`` is always ``"et0"``; ``method`` on the
    returned ``Result`` is ``"penman_monteith_1965"`` or
    ``"hargreaves_samani_1985"`` so the caller knows which one ran.
    """
    inputs_all: dict[str, float | None] = {
        "net_radiation_mj": net_radiation_mj,
        "temp_mean_c": temp_mean_c,
        "rh_pct": rh_pct,
        "wind_speed_2m_ms": wind_speed_2m_ms,
        "temp_max_c": temp_max_c,
        "temp_min_c": temp_min_c,
        "extraterrestrial_radiation_mj": extraterrestrial_radiation_mj,
    }

    pm_names = ("net_radiation_mj", "temp_mean_c", "rh_pct", "wind_speed_2m_ms")
    hs_names = (
        "temp_max_c",
        "temp_min_c",
        "temp_mean_c",
        "extraterrestrial_radiation_mj",
    )

    pm_complete = all(inputs_all[n] is not None for n in pm_names)
    hs_complete = all(inputs_all[n] is not None for n in hs_names)

    if pm_complete:
        inner = et0_penman_monteith(
            net_radiation_mj=net_radiation_mj,  # type: ignore[arg-type]
            temp_mean_c=temp_mean_c,  # type: ignore[arg-type]
            rh_pct=rh_pct,  # type: ignore[arg-type]
            wind_speed_2m_ms=wind_speed_2m_ms,  # type: ignore[arg-type]
        )
        if isinstance(inner, Result):
            return _rewrap_as_et0(inner, inputs=inputs_all)
        return inner

    if hs_complete:
        inner = et0_hargreaves_samani(
            temp_max_c=temp_max_c,  # type: ignore[arg-type]
            temp_min_c=temp_min_c,  # type: ignore[arg-type]
            temp_mean_c=temp_mean_c,  # type: ignore[arg-type]
            extraterrestrial_radiation_mj=extraterrestrial_radiation_mj,  # type: ignore[arg-type]
        )
        if isinstance(inner, Result):
            return _rewrap_as_et0(
                inner,
                inputs=inputs_all,
                extra_warnings=[
                    Notice(
                        code="used_hargreaves_fallback",
                        message=("Penman-Monteith inputs incomplete; used Hargreaves-Samani 1985"),
                    )
                ],
            )
        return inner

    # Neither complete: insufficient_input with the union of missing names.
    missing: list[str] = []
    if not pm_complete:
        missing.extend(n for n in pm_names if inputs_all[n] is None)
    if not hs_complete:
        missing.extend(n for n in hs_names if inputs_all[n] is None)

    subject = Subject(calculation="et0", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=dict(inputs_all))
    return insufficient_input(
        missing=missing,
        subject=subject,
        request_id=request_id,
    )
