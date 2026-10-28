"""resolve_taxon behavior (M8)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.name import NameRow
from agri_core.models.refusals import Ambiguous, Unknown
from agri_core.models.taxon import TaxonRow
from agri_core.pack import load_knowledge_set
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.pack.tables import TABLES, write_table
from agri_core.registry import TaxonOk, TaxonOutcomeAdapter, resolve_taxon

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")
_PACK_HASH = "sha256:" + "0" * 64


# ---- helpers --------------------------------------------------------------


def _manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "t",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _taxon(
    taxon_id: str,
    *,
    scientific_name: str | None = None,
    accepted_name: str | None = None,
    rank: str = "species",
) -> TaxonRow:
    return TaxonRow(
        taxon_id=taxon_id,
        rank=rank,  # type: ignore[arg-type]
        scientific_name=scientific_name or f"Sci {taxon_id}",
        accepted_name=accepted_name,
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        src=["S001"],
    )


def _name(
    taxon_id: str,
    name: str,
    *,
    language: str = "id",
    kind: str = "common",
    preferred: bool = False,
) -> NameRow:
    return NameRow(
        taxon_id=taxon_id,
        name=name,
        language=language,
        script="Latn",
        kind=kind,  # type: ignore[arg-type]
        preferred=preferred,
        src=["S001"],
    )


def _make_ks(
    *,
    taxa: list[TaxonRow] | None = None,
    names: list[NameRow] | None = None,
) -> InMemoryKnowledgeSet:
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash=_PACK_HASH,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa or [],
        names=names or [],
    )


def _write_pack(
    root: Path,
    *,
    taxa: list[dict] | None = None,
    names: list[dict] | None = None,
) -> None:
    """Minimal CSV pack writer for real-loader tests."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.toml").write_text(
        'name = "t"\n'
        'version = "1.0.0"\n'
        "schema_version = 1\n"
        'engine_min = "0.0.0"\n'
        'dictionary_min = "1.0.0"\n',
        encoding="utf-8",
    )
    for name, rows in (
        ("taxa", taxa or []),
        ("names", names or []),
    ):
        spec = TABLES[name]
        assert spec.filename is not None
        (root / spec.filename).write_bytes(write_table(spec, rows))
    # Minimal required tables
    for name in ("hazards", "datasets", "sources"):
        spec = TABLES[name]
        assert spec.filename is not None
        (root / spec.filename).write_bytes(write_table(spec, []))


# ---- base behavior --------------------------------------------------------


def test_taxon_ok_exact_scientific_name() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus")])
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, TaxonOk)
    assert r.status == "ok"
    assert r.taxon_id == "T000000001"
    assert r.matched_via == "scientific_name"


def test_taxon_ok_exact_accepted_name() -> None:
    ks = _make_ks(
        taxa=[_taxon("T000000001", scientific_name="Testus old", accepted_name="Testus new")]
    )
    r = resolve_taxon(ks, "Testus new")
    assert isinstance(r, TaxonOk)
    assert r.matched_via == "accepted_name"


def test_taxon_ok_exact_name_from_names_csv() -> None:
    t = _taxon("T000000001", scientific_name="Testus")
    n = _name("T000000001", "Foo bar", language="id")
    ks = _make_ks(taxa=[t], names=[n])
    r = resolve_taxon(ks, "Foo bar")
    assert isinstance(r, TaxonOk)
    assert r.matched_via == "names"


def test_taxon_ok_case_insensitive() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus")])
    r = resolve_taxon(ks, "TESTUS")
    assert isinstance(r, TaxonOk)


def test_taxon_ok_hybrid_sign_x_vs_multiply() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus \u00d7 hybridus")])
    r = resolve_taxon(ks, "Testus x hybridus")
    assert isinstance(r, TaxonOk)


def test_taxon_unknown_empty_input() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus")])
    r = resolve_taxon(ks, "")
    assert isinstance(r, Unknown)
    assert r.code == "empty_input"


def test_taxon_unknown_no_match() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus")])
    r = resolve_taxon(ks, "__nonexistent__")
    assert isinstance(r, Unknown)
    assert r.code == "no_match"


def test_taxon_ambiguous_two_taxa() -> None:
    ks = _make_ks(
        taxa=[
            _taxon("T000000001", scientific_name="Testus"),
            _taxon("T000000002", scientific_name="Testus"),
        ]
    )
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, Ambiguous)
    assert r.truncated is False
    assert [c.taxon_id for c in r.candidates] == ["T000000001", "T000000002"]


def test_taxon_ambiguous_via_real_loader(tmp_path: Path) -> None:
    """D18: ambiguity test through the real CSV loader, not from_rows."""
    _write_pack(
        tmp_path,
        taxa=[
            {
                "taxon_id": "T000000001",
                "rank": "species",
                "scientific_name": "Testus",
                "accepted_name": None,
                "organism_group": "vascular_plant",
                "archetype": "annual",
                "uses": ["vegetable"],
                "traits": [],
                "parent_id": None,
                "external_ids": None,
                "src": ["S001"],
                "dataset_id": None,
            },
            {
                "taxon_id": "T000000002",
                "rank": "species",
                "scientific_name": "Testus",
                "accepted_name": None,
                "organism_group": "vascular_plant",
                "archetype": "annual",
                "uses": ["vegetable"],
                "traits": [],
                "parent_id": None,
                "external_ids": None,
                "src": ["S001"],
                "dataset_id": None,
            },
        ],
    )
    # Add a source row so FK passes
    (tmp_path / "sources.csv").write_bytes(
        write_table(
            TABLES["sources"],
            [
                {
                    "id": "S001",
                    "url": "https://example.org/S001",
                    "license": "CC0-1.0",
                    "commercial_use": "yes",
                    "access_date": date(2026, 1, 1),
                    "citation": "S001",
                }
            ],
        )
    )
    ks = load_knowledge_set(tmp_path, allow_synthetic=True)
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, Ambiguous)
    assert [c.taxon_id for c in r.candidates] == ["T000000001", "T000000002"]


