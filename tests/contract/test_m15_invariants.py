"""Cross-module invariants across M15 (ADR-016).

These tests pin the connections between modules that M15 relies on but
that individual module tests do not exercise:

- `evaluate_trapezoid` (P4b) is the one shared classifier.
- `site_suitability` uses `evaluate_trapezoid` (proven by classification).
- `resolve_facts` (P4a) matches `resolve_fact` for M15 params.
- `PropagationOutcome` status set is exact.
- `Outcome` union unchanged (M15 added no member to it).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import get_args

import pytest

from agri_core.models import (
    CategoricalResult,
    EnumSetValue,
    FactRow,
    Outcome,
    ScalarValue,
    TaxonRow,
    TrapezoidValue,
)
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.propagation import PropagationOutcomeAdapter
from agri_core.registry.resolution import FactResolved, resolve_fact, resolve_facts
from agri_core.suitability import Site, site_suitability
from agri_core.thresholds import evaluate_trapezoid

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

_FID_COUNTER = [0]


def _next_fid() -> str:
    _FID_COUNTER[0] += 1
    return f"F{_FID_COUNTER[0]:011d}"


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


def _taxon() -> TaxonRow:
    return TaxonRow(
        taxon_id="T000000001",
        rank="species",
        scientific_name="T",
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        src=["S001"],
    )


def _fact(param, *, value, phase=None) -> FactRow:
    return FactRow(
        fact_id=_next_fid(),
        taxon_id="T000000001",
        parameter=param,
        phase=phase,
        value=value,
        scope={},
        provenance_kind="curated",
        src=["S001"],
        locator="t",
        evidence="B",
        status="approved",
        reviewed_by="r",
        reviewed_at=date(2026, 1, 1),
    )


def _pack_with_site_and_prop() -> InMemoryKnowledgeSet:
    facts = []
    phase_bearing = {"air_temp_day", "air_temp_night", "air_rh", "vpd", "dli"}
    for p in ["soil_ph", "soil_ec", "air_temp_day", "air_temp_night", "air_rh", "vpd", "dli"]:
        ph = "flowering" if p in phase_bearing else None
        facts.append(
            _fact(
                p,
                value=TrapezoidValue(shape="trapezoid", unit="x", pts=(4.5, 6.0, 7.0, 8.5)),
                phase=ph,
            )
        )
    facts.append(
        _fact(
            "propagation_method",
            value=EnumSetValue(shape="enum_set", values=("seed",)),
        )
    )
    facts.append(
        _fact(
            "propagation_duration_days",
            value=ScalarValue(shape="scalar", unit="day", value=30.0),
        )
    )
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=[_taxon()],
        facts=facts,
    )


def test_evaluate_trapezoid_exported() -> None:
    # P4b promoted _evaluate to public evaluate_trapezoid.
    assert evaluate_trapezoid(6.5, (4.5, 6.0, 7.0, 8.5)) == "optimal"
    assert evaluate_trapezoid(5.0, (4.5, 6.0, 7.0, 8.5)) == "suboptimal"
    assert evaluate_trapezoid(4.4, (4.5, 6.0, 7.0, 8.5)) == "critical"


def test_evaluate_trapezoid_matches_site_suitability() -> None:
    pack = _pack_with_site_and_prop()
    site = Site(
        soil_ph=6.5,
        soil_ec=6.5,
        air_temp_day=6.5,
        air_temp_night=6.5,
        air_rh=6.5,
        vpd=6.5,
        dli=6.5,
    )
    out = site_suitability(pack, "T000000001", site, phase="flowering")
    assert isinstance(out, CategoricalResult)
    factor_codes = [w.code for w in out.warnings if w.code.startswith("factor_")]
    # All 7 factors classified optimal because 6.5 lies in (6.0, 7.0).
    assert len(factor_codes) == 7
    assert all(c.endswith("_optimal") for c in factor_codes)


@pytest.mark.parametrize(
    "param",
    ["propagation_method", "propagation_duration_days", "propagation_start_months"],
)
def test_resolve_facts_matches_resolve_fact_for_propagation(param: str) -> None:
    pack = _pack_with_site_and_prop()
    single = resolve_fact(pack, "T000000001", param)
    batch = resolve_facts(pack, "T000000001", [param])
    assert type(single) is type(batch[param])
    if isinstance(single, FactResolved) and isinstance(batch[param], FactResolved):
        assert single.fact.fact_id == batch[param].fact.fact_id
        assert single.value == batch[param].value


def test_propagation_outcome_status_set() -> None:
    schema = PropagationOutcomeAdapter.json_schema(mode="serialization")
    found: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            d = o.get("discriminator")
            if isinstance(d, dict) and d.get("propertyName") == "status":
                found.update(d.get("mapping", {}).keys())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(schema)
    assert found == {
        "ok",
        "unknown",
        "not_applicable",
        "insufficient_input",
        "refer_to_authority",
    }


def test_outcome_union_unchanged_by_m15() -> None:
    union, _ = get_args(Outcome)
    members = get_args(union)
    assert len(members) == 8
    names = {m.__name__ for m in members}
    assert names == {
        "Result",
        "CategoricalResult",
        "InsufficientInput",
        "Unknown",
        "NotApplicable",
        "ReferToLabel",
        "Ambiguous",
        "ReferToAuthority",
    }
    for m in members:
        sf = m.model_fields["status"]
        assert sf.is_required(), f"{m.__name__}.status must be required"
