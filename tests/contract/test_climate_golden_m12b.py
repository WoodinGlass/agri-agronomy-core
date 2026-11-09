"""Golden vectors for M12b thermal time, hand-derived."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from agri_core.climate import (
    chill_hours,
    gdd_method_1,
    gdd_method_2,
    gdd_series,
    photothermal_units,
    utah_chill_units,
)
from agri_core.models import Result, is_success

pytestmark = pytest.mark.golden

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "climate" / "m12b.json"

_FN: dict[str, Callable[..., object]] = {
    "gdd_method_1": gdd_method_1,
    "gdd_method_2": gdd_method_2,
    "gdd_series": gdd_series,
    "chill_hours": chill_hours,
    "utah_chill_units": utah_chill_units,
    "photothermal_units": photothermal_units,
}


def _prep_inputs(fn_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    inputs = dict(inputs)
    if "dates" in inputs:
        inputs["dates"] = [date.fromisoformat(d) for d in inputs["dates"]]
    if "timestamps" in inputs:
        inputs["timestamps"] = [datetime.fromisoformat(t) for t in inputs["timestamps"]]
    return inputs


def _cases() -> list[tuple[str, dict[str, Any]]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    out: list[tuple[str, dict[str, Any]]] = []
    for fn_name, entries in data.items():
        for entry in entries:
            out.append((fn_name, entry))
    return out


_CASES = _cases()


@pytest.mark.parametrize(
    ("fn_name", "entry"),
    _CASES,
    ids=[f"{fn}::{i}" for i, (fn, _) in enumerate(_CASES)],
)
def test_golden(fn_name: str, entry: dict[str, Any]) -> None:
    fn = _FN[fn_name]
    inputs = _prep_inputs(fn_name, entry["inputs"])
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
