"""Propagation models + schema contract (M15, ADR-016)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from agri_core.models import (
    InsufficientInput,
    NotApplicable,
    Provenance,
    ReferToAuthority,
    Subject,
    Unknown,
)
from agri_core.propagation.models import (
    PropagationOutcomeAdapter,
    PropagationPlan,
    PropagationStep,
)

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _REPO / "schema"


def _prov() -> Provenance:
    return Provenance()


def _subject() -> Subject:
    return Subject(
        taxon_id="T000000001",
        scope={},
        calculation="propagation_plan",
        calculation_version="0.1.0",
    )


def _step(
    name: str = "prepare",
    start: str = "2026-01-01",
    end: str = "2026-01-05",
) -> PropagationStep:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return PropagationStep(
        step_name=name,  # type: ignore[arg-type]
        start_date=s,
        end_date=e,
        duration_days=(e - s).days + 1,
    )


def _plan_minimal() -> PropagationPlan:
    return PropagationPlan(
        status="ok",
        taxon_id="T000000001",
        method="seed",
        start_date=date(2026, 1, 1),
        steps=[_step()],
        provenance=_prov(),
        evidence=["B"],
        assumptions=[],
        warnings=[],
    )


def _walk_discriminators(o: Any, found: set[str], *, property_name: str) -> None:
    if isinstance(o, dict):
        disc = o.get("discriminator")
        if (
            isinstance(disc, dict)
            and disc.get("propertyName") == property_name
            and "mapping" in disc
        ):
            found.update(disc["mapping"].keys())
        for v in o.values():
            _walk_discriminators(v, found, property_name=property_name)
    elif isinstance(o, list):
        for v in o:
            _walk_discriminators(v, found, property_name=property_name)


# ---- schema existence + drift ------------------------------------------------


def test_propagation_plan_schema_exists() -> None:
    p = _SCHEMA_DIR / "propagation_plan.schema.json"
    assert p.is_file(), f"{p} missing; run `python scripts/gen_schemas.py`"


def test_propagation_plan_schema_matches_model() -> None:
    committed = json.loads(
        (_SCHEMA_DIR / "propagation_plan.schema.json").read_text(encoding="utf-8")
    )
    regenerated = TypeAdapter(PropagationPlan).json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/propagation_plan.schema.json is out of date; run `python scripts/gen_schemas.py`"
    )


def test_propagation_outcome_schema_exists() -> None:
    p = _SCHEMA_DIR / "propagation_outcome.schema.json"
    assert p.is_file(), f"{p} missing; run `python scripts/gen_schemas.py`"


def test_propagation_outcome_schema_matches_model() -> None:
    committed = json.loads(
        (_SCHEMA_DIR / "propagation_outcome.schema.json").read_text(encoding="utf-8")
    )
    regenerated = PropagationOutcomeAdapter.json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/propagation_outcome.schema.json is out of date; run `python scripts/gen_schemas.py`"
    )


def test_propagation_outcome_status_set_is_exact() -> None:
    found: set[str] = set()
    _walk_discriminators(
        PropagationOutcomeAdapter.json_schema(mode="serialization"),
        found,
        property_name="status",
    )
    assert found == {
        "ok",
        "unknown",
        "not_applicable",
        "insufficient_input",
        "refer_to_authority",
    }


# ---- roundtrip through adapter (all 5 members) -------------------------------


def test_outcome_roundtrip_ok() -> None:
    plan = _plan_minimal()
    dumped = PropagationOutcomeAdapter.dump_python(plan, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, PropagationPlan)
    assert reloaded.status == "ok"


def test_outcome_roundtrip_unknown() -> None:
    o = Unknown(status="unknown", reason="no facts for scope")
    dumped = PropagationOutcomeAdapter.dump_python(o, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, Unknown)


def test_outcome_roundtrip_not_applicable() -> None:
    o = NotApplicable(status="not_applicable", reason="method not recorded")
    dumped = PropagationOutcomeAdapter.dump_python(o, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, NotApplicable)


def test_outcome_roundtrip_insufficient_input() -> None:
    o = InsufficientInput(status="insufficient_input", missing=["start_date"])
    dumped = PropagationOutcomeAdapter.dump_python(o, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, InsufficientInput)


def test_outcome_roundtrip_refer_to_authority() -> None:
    o = ReferToAuthority(
        status="refer_to_authority",
        reason="protected species",
        flags=["CITES"],
    )
    dumped = PropagationOutcomeAdapter.dump_python(o, mode="json")
    reloaded = PropagationOutcomeAdapter.validate_python(dumped)
    assert isinstance(reloaded, ReferToAuthority)


# ---- validator coverage ------------------------------------------------------


def test_step_rejects_inconsistent_duration() -> None:
    with pytest.raises(ValidationError, match="duration_days"):
        PropagationStep(
            step_name="prepare",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 5),
            duration_days=100,
        )


def test_step_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        PropagationStep(
            step_name="prepare",
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 1),
            duration_days=1,
        )


def test_plan_rejects_non_contiguous_steps() -> None:
    with pytest.raises(ValidationError, match="one day after"):
        PropagationPlan(
            status="ok",
            taxon_id="T000000001",
            method="seed",
            start_date=date(2026, 1, 1),
            steps=[
                _step("prepare", "2026-01-01", "2026-01-10"),
                _step("propagate", "2026-01-15", "2026-01-20"),
            ],
            provenance=_prov(),
            evidence=["B"],
            assumptions=[],
            warnings=[],
        )


def test_plan_rejects_unknown_step_name() -> None:
    with pytest.raises(ValidationError, match="literal_error"):
        PropagationStep(
            step_name="ferment",  # type: ignore[arg-type]
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 5),
            duration_days=5,
        )


def test_plan_rejects_request_id_without_subject() -> None:
    with pytest.raises(ValidationError, match="request_id requires subject"):
        PropagationPlan(
            status="ok",
            taxon_id="T000000001",
            method="seed",
            start_date=date(2026, 1, 1),
            steps=[_step()],
            request_id="req_" + "0" * 32,
            provenance=_prov(),
            evidence=["B"],
            assumptions=[],
            warnings=[],
        )
