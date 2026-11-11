"""propagation_plan contract (M15, ADR-016)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from agri_core.models import (
    EnumSetValue,
    FactRow,
    NotApplicable,
    ScalarValue,
    TaxonRow,
)
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.propagation import (
    PropagationOutcomeAdapter,
    PropagationPlan,
    propagation_plan,
)

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

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
    facts = [
        FactRow(
            fact_id=_next_fid(),
            taxon_id="T000000001",
            parameter="propagation_method",
            phase=None,
            value=EnumSetValue(shape="enum_set", values=("seed",)),
            scope={},
            provenance_kind="curated",
            src=["S001"],
            locator="t",
            evidence="B",
            status="approved",
            reviewed_by="r",
            reviewed_at=date(2026, 1, 1),
        ),
        FactRow(
            fact_id=_next_fid(),
            taxon_id="T000000001",
            parameter="propagation_duration_days",
            phase=None,
            value=ScalarValue(shape="scalar", unit="day", value=30.0),
            scope={},
            provenance_kind="curated",
            src=["S001"],
            locator="t",
            evidence="B",
            status="approved",
            reviewed_by="r",
            reviewed_at=date(2026, 1, 1),
        ),
    ]
    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=[taxon],
        facts=facts,
    )


def _plan() -> PropagationPlan:
    out = propagation_plan(
        _pack(),
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    return out


def test_status_ok() -> None:
    assert _plan().status == "ok"


def test_method_preserved() -> None:
    assert _plan().method == "seed"


def test_envelope_subject_request_id() -> None:
    p = _plan()
    assert p.subject is not None
    assert p.subject.calculation == "propagation_plan"
    assert p.request_id is not None
    assert re.match(r"^req_[0-9a-f]{32}$", p.request_id)


def test_provenance_fact_ids() -> None:
    p = _plan()
    # two facts used (method + duration); start_months missing
    assert len(p.provenance.fact_ids) == 2


def test_json_roundtrip_plan() -> None:
    p = _plan()
    dumped = PropagationOutcomeAdapter.dump_python(p, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, PropagationPlan)
    assert reloaded.method == p.method
    assert reloaded.start_date == p.start_date
    assert len(reloaded.steps) == len(p.steps)


def test_json_roundtrip_not_applicable() -> None:
    pack = _pack()  # pack has method_values=("seed",)
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="grafting",
    )
    assert isinstance(out, NotApplicable)
    dumped = PropagationOutcomeAdapter.dump_python(out, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, NotApplicable)
    assert reloaded.status == "not_applicable"
