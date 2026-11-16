"""Tripwire: Cargo.lock single-version invariant (ADR-019 §11.1, §11.13).

Duplicates of `unicode-normalization` / `caseless` cause table drift
between NFKC and casefold. ICU4X must appear exactly once each as
dev-only third-oracle (ADR-019 §11.13).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract
_REPO = Path(__file__).resolve().parents[2]


def _versions(lock: str, name: str) -> list[str]:
    return re.findall(rf'name = "{re.escape(name)}"\nversion = "([^"]+)"', lock)


def test_single_unicode_normalization() -> None:
    lock = (_REPO / "Cargo.lock").read_text()
    v = _versions(lock, "unicode-normalization")
    assert len(v) == 1, f"expected 1, found {len(v)}: {v}"


def test_single_caseless() -> None:
    lock = (_REPO / "Cargo.lock").read_text()
    v = _versions(lock, "caseless")
    assert len(v) == 1, f"expected 1, found {len(v)}: {v}"


def test_single_icu_casemap() -> None:
    lock = (_REPO / "Cargo.lock").read_text()
    v = _versions(lock, "icu_casemap")
    assert len(v) == 1, f"expected 1, found {len(v)}: {v}"


def test_single_icu_normalizer() -> None:
    lock = (_REPO / "Cargo.lock").read_text()
    v = _versions(lock, "icu_normalizer")
    assert len(v) == 1, f"expected 1, found {len(v)}: {v}"
