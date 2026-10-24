"""Metadata vocab: habits, states, targets, scope_keys, modules, units."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pint
import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
VOCAB = ROOT / "dictionary" / "vocab"
UNIT_REG = ROOT / "dictionary" / "unit_registry.yaml"


def _load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((VOCAB / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{name} is not a mapping"
    return cast(dict[str, Any], data)


# --- simple enums -------------------------------------------------------


def test_simple_enum_files_exist() -> None:
    for name in ("growth_habits.yaml", "establishment_states.yaml", "yield_targets.yaml"):
        assert (VOCAB / name).is_file(), f"missing {name}"


def test_simple_enum_schema_version() -> None:
    for name in ("growth_habits.yaml", "establishment_states.yaml", "yield_targets.yaml"):
        assert _load(name)["schema_version"] == 1, name


def test_simple_enum_keys_snake_case() -> None:
    for name, section in [
        ("growth_habits.yaml", "growth_habits"),
        ("establishment_states.yaml", "establishment_states"),
        ("yield_targets.yaml", "yield_targets"),
    ]:
        entries = _load(name)[section]
        for k in entries:
            assert isinstance(k, str), f"{name}.{k} not str"
            assert k.isascii(), f"{name}.{k} not ASCII"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", k), f"{name}.{k} not snake_case"


def test_growth_habits_exact_set() -> None:
    habits = _load("growth_habits.yaml")["growth_habits"]
    assert set(habits) == {
        "rosette",
        "vine",
        "shrub",
        "tree",
        "clump",
        "mat",
        "submerged",
        "floating",
    }


def test_establishment_states_exact_set() -> None:
    states = _load("establishment_states.yaml")["establishment_states"]
    assert set(states) == {"new", "established"}


def test_yield_targets_exact_set() -> None:
    targets = _load("yield_targets.yaml")["yield_targets"]
    assert set(targets) == {"subsistence", "commercial", "experimental"}


def test_simple_enum_have_description() -> None:
    for name, section in [
        ("growth_habits.yaml", "growth_habits"),
        ("establishment_states.yaml", "establishment_states"),
        ("yield_targets.yaml", "yield_targets"),
    ]:
        for k, meta in _load(name)[section].items():
            desc = meta.get("description", "")
            assert isinstance(desc, str), f"{name}.{k}.description not str"
            assert desc, f"{name}.{k}.description empty"


# --- modules ------------------------------------------------------------


def test_modules_file_exists() -> None:
    assert (VOCAB / "modules.yaml").is_file()


def test_modules_exact_set() -> None:
    mods = _load("modules.yaml")["modules"]
    assert set(mods) == {
        "climate",
        "thresholds",
        "stages",
        "irrigation",
        "fertilizer",
        "media",
        "suitability",
        "propagation",
        "safety",
        "export",
    }


def test_modules_have_description() -> None:
    mods = _load("modules.yaml")["modules"]
    for k, meta in mods.items():
        desc = meta.get("description", "")
        assert isinstance(desc, str), f"modules.{k}.description not str"
        assert desc, f"modules.{k}.description empty"


# --- scope_keys ---------------------------------------------------------


def test_scope_keys_file_exists() -> None:
    assert (VOCAB / "scope_keys.yaml").is_file()


def test_scope_keys_exact_set() -> None:
    keys = _load("scope_keys.yaml")["keys"]
    assert set(keys) == {
        "country",
        "region",
        "elevation_m",
        "system",
        "environment",
        "climate_zone",
        "growth_habit",
        "establishment",
        "yield_target",
        "method",
        "variety",
        "use",
    }


def test_scope_keys_types() -> None:
    keys = _load("scope_keys.yaml")["keys"]
    for k, meta in keys.items():
        assert meta["type"] in ("string", "enum", "range"), f"{k}.type {meta['type']!r}"


def test_scope_keys_multi_is_bool() -> None:
    keys = _load("scope_keys.yaml")["keys"]
    for k, meta in keys.items():
        assert isinstance(meta["multi"], bool), f"{k}.multi not bool"


def test_scope_keys_range_only_elevation() -> None:
    keys = _load("scope_keys.yaml")["keys"]
    range_keys = [k for k, meta in keys.items() if meta["type"] == "range"]
    assert range_keys == ["elevation_m"]


def test_scope_keys_range_has_unit() -> None:
    keys = _load("scope_keys.yaml")["keys"]
    for k, meta in keys.items():
        if meta["type"] == "range":
            assert "unit" in meta, f"{k} range without unit"


# --- scope_keys vocab resolution ----------------------------------------
# Vocabularies referenced by scope_keys fall into three categories:
#   1. Internal: file exists in vocab/ (systems, environments, climate_zones, etc.)
#   2. External ISO: iso_3166_1_alpha2, iso_3166_2 (not our files)
#   3. Deferred: methods (defined in M1-2)

EXTERNAL_VOCABS = {"iso_3166_1_alpha2", "iso_3166_2"}
DEFERRED_VOCABS = {"methods"}


def test_scope_keys_vocabs_resolve() -> None:
    keys = _load("scope_keys.yaml")["keys"]
    for k, meta in keys.items():
        vocab = meta.get("vocab")
        if vocab is None:
            continue
        if vocab in EXTERNAL_VOCABS:
            continue
        if vocab in DEFERRED_VOCABS:
            continue
        assert (VOCAB / f"{vocab}.yaml").is_file(), f"scope_keys.{k} -> {vocab}.yaml not found"


def test_scope_keys_enum_vocab_exists_for_internal() -> None:
    """Every enum scope key with an internal vocab points to a real file."""
    keys = _load("scope_keys.yaml")["keys"]
    for k, meta in keys.items():
        if meta["type"] != "enum":
            continue
        vocab = meta.get("vocab")
        assert vocab is not None, f"{k} is enum but has no vocab"
        if vocab in EXTERNAL_VOCABS or vocab in DEFERRED_VOCABS:
            continue
        assert (VOCAB / f"{vocab}.yaml").is_file(), f"{k} -> enum vocab {vocab}.yaml not found"


# --- unit registry ------------------------------------------------------


def test_unit_registry_exists() -> None:
    assert UNIT_REG.is_file()


def test_unit_registry_schema_version() -> None:
    reg = yaml.safe_load(UNIT_REG.read_text(encoding="utf-8"))
    assert reg["schema_version"] == 1


def test_unit_registry_custom_units_exact_set() -> None:
    reg = yaml.safe_load(UNIT_REG.read_text(encoding="utf-8"))
    assert set(reg["custom_units"]) == {"pH", "ppm", "percent"}


def test_unit_registry_custom_units_have_shape() -> None:
    reg = yaml.safe_load(UNIT_REG.read_text(encoding="utf-8"))
    for name, meta in reg["custom_units"].items():
        assert meta["kind"] == "custom", f"{name}.kind"
        desc = meta.get("description", "")
        assert isinstance(desc, str), f"{name}.description not str"
        assert len(desc) >= 10, f"{name}.description too short"
        rng = meta.get("range")
        assert isinstance(rng, list), f"{name}.range not list"
        assert len(rng) == 2, f"{name}.range not 2-element"
        assert rng[0] < rng[1], f"{name}.range not increasing"


def test_unit_registry_standard_units_parse_via_pint() -> None:
    """Standard units used across the dictionary must parse with pint."""
    reg = yaml.safe_load(UNIT_REG.read_text(encoding="utf-8"))
    aliases = reg.get("pint_aliases", {})
    ureg = pint.UnitRegistry()
    for alias, target in aliases.items():
        ureg.define(f"{alias} = {target}")
    for u in [
        "degC",
        "dS/m",
        "kg/ha",
        "mole/m^2/day",
        "m",
        "cm",
        "L",
        "g/plant",
        "dimensionless",
    ]:
        ureg.parse_units(u)


def test_unit_registry_pint_aliases_shape() -> None:
    """pint_aliases, if present, is a dict of str -> str."""
    reg = yaml.safe_load(UNIT_REG.read_text(encoding="utf-8"))
    aliases = reg.get("pint_aliases", {})
    assert isinstance(aliases, dict), "pint_aliases not a dict"
    for k, v in aliases.items():
        assert isinstance(k, str), f"pint_aliases key {k!r} not str"
        assert isinstance(v, str), f"pint_aliases[{k}] not str"
        assert k.isascii(), f"non-ASCII key in pint_aliases: {k!r}"
        assert v.isascii(), f"non-ASCII target in pint_aliases[{k}]: {v!r}"
