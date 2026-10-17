"""Refusal outcomes: what a calculation returns when it cannot answer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


def insufficient_input(missing: list[str]) -> InsufficientInput:
    return InsufficientInput(status="insufficient_input", missing=missing)


def unknown(reason: str) -> Unknown:
    return Unknown(status="unknown", reason=reason)


def not_applicable(reason: str) -> NotApplicable:
    return NotApplicable(status="not_applicable", reason=reason)


def refer_to_label(reason: str) -> ReferToLabel:
    return ReferToLabel(status="refer_to_label", reason=reason)
