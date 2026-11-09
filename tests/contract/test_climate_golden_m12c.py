"""Golden vectors for M12c, hand-derived."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from agri_core.climate import (
    bio_01,
    bio_06,
    bio_07,
    bio_12,
    bio_13,
    bio_14,
    bio_15,
    threshold_index,
)
from agri_core.models import Result, is_success

pytestmark = pytest.mark.golden

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "climate" / "m12c.json"
_BASE = date(2026, 1, 1)

_FN: dict[str, Callable[..., object]] = {
    "bio_01": bio_01,
    "bio_06": bio_06,
    "bio_07": bio_07,
    "bio_12": bio_12,
    "bio_13": bio_13,
    "bio_14": bio_14,
    "bio_15": bio_15,
    "threshold_index": threshold_index,
}


def _cases() -> list[tuple[str, dict[str, Any]]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    out: list[tuple[str, dict[str, Any]]] = []
    for fn_name, entries in data.items():
        for entry in entries:
            out.append((fn_name, entry))
    return out


_CASES = _cases()


def _prep(fn_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    inputs = dict(inputs)
    if "dates_offset" in inputs:
        n = inputs["n"]
        inputs.pop("n")
        inputs.pop("dates_offset")
        inputs["dates"] = [_BASE + timedelta(days=i) for i in range(n)]
    return inputs


@pytest.mark.parametrize(
    ("fn_name", "entry"),
    _CASES,
    ids=[f"{fn}::{i}" for i, (fn, _) in enumerate(_CASES)],
)
def test_golden(fn_name: str, entry: dict[str, Any]) -> None:
    fn = _FN[fn_name]
    inputs = _prep(fn_name, entry["inputs"])
    out = fn(**inputs)
    assert is_success(out)
    assert isinstance(out, Result)
    expected = float(entry["expected"])
    rel = float(entry.get("tol_rel", 1e-2))
    abs_tol = float(entry.get("tol_abs", 0.0))
    delta = abs(out.value - expected)
    if abs_tol:
        assert delta <= abs_tol
    else:
        assert out.value == pytest.approx(expected, rel=rel), (
            f"{fn_name}: {out.value} vs {expected}\nderivation: {entry.get('derivation', '')}"
        )
