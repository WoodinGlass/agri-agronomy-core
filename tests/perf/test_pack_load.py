"""Perf gate: built-pack load in ≤ 1 s, source load as canary.

Measured on Colab-class CPU without tracemalloc on a 10k-taxa pack
(10k taxa, 30k names, 200k facts): min 917 ms, median 1019 ms, max 1602 ms
across 7 runs, post-B1.

The built-load test asserts **min-of-5 ≤ 1000 ms**, which catches a real
regression without flagging single-run CI noise. Median and max are
printed for monitoring. The source-load test is a canary (development
path, ~10x slower, measured ~27 s) with a 40 s ceiling; the real 1 s
budget lives on the built-pack test.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.perf

_BUDGET_BUILT_MS = 1000.0
_BUDGET_SOURCE_MS = 40_000.0
_N_WARMUP = 1
_N_RUNS = 5


def test_built_load_budget(perf_pack: tuple[Path, Path]) -> None:
    _src, built = perf_pack
    for _ in range(_N_WARMUP):
        load_knowledge_set(built, allow_synthetic=True)
    times_ms: list[float] = []
    for _ in range(_N_RUNS):
        t0 = time.perf_counter()
        load_knowledge_set(built, allow_synthetic=True)
        times_ms.append((time.perf_counter() - t0) * 1000.0)
    mn = min(times_ms)
    med = sorted(times_ms)[len(times_ms) // 2]
    mx = max(times_ms)
    print(
        f"\n  built load: min={mn:.1f} ms  median={med:.1f} ms  max={mx:.1f} ms "
        f"(n={len(times_ms)}, budget={_BUDGET_BUILT_MS:.0f} ms)"
    )
    assert mn <= _BUDGET_BUILT_MS, (
        f"built-pack load min {mn:.1f} ms exceeds budget {_BUDGET_BUILT_MS:.0f} ms"
    )


def test_source_load_canary(perf_pack: tuple[Path, Path]) -> None:
    src, _built = perf_pack
    t0 = time.perf_counter()
    load_knowledge_set(src, allow_synthetic=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(f"\n  source load: {elapsed_ms:.0f} ms (canary budget={_BUDGET_SOURCE_MS:.0f} ms)")
    assert elapsed_ms <= _BUDGET_SOURCE_MS, (
        f"source-pack load {elapsed_ms:.0f} ms exceeds canary budget {_BUDGET_SOURCE_MS:.0f} ms"
    )
