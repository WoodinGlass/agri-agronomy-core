"""Tests for CategoricalResult and is_success (ADR-006)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.models import (
    CategoricalResult,
    OutcomeAdapter,
    Provenance,
    Result,
    is_success,
    ok,
    ok_category,
    unknown,
)
from agri_core.models.notices import Notice

pytestmark = pytest.mark.unit


def _prov() -> Provenance:
    return Provenance(
        fact_ids=["F00000000001"],
        pack_version="0.1.0",
        pack_hash="sha256:" + "0" * 64,
    )


def _cat(**overrides: object) -> CategoricalResult:
    defaults: dict[str, object] = {
        "category": "optimal",
        "label": "Optimal range",
        "method": "test",
        "provenance": _prov(),
        "evidence": ["A"],
    }
    defaults.update(overrides)
    return ok_category(**defaults)  # type: ignore[arg-type]


def test_ok_category_minimal() -> None:
    r = _cat()
    assert r.status == "ok_category"
    assert r.category == "optimal"
    assert r.label == "Optimal range"
    assert r.assumptions == []
    assert r.warnings == []


def test_ok_category_with_assumptions_warnings() -> None:
    r = _cat(
        assumptions=[Notice(code="assumed_soil", message="Assumed loam")],
        warnings=[Notice(code="low_evidence", message="Only D-grade")],
    )
    assert r.assumptions[0].code == "assumed_soil"
    assert r.warnings[0].code == "low_evidence"


@pytest.mark.parametrize(
    "bad_category",
    ["Optimal", "optimal range", "_optimal", "1optimal", "optimal-1"],
)
def test_category_pattern_rejected(bad_category: str) -> None:
    with pytest.raises(ValidationError, match="category"):
        _cat(category=bad_category)


def test_label_empty_rejected() -> None:
    with pytest.raises(ValidationError, match="label"):
        _cat(label="")


def test_frozen() -> None:
    r = _cat()
    with pytest.raises(ValidationError, match="frozen"):
        r.category = "suboptimal"  # type: ignore[misc]


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError, match=r"[Ee]xtra"):
        CategoricalResult(
            status="ok_category",
            category="optimal",
            label="x",
            method="test",
            provenance=_prov(),
            evidence=["A"],
            assumptions=[],
            warnings=[],
            surprise=1,  # type: ignore[call-arg]
        )


def test_is_success_result() -> None:
    r = ok(value=1.0, unit="kPa", method="test", provenance=_prov(), evidence=["A"])
    assert is_success(r) is True


def test_is_success_categorical() -> None:
    assert is_success(_cat()) is True


def test_is_success_unknown() -> None:
    assert is_success(unknown("no data")) is False


def test_outcome_adapter_accepts_categorical() -> None:
    r = _cat()
    back = OutcomeAdapter.validate_python(OutcomeAdapter.dump_python(r, mode="json"))
    assert isinstance(back, CategoricalResult)
    assert back.category == r.category


def test_outcome_adapter_json_roundtrip() -> None:
    r = _cat()
    back = OutcomeAdapter.validate_json(OutcomeAdapter.dump_json(r))
    assert isinstance(back, CategoricalResult)
    assert back.label == r.label


def test_outcome_union_contains_both_success_variants() -> None:
    res = ok(value=1.0, unit="kPa", method="m", provenance=_prov(), evidence=["A"])
    cat = _cat()
    a = OutcomeAdapter.validate_python(OutcomeAdapter.dump_python(res, mode="json"))
    b = OutcomeAdapter.validate_python(OutcomeAdapter.dump_python(cat, mode="json"))
    assert isinstance(a, Result)
    assert isinstance(b, CategoricalResult)
