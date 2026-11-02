"""Protection-domain scope guard (ADR-007) -- table-driven tests."""

from __future__ import annotations

import pytest

from agri_core.models.parameter import ParameterDef
from agri_core.pack import validate_pack_report
from agri_core.pack.loader import _default_dictionary
from agri_core.pack.protection import (
    ALLOWED_UNITS,
    find_hazard_code_violations,
    find_protection_violations,
    is_protection_domain,
)

pytestmark = pytest.mark.contract

_CORE_DICT = _default_dictionary()


def _base_param() -> ParameterDef:
    for p in sorted(_CORE_DICT.parameters.values(), key=lambda x: x.key):
        if p.shape == "scalar" and p.unit == "percent":
            return p
    return next(p for p in _CORE_DICT.parameters.values() if p.shape == "scalar")


_BASE = _base_param()


def _mk(**overrides: object) -> ParameterDef:
    return _BASE.model_copy(update=overrides)


def _dict(*params: ParameterDef) -> dict[str, ParameterDef]:
    return {p.key: p for p in params}


@pytest.mark.parametrize(
    ("key", "stage", "expect"),
    [
        ("air_rh", "care", False),
        ("pest_risk_level", "care", True),
        ("disease_pressure", "care", True),
        ("unknown_param", "protection", True),
        ("frost_protection_days", "care", False),
        ("plant_protection_priority", "care", True),
    ],
)
def test_is_protection_domain(key: str, stage: str, expect: bool) -> None:
    assert is_protection_domain(_mk(key=key, stage=stage)) is expect


@pytest.mark.parametrize(
    "key",
    [
        "fungicide_interval_days",
        "herbicide_rate",
        "pesticide_products",
        "mode_of_action",
        "tank_mix_notes",
        "active_ingredient_id",
        "trade_name",
        "adjuvant_class",
    ],
)
def test_global_tier_fires_on_care_param(key: str) -> None:
    p = _mk(
        key=key, stage="care", shape="enum", enum_values=["a", "b"], unit=None, tier_required=False
    )
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("forbidden" in r for r in fs[0].reasons)


@pytest.mark.parametrize(
    ("key", "unit"),
    [
        ("pest_concentration", "percent"),
        ("pest_treatment_interval_days", "day"),
        ("pest_spray_volume", "centimeter"),
        ("disease_pre_harvest_interval_days", "day"),
        ("pest_schedule", None),
    ],
)
def test_domain_tier_fires_on_protection_param(key: str, unit: str | None) -> None:
    kwargs: dict[str, object] = {"key": key, "unit": unit, "tier_required": False}
    if unit is None:
        kwargs.update(shape="enum", enum_values=["a"])
    p = _mk(**kwargs)
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert fs[0].reasons


@pytest.mark.parametrize(
    "key",
    [
        "pest_resistance_rating",
        "pest_product_form",
        "pest_reinfestation_risk",
    ],
)
def test_false_positive_guards(key: str) -> None:
    p = _mk(key=key, shape="enum", enum_values=["a", "b"], unit=None, tier_required=False)
    assert find_protection_violations(_dict(p)) == []


def test_fertilizer_concentration_ok() -> None:
    p = _mk(key="nutrient_concentration", stage="care", unit="percent", tier_required=False)
    assert find_protection_violations(_dict(p)) == []


def test_fertilizer_pre_harvest_notes_ok() -> None:
    p = _mk(
        key="pre_harvest_fertilizer_notes",
        stage="care",
        shape="enum",
        enum_values=["before", "after"],
        unit=None,
        tier_required=False,
    )
    assert find_protection_violations(_dict(p)) == []


@pytest.mark.parametrize(
    "unit",
    ["kilogram/hectare", "liter/hectare", "gram/liter", "ppm", "millimeter/day"],
)
def test_protection_dose_like_unit_rejected(unit: str) -> None:
    p = _mk(key="pest_application", unit=unit, tier_required=False)
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("unit" in r for r in fs[0].reasons)


def test_protection_extension_kind_rejected() -> None:
    p = _mk(
        key="pest_risk_level",
        shape="enum",
        enum_values=["low"],
        unit=None,
        kind="extension",
        tier_required=False,
    )
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("extension" in r for r in fs[0].reasons)


def test_protection_rule_shape_rejected() -> None:
    p = _mk(key="pest_diagnostic", shape="rule", unit=None, tier_required=False)
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("rule" in r for r in fs[0].reasons)


def test_protection_tier_required_rejected() -> None:
    p = _mk(key="pest_risk_level", shape="enum", enum_values=["low"], unit=None, tier_required=True)
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("tier_required" in r for r in fs[0].reasons)


