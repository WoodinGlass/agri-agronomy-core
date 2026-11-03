"""The successful ``Result`` outcome."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agri_core.models.envelope import Subject
from agri_core.models.notices import EvidenceGrade, Notice
from agri_core.models.provenance import Provenance


class Result(BaseModel):
    """A successful calculation.

    ``status`` is always ``"ok"``. ``value`` is always finite: NaN and
    infinity are rejected because they are not valid JSON. ``capped`` is
    ``True`` when a safety cap limited ``value``.

    Construct through the :func:`ok` factory rather than directly, so that
    the ``status`` literal cannot be forgotten.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    status: Literal["ok"]
    value: float
    unit: str
    method: str
    provenance: Provenance
    evidence: list[EvidenceGrade]
    assumptions: list[Notice]
    warnings: list[Notice]
    capped: bool
    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def _envelope_consistency(self) -> Result:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


class CategoricalResult(BaseModel):
    """A successful calculation whose answer is a category, not a number.

    ``status`` is always ``"ok_category"``. ``category`` is a stable code
    (e.g. ``"optimal"``); ``label`` is English display text and may change
    between minor releases. No unit, no ``capped`` -- categories carry
    neither. See ADR-006.

    Construct through :func:`ok_category` rather than directly, so that
    the ``status`` literal cannot be forgotten.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok_category"]
    category: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    method: str
    provenance: Provenance
    evidence: list[EvidenceGrade]
    assumptions: list[Notice]
    warnings: list[Notice]
    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def _envelope_consistency(self) -> CategoricalResult:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


def ok(
    *,
    value: float,
    unit: str,
    method: str,
    provenance: Provenance,
    evidence: list[EvidenceGrade],
    assumptions: list[Notice] | None = None,
    warnings: list[Notice] | None = None,
    capped: bool = False,
    subject: Subject | None = None,
    request_id: str | None = None,
) -> Result:
    """Build a successful :class:`Result`.

    The keyword-only signature keeps call sites self-documenting and stable
    when a future release adds fields.
    """
    return Result(
        status="ok",
        value=value,
        unit=unit,
        method=method,
        provenance=provenance,
        evidence=list(evidence),
        assumptions=list(assumptions or []),
        warnings=list(warnings or []),
        capped=capped,
        subject=subject,
        request_id=request_id,
    )


def ok_category(
    *,
    category: str,
    label: str,
    method: str,
    provenance: Provenance,
    evidence: list[EvidenceGrade],
    assumptions: list[Notice] | None = None,
    warnings: list[Notice] | None = None,
    subject: Subject | None = None,
    request_id: str | None = None,
) -> CategoricalResult:
    """Build a successful :class:`CategoricalResult`.

    Keyword-only like :func:`ok`, so future fields are non-breaking.
    """
    return CategoricalResult(
        status="ok_category",
        category=category,
        label=label,
        method=method,
        provenance=provenance,
        evidence=list(evidence),
        assumptions=list(assumptions or []),
        warnings=list(warnings or []),
        subject=subject,
        request_id=request_id,
    )


__all__ = ["CategoricalResult", "Result", "ok", "ok_category"]
