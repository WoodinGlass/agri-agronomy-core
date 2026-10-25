"""Discriminated union parsing behaves correctly."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agri_core.models import (
    InsufficientInput,
    NotApplicable,
    OutcomeAdapter,
    Provenance,
    ReferToLabel,
    Result,
    Unknown,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "status": "ok",
                "value": 1.0,
                "unit": "kPa",
                "method": "x",
                "provenance": {
                    "fact_ids": [],
                    "pack_version": None,
                    "pack_hash": None,
                    "source_ids": [],
                },
                "evidence": [],
                "assumptions": [],
                "warnings": [],
                "capped": False,
            },
            Result,
        ),
        ({"status": "insufficient_input", "missing": ["a"]}, InsufficientInput),
        ({"status": "unknown", "reason": "r"}, Unknown),
        ({"status": "not_applicable", "reason": "r"}, NotApplicable),
        ({"status": "refer_to_label", "reason": "r"}, ReferToLabel),
    ],
)
def test_parse_by_status(payload: dict[str, Any], expected_type: type) -> None:
    obj = OutcomeAdapter.validate_python(payload)
    assert isinstance(obj, expected_type)
    assert obj.status == payload["status"]


def test_reject_unknown_status() -> None:
    with pytest.raises(ValidationError):
        OutcomeAdapter.validate_python({"status": "exploded"})


def test_provenance_default_constructible() -> None:
    p = Provenance()
    assert p.fact_ids == []
    assert p.pack_version is None
    assert p.pack_hash is None
    assert p.source_ids == []


def test_parse_ambiguous() -> None:
    from agri_core.models import Ambiguous

    obj = OutcomeAdapter.validate_python(
        {
            "status": "ambiguous",
            "candidates": [
                {"taxon_id": "t1", "name": "Foo"},
                {"taxon_id": "t2", "name": "Bar"},
            ],
        }
    )
    assert isinstance(obj, Ambiguous)


def test_parse_refer_to_authority() -> None:
    from agri_core.models import ReferToAuthority

    obj = OutcomeAdapter.validate_python(
        {"status": "refer_to_authority", "reason": "r", "flags": ["LEGAL"]}
    )
    assert isinstance(obj, ReferToAuthority)
