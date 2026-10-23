"""The committed JSON schema matches the Pydantic model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agri_core.models.outcome import Outcome, OutcomeAdapter

pytestmark = pytest.mark.contract

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "outcome.schema.json"


def test_committed_schema_exists() -> None:
    assert SCHEMA_PATH.is_file(), (
        f"{SCHEMA_PATH} is missing. Regenerate it with `python scripts/gen_schemas.py`."
    )


def test_committed_schema_matches_model() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    regenerated = OutcomeAdapter.json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/outcome.schema.json is out of date. "
        "Regenerate it with `python scripts/gen_schemas.py` and commit the result."
    )


def test_outcome_status_set_is_exact() -> None:
    from typing import Any

    schema = OutcomeAdapter.json_schema(mode="serialization")
    found: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            disc = o.get("discriminator")
            if isinstance(disc, dict) and "mapping" in disc:
                found.update(disc["mapping"].keys())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(schema)
    assert found == {
        "ok",
        "insufficient_input",
        "unknown",
        "not_applicable",
        "refer_to_label",
        "ambiguous",
        "refer_to_authority",
    }


def test_every_outcome_member_has_required_status() -> None:
    from typing import get_args

    union, _ = get_args(Outcome)
    members = get_args(union)
    assert len(members) == 7
    for m in members:
        sf = m.model_fields["status"]
        assert sf.is_required(), f"{m.__name__}.status must be required"
