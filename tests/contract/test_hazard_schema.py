"""The committed hazard schema matches the Pydantic model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from agri_core.models.hazard import HazardRow

pytestmark = pytest.mark.contract

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "hazard.schema.json"


def test_committed_schema_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_committed_schema_matches_model() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    regenerated = TypeAdapter(HazardRow).json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/hazard.schema.json is out of date. Regenerate with `python scripts/gen_schemas.py`."
    )
