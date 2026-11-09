"""ADR-009 envelope on the 8 M12c functions."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta

import pytest

from agri_core.climate import (
    bio_01,
    bio_06,
    bio_07,
    bio_12,
    bio_13,
    bio_14,
    bio_15,
    threshold_index,
)
from agri_core.models import Result, is_success

pytestmark = pytest.mark.contract

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"

_TEMP = [20.0] * 12
_PRECIP = [100.0] * 12
_DATES = [date(2026, 1, 1) + timedelta(days=i) for i in range(7)]
_TMIN = [5.0, 3.0, 10.0, -2.0, -1.0, 15.0, 20.0]


_CASES: list[tuple[str, Callable[..., object], dict[str, object]]] = [
    ("bio_01", bio_01, {"monthly_temp_c": _TEMP}),
    ("bio_06", bio_06, {"monthly_temp_c": _TEMP}),
    ("bio_07", bio_07, {"monthly_temp_c": _TEMP}),
    ("bio_12", bio_12, {"monthly_precip_mm": _PRECIP}),
    ("bio_13", bio_13, {"monthly_precip_mm": _PRECIP}),
    ("bio_14", bio_14, {"monthly_precip_mm": _PRECIP}),
    ("bio_15", bio_15, {"monthly_precip_mm": _PRECIP}),
    (
        "threshold_index",
        threshold_index,
        {"index_name": "frost_days", "dates": _DATES, "values": _TMIN},
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


def test_threshold_index_refusal_has_envelope() -> None:
    out = threshold_index(index_name="frost_days", dates=[], values=[])
    assert out.status == "insufficient_input"
    assert out.subject is not None
    assert out.subject.calculation == "threshold_index"
    assert out.request_id is not None
