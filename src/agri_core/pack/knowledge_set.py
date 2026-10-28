"""KnowledgeSet Protocol and its in-memory and SQLite implementations."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from agri_core.models.dataset import DatasetRow
from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow
from agri_core.models.hazard import HazardRow
from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack.errors import PackStaleArtifactError
from agri_core.pack.manifest import PackManifest
from agri_core.pack.name_index import NameIndexEntry, build_name_index
from agri_core.pack.normalize import normalize_name
from agri_core.pack.tables import TABLES, TableSpec
from agri_core.registry.sources import SourceRow

__all__ = ["InMemoryKnowledgeSet", "KnowledgeSet", "SQLiteKnowledgeSet"]

_T = TypeVar("_T", bound=BaseModel)
_PACK_HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


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

    @property
    def dictionary(self) -> Dictionary:
        """The full dictionary this pack was loaded against."""

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

    def names_index(self, query: str) -> tuple[NameIndexEntry, ...]:
        """Entries whose normalized name matches ``normalize_name(query)``.

        Sorted by ``(taxon_id, matched_via, language, name)``. Empty tuple
        if no entries match.
        """


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
    _dictionary: Dictionary
    _taxa_by_id: Mapping[str, TaxonRow]
    _taxa_sorted: tuple[TaxonRow, ...]
    _facts_by_taxon: Mapping[str, tuple[FactRow, ...]]
    _facts_by_taxon_param: Mapping[tuple[str, str], tuple[FactRow, ...]]
    _facts_all: tuple[FactRow, ...]
    _names_by_taxon: Mapping[str, tuple[NameRow, ...]]
    _names_all: tuple[NameRow, ...]
    _name_index: Mapping[str, tuple[NameIndexEntry, ...]]
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
        dictionary: Dictionary,
        verified: bool = False,
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
        if not _PACK_HASH_RE.match(pack_hash):
            raise ValueError(f"pack_hash must match 'sha256:<64 hex>', got {pack_hash!r}")
        if manifest.content_hash is not None and pack_hash != manifest.content_hash:
            raise ValueError(
                f"pack_hash {pack_hash!r} != manifest.content_hash {manifest.content_hash!r}"
            )
        if dictionary_version != dictionary.version:
            raise ValueError(
                f"dictionary_version {dictionary_version!r} != "
                f"dictionary.version {dictionary.version!r}"
            )
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
        object.__setattr__(ks, "_dictionary", dictionary)
        object.__setattr__(ks, "_taxa_by_id", MappingProxyType(taxa_by_id))
        object.__setattr__(ks, "_taxa_sorted", taxa_sorted)
        object.__setattr__(ks, "_facts_by_taxon", MappingProxyType(facts_by_taxon))
        object.__setattr__(ks, "_facts_by_taxon_param", MappingProxyType(facts_by_param))
        object.__setattr__(ks, "_facts_all", facts_all)
        object.__setattr__(ks, "_names_by_taxon", MappingProxyType(names_by_taxon))
        object.__setattr__(ks, "_names_all", names_all)
        object.__setattr__(
            ks,
            "_name_index",
            MappingProxyType(build_name_index(taxa=taxa_sorted, names=names_all)),
        )
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

    @property
    def dictionary(self) -> Dictionary:
        return self._dictionary

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

    def names_index(self, query: str) -> tuple[NameIndexEntry, ...]:
        normalized = normalize_name(query)
        return self._name_index.get(normalized, ())


def _conforms(ks: InMemoryKnowledgeSet) -> KnowledgeSet:
    """mypy structural check: InMemoryKnowledgeSet satisfies KnowledgeSet."""
    return ks


# ---- SQLiteKnowledgeSet (M6-2) ----------------------------------------


def _sqlite_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro&immutable=1"


def _row_to_dict(row: sqlite3.Row, spec: TableSpec) -> dict[str, Any]:
    """Decode a SQLite row into the shape Pydantic expects.

    Mirrors the writer in ``pack/sqlite_schema.py``: ``list_str`` cells
    are pipe-joined (sorted on write), JSON cells are canonical JSON,
    everything else is stored as-is (str / int / float / bool-as-int /
    date-as-ISO). Pydantic performs the final conversion to the row model.
    """
    out: dict[str, Any] = {}
    for col in spec.columns:
        v = row[col.name]
        if v is None:
            out[col.name] = None
        elif col.type == "list_str":
            out[col.name] = v.split("|") if v else []
        elif col.type in ("dict_str_str", "json"):
            out[col.name] = json.loads(v)
        else:
            out[col.name] = v
    return out


# Do not add slots=True: on Python 3.10/3.11 @dataclass(slots=True) with
# frozen=True rebuilds the class and breaks super().__setattr__. See the
# comment on InMemoryKnowledgeSet.
def _read_raw_rows_for_index(
    ks: SQLiteKnowledgeSet,
) -> tuple[tuple[TaxonRow, ...], tuple[NameRow, ...]]:
    """Read taxa and names rows from SQLite to build the name index.

    Uses ``model_construct`` — rows were validated at pack-build time,
    so ``model_validate`` per row is unnecessary.
    """
    conn = ks._connect()
    try:
        taxa_rows = conn.execute(
            "SELECT taxon_id, rank, scientific_name, accepted_name FROM taxa"
        ).fetchall()
        names_rows = conn.execute(
            "SELECT taxon_id, name, language, kind, preferred FROM names"
        ).fetchall()
    finally:
        conn.close()

    taxa = tuple(
        TaxonRow.model_construct(
            taxon_id=r["taxon_id"],
            rank=r["rank"],
            scientific_name=r["scientific_name"],
            accepted_name=r["accepted_name"],
        )
        for r in taxa_rows
    )
    names = tuple(
        NameRow.model_construct(
            taxon_id=r["taxon_id"],
            name=r["name"],
            language=r["language"],
            kind=r["kind"],
            preferred=bool(r["preferred"]),
        )
        for r in names_rows
    )
    return taxa, names


@dataclass(frozen=True, init=False)
class SQLiteKnowledgeSet:
    """Read-only SQLite-backed KnowledgeSet.

    Each method opens a fresh connection in ``mode=ro&immutable=1`` with
    ``query_only=ON`` and ``trusted_schema=OFF``, runs one query, and
    closes. No state is cached; reads are thread-safe by construction.
    Rows are validated with ``model_validate`` before being returned.

    Construct via :meth:`_build` from the loader after all integrity
    checks have passed. Not part of the public API; consumers depend on
    the ``KnowledgeSet`` Protocol.
    """

    _sqlite_path: Path
    _manifest: PackManifest
    _pack_hash: str
    _dictionary_version: str
    _verified: bool
    _dictionary: Dictionary
    _stat_snapshot: tuple[int, int, int]
    _name_index: Mapping[str, tuple[NameIndexEntry, ...]]

    @classmethod
    def _build(
        cls,
        *,
        sqlite_path: Path,
        manifest: PackManifest,
        pack_hash: str,
        dictionary_version: str,
        dictionary: Dictionary,
        verified: bool,
    ) -> SQLiteKnowledgeSet:
        if not _PACK_HASH_RE.match(pack_hash):
            raise ValueError(f"pack_hash must match 'sha256:<64 hex>', got {pack_hash!r}")
        if manifest.content_hash is not None and pack_hash != manifest.content_hash:
            raise ValueError(
                f"pack_hash {pack_hash!r} != manifest.content_hash {manifest.content_hash!r}"
            )
        if dictionary_version != dictionary.version:
            raise ValueError(
                f"dictionary_version {dictionary_version!r} != "
                f"dictionary.version {dictionary.version!r}"
            )

        path = Path(sqlite_path)
        st = path.stat()
        stat_snapshot = (st.st_size, st.st_mtime_ns, st.st_ino)

        ks = object.__new__(cls)
        object.__setattr__(ks, "_sqlite_path", path)
        object.__setattr__(ks, "_manifest", manifest)
        object.__setattr__(ks, "_pack_hash", pack_hash)
        object.__setattr__(ks, "_dictionary_version", dictionary_version)
        object.__setattr__(ks, "_verified", verified)
        object.__setattr__(ks, "_dictionary", dictionary)
        object.__setattr__(ks, "_stat_snapshot", stat_snapshot)
        raw_taxa, raw_names = _read_raw_rows_for_index(ks)
        object.__setattr__(
            ks,
            "_name_index",
            MappingProxyType(build_name_index(taxa=raw_taxa, names=raw_names)),
        )
        return ks

    # ---- internal -----------------------------------------------------

    def _check_not_stale(self) -> None:
        st = self._sqlite_path.stat()
        if (st.st_size, st.st_mtime_ns, st.st_ino) != self._stat_snapshot:
            raise PackStaleArtifactError(
                f"{self._sqlite_path} changed since load; re-load the pack",
                file="pack.sqlite",
            )

    def _connect(self) -> sqlite3.Connection:
        self._check_not_stale()
        conn = sqlite3.connect(_sqlite_uri(self._sqlite_path), uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA trusted_schema = OFF")
        return conn

    def _taxon_exists(self, conn: sqlite3.Connection, taxon_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM taxa WHERE taxon_id = ? LIMIT 1", (taxon_id,)).fetchone()
        return row is not None

    def _row_or_none(
        self,
        sql: str,
        params: tuple[Any, ...],
        spec: TableSpec,
        model: type[_T],
    ) -> _T | None:
        conn = self._connect()
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return model.model_validate(_row_to_dict(row, spec))

    def _iter_models(
        self,
        sql: str,
        spec: TableSpec,
        model: type[_T],
    ) -> Iterator[_T]:
        conn = self._connect()
        try:
            for row in conn.execute(sql):
                yield model.model_validate(_row_to_dict(row, spec))
        finally:
            conn.close()

    # ---- Protocol properties ------------------------------------------

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

    @property
    def dictionary(self) -> Dictionary:
        return self._dictionary

    # ---- per-item lookups ---------------------------------------------

    def taxon(self, taxon_id: str) -> TaxonRow:
        result = self._row_or_none(
            "SELECT * FROM taxa WHERE taxon_id = ?",
            (taxon_id,),
            TABLES["taxa"],
            TaxonRow,
        )
        if result is None:
            raise KeyError(taxon_id)
        return result

    def source(self, source_id: str) -> SourceRow:
        result = self._row_or_none(
            "SELECT * FROM sources WHERE id = ?",
            (source_id,),
            TABLES["sources"],
            SourceRow,
        )
        if result is None:
            raise KeyError(source_id)
        return result

    def dataset(self, dataset_id: str) -> DatasetRow:
        result = self._row_or_none(
            "SELECT * FROM datasets WHERE dataset_id = ?",
            (dataset_id,),
            TABLES["datasets"],
            DatasetRow,
        )
        if result is None:
            raise KeyError(dataset_id)
        return result

    def names_index(self, query: str) -> tuple[NameIndexEntry, ...]:
        self._check_not_stale()
        normalized = normalize_name(query)
        return self._name_index.get(normalized, ())

    # ---- iterators ----------------------------------------------------

    def taxa(self) -> Iterator[TaxonRow]:
        return self._iter_models(
            "SELECT * FROM taxa ORDER BY taxon_id",
            TABLES["taxa"],
            TaxonRow,
        )

    def facts(self) -> Iterator[FactRow]:
        return self._iter_models(
            "SELECT * FROM facts ORDER BY fact_id",
            TABLES["facts"],
            FactRow,
        )

    def names(self) -> Iterator[NameRow]:
        return self._iter_models(
            "SELECT * FROM names ORDER BY taxon_id, name, language, script, kind",
            TABLES["names"],
            NameRow,
        )

    def hazards(self) -> Iterator[HazardRow]:
        return self._iter_models(
            "SELECT * FROM hazards ORDER BY taxon_id, hazard_code",
            TABLES["hazards"],
            HazardRow,
        )

    # ---- per-taxon collections ----------------------------------------

    def facts_for(self, taxon_id: str, parameter: str | None = None) -> tuple[FactRow, ...]:
        conn = self._connect()
        try:
            if parameter is None:
                cursor = conn.execute(
                    "SELECT * FROM facts WHERE taxon_id = ? ORDER BY fact_id",
                    (taxon_id,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM facts WHERE taxon_id = ? AND parameter = ? ORDER BY fact_id",
                    (taxon_id, parameter),
                )
            rows = cursor.fetchall()
            if not rows and not self._taxon_exists(conn, taxon_id):
                raise KeyError(taxon_id)
        finally:
            conn.close()
        return tuple(FactRow.model_validate(_row_to_dict(r, TABLES["facts"])) for r in rows)

    def names_for(self, taxon_id: str) -> tuple[NameRow, ...]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM names WHERE taxon_id = ? ORDER BY name, language, script, kind",
                (taxon_id,),
            )
            rows = cursor.fetchall()
            if not rows and not self._taxon_exists(conn, taxon_id):
                raise KeyError(taxon_id)
        finally:
            conn.close()
        return tuple(NameRow.model_validate(_row_to_dict(r, TABLES["names"])) for r in rows)

    def hazards_for(self, taxon_id: str) -> tuple[HazardRow, ...]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM hazards WHERE taxon_id = ? ORDER BY hazard_code",
                (taxon_id,),
            )
            rows = cursor.fetchall()
            if not rows and not self._taxon_exists(conn, taxon_id):
                raise KeyError(taxon_id)
        finally:
            conn.close()
        return tuple(HazardRow.model_validate(_row_to_dict(r, TABLES["hazards"])) for r in rows)


def _conforms_sqlite(ks: SQLiteKnowledgeSet) -> KnowledgeSet:
    """mypy structural check: SQLiteKnowledgeSet satisfies KnowledgeSet."""
    return ks
