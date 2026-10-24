"""Taxon row: one rank, name and taxonomic identity for a cultivated organism."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agri_core.models.ids import (
    DatasetId,
    SourceId,
    TaxonId,
    ensure_src_or_dataset,
)

TaxonRank = Literal["species", "hybrid", "cultivar_group", "genus"]


class TaxonRow(BaseModel):
    """One row of ``taxon.csv``: the identity of a cultivated organism.

    Tier is **derived** from the taxon's facts, not stored on the row (W5).
    Vocabularies (``organism_group``, ``archetype``, ``uses``, ``traits``) are
    stored as free strings and validated at validate time against the pack's
    ``dictionary_version``, not by this model. That keeps the schema stateless
    when a vocabulary grows.

    ``rank`` is a **closed** enum from W5, not a vocabulary. Adding a new rank
    is an engine change (minor bump).

    ``parent_id`` is for navigation only; it does not imply inheritance of
    facts. ``parent_id`` must not equal ``taxon_id``. Deeper cycles
    (A -> B -> A) are checked at validate time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    taxon_id: TaxonId
    rank: TaxonRank
    scientific_name: str = Field(min_length=1)
    accepted_name: str | None = None
    organism_group: str = Field(min_length=1)
    archetype: str = Field(min_length=1)
    uses: list[str] = Field(min_length=1)
    traits: list[str] = Field(default_factory=list)
    parent_id: TaxonId | None = None
    external_ids: dict[str, str] | None = None
    src: list[SourceId] | None = None
    dataset_id: DatasetId | None = None

    @field_validator("accepted_name")
    @classmethod
    def _check_accepted_name(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("accepted_name must be non-empty if provided")
        return v

    @field_validator("uses")
    @classmethod
    def _check_uses_non_empty_strings(cls, v: list[str]) -> list[str]:
        for item in v:
            if not item:
                raise ValueError("uses must not contain empty strings")
        return v

    @field_validator("traits")
    @classmethod
    def _check_traits_non_empty_strings(cls, v: list[str]) -> list[str]:
        for item in v:
            if not item:
                raise ValueError("traits must not contain empty strings")
        if len(v) != len(set(v)):
            raise ValueError("traits must not contain duplicates")
        return v

    @model_validator(mode="after")
    def _check_invariants(self) -> TaxonRow:
        if self.parent_id is not None and self.parent_id == self.taxon_id:
            raise ValueError("parent_id must not equal taxon_id")
        ensure_src_or_dataset(self.src, self.dataset_id)
        return self
