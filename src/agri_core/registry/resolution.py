"""Taxon resolution: name query -> TaxonOutcome (M8).

.. note::

   This module lives in the registry layer, not the pack layer, because
   resolution is a decision procedure over a loaded pack. It depends on
   the ``KnowledgeSet`` Protocol, not on either concrete backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from agri_core.models.refusals import Ambiguous, AmbiguousCandidate, Unknown
from agri_core.models.taxon import TaxonRank, TaxonRow
from agri_core.pack.name_index import MatchedVia, NameIndexEntry
from agri_core.pack.normalize import normalize_name

if TYPE_CHECKING:
    from agri_core.pack.knowledge_set import KnowledgeSet

__all__ = [
    "TaxonOk",
    "TaxonOutcome",
    "TaxonOutcomeAdapter",
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
