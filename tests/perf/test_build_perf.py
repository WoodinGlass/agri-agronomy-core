"""Perf gate: `agri-core pack build` on a 10k-taxa source pack.

Budget: 160 s.

Measured on Colab-class CPU (shared, throttled) on a 10k-taxa /
320k-fact synthetic pack (v1.2.0 dictionary, M15): 128.2 s (single
run). Budget is ~25% headroom over that, to allow for CI variance
and slower-than-usual runners.

This is a CLI smoke test, not an algorithm measurement. The budget
includes process startup, Python imports, and pack I/O. It catches
catastrophic regressions (>= 3x), not 20% drift. For in-process
algorithm perf, see `test_built_load_budget` and
`test_coverage_scaling`. See ADR-010.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf

_BUDGET_MS = 160_000.0


def test_build_budget(perf_pack: tuple[Path, Path], tmp_path: Path) -> None:
    src, _built = perf_pack
    out = tmp_path / "out"
    out.mkdir()

    t0 = time.perf_counter()
    r = subprocess.run(
        ["agri-core", "pack", "build", "--pack", str(src), "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n  build: {elapsed_ms:.0f} ms (budget={_BUDGET_MS:.0f} ms)")

    if r.returncode != 0:
        pytest.fail(
            f"agri-core pack build failed (rc={r.returncode}):\n"
            f"stdout:\n{r.stdout[-1000:]}\nstderr:\n{r.stderr[-1000:]}"
        )

    assert (out / "pack.sqlite").exists(), "build did not produce pack.sqlite"
    assert elapsed_ms <= _BUDGET_MS, f"build {elapsed_ms:.0f} ms exceeds budget {_BUDGET_MS:.0f} ms"
