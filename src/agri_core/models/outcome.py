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
from agri_core.models.result import CategoricalResult, Result

Outcome = Annotated[
    Result
    | CategoricalResult
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
OutcomeAdapter: TypeAdapter[Outcome] = TypeAdapter(Outcome)
"""Validate or serialize any :data:`Outcome` value."""


def is_success(outcome: Outcome) -> bool:
    """Return ``True`` for ``Result`` and ``CategoricalResult``.

    Both success variants carry ``status`` in ``{"ok", "ok_category"}``;
    every refusal variant returns ``False``. See ADR-006.
    """
    return outcome.status in ("ok", "ok_category")


__all__ = [
    "Ambiguous",
    "CategoricalResult",
    "InsufficientInput",
    "NotApplicable",
    "Outcome",
    "OutcomeAdapter",
    "ReferToAuthority",
    "ReferToLabel",
    "Result",
    "Unknown",
    "is_success",
]
