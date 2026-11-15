"""Perf gate: native `hash_pack_files` is <=0.5x pure-Python on a 10k pack.

Gate per ADR-019 amendment 2026-11-15 (Phase B).
Runs with `pytest -m perf --no-cov`; skipped under coverage (see
tests/perf/conftest.py).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agri_core.pack.files import read_pack_bytes
from agri_core.pack.verify import _hash_pack_files_py

try:
    from agri_core import _native

    _NATIVE_AVAILABLE = hasattr(_native, "hash_pack_files")
except ImportError:
    _native = None  # type: ignore[assignment]
    _NATIVE_AVAILABLE = False

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native.hash_pack_files not built"),
    # ADR-019 stop-loss (Phase B, 2026-11-15): native measured 1.86x
    # pure-Python on the 10k pack. Root cause: rustcrypto `sha2 0.11`
    # ~2.0x slower than OpenSSL `hashlib` on CPUs without SHA-NI.
    # Follow-up under M21.5: swap SHA-256 crate + Rayon per-file.
    # strict=False: XPASS is reported (not failed) when native improves.
    pytest.mark.xfail(
        strict=False,
        reason=(
            "native hash_pack_files is 1.86x pure-Python on the 10k "
            "reference pack (SHA-256 crate bottleneck, no SHA-NI on "
            "runner); see ADR-019 amendment 2026-11-15 §9"
        ),
    ),
]

_REPO = Path(__file__).resolve().parents[2]


def _min_seconds(fn, repeats: int = 3) -> float:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def test_native_hash_pack_files_is_at_most_half_python(perf_pack: tuple[Path, Path]) -> None:
    src, _built = perf_pack
    files = dict(read_pack_bytes(src))
    alg = "rfc8785"

    # Warmup (touch OS caches, jit-like effects if any)
    _hash_pack_files_py(files, hash_alg=alg)
    _native.hash_pack_files(files, hash_alg=alg)  # type: ignore[union-attr]

    py = _min_seconds(lambda: _hash_pack_files_py(files, hash_alg=alg))
    native = _min_seconds(
        lambda: _native.hash_pack_files(files, hash_alg=alg)  # type: ignore[union-attr]
    )
    ratio = native / py
    print(
        f"\n  hash_pack_files 10k pack ({len(files)} files):"
        f"\n    python: {py * 1000:.1f} ms"
        f"\n    native: {native * 1000:.1f} ms"
        f"\n    ratio:  {ratio:.2f}  (gate ≤0.50)"
    )
    assert ratio <= 0.5, (
        f"native hash_pack_files {ratio:.2f}x Python (gate ≤0.5x); "
        "stop-loss: keep Python default, drop native"
    )
