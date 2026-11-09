"""compute_sar: Sodium Adsorption Ratio (Richards 1954)."""

from __future__ import annotations

import math

import pytest

from agri_core.media import compute_sar
from agri_core.models import Result

pytestmark = pytest.mark.unit


def test_basic_formula() -> None:
    # 10 / sqrt((5 + 3) / 2) = 10 / 2 = 5.0
    out = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(5.0, abs=1e-9)


def test_zero_sodium() -> None:
    out = compute_sar(na_meq_l=0.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_zero_denominator_raises() -> None:
    with pytest.raises(ValueError, match="ca_meq_l"):
        compute_sar(na_meq_l=10.0, ca_meq_l=0.0, mg_meq_l=0.0)


def test_negative_na_raises() -> None:
    with pytest.raises(ValueError, match="na_meq_l"):
        compute_sar(na_meq_l=-1.0, ca_meq_l=5.0, mg_meq_l=3.0)


def test_unit_dimensionless() -> None:
    out = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(out, Result)
    assert out.unit == "dimensionless"


def test_method_richards() -> None:
    out = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(out, Result)
    assert out.method == "richards_1954_sar"


def test_envelope() -> None:
    out = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(out, Result)
    assert out.subject is not None
    assert out.subject.calculation == "compute_sar"
    assert out.subject.taxon_id is None
    assert out.request_id is not None
    assert out.request_id.startswith("req_")
    # No pack read: empty provenance, empty evidence
    assert out.provenance.fact_ids == []
    assert out.evidence == []


def test_determinism() -> None:
    a = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    b = compute_sar(na_meq_l=10.0, ca_meq_l=5.0, mg_meq_l=3.0)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id == b.request_id
    assert a.value == b.value


def test_known_vector() -> None:
    # 25.0 / sqrt((12.5 + 7.5) / 2) = 25.0 / sqrt(10) = 7.90569415042...
    out = compute_sar(na_meq_l=25.0, ca_meq_l=12.5, mg_meq_l=7.5)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(25.0 / math.sqrt(10.0), abs=1e-9)
