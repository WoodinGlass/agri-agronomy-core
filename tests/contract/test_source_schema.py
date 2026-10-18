"""The committed source schema matches the Pydantic model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from agri_core.registry.sources import SourceRow

pytestmark = pytest.mark.contract

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "source.schema.json"


def test_committed_schema_exists() -> None:
    assert SCHEMA_PATH.is_file(), (
        f"{SCHEMA_PATH} is missing. Regenerate it with `python scripts/gen_schemas.py`."
    )


def test_committed_schema_matches_model() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    regenerated = TypeAdapter(SourceRow).json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/source.schema.json is out of date. "
        "Regenerate it with `python scripts/gen_schemas.py`."
    )
