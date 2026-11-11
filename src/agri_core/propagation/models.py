"""Propagation plan models (M15, ADR-016).

P3 defines the data models and the discriminated union. The planner
that fills them from a pack (`propagation_plan()`) is P5.

M15 does not emit `ReferToAuthority`; the member is reserved for M16
when the hazard short-circuit policy for propagation is finalized.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from agri_core.models.envelope import Subject
from agri_core.models.ids import TaxonId
from agri_core.models.notices import EvidenceGrade, Notice
from agri_core.models.provenance import Provenance
from agri_core.models.refusals import (
    InsufficientInput,
    NotApplicable,
    ReferToAuthority,
    Unknown,
)

PropagationStepName = Literal["prepare", "propagate", "establish", "ready"]
"""Closed set of generic step names (ADR-016 D-M15-P1)."""


class PropagationStep(BaseModel):
    """One dated step in a propagation plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_name: PropagationStepName
    start_date: date
    end_date: date
    duration_days: int = Field(ge=1)

    @model_validator(mode="after")
    def _consistent(self) -> PropagationStep:
        if self.end_date < self.start_date:
            raise ValueError(
                f"end_date ({self.end_date}) must be >= start_date ({self.start_date})"
            )
        span = (self.end_date - self.start_date).days + 1
        if span != self.duration_days:
            raise ValueError(
                f"duration_days ({self.duration_days}) must equal "
                f"end_date - start_date + 1 = {span}"
            )
        return self


class PropagationPlan(BaseModel):
    """A successful dated propagation plan.

    ``steps`` must be contiguous: ``steps[i].start_date`` equals
    ``steps[i-1].end_date + 1 day``. ``request_id`` requires ``subject``
    (ADR-009 envelope consistency).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    taxon_id: TaxonId
    method: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    start_date: date
    steps: list[PropagationStep] = Field(min_length=1)

    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")
    provenance: Provenance
    evidence: list[EvidenceGrade]
    assumptions: list[Notice]
    warnings: list[Notice]

    @model_validator(mode="after")
    def _envelope_consistency(self) -> PropagationPlan:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self

    @model_validator(mode="after")
    def _steps_contiguous(self) -> PropagationPlan:
        for i in range(1, len(self.steps)):
            prev = self.steps[i - 1]
            cur = self.steps[i]
            if cur.start_date != prev.end_date + timedelta(days=1):
                raise ValueError(
                    f"step {i} start_date ({cur.start_date}) must be "
                    f"one day after step {i - 1} end_date ({prev.end_date})"
                )
        return self


PropagationOutcome = Annotated[
    PropagationPlan | Unknown | NotApplicable | InsufficientInput | ReferToAuthority,
    Field(discriminator="status"),
]
"""Discriminated union returned by :func:`propagation_plan` (P5).

Separate from ``Outcome`` because ``PropagationPlan.status`` is ``"ok"``,
matching ``Result.status``; combining them would make the discriminator
ambiguous (precedent: ``TaxonOutcome``, ``FactOutcome``).
"""

PropagationOutcomeAdapter: TypeAdapter[PropagationOutcome] = TypeAdapter(PropagationOutcome)
"""Validate or serialize any :data:`PropagationOutcome` value."""

__all__ = [
    "PropagationOutcome",
    "PropagationOutcomeAdapter",
    "PropagationPlan",
    "PropagationStep",
    "PropagationStepName",
]
