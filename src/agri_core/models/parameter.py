"""Parameter definition model (v1.0.0)."""

from __future__ import annotations

import re
from typing import Any, Literal

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ParameterShape = Literal[
    "trapezoid", "range", "scalar", "enum", "enum_set", "bool", "rule", "unknown"
]
ParameterKind = Literal["core", "extension"]
SafetyClass = Literal["none", "dose_cap", "toxicity_limit", "regulatory"]

_NUMERIC_SHAPES: frozenset[str] = frozenset({"trapezoid", "range", "scalar"})
_ENUM_SHAPES: frozenset[str] = frozenset({"enum", "enum_set"})

# Strict three-component semver with optional pre-release and build suffix.
# packaging.version.Version accepts "1.0" as "1.0.0"; the dictionary contract
# requires three explicit components.
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def check_semver(v: str) -> str:
    """Require strict X.Y.Z semver with optional pre-release/build.

    ``packaging.version.Version`` accepts ``1.0`` as ``1.0.0``; that is too
    permissive for the dictionary contract, which requires three explicit
    components. The regex enforces three components; ``Version`` catches any
    remaining PEP 440 edge cases.
    """
    if not _SEMVER_RE.match(v):
        raise ValueError(f"not valid X.Y.Z semver: {v!r}")
    try:
        Version(v)
    except InvalidVersion as exc:
        raise ValueError(f"not valid X.Y.Z semver: {v!r}") from exc
    return v


class AppliesTo(BaseModel):
    """Dimensions a parameter applies to (AND between, OR within).

    ``organism_groups`` is required and non-empty. ``None`` means the dimension
    is not written (unlimited); an explicit empty list is rejected so that
    "unlimited" and "no values" cannot be confused.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    organism_groups: list[str] = Field(min_length=1)
    archetypes: list[str] | None = None
    uses: list[str] | None = None
    systems: list[str] | None = None
    traits: list[str] | None = None

    @field_validator("archetypes", "uses", "systems", "traits")
    @classmethod
    def _non_empty_if_provided(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) == 0:
            raise ValueError("if provided, must be non-empty; omit the dimension to mean unlimited")
        return v


class ParameterDef(BaseModel):
    """Definition of one parameter in the core dictionary or in a pack."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    stage: str
    shape: ParameterShape
    unit: str | None = None
    physical_range: tuple[float, float] | None = None
    enum_values: list[str] | None = None
    enum_source: str | None = None
    phase_set: str = "none"
    allowed_phases: list[str] | None = None
    applies_to: AppliesTo
    scope_keys: list[str] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)
    tier_required: bool = False
    safety_class: SafetyClass = "none"
    rationale: str | None = None
    kind: ParameterKind
    description: str = Field(min_length=1)
    introduced_in: str
    deprecated_in: str | None = None
    replaced_by: str | None = None
    rule_schema: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        """Alias for ``key``. Retained for compatibility with pre-1.0.0 code."""
        return self.key

    @property
    def safety_critical(self) -> bool:
        """Derived: True iff safety_class is not ``none``."""
        return self.safety_class != "none"

    @field_validator("introduced_in", "deprecated_in")
    @classmethod
    def _semver_ok(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return check_semver(v)

    @field_validator("allowed_phases")
    @classmethod
    def _non_empty_phases(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) == 0:
            raise ValueError("allowed_phases must be non-empty if provided")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> ParameterDef:
        from agri_core.models.units import CANONICAL_UNITS

        if self.shape in _NUMERIC_SHAPES:
            if self.unit is None:
                raise ValueError(f"shape={self.shape} requires unit")
            if self.physical_range is None:
                raise ValueError(f"shape={self.shape} requires physical_range")
            lo, hi = self.physical_range
            if lo >= hi:
                raise ValueError("physical_range low must be < high")
            if self.enum_values is not None or self.enum_source is not None:
                raise ValueError(f"enum_values/enum_source not allowed for shape={self.shape}")
            if self.rule_schema is not None:
                raise ValueError(f"rule_schema not allowed for shape={self.shape}")
        elif self.shape in _ENUM_SHAPES:
            if self.unit is not None:
                raise ValueError(f"shape={self.shape} must have unit=null")
            if self.physical_range is not None:
                raise ValueError(f"physical_range not allowed for shape={self.shape}")
            if self.enum_values is None and self.enum_source is None:
                raise ValueError(f"shape={self.shape} requires enum_values or enum_source")
            if self.enum_values is not None and self.enum_source is not None:
                raise ValueError("cannot have both enum_values and enum_source")
            if self.enum_values is not None and len(self.enum_values) == 0:
                raise ValueError("enum_values must be non-empty if provided")
            if self.rule_schema is not None:
                raise ValueError(f"rule_schema not allowed for shape={self.shape}")
        elif self.shape == "rule":
            if self.unit is not None:
                raise ValueError("shape=rule must have unit=null")
            if self.rule_schema is None:
                raise ValueError("shape=rule requires rule_schema")
            if self.enum_values is not None or self.enum_source is not None:
                raise ValueError("enum_* not allowed for shape=rule")
        elif self.shape in ("bool", "unknown"):
            if self.unit is not None:
                raise ValueError(f"shape={self.shape} must have unit=null")
            if self.enum_values is not None or self.enum_source is not None:
                raise ValueError(f"enum_* not allowed for shape={self.shape}")
            if self.rule_schema is not None:
                raise ValueError(f"rule_schema not allowed for shape={self.shape}")

        if self.unit is not None and self.unit not in CANONICAL_UNITS:
            raise ValueError(
                f"unit {self.unit!r} not in canonical set; see models/units.py CANONICAL_UNITS"
            )

        if self.safety_class != "none" and not self.rationale:
            raise ValueError("safety_class != none requires rationale")

        if self.kind == "core" and not self.used_by:
            raise ValueError("core parameter requires used_by")

        return self
