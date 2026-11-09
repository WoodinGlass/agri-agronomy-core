"""ADR-006/ADR-009 contract: media calculators."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agri_core.media import check_water_quality, compute_rsc, compute_sar
from agri_core.models import CategoricalResult, OutcomeAdapter, Result
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"

_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


def test_sar_is_result() -> None:
    out = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(out, Result)
    assert re.match(_REQ, out.request_id)
    assert re.match(_SEMVER, out.subject.calculation_version)


def test_rsc_is_result() -> None:
    out = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(out, Result)
    assert re.match(_REQ, out.request_id)
    assert re.match(_SEMVER, out.subject.calculation_version)


def test_wq_is_categorical(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=25.0)
    assert isinstance(out, CategoricalResult)
    assert out.category in {"ok", "exceed_ec", "exceed_temp", "exceed_both"}


def test_sar_json_roundtrip() -> None:
    out = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok"
    assert dumped["unit"] == "dimensionless"
    assert dumped["method"] == "richards_1954_sar"


def test_rsc_json_roundtrip() -> None:
    out = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok"
    assert dumped["unit"] == "dimensionless"
    assert dumped["method"] == "eaton_1950_rsc"


def test_wq_json_roundtrip(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=2.5, temp_c=30.0)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok_category"
    assert dumped["category"] == "exceed_both"


def test_deterministic_pure_math() -> None:
    a1 = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    a2 = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(a1, Result)
    assert isinstance(a2, Result)
    assert a1.request_id == a2.request_id

    b1 = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    b2 = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(b1, Result)
    assert isinstance(b2, Result)
    assert b1.request_id == b2.request_id


def test_all_four_categories(pack) -> None:
    cases = [
        (1.5, 25.0, "ok"),
        (2.5, 25.0, "exceed_ec"),
        (1.5, 30.0, "exceed_temp"),
        (2.5, 30.0, "exceed_both"),
    ]
    for ec, temp, expected in cases:
        out = check_water_quality(pack, "T000000002", ec_ds_m=ec, temp_c=temp)
        assert isinstance(out, CategoricalResult)
        assert out.category == expected
