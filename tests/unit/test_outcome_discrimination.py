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
                    "profile_ids": [],
                    "profile_version": None,
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
    assert p.profile_ids == []
    assert p.profile_version is None
    assert p.source_ids == []
