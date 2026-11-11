"""site_suitability against the ACTUAL sample pack (M15 e2e).

All P4b suitability tests use from_rows in-memory packs. This module is
the milestone-acceptance end-to-end test: it loads the shipped sample
pack and exercises the unsuitable case against T000000009 (tropical
annual added in P6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.models import CategoricalResult, Unknown
from agri_core.pack import load_knowledge_set
from agri_core.suitability import Site, batch_suitability, site_suitability

pytestmark = pytest.mark.scenario

_REPO = Path(__file__).resolve().parents[2]
_SAMPLE = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(_SAMPLE, allow_synthetic=True)


def _tropical_site() -> Site:
    # All values inside T000000009 optimal ranges (from P6 facts).
    return Site(
        soil_ph=6.5,
        soil_ec=1.5,
        air_temp_day=30.0,
        air_temp_night=25.0,
        air_rh=70.0,
        vpd=1.0,
        dli=25.0,
    )


def _temperate_site() -> Site:
    # air_temp_day=5.0 < abs_min=20 (T000000009 tropical) -> critical.
    return Site(
        soil_ph=6.5,
        soil_ec=1.5,
        air_temp_day=5.0,
        air_temp_night=25.0,
        air_rh=70.0,
        vpd=1.0,
        dli=25.0,
    )


def test_sample_pack_suitable_against_real_pack(pack) -> None:
    out = site_suitability(pack, "T000000009", _tropical_site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "suitable"


def test_sample_pack_unsuitable_against_real_pack(pack) -> None:
    out = site_suitability(pack, "T000000009", _temperate_site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "unsuitable"
    codes = [w.code for w in out.warnings if w.code.startswith("factor_")]
    assert "factor_air_temp_day_critical" in codes


def test_sample_pack_batch_mixed_outcomes(pack) -> None:
    ids = ["T000000009", "T000000001", "T000000005"]
    results = batch_suitability(pack, _tropical_site(), ids, phase="flowering")
    assert len(results) == 3
    # T000000009: has all 7 site params -> CategoricalResult suitable
    assert isinstance(results[0], CategoricalResult)
    assert results[0].category == "suitable"
    # T000000001: only soil_ph, missing other 6 -> Unknown
    assert isinstance(results[1], Unknown)
    # T000000005: fungal, no facts -> Unknown
    assert isinstance(results[2], Unknown)
