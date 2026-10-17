"""The successful ``Result`` outcome."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    )
