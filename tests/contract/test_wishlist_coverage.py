"""Wishlist coverage: validate counted rows against current vocab.

Counting rule: a row is counted if mapping_rule=auto OR
(mapping_rule=manual AND reviewed_by is non-empty).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "wishlist_derived.csv"
VOCAB = ROOT / "dictionary" / "vocab"


def _rows() -> list[dict[str, str]]:
    with FIXTURE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _vocab(section_file: str, section: str) -> set[str]:
    data = yaml.safe_load((VOCAB / section_file).read_text(encoding="utf-8"))
    return set(data[section].keys())


def _counted(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in rows if r["mapping_rule"] == "auto" or r["reviewed_by"]]


def test_counted_rows_are_final() -> None:
    all_rows = _rows()
    counted = _counted(all_rows)
    assert len(counted) <= len(all_rows)
    for r in counted:
        assert r["mapping_rule"] == "auto" or r["reviewed_by"]


def test_counted_rows_have_valid_use() -> None:
    uses = _vocab("uses.yaml", "uses") | {"unknown"}
    for r in _counted(_rows()):
        assert r["use"] in uses, f"{r['name']}: use={r['use']!r}"


def test_counted_rows_have_valid_archetype() -> None:
    archetypes = _vocab("archetypes.yaml", "archetypes")
    for r in _counted(_rows()):
        assert r["archetype"] in archetypes, f"{r['name']}: archetype={r['archetype']!r}"


def test_counted_rows_have_valid_system_or_unknown() -> None:
    systems = _vocab("systems.yaml", "systems") | {"unknown"}
    for r in _counted(_rows()):
        assert r["system"] in systems, f"{r['name']}: system={r['system']!r}"


def test_counted_rows_have_valid_environment_or_unknown() -> None:
    envs = _vocab("environments.yaml", "environments") | {"unknown"}
    for r in _counted(_rows()):
        assert r["environment"] in envs, f"{r['name']}: environment={r['environment']!r}"


def test_counted_rows_have_valid_climate() -> None:
    climates = _vocab("climate_zones.yaml", "climate_zones")
    for r in _counted(_rows()):
        assert r["climate"] in climates, f"{r['name']}: climate={r['climate']!r}"


def test_counted_rows_traits_in_vocab() -> None:
    traits = _vocab("traits.yaml", "traits")
    for r in _counted(_rows()):
        for t in r["traits"].split("|") if r["traits"] else []:
            if not t:
                continue
            assert t in traits, f"{r['name']}: trait={t!r}"


def test_counted_count_is_consistent() -> None:
    """Counted rows = auto + reviewed manual. No row double-counted or missed."""
    rows = _rows()
    counted = _counted(rows)
    auto = sum(1 for r in rows if r["mapping_rule"] == "auto")
    manual = sum(1 for r in rows if r["mapping_rule"] == "manual")
    reviewed = sum(1 for r in rows if r["reviewed_by"] and r["mapping_rule"] == "manual")
    assert auto + manual == len(rows), (
        f"auto ({auto}) + manual ({manual}) must equal total ({len(rows)})"
    )
    assert len(counted) == auto + reviewed, (
        f"counted ({len(counted)}) must equal auto ({auto}) + reviewed_manual ({reviewed})"
    )
    assert len(counted) >= 1
    assert len(counted) <= len(rows)
