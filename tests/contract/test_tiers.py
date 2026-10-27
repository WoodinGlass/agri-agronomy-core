"""Tier derivation (M7-5)."""

from __future__ import annotations

import json
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack import load_knowledge_set
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.pack.tiers import Tier, derive_all_tiers, derive_tier

pytestmark = pytest.mark.contract


def _sample_ks():
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    return load_knowledge_set(src, allow_synthetic=True)


def _sample_dict() -> Dictionary:
    from agri_core.pack.loader import _default_dictionary

    return _default_dictionary()


def _param(key: str, **overrides):
    defaults = {
        "key": key,
        "stage": "other",
        "shape": "scalar",
        "unit": "dimensionless",
        "physical_range": (0.0, 1000.0),
        "phase_set": "none",
        "applies_to": {"organism_groups": ["vascular_plant"]},
        "scope_keys": [],
        "used_by": ["test_module"],
        "tier_required": True,
        "safety_class": "none",
        "kind": "core",
        "description": f"test param {key}",
        "introduced_in": "1.0.0",
    }
    defaults.update(overrides)
    if defaults.get("safety_class", "none") != "none" and not defaults.get("rationale"):
        defaults["rationale"] = f"test rationale for {key}"
    return defaults


def _mini_dict(*, params: dict[str, dict], phases_by_archetype=None) -> Dictionary:
    return Dictionary.model_validate(
        {
            "version": "0.0.1",
            "parameters": {k: _param(k, **v) for k, v in params.items()},
            "phases_by_archetype": phases_by_archetype or {},
        }
    )


def _mini_ks(
    dictionary,
    *,
    taxon_id,
    archetype="annual",
    uses=("vegetable",),
    organism_group="vascular_plant",
    facts=None,
):
    taxon = TaxonRow(
        taxon_id=taxon_id,
        rank="species",
        scientific_name=f"Test {taxon_id}",
        organism_group=organism_group,
        archetype=archetype,
        uses=list(uses),
        traits=[],
        src=["S001"],
    )
    manifest = PackManifest(
        name="test",
        version="1.0.0",
        schema_version=1,
        engine_min="0.0.0",
        dictionary_min="1.0.0",
        synthetic=True,
    )
    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=dictionary.version,
        verified=True,
        taxa=[taxon],
        facts=facts or [],
    )


def _fact(
    fact_id,
    taxon_id,
    parameter,
    *,
    status="approved",
    phase=None,
    reviewed_by=None,
    superseded_by=None,
    value_shape="scalar",
):
    if value_shape == "unknown":
        value = {"shape": "unknown", "reason": "n/a"}
    else:
        value = {"shape": "scalar", "unit": "dimensionless", "value": 1.0}
    return FactRow(
        fact_id=fact_id,
        taxon_id=taxon_id,
        parameter=parameter,
        phase=phase,
        value=value,
        scope={},
        provenance_kind="curated",
        src=["S001"],
        locator="x",
        evidence="A",
        status=status,
        reviewed_by=reviewed_by,
        reviewed_at="2026-01-01" if reviewed_by else None,
        superseded_by=superseded_by,
    )


def test_sample_all_taxa_t1_except_fungal_t0() -> None:
    ks = _sample_ks()
    d = _sample_dict()
    results = derive_all_tiers(ks, d)
    assert len(results) == 8
    by_tier: dict[Tier, list[str]] = {}
    for tid, r in results.items():
        by_tier.setdefault(r.tier, []).append(tid)
    assert by_tier.get(Tier.T0) == ["T000000005"]
    assert set(by_tier.get(Tier.T1, [])) == {
        "T000000001",
        "T000000002",
        "T000000003",
        "T000000004",
        "T000000006",
        "T000000007",
        "T000000008",
    }
    assert Tier.T2 not in by_tier
    assert Tier.T3 not in by_tier


def test_sample_required_params_is_five() -> None:
    ks = _sample_ks()
    d = _sample_dict()
    r = derive_tier(ks, "T000000001", d)
    assert set(r.required_params) == {
        "managed_cycle",
        "phase_duration",
        "air_temp_day",
        "air_temp_night",
        "air_rh",
    }


def test_sample_missing_params_exposed() -> None:
    ks = _sample_ks()
    d = _sample_dict()
    r = derive_tier(ks, "T000000001", d)
    assert r.tier == Tier.T1
    assert set(r.missing_params) == set(r.required_params)


def test_mini_t0_no_facts() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(d, taxon_id="T000000001", facts=[])
    assert derive_tier(ks, "T000000001", d).tier == Tier.T0


def test_mini_t1_one_draft_fact() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="draft"),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T1


