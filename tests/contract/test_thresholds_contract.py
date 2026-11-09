"""ADR-006/ADR-009 contract: threshold_check returns CategoricalResult.

Golden vectors are inline: value -> expected category, from the sample
pack's T000000001 soil_ph trapezoid (4.5, 6.0, 7.0, 8.5).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agri_core.models import CategoricalResult, OutcomeAdapter
from agri_core.pack import load_knowledge_set
from agri_core.thresholds import threshold_check

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# ─── Golden: soil_ph (4.5, 6.0, 7.0, 8.5) ───


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.4, "critical"),
        (4.5, "suboptimal"),
        (5.0, "suboptimal"),
        (5.99, "suboptimal"),
        (6.0, "optimal"),
        (6.5, "optimal"),
        (7.0, "optimal"),
        (7.01, "suboptimal"),
        (8.5, "suboptimal"),
        (8.51, "critical"),
    ],
)
def test_golden_soil_ph(pack, value: float, expected: str) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=value)
    assert isinstance(out, CategoricalResult)
    assert out.category == expected, f"value {value} -> {out.category}"


# ─── Envelope (ADR-009) ───


def test_envelope_subject(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert re.match(_CALC, out.subject.calculation)
    assert re.match(_SEMVER, out.subject.calculation_version)
    assert out.subject.taxon_id == "T000000001"
    assert out.request_id is not None
    assert re.match(_REQ, out.request_id)


def test_envelope_provenance(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(out, CategoricalResult)
    assert out.provenance.fact_ids, "provenance.fact_ids should name the winner"
    assert out.provenance.pack_version is not None
    assert out.provenance.pack_hash is not None


def test_envelope_evidence(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(out, CategoricalResult)
    assert len(out.evidence) == 1
    assert out.evidence[0] in ("A", "B", "C", "D")


def test_envelope_json_roundtrip(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(out, CategoricalResult)
    # OutcomeAdapter covers CategoricalResult (ADR-006 + ADR-009).
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok_category"
    assert dumped["category"] == "optimal"


# ─── Refusal paths also survive the adapter ───


def test_unknown_roundtrips(pack) -> None:
    out = threshold_check(pack, "T999999999", "soil_ph", value=6.5)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "unknown"
