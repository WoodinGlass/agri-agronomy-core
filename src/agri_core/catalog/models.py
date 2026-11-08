"""Climate parameter catalog: row model and enums."""

from __future__ import annotations

from datetime import date as _date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "CatalogKind",
    "CatalogOwner",
    "CatalogRow",
    "CatalogSafetyTier",
    "CatalogStatus",
    "CommercialUse",
]


class CatalogKind(StrEnum):
    """Kind of climate parameter."""

    COMPUTED = "computed"
    INPUT = "input"
    PACK_VALUE = "pack_value"
    EXCLUDED = "excluded"


class CatalogStatus(StrEnum):
    """Lifecycle status of a catalog row."""

    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    BACKLOG = "backlog"
    EXCLUDED = "excluded"


class CatalogSafetyTier(StrEnum):
    """Safety tier of a catalog row."""

    LOW = "low"
    HIGH = "high"


class CatalogOwner(StrEnum):
    """Repository that owns the parameter."""

    CORE = "core"
    KNOWLEDGE = "knowledge"
    CALLER = "caller"


class CommercialUse(StrEnum):
    """Commercial-use flag, mirroring sources.csv."""

    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


class CatalogRow(BaseModel):
    """One row of the climate parameter catalog."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    param_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    group: str = Field(min_length=1)
    kind: CatalogKind
    unit: str = ""
    method_ref: str = ""
    owner_repo: CatalogOwner
    commercial_use: CommercialUse
    safety_tier: CatalogSafetyTier
    status: CatalogStatus
    milestone: str = Field(pattern=r"^M\d+$")
    test_id: str = ""
    checked_on: str
    reason: str = ""

    @field_validator("checked_on")
    @classmethod
    def _checked_on_is_date(cls, v: str) -> str:
        try:
            _date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"checked_on not YYYY-MM-DD: {v!r}") from exc
        return v
