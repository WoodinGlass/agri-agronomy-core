"""Refusal outcomes: what a calculation returns when it cannot answer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agri_core.models.envelope import Subject
from agri_core.models.notices import Notice

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

    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @field_validator("missing")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("missing must contain at least one item")
        for item in v:
            if not item:
                raise ValueError("missing items must be non-empty strings")
        return v

    @model_validator(mode="after")
    def _envelope_consistency(self) -> InsufficientInput:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


class Unknown(BaseModel):
    """The answer needs a value the profile marks as unknown.

    This includes the case where no value covers the requested scope.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["unknown"]
    reason: str = Field(min_length=1)
    code: Annotated[str, Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")] | None = None
    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")
    filter_counts: dict[str, int] | None = None
    warnings: list[Notice] = Field(default_factory=list)

    @model_validator(mode="after")
    def _envelope_consistency(self) -> Unknown:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


class NotApplicable(BaseModel):
    """The question does not apply (no standard Kc, propagation method not used, etc.)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_applicable"]
    reason: str = Field(min_length=1)
    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def _envelope_consistency(self) -> NotApplicable:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


class ReferToLabel(BaseModel):
    """Pesticides are out of scope; the caller follows the label and local regulations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["refer_to_label"]
    reason: str = Field(min_length=1)
    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def _envelope_consistency(self) -> ReferToLabel:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


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
    truncated: bool = False

    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @field_validator("candidates")
    @classmethod
    def _unique_taxon_ids(cls, v: list[AmbiguousCandidate]) -> list[AmbiguousCandidate]:
        ids = [c.taxon_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("taxon_id must be unique within candidates")
        return v

    @model_validator(mode="after")
    def _envelope_consistency(self) -> Ambiguous:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


class ReferToAuthority(BaseModel):
    """The answer depends on a legal or regulatory authority; the caller must consult it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["refer_to_authority"]
    reason: str = Field(min_length=1)
    flags: list[FlagCode] = Field(default_factory=list)

    subject: Subject | None = None
    request_id: str | None = Field(default=None, pattern=r"^req_[0-9a-f]{32}$")

    @field_validator("flags")
    @classmethod
    def _unique_sorted(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("flags must be unique")
        return sorted(v)

    @model_validator(mode="after")
    def _envelope_consistency(self) -> ReferToAuthority:
        if self.request_id is not None and self.subject is None:
            raise ValueError("request_id requires subject")
        return self


def insufficient_input(
    missing: list[str], *, subject: Subject | None = None, request_id: str | None = None
) -> InsufficientInput:
    """Refuse because required input is missing.

    *missing* lists the input names the caller must supply.
    See ADR-009 for the envelope fields (``subject``, ``request_id``).
    """
    return InsufficientInput(
        status="insufficient_input", missing=missing, subject=subject, request_id=request_id
    )


def unknown(
    reason: str,
    code: str | None = None,
    *,
    subject: Subject | None = None,
    request_id: str | None = None,
) -> Unknown:
    """Refuse because no fact covers the request.

    *code* is a stable registry code from
    ``schema/unknown_code_registry.json`` when one applies; ``None`` otherwise.
    """
    return Unknown(
        status="unknown", reason=reason, code=code, subject=subject, request_id=request_id
    )


def not_applicable(
    reason: str, *, subject: Subject | None = None, request_id: str | None = None
) -> NotApplicable:
    """Refuse because the question does not apply.

    For example: no standard Kc for this taxon, or a propagation method
    the taxon does not use.
    """
    return NotApplicable(
        status="not_applicable", reason=reason, subject=subject, request_id=request_id
    )


def refer_to_label(
    reason: str, *, subject: Subject | None = None, request_id: str | None = None
) -> ReferToLabel:
    """Refuse because the answer is a plant-protection question.

    Pesticide, herbicide and fungicide doses are never computed by this
    library. Follow the product label and local regulations.
    See ADR-007 for the two-tier guard.
    """
    return ReferToLabel(
        status="refer_to_label", reason=reason, subject=subject, request_id=request_id
    )


def ambiguous(
    candidates: list[AmbiguousCandidate],
    *,
    truncated: bool = False,
    subject: Subject | None = None,
    request_id: str | None = None,
) -> Ambiguous:
    """Refuse because a taxon name matched more than one candidate.

    *candidates* is capped at 20 (see ``_MAX_CANDIDATES``);
    ``truncated=True`` means the cap was hit and the caller must narrow
    the query.
    """
    return Ambiguous(
        status="ambiguous",
        candidates=candidates,
        truncated=truncated,
        subject=subject,
        request_id=request_id,
    )


def refer_to_authority(
    reason: str,
    flags: list[str] | None = None,
    *,
    subject: Subject | None = None,
    request_id: str | None = None,
) -> ReferToAuthority:
    """Refuse because the answer depends on a legal or regulatory authority.

    *flags* is a sorted, unique list of stable uppercase codes naming the
    authorities involved (for example ``["CITES"]``, ``["EU_NITRATES"]``).
    """
    return ReferToAuthority(
        status="refer_to_authority",
        reason=reason,
        flags=list(flags or []),
        subject=subject,
        request_id=request_id,
    )
