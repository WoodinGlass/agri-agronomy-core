"""The ``Outcome`` union returned by every calculation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, TypeAdapter

from agri_core.models.refusals import (
    Ambiguous,
    InsufficientInput,
    NotApplicable,
    ReferToAuthority,
    ReferToLabel,
    Unknown,
)
from agri_core.models.result import Result

Outcome = Annotated[
    Result
    | InsufficientInput
    | Unknown
    | NotApplicable
    | ReferToLabel
    | Ambiguous
    | ReferToAuthority,
    Field(discriminator="status"),
]
"""Discriminated union of every possible calculation response."""

# mypy strict cannot see through Annotated at the TypeAdapter call site;
# pydantic resolves it at runtime (tests exercise both validate_python and
# dump_python through OutcomeAdapter).
OutcomeAdapter: TypeAdapter[Outcome] = TypeAdapter(Outcome)  # type: ignore[arg-type, unused-ignore]
"""Validate or serialize any :data:`Outcome` value."""

__all__ = [
    "Ambiguous",
    "InsufficientInput",
    "NotApplicable",
    "Outcome",
    "OutcomeAdapter",
    "ReferToAuthority",
    "ReferToLabel",
    "Result",
    "Unknown",
]
