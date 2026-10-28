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


class EnumSetValue(BaseModel):
    """Set of enum values.

    One fact represents the whole set, avoiding FACT_CONFLICT from multiple
    facts with identical scope. ``values`` must be non-empty and unique.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: Literal["enum_set"]
    values: tuple[str, ...]

    @field_validator("values")
    @classmethod
    def _non_empty_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(v) == 0:
            raise ValueError("values must not be empty")
        for item in v:
            if not item:
                raise ValueError("values must not contain empty strings")
        if len(set(v)) != len(v):
            raise ValueError("values must be unique")
        return v


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
    TrapezoidValue
    | RangeValue
    | ScalarValue
    | EnumValue
    | EnumSetValue
    | BoolValue
    | RuleValue
    | UnknownValue,
    Field(discriminator="shape"),
]
"""Union of all eight fact-value shapes, discriminated by ``shape``."""


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
    reviewed_by: list[str] | None = None
    reviewed_at: date | None = None
    superseded_by: FactId | None = None

    @field_validator("phase")
    @classmethod
    def _check_phase(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("phase must be non-empty if provided")
        return v

    @field_validator("reviewed_by", mode="before")
    @classmethod
    def _check_reviewed_by(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            raise ValueError(
                f"reviewed_by must be a list of strings or None, got {type(v).__name__}"
            )
        if not v:
            raise ValueError("reviewed_by must be non-empty if provided")
        for item in v:
            if not isinstance(item, str) or not item:
                raise ValueError("reviewed_by items must be non-empty strings")
        return sorted(set(v))

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


def format_value(value: FactValue) -> str:
    """Human-readable, deterministic string for a fact value.

    Used by ``FactResolved.value_pretty``. Not for wire serialization —
    that goes through Pydantic / canonical JSON. This is display text.
    """
    if isinstance(value, ScalarValue):
        return f"{value.value} {value.unit}"
    if isinstance(value, RangeValue):
        return f"{value.min}\u2013{value.max} {value.unit}"
    if isinstance(value, TrapezoidValue):
        a, b, c, d = value.pts
        return f"[{a}, {b}, {c}, {d}] {value.unit}"
    if isinstance(value, EnumValue):
        return value.value
    if isinstance(value, EnumSetValue):
        return "{" + ", ".join(sorted(value.values)) + "}"
    if isinstance(value, BoolValue):
        return "true" if value.value else "false"
    if isinstance(value, RuleValue):
        return f"<rule {len(value.data)} keys>"
    if isinstance(value, UnknownValue):
        return f"unknown ({value.reason})"
    # FactValue is a closed union; unreachable.
    raise TypeError(f"unknown FactValue: {value!r}")


__all__ = [
    "BoolValue",
    "EnumSetValue",
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
    "format_value",
]
