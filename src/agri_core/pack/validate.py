"""Validate a source pack from in-memory allowlist bytes (M6-4, M7-1)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, computed_field

from agri_core.models.canonical import canonical_json
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
from agri_core.pack.tables import TABLES, read_table
from agri_core.registry.sources import (
    is_nc_license,
    is_nd_license,
    is_sa_license,
)

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


def check_superseded_self(ks: KnowledgeSet, files: Mapping[str, bytes]) -> Iterable[Finding]:
    """Flag facts that reference themselves via ``superseded_by``."""
    for fact in ks.facts():
        if fact.superseded_by == fact.fact_id:
            yield Finding(
                code="PACK_SUPERSEDED_SELF",
                severity=FindingSeverity.ERROR,
                message=(
                    f"fact {fact.fact_id} supersedes itself; "
                    f"superseded_by must be a different fact_id"
                ),
                location=FindingLocation(
                    taxon_id=fact.taxon_id,
                    fact_id=fact.fact_id,
                    parameter=fact.parameter,
                ),
            )


def check_superseded_cycle(ks: KnowledgeSet, files: Mapping[str, bytes]) -> Iterable[Finding]:
    """Detect cycles in the ``superseded_by`` chain (excluding self-loops).

    ``superseded_by`` is a single pointer per fact, so chains are simple
    paths ending either in ``None`` or in a cycle. We walk each chain
    forward, tracking local path; when a node repeats within the path,
    that sub-path is a cycle. One finding per cycle, anchored at the
    smallest ``fact_id`` in the cycle for determinism. Self-loops are
    excluded (``check_superseded_self`` handles them).
    """
    facts_by_id = {f.fact_id: f for f in ks.facts()}
    visited: set[str] = set()
    reported: set[frozenset[str]] = set()

    for start in sorted(facts_by_id):
        if start in visited:
            continue
        path: list[str] = []
        local_seen: dict[str, int] = {}
        node: str | None = start

        while node is not None and node not in visited and node not in local_seen:
            local_seen[node] = len(path)
            path.append(node)
            fact = facts_by_id.get(node)
            nxt = fact.superseded_by if fact else None
            node = nxt if (nxt is not None and nxt in facts_by_id) else None

        if node is not None and node in local_seen:
            cycle = frozenset(path[local_seen[node] :])
            if len(cycle) >= 2 and cycle not in reported:
                reported.add(cycle)
                anchor = min(cycle)
                anchor_fact = facts_by_id[anchor]
                yield Finding(
                    code="PACK_SUPERSEDED_CYCLE",
                    severity=FindingSeverity.ERROR,
                    message=(f"cycle in superseded_by: {' -> '.join(sorted(cycle))} -> ..."),
                    location=FindingLocation(
                        taxon_id=anchor_fact.taxon_id,
                        fact_id=anchor,
                        parameter=anchor_fact.parameter,
                    ),
                )

        for p in path:
            visited.add(p)


def check_fact_key_duplicate(ks: KnowledgeSet, files: Mapping[str, bytes]) -> Iterable[Finding]:
    """Flag live facts with identical fact keys **and different values**.

    Fact key = ``(taxon_id, parameter, phase, canonical_scope)``.
    Same key with same value across different ``src`` is corroboration,
    not a duplicate. Superseded facts are excluded from this check.
    """
    by_key: dict[tuple[str, str, str | None, str], object] = {}
    for fact in ks.facts():
        if fact.superseded_by is not None:
            continue
        scope_key = canonical_json(fact.scope).decode("utf-8")
        key = (fact.taxon_id, fact.parameter, fact.phase, scope_key)
        if key not in by_key:
            by_key[key] = fact
            continue
        first = by_key[key]
        # first and fact are FactRow; compare values via Pydantic equality.
        if getattr(first, "value", None) != fact.value:
            yield Finding(
                code="PACK_FACT_KEY_DUPLICATE",
                severity=FindingSeverity.ERROR,
                message=(
                    f"conflicting facts for "
                    f"(taxon={fact.taxon_id}, parameter={fact.parameter!r}, "
                    f"phase={fact.phase!r}, scope={scope_key}): "
                    f"{getattr(first, 'fact_id', '?')} vs {fact.fact_id}; "
                    f"supersede one via superseded_by"
                ),
                location=FindingLocation(
                    taxon_id=fact.taxon_id,
                    fact_id=fact.fact_id,
                    parameter=fact.parameter,
                    phase=fact.phase,
                ),
            )


def check_license_source_nc_commercial(
    ks: KnowledgeSet, files: Mapping[str, bytes]
) -> Iterable[Finding]:
    """Flag non-commercial sources marked ``commercial_use=yes``.

    A source declared NC (CC-BY-NC-*, LicenseRef-NC-*, etc.) with
    ``commercial_use=yes`` contradicts itself: the row asserts
    commercial use is permitted, the license forbids it. Pack-level
    promotion of ``SRC001`` from ``agri-core lint-sources``.
    """
    table = read_table(TABLES["sources"], files["sources.csv"], source_name="sources.csv")
    for row in table.rows:
        if row.get("commercial_use") == "yes" and is_nc_license(row.get("license", "")):
            sid = row["id"]
            yield Finding(
                code="PACK_LICENSE_NC_COMMERCIAL",
                severity=FindingSeverity.ERROR,
                message=(
                    f"source {sid} has non-commercial license "
                    f"{row['license']!r} but commercial_use=yes"
                ),
                location=FindingLocation(file="sources.csv", key=sid),
            )


def check_license_dataset_sa_nd(ks: KnowledgeSet, files: Mapping[str, bytes]) -> Iterable[Finding]:
    """Flag SA/ND datasets that any fact references.

    ShareAlike and NoDerivatives forbid redistribution of derived values
    under this repository's Apache-2.0 license. Unreferenced datasets
    are not flagged (dead weight, not a redistribution problem).
    """
    table = read_table(TABLES["datasets"], files["datasets.csv"], source_name="datasets.csv")
    by_id = {row["dataset_id"]: row for row in table.rows}
    referenced = sorted({f.dataset_id for f in ks.facts() if f.dataset_id})
    for did in referenced:
        row = by_id.get(did)
        if row is None:
            continue  # FK check fires elsewhere (PACK_FK_VIOLATION)
        lic = row.get("license", "")
        if is_sa_license(lic) or is_nd_license(lic):
            yield Finding(
                code="PACK_LICENSE_DATASET_SA_ND",
                severity=FindingSeverity.ERROR,
                message=(
                    f"dataset {did} has {lic!r} (SA/ND) and is referenced "
                    f"by a fact; derived values cannot be redistributed "
                    f"under this pack's license"
                ),
                location=FindingLocation(file="datasets.csv", key=did),
            )


RULES: tuple[RuleFn, ...] = (
    check_trapezoid_not_degenerate,
    check_superseded_self,
    check_superseded_cycle,
    check_fact_key_duplicate,
    check_license_source_nc_commercial,
    check_license_dataset_sa_nd,
)
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
