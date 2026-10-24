"""Fact row: a single value at a single scope, with full provenance."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agri_core.models.ids import (
    DatasetId,
    FactId,
    SourceId,
    TaxonId,
    ensure_src_or_dataset,
)
from agri_core.models.notices import EvidenceGrade

ProvenanceKind = Literal["curated", "imported", "derived"]
FactStatus = Literal["imported", "draft", "reviewed", "approved"]


class TrapezoidValue(BaseModel):
    """Four-point trapezoid: abs_min <= opt_min <= opt_max <= abs_max."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["trapezoid"]
    unit: str = Field(min_length=1)
    pts: tuple[float, float, float, float]

    @model_validator(mode="after")
    def _check_order(self) -> TrapezoidValue:
        a, b, c, d = self.pts
        if not (a <= b <= c <= d):
            raise ValueError(
                f"pts must satisfy abs_min <= opt_min <= opt_max <= abs_max, got {self.pts}"
            )
        return self


class RangeValue(BaseModel):
    """Range: min <= max, both with a unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["range"]
    unit: str = Field(min_length=1)
    min: float
    max: float

    @model_validator(mode="after")
    def _check_order(self) -> RangeValue:
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must be <= max ({self.max})")
        return self


class ScalarValue(BaseModel):
    """Single numeric value with a unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["scalar"]
    unit: str = Field(min_length=1)
    value: float


class EnumValue(BaseModel):
    """One value from a closed set. Membership validated at M1-2 against
    the parameter's ``enum_values``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["enum"]
    value: str = Field(min_length=1)


class BoolValue(BaseModel):
    """Boolean value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["bool"]
    value: bool


class RuleValue(BaseModel):
    """Structured rule; shape-specific schema validated at M1-2 against
    the parameter's ``rule_schema``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["rule"]
    data: dict[str, Any]


class UnknownValue(BaseModel):
    """Explicitly unknown, with a required reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["unknown"]
    reason: str = Field(min_length=1)


FactValue = Annotated[
    TrapezoidValue | RangeValue | ScalarValue | EnumValue | BoolValue | RuleValue | UnknownValue,
    Field(discriminator="shape"),
]
"""Union of all seven fact-value shapes, discriminated by ``shape``."""


class FactRow(BaseModel):
    """One row of ``fact.csv``: a single value at a single scope.

    Cross-rules enforced here:
    - ``src`` or ``dataset_id`` (at least one)
    - ``provenance_kind=imported`` requires ``dataset_id`` and ``evidence`` C or D
    - ``provenance_kind=derived`` requires ``dataset_id``
    - ``provenance_kind=curated`` requires ``locator``
    - ``status`` reviewed/approved requires ``reviewed_by`` and ``reviewed_at``

    Deferred to validate (M1-2), because they need the dictionary:
    - ``parameter`` exists in ``parameters.core.yaml`` or a pack
    - ``phase`` is a member of the parameter's ``phase_set``
    - safety-critical parameters require ``status`` reviewed or approved
    - shape matches ``parameter.shape``
    - ``enum`` value is in the parameter's ``enum_values``
    - ``unit`` matches the parameter's ``unit``
    - ``scope`` keys and values are valid against ``scope_keys.yaml``
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    fact_id: FactId
    taxon_id: TaxonId
    parameter: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    phase: str | None = None
    value: FactValue
    scope: dict[str, Any] = Field(default_factory=dict)
    provenance_kind: ProvenanceKind
    src: list[SourceId] | None = None
    dataset_id: DatasetId | None = None
    locator: str | None = None
    evidence: EvidenceGrade
    status: FactStatus
    reviewed_by: str | None = None
    reviewed_at: date | None = None
    superseded_by: FactId | None = None

    @field_validator("phase")
    @classmethod
    def _check_phase(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("phase must be non-empty if provided")
        return v

    @field_validator("reviewed_by")
    @classmethod
    def _check_reviewed_by(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("reviewed_by must be non-empty if provided")
        return v

    @model_validator(mode="after")
    def _check_cross_rules(self) -> FactRow:
        ensure_src_or_dataset(self.src, self.dataset_id)

        if self.provenance_kind == "imported":
            if self.dataset_id is None:
                raise ValueError("provenance_kind=imported requires dataset_id")
            if self.evidence not in ("C", "D"):
                raise ValueError(
                    f"provenance_kind=imported allows evidence C or D only, got {self.evidence!r}"
                )
        elif self.provenance_kind == "derived":
            if self.dataset_id is None:
                raise ValueError("provenance_kind=derived requires dataset_id")
        elif self.provenance_kind == "curated":
            if self.locator is None:
                raise ValueError("provenance_kind=curated requires locator")

        if self.status in ("reviewed", "approved"):
            if self.reviewed_by is None:
                raise ValueError(f"status={self.status} requires reviewed_by")
            if self.reviewed_at is None:
                raise ValueError(f"status={self.status} requires reviewed_at")

        return self


__all__ = [
    "BoolValue",
    "EnumValue",
    "FactRow",
    "FactStatus",
    "FactValue",
    "ProvenanceKind",
    "RangeValue",
    "RuleValue",
    "ScalarValue",
    "TrapezoidValue",
    "UnknownValue",
]
