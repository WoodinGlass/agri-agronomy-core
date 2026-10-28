"""Name index: normalized taxon name -> entries for resolution (M8).

The index is a pure function of ``taxa`` and ``names`` rows. It is
built eagerly when a pack loads; it is never persisted (Unicode
normalization differs across Python versions, so an on-disk index
would need a version tag). Two names that normalize to the same
string share a key; the value is a sorted tuple of
``NameIndexEntry``.

Sort order per bucket: ``(taxon_id, matched_via, language, name)``.
This is stable across runs because all four fields are deterministic.

Caller responsibility:
- ``taxa`` must have unique ``taxon_id`` (verified upstream by
  ``from_rows`` / ``_build`` before calling this builder).
- ``names`` rows whose ``taxon_id`` does not appear in ``taxa`` are
  silently dropped; FK was validated at load time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from agri_core.models.name import NameKind, NameRow
from agri_core.models.taxon import TaxonRank, TaxonRow
from agri_core.pack.normalize import normalize_name

__all__ = ["MatchedVia", "NameIndexEntry", "build_name_index"]

MatchedVia = Literal["scientific_name", "accepted_name", "names"]
"""How a ``NameIndexEntry`` matched the query.

- ``scientific_name``: the taxon's ``scientific_name`` column.
- ``accepted_name``: the taxon's ``accepted_name`` column (only added
  when it differs from ``scientific_name`` after normalization).
- ``names``: a row in ``names.csv`` for the same ``taxon_id``.
"""

# Latin is the conventional language for botanical scientific names.
# Used only for the two synthetic entries derived from ``TaxonRow``;
# ``NameRow`` entries use their own ``language`` field.
_SYNTHETIC_LANGUAGE = "la"


# slots=True: NameIndexEntry is a plain value object (constructed via
# the generated __init__, never subclassed, never built via
# object.__new__ + object.__setattr__). Slots save memory here since
# a pack can hold dozens of entries. The knowledge_set.py comment
# against slots=True applies to frozen dataclasses that use
# object.__new__ + object.__setattr__; this class does not.
# Verified on Python 3.13.18 (Colab runtime).
@dataclass(frozen=True, slots=True)
class NameIndexEntry:
    """One name entry in the resolution index.

    ``name`` and ``normalized_name`` differ: ``name`` is the display
    form (as written in the pack), ``normalized_name`` is the matching
    key produced by :func:`normalize_name`. Two different ``name``
    values may share a ``normalized_name``.
    """

    taxon_id: str
    name: str
    normalized_name: str
    language: str
    kind: NameKind
    preferred: bool
    matched_via: MatchedVia
    rank: TaxonRank
    scientific_name: str


def build_name_index(
    *,
    taxa: Iterable[TaxonRow],
    names: Iterable[NameRow],
) -> dict[str, tuple[NameIndexEntry, ...]]:
    """Build ``{normalized_name: tuple[NameIndexEntry, ...]}``.

    Each taxon contributes up to three kinds of entries:

    1. ``scientific_name`` (always).
    2. ``accepted_name`` (only if non-None and distinct after
       normalization).
    3. One entry per ``names.csv`` row for that taxon.

    Entries are not deduplicated: a name that appears both as
    ``scientific_name`` and as a ``names.csv`` row produces two
    entries (different ``matched_via``), so callers can see the
    match path.
    """
    names_by_taxon: dict[str, list[NameRow]] = {}
    for row in names:
        names_by_taxon.setdefault(row.taxon_id, []).append(row)

    acc: dict[str, list[NameIndexEntry]] = {}

    def _add(entry: NameIndexEntry) -> None:
        acc.setdefault(entry.normalized_name, []).append(entry)

    for taxon in taxa:
        sci_norm = normalize_name(taxon.scientific_name)
        _add(
            NameIndexEntry(
                taxon_id=taxon.taxon_id,
                name=taxon.scientific_name,
                normalized_name=sci_norm,
                language=_SYNTHETIC_LANGUAGE,
                kind="scientific",
                preferred=True,
                matched_via="scientific_name",
                rank=taxon.rank,
                scientific_name=taxon.scientific_name,
            )
        )

        if taxon.accepted_name is not None:
            acc_norm = normalize_name(taxon.accepted_name)
            if acc_norm != sci_norm:
                _add(
                    NameIndexEntry(
                        taxon_id=taxon.taxon_id,
                        name=taxon.accepted_name,
                        normalized_name=acc_norm,
                        language=_SYNTHETIC_LANGUAGE,
                        kind="scientific",
                        preferred=False,
                        matched_via="accepted_name",
                        rank=taxon.rank,
                        scientific_name=taxon.scientific_name,
                    )
                )

        for name_row in names_by_taxon.get(taxon.taxon_id, ()):
            _add(
                NameIndexEntry(
                    taxon_id=taxon.taxon_id,
                    name=name_row.name,
                    normalized_name=normalize_name(name_row.name),
                    language=name_row.language,
                    kind=name_row.kind,
                    preferred=name_row.preferred,
                    matched_via="names",
                    rank=taxon.rank,
                    scientific_name=taxon.scientific_name,
                )
            )

    return {
        key: tuple(sorted(entries, key=lambda e: (e.taxon_id, e.matched_via, e.language, e.name)))
        for key, entries in acc.items()
    }