def test_global_enum_value_rejected() -> None:
    p = _mk(
        key="soil_treatment",
        stage="care",
        shape="enum",
        enum_values=["fungicide_x"],
        unit=None,
        tier_required=False,
    )
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("enum value" in r for r in fs[0].reasons)


def test_domain_enum_value_rejected() -> None:
    p = _mk(
        key="pest_control_method",
        shape="enum",
        enum_values=["spray"],
        unit=None,
        tier_required=False,
    )
    fs = find_protection_violations(_dict(p))
    assert len(fs) == 1
    assert any("enum value" in r for r in fs[0].reasons)


def test_core_dictionary_has_no_protection_violations() -> None:
    assert find_protection_violations(_CORE_DICT.parameters) == []


def test_sample_pack_no_protection_findings() -> None:
    from pathlib import Path as _Path

    from agri_core.pack import read_pack_bytes

    root = _Path(__file__).resolve().parents[2]
    src = root / "src" / "agri_core" / "_samples" / "sample_pack"
    files = dict(read_pack_bytes(src))
    toml = files["pack.toml"].decode("utf-8")
    files["pack.toml"] = (
        "\n".join(ln for ln in toml.splitlines() if not ln.startswith("content_hash"))
    ).encode("utf-8") + b"\n"
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    prot = [f for f in report.findings if f.code.startswith("PACK_PROTECTION_")]
    assert prot == []


def test_allowed_units_subset_of_canonical() -> None:
    from agri_core.models.units import CANONICAL_UNITS

    assert ALLOWED_UNITS <= CANONICAL_UNITS


@pytest.mark.parametrize(
    "code",
    [
        "spray_dose_per_hectare",
        "fungicide_residue_warning",
        "mode_of_action_note",
    ],
)
def test_hazard_code_forbidden_token(code: str) -> None:
    vs = find_hazard_code_violations([code])
    assert len(vs) == 1
    assert vs[0].reasons


@pytest.mark.parametrize(
    "code",
    [
        "spore_allergy",
        "thorn_injury",
        "toxic_to_pets",
        "phototoxicity_burn",
    ],
)
def test_hazard_code_legitimate(code: str) -> None:
    assert find_hazard_code_violations([code]) == []


def test_stages_vocab_pinned() -> None:
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[2] / "dictionary" / "vocab" / "stages.yaml"
    data = yaml.safe_load(path.read_text())
    assert set(data["stages"].keys()) == {
        "care",
        "cycle",
        "harvest",
        "planting",
        "propagation",
        "seeding",
        "site_media",
    }


def test_organism_groups_vocab_pinned() -> None:
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[2] / "dictionary" / "vocab" / "organism_groups.yaml"
    data = yaml.safe_load(path.read_text())
    og = data.get("organism_groups") or data.get("values") or {}
    keys = set(og.keys()) if isinstance(og, dict) else set(og)
    assert keys == {"alga", "bryophyte", "fungus", "lichen", "vascular_plant"}


# ---------------------------------------------------------------------------
# Finding-code fixtures
# (satisfies test_finding_registry.py::test_each_rule_code_has_contract_fixture)
# ---------------------------------------------------------------------------


def test_check_protection_out_of_scope_emits_code() -> None:
    """PACK_PROTECTION_OUT_OF_SCOPE fires on a bad protection parameter."""
    from agri_core.models.dictionary import Dictionary
    from agri_core.pack.validate import check_protection_out_of_scope

    bad = _mk(
        key="pest_application_rate",
        unit="kilogram/hectare",
        tier_required=False,
    )
    d = Dictionary(
        version=_CORE_DICT.version,
        parameters={bad.key: bad},
        phases_by_archetype={},
    )
    findings = check_protection_out_of_scope(None, {}, d)  # type: ignore[arg-type]
    assert "PACK_PROTECTION_OUT_OF_SCOPE" in [f.code for f in findings]


def test_check_hazard_code_out_of_scope_emits_code() -> None:
    """PACK_HAZARD_CODE_OUT_OF_SCOPE fires on a bad hazard_code."""
    from agri_core.pack.validate import check_hazard_code_out_of_scope

    class _H:
        hazard_code = "spray_dose_per_hectare"

    class _KS:
        def hazards(self):
            yield _H()

    findings = check_hazard_code_out_of_scope(_KS(), {}, _CORE_DICT)  # type: ignore[arg-type]
    assert "PACK_HAZARD_CODE_OUT_OF_SCOPE" in [f.code for f in findings]
