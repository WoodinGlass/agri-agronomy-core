"""Refusal outcomes: what a calculation returns when it cannot answer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FlagCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
"""Stable uppercase code for ``ReferToAuthority.flags``."""


class InsufficientInput(BaseModel):
    """A required input is missing.

    ``missing`` names each missing input in the caller's vocabulary (for
    example ``"temp_c"`` or ``"ec_to_ppm_factor (choose 0.5, 0.64 or 0.7)"``).
    Each entry must be a non-empty string.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["insufficient_input"]
    missing: list[str]

    @field_validator("missing")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("missing must contain at least one item")
        for item in v:
            if not item:
                raise ValueError("missing items must be non-empty strings")
        return v


class Unknown(BaseModel):
    """The answer needs a value the profile marks as unknown.

    This includes the case where no value covers the requested scope.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["unknown"]
    reason: str = Field(min_length=1)


class NotApplicable(BaseModel):
    """The question does not apply (no standard Kc, propagation method not used, etc.)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_applicable"]
    reason: str = Field(min_length=1)


class ReferToLabel(BaseModel):
    """Pesticides are out of scope; the caller follows the label and local regulations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["refer_to_label"]
    reason: str = Field(min_length=1)


class AmbiguousCandidate(BaseModel):
    """One possible taxon when a name resolves to more than one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    taxon_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    note: str | None = None


class Ambiguous(BaseModel):
    """A name matched more than one taxon; the caller must choose one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ambiguous"]
    candidates: list[AmbiguousCandidate] = Field(min_length=2, max_length=20)

    @field_validator("candidates")
    @classmethod
    def _unique_taxon_ids(cls, v: list[AmbiguousCandidate]) -> list[AmbiguousCandidate]:
        ids = [c.taxon_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("taxon_id must be unique within candidates")
        return v


class ReferToAuthority(BaseModel):
    """The answer depends on a legal or regulatory authority; the caller must consult it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["refer_to_authority"]
    reason: str = Field(min_length=1)
    flags: list[FlagCode] = Field(default_factory=list)

    @field_validator("flags")
    @classmethod
    def _unique_sorted(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("flags must be unique")
        return sorted(v)


def insufficient_input(missing: list[str]) -> InsufficientInput:
    return InsufficientInput(status="insufficient_input", missing=missing)


def unknown(reason: str) -> Unknown:
    return Unknown(status="unknown", reason=reason)


def not_applicable(reason: str) -> NotApplicable:
    return NotApplicable(status="not_applicable", reason=reason)


def refer_to_label(reason: str) -> ReferToLabel:
    return ReferToLabel(status="refer_to_label", reason=reason)


def ambiguous(candidates: list[AmbiguousCandidate]) -> Ambiguous:
    return Ambiguous(status="ambiguous", candidates=candidates)


def refer_to_authority(reason: str, flags: list[str] | None = None) -> ReferToAuthority:
    return ReferToAuthority(status="refer_to_authority", reason=reason, flags=list(flags or []))
