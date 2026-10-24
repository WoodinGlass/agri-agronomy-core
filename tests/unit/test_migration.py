"""Migration must be lossless and use only current vocab codes."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "design" / "plant_wishlist_v4.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "wishlist_derived.csv"


def _rows(p: Path) -> list[dict[str, str]]:
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_lossless_count_and_names() -> None:
    snap = _rows(SNAPSHOT)
    fix = _rows(FIXTURE)
    assert len(snap) == len(fix), "row count changed during migration"
    assert sorted(r["name"] for r in snap) == sorted(r["name"] for r in fix)


def test_removed_use_codes_absent() -> None:
    for r in _rows(FIXTURE):
        assert r["use"] not in ("specialty", "fodder"), (
            f"{r['name']}: use={r['use']!r} is a removed code"
        )


def test_removed_system_codes_absent() -> None:
    for r in _rows(FIXTURE):
        assert r["system"] not in ("substrate", "greenhouse"), (
            f"{r['name']}: system={r['system']!r} is a removed code"
        )


def test_removed_trait_codes_absent() -> None:
    removed = {"humidity_min", "water_tds_max"}
    for r in _rows(FIXTURE):
        traits = {t for t in r["traits"].split("|") if t}
        assert not (traits & removed), (
            f"{r['name']}: contains removed trait {sorted(traits & removed)}"
        )


def test_mapping_rule_values() -> None:
    for r in _rows(FIXTURE):
        assert r["mapping_rule"] in ("auto", "manual"), (
            f"{r['name']}: mapping_rule={r['mapping_rule']!r}"
        )


def test_needs_review_values() -> None:
    for r in _rows(FIXTURE):
        assert r["needs_review"] in ("true", "false"), (
            f"{r['name']}: needs_review={r['needs_review']!r}"
        )


def test_manual_rows_flagged() -> None:
    for r in _rows(FIXTURE):
        if r["mapping_rule"] == "manual":
            assert r["needs_review"] == "true", (
                f"{r['name']}: manual mapping without needs_review=true"
            )


def test_special_needs_kept_for_audit() -> None:
    snap = {r["name"]: r for r in _rows(SNAPSHOT)}
    for r in _rows(FIXTURE):
        original = snap[r["name"]]["special_needs"] or ""
        assert r["special_needs_v4"] == original, (
            f"{r['name']}: special_needs_v4 does not match snapshot"
        )
