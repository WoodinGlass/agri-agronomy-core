"""Perf regression: coverage scales linearly with taxon count.

Before the fix, `derive_tier` re-scanned every fact in the pack per taxon,
making `derive_all_tiers` O(n·total_facts) = O(n^2). On a 10k-taxa pack
this took >180 s. After the fix (`ks.facts_for(taxon_id)` with the
existing `_facts_by_taxon` index), it is O(n).

This test builds two packs of different sizes, loads each once, and
times only `derive_all_tiers` (not the pack load). It is NOT a hard
timing budget — the ratio tolerates noise — but a quadratic regression
would push the ratio from ~2x to ~4x and fail the test.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _gen_pack import generate_perf_pack

from agri_core.pack import load_knowledge_set
from agri_core.pack.loader import _default_dictionary
from agri_core.pack.tiers import derive_all_tiers

pytestmark = pytest.mark.perf

_N_SMALL = 500
_N_LARGE = 1_000
_RATIO_MAX = 3.0
"""Upper bound on time(large)/time(small).

Linear scaling would give ~2.0 (2x taxa => 2x time).
Quadratic scaling would give ~4.0.
3.0 gives room for noise while catching a real regression.
"""


def _load_once(path: Path):
    ks = load_knowledge_set(path, allow_synthetic=True)
    return ks, _default_dictionary()


def test_coverage_scaling_is_linear(tmp_path: Path) -> None:
    small = tmp_path / "small"
    large = tmp_path / "large"
    small.mkdir()
    large.mkdir()

    generate_perf_pack(small, n_taxa=_N_SMALL)
    generate_perf_pack(large, n_taxa=_N_LARGE)

    small_ks, dict_small = _load_once(small)
    large_ks, dict_large = _load_once(large)

    # Warmup (first call may include lazy imports / attribute lookups)
    derive_all_tiers(small_ks, dict_small)

    # 3 runs each, take min to reduce noise. Load is out of the timing.
    small_times = []
    for _ in range(3):
        t0 = time.perf_counter()
        derive_all_tiers(small_ks, dict_small)
        small_times.append(time.perf_counter() - t0)

    large_times = []
    for _ in range(3):
        t0 = time.perf_counter()
        derive_all_tiers(large_ks, dict_large)
        large_times.append(time.perf_counter() - t0)

    small_min = min(small_times)
    large_min = min(large_times)
    ratio = large_min / small_min if small_min > 0 else float("inf")

    print(
        f"\n  small ({_N_SMALL} taxa): derive min={small_min * 1000:.1f} ms  "
        f"runs={[f'{t * 1000:.1f}' for t in small_times]}"
    )
    print(
        f"  large ({_N_LARGE} taxa): derive min={large_min * 1000:.1f} ms  "
        f"runs={[f'{t * 1000:.1f}' for t in large_times]}"
    )
    print(f"  ratio: {ratio:.2f}x (threshold {_RATIO_MAX}x)")

    assert ratio < _RATIO_MAX, (
        f"coverage scaling is super-linear: {_N_LARGE} taxa took "
        f"{ratio:.2f}x the time of {_N_SMALL} taxa "
        f"(threshold {_RATIO_MAX}x; linear≈2x, quadratic≈4x). "
        f"Likely regression to O(n·total_facts) in derive_tier."
    )
