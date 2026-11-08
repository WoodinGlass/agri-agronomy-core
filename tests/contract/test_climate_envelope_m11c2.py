"""ADR-009 envelope on the six M11c2 wind / elevation calculators."""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from agri_core.climate import (
    pressure_from_elevation,
    temp_from_elevation,
    wind_direction_from_uv,
    wind_height_adjust,
    wind_run,
    wind_speed_from_uv,
)
from agri_core.models import Result, is_success

pytestmark = pytest.mark.contract

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


_CASES: list[tuple[str, Callable[..., object], dict[str, object]]] = [
    ("wind_speed_from_uv", wind_speed_from_uv, {"u_ms": 3.0, "v_ms": 4.0}),
    (
        "wind_direction_from_uv",
        wind_direction_from_uv,
        {"u_ms": 0.0, "v_ms": -1.0},
    ),
    (
        "wind_height_adjust",
        wind_height_adjust,
        {"speed_ms": 5.0, "measurement_height_m": 10.0},
    ),
    ("wind_run", wind_run, {"speed_ms": 5.0}),
    ("pressure_from_elevation", pressure_from_elevation, {"elevation_m": 1000.0}),
    (
        "temp_from_elevation",
        temp_from_elevation,
        {"temp_c_at_sea_level": 28.0, "elevation_m": 1000.0},
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


def test_wind_direction_calm_refusal_has_envelope() -> None:
    out = wind_direction_from_uv(u_ms=0.0, v_ms=0.0)
    assert out.status == "not_applicable"
    assert out.subject is not None
    assert out.subject.calculation == "wind_direction_from_uv"
    assert out.request_id is not None
