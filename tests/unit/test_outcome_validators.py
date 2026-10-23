"""Validators reject malformed inputs and protect the contract."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from agri_core.models import (
    InsufficientInput,
    NotApplicable,
    Notice,
    Provenance,
    ReferToLabel,
    Result,
    Unknown,
    ok,
)

pytestmark = pytest.mark.unit


def test_result_rejects_nan() -> None:
    with pytest.raises(ValidationError):
        ok(value=math.nan, unit="kPa", method="x", provenance=Provenance(), evidence=[])


def test_result_rejects_inf() -> None:
    with pytest.raises(ValidationError):
        ok(value=math.inf, unit="kPa", method="x", provenance=Provenance(), evidence=[])


def test_result_is_frozen() -> None:
    r = ok(value=1.0, unit="kPa", method="x", provenance=Provenance(), evidence=[])
    with pytest.raises(ValidationError):
        r.value = 2.0


def test_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Result(  # type: ignore[call-arg]
            status="ok",
            value=1.0,
            unit="kPa",
            method="x",
            provenance=Provenance(),
            evidence=[],
            assumptions=[],
            warnings=[],
            capped=False,
            extra_field="boom",
        )


def test_notice_rejects_bad_code() -> None:
    with pytest.raises(ValidationError):
        Notice(code="Bad-Code", message="x")


def test_notice_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        Notice(code="valid_code", message="")


def test_insufficient_input_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        InsufficientInput(status="insufficient_input", missing=[])


def test_insufficient_input_rejects_empty_item() -> None:
    with pytest.raises(ValidationError):
        InsufficientInput(status="insufficient_input", missing=[""])


def test_unknown_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        Unknown(status="unknown", reason="")


def test_not_applicable_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        NotApplicable(status="not_applicable", reason="")


def test_refer_to_label_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        ReferToLabel(status="refer_to_label", reason="")


def test_ambiguous_rejects_single_candidate() -> None:
    from agri_core.models import Ambiguous, AmbiguousCandidate

    with pytest.raises(ValidationError):
        Ambiguous(
            status="ambiguous",
            candidates=[AmbiguousCandidate(taxon_id="t1", name="Foo")],
        )


def test_ambiguous_rejects_too_many() -> None:
    from agri_core.models import Ambiguous, AmbiguousCandidate

    with pytest.raises(ValidationError):
        Ambiguous(
            status="ambiguous",
            candidates=[AmbiguousCandidate(taxon_id=f"t{i}", name=f"N{i}") for i in range(21)],
        )


def test_ambiguous_rejects_duplicate_taxon_id() -> None:
    from agri_core.models import Ambiguous, AmbiguousCandidate

    with pytest.raises(ValidationError):
        Ambiguous(
            status="ambiguous",
            candidates=[
                AmbiguousCandidate(taxon_id="t1", name="A"),
                AmbiguousCandidate(taxon_id="t1", name="B"),
            ],
        )


def test_refer_to_authority_rejects_lowercase_flag() -> None:
    from agri_core.models import ReferToAuthority

    with pytest.raises(ValidationError):
        ReferToAuthority(status="refer_to_authority", reason="r", flags=["legal"])


def test_refer_to_authority_rejects_duplicate_flags() -> None:
    from agri_core.models import ReferToAuthority

    with pytest.raises(ValidationError):
        ReferToAuthority(status="refer_to_authority", reason="r", flags=["LEGAL", "LEGAL"])


def test_refer_to_authority_sorts_flags() -> None:
    from agri_core.models import ReferToAuthority

    o = ReferToAuthority(status="refer_to_authority", reason="r", flags=["LEGAL", "ENV", "PEST"])
    assert o.flags == ["ENV", "LEGAL", "PEST"]
