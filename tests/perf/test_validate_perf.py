"""Perf gate: `agri-core validate --strict` on a 10k-taxa SOURCE pack.

Budget: 70 s.

Target is the source tree, not the built pack: `validate` expects
source CSVs (`taxa.csv`, `facts/*.csv`, etc.). A built pack contains
`pack.sqlite` only and `validate` rejects it by design
(`PACK_INVALID: required file missing: taxa.csv`). Built-pack load
correctness is covered by `test_built_load_budget`.

Measured on Colab-class CPU: 47 s (min of 2). Budget is ~1.5x that.
See ADR-010.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf

_BUDGET_MS = 70_000.0


def test_validate_budget(perf_pack: tuple[Path, Path]) -> None:
    src, _built = perf_pack

    t0 = time.perf_counter()
    r = subprocess.run(
        ["agri-core", "validate", "--pack", str(src), "--strict"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n  validate: {elapsed_ms:.0f} ms (budget={_BUDGET_MS:.0f} ms)")

    if r.returncode != 0:
        pytest.fail(
            f"agri-core validate failed (rc={r.returncode}):\n"
            f"stdout:\n{r.stdout[-1000:]}\nstderr:\n{r.stderr[-1000:]}"
        )

    assert elapsed_ms <= _BUDGET_MS, (
        f"validate {elapsed_ms:.0f} ms exceeds budget {_BUDGET_MS:.0f} ms"
    )
