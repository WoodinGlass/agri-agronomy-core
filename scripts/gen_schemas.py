"""Regenerate ``schema/*.schema.json`` from the Pydantic models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from agri_core.models.dataset import DatasetRow
from agri_core.models.hazard import HazardRow
from agri_core.models.name import NameRow
from agri_core.models.outcome import OutcomeAdapter
from agri_core.models.taxon import TaxonRow
from agri_core.pack.manifest import PackManifest
from agri_core.registry.sources import SourceRow


def _write(name: str, schema: dict[str, object], schema_dir: Path) -> Path:
    target = schema_dir / name
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {target}")
    return target


def main() -> int:
    schema_dir = Path(__file__).resolve().parent.parent / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    _write(
        "outcome.schema.json",
        OutcomeAdapter.json_schema(mode="serialization"),
        schema_dir,
    )
    _write(
        "source.schema.json",
        TypeAdapter(SourceRow).json_schema(mode="serialization"),
        schema_dir,
    )
    _write(
        "manifest.schema.json",
        TypeAdapter(PackManifest).json_schema(mode="serialization"),
        schema_dir,
    )
    _write(
        "dataset.schema.json",
        TypeAdapter(DatasetRow).json_schema(mode="serialization"),
        schema_dir,
    )
    _write(
        "hazard.schema.json",
        TypeAdapter(HazardRow).json_schema(mode="serialization"),
        schema_dir,
    )
    _write(
        "name.schema.json",
        TypeAdapter(NameRow).json_schema(mode="serialization"),
        schema_dir,
    )
    _write(
        "taxon.schema.json",
        TypeAdapter(TaxonRow).json_schema(mode="serialization"),
        schema_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
