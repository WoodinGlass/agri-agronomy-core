"""propagation_plan: unit coverage (M15, ADR-016)."""

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
    Unknown,
)
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.propagation import PropagationPlan, propagation_plan

pytestmark = pytest.mark.unit

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


def _fact(param: str, *, value, phase=None) -> FactRow:
    return FactRow(
        fact_id=_next_fid(),
        taxon_id="T000000001",
        parameter=param,
        phase=phase,
        value=value,
        scope={},
        provenance_kind="curated",
        src=["S001"],
        locator="test",
        evidence="B",
        status="approved",
        reviewed_by="tester",
        reviewed_at=date(2026, 1, 1),
    )


def _make_pack(
    *,
    method_values: list[str] | None = None,
    duration: float | None = 30.0,
    start_months: list[str] | None = None,
) -> InMemoryKnowledgeSet:
    facts = []
    if method_values is not None:
        facts.append(
            _fact(
                "propagation_method",
                value=EnumSetValue(
                    shape="enum_set",
                    values=tuple(method_values),
                ),
            )
        )
    if duration is not None:
        facts.append(
            _fact(
                "propagation_duration_days",
                value=ScalarValue(
                    shape="scalar",
                    unit="day",
                    value=duration,
                ),
            )
        )
    if start_months is not None:
        facts.append(
            _fact(
                "propagation_start_months",
                value=EnumSetValue(
                    shape="enum_set",
                    values=tuple(start_months),
                ),
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


def test_happy_path_4_steps() -> None:
    pack = _make_pack(
        method_values=["seed"],
        duration=30.0,
        start_months=["4"],
    )
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    assert out.start_date == date(2026, 4, 15)
    assert len(out.steps) == 4
    names = [s.step_name for s in out.steps]
    assert names == ["prepare", "propagate", "establish", "ready"]
    assert out.steps[0].duration_days == 1
    assert out.steps[1].duration_days == 30
    assert out.steps[2].duration_days == 7
    assert out.steps[3].duration_days == 1


def test_unknown_taxon() -> None:
    pack = _make_pack(method_values=["seed"])
    out = propagation_plan(
        pack,
        "T999999999",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, Unknown)
    assert out.code == "no_match"


def test_missing_method_fact() -> None:
    pack = _make_pack(method_values=None)
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, Unknown)


def test_missing_duration_fact() -> None:
    pack = _make_pack(method_values=["seed"], duration=None)
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, Unknown)


def test_method_not_in_fact_values() -> None:
    pack = _make_pack(method_values=["stem_cutting"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, NotApplicable)
    assert "seed" in out.reason
    assert "not recorded" in out.reason


def test_method_validation_msg() -> None:
    pack = _make_pack(method_values=["stem_cutting", "grafting"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, NotApplicable)
    assert "'seed'" in out.reason


def test_missing_start_months_any_month_default() -> None:
    pack = _make_pack(method_values=["seed"], start_months=None)
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    codes = [a.code for a in out.assumptions]
    assert "propagation_start_months_defaulted" in codes


def test_no_shift_when_month_valid() -> None:
    pack = _make_pack(method_values=["seed"], start_months=["4", "5"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    warnings = [w.code for w in out.warnings]
    assert "propagation_start_shifted" not in warnings
    assert out.start_date == date(2026, 4, 15)


def test_shift_to_next_valid_month() -> None:
    pack = _make_pack(method_values=["seed"], start_months=["3"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 2, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    assert out.start_date == date(2026, 3, 15)
    codes = [w.code for w in out.warnings]
    assert "propagation_start_shifted" in codes


def test_day_clamped_to_month_end() -> None:
    pack = _make_pack(method_values=["seed"], start_months=["2"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 1, 31),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    assert out.start_date == date(2026, 2, 28)


def test_step_durations_defaulted_notice() -> None:
    pack = _make_pack(method_values=["seed"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    codes = [a.code for a in out.assumptions]
    assert "propagation_step_durations_defaulted" in codes


def test_non_integral_duration_refused() -> None:
    pack = _make_pack(method_values=["seed"], duration=30.5)
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, NotApplicable)
    assert "positive integer" in out.reason


def test_steps_contiguous() -> None:
    pack = _make_pack(method_values=["seed"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
    for i in range(1, len(out.steps)):
        prev = out.steps[i - 1]
        cur = out.steps[i]
        assert cur.start_date == prev.end_date + timedelta(days=1)


def test_non_phase_params_no_phase_needed() -> None:
    # All three propagation params have phase_set=none; phase=None is fine.
    pack = _make_pack(method_values=["seed"])
    out = propagation_plan(
        pack,
        "T000000001",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, PropagationPlan)
