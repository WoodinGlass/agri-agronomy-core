"""Perf gate: peak memory during built-pack load ≤ 200 MB.

The measurement runs in a fresh subprocess with tracemalloc enabled, so
that the parent pytest process and its fixtures do not contaminate the
peak. tracemalloc slows the load by ~10x; that is acceptable because
this test only asserts memory, not time.

The probe is portable: it does not hardcode a repo path. It relies on
``PYTHONPATH`` propagation from the parent so that in Colab (editable
install) and in CI (pip install .) the same ``agri_core`` package is
imported.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="tracemalloc peak is unreliable on Windows CI",
    ),
]

_BUDGET_PEAK_MB = 200.0
_REPO_SRC = Path(__file__).resolve().parents[2] / "src"

_PROBE = """
import json, sys, tracemalloc
from pathlib import Path
from agri_core.pack import load_knowledge_set

tracemalloc.start(10)
ks = load_knowledge_set(Path(sys.argv[1]), allow_synthetic=True)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(json.dumps({
    "peak_mb": peak / 1024 / 1024,
    "taxa": sum(1 for _ in ks.taxa()),
}))
"""


def test_built_load_peak_memory(perf_pack: tuple[Path, Path]) -> None:
    _src, built = perf_pack

    env = {**os.environ}
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_REPO_SRC}{os.pathsep}{existing}" if existing else str(_REPO_SRC)

    r = subprocess.run(
        [sys.executable, "-c", _PROBE, str(built)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if r.returncode != 0:
        pytest.fail(
            f"subprocess failed (rc={r.returncode}):\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    data = json.loads(r.stdout.strip().splitlines()[-1])
    print(
        f"\n  built load peak: {data['peak_mb']:.1f} MB "
        f"(taxa={data['taxa']}, budget={_BUDGET_PEAK_MB:.0f} MB)"
    )
    assert data["taxa"] == 10_000, f"expected 10k taxa, got {data['taxa']}"
    assert data["peak_mb"] <= _BUDGET_PEAK_MB, (
        f"peak {data['peak_mb']:.1f} MB exceeds budget {_BUDGET_PEAK_MB:.0f} MB"
    )
