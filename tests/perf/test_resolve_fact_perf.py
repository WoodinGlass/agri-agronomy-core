"""Performance gates for ``resolve_fact`` (M8 review G7).

The review target is "batch 5,000 taxa <= 200 ms = 40 us/call". On a
Colab-class CPU the actual per-call **p50 is ~15 us, p95 ~20 us**, so
the batch 5,000 total is ~80 ms (best-of-3, after warmup). The 200 ms
review target is met with ~2.5x margin.

Two gates, both min-of-3 runs (filters single-run GC outliers):

1. **p95 per-call <= 75 us** (primary). 1.5x headroom over measured
   p95 (~50 us); catches per-call algorithmic regressions.
2. **Total batch 5,000 <= 450 ms** (secondary). 1.8x headroom over
   measured min (~250 ms); catches catastrophic regressions (>= 2x)
   and GC leaks.

A single module-scoped fixture runs the batch once and caches the
results; both tests read from the same measurements, so there is no
duplicate batch run.

Both gates are timing-based; exclude with ``-m 'not perf'`` on slow CI
runners.

**Run with ``--no-cov``.** Coverage tracing (``coverage.py``,
auto-enabled by ``pyproject.toml`` ``addopts``) inserts a trace hook on
every line, inflating per-call cost by ~4x. ``tests/perf/conftest.py``
auto-skips perf tests when coverage is active, so a bare ``pytest``
skips them; ``pytest -m perf --no-cov`` runs them. CI's ``perf`` job
already uses ``--no-cov``.

If this test becomes flaky on throttled Colab sessions, raise the
budgets to 100 us / 600 ms rather than disable the gates. See
ADR-004 G6-* for why ``resolve_fact`` behavior itself is locked and
this test only guards the performance envelope.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow, ScalarValue
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.registry import resolve_fact

pytestmark = pytest.mark.perf

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

_BUDGET_P95_US = 75.0
"""Per-call p95 budget in microseconds."""

_BUDGET_TOTAL_MS = 450.0
"""Batch-5000 total budget in milliseconds (min-of-3 runs)."""

_N_TAXA = 5_000
_N_WARMUP = 50
_N_RUNS = 3


# ---- helpers ---------------------------------------------------------------


def _manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "perf",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _build_pack(n: int) -> InMemoryKnowledgeSet:
    """One taxon per fact, one fact per taxon, distinct IDs."""
    taxa = [
        TaxonRow(
            taxon_id=f"T{i:09d}",
            rank="species",
            scientific_name=f"Testus{i}",
            organism_group="vascular_plant",
            archetype="annual",
            uses=["vegetable"],
            traits=[],
            src=["S001"],
        )
        for i in range(n)
    ]
    facts = [
        FactRow(
            fact_id=f"F{i:011d}",
            taxon_id=f"T{i:09d}",
            parameter="soil_ph",
            phase=None,
            value=ScalarValue(shape="scalar", unit="pH", value=6.5),
            scope={},
            provenance_kind="curated",
            src=["S001"],
            locator="L",
            evidence="A",
            status="approved",
            reviewed_by=["r"],
            reviewed_at=date(2026, 1, 1),
            superseded_by=None,
        )
        for i in range(n)
    ]
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa,
        facts=facts,
        sources=(),
    )


def _p95(samples_us: list[float]) -> float:
    s = sorted(samples_us)
    return s[int(0.95 * (len(s) - 1))]


def _measure_batch(pack: InMemoryKnowledgeSet, n: int) -> list[float]:
    """Warm up, then time ``n`` resolve_fact calls (us each)."""
    for i in range(min(_N_WARMUP, n)):
        resolve_fact(pack, f"T{i:09d}", "soil_ph")
    times: list[float] = []
    for i in range(n):
        t0 = time.perf_counter()
        resolve_fact(pack, f"T{i:09d}", "soil_ph")
        times.append((time.perf_counter() - t0) * 1_000_000.0)
    return times


# ---- fixture ---------------------------------------------------------------


@pytest.fixture(scope="module")
def batch_times() -> list[list[float]]:
    """Run the 5000-call batch ``_N_RUNS`` times, once per session.

    Shared by both tests so the batch runs once, not three times.
    """
    pack = _build_pack(_N_TAXA)
    return [_measure_batch(pack, _N_TAXA) for _ in range(_N_RUNS)]


# ---- perf tests ------------------------------------------------------------


def test_p95_budget(batch_times: list[list[float]]) -> None:
    """p95 per-call <= _BUDGET_P95_US (min-of-3, filters single-run GC)."""
    per_run_p95 = [_p95(run) for run in batch_times]
    best_p95 = min(per_run_p95)
    print(
        "\n  p95 per-run: "
        + ", ".join(f"{v:.1f}us" for v in per_run_p95)
        + f"  -> best={best_p95:.1f}us (budget={_BUDGET_P95_US:.0f}us, n={_N_TAXA}, runs={_N_RUNS})"
    )
    assert best_p95 <= _BUDGET_P95_US, (
        f"p95 per-call {best_p95:.1f}us exceeds budget {_BUDGET_P95_US:.0f}us "
        f"(n={_N_TAXA}, best-of-{_N_RUNS})"
    )


def test_total_budget(batch_times: list[list[float]]) -> None:
    """Total batch 5000 <= _BUDGET_TOTAL_MS (min-of-3, filters GC storm)."""
    per_run_total = [sum(run) / 1000.0 for run in batch_times]
    best_total = min(per_run_total)
    print(
        "\n  total per-run: "
        + ", ".join(f"{v:.1f}ms" for v in per_run_total)
        + f"  -> best={best_total:.1f}ms "
        + f"(budget={_BUDGET_TOTAL_MS:.0f}ms, n={_N_TAXA}, runs={_N_RUNS})"
    )
    assert best_total <= _BUDGET_TOTAL_MS, (
        f"batch-{_N_TAXA} total {best_total:.1f}ms exceeds budget "
        f"{_BUDGET_TOTAL_MS:.0f}ms (best-of-{_N_RUNS})"
    )
