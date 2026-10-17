"""Regenerate ``schema/*.schema.json`` from the Pydantic models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from agri_core.models.outcome import Outcome


def main() -> int:
    schema_dir = Path(__file__).resolve().parent.parent / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)

    schema = TypeAdapter(Outcome).json_schema(mode="serialization")
    target = schema_dir / "outcome.schema.json"
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
