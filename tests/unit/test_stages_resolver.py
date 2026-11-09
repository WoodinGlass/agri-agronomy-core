"""resolve_stage: annual age, annual thermal, perennial events."""

from __future__ import annotations

from datetime import date

import pytest

from agri_core.models import (
    CategoricalResult,
    InsufficientInput,
    NotApplicable,
    Unknown,
)
from agri_core.pack import load_knowledge_set_from_files, read_pack_bytes
from agri_core.stages import resolve_stage

pytestmark = pytest.mark.unit


# ─── Inline pack builder ───


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


def _write_pack(
    tmp_path,
    *,
    taxon_id="T000000001",
    archetype="annual",
    facts_rows=None,
):
    """Write a minimal pack to ``tmp_path/pack`` and return the file dict."""
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
        _HEADERS["taxa"] + "\n" + f"{taxon_id},species,Testus annualis,,vascular_plant,{archetype},"
        "vegetable,,,,S001,\n"
    )
    (pack / "names.csv").write_text(_HEADERS["names"] + "\n")
    (pack / "hazards.csv").write_text(_HEADERS["hazards"] + "\n")
    (pack / "datasets.csv").write_text(_HEADERS["datasets"] + "\n")
    (pack / "sources.csv").write_text(
        _HEADERS["sources"] + "\nS001,https://example.org,CC0-1.0,yes,2026-01-01,Test source\n"
    )
    (pack / "ids.lock").write_text(f"{taxon_id}\n")

    facts_file = pack / "facts" / f"{taxon_id}.csv"
    lines = [_HEADERS["facts"]]
    if facts_rows:
        lines.extend(facts_rows)
    facts_file.write_text("\n".join(lines) + "\n")

    return dict(read_pack_bytes(pack))


def _phase_fact(fact_id, taxon_id, parameter, phase, value, unit):
    return (
        f"{fact_id},{taxon_id},{parameter},{phase},"
        f'"{{""shape"":""scalar"",""unit"":""{unit}"",""value"":{value}}}",'
        "{},curated,S001,,loc1,A,approved,test-reviewer,2026-01-01,"
    )


@pytest.fixture
def annual_age_pack(tmp_path):
    rows = [
        _phase_fact("F00000000001", "T000000001", "phase_duration", "vegetative", 30, "day"),
        _phase_fact("F00000000002", "T000000001", "phase_duration", "flowering", 20, "day"),
        _phase_fact("F00000000003", "T000000001", "phase_duration", "fruiting", 10, "day"),
        _phase_fact("F00000000004", "T000000001", "phase_duration", "maturity", 30, "day"),
    ]
    files = _write_pack(tmp_path, facts_rows=rows)
    return load_knowledge_set_from_files(files, allow_synthetic=True)


@pytest.fixture
def annual_thermal_pack(tmp_path):
    rows = [
        _phase_fact(
            "F00000000011", "T000000001", "phase_thermal_time", "vegetative", 500, "degree_day"
        ),
        _phase_fact(
            "F00000000012", "T000000001", "phase_thermal_time", "flowering", 300, "degree_day"
        ),
        _phase_fact(
            "F00000000013", "T000000001", "phase_thermal_time", "fruiting", 200, "degree_day"
        ),
        _phase_fact(
            "F00000000014", "T000000001", "phase_thermal_time", "maturity", 400, "degree_day"
        ),
    ]
    files = _write_pack(tmp_path, facts_rows=rows)
    return load_knowledge_set_from_files(files, allow_synthetic=True)


# ─── annual age ───


def test_age_day_0_is_vegetative(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 1, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "vegetative"
    assert out.method == "age"


def test_age_day_15_vegetative(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 1, 16),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "vegetative"


def test_age_day_30_still_vegetative(annual_age_pack) -> None:
    # cumulative = 30, elapsed = 30, 30 > 30 is False -> vegetative stays
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 1, 31),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "vegetative"


def test_age_day_31_flowering(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "flowering"


def test_age_day_60_fruiting(annual_age_pack) -> None:
    # cumulative after fruiting = 60, elapsed = 60 -> NOT > 60, stays fruiting
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 3, 2),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "fruiting"


def test_age_day_61_maturity(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 3, 3),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "maturity"


def test_age_day_500_stays_maturity(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2027, 1, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "maturity"


def test_age_planting_after_as_of_refused(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 1, 1),
        planting_date=date(2026, 2, 1),
    )
    assert isinstance(out, InsufficientInput)
    assert any("planting_date_after" in m for m in out.missing)


