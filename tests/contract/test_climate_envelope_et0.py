"""ADR-009 envelope on the three M11d ET0 calculators."""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from agri_core.climate import (
    et0,
    et0_hargreaves_samani,
    et0_penman_monteith,
)
from agri_core.models import InsufficientInput, Result, is_success

pytestmark = pytest.mark.contract

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


_CASES: list[tuple[str, Callable[..., object], dict[str, object]]] = [
    (
        "et0_penman_monteith",
        et0_penman_monteith,
        {
            "net_radiation_mj": 14.07,
            "temp_mean_c": 25.0,
            "rh_pct": 60.0,
            "wind_speed_2m_ms": 2.0,
        },
    ),
    (
        "et0_hargreaves_samani",
        et0_hargreaves_samani,
        {
            "temp_max_c": 30.0,
            "temp_min_c": 18.0,
            "temp_mean_c": 24.0,
            "extraterrestrial_radiation_mj": 20.0,
        },
    ),
    (
        "et0",
        et0,
        {
            "net_radiation_mj": 14.07,
            "temp_mean_c": 25.0,
            "rh_pct": 60.0,
            "wind_speed_2m_ms": 2.0,
        },
    ),
]


@pytest.mark.parametrize(("name", "fn", "kwargs"), _CASES)
def test_envelope_on_success(
    name: str, fn: Callable[..., object], kwargs: dict[str, object]
) -> None:
    out = fn(**kwargs)
    assert is_success(out)
    assert isinstance(out, Result)
    assert out.subject is not None
    assert re.match(_CALC, out.subject.calculation)
    assert re.match(_SEMVER, out.subject.calculation_version)
    assert out.subject.taxon_id is None
    assert out.subject.scope == {}
    assert out.request_id is not None
    assert re.match(_REQ, out.request_id)
    assert out.provenance.fact_ids == []
    assert out.provenance.pack_version is None
    assert out.evidence == []


@pytest.mark.parametrize(("name", "fn", "kwargs"), _CASES)
def test_request_id_deterministic(
    name: str, fn: Callable[..., object], kwargs: dict[str, object]
) -> None:
    a = fn(**kwargs)
    b = fn(**kwargs)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id == b.request_id


def test_dispatcher_refusal_has_envelope() -> None:
    out = et0(temp_max_c=30.0)
    assert isinstance(out, InsufficientInput)
    assert out.subject is not None
    assert out.subject.calculation == "et0"
    assert out.request_id is not None


def test_dispatcher_rewrap_preserves_method() -> None:
    # When PM is complete, method is PM even though subject.calculation='et0'.
    out = et0(
        net_radiation_mj=14.07,
        temp_mean_c=25.0,
        rh_pct=60.0,
        wind_speed_2m_ms=2.0,
    )
    assert isinstance(out, Result)
    assert out.method == "penman_monteith_1965"


def test_dispatcher_fallback_adds_warning() -> None:
    out = et0(
        temp_max_c=30.0,
        temp_min_c=18.0,
        temp_mean_c=24.0,
        extraterrestrial_radiation_mj=20.0,
    )
    assert isinstance(out, Result)
    assert out.method == "hargreaves_samani_1985"
    codes = {w.code for w in out.warnings}
    assert "used_hargreaves_fallback" in codes
