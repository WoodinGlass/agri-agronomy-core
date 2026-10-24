"""Derived vocabulary: phase_sets, phases_by_archetype, climate_zones."""

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


def test_all_derived_files_exist() -> None:
    for name in ("phase_sets.yaml", "phases_by_archetype.yaml", "climate_zones.yaml"):
        assert (VOCAB_DIR / name).is_file(), f"missing {name}"


def test_schema_version_is_one() -> None:
    for name in ("phase_sets.yaml", "phases_by_archetype.yaml", "climate_zones.yaml"):
        assert _load(name)["schema_version"] == 1, name


def test_keys_snake_case_ascii() -> None:
    for name, section in [
        ("phase_sets.yaml", "phase_sets"),
        ("phases_by_archetype.yaml", "phases_by_archetype"),
        ("climate_zones.yaml", "climate_zones"),
    ]:
        entries = _load(name)[section]
        assert isinstance(entries, dict)
        for k in entries:
            assert isinstance(k, str)
            assert k.isascii(), f"{name}.{k} not ASCII"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", k), f"{name}.{k} not snake_case"


def test_phase_sets_exact_set() -> None:
    ps = _load("phase_sets.yaml")["phase_sets"]
    assert set(ps) == {"none", "biological", "kc"}


def test_phase_sets_sources() -> None:
    ps = _load("phase_sets.yaml")["phase_sets"]
    assert ps["none"]["source"] == "none"
    assert ps["biological"]["source"] == "biological"
    assert ps["kc"]["source"] == "kc"


def test_phase_sets_kc_phases() -> None:
    ps = _load("phase_sets.yaml")["phase_sets"]
    assert ps["kc"]["phases"] == ["initial", "development", "midseason", "late_season"]


def test_phase_sets_none_has_no_phases() -> None:
    ps = _load("phase_sets.yaml")["phase_sets"]
    assert "phases" not in ps["none"]
    assert "phases" not in ps["biological"]


def test_phases_by_archetype_only_initial() -> None:
    archetypes = _load("archetypes.yaml")["archetypes"]
    initial = {k for k, v in archetypes.items() if v["has_default_phases"]}
    non_initial = {k for k, v in archetypes.items() if not v["has_default_phases"]}
    pb = _load("phases_by_archetype.yaml")["phases_by_archetype"]
    assert set(pb) == initial, f"phases_by_archetype keys={sorted(pb)} vs initial={sorted(initial)}"
    for k in non_initial:
        assert k not in pb, f"{k} is non-initial but has phases"


def test_phases_are_valid_format() -> None:
    pb = _load("phases_by_archetype.yaml")["phases_by_archetype"]
    for arch, meta in pb.items():
        phases = meta["phases"]
        assert isinstance(phases, list), f"{arch}.phases not a list"
        assert len(phases) >= 1, f"{arch}.phases empty"
        for phase in phases:
            assert isinstance(phase, str)
            assert phase.isascii(), f"{arch}.phases has non-ASCII {phase!r}"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", phase), f"{arch}.phases bad {phase!r}"
        assert len(set(phases)) == len(phases), f"{arch}.phases has duplicates"


def test_climate_zones_exact_set() -> None:
    cz = _load("climate_zones.yaml")["climate_zones"]
    assert set(cz) == {
        "tropical",
        "subtropical",
        "temperate",
        "arid",
        "mediterranean",
        "alpine",
    }


def test_climate_zones_have_description() -> None:
    cz = _load("climate_zones.yaml")["climate_zones"]
    for meta in cz.values():
        assert isinstance(meta["description"], str)
        assert meta["description"]
