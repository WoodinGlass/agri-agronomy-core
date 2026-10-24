"""Parameter definition model.

The model validates *structure*: shape consistency, unit presence, semver
format, non-empty used_by for core parameters. Cross-reference checks
(stage exists in vocab, archetype exists, used_by module exists, trait
exists) happen at validate time against the manifest's dictionary_version,
not here — the model stays stateless.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ParameterShape = Literal["trapezoid", "range", "scalar", "enum", "bool", "rule", "unknown"]
ParameterKind = Literal["core", "extension"]


class AppliesTo(BaseModel):
    """Dimensions this parameter applies to.

    Empty list = wildcard (applies to all values of that dimension).
    ``organism_groups=None`` means no filter; a non-empty list restricts
    the parameter to those groups.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    archetypes: list[str] = Field(default_factory=list)
    uses: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    organism_groups: list[str] | None = None


class ParameterDef(BaseModel):
    """Definition of one parameter in the core dictionary or in a pack."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    stage: str
    shape: ParameterShape
    unit: str | None = None
    physical_range: tuple[float, float] | None = None
    phase_set: str = "none"
    applies_to: AppliesTo
    kind: ParameterKind
    used_by: list[str] = Field(default_factory=list)
    tier_required: bool = False
    safety_critical: bool = False
    description: str = Field(min_length=1)
    introduced_in: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    deprecated_in: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    replaced_by: str | None = None
    enum_values: list[str] | None = None
    rule_schema: dict[str, object] | None = None

    @model_validator(mode="after")
    def _check_shape_consistency(self) -> ParameterDef:
        if self.shape == "enum":
            if not self.enum_values:
                raise ValueError("shape=enum requires non-empty enum_values")
        elif self.enum_values is not None:
            raise ValueError("enum_values only allowed for shape=enum")

        if self.shape == "rule":
            if not self.rule_schema:
                raise ValueError("shape=rule requires non-empty rule_schema")
        elif self.rule_schema is not None:
            raise ValueError("rule_schema only allowed for shape=rule")

        if self.shape in ("enum", "bool", "unknown") and self.unit is not None:
            raise ValueError(f"shape={self.shape} must have unit=null")

        if self.unit is not None and not self.unit:
            raise ValueError("unit must be non-empty string or null")

        if self.kind == "core" and not self.used_by:
            raise ValueError("core parameter must declare at least one used_by module")

        if self.physical_range is not None:
            lo, hi = self.physical_range
            if lo >= hi:
                raise ValueError(f"physical_range low ({lo}) must be < high ({hi})")

        return self