# ─── annual thermal ───


def test_thermal_gdd_0_vegetative(annual_thermal_pack) -> None:
    out = resolve_stage(
        annual_thermal_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        gdd_cumulative=0.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "vegetative"
    assert out.method == "thermal_time"


def test_thermal_gdd_500_vegetative(annual_thermal_pack) -> None:
    out = resolve_stage(
        annual_thermal_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        gdd_cumulative=500.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "vegetative"


def test_thermal_gdd_501_flowering(annual_thermal_pack) -> None:
    out = resolve_stage(
        annual_thermal_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        gdd_cumulative=501.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "flowering"


def test_thermal_gdd_1400_maturity(annual_thermal_pack) -> None:
    # 500+300+200+400 = 1400; cumulative=1400, target=1400 -> NOT > 1400
    out = resolve_stage(
        annual_thermal_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        gdd_cumulative=1400.0,
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "maturity"


def test_thermal_negative_gdd_refused(annual_thermal_pack) -> None:
    out = resolve_stage(
        annual_thermal_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        gdd_cumulative=-1.0,
    )
    assert isinstance(out, InsufficientInput)
    assert any("gdd_cumulative_negative" in m for m in out.missing)


# ─── perennial events ───


@pytest.fixture
def perennial_pack(tmp_path):
    files = _write_pack(tmp_path, archetype="woody_perennial")
    return load_knowledge_set_from_files(files, allow_synthetic=True)


def test_events_establishment(perennial_pack) -> None:
    out = resolve_stage(
        perennial_pack,
        "T000000001",
        date(2026, 3, 1),
        events={
            "establishment": date(2026, 1, 15),
            "juvenile": date(2027, 1, 15),
        },
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "establishment"
    assert out.method == "events"


def test_events_latest(perennial_pack) -> None:
    out = resolve_stage(
        perennial_pack,
        "T000000001",
        date(2027, 6, 1),
        events={
            "establishment": date(2026, 1, 15),
            "juvenile": date(2027, 1, 15),
        },
    )
    assert isinstance(out, CategoricalResult)
    assert out.category == "juvenile"


def test_events_none_before_as_of_refused(perennial_pack) -> None:
    out = resolve_stage(
        perennial_pack,
        "T000000001",
        date(2025, 1, 1),
        events={"establishment": date(2026, 1, 15)},
    )
    assert isinstance(out, InsufficientInput)
    assert any("no_phase_event_before" in m for m in out.missing)


def test_events_unknown_phase_refused(perennial_pack) -> None:
    out = resolve_stage(
        perennial_pack,
        "T000000001",
        date(2026, 6, 1),
        events={"not_a_phase": date(2026, 1, 15)},
    )
    assert isinstance(out, InsufficientInput)
    assert any("no_events_match" in m for m in out.missing)


# ─── General refusals ───


def test_no_args_refused(annual_age_pack) -> None:
    out = resolve_stage(annual_age_pack, "T000000001", date(2026, 3, 1))
    assert isinstance(out, InsufficientInput)
    assert "events_or_planting_date" in out.missing


def test_events_and_planting_date_both_refused(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        events={"vegetative": date(2026, 1, 15)},
    )
    assert isinstance(out, InsufficientInput)
    assert "events_or_planting_date" in out.missing


def test_ptu_refused(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
        ptu_cumulative=100.0,
    )
    assert isinstance(out, NotApplicable)
    assert "photothermal" in out.reason.lower()


def test_unknown_taxon_refused(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T999999999",
        date(2026, 3, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, Unknown)


# ─── Envelope ───


def test_envelope_fields(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert out.subject.taxon_id == "T000000001"
    assert out.subject.calculation == "resolve_stage"
    assert out.request_id is not None
    assert out.request_id.startswith("req_")


def test_request_id_deterministic(annual_age_pack) -> None:
    a = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    b = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(a, CategoricalResult)
    assert isinstance(b, CategoricalResult)
    assert a.request_id == b.request_id


def test_label_pretty(annual_age_pack) -> None:
    out = resolve_stage(
        annual_age_pack,
        "T000000001",
        date(2026, 2, 1),
        planting_date=date(2026, 1, 1),
    )
    assert isinstance(out, CategoricalResult)
    assert out.label == "Flowering"
