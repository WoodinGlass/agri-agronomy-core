"""Hazard row: a legal or regulatory hazard recorded against a taxon."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agri_core.models.ids import DatasetId, SourceId, TaxonId, ensure_src_or_dataset

HazardSeverity = Literal["info", "warning", "critical"]


class HazardRow(BaseModel):
    """One row of ``hazard.csv``: a specific hazard recorded for a taxon.

    Legal status decays; ``as_of`` and ``authority`` are required so a stale
    entry can be identified and re-verified.

    ``hazard_code`` is a stable lowercase snake_case identifier. It is not
    a ``FlagCode`` (uppercase) because it names the hazard itself, not the
    outcome reason. Codes are validated at validate time against whatever
    hazard vocabulary the pack declares.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    taxon_id: TaxonId
    hazard_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    severity: HazardSeverity
    reason: str = Field(min_length=1)
    as_of: date
    authority: str = Field(min_length=1)
    src: list[SourceId] | None = None
    dataset_id: DatasetId | None = None

    @model_validator(mode="after")
    def _require_src_or_dataset(self) -> HazardRow:
        ensure_src_or_dataset(self.src, self.dataset_id)
        return self
