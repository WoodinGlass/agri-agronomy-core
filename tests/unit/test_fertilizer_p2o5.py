"""fertilize_p2o5: nutrient-to-product conversion with dose-cap enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.fertilizer import fertilize_p2o5
from agri_core.models import Result, is_success
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# T000000001: p2o5_max_per_application = 60 kg/ha (F33)
# T000000008: p2o5_max_per_application = 80 kg/ha (F47)


def test_below_cap_no_clamp(pack) -> None:
    # TSP 46% P2O5, target 40 kg/ha, cap 60
    out = fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=40.0, product_p2o5_pct=46.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(40.0 / 0.46, abs=1e-9)
    assert out.capped is False


def test_at_cap_no_clamp(pack) -> None:
    out = fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=60.0, product_p2o5_pct=46.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(60.0 / 0.46, abs=1e-9)
    assert out.capped is False


def test_above_cap_clamped(pack) -> None:
    out = fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=80.0, product_p2o5_pct=46.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(60.0 / 0.46, abs=1e-9)
    assert out.capped is True
    codes = {w.code for w in out.warnings}
    assert "dose_cap_applied" in codes


def test_woody_taxon_cap(pack) -> None:
    # T000000008 cap = 80 kg/ha
    out = fertilize_p2o5(pack, "T000000008", nutrient_kg_ha=100.0, product_p2o5_pct=46.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(80.0 / 0.46, abs=1e-9)
    assert out.capped is True


def test_product_pct_100(pack) -> None:
    out = fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=40.0, product_p2o5_pct=100.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(40.0, abs=1e-9)


def test_product_pct_zero_raises(pack) -> None:
    with pytest.raises(ValueError, match="product_pct"):
        fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=40.0, product_p2o5_pct=0.0)


def test_product_pct_above_100_raises(pack) -> None:
    with pytest.raises(ValueError, match="product_pct"):
        fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=40.0, product_p2o5_pct=101.0)


def test_negative_nutrient_raises(pack) -> None:
    with pytest.raises(ValueError, match="nutrient_kg_ha"):
        fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=-1.0, product_p2o5_pct=46.0)


def test_cap_missing_refuses(pack) -> None:
    out = fertilize_p2o5(pack, "T000000004", nutrient_kg_ha=40.0, product_p2o5_pct=46.0)
    assert not is_success(out)


def test_envelope(pack) -> None:
    out = fertilize_p2o5(pack, "T000000001", nutrient_kg_ha=40.0, product_p2o5_pct=46.0)
    assert isinstance(out, Result)
    assert out.subject is not None
    assert out.subject.calculation == "fertilize_p2o5"
    assert out.request_id is not None
    assert out.request_id.startswith("req_")
    assert out.provenance.fact_ids
