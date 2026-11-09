"""ADR-006/ADR-009 contract: fertilizer calculators."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agri_core.fertilizer import fertilize_k2o, fertilize_n, fertilize_p2o5
from agri_core.models import OutcomeAdapter, Result
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


def test_fertilize_n_is_result(pack) -> None:
    out = fertilize_n(pack, "T000000001", nutrient_kg_ha=50.0, product_n_pct=46.0)
    assert isinstance(out, Result)
    assert out.subject is not None
    assert re.match(_CALC, out.subject.calculation)
    assert re.match(_SEMVER, out.subject.calculation_version)
    assert out.request_id is not None
    assert re.match(_REQ, out.request_id)


def test_fertilize_n_json_roundtrip(pack) -> None:
    out = fertilize_n(pack, "T000000001", nutrient_kg_ha=50.0, product_n_pct=46.0)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok"
    assert dumped["unit"] == "kilogram/hectare"
    assert dumped["capped"] is False


def test_fertilize_capped_json(pack) -> None:
    out = fertilize_n(pack, "T000000001", nutrient_kg_ha=100.0, product_n_pct=46.0)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok"
    assert dumped["capped"] is True
    codes = {w["code"] for w in dumped["warnings"]}
    assert "dose_cap_applied" in codes


def test_fertilize_deterministic(pack) -> None:
    a = fertilize_n(pack, "T000000001", nutrient_kg_ha=50.0, product_n_pct=46.0)
    b = fertilize_n(pack, "T000000001", nutrient_kg_ha=50.0, product_n_pct=46.0)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id == b.request_id
    assert a.value == b.value


def test_all_three_share_method(pack) -> None:
    outs = [
        fertilize_n(pack, "T000000001", nutrient_kg_ha=50.0, product_n_pct=46.0),
        fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=40.0, product_p2o5_pct=46.0),
        fertilize_k2o(pack, "T000000001", nutrient_kg_ha=60.0, product_k2o_pct=60.0),
    ]
    for out in outs:
        assert isinstance(out, Result)
        assert out.method == "product_composition_division"
        assert out.unit == "kilogram/hectare"
