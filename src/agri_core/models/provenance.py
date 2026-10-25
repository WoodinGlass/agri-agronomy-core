"""Provenance metadata for calculation results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """Where a calculation's numbers came from.

    ``fact_ids`` names the facts that contributed values.
    ``pack_version`` is the version of the pack that supplied those facts;
    it is ``None`` when the calculation does not read a pack (for example,
    raw VPD from weather inputs).
    ``pack_hash`` is the pack's ``content_hash`` (``sha256:<hex>``), which
    pins the exact data used; it is ``None`` under the same conditions as
    ``pack_version``.
    ``source_ids`` lists the ``src`` IDs from ``sources.csv`` behind the
    values used.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_ids: list[str] = Field(default_factory=list)
    pack_version: str | None = None
    pack_hash: str | None = None
    source_ids: list[str] = Field(default_factory=list)
