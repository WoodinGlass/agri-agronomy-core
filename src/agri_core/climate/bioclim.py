"""Bioclimatic variables (subset of Nix 1986 BIO01-BIO19).

Primary literature: Nix 1986, in: Longley (ed.) Atlas of Australian
Resources, CSIRO.

Each function takes exactly 12 monthly values and returns one BIO
variable. Full BIO01-BIO19 (including BIO02-BIO05, BIO08-BIO11,
BIO16-BIO19) is backlog; the seven shipped here cover the most common
use cases.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence

from agri_core.models import (
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    not_applicable,
    ok,
)

__all__ = ["bio_01", "bio_06", "bio_07", "bio_12", "bio_13", "bio_14", "bio_15"]

_CALC_VERSION = "0.1.0"
_N_MONTHS = 12


def _check_months(name: str, monthly: Sequence[float]) -> None:
    if len(monthly) != _N_MONTHS:
        raise ValueError(f"{name}: expected {_N_MONTHS} monthly values, got {len(monthly)}")


def _make_result(
    value: float,
    unit: str,
    calculation: str,
    inputs: Mapping[str, object],
) -> Outcome:
    subject = Subject(calculation=calculation, calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=dict(inputs))
    return ok(
        value=value,
        unit=unit,
        method="nix_1986",
        provenance=Provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def bio_01(*, monthly_temp_c: Sequence[float]) -> Outcome:
    """BIO01: annual mean temperature (degC); Nix 1986."""
    _check_months("bio_01", monthly_temp_c)
    value = statistics.fmean(monthly_temp_c)
    return _make_result(
        value,
        "degree_Celsius",
        "bio_01",
        {"monthly_temp_c": list(monthly_temp_c)},
    )


def bio_06(*, monthly_temp_c: Sequence[float]) -> Outcome:
    """BIO06: minimum temperature of the coldest month (degC); Nix 1986."""
    _check_months("bio_06", monthly_temp_c)
    value = float(min(monthly_temp_c))
    return _make_result(
        value,
        "degree_Celsius",
        "bio_06",
        {"monthly_temp_c": list(monthly_temp_c)},
    )


def bio_07(*, monthly_temp_c: Sequence[float]) -> Outcome:
    """BIO07: temperature annual range (degC); Nix 1986."""
    _check_months("bio_07", monthly_temp_c)
    value = float(max(monthly_temp_c) - min(monthly_temp_c))
    return _make_result(
        value,
        "degree_Celsius",
        "bio_07",
        {"monthly_temp_c": list(monthly_temp_c)},
    )


def bio_12(*, monthly_precip_mm: Sequence[float]) -> Outcome:
    """BIO12: annual precipitation (mm); Nix 1986."""
    _check_months("bio_12", monthly_precip_mm)
    value = float(sum(monthly_precip_mm))
    return _make_result(
        value,
        "millimeter",
        "bio_12",
        {"monthly_precip_mm": list(monthly_precip_mm)},
    )


def bio_13(*, monthly_precip_mm: Sequence[float]) -> Outcome:
    """BIO13: precipitation of the wettest month (mm); Nix 1986."""
    _check_months("bio_13", monthly_precip_mm)
    value = float(max(monthly_precip_mm))
    return _make_result(
        value,
        "millimeter",
        "bio_13",
        {"monthly_precip_mm": list(monthly_precip_mm)},
    )


def bio_14(*, monthly_precip_mm: Sequence[float]) -> Outcome:
    """BIO14: precipitation of the driest month (mm); Nix 1986."""
    _check_months("bio_14", monthly_precip_mm)
    value = float(min(monthly_precip_mm))
    return _make_result(
        value,
        "millimeter",
        "bio_14",
        {"monthly_precip_mm": list(monthly_precip_mm)},
    )


def bio_15(*, monthly_precip_mm: Sequence[float]) -> Outcome:
    """BIO15: precipitation seasonality as CV % (sample stdev); Nix 1986.

    ``CV = 100 * stdev / mean`` with sample standard deviation
    (``ddof=1``). Returns ``not_applicable`` when the mean is zero (CV is
    undefined).
    """
    _check_months("bio_15", monthly_precip_mm)
    mean = statistics.fmean(monthly_precip_mm)
    inputs = {"monthly_precip_mm": list(monthly_precip_mm)}
    if mean <= 0.0:
        subject = Subject(calculation="bio_15", calculation_version=_CALC_VERSION)
        request_id = compute_request_id(subject=subject, inputs=inputs)
        return not_applicable(
            reason="precipitation mean is zero; coefficient of variation is undefined",
            subject=subject,
            request_id=request_id,
        )
    stdev = statistics.stdev(monthly_precip_mm)  # sample (ddof=1)
    value = 100.0 * stdev / mean
    return _make_result(value, "percent", "bio_15", inputs)
