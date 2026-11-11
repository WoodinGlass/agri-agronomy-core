"""site_suitability scenario: unsuitable is a real answer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.models import CategoricalResult, FactRow, TaxonRow, TrapezoidValue
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.suitability import Site, site_suitability

pytestmark = pytest.mark.scenario

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")
_SITE_PARAMS = ("soil_ph", "soil_ec", "air_temp_day", "air_temp_night", "air_rh", "vpd", "dli")
_PHASE_BEARING = {"air_temp_day", "air_temp_night", "air_rh", "vpd", "dli"}
_PTS = (4.5, 6.0, 7.0, 8.5)

_FID_COUNTER = [0]


def _next_fid() -> str:
    _FID_COUNTER[0] += 1
    return f"F{_FID_COUNTER[0]:011d}"


def _pack() -> InMemoryKnowledgeSet:
    manifest = PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )
    taxon = TaxonRow(
        taxon_id="T000000001",
        rank="species",
        scientific_name="T",
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        src=["S001"],
    )
    facts = []
    for p in _SITE_PARAMS:
        ph = "flowering" if p in _PHASE_BEARING else None
        facts.append(
            FactRow(
                fact_id=_next_fid(),
                taxon_id="T000000001",
                parameter=p,
                phase=ph,
                value=TrapezoidValue(shape="trapezoid", unit="x", pts=_PTS),
                scope={},
                provenance_kind="curated",
                src=["S001"],
                locator="t",
                evidence="B",
                status="approved",
                reviewed_by="r",
                reviewed_at=date(2026, 1, 1),
            )
        )
    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=[taxon],
        facts=facts,
    )


def _site(**overrides) -> Site:
    base = {p: 6.5 for p in _SITE_PARAMS}
    base.update(overrides)
    return Site(**base)


def test_unsuitable_scenario_air_temp_out_of_range() -> None:
    """Air temp outside abs_max -> critical -> unsuitable."""
    out = site_suitability(_pack(), "T000000001", _site(air_temp_day=40.0), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "unsuitable"
    codes = [w.code for w in out.warnings if w.code.startswith("factor_")]
    assert "factor_air_temp_day_critical" in codes


def test_suitable_scenario() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "suitable"


def test_marginal_scenario() -> None:
    out = site_suitability(_pack(), "T000000001", _site(vpd=5.0), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "marginal"
    codes = [w.code for w in out.warnings if w.code.startswith("factor_")]
    assert "factor_vpd_suboptimal" in codes
