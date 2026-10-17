"""The ``Outcome`` union returned by every calculation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, TypeAdapter

from agri_core.models.refusals import (
    InsufficientInput,
    NotApplicable,
    ReferToLabel,
    Unknown,
)
from agri_core.models.result import Result

Outcome = Annotated[
    Result | InsufficientInput | Unknown | NotApplicable | ReferToLabel,
    Field(discriminator="status"),
]
"""Discriminated union of every possible calculation response."""

OutcomeAdapter: TypeAdapter[Outcome] = TypeAdapter(Outcome)
"""Validate or serialize any :data:`Outcome` value."""

__all__ = [
    "InsufficientInput",
    "NotApplicable",
    "Outcome",
    "OutcomeAdapter",
    "ReferToLabel",
    "Result",
    "Unknown",
]
