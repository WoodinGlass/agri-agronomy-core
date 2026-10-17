"""Provenance metadata for calculation results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """Where a calculation's numbers came from.

    ``profile_ids`` names the crop profiles that contributed values.
    ``profile_version`` is the content hash of those profiles at computation
    time; it is ``None`` when the calculation does not read a profile (for
    example, raw VPD from weather inputs).
    ``source_ids`` lists the ``src`` IDs in ``profiles/sources.csv`` behind
    the values used.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_ids: list[str] = Field(default_factory=list)
    profile_version: str | None = None
    source_ids: list[str] = Field(default_factory=list)
