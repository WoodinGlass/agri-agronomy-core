"""Name row: one name (scientific, common, synonym or trade) for a taxon."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agri_core.models.ids import (
    DatasetId,
    SourceId,
    TaxonId,
    ensure_src_or_dataset,
)

NameKind = Literal["common", "scientific", "synonym", "trade"]

_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
_SCRIPT_PATTERN = re.compile(r"^[A-Z][a-z]{3}$")


class NameRow(BaseModel):
    """One row of ``name.csv``: a name attached to a taxon.

    ``language`` follows a pragmatic BCP-47 subset: a primary language tag of
    2-3 lowercase letters, optionally followed by `-` separated subtags of
    1-8 alphanumeric characters. This accepts ``en``, ``id``, ``und``,
    ``zh-Hans``, ``en-US``, ``zh-Hans-CN``. Full BCP-47 validation happens
    at validate time against a lookup table if needed.

    ``script`` is an ISO 15924 code: 4 letters, first uppercase, e.g.
    ``Latn``, ``Arab``, ``Zyyy`` (undetermined).

    ``kind`` is a closed set (``common``, ``scientific``, ``synonym``,
    ``trade``) matching W5. ``preferred`` marks the canonical name in the
    given language and kind.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    taxon_id: TaxonId
    name: str = Field(min_length=1)
    language: str
    script: str
    kind: NameKind
    preferred: bool = False
    src: list[SourceId] | None = None
    dataset_id: DatasetId | None = None

    @field_validator("language")
    @classmethod
    def _check_language(cls, v: str) -> str:
        if not _LANGUAGE_PATTERN.match(v):
            raise ValueError(f"language must be a BCP-47 tag, got {v!r}")
        return v

    @field_validator("script")
    @classmethod
    def _check_script(cls, v: str) -> str:
        if not _SCRIPT_PATTERN.match(v):
            raise ValueError(f"script must be an ISO 15924 code, got {v!r}")
        return v

    @model_validator(mode="after")
    def _require_src_or_dataset(self) -> NameRow:
        ensure_src_or_dataset(self.src, self.dataset_id)
        return self
