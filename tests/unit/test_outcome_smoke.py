"""Smoke tests: construct each outcome type and JSON-roundtrip it."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agri_core.models import (
    InsufficientInput,
    NotApplicable,
    Notice,
    OutcomeAdapter,
    Provenance,
    ReferToLabel,
    Result,
    Unknown,
    insufficient_input,
    not_applicable,
    ok,
    refer_to_label,
    unknown,
)

pytestmark = pytest.mark.unit


def _provenance() -> Provenance:
    return Provenance(
        fact_ids=["F0000001"],
        pack_version="2026.10.0",
        pack_hash="sha256:" + "a" * 64,
        source_ids=["S014"],
    )


def _assert_roundtrip(obj: Any, status: str) -> None:
    payload = OutcomeAdapter.dump_python(obj, mode="json")
    assert payload["status"] == status
    restored = OutcomeAdapter.validate_python(json.loads(json.dumps(payload)))
    assert restored == obj


def test_ok_factory_returns_result() -> None:
    r = ok(
        value=1.32,
        unit="kPa",
        method="tetens",
        provenance=_provenance(),
        evidence=["B"],
    )
    assert isinstance(r, Result)
    assert r.status == "ok"
    assert r.value == 1.32
    assert r.assumptions == []
    assert r.warnings == []
    assert r.capped is False


def test_ok_with_notices_and_cap() -> None:
    r = ok(
        value=1.0,
        unit="kPa",
        method="tetens",
        provenance=_provenance(),
        evidence=["A", "B"],
        assumptions=[Notice(code="temp_from_elevation", message="estimated")],
        warnings=[Notice(code="low_precision", message="rough")],
        capped=True,
    )
    assert r.assumptions[0].code == "temp_from_elevation"
    assert r.warnings[0].code == "low_precision"
    assert r.capped is True


def test_insufficient_input_factory() -> None:
    o = insufficient_input(["temp_c"])
    assert isinstance(o, InsufficientInput)
    assert o.status == "insufficient_input"
    assert o.missing == ["temp_c"]


def test_unknown_factory() -> None:
    o = unknown("no Kc for this scope")
    assert isinstance(o, Unknown)
    assert o.status == "unknown"
    assert o.reason == "no Kc for this scope"


def test_not_applicable_factory() -> None:
    o = not_applicable("propagation not defined")
    assert isinstance(o, NotApplicable)
    assert o.status == "not_applicable"


def test_refer_to_label_factory() -> None:
    o = refer_to_label("pesticides are out of scope")
    assert isinstance(o, ReferToLabel)
    assert o.status == "refer_to_label"


def test_roundtrip_ok() -> None:
    _assert_roundtrip(
        ok(value=1.0, unit="kPa", method="x", provenance=Provenance(), evidence=[]),
        "ok",
    )


def test_roundtrip_insufficient_input() -> None:
    _assert_roundtrip(insufficient_input(["a"]), "insufficient_input")


def test_roundtrip_unknown() -> None:
    _assert_roundtrip(unknown("r"), "unknown")


def test_roundtrip_not_applicable() -> None:
    _assert_roundtrip(not_applicable("r"), "not_applicable")


def test_roundtrip_refer_to_label() -> None:
    _assert_roundtrip(refer_to_label("r"), "refer_to_label")


def test_ambiguous_factory() -> None:
    from agri_core.models import Ambiguous, AmbiguousCandidate, ambiguous

    o = ambiguous(
        [
            AmbiguousCandidate(taxon_id="t1", name="Foo"),
            AmbiguousCandidate(taxon_id="t2", name="Bar", note="different"),
        ]
    )
    assert isinstance(o, Ambiguous)
    assert o.status == "ambiguous"
    assert len(o.candidates) == 2


def test_refer_to_authority_factory() -> None:
    from agri_core.models import ReferToAuthority, refer_to_authority

    o = refer_to_authority("consult local regulator", flags=["LEGAL", "PESTICIDE"])
    assert isinstance(o, ReferToAuthority)
    assert o.status == "refer_to_authority"
    assert o.flags == ["LEGAL", "PESTICIDE"]


def test_roundtrip_ambiguous() -> None:
    from agri_core.models import AmbiguousCandidate, ambiguous

    _assert_roundtrip(
        ambiguous(
            [
                AmbiguousCandidate(taxon_id="t1", name="Foo"),
                AmbiguousCandidate(taxon_id="t2", name="Bar"),
            ]
        ),
        "ambiguous",
    )


def test_roundtrip_refer_to_authority() -> None:
    from agri_core.models import refer_to_authority

    _assert_roundtrip(refer_to_authority("r", flags=["LEGAL"]), "refer_to_authority")
