"""names_index() behavior across backends (M8-1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack import InMemoryKnowledgeSet, PackManifest, load_knowledge_set, read_pack_bytes
from agri_core.pack.name_index import NameIndexEntry
from agri_core.pack.sqlite_schema import write_built_pack

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")


# ---- helpers ---------------------------------------------------------------


def _taxon(
    taxon_id: str,
    *,
    scientific_name: str,
    accepted_name: str | None = None,
) -> TaxonRow:
    return TaxonRow(
        taxon_id=taxon_id,
        rank="species",
        scientific_name=scientific_name,
        accepted_name=accepted_name,
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        src=["S001"],
    )


def _make_manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "t",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _make_inmemory(
    *,
    taxa: list[TaxonRow] | None = None,
    names: list[NameRow] | None = None,
) -> InMemoryKnowledgeSet:
    return InMemoryKnowledgeSet.from_rows(
        manifest=_make_manifest(),
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa or [],
        names=names or [],
    )


def _build_sample(tmp_path: Path) -> Path:
    files = read_pack_bytes(_SRC)
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    return out


# ---- InMemory: direct from_rows tests -------------------------------------


def test_inmemory_names_index_exact_match() -> None:
    t = _taxon("T000000001", scientific_name="Testus")
    ks = _make_inmemory(taxa=[t])
    hits = ks.names_index("Testus")
    assert len(hits) == 1
    assert isinstance(hits[0], NameIndexEntry)
    assert hits[0].taxon_id == "T000000001"
    assert hits[0].matched_via == "scientific_name"


def test_inmemory_names_index_case_insensitive() -> None:
    t = _taxon("T000000001", scientific_name="Testus")
    ks = _make_inmemory(taxa=[t])
    for q in ("TESTUS", "testus", "TeStUs"):
        hits = ks.names_index(q)
        assert len(hits) == 1
        assert hits[0].taxon_id == "T000000001"


def test_inmemory_names_index_returns_empty_for_unknown() -> None:
    t = _taxon("T000000001", scientific_name="Testus")
    ks = _make_inmemory(taxa=[t])
    assert ks.names_index("__nonexistent__") == ()
    assert ks.names_index("Otherus") == ()


def test_inmemory_names_index_hybrid_sign_normalized() -> None:
    t = _taxon("T000000001", scientific_name="Testus \u00d7 hybridus")
    ks = _make_inmemory(taxa=[t])
    # Query with ASCII x should match the multiplication sign name
    hits = ks.names_index("Testus x hybridus")
    assert len(hits) == 1
    assert hits[0].taxon_id == "T000000001"
    assert hits[0].matched_via == "scientific_name"


def test_inmemory_names_index_multiple_matches_sorted() -> None:
    t1 = _taxon("T000000002", scientific_name="Testus")
    t2 = _taxon("T000000001", scientific_name="Testus")
    ks = _make_inmemory(taxa=[t1, t2])  # reverse input order
    hits = ks.names_index("Testus")
    assert len(hits) == 2
    assert [h.taxon_id for h in hits] == ["T000000001", "T000000002"]


# ---- via real loader (source) ---------------------------------------------


def test_loader_source_pack_names_index() -> None:
    ks = load_knowledge_set(_SRC, allow_synthetic=True)
    taxa = list(ks.taxa())
    assert len(taxa) >= 1
    first = taxa[0]
    hits = ks.names_index(first.scientific_name)
    assert len(hits) >= 1
    assert any(h.taxon_id == first.taxon_id for h in hits)


# ---- via real loader (built) ----------------------------------------------


def test_loader_built_pack_names_index(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    taxa = list(ks.taxa())
    assert len(taxa) >= 1
    first = taxa[0]
    hits = ks.names_index(first.scientific_name)
    assert len(hits) >= 1
    assert any(h.taxon_id == first.taxon_id for h in hits)


# ---- cross-backend parity -------------------------------------------------


def test_names_index_backend_parity(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    src = load_knowledge_set(_SRC, allow_synthetic=True)
    ks = load_knowledge_set(built, allow_synthetic=True)
    taxa = list(src.taxa())
    assert len(taxa) >= 1
    q = taxa[0].scientific_name
    src_hits = src.names_index(q)
    built_hits = ks.names_index(q)
    assert len(src_hits) >= 1
    assert {h.taxon_id for h in src_hits} == {h.taxon_id for h in built_hits}
    assert {h.matched_via for h in src_hits} == {h.matched_via for h in built_hits}
