"""ADR-009 envelope on the four M11c radiation / PAR calculators."""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from agri_core.climate import dli, net_radiation, ppfd, solar_radiation
from agri_core.models import Result, is_success

pytestmark = pytest.mark.contract

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


_CASES: list[tuple[str, Callable[..., object], dict[str, object]]] = [
    (
        "solar_radiation",
        solar_radiation,
        {
            "temp_max_c": 30.0,
            "temp_min_c": 18.0,
            "extraterrestrial_radiation_mj": 41.88,
        },
    ),
    (
        "net_radiation",
        net_radiation,
        {
            "solar_radiation_mj": 23.21,
            "extraterrestrial_radiation_mj": 41.88,
            "temp_max_c": 30.0,
            "temp_min_c": 18.0,
            "temp_mean_c": 24.0,
            "rh_pct": 60.0,
        },
    ),
    ("ppfd", ppfd, {"par_w_m2": 500.0}),
    ("dli", dli, {"ppfd_umol": 2285.0, "photoperiod_hours": 12.0}),
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


def test_different_inputs_give_different_request_id() -> None:
    a = ppfd(par_w_m2=500.0)
    b = ppfd(par_w_m2=501.0)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id != b.request_id
