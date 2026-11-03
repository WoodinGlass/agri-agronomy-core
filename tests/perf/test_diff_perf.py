"""Perf gate: `agri-core diff --json` on a 10k-taxa BUILT pack (self-diff).

Budget: 36 s.

Compares the built pack against itself (no differences), which still
exercises the full diff pipeline: both packs are loaded, indices are
built, rows are compared. `--json` keeps output to one blob.

Measured on Colab-class CPU: 24.1 s (min of 2). Two `load_knowledge_set`
calls on the built pack plus diff compute. See ADR-010.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf

_BUDGET_MS = 36_000.0


def test_diff_budget(perf_pack: tuple[Path, Path]) -> None:
    _src, built = perf_pack

    t0 = time.perf_counter()
    r = subprocess.run(
        [
            "agri-core",
            "diff",
            "--old",
            str(built),
            "--new",
            str(built),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n  diff: {elapsed_ms:.0f} ms (budget={_BUDGET_MS:.0f} ms)")

    if r.returncode != 0:
        pytest.fail(
            f"agri-core diff failed (rc={r.returncode}):\n"
            f"stdout:\n{r.stdout[-1000:]}\nstderr:\n{r.stderr[-1000:]}"
        )

    assert elapsed_ms <= _BUDGET_MS, f"diff {elapsed_ms:.0f} ms exceeds budget {_BUDGET_MS:.0f} ms"
