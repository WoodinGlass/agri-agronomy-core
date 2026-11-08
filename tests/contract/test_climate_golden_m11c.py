"""Golden vectors for M11c radiation and PAR, hand-derived."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agri_core.climate import dli, net_radiation, ppfd, solar_radiation
from agri_core.models import Result, is_success

pytestmark = pytest.mark.golden

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "climate" / "m11c.json"

_FN: dict[str, Callable[..., object]] = {
    "solar_radiation": solar_radiation,
    "net_radiation": net_radiation,
    "ppfd": ppfd,
    "dli": dli,
}


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
    out = fn(**entry["inputs"])
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