def test_mini_t2_requires_reviewed() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="reviewed", reviewed_by=["r1"]),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T2


def test_mini_t3_requires_approved() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="approved", reviewed_by=["r1"]),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T3


def test_phase_partial_does_not_satisfy() -> None:
    d = _mini_dict(
        params={"p1": {"phase_set": "biological"}},
        phases_by_archetype={"annual": ["a", "b"]},
    )
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact(
                "F00000000001", "T000000001", "p1", status="reviewed", reviewed_by=["r1"], phase="a"
            ),
        ],
    )
    r = derive_tier(ks, "T000000001", d)
    assert r.tier == Tier.T1
    assert "p1" in r.missing_params


def test_phase_full_satisfies() -> None:
    d = _mini_dict(
        params={"p1": {"phase_set": "biological"}},
        phases_by_archetype={"annual": ["a", "b"]},
    )
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact(
                "F00000000001", "T000000001", "p1", status="reviewed", reviewed_by=["r1"], phase="a"
            ),
            _fact(
                "F00000000002", "T000000001", "p1", status="reviewed", reviewed_by=["r1"], phase="b"
            ),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T2


def test_unknown_without_review_does_not_bump_tier() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="draft", value_shape="unknown"),
        ],
    )
    r = derive_tier(ks, "T000000001", d)
    assert r.tier == Tier.T1
    assert "p1" in r.missing_params


def test_unknown_with_review_does_satisfy() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact(
                "F00000000001",
                "T000000001",
                "p1",
                status="reviewed",
                reviewed_by=["r1"],
                value_shape="unknown",
            ),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T2


def test_safety_critical_single_reviewer_not_t3() -> None:
    d = _mini_dict(
        params={
            "p1": {},
            "cap": {"tier_required": False, "safety_class": "dose_cap"},
        }
    )
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="approved", reviewed_by=["r1"]),
            _fact("F00000000002", "T000000001", "cap", status="approved", reviewed_by=["r1"]),
        ],
    )
    r = derive_tier(ks, "T000000001", d)
    assert r.tier == Tier.T2
    assert "cap" in r.missing_params


def test_safety_critical_two_reviewers_t3() -> None:
    d = _mini_dict(
        params={
            "p1": {},
            "cap": {"tier_required": False, "safety_class": "dose_cap"},
        }
    )
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="approved", reviewed_by=["r1"]),
            _fact("F00000000002", "T000000001", "cap", status="approved", reviewed_by=["r1", "r2"]),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T3


def test_superseded_fact_not_counted_for_tier() -> None:
    d = _mini_dict(params={"p1": {}})
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="reviewed", reviewed_by=["r1"]),
            _fact("F00000000002", "T000000001", "p1", status="draft", superseded_by="F00000000001"),
        ],
    )
    assert derive_tier(ks, "T000000001", d).tier == Tier.T2


def test_system_scoped_param_not_gating_tier() -> None:
    d = _mini_dict(
        params={
            "p1": {},
            "scoped": {
                "tier_required": True,
                "applies_to": {
                    "organism_groups": ["vascular_plant"],
                    "systems": ["field"],
                },
            },
        }
    )
    ks = _mini_ks(
        d,
        taxon_id="T000000001",
        facts=[
            _fact("F00000000001", "T000000001", "p1", status="approved", reviewed_by=["r1"]),
        ],
    )
    r = derive_tier(ks, "T000000001", d)
    assert r.tier == Tier.T3
    assert "scoped" in r.system_gaps
    assert "scoped" not in r.required_params


def test_tier_monotone_with_status() -> None:
    d = _mini_dict(params={"p1": {}})
    prev = -1
    for status in ["draft", "reviewed", "approved"]:
        ks = _mini_ks(
            d,
            taxon_id="T000000001",
            facts=[
                _fact(
                    "F00000000001",
                    "T000000001",
                    "p1",
                    status=status,
                    reviewed_by=["r1"] if status != "draft" else None,
                ),
            ],
        )
        t = derive_tier(ks, "T000000001", d).tier
        v = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}[t.value]
        assert v >= prev
        prev = v


def test_tier_deterministic() -> None:
    ks = _sample_ks()
    d = _sample_dict()
    r1 = derive_all_tiers(ks, d)
    r2 = derive_all_tiers(ks, d)
    for tid in r1:
        assert r1[tid].model_dump_json() == r2[tid].model_dump_json()


def test_tier_json_roundtrip() -> None:
    ks = _sample_ks()
    d = _sample_dict()
    r = derive_tier(ks, "T000000001", d)
    data = json.loads(r.model_dump_json())
    assert data["taxon_id"] == "T000000001"
    assert data["tier"] == "T1"
    assert isinstance(data["required_params"], list)
