"""Traits and organism_groups vocabularies."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

pytestmark = pytest.mark.contract

VOCAB_DIR = Path(__file__).resolve().parents[2] / "dictionary" / "vocab"


def _load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((VOCAB_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{name} is not a mapping"
    return cast(dict[str, Any], data)


# --- traits -------------------------------------------------------------


def test_traits_file_exists() -> None:
    assert (VOCAB_DIR / "traits.yaml").is_file()


def test_traits_schema_version_is_one() -> None:
    assert _load("traits.yaml")["schema_version"] == 1


def test_traits_exact_set() -> None:
    traits = _load("traits.yaml")["traits"]
    assert set(traits) == {
        "chill_requirement",
        "vernalization",
        "photoperiod_sensitive",
        "dormancy_period",
        "symbiont_required",
        "nitrogen_fixing",
        "pollination_management",
        "rootstock_graft",
        "support_required",
        "shade_required",
        "regrowth_cycle",
        "curing_required",
        "acidic_media_required",
        "alkaline_soil_required",
        "cool_water_required",
    }


def test_trait_names_snake_case_ascii() -> None:
    traits = _load("traits.yaml")["traits"]
    for k in traits:
        assert isinstance(k, str)
        assert k.isascii(), f"trait {k!r} not ASCII"
        assert re.fullmatch(r"[a-z][a-z0-9_]*", k), f"trait {k!r} not snake_case"


def test_trait_names_not_parameter_like() -> None:
    """Trait names must not look like parameter names or bounds."""
    traits = _load("traits.yaml")["traits"]
    for k in traits:
        assert not k.endswith("_min"), f"{k} ends with _min"
        assert not k.endswith("_max"), f"{k} ends with _max"
        assert not k.endswith("_opt"), f"{k} ends with _opt"
        assert "preference" not in k, f"{k} contains 'preference'"


def test_traits_have_description() -> None:
    traits = _load("traits.yaml")["traits"]
    for k, meta in traits.items():
        desc = meta.get("description", "")
        assert isinstance(desc, str), f"{k}.description not str"
        assert len(desc) >= 20, f"{k}.description too short: {desc!r}"
        assert desc.rstrip().endswith("."), f"{k}.description missing final period"


def test_traits_have_examples() -> None:
    traits = _load("traits.yaml")["traits"]
    for k, meta in traits.items():
        examples = meta.get("examples", [])
        assert isinstance(examples, list), f"{k}.examples not list"
        assert len(examples) >= 1, f"{k}.examples empty"
        for ex in examples:
            assert isinstance(ex, str), f"{k}.examples contains non-str {ex!r}"
            assert ex, f"{k}.examples contains empty string"
            assert ex.isascii(), f"{k}.examples contains non-ASCII {ex!r}"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", ex), f"{k}.examples bad {ex!r}"


# --- organism_groups ----------------------------------------------------


def test_organism_groups_file_exists() -> None:
    assert (VOCAB_DIR / "organism_groups.yaml").is_file()


def test_organism_groups_schema_version_is_one() -> None:
    assert _load("organism_groups.yaml")["schema_version"] == 1


def test_organism_groups_exact_set() -> None:
    groups = _load("organism_groups.yaml")["organism_groups"]
    assert set(groups) == {
        "vascular_plant",
        "bryophyte",
        "alga",
        "fungus",
        "lichen",
    }


def test_organism_groups_allowed_archetypes_subset() -> None:
    groups = _load("organism_groups.yaml")["organism_groups"]
    archetypes = set(_load("archetypes.yaml")["archetypes"])
    for name, meta in groups.items():
        allowed = meta.get("allowed_archetypes", [])
        assert isinstance(allowed, list), f"{name}.allowed_archetypes not list"
        assert len(allowed) >= 1, f"{name}.allowed_archetypes empty"
        for arch in allowed:
            assert arch in archetypes, f"{name} allows unknown archetype {arch!r}"


def test_organism_groups_exclusive_matrix() -> None:
    """Fungus only allows fungal; alga only allows algae; etc."""
    groups = _load("organism_groups.yaml")["organism_groups"]
    assert groups["fungus"]["allowed_archetypes"] == ["fungal"]
    assert groups["alga"]["allowed_archetypes"] == ["algae"]
    assert groups["lichen"]["allowed_archetypes"] == ["lichen"]
    assert groups["bryophyte"]["allowed_archetypes"] == ["bryophyte"]


def test_organism_groups_vascular_includes_all_initial_plus() -> None:
    groups = _load("organism_groups.yaml")["organism_groups"]
    expected = {
        "annual",
        "biennial",
        "herbaceous_perennial",
        "woody_perennial",
        "geophyte",
        "aquatic",
        "epiphyte",
        "pteridophyte",
        "gymnosperm",
    }
    assert set(groups["vascular_plant"]["allowed_archetypes"]) == expected


def test_organism_groups_have_description() -> None:
    groups = _load("organism_groups.yaml")["organism_groups"]
    for name, meta in groups.items():
        desc = meta.get("description", "")
        assert isinstance(desc, str), f"{name}.description not str"
        assert desc, f"{name}.description empty"
