"""KnowledgeSet Protocol behavior via InMemoryKnowledgeSet."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path  # noqa: F401 (used in helper type hints only)

import pytest

from agri_core.models.dataset import DatasetRow
from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow
from agri_core.models.hazard import HazardRow
from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack import InMemoryKnowledgeSet, PackManifest
from agri_core.pack.loader import _default_dictionary
from agri_core.registry.sources import SourceRow

pytestmark = pytest.mark.contract

_DICT = _default_dictionary()


# ---- fixture builders --------------------------------------------------


def _taxon(tid: str) -> TaxonRow:
    return TaxonRow(
        taxon_id=tid,
        rank="species",
        scientific_name=f"Testus {tid}",
        organism_group="plant",
        archetype="annual",
        uses=["vegetable"],
        src=["S001"],
    )


def _fact(fid: str, tid: str, parameter: str = "base_temp_c") -> FactRow:
    return FactRow(
        fact_id=fid,
        taxon_id=tid,
        parameter=parameter,
        value={"shape": "scalar", "unit": "degC", "value": 10.0},
        scope={},
        provenance_kind="curated",
        src=["S001"],
        locator="Table 1",
        evidence="B",
        status="reviewed",
        reviewed_by="reviewer-1",
        reviewed_at=date(2026, 1, 1),
    )


def _name(tid: str, name: str = "Foo", kind: str = "common") -> NameRow:
    return NameRow(
        taxon_id=tid,
        name=name,
        language="en",
        script="Latn",
        kind=kind,
        preferred=False,
        src=["S001"],
    )


def _hazard(tid: str, code: str = "toxicity_mild") -> HazardRow:
    return HazardRow(
        taxon_id=tid,
        hazard_code=code,
        severity="warning",
        reason="Test hazard",
        as_of=date(2026, 1, 1),
        authority="Test authority",
        src=["S001"],
    )


def _source(sid: str) -> SourceRow:
    return SourceRow(
        id=sid,
        url=f"https://example.org/{sid}",
        license="CC0-1.0",
        commercial_use="yes",
        access_date=date(2026, 1, 1),
        citation=f"Synthetic {sid}",
    )


def _dataset(did: str) -> DatasetRow:
    return DatasetRow(
        dataset_id=did,
        name=f"Dataset {did}",
        version="1.0",
        license="CC0-1.0",
        checksum="sha256:" + "0" * 64,
        url="https://example.org/ds",
        access_date=date(2026, 1, 1),
    )


def _make_ks(
    *,
    dictionary: Dictionary = _DICT,
    taxa=(),
    names=(),
    facts=(),
    hazards=(),
    sources=(),
    datasets=(),
    verified: bool = True,
) -> InMemoryKnowledgeSet:
    manifest = PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )
    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=dictionary.version,
        dictionary=dictionary,
        verified=verified,
        taxa=taxa,
        names=names,
        facts=facts,
        hazards=hazards,
        sources=sources,
        datasets=datasets,
    )


# ---- properties --------------------------------------------------------


def test_properties_reflect_inputs() -> None:
    ks = _make_ks(verified=False)
    assert ks.manifest.name == "test"
    assert ks.manifest.version == "1.0.0"
    assert ks.pack_hash == "sha256:" + "1" * 64
    assert ks.dictionary_version == "1.0.0"
    assert ks.verified is False


# ---- taxa --------------------------------------------------------------


def test_taxon_returns_row() -> None:
    t = _taxon("T000000001")
    ks = _make_ks(taxa=[t])
    assert ks.taxon("T000000001") is t


def test_taxon_raises_keyerror_for_unknown() -> None:
    ks = _make_ks()
    with pytest.raises(KeyError):
        ks.taxon("T999999999")


def test_taxa_iterates_sorted() -> None:
    t3 = _taxon("T000000003")
    t1 = _taxon("T000000001")
    t2 = _taxon("T000000002")
    ks = _make_ks(taxa=[t3, t1, t2])
    ids = [t.taxon_id for t in ks.taxa()]
    assert ids == ["T000000001", "T000000002", "T000000003"]


def test_taxa_empty() -> None:
    ks = _make_ks()
    assert list(ks.taxa()) == []


# ---- facts -------------------------------------------------------------


def test_facts_for_unknown_taxon_raises_keyerror() -> None:
    ks = _make_ks()
    with pytest.raises(KeyError):
        ks.facts_for("T999999999")


def test_facts_for_known_taxon_empty() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001")])
    assert ks.facts_for("T000000001") == ()


def test_facts_for_returns_all_when_no_parameter() -> None:
    t = _taxon("T000000001")
    f1 = _fact("F00000000001", "T000000001", "base_temp_c")
    f2 = _fact("F00000000002", "T000000001", "ph_min")
    ks = _make_ks(taxa=[t], facts=[f1, f2])
    got = ks.facts_for("T000000001")
    assert [f.fact_id for f in got] == ["F00000000001", "F00000000002"]


def test_facts_for_filters_by_parameter() -> None:
    t = _taxon("T000000001")
    f1 = _fact("F00000000001", "T000000001", "base_temp_c")
    f2 = _fact("F00000000002", "T000000001", "ph_min")
    ks = _make_ks(taxa=[t], facts=[f1, f2])
    got = ks.facts_for("T000000001", parameter="ph_min")
    assert [f.fact_id for f in got] == ["F00000000002"]


def test_facts_iterates_sorted() -> None:
    t = _taxon("T000000001")
    f3 = _fact("F00000000003", "T000000001")
    f1 = _fact("F00000000001", "T000000001")
    f2 = _fact("F00000000002", "T000000001")
    ks = _make_ks(taxa=[t], facts=[f3, f1, f2])
    ids = [f.fact_id for f in ks.facts()]
    assert ids == ["F00000000001", "F00000000002", "F00000000003"]


# ---- names -------------------------------------------------------------


def test_names_for_unknown_taxon_raises_keyerror() -> None:
    ks = _make_ks()
    with pytest.raises(KeyError):
        ks.names_for("T999999999")


def test_names_for_known_taxon_empty() -> None:
    ks = _make_ks(taxa=[_taxon("T000000001")])
    assert ks.names_for("T000000001") == ()


def test_names_for_returns_attached() -> None:
    t = _taxon("T000000001")
    n = _name("T000000001", "Foo", "common")
    ks = _make_ks(taxa=[t], names=[n])
    got = ks.names_for("T000000001")
    assert len(got) == 1
    assert got[0].name == "Foo"


def test_names_iterates_sorted() -> None:
    t1 = _taxon("T000000001")
    t2 = _taxon("T000000002")
    na = _name("T000000002", "Bravo")
    nb = _name("T000000001", "Alpha")
    ks = _make_ks(taxa=[t1, t2], names=[na, nb])
    keys = [(n.taxon_id, n.name) for n in ks.names()]
    assert keys == [("T000000001", "Alpha"), ("T000000002", "Bravo")]


# ---- hazards -----------------------------------------------------------


def test_hazards_for_unknown_taxon_raises_keyerror() -> None:
    ks = _make_ks()
    with pytest.raises(KeyError):
        ks.hazards_for("T999999999")


def test_hazards_iterates_sorted() -> None:
    t1 = _taxon("T000000001")
    t2 = _taxon("T000000002")
    h_b = _hazard("T000000002", "toxicity_mild")
    h_a = _hazard("T000000001", "toxicity_mild")
    ks = _make_ks(taxa=[t1, t2], hazards=[h_b, h_a])
    keys = [(h.taxon_id, h.hazard_code) for h in ks.hazards()]
    assert keys == [
        ("T000000001", "toxicity_mild"),
        ("T000000002", "toxicity_mild"),
    ]


# ---- sources / datasets ------------------------------------------------


def test_source_returns_row() -> None:
    s = _source("S001")
    ks = _make_ks(sources=[s])
    assert ks.source("S001") is s


def test_source_raises_keyerror_for_unknown() -> None:
    ks = _make_ks()
    with pytest.raises(KeyError):
        ks.source("S999")


def test_dataset_raises_keyerror_for_unknown() -> None:
    ks = _make_ks()
    with pytest.raises(KeyError):
        ks.dataset("D999999999")


# ---- validation --------------------------------------------------------


def test_from_rows_rejects_duplicate_taxon_id() -> None:
    t1 = _taxon("T000000001")
    t2 = _taxon("T000000001")
    with pytest.raises(ValueError, match="duplicate taxon_id"):
        _make_ks(taxa=[t1, t2])


# ---- invariants --------------------------------------------------------


def test_immutability() -> None:
    ks = _make_ks()
    with pytest.raises(FrozenInstanceError, match="cannot assign"):
        ks.manifest = ks.manifest  # type: ignore[misc]


def test_concurrent_reads_identical() -> None:
    t1 = _taxon("T000000001")
    t2 = _taxon("T000000002")
    f1 = _fact("F00000000001", "T000000001")
    f2 = _fact("F00000000002", "T000000002")
    ks = _make_ks(taxa=[t1, t2], facts=[f1, f2])

    def snapshot() -> tuple[list[str], list[str]]:
        return (
            [t.taxon_id for t in ks.taxa()],
            [f.fact_id for f in ks.facts()],
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: snapshot(), range(20)))

    first = results[0]
    for r in results[1:]:
        assert r == first
