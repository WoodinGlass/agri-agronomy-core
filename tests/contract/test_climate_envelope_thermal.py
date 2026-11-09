"""ADR-009 envelope on the M12b thermal calculators."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta

import pytest

from agri_core.climate import (
    chill_hours,
    gdd_method_1,
    gdd_method_2,
    gdd_series,
    photothermal_units,
    utah_chill_units,
)
from agri_core.models import Result, is_success

pytestmark = pytest.mark.contract

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"

_BASE_TS = datetime(2026, 1, 1, 0, 0, 0)
_TS_24H = [_BASE_TS + timedelta(hours=i) for i in range(24)]
_TEMP_24H = [5.0] * 24


_CASES: list[tuple[str, Callable[..., object], dict[str, object]]] = [
    (
        "gdd_method_1",
        gdd_method_1,
        {"temp_max_c": 25.0, "temp_min_c": 15.0, "tbase_c": 10.0},
    ),
    (
        "gdd_method_2",
        gdd_method_2,
        {"temp_max_c": 25.0, "temp_min_c": 15.0, "tbase_c": 10.0},
    ),
    (
        "gdd_series",
        gdd_series,
        {
            "dates": [date(2026, 1, 1), date(2026, 1, 2)],
            "temp_max_c": [25.0, 30.0],
            "temp_min_c": [15.0, 20.0],
            "tbase_c": 10.0,
        },
    ),
    (
        "chill_hours",
        chill_hours,
        {"timestamps": _TS_24H, "temps_c": _TEMP_24H},
    ),
    (
        "utah_chill_units",
        utah_chill_units,
        {"timestamps": _TS_24H, "temps_c": _TEMP_24H},
    ),
    (
        "photothermal_units",
        photothermal_units,
        {"gdd": 30.0, "daylength_hours": 12.0},
    ),
]


@pytest.mark.parametrize(("name", "fn", "kwargs"), _CASES)
def test_envelope(name: str, fn: Callable[..., object], kwargs: dict[str, object]) -> None:
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


def test_gdd_series_refusal_has_envelope() -> None:
    out = gdd_series(
        dates=[date(2026, 1, 1), date(2026, 1, 4)],
        temp_max_c=[25.0, 22.0],
        temp_min_c=[15.0, 12.0],
        tbase_c=10.0,
    )
    assert out.status == "insufficient_input"
    assert out.subject is not None
    assert out.subject.calculation == "gdd_series"
    assert out.request_id is not None
