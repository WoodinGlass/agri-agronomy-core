"""Performance gates for ``resolve_taxon`` (M8-2b).

These tests verify the M8 budget: p95 < 5 ms per query on a 10k-taxa
pack. They are timing-based and may be excluded with ``-m 'not perf'``
on slow CI runners.

The budget has ~300x headroom over measured baseline (p95 ~15 us on a
Colab-class CPU), so genuine regressions will fail long before CI
flakiness does.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.refusals import Ambiguous
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.registry import resolve_taxon

pytestmark = pytest.mark.perf

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

_BUDGET_P95_US = 5_000.0
"""Per-query p95 budget in microseconds (5 ms)."""

_N_TAXA = 10_000
_N_QUERIES = 100
_WARMUP = 10


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


def _build_distinct_pack(n: int) -> InMemoryKnowledgeSet:
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
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa,
    )


def _build_colliding_pack(n: int) -> InMemoryKnowledgeSet:
    taxa = [
        TaxonRow(
            taxon_id=f"T{i:09d}",
            rank="species",
            scientific_name="SharedName",
            organism_group="vascular_plant",
            archetype="annual",
            uses=["vegetable"],
            traits=[],
            src=["S001"],
        )
        for i in range(n)
    ]
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa,
    )


def _p95(samples_us: list[float]) -> float:
    s = sorted(samples_us)
    return s[int(0.95 * (len(s) - 1))]


def _measure(fn, queries: list[str]) -> list[float]:
    for q in queries[:_WARMUP]:
        fn(q)
    times: list[float] = []
    for q in queries:
        t0 = time.perf_counter()
        fn(q)
        times.append((time.perf_counter() - t0) * 1_000_000.0)
    return times


# ---- fixtures --------------------------------------------------------------


@pytest.fixture(scope="module")
def large_pack() -> InMemoryKnowledgeSet:
    return _build_distinct_pack(_N_TAXA)


# ---- perf tests ------------------------------------------------------------


def test_perf_hit(large_pack: InMemoryKnowledgeSet) -> None:
    queries = [f"Testus{i}" for i in range(_N_QUERIES)]
    times = _measure(lambda q: resolve_taxon(large_pack, q), queries)
    p50 = sorted(times)[len(times) // 2]
    p95 = _p95(times)
    print(f"\n  hit: p50={p50:.1f}us p95={p95:.1f}us (n={len(times)}, pack={_N_TAXA})")
    assert p95 < _BUDGET_P95_US, f"hit p95={p95:.1f}us exceeds budget {_BUDGET_P95_US:.0f}us"


def test_perf_miss(large_pack: InMemoryKnowledgeSet) -> None:
    queries = [f"NoSuchTaxon{i}" for i in range(_N_QUERIES)]
    times = _measure(lambda q: resolve_taxon(large_pack, q), queries)
    p50 = sorted(times)[len(times) // 2]
    p95 = _p95(times)
    print(f"\n  miss: p50={p50:.1f}us p95={p95:.1f}us (n={len(times)}, pack={_N_TAXA})")
    assert p95 < _BUDGET_P95_US, f"miss p95={p95:.1f}us exceeds budget {_BUDGET_P95_US:.0f}us"


def test_perf_ambiguous_truncated() -> None:
    # 25 taxa sharing one name -> Ambiguous with truncated=True, 20 kept.
    pack = _build_colliding_pack(25)
    queries = ["SharedName"] * _N_QUERIES
    times = _measure(lambda q: resolve_taxon(pack, q), queries)
    p50 = sorted(times)[len(times) // 2]
    p95 = _p95(times)
    print(f"\n  ambiguous-truncated: p50={p50:.1f}us p95={p95:.1f}us (n=25, keep=20)")
    assert p95 < _BUDGET_P95_US, f"ambiguous p95={p95:.1f}us exceeds budget {_BUDGET_P95_US:.0f}us"
    # functional assertion: truncation must have happened and be reported
    r = resolve_taxon(pack, "SharedName")
    assert isinstance(r, Ambiguous)
    assert r.truncated is True
    assert len(r.candidates) == 20
