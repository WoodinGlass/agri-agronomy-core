"""Base vocabulary: archetypes, stages, systems, environments, uses."""

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


def test_all_base_files_exist() -> None:
    for name in (
        "archetypes.yaml",
        "stages.yaml",
        "systems.yaml",
        "environments.yaml",
        "uses.yaml",
    ):
        assert (VOCAB_DIR / name).is_file(), f"missing {name}"


def test_schema_version_is_one() -> None:
    for name in (
        "archetypes.yaml",
        "stages.yaml",
        "systems.yaml",
        "environments.yaml",
        "uses.yaml",
    ):
        assert _load(name)["schema_version"] == 1, name


def test_keys_snake_case_ascii() -> None:
    for name, section in [
        ("archetypes.yaml", "archetypes"),
        ("stages.yaml", "stages"),
        ("systems.yaml", "systems"),
        ("environments.yaml", "environments"),
        ("uses.yaml", "uses"),
    ]:
        entries = _load(name)[section]
        assert isinstance(entries, dict)
        for k in entries:
            assert isinstance(k, str)
            assert k.isascii(), f"{name}.{k} not ASCII"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", k), f"{name}.{k} not snake_case"


def test_archetypes_exact_set() -> None:
    arch = _load("archetypes.yaml")["archetypes"]
    assert set(arch) == {
        "annual",
        "biennial",
        "herbaceous_perennial",
        "woody_perennial",
        "geophyte",
        "aquatic",
        "epiphyte",
        "fungal",
        "pteridophyte",
        "gymnosperm",
        "algae",
        "lichen",
        "bryophyte",
    }


def test_archetypes_initial_flags() -> None:
    arch = _load("archetypes.yaml")["archetypes"]
    initial = {k for k, v in arch.items() if v["has_default_phases"]}
    non_initial = {k for k, v in arch.items() if not v["has_default_phases"]}
    assert initial == {
        "annual",
        "biennial",
        "herbaceous_perennial",
        "woody_perennial",
        "geophyte",
        "aquatic",
        "epiphyte",
        "fungal",
    }
    assert non_initial == {
        "pteridophyte",
        "gymnosperm",
        "algae",
        "lichen",
        "bryophyte",
    }


def test_archetypes_have_description() -> None:
    for meta in _load("archetypes.yaml")["archetypes"].values():
        assert isinstance(meta["description"], str)
        assert meta["description"]


def test_stages_exact_set_and_flags() -> None:
    stages = _load("stages.yaml")["stages"]
    assert set(stages) == {
        "cycle",
        "site_media",
        "seeding",
        "planting",
        "care",
        "harvest",
        "propagation",
    }
    assert stages["cycle"]["runtime"] is False
    for name in ("site_media", "seeding", "planting", "care", "harvest", "propagation"):
        assert stages[name]["runtime"] is True


def test_stages_have_order() -> None:
    stages = _load("stages.yaml")["stages"]
    orders = sorted(meta["order"] for meta in stages.values())
    assert orders == list(range(len(stages))), f"non-sequential orders: {orders}"


def test_systems_exact_set() -> None:
    systems = _load("systems.yaml")["systems"]
    assert set(systems) == {
        "field",
        "flooded",
        "container",
        "soilless",
        "fungal_bed",
        "marine",
    }
    for name in ("greenhouse", "substrate"):
        assert name not in systems, f"{name} must not be in systems"


def test_environments_exact_set() -> None:
    envs = _load("environments.yaml")["environments"]
    assert set(envs) == {"open", "protected", "indoor"}


def test_uses_exact_set() -> None:
    uses = _load("uses.yaml")["uses"]
    assert set(uses) == {
        "vegetable",
        "fruit",
        "staple",
        "forage",
        "ornamental",
        "spice",
        "edible_fungus",
    }
    for name in ("fodder", "specialty"):
        assert name not in uses, f"{name} must not be in uses"


def test_uses_status() -> None:
    uses = _load("uses.yaml")["uses"]
    assert uses["spice"]["status"] == "proposed"
    assert uses["edible_fungus"]["status"] == "proposed"
    for name in ("vegetable", "fruit", "staple", "forage", "ornamental"):
        assert uses[name]["status"] == "stable"
