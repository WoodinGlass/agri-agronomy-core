"""ADR-006/ADR-009 contract: irrigation modes.

- field_etc returns Result.
- paddy_awd and container_band return CategoricalResult.
- Refusals and not_applicable propagate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agri_core.irrigation import (
    irrigate_container_band,
    irrigate_field_etc,
    irrigate_paddy_awd,
)
from agri_core.models import CategoricalResult, OutcomeAdapter, Result
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# ─── field_etc: Result ───


def test_field_etc_is_result(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="midseason",
        et0_mm_day=5.0,
    )
    assert isinstance(out, Result)
    assert out.subject is not None
    assert re.match(_CALC, out.subject.calculation)
    assert re.match(_SEMVER, out.subject.calculation_version)
    assert out.request_id is not None
    assert re.match(_REQ, out.request_id)


def test_field_etc_json_roundtrip(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="midseason",
        et0_mm_day=5.0,
    )
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok"
    assert dumped["unit"] == "millimeter/day"


# ─── paddy_awd: CategoricalResult ───


def test_paddy_awd_is_categorical(pack) -> None:
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=5.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category in {"reflood", "hold"}
    assert out.subject is not None
    assert out.subject.calculation == "irrigate_paddy_awd"


def test_paddy_awd_json_roundtrip(pack) -> None:
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=5.0,
    )
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok_category"
    assert dumped["category"] in {"reflood", "hold"}


# ─── container_band: CategoricalResult ───


def test_container_band_is_categorical(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=70.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category in {"irrigate", "hold", "drain"}


def test_container_band_json_roundtrip(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=70.0,
    )
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok_category"
    assert dumped["category"] in {"irrigate", "hold", "drain"}


# ─── determinism ───


def test_all_modes_deterministic(pack) -> None:
    a1 = irrigate_field_etc(pack, "T000000001", phase="midseason", et0_mm_day=5.0)
    a2 = irrigate_field_etc(pack, "T000000001", phase="midseason", et0_mm_day=5.0)
    assert isinstance(a1, Result)
    assert isinstance(a2, Result)
    assert a1.request_id == a2.request_id

    b1 = irrigate_paddy_awd(pack, "T000000002", phase="maturity", water_table_depth_cm=5.0)
    b2 = irrigate_paddy_awd(pack, "T000000002", phase="maturity", water_table_depth_cm=5.0)
    assert isinstance(b1, CategoricalResult)
    assert isinstance(b2, CategoricalResult)
    assert b1.request_id == b2.request_id

    c1 = irrigate_container_band(pack, "T000000004", current_moisture_pct=70.0)
    c2 = irrigate_container_band(pack, "T000000004", current_moisture_pct=70.0)
    assert isinstance(c1, CategoricalResult)
    assert isinstance(c2, CategoricalResult)
    assert c1.request_id == c2.request_id
