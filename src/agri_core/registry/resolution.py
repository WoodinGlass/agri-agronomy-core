"""Taxon resolution: name query -> TaxonOutcome (M8).

.. note::

   This module lives in the registry layer, not the pack layer, because
   resolution is a decision procedure over a loaded pack. It depends on
   the ``KnowledgeSet`` Protocol, not on either concrete backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from agri_core.models.fact import FactRow, FactStatus, FactValue, format_value
from agri_core.models.notices import Notice
from agri_core.models.parameter import ParameterDef
from agri_core.models.provenance import Provenance
from agri_core.models.refusals import (
    Ambiguous,
    AmbiguousCandidate,
    InsufficientInput,
    NotApplicable,
    Unknown,
)
from agri_core.models.taxon import TaxonRank, TaxonRow
from agri_core.pack.name_index import MatchedVia, NameIndexEntry
from agri_core.pack.normalize import normalize_name

if TYPE_CHECKING:
    from agri_core.pack.knowledge_set import KnowledgeSet

__all__ = [
    "FactResolved",
    "TaxonOk",
    "TaxonOutcome",
    "TaxonOutcomeAdapter",
    "resolve_fact",
    "resolve_taxon",
]

_PRECEDENCE: dict[MatchedVia, int] = {
    "scientific_name": 0,
    "accepted_name": 1,
    "names": 2,
}
"""Lower is better. ``scientific_name`` wins over ``accepted_name``, which
wins over ``names.csv``. Within the same ``matched_via``, the entry flagged
``preferred=True`` wins (``not e.preferred`` in the sort key)."""

_MAX_CANDIDATES = 20
"""Mirror of ``Ambiguous.candidates`` ``max_length``. If a query matches
more distinct taxa than this, ``Ambiguous.truncated`` is set to ``True``
and only the first ``_MAX_CANDIDATES`` (sorted by ``taxon_id``) are kept."""


class TaxonOk(BaseModel):
    """A name resolved to exactly one taxon.

    ``status`` is always ``"ok"``. This is a **separate** success model from
    :class:`agri_core.models.result.Result` because ``Result`` carries a
    numeric value; ``TaxonOk`` identifies a taxon. The two never appear in
    the same union, so the ``status="ok"`` collision is avoided by
    construction (``TaxonOutcome`` is a distinct discriminated union).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    taxon_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    matched_via: MatchedVia
    scientific_name: str = Field(min_length=1)
    rank: TaxonRank


TaxonOutcome = Annotated[
    TaxonOk | Ambiguous | Unknown,
    Field(discriminator="status"),
]
"""Discriminated union returned by :func:`resolve_taxon`.

Uses its own adapter (``TaxonOutcomeAdapter``) rather than
``OutcomeAdapter`` because ``TaxonOk`` and ``Result`` both carry
``status="ok"``; a single union would be ambiguous.
"""

TaxonOutcomeAdapter: TypeAdapter[TaxonOutcome] = TypeAdapter(TaxonOutcome)  # type: ignore[arg-type, unused-ignore]
"""Validate or serialize any :data:`TaxonOutcome` value."""


def _best(entries: tuple[NameIndexEntry, ...]) -> NameIndexEntry:
    """Pick the entry with the highest precedence match."""
    return min(
        entries,
        key=lambda e: (_PRECEDENCE[e.matched_via], not e.preferred, e.name),
    )


def resolve_taxon(pack: KnowledgeSet, name: str) -> TaxonOutcome:
    """Resolve *name* against *pack*, returning a discriminated outcome.

    Match set is the union of ``scientific_name``, ``accepted_name``, and
    ``names.csv`` entries (D3). A match to a single ``taxon_id`` yields
    :class:`TaxonOk`; more than one distinct ``taxon_id`` yields
    :class:`Ambiguous` (sorted by ``taxon_id``, truncated to 20 with
    ``truncated=True`` if necessary); zero matches yields
    :class:`Unknown` with ``code="no_match"``. An empty query after
    normalization yields ``Unknown(code="empty_input")``.

    This function is pure: it does not touch the filesystem or clock. All
    I/O happened when *pack* was loaded.
    """
    normalized = normalize_name(name)
    if not normalized:
        return Unknown(
            status="unknown",
            reason="empty name after normalization",
            code="empty_input",
        )

    entries = pack.names_index(name)
    if not entries:
        return Unknown(
            status="unknown",
            reason=f"no taxon matched {name!r}",
            code="no_match",
        )

    by_taxon: dict[str, list[NameIndexEntry]] = {}
    for e in entries:
        by_taxon.setdefault(e.taxon_id, []).append(e)

    if len(by_taxon) == 1:
        tid, tid_entries = next(iter(by_taxon.items()))
        row: TaxonRow = pack.taxon(tid)
        best = _best(tuple(tid_entries))
        return TaxonOk(
            status="ok",
            taxon_id=tid,
            name=best.name,
            matched_via=best.matched_via,
            scientific_name=row.scientific_name,
            rank=row.rank,
        )

    sorted_ids = sorted(by_taxon.keys())
    truncated = len(sorted_ids) > _MAX_CANDIDATES
    if truncated:
        sorted_ids = sorted_ids[:_MAX_CANDIDATES]
    candidates = [
        AmbiguousCandidate(
            taxon_id=tid,
            name=_best(tuple(by_taxon[tid])).name,
            note=f"matched via {_best(tuple(by_taxon[tid])).matched_via}",
        )
        for tid in sorted_ids
    ]
    return Ambiguous(
        status="ambiguous",
        candidates=candidates,
        truncated=truncated,
    )


