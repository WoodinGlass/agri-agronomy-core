"""resolve_fact behavior (M8-3b)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow, ScalarValue
from agri_core.models.refusals import InsufficientInput, NotApplicable, Unknown
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.registry import FactResolved, resolve_fact
from agri_core.registry.sources import SourceRow

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")
_PACK_HASH = "sha256:" + "0" * 64
_TODAY = date(2026, 1, 1)


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
    taxon_id: str = "T000000001",
    *,
    organism_group: str = "vascular_plant",
    archetype: str = "annual",
    uses: tuple[str, ...] = ("vegetable",),
) -> TaxonRow:
    return TaxonRow(
        taxon_id=taxon_id,
        rank="species",
        scientific_name=f"Test {taxon_id}",
        organism_group=organism_group,
        archetype=archetype,
        uses=list(uses),
        traits=[],
        src=["S001"],
    )


def _source(sid: str = "S001", *, commercial_use: str = "yes") -> SourceRow:
    return SourceRow(
        id=sid,
        url=f"https://example.org/{sid}",
        license="CC0-1.0" if commercial_use == "yes" else "CC-BY-NC-4.0",
        commercial_use=commercial_use,  # type: ignore[arg-type]
        access_date=_TODAY,
        citation=f"Source {sid}",
    )


def _fact(
    fid: str,
    *,
    parameter: str = "soil_ph",
    value: float = 6.5,
    scope: dict | None = None,
    status: str = "approved",
    phase: str | None = None,
    superseded_by: str | None = None,
    src: tuple[str, ...] = ("S001",),
) -> FactRow:
    reviewed = status in ("reviewed", "approved")
    return FactRow(
        fact_id=fid,
        taxon_id="T000000001",
        parameter=parameter,
        phase=phase,
        value=ScalarValue(shape="scalar", unit="pH", value=value),
        scope=scope or {},
        provenance_kind="curated",
        src=list(src),
        locator="L",
        evidence="A",
        status=status,  # type: ignore[arg-type]
        reviewed_by=["r"] if reviewed else None,
        reviewed_at=_TODAY if reviewed else None,
        superseded_by=superseded_by,  # type: ignore[arg-type]
    )


def _ks(
    *,
    taxa: list[TaxonRow] | None = None,
    facts: list[FactRow] | None = None,
    sources: list[SourceRow] | None = None,
) -> InMemoryKnowledgeSet:
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash=_PACK_HASH,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa or [_taxon()],
        facts=facts or [],
        sources=sources or [_source()],
    )


# ---- scope matching (A union B) ------------------------------------------


def test_scope_empty_matches_empty() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={})
    assert isinstance(r, FactResolved)


def test_scope_fact_subset_of_request() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={"system": "field"})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={"system": "field", "country": "ID"})
    assert isinstance(r, FactResolved)


def test_scope_fact_superset_of_request() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={"system": "field", "country": "ID"})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={"system": "field"})
    assert isinstance(r, FactResolved)


def test_scope_partial_overlap_rejected() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={"system": "field", "elevation_m": [0, 500]})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={"system": "field", "country": "ID"})
    assert isinstance(r, Unknown)
    assert r.code == "no_match"


def test_scope_value_mismatch() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={"system": "field"})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={"system": "container"})
    assert isinstance(r, Unknown)
    assert r.code == "no_match"


def test_scope_range_covers() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={"elevation_m": [0, 500]})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={"elevation_m": [100, 300]})
    assert isinstance(r, FactResolved)


def test_scope_range_not_covered() -> None:
    ks = _ks(facts=[_fact("F00000000001", scope={"elevation_m": [0, 500]})])
    r = resolve_fact(ks, "T000000001", "soil_ph", scope={"elevation_m": [400, 600]})
    assert isinstance(r, Unknown)


# ---- status filtering -----------------------------------------------------


def test_status_default_approved_excludes_reviewed() -> None:
    ks = _ks(
        facts=[
            _fact("F00000000001", value=6.5, status="reviewed"),
            _fact("F00000000002", value=7.0, status="approved"),
        ]
    )
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)
    assert r.fact.fact_id == "F00000000002"


def test_min_status_reviewed_includes_reviewed() -> None:
    ks = _ks(facts=[_fact("F00000000001", value=6.5, status="reviewed")])
    r = resolve_fact(ks, "T000000001", "soil_ph", min_status="reviewed")
    assert isinstance(r, FactResolved)


# ---- safety floor ---------------------------------------------------------


def test_safety_floor_raised() -> None:
    # n_max_per_application is safety_class="dose_cap"
    ks = _ks(
        facts=[_fact("F00000000001", parameter="n_max_per_application", status="reviewed")],
    )
    r = resolve_fact(ks, "T000000001", "n_max_per_application", min_status=None)
    assert isinstance(r, FactResolved)
    assert any(w.code == "safety_min_status_raised" for w in r.warnings)


# ---- superseded -----------------------------------------------------------


def test_superseded_excluded() -> None:
    ks = _ks(
        facts=[
            _fact("F00000000001", value=6.5, superseded_by="F00000000002"),
            _fact("F00000000002", value=7.0),
        ]
    )
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)
    assert r.fact.fact_id == "F00000000002"


def test_alternatives_populated() -> None:
    ks = _ks(
        facts=[
            _fact("F00000000001", value=7.0),
            _fact("F00000000002", value=6.5),
        ]
    )
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)
    assert len(r.alternatives) == 1
    assert r.alternatives[0].fact_id == "F00000000002"


# ---- fact conflict / corroboration ----------------------------------------


def test_fact_conflict_warning() -> None:
    ks = _ks(
        facts=[
            _fact("F00000000001", value=6.5),
            _fact("F00000000002", value=7.0),
        ]
    )
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)
    assert any(w.code == "fact_conflict" for w in r.warnings)


def test_corroboration_no_warning() -> None:
    ks = _ks(
        facts=[
            _fact("F00000000001", value=6.5, src=("S001",)),
            _fact("F00000000002", value=6.5, src=("S002",)),
        ],
        sources=[_source("S001"), _source("S002")],
    )
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)
    assert not any(w.code == "fact_conflict" for w in r.warnings)


def test_single_fact_no_warning() -> None:
    ks = _ks(facts=[_fact("F00000000001", value=6.5)])
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)
    assert r.alternatives == []
    assert not any(w.code == "fact_conflict" for w in r.warnings)


# ---- phase ----------------------------------------------------------------


def test_phase_none_phased_param_insufficient() -> None:
    ks = _ks()
    r = resolve_fact(ks, "T000000001", "phase_duration", phase=None)
    assert isinstance(r, InsufficientInput)
    assert r.missing == ["phase"]


def test_phase_valid() -> None:
    ks = _ks(
        facts=[_fact("F00000000001", parameter="phase_duration", phase="vegetative")],
    )
    r = resolve_fact(ks, "T000000001", "phase_duration", phase="vegetative")
    assert isinstance(r, FactResolved)


def test_phase_invalid_insufficient() -> None:
    ks = _ks()
    r = resolve_fact(ks, "T000000001", "phase_duration", phase="dormancy")
    assert isinstance(r, InsufficientInput)
    assert r.missing == ["phase"]


def test_phase_none_unphased_param_ok() -> None:
    ks = _ks(facts=[_fact("F00000000001", parameter="soil_ph")])
    r = resolve_fact(ks, "T000000001", "soil_ph", phase=None)
    assert isinstance(r, FactResolved)


# ---- license gate ---------------------------------------------------------


def test_license_gate_excludes_nc() -> None:
    ks = _ks(
        facts=[_fact("F00000000001", src=("S001",))],
        sources=[_source("S001", commercial_use="no")],
    )
    r = resolve_fact(ks, "T000000001", "soil_ph", require_commercial=True)
    assert isinstance(r, Unknown)
    assert r.code == "license_excluded"


def test_license_gate_cc0_passes() -> None:
    ks = _ks(
        facts=[_fact("F00000000001", src=("S001",))],
        sources=[_source("S001", commercial_use="yes")],
    )
    r = resolve_fact(ks, "T000000001", "soil_ph", require_commercial=True)
    assert isinstance(r, FactResolved)


def test_license_gate_default_off() -> None:
    ks = _ks(
        facts=[_fact("F00000000001", src=("S001",))],
        sources=[_source("S001", commercial_use="no")],
    )
    r = resolve_fact(ks, "T000000001", "soil_ph")
    assert isinstance(r, FactResolved)


# ---- applies_to mismatch (NotApplicable) --------------------------------


def test_applies_to_mismatch_returns_not_applicable() -> None:
    # `kc` applies only to organism_group=vascular_plant (per dictionary);
    # a fungal taxon must yield NotApplicable, not Unknown.
    fungal = _taxon("T000000009", organism_group="fungus", archetype="fungal")
    ks = _ks(taxa=[fungal], facts=[], sources=[_source()])
    r = resolve_fact(ks, "T000000009", "kc")
    assert isinstance(r, NotApplicable)
