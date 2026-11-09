"""threshold_check: four-point trapezoid classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.models import CategoricalResult, NotApplicable, Unknown
from agri_core.pack import load_knowledge_set
from agri_core.thresholds import threshold_check

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# T000000001 soil_ph: pts = (4.5, 6.0, 7.0, 8.5)
# T000000001 has all-facts approved for threshold facts.


def test_optimal(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(out, CategoricalResult)
    assert out.status == "ok_category"
    assert out.category == "optimal"
    assert out.label == "Optimal"
    assert out.method == "trapezoid_4pt"


def test_optimal_at_opt_min_boundary(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "optimal"


def test_optimal_at_opt_max_boundary(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=7.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "optimal"


def test_suboptimal_below(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=5.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "suboptimal"


def test_suboptimal_above(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=8.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "suboptimal"


def test_suboptimal_at_abs_min_boundary(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=4.5)
    assert isinstance(out, CategoricalResult)
    assert out.category == "suboptimal"


def test_suboptimal_at_abs_max_boundary(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=8.5)
    assert isinstance(out, CategoricalResult)
    assert out.category == "suboptimal"


def test_critical_below(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=4.4)
    assert isinstance(out, CategoricalResult)
    assert out.category == "critical"


def test_critical_above(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=8.6)
    assert isinstance(out, CategoricalResult)
    assert out.category == "critical"


def test_unknown_taxon(pack) -> None:
    out = threshold_check(pack, "T999999999", "soil_ph", value=6.5)
    assert isinstance(out, Unknown)
    assert out.status == "unknown"


def test_unknown_parameter(pack) -> None:
    out = threshold_check(pack, "T000000001", "not_a_real_param", value=6.5)
    assert isinstance(out, Unknown)
    assert out.status == "unknown"


def test_not_trapezoid(pack) -> None:
    # gdd_base is scalar on T000000001; threshold_check should refuse.
    out = threshold_check(pack, "T000000001", "gdd_base", value=8.0)
    assert isinstance(out, NotApplicable)
    assert out.status == "not_applicable"
    assert "trapezoid" in out.reason.lower()


def test_phase_required_for_phase_parameter(pack) -> None:
    # air_temp_day has phase_set = biological on T000000003
    # (biennial, phase vegetative_year_1).
    out = threshold_check(pack, "T000000003", "air_temp_day", value=20.0)
    # Without a phase, resolve_fact returns InsufficientInput.
    assert out.status == "insufficient_input"


def test_phase_provided_succeeds(pack) -> None:
    # T000000003 air_temp_day at phase=vegetative_year_1,
    # pts = (5.0, 15.0, 22.0, 30.0); value 18 is optimal.
    out = threshold_check(
        pack,
        "T000000003",
        "air_temp_day",
        value=18.0,
        phase="vegetative_year_1",
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "optimal"


def test_envelope_fields(pack) -> None:
    out = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert out.subject.taxon_id == "T000000001"
    assert out.subject.calculation == "threshold_check"
    assert out.request_id is not None
    assert out.request_id.startswith("req_")
    assert out.provenance.fact_ids
    assert out.evidence == ["A"]


def test_request_id_deterministic(pack) -> None:
    a = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    b = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    assert isinstance(a, CategoricalResult)
    assert isinstance(b, CategoricalResult)
    assert a.request_id == b.request_id


def test_request_id_sensitive_to_value(pack) -> None:
    a = threshold_check(pack, "T000000001", "soil_ph", value=6.5)
    b = threshold_check(pack, "T000000001", "soil_ph", value=6.6)
    assert isinstance(a, CategoricalResult)
    assert isinstance(b, CategoricalResult)
    assert a.request_id != b.request_id
