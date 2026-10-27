"""Validate a source pack from in-memory allowlist bytes (M6-4, M7-1)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, computed_field

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import TrapezoidValue
from agri_core.models.finding import (
    REPORT_VERSION,
    Finding,
    FindingLocation,
    FindingSeverity,
)
from agri_core.pack.errors import PackError
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.pack.loader import load_knowledge_set_from_files

__all__ = [
    "RULES",
    "ValidationReport",
    "validate_pack",
    "validate_pack_report",
]


RuleFn = Callable[[KnowledgeSet, Mapping[str, bytes]], Iterable[Finding]]
"""A pure validation rule. Runs only after a successful structural load."""


def check_trapezoid_not_degenerate(
    ks: KnowledgeSet, files: Mapping[str, bytes]
) -> Iterable[Finding]:
    """Flag trapezoids where ``pts[0] == pts[-1]`` (a collapsed trapezoid).

    The model already enforces ``a <= b <= c <= d``. If additionally
    ``a == d``, then ``a == b == c == d``: the "trapezoid" has no
    suboptimal zone and does not express a threshold. That is a scalar
    in disguise; use ``shape=scalar``.
    """
    for fact in ks.facts():
        value = fact.value
        if not isinstance(value, TrapezoidValue):
            continue
        if value.pts[0] == value.pts[-1]:
            yield Finding(
                code="PACK_TRAPEZOID_DEGENERATE",
                severity=FindingSeverity.ERROR,
                message=(
                    f"trapezoid has pts[0] == pts[-1] == {value.pts[0]}; "
                    f"a non-degenerate trapezoid needs abs_min < abs_max "
                    f"(pts={value.pts})"
                ),
                location=FindingLocation(
                    taxon_id=fact.taxon_id,
                    fact_id=fact.fact_id,
                    parameter=fact.parameter,
                    phase=fact.phase,
                ),
            )


RULES: tuple[RuleFn, ...] = (check_trapezoid_not_degenerate,)
"""Registered rules. Explicit tuple, not auto-import.

M7-1 ships empty. M7-2..M7-4 append. Review sees exactly what runs and
in what order, with no import side effects and no risk of a rule that
forgets to register.
"""


class ValidationReport(BaseModel):
    """Result of validate_pack_report().

    Findings only. ``ok`` is computed from them. The KnowledgeSet is
    returned separately so the report stays JSON-safe.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_version: int = Field(default=REPORT_VERSION)
    findings: tuple[Finding, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        return not any(f.severity == FindingSeverity.ERROR for f in self.findings)

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == FindingSeverity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == FindingSeverity.WARNING)


def _sort_key(f: Finding) -> tuple[str, int, str, str, str]:
    loc = f.location
    return (
        loc.file or "",
        loc.line or 0,
        loc.key or "",
        loc.taxon_id or "",
        f.code,
    )


def _location_from_error(exc: PackError) -> FindingLocation:
    return FindingLocation(file=exc.file, line=exc.line, key=exc.key)


def _finding_from_error(exc: PackError) -> Finding:
    return Finding(
        code=exc.code,
        severity=FindingSeverity.ERROR,
        message=str(exc),
        location=_location_from_error(exc),
    )


def _report_from_missing_key(exc: KeyError) -> ValidationReport:
    """Convert a KeyError from missing required files into a load finding."""
    key = str(exc).strip("'\"")
    finding = Finding(
        code="PACK_INVALID",
        severity=FindingSeverity.ERROR,
        message=f"missing required file in pack: {key}",
        location=FindingLocation(file=key),
    )
    return ValidationReport(findings=(finding,))


def _report_from_error(exc: PackError) -> ValidationReport:
    findings: list[Finding] = [_finding_from_error(exc)]
    for child in getattr(exc, "findings", ()):
        if isinstance(child, PackError):
            findings.append(_finding_from_error(child))
    findings.sort(key=_sort_key)
    return ValidationReport(findings=tuple(findings))


def validate_pack_report(
    files: Mapping[str, bytes],
    *,
    allow_synthetic: bool = False,
    expected_hash: str | None = None,
    dictionary: Dictionary | None = None,
) -> tuple[ValidationReport, KnowledgeSet | None]:
    """Single validation pipeline: load + rules.

    Returns ``(report, knowledge_set)``. ``knowledge_set`` is ``None`` only
    when the pack could not be loaded (report contains load findings).
    When the pack loads, ``report.findings`` contains rule findings only.

    M7-4 will extend this to also run ``license_gate``; M7-2..M7-4 append
    rule functions to ``RULES``. Callers see one function, one return type.
    """
    try:
        ks = load_knowledge_set_from_files(
            files,
            allow_synthetic=allow_synthetic,
            expected_hash=expected_hash,
            dictionary=dictionary,
        )
    except PackError as exc:
        return _report_from_error(exc), None
    except KeyError as exc:
        return _report_from_missing_key(exc), None

    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(ks, files))
    findings.sort(key=_sort_key)
    return ValidationReport(findings=tuple(findings)), ks


def validate_pack(
    files: Mapping[str, bytes],
    *,
    allow_synthetic: bool = False,
    expected_hash: str | None = None,
    dictionary: Dictionary | None = None,
) -> KnowledgeSet:
    """M6-4 API preserved: return the KnowledgeSet, raise on any error.

    Load errors keep their native PackError subclass (same as M6-4).
    Rule errors raise base PackError with the finding code embedded in
    the message. Callers who need structured errors should use
    ``validate_pack_report``.
    """
    ks = load_knowledge_set_from_files(
        files,
        allow_synthetic=allow_synthetic,
        expected_hash=expected_hash,
        dictionary=dictionary,
    )
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(ks, files))
    errors = [f for f in findings if f.severity == FindingSeverity.ERROR]
    if errors:
        first = errors[0]
        raise PackError(
            f"{first.code}: {first.message}",
            file=first.location.file,
            line=first.location.line,
            key=first.location.key,
        )
    return ks
