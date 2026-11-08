"""Load the climate parameter catalog from CSV."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from agri_core.catalog.models import CatalogRow

__all__ = ["CatalogLoadError", "load_catalog"]


class CatalogLoadError(Exception):
    """Raised when a catalog CSV cannot be loaded."""


def load_catalog(path: Path) -> list[CatalogRow]:
    """Load and validate a climate parameter catalog.

    Raises ``CatalogLoadError`` on malformed CSV, duplicate ``param_id``,
    or empty catalog.
    """
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CatalogLoadError(f"missing header: {path}")
    required = {
        "param_id",
        "group",
        "kind",
        "unit",
        "method_ref",
        "owner_repo",
        "commercial_use",
        "safety_tier",
        "status",
        "milestone",
        "test_id",
        "checked_on",
        "reason",
    }
    missing = required - set(reader.fieldnames)
    if missing:
        raise CatalogLoadError(f"missing columns: {sorted(missing)}")

    rows: list[CatalogRow] = []
    seen: dict[str, int] = {}
    for line_no, raw in enumerate(reader, start=2):
        try:
            row = CatalogRow.model_validate(raw)
        except Exception as exc:
            raise CatalogLoadError(f"row {line_no}: {exc}") from exc
        if row.param_id in seen:
            first = seen[row.param_id]
            raise CatalogLoadError(
                f"row {line_no}: duplicate param_id {row.param_id!r} (first seen at row {first})"
            )
        seen[row.param_id] = line_no
        rows.append(row)

    if not rows:
        raise CatalogLoadError(f"empty catalog: {path}")
    return rows
