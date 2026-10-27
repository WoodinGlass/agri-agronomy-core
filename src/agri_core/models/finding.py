"""Validation findings: data, not exceptions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

REPORT_VERSION: int = 1
"""Wire-format version of ValidationReport. Bumped only on breaking changes."""


class FindingSeverity(StrEnum):
    """Severity of a validation finding."""

    ERROR = "error"
    WARNING = "warning"


class FindingLocation(BaseModel):
    """Where a finding points. All fields optional; at least one recommended."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    key: str | None = None
    taxon_id: str | None = None
    fact_id: str | None = None
    parameter: str | None = None
    phase: str | None = None


class Finding(BaseModel):
    """One finding from validation.

    Codes are stable; messages are not. A finding is data, not an
    exception, so it can be serialized, sorted, deduplicated.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,}$")
    severity: FindingSeverity
    message: str = Field(min_length=1)
    location: FindingLocation = Field(default_factory=FindingLocation)


__all__ = ["REPORT_VERSION", "Finding", "FindingLocation", "FindingSeverity"]
