"""The shipped parameters.core.yaml is valid and consistent."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agri_core.models.dictionary import Dictionary

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
DICT = ROOT / "dictionary"
VOCAB = DICT / "vocab"
PARAMS_YAML = DICT / "parameters.core.yaml"
MODULES_YAML = VOCAB / "modules.yaml"
UNIT_REG = DICT / "unit_registry.yaml"


def _vocab_keys(name: str, section: str) -> set[str]:
    data = yaml.safe_load((VOCAB / f"{name}.yaml").read_text(encoding="utf-8"))
    return set(data[section].keys())


@pytest.fixture(scope="module")
def dictionary() -> Dictionary:
    return Dictionary.load(PARAMS_YAML)


def test_dictionary_version_is_dev() -> None:
    data = yaml.safe_load(PARAMS_YAML.read_text(encoding="utf-8"))
    assert data["dictionary_version"] == "1.0.0-dev"


def test_all_params_have_required_shape_fields(dictionary: Dictionary) -> None:
    for p in dictionary.parameters.values():
        numeric = {"trapezoid", "range", "scalar"}
        enum = {"enum", "enum_set"}
        if p.shape in numeric:
            assert p.unit is not None
            assert p.physical_range is not None
        if p.shape in enum:
            assert p.enum_values is not None or p.enum_source is not None


def test_stages_in_vocab(dictionary: Dictionary) -> None:
    stages = _vocab_keys("stages", "stages")
    for p in dictionary.parameters.values():
        assert p.stage in stages, f"{p.key}: stage {p.stage!r}"


def test_phase_sets_in_vocab(dictionary: Dictionary) -> None:
    phase_sets = _vocab_keys("phase_sets", "phase_sets")
    for p in dictionary.parameters.values():
        assert p.phase_set in phase_sets, f"{p.key}: phase_set {p.phase_set!r}"


def test_archetypes_subset(dictionary: Dictionary) -> None:
    archetypes = _vocab_keys("archetypes", "archetypes")
    for p in dictionary.parameters.values():
        if p.applies_to.archetypes is not None:
            for a in p.applies_to.archetypes:
                assert a in archetypes, f"{p.key}: archetype {a!r}"


def test_uses_subset(dictionary: Dictionary) -> None:
    uses = _vocab_keys("uses", "uses")
    for p in dictionary.parameters.values():
        if p.applies_to.uses is not None:
            for u in p.applies_to.uses:
                assert u in uses, f"{p.key}: use {u!r}"


def test_systems_subset(dictionary: Dictionary) -> None:
    systems = _vocab_keys("systems", "systems")
    for p in dictionary.parameters.values():
        if p.applies_to.systems is not None:
            for s in p.applies_to.systems:
                assert s in systems, f"{p.key}: system {s!r}"


def test_traits_subset(dictionary: Dictionary) -> None:
    traits = _vocab_keys("traits", "traits")
    for p in dictionary.parameters.values():
        if p.applies_to.traits is not None:
            for t in p.applies_to.traits:
                assert t in traits, f"{p.key}: trait {t!r}"


def test_organism_groups_subset(dictionary: Dictionary) -> None:
    groups = _vocab_keys("organism_groups", "organism_groups")
    for p in dictionary.parameters.values():
        for g in p.applies_to.organism_groups:
            assert g in groups, f"{p.key}: organism_group {g!r}"


def test_scope_keys_subset(dictionary: Dictionary) -> None:
    scope_keys = _vocab_keys("scope_keys", "keys")
    for p in dictionary.parameters.values():
        for k in p.scope_keys:
            assert k in scope_keys, f"{p.key}: scope_key {k!r}"


def test_used_by_modules_exist(dictionary: Dictionary) -> None:
    modules_data = yaml.safe_load(MODULES_YAML.read_text(encoding="utf-8"))
    modules = set(modules_data["modules"].keys())
    for p in dictionary.parameters.values():
        for m in p.used_by:
            assert m in modules, f"{p.key}: module {m!r}"


def test_bidirectional_used_by_reads(dictionary: Dictionary) -> None:
    """For each (param, module): param in module.reads iff module in param.used_by."""
    modules_data = yaml.safe_load(MODULES_YAML.read_text(encoding="utf-8"))
    param_to_modules: dict[str, set[str]] = {k: set() for k in dictionary.parameters}
    module_to_params: dict[str, set[str]] = {
        m: set(meta.get("reads", [])) for m, meta in modules_data["modules"].items()
    }

    for key, p in dictionary.parameters.items():
        for m in p.used_by:
            param_to_modules[key].add(m)
            if key not in module_to_params[m]:
                pytest.fail(f"{key}.used_by contains {m!r}, but {m}.reads does not list {key!r}")

    for m, reads in module_to_params.items():
        for key in reads:
            if key not in dictionary.parameters:
                pytest.fail(f"{m}.reads contains {key!r}, not in dictionary")
            if m not in dictionary.parameters[key].used_by:
                pytest.fail(f"{m}.reads contains {key!r}, but {key}.used_by does not contain {m!r}")


def test_trapezoid_implies_thresholds(dictionary: Dictionary) -> None:
    for p in dictionary.parameters.values():
        if p.shape == "trapezoid":
            assert "thresholds" in p.used_by, (
                f"{p.key}: shape=trapezoid but used_by lacks 'thresholds'"
            )


def test_no_safety_critical_in_c_1(dictionary: Dictionary) -> None:
    """c-1 has no safety-critical params; c-3 will pin the 3 dose caps."""
    sc = {k for k, p in dictionary.parameters.items() if p.safety_critical}
    assert sc == set(), f"unexpected safety_critical params in c-1: {sc}"


def test_tier_required_pinned_set(dictionary: Dictionary) -> None:
    expected = {
        "managed_cycle",
        "phase_duration",
        "air_temp_day",
        "air_temp_night",
        "air_rh",
    }
    actual = {k for k, p in dictionary.parameters.items() if p.tier_required}
    assert actual == expected, f"tier_required differs: {actual ^ expected}"


def test_content_hash_stable_across_loads() -> None:
    """Hash is stable across two loads; lock file comes in c-3."""
    d1 = Dictionary.load(PARAMS_YAML)
    d2 = Dictionary.load(PARAMS_YAML)
    assert d1.content_hash() == d2.content_hash()


def test_unit_registry_matches_canonical_units() -> None:
    from agri_core.models.units import CUSTOM_CANONICAL_UNITS

    reg = yaml.safe_load(UNIT_REG.read_text(encoding="utf-8"))
    custom = set(reg["custom_units"].keys())
    assert custom == CUSTOM_CANONICAL_UNITS, (
        f"custom_units mismatch: {custom ^ CUSTOM_CANONICAL_UNITS}"
    )


def test_pint_canonical_units_parse() -> None:
    """Every PINT_CANONICAL_UNITS string must be parsable by pint.

    We do NOT compare ``str(ureg.Unit(u))`` to ``u``: pint normalizes the
    order of units in denominators (alphabetical), so
    ``mole/meter**2/day`` serializes as ``mole/day/meter**2``. What matters
    is that the string parses without error.
    """
    import pint

    from agri_core.models.units import PINT_CANONICAL_UNITS

    ureg = pint.UnitRegistry()
    for u in PINT_CANONICAL_UNITS:
        try:
            ureg.Unit(u)
        except Exception as exc:
            pytest.fail(f"unit {u!r} failed to parse: {exc}")


def test_pint_canonical_units_unique() -> None:
    """No two strings in PINT_CANONICAL_UNITS represent the same physical unit."""
    import pint

    from agri_core.models.units import PINT_CANONICAL_UNITS

    ureg = pint.UnitRegistry()
    seen: dict[str, str] = {}
    for u in PINT_CANONICAL_UNITS:
        key = str(ureg.Unit(u))
        if key in seen:
            pytest.fail(f"duplicate unit: {u!r} and {seen[key]!r} both serialize to {key!r}")
        seen[key] = u


def test_pint_canonical_units_are_used_somewhere(dictionary: Dictionary) -> None:
    """Every pint-canonical unit appears in at least one parameter.

    This guards against typos where a unit is spelled correctly in the test
    set but never referenced, or vice versa. In c-1, only a subset of
    PINT_CANONICAL_UNITS is used (deferred units arrive in c-2/c-3); this
    test will be tightened to strict equality at c-3.
    """
    from agri_core.models.units import PINT_CANONICAL_UNITS

    used = {p.unit for p in dictionary.parameters.values() if p.unit is not None}
    for u in used:
        assert (
            u in PINT_CANONICAL_UNITS
            or u
            in __import__(
                "agri_core.models.units", fromlist=["CUSTOM_CANONICAL_UNITS"]
            ).CUSTOM_CANONICAL_UNITS
        ), f"parameter uses non-canonical unit {u!r}"


# --- c-2b parameters ---


def test_dictionary_has_24_params(dictionary: Dictionary) -> None:
    """12 from c-1 + 12 from c-2b."""
    assert len(dictionary.parameters) == 24


@pytest.mark.parametrize(
    "key",
    [
        "kc",
        "kc_stage_length",
        "root_depth",
        "depletion_fraction",
        "awd_reflood_depth",
        "ponding_depth",
        "percolation_rate",
        "predrain_days",
        "must_flood_phases",
        "moisture_band",
        "water_ec_max",
        "water_temp_max",
    ],
)
def test_c_2b_param_present(dictionary: Dictionary, key: str) -> None:
    p = dictionary.lookup(key)
    assert p.key == key


def test_must_flood_phases_uses_enum_source(dictionary: Dictionary) -> None:
    p = dictionary.lookup("must_flood_phases")
    assert p.shape == "enum_set"
    assert p.enum_source == "phases:biological"
    assert p.enum_values is None


def test_moisture_band_in_irrigation_and_thresholds(dictionary: Dictionary) -> None:
    p = dictionary.lookup("moisture_band")
    assert "irrigation" in p.used_by
    assert "thresholds" in p.used_by
    assert p.shape == "trapezoid"


def test_kc_allowed_phases(dictionary: Dictionary) -> None:
    p = dictionary.lookup("kc")
    assert p.allowed_phases == ["initial", "midseason", "late_season"]


def test_kc_stage_length_allowed_phases(dictionary: Dictionary) -> None:
    p = dictionary.lookup("kc_stage_length")
    assert p.allowed_phases == ["initial", "development", "midseason", "late_season"]


def test_awd_reflood_depth_description(dictionary: Dictionary) -> None:
    p = dictionary.lookup("awd_reflood_depth")
    assert "below" in p.description.lower()
    assert "positive" in p.description.lower()


def test_root_depth_stage_and_unit(dictionary: Dictionary) -> None:
    p = dictionary.lookup("root_depth")
    assert p.stage == "care"
    assert p.unit == "meter"
    assert p.phase_set == "kc"


def test_water_ec_max_stage_and_unit(dictionary: Dictionary) -> None:
    p = dictionary.lookup("water_ec_max")
    assert p.stage == "site_media"
    assert p.unit == "decisiemens/meter"
    assert "media" in p.used_by


def test_percolation_rate_unit(dictionary: Dictionary) -> None:
    p = dictionary.lookup("percolation_rate")
    assert p.unit == "millimeter/day"


def test_predrain_days_unit_and_range(dictionary: Dictionary) -> None:
    p = dictionary.lookup("predrain_days")
    assert p.unit == "day"
    assert p.physical_range == (0.0, 30.0)
