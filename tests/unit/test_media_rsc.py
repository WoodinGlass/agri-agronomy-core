"""compute_rsc: Residual Sodium Carbonate (Eaton 1950)."""

from __future__ import annotations

import pytest

from agri_core.media import compute_rsc
from agri_core.models import Result

pytestmark = pytest.mark.unit


def test_positive_rsc() -> None:
    # (2 + 3) - (1 + 1) = 3.0
    out = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(3.0, abs=1e-9)


def test_negative_rsc_valid() -> None:
    # (0 + 0) - (5 + 5) = -10.0 (valid, not an error)
    out = compute_rsc(co3_meq_l=0.0, hco3_meq_l=0.0, ca_meq_l=5.0, mg_meq_l=5.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(-10.0, abs=1e-9)


def test_zero_inputs() -> None:
    out = compute_rsc(co3_meq_l=0.0, hco3_meq_l=0.0, ca_meq_l=0.0, mg_meq_l=0.0)
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_negative_input_raises() -> None:
    with pytest.raises(ValueError, match="co3_meq_l"):
        compute_rsc(co3_meq_l=-1.0, hco3_meq_l=0.0, ca_meq_l=0.0, mg_meq_l=0.0)


def test_unit_dimensionless() -> None:
    out = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(out, Result)
    assert out.unit == "dimensionless"


def test_method_eaton() -> None:
    out = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(out, Result)
    assert out.method == "eaton_1950_rsc"


def test_envelope() -> None:
    out = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(out, Result)
    assert out.subject is not None
    assert out.subject.calculation == "compute_rsc"
    assert out.request_id is not None
    assert out.request_id.startswith("req_")


def test_determinism() -> None:
    a = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    b = compute_rsc(co3_meq_l=2.0, hco3_meq_l=3.0, ca_meq_l=1.0, mg_meq_l=1.0)
    assert isinstance(a, Result)
    assert isinstance(b, Result)
    assert a.request_id == b.request_id
    assert a.value == b.value
