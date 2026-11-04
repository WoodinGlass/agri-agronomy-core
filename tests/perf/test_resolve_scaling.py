"""Multi-scale performance for ``resolve_taxon`` and ``resolve_fact`` (G14).

The existing ``test_resolve_taxon_perf.py`` and ``test_resolve_fact_perf.py``
verify absolute budgets at N=10,000 and N=5,000. They do NOT verify
**scaling**: an O(n) regression that stayed under the absolute budget at
N=10k would slip through. This test closes that gap.

Three scales (1k, 10k, 100k) with the ratio of the largest to the
smallest serving as the scaling signal:

- O(1) lookup → ratio ≈ 1x (plus noise);
- O(log n) → ratio ≈ 1.7x (log10(100k)/log10(1k));
- O(n) → ratio ≈ 100x.

The thresholds (3.0x for ``resolve_taxon``, 4.0x for ``resolve_fact``)
catch an O(n) or O(n log n) regression while tolerating cache-miss noise
at 100k (measured baseline: `resolve_taxon` max/min ratio ≈ 1.16x,
`resolve_fact` ≈ 2.55x; the 4.0x for `resolve_fact` accommodates its
expected cache-miss growth, which is not a bug).

No 1M scale. A 1M-taxa pack takes ~100 s to build and ~4 GB RAM; that is
not feasible for a test that runs on every PR. The 100x span from 1k to
100k is enough to distinguish O(1) from O(n); an O(n) regression would
already push the ratio far past 3x at 100k.

Run with ``pytest -m perf --no-cov`` (perf tests skip when coverage is
active, see ``tests/perf/conftest.py``).
"""

from __future__ import annotations

import statistics
import time
from datetime import date
from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow, ScalarValue
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.registry import resolve_fact, resolve_taxon

pytestmark = pytest.mark.perf

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

_SCALES = (1_000, 10_000, 100_000)
_N_QUERIES_PER_SCALE = 300
_N_BATCHES = 3
_WARMUP = 20

_TAXON_RATIO_MAX = 3.0
_FACT_RATIO_MAX = 4.0


# ---- helpers ----------------------------------------------------------------


def _manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "scaling",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _build_pack(n: int) -> InMemoryKnowledgeSet:
    """One taxon per fact, one fact per taxon, distinct IDs at every scale."""
    taxa = [
        TaxonRow(
            taxon_id=f"T{i:09d}",
            rank="species",
            scientific_name=f"Testus species{i:09d}",
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


def _measure_taxon(pack: InMemoryKnowledgeSet, n: int) -> float:
    """Return median p50 of ``_N_BATCHES`` batches of ``resolve_taxon`` calls."""
    step = max(1, n // _N_QUERIES_PER_SCALE)
    samples = list(range(0, n, step))[:_N_QUERIES_PER_SCALE]
    for i in samples[:_WARMUP]:
        resolve_taxon(pack, f"Testus species{i:09d}")
    batch_medians: list[float] = []
    for _ in range(_N_BATCHES):
        times: list[float] = []
        for i in samples:
            t0 = time.perf_counter()
            resolve_taxon(pack, f"Testus species{i:09d}")
            times.append(time.perf_counter() - t0)
        batch_medians.append(statistics.median(times))
    return statistics.median(batch_medians)


def _measure_fact(pack: InMemoryKnowledgeSet, n: int) -> float:
    """Return median p50 of ``_N_BATCHES`` batches of ``resolve_fact`` calls."""
    step = max(1, n // _N_QUERIES_PER_SCALE)
    samples = list(range(0, n, step))[:_N_QUERIES_PER_SCALE]
    for i in samples[:_WARMUP]:
        resolve_fact(pack, f"T{i:09d}", "soil_ph")
    batch_medians: list[float] = []
    for _ in range(_N_BATCHES):
        times: list[float] = []
        for i in samples:
            t0 = time.perf_counter()
            resolve_fact(pack, f"T{i:09d}", "soil_ph")
            times.append(time.perf_counter() - t0)
        batch_medians.append(statistics.median(times))
    return statistics.median(batch_medians)


# ---- scaling tests ----------------------------------------------------------


def test_resolve_taxon_scales_constant() -> None:
    """``resolve_taxon`` p50 must not grow with pack size (O(1) lookup).

    Measured baseline on a Colab-class CPU: p50 ≈ 11-13 µs at every scale
    (100 → 100k). Ratio max/min ≈ 1.16x. Threshold 3.0x catches an O(n)
    regression (which would push the 100k/1k ratio to ~100x) without
    flagging cache-miss noise.
    """
    medians_us: dict[int, float] = {}
    for n in _SCALES:
        pack = _build_pack(n)
        medians_us[n] = _measure_taxon(pack, n) * 1_000_000.0

    small = medians_us[_SCALES[0]]
    large = medians_us[_SCALES[-1]]
    ratio = large / small if small > 0 else float("inf")
    print(
        "\n  resolve_taxon p50 (µs): "
        + ", ".join(f"N={n}: {medians_us[n]:.1f}" for n in _SCALES)
        + f"  ratio={ratio:.2f}x (threshold {_TAXON_RATIO_MAX}x)"
    )
    assert ratio <= _TAXON_RATIO_MAX, (
        f"resolve_taxon scales super-constantly: N={_SCALES[-1]} took "
        f"{ratio:.2f}x the time of N={_SCALES[0]} (threshold "
        f"{_TAXON_RATIO_MAX}x). O(1) baseline ≈ 1x; O(n) would be ~100x. "
        f"Likely a regression to linear scan of the name index."
    )


def test_resolve_fact_scales_near_constant() -> None:
    """``resolve_fact`` p50 must not grow linearly with pack size.

    ``resolve_fact`` does pay a cache-miss cost at 100k (facts index
    spills L2/L3), measured ratio ≈ 2.55x from 1k to 100k. That is
    near-constant — far below the 100x an O(n) regression would produce.
    Threshold 4.0x accommodates the cache effect while catching an O(n)
    or O(n log n) regression.
    """
    medians_us: dict[int, float] = {}
    for n in _SCALES:
        pack = _build_pack(n)
        medians_us[n] = _measure_fact(pack, n) * 1_000_000.0

    small = medians_us[_SCALES[0]]
    large = medians_us[_SCALES[-1]]
    ratio = large / small if small > 0 else float("inf")
    print(
        "\n  resolve_fact p50 (µs): "
        + ", ".join(f"N={n}: {medians_us[n]:.1f}" for n in _SCALES)
        + f"  ratio={ratio:.2f}x (threshold {_FACT_RATIO_MAX}x)"
    )
    assert ratio <= _FACT_RATIO_MAX, (
        f"resolve_fact scales super-linearly: N={_SCALES[-1]} took "
        f"{ratio:.2f}x the time of N={_SCALES[0]} (threshold "
        f"{_FACT_RATIO_MAX}x). Near-constant baseline ≈ 1-3x; O(n) would "
        f"be ~100x. Likely a regression to linear scan of the fact index."
    )
