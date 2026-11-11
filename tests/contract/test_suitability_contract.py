"""site_suitability contract (M15, ADR-016)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from agri_core.models import (
    CategoricalResult,
    FactRow,
    OutcomeAdapter,
    ScalarValue,
    TaxonRow,
    TrapezoidValue,
)
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.suitability import Site, batch_suitability, site_suitability

pytestmark = pytest.mark.contract

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
        facts.append(
            FactRow(
                fact_id=_next_fid(),
                taxon_id="T000000001",
                parameter=f"suitability_weight_{p}",
                phase=None,
                value=ScalarValue(shape="scalar", unit="dimensionless", value=1.0),
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


def test_category_literal() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category in {"suitable", "marginal", "unsuitable"}


def test_method_string_stable() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.method == "suitability_v1"


def test_factor_notice_codes_stable() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    codes = [w.code for w in out.warnings if w.code.startswith("factor_")]
    assert len(codes) == 7
    for c in codes:
        assert re.fullmatch(r"factor_[a-z_]+_(optimal|suboptimal|critical)", c), c


def test_envelope_subject_request_id() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert out.subject.calculation == "site_suitability"
    assert out.request_id is not None
    assert re.match(r"^req_[0-9a-f]{32}$", out.request_id)


def test_batch_identical_to_single() -> None:
    pack = _pack()
    single = site_suitability(pack, "T000000001", _site(), phase="flowering")
    batch = batch_suitability(pack, _site(), ["T000000001"], phase="flowering")
    assert len(batch) == 1
    b = batch[0]
    assert isinstance(single, CategoricalResult)
    assert isinstance(b, CategoricalResult)
    assert single.category == b.category
    assert single.method == b.method
    assert single.request_id == b.request_id


def test_json_roundtrip_all_categories() -> None:
    pack = _pack()
    for site, expected_cat in [
        (_site(), "suitable"),
        (_site(soil_ph=5.0), "marginal"),
        (_site(soil_ph=4.4), "unsuitable"),
    ]:
        out = site_suitability(pack, "T000000001", site, phase="flowering")
        assert isinstance(out, CategoricalResult)
        assert out.category == expected_cat
        dumped = OutcomeAdapter.dump_python(out, mode="json")
        reloaded = OutcomeAdapter.validate_python(dumped)
        assert isinstance(reloaded, CategoricalResult)
        assert reloaded.category == expected_cat
