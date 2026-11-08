"""Photosynthetically active radiation: PPFD and DLI.

Primary literature: Thimijan & Heins 1983, HortScience 18(6), 818-822.

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

__all__ = ["dli", "ppfd"]

_CALC_VERSION = "0.1.0"
_PAR_TO_PPFD = 4.57  # umol m-2 s-1 per W m-2 (Thimijan & Heins 1983, Table 2)


def ppfd(*, par_w_m2: float) -> Outcome:
    """PPFD (umol m-2 s-1) from PAR irradiance (W m-2, 400-700 nm).

    ``PPFD = 4.57 * PAR``; factor from Thimijan & Heins 1983 (solar
    spectrum). Assumption ``par_to_ppfd_4_57`` always emitted because
    the factor is empirical.

    Instantaneous PPFD. For a daily total, integrate PPFD over the
    photoperiod with :func:`dli`.
    """
    if par_w_m2 < 0.0:
        raise ValueError(f"par_w_m2 must be >= 0, got {par_w_m2}")
    value = _PAR_TO_PPFD * par_w_m2
    assumptions = [
        Notice(
            code="par_to_ppfd_4_57",
            message=(
                "PAR-to-PPFD factor 4.57 umol/W applied (Thimijan & Heins 1983, solar spectrum)"
            ),
        )
    ]
    subject = Subject(calculation="ppfd", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs={"par_w_m2": par_w_m2})
    return ok(
        value=value,
        unit="micromole/meter**2/second",
        method="thimijan_heins_1983",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )


def dli(*, ppfd_umol: float, photoperiod_hours: float) -> Outcome:
    """Daily light integral (mol m-2 day-1) from PPFD and photoperiod.

    ``DLI = PPFD * photoperiod_hours * 3600 / 1e6``. Pure unit conversion;
    no assumption emitted.

    The caller supplies ``photoperiod_hours`` (for example from
    :func:`agri_core.climate.daylength` or from a sensor).
    """
    if ppfd_umol < 0.0:
        raise ValueError(f"ppfd_umol must be >= 0, got {ppfd_umol}")
    if not (0.0 <= photoperiod_hours <= 24.0):
        raise ValueError(f"photoperiod_hours must be in [0, 24], got {photoperiod_hours}")
    value = ppfd_umol * photoperiod_hours * 3600.0 / 1e6
    subject = Subject(calculation="dli", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "ppfd_umol": ppfd_umol,
            "photoperiod_hours": photoperiod_hours,
        },
    )
    return ok(
        value=value,
        unit="mole/meter**2/day",
        method="thimijan_heins_1983",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )
