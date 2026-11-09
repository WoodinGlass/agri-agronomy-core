"""irrigate_paddy_awd: categorical reflood / hold."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.irrigation import irrigate_paddy_awd
from agri_core.models import CategoricalResult, Unknown
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# T000000002: awd_reflood_depth = 10.0 cm; must_flood_phases = [vegetative, flowering]


def test_phase_in_must_flood_refloods(pack) -> None:
    # Depth shallow, but phase=vegetative in must_flood_phases -> reflood
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="vegetative",
        water_table_depth_cm=2.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "reflood"
    assert out.label == "Reflood"


def test_phase_in_must_flood_flowering(pack) -> None:
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="flowering",
        water_table_depth_cm=0.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "reflood"


def test_phase_not_in_must_flood_shallow_holds(pack) -> None:
    # maturity not in must_flood; depth < reflood (10) -> hold
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=5.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "hold"


def test_phase_not_in_must_flood_deep_refloods(pack) -> None:
    # maturity; depth 12 >= 10 -> reflood
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=12.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "reflood"


def test_at_reflood_threshold(pack) -> None:
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=10.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "reflood"


def test_unknown_taxon_refused(pack) -> None:
    out = irrigate_paddy_awd(
        pack,
        "T999999999",
        phase="vegetative",
        water_table_depth_cm=5.0,
    )
    assert isinstance(out, Unknown)


def test_envelope(pack) -> None:
    out = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=5.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert out.subject.calculation == "irrigate_paddy_awd"
    assert out.request_id is not None


def test_request_id_deterministic(pack) -> None:
    a = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=5.0,
    )
    b = irrigate_paddy_awd(
        pack,
        "T000000002",
        phase="maturity",
        water_table_depth_cm=5.0,
    )
    assert isinstance(a, CategoricalResult)
    assert isinstance(b, CategoricalResult)
    assert a.request_id == b.request_id
