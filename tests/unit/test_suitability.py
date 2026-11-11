"""site_suitability: unit coverage (M15, ADR-016)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from agri_core.models import (
    CategoricalResult,
    FactRow,
    HazardRow,
    InsufficientInput,
    NotApplicable,
    ReferToAuthority,
    ScalarValue,
    TaxonRow,
    TrapezoidValue,
    Unknown,
)
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.suitability import Site, batch_suitability, site_suitability

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

_SITE_PARAMS = ("soil_ph", "soil_ec", "air_temp_day", "air_temp_night", "air_rh", "vpd", "dli")
_PHASE_BEARING = {"air_temp_day", "air_temp_night", "air_rh", "vpd", "dli"}

_PTS_OPT = (4.5, 6.0, 7.0, 8.5)  # value 6.5 = optimal, 5.0 = suboptimal, 4.4 = critical

_FID_COUNTER = [0]


def _next_fid() -> str:
    _FID_COUNTER[0] += 1
    return f"F{_FID_COUNTER[0]:011d}"


def _manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _taxon(tid: str = "T000000001") -> TaxonRow:
    return TaxonRow(
        taxon_id=tid,
        rank="species",
        scientific_name=f"Testus {tid}",
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        src=["S001"],
    )


def _fact(fid: str, param: str, *, value, phase=None, scope=None) -> FactRow:
    return FactRow(
        fact_id=fid,
        taxon_id="T000000001",
        parameter=param,
        phase=phase,
        value=value,
        scope=scope or {},
        provenance_kind="curated",
        src=["S001"],
        locator="test",
        evidence="B",
        status="approved",
        reviewed_by="tester",
        reviewed_at=date(2026, 1, 1),
    )


def _trap(param: str) -> FactRow:
    phase = "flowering" if param in _PHASE_BEARING else None
    return _fact(
        _next_fid(),
        param,
        value=TrapezoidValue(shape="trapezoid", unit="x", pts=_PTS_OPT),
        phase=phase,
    )


def _weight(param: str, w: float = 1.0) -> FactRow:
    return _fact(
        _next_fid(),
        f"suitability_weight_{param}",
        value=ScalarValue(shape="scalar", unit="dimensionless", value=w),
    )


def _pack(*, hazards=(), weights=True) -> InMemoryKnowledgeSet:
    facts = [_trap(p) for p in _SITE_PARAMS]
    if weights:
        facts += [_weight(p) for p in _SITE_PARAMS]
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=[_taxon()],
        facts=facts,
        hazards=list(hazards),
    )


def _site(**overrides) -> Site:
    # default: all optimal (6.5 inside 6.0..7.0)
    base = {p: 6.5 for p in _SITE_PARAMS}
    base.update(overrides)
    return Site(**base)


def _hazard(sev: str, code: str = "test_hazard") -> HazardRow:
    return HazardRow(
        taxon_id="T000000001",
        hazard_code=code,
        severity=sev,
        reason="test",
        as_of=date(2026, 1, 1),
        authority="authority",
        src=["S001"],
    )


# ---- Site model ----


def test_site_model_all_none_default() -> None:
    s = Site()
    assert all(getattr(s, p) is None for p in _SITE_PARAMS)


def test_site_model_extra_forbidden() -> None:
    with pytest.raises(ValidationError, match="extra"):
        Site(unknown_field=1.0)


def test_site_model_frozen() -> None:
    s = _site()
    with pytest.raises(ValidationError):
        s.soil_ph = 5.0  # type: ignore[misc]


# ---- Refusals ----


def test_missing_site_value_insufficient_input() -> None:
    out = site_suitability(_pack(), "T000000001", Site(), phase="flowering")
    assert isinstance(out, InsufficientInput)
    assert set(out.missing) == set(_SITE_PARAMS)


def test_partial_site_insufficient_input() -> None:
    out = site_suitability(_pack(), "T000000001", Site(soil_ph=6.5), phase="flowering")
    assert isinstance(out, InsufficientInput)
    assert "soil_ph" not in out.missing
    assert set(out.missing) == set(_SITE_PARAMS) - {"soil_ph"}


def test_phase_none_with_phase_bearing_params_insufficient_input() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase=None)
    assert isinstance(out, InsufficientInput)
    assert out.missing == ["phase"]


def test_missing_fact_unknown() -> None:
    facts = [_trap(p) for p in _SITE_PARAMS if p != "vpd"]
    pack = InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=[_taxon()],
        facts=facts,
    )
    out = site_suitability(pack, "T000000001", _site(), phase="flowering")
    assert isinstance(out, Unknown)


def test_not_applicable_applies_to_mismatch() -> None:
    """vpd/dli applies_to only vascular_plant; fungal -> NotApplicable."""
    fungal = TaxonRow(
        taxon_id="T000000001",
        rank="species",
        scientific_name="F",
        organism_group="fungus",
        archetype="fungal",
        uses=["edible_fungus"],
        traits=[],
        src=["S001"],
    )
    fungal_site_params = [
        "soil_ph",
        "soil_ec",
        "air_temp_day",
        "air_temp_night",
        "air_rh",
    ]
    facts = []
    for p in fungal_site_params:
        ph = "fruiting" if p in _PHASE_BEARING else None
        facts.append(
            _fact(
                _next_fid(),
                p,
                value=TrapezoidValue(shape="trapezoid", unit="x", pts=_PTS_OPT),
                phase=ph,
            )
        )
    pack = InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=[fungal],
        facts=facts,
    )
    out = site_suitability(pack, "T000000001", _site(), phase="fruiting")
    assert isinstance(out, NotApplicable)
    assert "vpd" in out.reason or "dli" in out.reason


def test_all_optimal_suitable() -> None:
    out = site_suitability(_pack(), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "suitable"
    assert out.method == "suitability_v1"


def test_one_suboptimal_marginal() -> None:
    out = site_suitability(_pack(), "T000000001", _site(soil_ph=5.0), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "marginal"


def test_one_critical_unsuitable() -> None:
    out = site_suitability(_pack(), "T000000001", _site(soil_ph=4.4), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "unsuitable"


def test_critical_overrides_suboptimal() -> None:
    out = site_suitability(_pack(), "T000000001", _site(soil_ph=4.4, vpd=5.0), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert out.category == "unsuitable"


# ---- Hazards ----


def test_hazard_info_notice() -> None:
    pack = _pack(hazards=[_hazard("info", "info_code")])
    out = site_suitability(pack, "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert any(w.code == "hazard_info_code" for w in out.warnings)


def test_hazard_warning_notice() -> None:
    pack = _pack(hazards=[_hazard("warning", "warn_code")])
    out = site_suitability(pack, "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert any(w.code == "hazard_warn_code" for w in out.warnings)


def test_hazard_critical_refer_to_authority() -> None:
    pack = _pack(hazards=[_hazard("critical", "crit_code")])
    out = site_suitability(pack, "T000000001", _site(), phase="flowering")
    assert isinstance(out, ReferToAuthority)
    assert out.flags == ["CRIT_CODE"]


# ---- Weighted score ----


def test_weighted_score_notice() -> None:
    out = site_suitability(_pack(weights=True), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert any(w.code == "suitability_score" for w in out.warnings)


def test_no_weights_no_score_notice() -> None:
    out = site_suitability(_pack(weights=False), "T000000001", _site(), phase="flowering")
    assert isinstance(out, CategoricalResult)
    assert not any(w.code == "suitability_score" for w in out.warnings)


# ---- Batch ----


def test_batch_input_order_preserved() -> None:
    pack = _pack()
    ids = ["T000000001"]  # only one taxon available
    out = batch_suitability(pack, _site(), ids, phase="flowering")
    assert len(out) == len(ids)
    assert isinstance(out[0], CategoricalResult)
