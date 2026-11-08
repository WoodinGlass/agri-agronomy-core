"""ADR-009 envelope on every M11b calculator.

For every public function in ``agri_core.climate``:

- Returns a value whose ``status`` is one of the ``Outcome`` variants.
- On success: ``subject`` is populated (``calculation`` = snake_case,
  ``calculation_version`` semver), ``request_id`` starts with ``req_``,
  ``provenance`` is empty (no pack read).
- Determinism: same inputs -> same ``request_id``.
- Distinct inputs -> distinct ``request_id``.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from agri_core.climate import (
    clearness_index,
    daylength,
    dew_point,
    extraterrestrial_radiation,
    vpd,
    wet_bulb,
)
from agri_core.models import Result, is_success

pytestmark = pytest.mark.contract

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


_CASES: list[tuple[str, Callable[..., object], dict[str, object]]] = [
    ("vpd", vpd, {"temp_c": 25.0, "rh_pct": 60.0}),
    ("dew_point", dew_point, {"temp_c": 25.0, "rh_pct": 60.0}),
    ("wet_bulb", wet_bulb, {"temp_c": 25.0, "rh_pct": 60.0}),
    ("daylength", daylength, {"latitude_deg": 40.0, "day_of_year": 172}),
    (
        "extraterrestrial_radiation",
        extraterrestrial_radiation,
        {"latitude_deg": 40.0, "day_of_year": 172},
    ),
    (
        "clearness_index",
        clearness_index,
        {"solar_radiation_mj": 25.0, "extraterrestrial_radiation_mj": 41.88},
    ),
]


@pytest.mark.parametrize(("name", "fn", "kwargs"), _CASES)
def test_envelope_on_success(
    name: str, fn: Callable[..., object], kwargs: dict[str, object]
) -> None:
    out = fn(**kwargs)
    assert is_success(out), f"{name} did not succeed: {out}"
    assert isinstance(out, Result)

    assert out.subject is not None
    assert re.match(_CALC, out.subject.calculation)
    assert re.match(_SEMVER, out.subject.calculation_version)
    assert out.subject.taxon_id is None
    assert out.subject.taxon_name is None
    assert out.subject.scope == {}

    assert out.request_id is not None
    assert re.match(_REQ, out.request_id)

    # No pack was read.
    assert out.provenance.fact_ids == []
    assert out.provenance.pack_version is None
    assert out.provenance.pack_hash is None
    assert out.provenance.source_ids == []
    assert out.evidence == []


@pytest.mark.parametrize(("name", "fn", "kwargs"), _CASES)
def test_request_id_deterministic(
    name: str, fn: Callable[..., object], kwargs: dict[str, object]
) -> None:
    a = fn(**kwargs)
    b = fn(**kwargs)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id == b.request_id, f"{name}: request_id not deterministic"


def test_request_id_differs_on_inputs() -> None:
    a = vpd(temp_c=25.0, rh_pct=60.0)
    b = vpd(temp_c=25.0, rh_pct=61.0)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id != b.request_id


def test_clearness_index_refusal_also_has_envelope() -> None:
    out = clearness_index(solar_radiation_mj=0.0, extraterrestrial_radiation_mj=0.0)
    assert out.status == "not_applicable"
    assert out.subject is not None
    assert out.subject.calculation == "clearness_index"
    assert out.request_id is not None