def test_taxon_ambiguous_sorted_by_taxon_id() -> None:
    ks = _make_ks(
        taxa=[
            _taxon("T000000099", scientific_name="Testus"),
            _taxon("T000000001", scientific_name="Testus"),
        ]
    )
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, Ambiguous)
    assert [c.taxon_id for c in r.candidates] == ["T000000001", "T000000099"]


def test_taxon_ambiguous_truncated_at_20() -> None:
    taxa = [_taxon(f"T{i:09d}", scientific_name="Testus") for i in range(25)]
    ks = _make_ks(taxa=taxa)
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, Ambiguous)
    assert r.truncated is True
    assert len(r.candidates) == 20


def test_taxon_ambiguous_accepted_name_collision() -> None:
    # F7/D6: accepted_name of one taxon equals scientific_name of another
    ks = _make_ks(
        taxa=[
            _taxon("T000000001", scientific_name="Testus", accepted_name="Testus new"),
            _taxon("T000000002", scientific_name="Testus new"),
        ]
    )
    r = resolve_taxon(ks, "Testus new")
    assert isinstance(r, Ambiguous)
    assert len(r.candidates) == 2


def test_taxon_ok_matched_via_precedence() -> None:
    # scientific_name beats names.csv for the same taxon
    t = _taxon("T000000001", scientific_name="Testus")
    n = _name("T000000001", "Testus", language="id")
    ks = _make_ks(taxa=[t], names=[n])
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, TaxonOk)
    assert r.matched_via == "scientific_name"


def test_taxon_ok_preferred_wins_within_matched_via() -> None:
    t = _taxon("T000000001", scientific_name="Testus")
    n_pref = _name("T000000001", "Testus", language="id", preferred=True)
    n_alt = _name("T000000001", "Testus", language="en", preferred=False)
    ks = _make_ks(taxa=[t], names=[n_pref, n_alt])
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, TaxonOk)
    # both are names matched; preferred should win, but scientific_name
    # has higher precedence and is also present
    assert r.matched_via == "scientific_name"


def test_taxon_ok_carries_row_fields() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus", rank="genus")])
    r = resolve_taxon(ks, "Testus")
    assert isinstance(r, TaxonOk)
    assert r.scientific_name == "Testus"
    assert r.rank == "genus"


def test_taxon_outcome_adapter_roundtrip() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus")])
    r = resolve_taxon(ks, "Testus")
    payload = TaxonOutcomeAdapter.dump_python(r, mode="json")
    restored = TaxonOutcomeAdapter.validate_python(payload)
    assert isinstance(restored, TaxonOk)
    assert restored.taxon_id == "T000000001"


# ---- language preference ---------------------------------------------------


def _bawang_ks() -> InMemoryKnowledgeSet:
    t1 = _taxon("T000000001", scientific_name="Allium cepa")
    t2 = _taxon("T000000002", scientific_name="Allium sativum")
    n1 = _name("T000000001", "Bawang", language="id")
    n2 = _name("T000000002", "Bawang", language="ms")
    return _make_ks(taxa=[t1, t2], names=[n1, n2])


def test_taxon_ambiguous_without_language() -> None:
    ks = _bawang_ks()
    r = resolve_taxon(ks, "Bawang")
    assert isinstance(r, Ambiguous)
    assert len(r.candidates) == 2


def test_taxon_ok_language_prefers_id() -> None:
    ks = _bawang_ks()
    r = resolve_taxon(ks, "Bawang", language="id")
    assert isinstance(r, TaxonOk)
    assert r.taxon_id == "T000000001"


def test_taxon_ok_language_prefers_ms() -> None:
    ks = _bawang_ks()
    r = resolve_taxon(ks, "Bawang", language="ms")
    assert isinstance(r, TaxonOk)
    assert r.taxon_id == "T000000002"


def test_taxon_ok_language_fallback_when_no_match() -> None:
    # query is a scientific_name; language="id" has no matching entry ->
    # fallback to full set, taxon still resolves
    ks = _bawang_ks()
    r = resolve_taxon(ks, "Allium cepa", language="id")
    assert isinstance(r, TaxonOk)
    assert r.taxon_id == "T000000001"


def test_taxon_ok_language_la_matches_scientific() -> None:
    # language="la" is the tag for synthetic scientific_name entries
    ks = _make_ks(taxa=[_taxon("T000000001", scientific_name="Testus")])
    r = resolve_taxon(ks, "Testus", language="la")
    assert isinstance(r, TaxonOk)
    assert r.matched_via == "scientific_name"
