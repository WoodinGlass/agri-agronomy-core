"""build_name_index behavior (M8-1)."""

from __future__ import annotations

import pytest

from agri_core.models.name import NameKind, NameRow
from agri_core.models.taxon import TaxonRank, TaxonRow
from agri_core.pack.name_index import NameIndexEntry, build_name_index

pytestmark = pytest.mark.contract


# ---- fixtures -------------------------------------------------------------


def _taxon(
    taxon_id: str = "T000000001",
    *,
    scientific_name: str = "Testus",
    accepted_name: str | None = None,
    rank: TaxonRank = "species",
) -> TaxonRow:
    return TaxonRow(
        taxon_id=taxon_id,
        rank=rank,
        scientific_name=scientific_name,
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
    script: str = "Latn",
    kind: NameKind = "common",
    preferred: bool = False,
) -> NameRow:
    return NameRow(
        taxon_id=taxon_id,
        name=name,
        language=language,
        script=script,
        kind=kind,
        preferred=preferred,
        src=["S001"],
    )


# ---- tests ----------------------------------------------------------------


def test_build_index_from_taxa_only() -> None:
    t = _taxon(scientific_name="Testus")
    idx = build_name_index(taxa=[t], names=[])

    assert list(idx.keys()) == ["testus"]
    entries = idx["testus"]
    assert len(entries) == 1
    e = entries[0]
    assert isinstance(e, NameIndexEntry)
    assert e.taxon_id == "T000000001"
    assert e.name == "Testus"
    assert e.normalized_name == "testus"
    assert e.language == "la"
    assert e.kind == "scientific"
    assert e.preferred is True
    assert e.matched_via == "scientific_name"
    assert e.rank == "species"
    assert e.scientific_name == "Testus"


def test_build_index_adds_accepted_name_when_distinct() -> None:
    t = _taxon(scientific_name="Testus oldname", accepted_name="Testus newname")
    idx = build_name_index(taxa=[t], names=[])

    assert set(idx.keys()) == {"testus oldname", "testus newname"}

    sci = idx["testus oldname"]
    assert len(sci) == 1
    assert sci[0].matched_via == "scientific_name"
    assert sci[0].preferred is True

    acc = idx["testus newname"]
    assert len(acc) == 1
    assert acc[0].matched_via == "accepted_name"
    assert acc[0].preferred is False
    assert acc[0].name == "Testus newname"
    assert acc[0].kind == "scientific"
    assert acc[0].language == "la"


def test_build_index_skips_accepted_name_when_identical_after_normalize() -> None:
    t = _taxon(scientific_name="Testus", accepted_name="TESTUS")
    idx = build_name_index(taxa=[t], names=[])

    assert list(idx.keys()) == ["testus"]
    entries = idx["testus"]
    assert len(entries) == 1
    assert entries[0].matched_via == "scientific_name"


def test_build_index_includes_names_rows() -> None:
    t = _taxon(scientific_name="Testus")
    n_common = _name("T000000001", "Testus", language="id", kind="common", preferred=True)
    n_sci = _name("T000000001", "Testus", language="la", kind="scientific", preferred=False)
    idx = build_name_index(taxa=[t], names=[n_common, n_sci])

    assert list(idx.keys()) == ["testus"]
    entries = idx["testus"]
    assert len(entries) == 3
    # Sorted by (taxon_id, matched_via, language, name):
    # ("names", "id") < ("names", "la") < ("scientific_name", "la")
    assert [e.matched_via for e in entries] == ["names", "names", "scientific_name"]
    assert [e.language for e in entries] == ["id", "la", "la"]
    assert entries[0].kind == "common"
    assert entries[0].preferred is True
    assert entries[1].kind == "scientific"
    assert entries[1].preferred is False


def test_build_index_normalizes_hybrid_sign() -> None:
    t = _taxon(scientific_name="Testus \u00d7 hybridus")
    n = _name("T000000001", "testus x hybridus", language="la", kind="scientific")
    idx = build_name_index(taxa=[t], names=[n])

    assert list(idx.keys()) == ["testus x hybridus"]
    entries = idx["testus x hybridus"]
    assert len(entries) == 2
    assert {e.matched_via for e in entries} == {"scientific_name", "names"}
    sci = next(e for e in entries if e.matched_via == "scientific_name")
    # display form preserved (not normalized)
    assert sci.name == "Testus \u00d7 hybridus"
    assert sci.normalized_name == "testus x hybridus"


def test_build_index_sorts_by_taxon_id() -> None:
    t1 = _taxon("T000000001", scientific_name="Testus")
    t2 = _taxon("T000000002", scientific_name="Testus")
    idx = build_name_index(taxa=[t1, t2], names=[])

    assert list(idx.keys()) == ["testus"]
    entries = idx["testus"]
    assert len(entries) == 2
    assert [e.taxon_id for e in entries] == ["T000000001", "T000000002"]


def test_build_index_ignores_names_for_unknown_taxon() -> None:
    t = _taxon("T000000001", scientific_name="Testus")
    orphan = _name("T999999999", "Ghostus", language="la", kind="scientific")
    idx = build_name_index(taxa=[t], names=[orphan])

    assert list(idx.keys()) == ["testus"]
    assert "ghostus" not in idx


def test_build_index_empty_inputs() -> None:
    assert build_name_index(taxa=[], names=[]) == {}
