"""Result envelope tests (ADR-009)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from agri_core.models import (
    Outcome,
    OutcomeAdapter,
    Provenance,
    Result,
    Subject,
    compute_request_id,
    ok,
    ok_category,
    unknown,
)

pytestmark = pytest.mark.contract


def _prov() -> Provenance:
    return Provenance(fact_ids=[], pack_version="0.1.0", pack_hash="sha256:" + "0" * 64)


def _subject(**overrides: object) -> Subject:
    defaults: dict[str, object] = {
        "taxon_id": "T000000001",
        "taxon_name": "Test plant",
        "scope": {"country": "ID"},
        "calculation": "vpd",
        "calculation_version": "0.1.0",
    }
    defaults.update(overrides)
    return Subject(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Subject model
# ---------------------------------------------------------------------------


def test_subject_minimal() -> None:
    s = Subject(calculation="vpd", calculation_version="0.1.0")
    assert s.taxon_id is None
    assert s.scope == {}


def test_subject_full() -> None:
    s = _subject()
    assert s.taxon_id == "T000000001"
    assert s.scope["country"] == "ID"


@pytest.mark.parametrize("bad_calc", ["VPD", "1vpd", "vpd-x", ""])
def test_subject_calculation_pattern(bad_calc: str) -> None:
    with pytest.raises(ValidationError, match="calculation"):
        Subject(calculation=bad_calc, calculation_version="0.1.0")


@pytest.mark.parametrize("bad_ver", ["1.0", "v1.0.0", "1.0.0.0", ""])
def test_subject_version_pattern(bad_ver: str) -> None:
    with pytest.raises(ValidationError, match="calculation_version"):
        Subject(calculation="vpd", calculation_version=bad_ver)


def test_subject_frozen() -> None:
    s = _subject()
    with pytest.raises(ValidationError, match="frozen"):
        s.calculation = "gdd"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# compute_request_id
# ---------------------------------------------------------------------------


def test_request_id_shape() -> None:
    rid = compute_request_id(subject=_subject(), inputs={"temp_c": 25.0})
    assert rid.startswith("req_")
    assert len(rid) == 36


def test_request_id_deterministic() -> None:
    s = _subject()
    inp = {"temp_c": 25.0, "rh_pct": 60.0}
    assert compute_request_id(subject=s, inputs=inp) == compute_request_id(subject=s, inputs=inp)


def test_request_id_differs_on_input() -> None:
    s = _subject()
    assert compute_request_id(subject=s, inputs={"temp_c": 25.0}) != compute_request_id(
        subject=s, inputs={"temp_c": 26.0}
    )


def test_request_id_differs_on_subject() -> None:
    inp = {"temp_c": 25.0}
    assert compute_request_id(
        subject=_subject(calculation="vpd"), inputs=inp
    ) != compute_request_id(subject=_subject(calculation="gdd"), inputs=inp)


def test_request_id_differs_on_pack_hash() -> None:
    s = _subject()
    inp = {"temp_c": 25.0}
    assert compute_request_id(subject=s, inputs=inp, pack_hash=None) != compute_request_id(
        subject=s, inputs=inp, pack_hash="sha256:" + "a" * 64
    )


def test_request_id_none_subject() -> None:
    rid = compute_request_id(subject=None, inputs={"a": 1})
    assert rid.startswith("req_")


# ---------------------------------------------------------------------------
# Envelope on outcomes
# ---------------------------------------------------------------------------


def test_result_with_envelope() -> None:
    s = _subject()
    rid = compute_request_id(subject=s, inputs={})
    r = ok(
        value=1.0,
        unit="kPa",
        method="vpd",
        provenance=_prov(),
        evidence=["A"],
        subject=s,
        request_id=rid,
    )
    assert r.subject is not None
    assert r.request_id == rid


def test_result_without_envelope() -> None:
    r = ok(value=1.0, unit="kPa", method="vpd", provenance=_prov(), evidence=["A"])
    assert r.subject is None
    assert r.request_id is None


def test_request_id_without_subject_rejected() -> None:
    with pytest.raises(ValidationError, match="request_id requires subject"):
        ok(
            value=1.0,
            unit="kPa",
            method="vpd",
            provenance=_prov(),
            evidence=["A"],
            request_id="req_" + "a" * 32,
        )


def test_subject_without_request_id_ok() -> None:
    s = _subject()
    r = ok(value=1.0, unit="kPa", method="vpd", provenance=_prov(), evidence=["A"], subject=s)
    assert r.subject is not None
    assert r.request_id is None


def test_categorical_envelope() -> None:
    s = _subject(calculation="check_threshold")
    rid = compute_request_id(subject=s, inputs={})
    c = ok_category(
        category="optimal",
        label="Optimal",
        method="check_threshold",
        provenance=_prov(),
        evidence=["A"],
        subject=s,
        request_id=rid,
    )
    assert c.subject is not None
    assert c.request_id == rid


def test_unknown_envelope() -> None:
    s = _subject()
    rid = compute_request_id(subject=s, inputs={})
    u = unknown("no data", subject=s, request_id=rid)
    assert u.subject is not None
    assert u.request_id == rid


def test_unknown_request_id_without_subject_rejected() -> None:
    with pytest.raises(ValidationError, match="request_id requires subject"):
        unknown("no data", request_id="req_" + "a" * 32)


def test_all_8_variants_have_envelope_fields() -> None:
    union, _ = get_args(Outcome)
    members = get_args(union)
    assert len(members) == 8
    for m in members:
        fields = m.model_fields
        assert "subject" in fields, f"{m.__name__} missing subject"
        assert "request_id" in fields, f"{m.__name__} missing request_id"
        assert fields["subject"].default is None
        assert fields["request_id"].default is None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_outcome_schema_has_subject_def() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schema" / "outcome.schema.json").read_text())
    assert "Subject" in schema["$defs"]
    for name in (
        "Ambiguous",
        "CategoricalResult",
        "InsufficientInput",
        "NotApplicable",
        "ReferToAuthority",
        "ReferToLabel",
        "Result",
        "Unknown",
    ):
        props = schema["$defs"][name].get("properties", {})
        assert "subject" in props
        assert "request_id" in props


@pytest.mark.parametrize("dependent", ["taxon_outcome", "fact_outcome"])
def test_dependent_schema_regenerated(dependent: str) -> None:
    """taxon_outcome / fact_outcome share Unknown and Ambiguous; regen must propagate."""
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schema" / f"{dependent}.schema.json").read_text())
    assert "subject" in schema["$defs"]["Unknown"].get("properties", {})
    assert "subject" in schema["$defs"]["Ambiguous"].get("properties", {})
    assert "request_id" in schema["$defs"]["Unknown"].get("properties", {})
    assert "request_id" in schema["$defs"]["Ambiguous"].get("properties", {})


# ---------------------------------------------------------------------------
# Adapter roundtrip
# ---------------------------------------------------------------------------


def test_outcome_adapter_roundtrip_envelope() -> None:
    s = _subject()
    rid = compute_request_id(subject=s, inputs={})
    r = ok(
        value=1.0,
        unit="kPa",
        method="vpd",
        provenance=_prov(),
        evidence=["A"],
        subject=s,
        request_id=rid,
    )
    back = OutcomeAdapter.validate_json(OutcomeAdapter.dump_json(r))
    assert isinstance(back, Result)
    assert back.subject is not None
    assert back.request_id == rid


def test_outcome_adapter_roundtrip_no_envelope() -> None:
    r = ok(value=1.0, unit="kPa", method="vpd", provenance=_prov(), evidence=["A"])
    back = OutcomeAdapter.validate_json(OutcomeAdapter.dump_json(r))
    assert back.subject is None
    assert back.request_id is None
