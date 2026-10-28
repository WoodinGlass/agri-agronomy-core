"""Committed JSON schemas for the resolution module (M8-4b).

The `taxon_outcome` and `fact_outcome` unions are kept separate from
the top-level `Outcome` union (see ADR-004). This module pins each
union's JSON schema and the status set it discriminates on, plus the
`MetaInfo` schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from agri_core.registry.resolution import (
    FactOutcomeAdapter,
    MetaInfo,
    TaxonOutcomeAdapter,
)

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _REPO / "schema"


def _walk_discriminators(o: Any, found: set[str], *, property_name: str) -> None:
    """Collect discriminator mapping keys for a given ``propertyName``.

    ``FactResolved`` nests ``FactRow`` whose ``FactValue`` field has
    its own discriminator on ``shape``. Filtering by ``propertyName``
    keeps the walker from picking up those nested shape keys.
    """
    if isinstance(o, dict):
        disc = o.get("discriminator")
        if (
            isinstance(disc, dict)
            and disc.get("propertyName") == property_name
            and "mapping" in disc
        ):
            found.update(disc["mapping"].keys())
        for v in o.values():
            _walk_discriminators(v, found, property_name=property_name)
    elif isinstance(o, list):
        for v in o:
            _walk_discriminators(v, found, property_name=property_name)


# ---- taxon_outcome --------------------------------------------------------


def test_taxon_outcome_schema_exists() -> None:
    p = _SCHEMA_DIR / "taxon_outcome.schema.json"
    assert p.is_file(), f"{p} missing; run `python scripts/gen_schemas.py`"


def test_taxon_outcome_schema_matches_model() -> None:
    committed = json.loads((_SCHEMA_DIR / "taxon_outcome.schema.json").read_text(encoding="utf-8"))
    regenerated = TaxonOutcomeAdapter.json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/taxon_outcome.schema.json is out of date; run `python scripts/gen_schemas.py`"
    )


def test_taxon_outcome_status_set_is_exact() -> None:
    found: set[str] = set()
    _walk_discriminators(
        TaxonOutcomeAdapter.json_schema(mode="serialization"),
        found,
        property_name="status",
    )
    assert found == {"ok", "ambiguous", "unknown"}


# ---- fact_outcome ---------------------------------------------------------


def test_fact_outcome_schema_exists() -> None:
    p = _SCHEMA_DIR / "fact_outcome.schema.json"
    assert p.is_file(), f"{p} missing; run `python scripts/gen_schemas.py`"


def test_fact_outcome_schema_matches_model() -> None:
    committed = json.loads((_SCHEMA_DIR / "fact_outcome.schema.json").read_text(encoding="utf-8"))
    regenerated = FactOutcomeAdapter.json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/fact_outcome.schema.json is out of date; run `python scripts/gen_schemas.py`"
    )


def test_fact_outcome_status_set_is_exact() -> None:
    found: set[str] = set()
    _walk_discriminators(
        FactOutcomeAdapter.json_schema(mode="serialization"),
        found,
        property_name="status",
    )
    assert found == {"ok", "ambiguous", "unknown"}


# ---- meta_info ------------------------------------------------------------


def test_meta_info_schema_exists() -> None:
    p = _SCHEMA_DIR / "meta_info.schema.json"
    assert p.is_file(), f"{p} missing; run `python scripts/gen_schemas.py`"


def test_meta_info_schema_matches_model() -> None:
    committed = json.loads((_SCHEMA_DIR / "meta_info.schema.json").read_text(encoding="utf-8"))
    regenerated = TypeAdapter(MetaInfo).json_schema(mode="serialization")
    assert committed == regenerated, (
        "schema/meta_info.schema.json is out of date; run `python scripts/gen_schemas.py`"
    )
