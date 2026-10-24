"""The committed fact schema matches the Pydantic model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from agri_core.models.fact import FactRow

pytestmark = pytest.mark.contract

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "fact.schema.json"


def test_committed_schema_exists() -> None:
    assert SCHEMA_PATH.is_file(), (
        f"{SCHEMA_PATH.name} missing. Regenerate with `python scripts/gen_schemas.py`."
    )


def test_committed_schema_matches_model() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    regenerated = TypeAdapter(FactRow).json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/fact.schema.json is out of date. Regenerate with `python scripts/gen_schemas.py`."
    )


def test_schema_defs_has_all_seven_shapes() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    defs = schema.get("$defs", {})
    for name in (
        "TrapezoidValue",
        "RangeValue",
        "ScalarValue",
        "EnumValue",
        "BoolValue",
        "RuleValue",
        "UnknownValue",
    ):
        assert name in defs, f"{name} missing from $defs"
