"""Structured notices attached to calculation results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceGrade = Literal["A", "B", "C", "D"]
"""Evidence grade for a profile value.

``A`` is strongest (guideline or peer-reviewed); ``D`` is weakest (anecdotal).
The full rubric lives in ``docs/REVIEW_GUIDE.md``.
"""


class Notice(BaseModel):
    """A structured warning or assumption attached to a result.

    ``code`` is a stable snake_case identifier and part of the contract.
    ``message`` is human-readable and may change between releases.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1)
