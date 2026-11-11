"""resolve_facts contract: batch identical to per-parameter resolve_fact."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.models import (
    FactRow,
    ScalarValue,
    TaxonRow,
    TrapezoidValue,
    Unknown,
)
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.registry import resolve_fact, resolve_facts
from agri_core.registry.resolution import FactResolved

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")


def _manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _make_ks(*, taxa=(), facts=()):
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=taxa,
        facts=facts,
    )


def _taxon(tid: str = "T000000001") -> TaxonRow:
    return TaxonRow(
        taxon_id=tid,
        rank="species",
        scientific_name=f"Testus {tid}",
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        src=["S001"],
    )


def _fact(
    fact_id: str,
    parameter: str = "soil_ph",
    *,
    value=None,
    status: str = "approved",
) -> FactRow:
    return FactRow(
        fact_id=fact_id,
        taxon_id="T000000001",
        parameter=parameter,
        phase=None,
        value=value or TrapezoidValue(shape="trapezoid", unit="pH", pts=(4.5, 6.0, 7.0, 8.5)),
        scope={},
        provenance_kind="curated",
        src=["S001"],
        locator="test",
        evidence="B",
        status=status,
        reviewed_by="tester",
        reviewed_at=date(2026, 1, 1),
    )


def _sample_pack() -> InMemoryKnowledgeSet:
    return _make_ks(
        taxa=[_taxon()],
        facts=[
            _fact("F00000000001", "soil_ph"),
            _fact(
                "F00000000002",
                "gdd_base",
                value=ScalarValue(shape="scalar", unit="degree_Celsius", value=8.0),
            ),
            _fact(
                "F00000000003",
                "gdd_upper",
                value=ScalarValue(shape="scalar", unit="degree_Celsius", value=35.0),
            ),
        ],
    )


# ---------------- Tests ----------------


def test_empty_parameters_returns_empty_dict() -> None:
    pack = _sample_pack()
    assert resolve_facts(pack, "T000000001", []) == {}


def test_single_param_matches_resolve_fact() -> None:
    pack = _sample_pack()
    single = resolve_fact(pack, "T000000001", "soil_ph")
    batch = resolve_facts(pack, "T000000001", ["soil_ph"])
    assert isinstance(single, FactResolved)
    assert isinstance(batch["soil_ph"], FactResolved)
    assert single.fact.fact_id == batch["soil_ph"].fact.fact_id
    assert single.value == batch["soil_ph"].value
    assert single.provenance.fact_ids == batch["soil_ph"].provenance.fact_ids
    assert single.min_status_applied == batch["soil_ph"].min_status_applied


def test_multi_param_matches_per_param() -> None:
    pack = _sample_pack()
    params = ["soil_ph", "gdd_base", "gdd_upper"]
    batch = resolve_facts(pack, "T000000001", params)
    assert set(batch.keys()) == set(params)
    for p in params:
        single = resolve_fact(pack, "T000000001", p)
        assert type(single) is type(batch[p]), f"param {p}: type mismatch"
        if isinstance(single, FactResolved) and isinstance(batch[p], FactResolved):
            assert single.fact.fact_id == batch[p].fact.fact_id, f"param {p}: fact_id"
            assert single.value == batch[p].value, f"param {p}: value"


def test_unknown_taxon_maps_all_params_to_unknown() -> None:
    pack = _sample_pack()
    result = resolve_facts(pack, "T999999999", ["soil_ph", "gdd_base"])
    assert set(result.keys()) == {"soil_ph", "gdd_base"}
    assert all(isinstance(v, Unknown) for v in result.values())
    for v in result.values():
        assert isinstance(v, Unknown)
        assert v.code == "no_match"
    # Shared instance so callers can compare identity without re-parsing.
    assert result["soil_ph"] is result["gdd_base"]


def test_duplicate_parameters_dedup() -> None:
    pack = _sample_pack()
    result = resolve_facts(pack, "T000000001", ["soil_ph", "soil_ph"])
    assert len(result) == 1
    assert "soil_ph" in result


def test_order_preserved() -> None:
    pack = _sample_pack()
    params = ["gdd_base", "soil_ph", "gdd_upper"]
    result = resolve_facts(pack, "T000000001", params)
    assert list(result.keys()) == params


def test_mixed_outcomes() -> None:
    pack = _make_ks(
        taxa=[_taxon()],
        facts=[_fact("F00000000001", "soil_ph")],
    )
    result = resolve_facts(pack, "T000000001", ["soil_ph", "not_a_real_param"])
    assert isinstance(result["soil_ph"], FactResolved)
    assert isinstance(result["not_a_real_param"], Unknown)
    assert result["not_a_real_param"].code == "no_match"


def test_safety_floor_applies_per_param() -> None:
    pack = _make_ks(
        taxa=[_taxon()],
        facts=[
            _fact("F00000000001", "soil_ph"),
            _fact(
                "F00000000002",
                "n_max_per_application",
                value=ScalarValue(shape="scalar", unit="kilogram/hectare", value=80.0),
                status="reviewed",
            ),
        ],
    )
    result = resolve_facts(
        pack,
        "T000000001",
        ["soil_ph", "n_max_per_application"],
        min_status="draft",
    )
    assert isinstance(result["soil_ph"], FactResolved)
    assert isinstance(result["n_max_per_application"], FactResolved)
    assert not any(w.code == "safety_min_status_raised" for w in result["soil_ph"].warnings)
    assert any(
        w.code == "safety_min_status_raised" for w in result["n_max_per_application"].warnings
    )


def test_filter_counts_isolated_per_param() -> None:
    pack = _make_ks(
        taxa=[_taxon()],
        facts=[_fact("F00000000001", "soil_ph", status="draft")],
    )
    result = resolve_facts(pack, "T000000001", ["soil_ph", "gdd_base"], min_status="approved")
    assert isinstance(result["soil_ph"], Unknown)
    assert result["soil_ph"].code == "below_min_status"
    assert isinstance(result["gdd_base"], Unknown)
    assert result["gdd_base"].code == "no_match"


def test_determinism_repeat() -> None:
    pack = _sample_pack()
    params = ["soil_ph", "gdd_base"]
    a = resolve_facts(pack, "T000000001", params)
    b = resolve_facts(pack, "T000000001", params)
    for p in params:
        assert type(a[p]) is type(b[p])
        if isinstance(a[p], FactResolved) and isinstance(b[p], FactResolved):
            assert a[p].fact.fact_id == b[p].fact.fact_id
            assert a[p].value == b[p].value
