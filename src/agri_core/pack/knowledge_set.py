"""Immutable in-memory pack view (KnowledgeSet Protocol + InMemoryKnowledgeSet)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from agri_core.models.dataset import DatasetRow
from agri_core.models.fact import FactRow
from agri_core.models.hazard import HazardRow
from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack.manifest import PackManifest
from agri_core.registry.sources import SourceRow

__all__ = ["InMemoryKnowledgeSet", "KnowledgeSet"]


class KnowledgeSet(Protocol):
    """Immutable, eager, in-memory view of a pack.

    Protocol because M6 will add an SQLite-backed implementation. The
    resolver in M8 will depend only on this Protocol, not on a concrete
    class. Row iterators are sorted by primary key; ``*_for`` methods
    raise ``KeyError`` when the taxon is unknown and return an empty
    tuple when the taxon is known but has no rows of that kind.
    """

    @property
    def manifest(self) -> PackManifest: ...

    @property
    def pack_hash(self) -> str:
        """Computed hash (``"sha256:<hex>"``) of the pack contents."""

    @property
    def dictionary_version(self) -> str:
        """Dictionary version at the time the pack was loaded."""

    @property
    def verified(self) -> bool:
        """True if a manifest hash or caller-pinned hash was checked."""

    def taxon(self, taxon_id: str) -> TaxonRow:
        """Return the taxon row; ``KeyError`` if unknown."""

    def taxa(self) -> Iterator[TaxonRow]:
        """Iterate all taxa sorted by ``taxon_id``."""

    def facts_for(self, taxon_id: str, parameter: str | None = None) -> tuple[FactRow, ...]:
        """Facts attached to *taxon_id*, optionally filtered by parameter.

        ``KeyError`` if the taxon is unknown. Returns an empty tuple if
        the taxon exists but has no facts, or if *parameter* is given
        and no fact matches. Rows are sorted by ``fact_id``.
        """

    def facts(self) -> Iterator[FactRow]:
        """Iterate all facts sorted by ``fact_id``."""

    def names_for(self, taxon_id: str) -> tuple[NameRow, ...]:
        """Names attached to *taxon_id*; ``KeyError`` if taxon unknown."""

    def names(self) -> Iterator[NameRow]:
        """Iterate all names sorted by ``(taxon_id, name, language, script, kind)``."""

    def hazards_for(self, taxon_id: str) -> tuple[HazardRow, ...]:
        """Hazards attached to *taxon_id*; ``KeyError`` if taxon unknown."""

    def hazards(self) -> Iterator[HazardRow]:
        """Iterate all hazards sorted by ``(taxon_id, hazard_code)``."""

    def source(self, source_id: str) -> SourceRow:
        """Return the source row; ``KeyError`` if unknown."""

    def dataset(self, dataset_id: str) -> DatasetRow:
        """Return the dataset row; ``KeyError`` if unknown."""


# Do not add slots=True: on Python 3.10/3.11, @dataclass(slots=True)
# with frozen=True rebuilds the class and breaks super().__setattr__,
# so immutability checks raise TypeError instead of FrozenInstanceError.
# Slots save ~150 bytes per instance; there is exactly one
# InMemoryKnowledgeSet per loaded pack, so the cost is negligible.
@dataclass(frozen=True, init=False)
class InMemoryKnowledgeSet:
    """Frozen, eager InMemoryKnowledgeSet (see ``KnowledgeSet``).

    Construct via :meth:`from_rows`. All indices are built once and
    wrapped in :class:`MappingProxyType`; row collections are tuples.
    Reads are thread-safe because the underlying containers are
    immutable.
    """

    _manifest: PackManifest
    _pack_hash: str
    _dictionary_version: str
    _verified: bool
    _taxa_by_id: Mapping[str, TaxonRow]
    _taxa_sorted: tuple[TaxonRow, ...]
    _facts_by_taxon: Mapping[str, tuple[FactRow, ...]]
    _facts_by_taxon_param: Mapping[tuple[str, str], tuple[FactRow, ...]]
    _facts_all: tuple[FactRow, ...]
    _names_by_taxon: Mapping[str, tuple[NameRow, ...]]
    _names_all: tuple[NameRow, ...]
    _hazards_by_taxon: Mapping[str, tuple[HazardRow, ...]]
    _hazards_all: tuple[HazardRow, ...]
    _sources_by_id: Mapping[str, SourceRow]
    _datasets_by_id: Mapping[str, DatasetRow]

    @classmethod
    def from_rows(
        cls,
        *,
        manifest: PackManifest,
        pack_hash: str,
        dictionary_version: str,
        verified: bool = True,
        taxa: Iterable[TaxonRow] = (),
        names: Iterable[NameRow] = (),
        facts: Iterable[FactRow] = (),
        hazards: Iterable[HazardRow] = (),
        sources: Iterable[SourceRow] = (),
        datasets: Iterable[DatasetRow] = (),
    ) -> InMemoryKnowledgeSet:
        """Build a frozen KnowledgeSet from row iterables.

        Indices are built eagerly. Duplicate primary keys raise
        ``ValueError`` with the offending key set's name.
        """
        taxa_tuple = tuple(taxa)
        taxa_by_id: dict[str, TaxonRow] = {}
        for t in taxa_tuple:
            if t.taxon_id in taxa_by_id:
                raise ValueError(f"duplicate taxon_id: {t.taxon_id!r}")
            taxa_by_id[t.taxon_id] = t
        taxa_sorted = tuple(sorted(taxa_tuple, key=lambda r: r.taxon_id))

        facts_tuple = tuple(facts)
        seen_fact_ids: set[str] = set()
        facts_by_taxon_lists: dict[str, list[FactRow]] = {}
        facts_by_param_lists: dict[tuple[str, str], list[FactRow]] = {}
        for f in facts_tuple:
            if f.fact_id in seen_fact_ids:
                raise ValueError(f"duplicate fact_id: {f.fact_id!r}")
            seen_fact_ids.add(f.fact_id)
            facts_by_taxon_lists.setdefault(f.taxon_id, []).append(f)
            facts_by_param_lists.setdefault((f.taxon_id, f.parameter), []).append(f)
        facts_by_taxon: dict[str, tuple[FactRow, ...]] = {
            tid: tuple(sorted(lst, key=lambda r: r.fact_id))
            for tid, lst in facts_by_taxon_lists.items()
        }
        facts_by_param: dict[tuple[str, str], tuple[FactRow, ...]] = {
            key: tuple(sorted(lst, key=lambda r: r.fact_id))
            for key, lst in facts_by_param_lists.items()
        }
        facts_all = tuple(sorted(facts_tuple, key=lambda r: r.fact_id))

        names_tuple = tuple(names)
        seen_name_keys: set[tuple[str, str, str, str, str]] = set()
        names_by_taxon_lists: dict[str, list[NameRow]] = {}
        for n in names_tuple:
            name_key = (n.taxon_id, n.name, n.language, n.script, n.kind)
            if name_key in seen_name_keys:
                raise ValueError(f"duplicate name primary key: {name_key!r}")
            seen_name_keys.add(name_key)
            names_by_taxon_lists.setdefault(n.taxon_id, []).append(n)
        names_by_taxon: dict[str, tuple[NameRow, ...]] = {
            tid: tuple(sorted(lst, key=lambda r: (r.name, r.language, r.script, r.kind)))
            for tid, lst in names_by_taxon_lists.items()
        }
        names_all = tuple(
            sorted(
                names_tuple,
                key=lambda r: (r.taxon_id, r.name, r.language, r.script, r.kind),
            )
        )

        hazards_tuple = tuple(hazards)
        seen_hazard_keys: set[tuple[str, str]] = set()
        hazards_by_taxon_lists: dict[str, list[HazardRow]] = {}
        for h in hazards_tuple:
            hazard_key = (h.taxon_id, h.hazard_code)
            if hazard_key in seen_hazard_keys:
                raise ValueError(f"duplicate hazard primary key: {hazard_key!r}")
            seen_hazard_keys.add(hazard_key)
            hazards_by_taxon_lists.setdefault(h.taxon_id, []).append(h)
        hazards_by_taxon: dict[str, tuple[HazardRow, ...]] = {
            tid: tuple(sorted(lst, key=lambda r: r.hazard_code))
            for tid, lst in hazards_by_taxon_lists.items()
        }
        hazards_all = tuple(sorted(hazards_tuple, key=lambda r: (r.taxon_id, r.hazard_code)))

        sources_tuple = tuple(sources)
        sources_by_id: dict[str, SourceRow] = {}
        for s in sources_tuple:
            if s.id in sources_by_id:
                raise ValueError(f"duplicate source id: {s.id!r}")
            sources_by_id[s.id] = s

        datasets_tuple = tuple(datasets)
        datasets_by_id: dict[str, DatasetRow] = {}
        for d in datasets_tuple:
            if d.dataset_id in datasets_by_id:
                raise ValueError(f"duplicate dataset_id: {d.dataset_id!r}")
            datasets_by_id[d.dataset_id] = d

        ks = object.__new__(cls)
        object.__setattr__(ks, "_manifest", manifest)
        object.__setattr__(ks, "_pack_hash", pack_hash)
        object.__setattr__(ks, "_dictionary_version", dictionary_version)
        object.__setattr__(ks, "_verified", verified)
        object.__setattr__(ks, "_taxa_by_id", MappingProxyType(taxa_by_id))
        object.__setattr__(ks, "_taxa_sorted", taxa_sorted)
        object.__setattr__(ks, "_facts_by_taxon", MappingProxyType(facts_by_taxon))
        object.__setattr__(ks, "_facts_by_taxon_param", MappingProxyType(facts_by_param))
        object.__setattr__(ks, "_facts_all", facts_all)
        object.__setattr__(ks, "_names_by_taxon", MappingProxyType(names_by_taxon))
        object.__setattr__(ks, "_names_all", names_all)
        object.__setattr__(ks, "_hazards_by_taxon", MappingProxyType(hazards_by_taxon))
        object.__setattr__(ks, "_hazards_all", hazards_all)
        object.__setattr__(ks, "_sources_by_id", MappingProxyType(sources_by_id))
        object.__setattr__(ks, "_datasets_by_id", MappingProxyType(datasets_by_id))
        return ks

    @property
    def manifest(self) -> PackManifest:
        return self._manifest

    @property
    def pack_hash(self) -> str:
        return self._pack_hash

    @property
    def dictionary_version(self) -> str:
        return self._dictionary_version

    @property
    def verified(self) -> bool:
        return self._verified

    def taxon(self, taxon_id: str) -> TaxonRow:
        return self._taxa_by_id[taxon_id]

    def taxa(self) -> Iterator[TaxonRow]:
        return iter(self._taxa_sorted)

    def facts_for(self, taxon_id: str, parameter: str | None = None) -> tuple[FactRow, ...]:
        if taxon_id not in self._taxa_by_id:
            raise KeyError(taxon_id)
        if parameter is None:
            return self._facts_by_taxon.get(taxon_id, ())
        return self._facts_by_taxon_param.get((taxon_id, parameter), ())

    def facts(self) -> Iterator[FactRow]:
        return iter(self._facts_all)

    def names_for(self, taxon_id: str) -> tuple[NameRow, ...]:
        if taxon_id not in self._taxa_by_id:
            raise KeyError(taxon_id)
        return self._names_by_taxon.get(taxon_id, ())

    def names(self) -> Iterator[NameRow]:
        return iter(self._names_all)

    def hazards_for(self, taxon_id: str) -> tuple[HazardRow, ...]:
        if taxon_id not in self._taxa_by_id:
            raise KeyError(taxon_id)
        return self._hazards_by_taxon.get(taxon_id, ())

    def hazards(self) -> Iterator[HazardRow]:
        return iter(self._hazards_all)

    def source(self, source_id: str) -> SourceRow:
        return self._sources_by_id[source_id]

    def dataset(self, dataset_id: str) -> DatasetRow:
        return self._datasets_by_id[dataset_id]


def _conforms(ks: InMemoryKnowledgeSet) -> KnowledgeSet:
    """mypy structural check: InMemoryKnowledgeSet satisfies KnowledgeSet."""
    return ks
