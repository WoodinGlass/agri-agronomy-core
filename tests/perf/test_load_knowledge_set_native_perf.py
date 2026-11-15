"""Perf gate: native load_knowledge_set ≤0.5x Python (ADR-019 §11.9).

Gate per ADR-019 §11.9: ``load_knowledge_set(built)`` ≤0.5x Python
``SQLiteKnowledgeSet._build``.

Runs with ``pytest -m perf --no-cov``; skipped under coverage (see
``tests/perf/conftest.py``).

Status: **xfail** (per ADR-019 §11.9 monitor mode + §5 stop-loss spirit).
The M21 tag gate is content_hash + error-code parity (§11.10), not perf.
This test is a nightly monitor; XPASS reports when the ≤0.5x budget
passes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from agri_core.pack import load_knowledge_set

try:
    from agri_core import _native

    _NATIVE_AVAILABLE = hasattr(_native, "load_built_pack_native")
except ImportError:
    _native = None  # type: ignore[assignment]
    _NATIVE_AVAILABLE = False

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(
        not _NATIVE_AVAILABLE,
        reason="agri_core._native.load_built_pack_native not built",
    ),
    pytest.mark.xfail(
        strict=False,
        reason=(
            "native load_knowledge_set gate ≤0.5x Python is monitored in "
            "nightly CI per ADR-019 §11.9; XPASS reports improvement. "
            "M21 tag gate is content_hash + error-code parity, not perf."
        ),
    ),
]


def _min_seconds(fn: Callable[[], object], repeats: int = 3) -> float:
    times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def test_native_load_is_at_most_half_python(
    perf_pack: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _src, built = perf_pack

    # Warmup both paths (populate OS caches, JIT-like effects)
    monkeypatch.setattr("agri_core.pack.loader._NATIVE_LOAD", False)
    load_knowledge_set(built, allow_synthetic=True)
    monkeypatch.setattr("agri_core.pack.loader._NATIVE_LOAD", True)
    load_knowledge_set(built, allow_synthetic=True)

    # Python baseline
    monkeypatch.setattr("agri_core.pack.loader._NATIVE_LOAD", False)
    py = _min_seconds(lambda: load_knowledge_set(built, allow_synthetic=True))

    # Native
    monkeypatch.setattr("agri_core.pack.loader._NATIVE_LOAD", True)
    native = _min_seconds(lambda: load_knowledge_set(built, allow_synthetic=True))

    ratio = native / py
    print(
        f"\n  load_knowledge_set 10k built pack:"
        f"\n    python: {py * 1000:.1f} ms"
        f"\n    native: {native * 1000:.1f} ms"
        f"\n    ratio:  {ratio:.2f}  (gate ≤0.50)"
    )
    assert ratio <= 0.5, (
        f"native load {ratio:.2f}x Python (gate ≤0.5x); stop-loss: keep Python default, drop native"
    )
