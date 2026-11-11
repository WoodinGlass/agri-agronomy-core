"""propagation_plan scenario: dated 4-step plan end-to-end."""

from __future__ import annotations

from datetime import date, timedelta
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
from agri_core.propagation import PropagationPlan, propagation_plan

pytestmark = pytest.mark.scenario

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

_FID_COUNTER = [0]


def _next_fid() -> str:
    _FID_COUNTER[0] += 1
    return f"F{_FID_COUNTER[0]:011d}"


def _pack(
    *,
    method_values=("seed",),
    start_months=None,
) -> InMemoryKnowledgeSet:
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
            value=EnumSetValue(shape="enum_set", values=method_values),
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
    if start_months is not None:
        facts.append(
            FactRow(
                fact_id=_next_fid(),
                taxon_id="T000000001",
                parameter="propagation_start_months",
                phase=None,
                value=EnumSetValue(shape="enum_set", values=start_months),
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


def test_4_step_dated_plan_end_to_end() -> None:
    pack = _pack(start_months=("4",))
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    assert len(out.steps) == 4
    # span: 1 + 30 + 7 + 1 = 39 days, contiguous
    total_span = (out.steps[-1].end_date - out.steps[0].start_date).days + 1
    assert total_span == 39
    for i in range(1, len(out.steps)):
        prev = out.steps[i - 1]
        cur = out.steps[i]
        assert cur.start_date == prev.end_date + timedelta(days=1)


def test_winter_start_shifts_to_spring() -> None:
    pack = _pack(start_months=("3", "4", "5"))
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 11, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    assert out.start_date == date(2027, 3, 15)
    assert any(w.code == "propagation_start_shifted" for w in out.warnings)


def test_method_rejected_scenario() -> None:
    pack = _pack(method_values=("stem_cutting",))
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="grafting",
    )
    assert isinstance(out, NotApplicable)
    assert "grafting" in out.reason