class FactResolved(BaseModel):
    """A fact matched the query.

    ``fact`` is the winning ``FactRow``; ``value`` and ``value_pretty``
    mirror ``fact.value`` for API ergonomics. ``alternatives`` are the
    other non-superseded facts that matched the query, sorted by the
    same tie-break as the winner (more specific first, then higher
    status, then newer review, then ``fact_id``).
    ``provenance.fact_ids`` names **only** the winner.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    fact: FactRow
    value: FactValue
    value_pretty: str
    alternatives: list[FactRow]
    provenance: Provenance
    warnings: list[Notice]


_STATUS_RANK: dict[str, int] = {
    "imported": 0,
    "draft": 1,
    "reviewed": 2,
    "approved": 3,
}


def _status_rank(status: str) -> int:
    return _STATUS_RANK[status]


def _value_matches(fact_value: Any, request_value: Any) -> bool:
    """Whether a fact scope value covers the request scope value.

    - range: both are 2-element numeric lists; fact covers request when
      ``fact[0] <= request[0]`` and ``fact[1] >= request[1]``.
    - multi string/enum: both are lists; equal as sets.
    - scalar: equality (after wrapping lists of one).
    """
    if (
        isinstance(fact_value, list)
        and isinstance(request_value, list)
        and len(fact_value) == 2
        and len(request_value) == 2
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in fact_value)
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in request_value)
    ):
        return bool(fact_value[0] <= request_value[0] and fact_value[1] >= request_value[1])
    fs = set(fact_value) if isinstance(fact_value, list) else {fact_value}
    rs = set(request_value) if isinstance(request_value, list) else {request_value}
    return fs == rs


def _scope_matches(fact_scope: dict[str, Any], request_scope: dict[str, Any]) -> bool:
    """Match fact scope to request scope using union semantics.

    Fact keys subset of request keys OR request keys subset of fact
    keys; per-key value check on the intersection. Partial overlap
    (neither subset) is rejected: the fact requires a constraint the
    caller did not supply, so it cannot be verified.
    """
    fk = set(fact_scope.keys())
    rk = set(request_scope.keys())
    if not (fk <= rk or rk <= fk):
        return False
    return all(_value_matches(fact_scope[k], request_scope[k]) for k in fk & rk)


def _applies_to_matches(pdef: ParameterDef, taxon: TaxonRow) -> bool:
    at = pdef.applies_to
    if taxon.organism_group not in at.organism_groups:
        return False
    if at.archetypes is not None and taxon.archetype not in at.archetypes:
        return False
    if at.uses is not None and not (set(taxon.uses) & set(at.uses)):
        return False
    return not (at.traits is not None and not set(taxon.traits) & set(at.traits))


def _all_sources_commercial(pack: KnowledgeSet, fact: FactRow) -> bool:
    for sid in fact.src or ():
        try:
            source = pack.source(sid)
        except KeyError:
            return False
        if source.commercial_use != "yes":
            return False
    return True


def _fact_sort_key(fact: FactRow) -> tuple[int, int, int, str]:
    reviewed = fact.reviewed_at.toordinal() if fact.reviewed_at else 0
    return (
        -len(fact.scope),
        -_status_rank(fact.status),
        -reviewed,
        fact.fact_id,
    )


def resolve_fact(
    pack: KnowledgeSet,
    taxon_id: str,
    parameter: str,
    *,
    phase: str | None = None,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
    require_commercial: bool = False,
) -> FactResolved | Unknown | NotApplicable | InsufficientInput:
    """Resolve a fact query against *pack*.

    Filters (in order):

    1. ``taxon_id`` must exist in the pack; else ``Unknown(code="no_match")``.
    2. ``parameter`` must exist in the dictionary; else
       ``Unknown(code="no_match")``.
    3. ``parameter.applies_to`` must match the taxon; else ``NotApplicable``.
    4. If ``parameter.phase_set != "none"`` and ``phase`` is None or not
       allowed for the taxon's archetype, ``InsufficientInput(missing=["phase"])``.
    5. Superseded facts are excluded.
    6. Facts with status below ``min_status`` are excluded. Safety-critical
       parameters raise the effective floor to ``"reviewed"``; the elevation
       is reported as ``Notice(code="safety_min_status_raised")``.
    7. Facts whose phase does not match ``phase`` are excluded (only for
       phase-bearing parameters).
    8. Facts whose scope does not match ``scope`` are excluded (union
       semantics: fact keys subset OR request keys subset; per-key value
       check on the intersection; range scope uses cover semantics).
    9. If ``require_commercial``, facts whose sources are not all
       ``commercial_use="yes"`` are excluded; empty result yields
       ``Unknown(code="license_excluded")``.

    The winner is the most specific candidate (largest ``len(scope)``), then
    highest status, then most recent review, then smallest ``fact_id``. If
    any alternative carries a different ``value``, a
    ``Notice(code="fact_conflict")`` is attached to the warnings.

    This function is pure apart from the ``pack`` it reads through; it does
    not touch the filesystem or clock.
    """
    request_scope = scope or {}

    # 1. taxon exists
    try:
        taxon = pack.taxon(taxon_id)
    except KeyError:
        return Unknown(
            status="unknown",
            reason=f"taxon {taxon_id!r} not in pack",
            code="no_match",
        )

    # 2. parameter exists
    try:
        pdef = pack.dictionary.lookup(parameter)
    except KeyError:
        return Unknown(
            status="unknown",
            reason=f"parameter {parameter!r} not in dictionary",
            code="no_match",
        )

    # 3. applies_to
    if not _applies_to_matches(pdef, taxon):
        return NotApplicable(
            status="not_applicable",
            reason=f"parameter {parameter!r} does not apply to taxon {taxon_id!r}",
        )

    # 4. phase
    if pdef.phase_set != "none":
        if phase is None:
            return InsufficientInput(
                status="insufficient_input",
                missing=["phase"],
            )
        allowed = pdef.allowed_phases
        if allowed is None:
            allowed = pack.dictionary.phases_by_archetype.get(taxon.archetype)
        if allowed is not None and phase not in allowed:
            return InsufficientInput(
                status="insufficient_input",
                missing=["phase"],
            )

    # 5. safety floor
    warnings: list[Notice] = []
    effective_min = min_status
    if pdef.safety_critical:
        floor: FactStatus = "reviewed"
        if effective_min is None or _status_rank(effective_min) < _status_rank(floor):
            effective_min = floor
            warnings.append(
                Notice(
                    code="safety_min_status_raised",
                    message=(
                        f"parameter {parameter!r} has safety_class={pdef.safety_class!r}; "
                        f"min_status raised to 'reviewed'"
                    ),
                )
            )

    # 6-8. filter facts
    try:
        all_facts = pack.facts_for(taxon_id, parameter)
    except KeyError:
        all_facts = ()

    candidates: list[FactRow] = []
    for f in all_facts:
        if f.superseded_by is not None:
            continue
        if effective_min is not None and _status_rank(f.status) < _status_rank(effective_min):
            continue
        if pdef.phase_set != "none" and f.phase != phase:
            continue
        if not _scope_matches(f.scope, request_scope):
            continue
        candidates.append(f)

    if not candidates:
        return Unknown(
            status="unknown",
            reason=(
                f"no fact for taxon {taxon_id!r}, parameter {parameter!r} "
                f"matching the given constraints"
            ),
            code="no_match",
        )

    # 9. license gate
    if require_commercial:
        licensed = [f for f in candidates if _all_sources_commercial(pack, f)]
        if not licensed:
            return Unknown(
                status="unknown",
                reason="all matching facts are excluded by license gate",
                code="license_excluded",
            )
        candidates = licensed

    # winner + alternatives
    candidates.sort(key=_fact_sort_key)
    winner = candidates[0]
    alternatives = candidates[1:]

    if any(alt.value != winner.value for alt in alternatives):
        warnings.append(
            Notice(
                code="fact_conflict",
                message=(
                    f"{sum(1 for alt in alternatives if alt.value != winner.value)} "
                    f"alternative fact(s) disagree with winner {winner.fact_id}"
                ),
            )
        )

    source_ids = sorted(set(winner.src or ()))
    provenance = Provenance(
        fact_ids=[winner.fact_id],
        pack_version=pack.manifest.version,
        pack_hash=pack.pack_hash,
        source_ids=source_ids,
    )

    return FactResolved(
        status="ok",
        fact=winner,
        value=winner.value,
        value_pretty=format_value(winner.value),
        alternatives=alternatives,
        provenance=provenance,
        warnings=warnings,
    )
