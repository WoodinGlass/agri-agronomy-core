"""ADR-006/ADR-009 contract: resolve_stage returns CategoricalResult.

Inline golden values: day / gdd -> phase, from the inline annual pack
(phase_duration = 30/20/10/30, phase_thermal_time = 500/300/200/400).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from agri_core.models import CategoricalResult, OutcomeAdapter
from agri_core.pack import load_knowledge_set_from_files, read_pack_bytes
from agri_core.stages import resolve_stage

pytestmark = pytest.mark.contract


_HEADERS = {
    "taxa": (
        "taxon_id,rank,scientific_name,accepted_name,organism_group,"
        "archetype,uses,traits,parent_id,external_ids,src,dataset_id"
    ),
    "names": "taxon_id,name,language,script,kind,preferred,src,dataset_id",
    "hazards": ("taxon_id,hazard_code,severity,reason,as_of,authority,src,dataset_id"),
    "datasets": ("dataset_id,name,version,license,checksum,url,locator,access_date"),
    "sources": "id,url,license,commercial_use,access_date,citation",
    "facts": (
        "fact_id,taxon_id,parameter,phase,value,scope,provenance_kind,src,"
        "dataset_id,locator,evidence,status,reviewed_by,reviewed_at,superseded_by"
    ),
}

_CALC = r"^[a-z][a-z0-9_]*$"
_REQ = r"^req_[0-9a-f]{32}$"
_SEMVER = r"^\d+\.\d+\.\d+$"


def _write_pack(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "facts").mkdir()
    (pack / "pack.toml").write_text(
        'name = "test"\n'
        'version = "0.1.0"\n'
        "schema_version = 1\n"
        'engine_min = "0.0.0"\n'
        'dictionary_min = "1.0.0"\n'
        "synthetic = true\n"
    )
    (pack / "taxa.csv").write_text(
        _HEADERS["taxa"] + "\n"
        "T000000001,species,Testus annualis,,vascular_plant,annual,"
        "vegetable,,,,S001,\n"
    )
    (pack / "names.csv").write_text(_HEADERS["names"] + "\n")
    (pack / "hazards.csv").write_text(_HEADERS["hazards"] + "\n")
    (pack / "datasets.csv").write_text(_HEADERS["datasets"] + "\n")
    (pack / "sources.csv").write_text(
        _HEADERS["sources"] + "\nS001,https://example.org,CC0-1.0,yes,2026-01-01,Test source\n"
    )
    (pack / "ids.lock").write_text("T000000001\n")
    (pack / "facts" / "T000000001.csv").write_text(
        _HEADERS["facts"] + "\n"
        "F00000000001,T000000001,phase_duration,vegetative,"
        '"{""shape"":""scalar"",""unit"":""day"",""value"":30.0}",'
        "{},curated,S001,,loc1,A,approved,test-reviewer,2026-01-01,\n"
        "F00000000002,T000000001,phase_duration,flowering,"
        '"{""shape"":""scalar"",""unit"":""day"",""value"":20.0}",'
        "{},curated,S001,,loc1,A,approved,test-reviewer,2026-01-01,\n"
        "F00000000003,T000000001,phase_duration,fruiting,"
        '"{""shape"":""scalar"",""unit"":""day"",""value"":10.0}",'
        "{},curated,S001,,loc1,A,approved,test-reviewer,2026-01-01,\n"
        "F00000000004,T000000001,phase_duration,maturity,"
        '"{""shape"":""scalar"",""unit"":""day"",""value"":30.0}",'
        "{},curated,S001,,loc1,A,approved,test-reviewer,2026-01-01,\n"
    )
    return dict(read_pack_bytes(pack))


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("m13b2_contract")
    return load_knowledge_set_from_files(_write_pack(tmp), allow_synthetic=True)


# Golden: day offset -> phase (duration cumulative 30/50/60/90)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, "vegetative"),
        (15, "vegetative"),
        (30, "vegetative"),
        (31, "flowering"),
        (50, "flowering"),
        (51, "fruiting"),
        (60, "fruiting"),
        (61, "maturity"),
        (500, "maturity"),
    ],
)
def test_golden_annual_age(pack, days: int, expected: str) -> None:
    out = resolve_stage(
        pack,
        "T000000001",
        date(2026, 1, 1) + timedelta(days=days),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == expected, f"days {days} -> {out.category}"


# Envelope (ADR-009)


def test_envelope_subject(pack) -> None:
    out = resolve_stage(
        pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert re.match(_CALC, out.subject.calculation)
    assert re.match(_SEMVER, out.subject.calculation_version)
    assert out.subject.taxon_id == "T000000001"
    assert out.request_id is not None
    assert re.match(_REQ, out.request_id)


def test_envelope_json_roundtrip(pack) -> None:
    out = resolve_stage(
        pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    dumped = OutcomeAdapter.dump_python(out, mode="json")
    assert dumped["status"] == "ok_category"
    assert dumped["category"] == "flowering"
