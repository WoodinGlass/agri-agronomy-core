"""Perf gate: `agri-core coverage --json` on a 10k-taxa BUILT pack.

Budget: 27 s.

Uses `--json` so output is a single blob rather than 10k per-taxon
echo lines; the text path adds ~1 s of pipe I/O overhead on 10k taxa,
which would blur the measurement. The underlying compute is identical.

`coverage` on a built pack includes one `load_knowledge_set` (built
SQLite, ~1 s) plus `derive_all_tiers` (~0.7 s in-process on 10k taxa
after the O(n) fix in #131). The remaining ~15 s of the measured 17 s
is process startup + imports. See ADR-010.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf

_BUDGET_MS = 27_000.0


def test_coverage_budget(perf_pack: tuple[Path, Path]) -> None:
    _src, built = perf_pack

    t0 = time.perf_counter()
    r = subprocess.run(
        ["agri-core", "coverage", "--pack", str(built), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n  coverage: {elapsed_ms:.0f} ms (budget={_BUDGET_MS:.0f} ms)")

    if r.returncode != 0:
        pytest.fail(
            f"agri-core coverage failed (rc={r.returncode}):\n"
            f"stdout:\n{r.stdout[-1000:]}\nstderr:\n{r.stderr[-1000:]}"
        )

    # Sanity: parse JSON, confirm all 10k taxa are accounted for.
    payload = json.loads(r.stdout)
    assert "summary" in payload, "coverage --json missing 'summary'"
    assert set(payload["summary"].keys()) == {"T0", "T1", "T2", "T3"}
    total = sum(payload["summary"].values())
    assert total == 10_000, f"expected 10k taxa in summary, got {total}"

    assert elapsed_ms <= _BUDGET_MS, (
        f"coverage {elapsed_ms:.0f} ms exceeds budget {_BUDGET_MS:.0f} ms"
    )
