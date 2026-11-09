"""irrigate_container_band: categorical irrigate / hold / drain."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.irrigation import irrigate_container_band
from agri_core.models import CategoricalResult, Unknown
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# T000000004: moisture_band = (30, 60, 80, 95); opt_min=60, opt_max=80


def test_below_opt_min_irrigate(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=40.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "irrigate"


def test_at_opt_min_hold(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=60.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "hold"


def test_in_band_hold(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=70.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "hold"


def test_at_opt_max_hold(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=80.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "hold"


def test_above_opt_max_drain(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=90.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "drain"


def test_negative_moisture_raises(pack) -> None:
    with pytest.raises(ValueError, match="current_moisture_pct"):
        irrigate_container_band(
            pack,
            "T000000004",
            current_moisture_pct=-1.0,
        )


def test_above_100_raises(pack) -> None:
    with pytest.raises(ValueError, match="current_moisture_pct"):
        irrigate_container_band(
            pack,
            "T000000004",
            current_moisture_pct=101.0,
        )


def test_unknown_taxon_refused(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T999999999",
        current_moisture_pct=70.0,
    )
    assert isinstance(out, Unknown)


def test_envelope(pack) -> None:
    out = irrigate_container_band(
        pack,
        "T000000004",
        current_moisture_pct=70.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert out.subject.calculation == "irrigate_container_band"
    assert out.request_id is not None
    assert out.provenance.fact_ids
