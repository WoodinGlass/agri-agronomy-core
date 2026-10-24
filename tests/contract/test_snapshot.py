"""Snapshot integrity."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "design" / "plant_wishlist_v4.csv"
MIGRATION = ROOT / "docs" / "design" / "plant_wishlist_v4_migration.md"


def test_snapshot_exists() -> None:
    assert SNAPSHOT.is_file(), f"missing {SNAPSHOT.relative_to(ROOT)}"


def test_migration_doc_exists() -> None:
    assert MIGRATION.is_file(), f"missing {MIGRATION.relative_to(ROOT)}"


def test_sha256_matches_migration_doc() -> None:
    assert MIGRATION.is_file()
    doc = MIGRATION.read_text(encoding="utf-8")
    m = re.search(r"SHA-256: `([0-9a-f]{64})`", doc)
    assert m is not None, "migration doc does not record SHA-256"
    recorded = m.group(1)
    actual = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    assert recorded == actual, (
        "plant_wishlist_v4.csv has changed since migration was recorded. "
        "If the change is intentional, regenerate the migration doc; "
        "otherwise restore the file."
    )
