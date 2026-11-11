"""propagation_plan against the ACTUAL sample pack (M15 e2e).

The sample pack has no propagation facts for any taxon (T000000009 was
added in P6 with suitability facts only). These tests confirm the
planner refuses with `Unknown` rather than crashing or guessing — the
"refuse rather than guess" principle against a real pack.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agri_core.models import Unknown
from agri_core.pack import load_knowledge_set
from agri_core.propagation import propagation_plan

pytestmark = pytest.mark.scenario

_REPO = Path(__file__).resolve().parents[2]
_SAMPLE = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(_SAMPLE, allow_synthetic=True)


def test_propagation_plan_unknown_for_real_taxon_without_facts(pack) -> None:
    out = propagation_plan(
        pack,
        "T000000009",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, Unknown)
    assert out.code == "no_match"


def test_propagation_plan_unknown_for_fungal_taxon(pack) -> None:
    out = propagation_plan(
        pack,
        "T000000005",
        start_date=date(2026, 4, 15),
        method="seed",
    )
    assert isinstance(out, Unknown)
    assert out.code == "no_match"
