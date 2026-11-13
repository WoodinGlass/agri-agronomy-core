"""Parity test: native Rust kernel vs Python implementation (ADR-019 M20a).

Skipped when `agri_core._native` is not built (e.g. dev without maturin).
"""
from __future__ import annotations

import pytest

from agri_core.models.canonical import canonical_json as py_canonical_json

pytestmark = pytest.mark.contract

try:
    from agri_core import _native  # type: ignore[attr-defined]
    _NATIVE_AVAILABLE = True
except ImportError:
    _native = None  # type: ignore[assignment]
    _NATIVE_AVAILABLE = False


@pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native not built")
def test_canonical_json_byte_identical_golden() -> None:
    cases = [
        {},
        [],
        {"b": 2, "a": 1, "c": [3, 1, 2]},
        {"v": 1.0, "w": 1.5, "z": 0.0},
        {"v": -0.0},
        {"n": "tomato", "id": "ID"},
        {"nested": {"x": [1, 2, 3]}, "y": "v"},
    ]
    for case in cases:
        py = py_canonical_json(case)
        rust = _native.canonical_json(case)  # type: ignore[union-attr]
        assert py == rust, f"divergence on {case!r}: py={py!r} rust={rust!r}"


@pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native not built")
def test_canonical_json_hypothesis() -> None:
    from hypothesis import given, strategies as st

    scalar = st.one_of(
        st.none(), st.booleans(),
        st.integers(min_value=-10**6, max_value=10**6),
        st.floats(allow_nan=False, allow_infinity=False, width=64),
        st.text(max_size=20),
    )
    value = st.recursive(
        scalar,
        lambda c: st.one_of(st.lists(c, max_size=4), st.dictionaries(st.text(max_size=8), c, max_size=4)),
        max_leaves=20,
    )

    @given(value)
    def _check(v: object) -> None:
        py = py_canonical_json(v)
        rust = _native.canonical_json(v)  # type: ignore[union-attr]
        assert py == rust

    _check()


@pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native not built")
def test_sha256_hex_parity() -> None:
    import hashlib
    for data in [b"", b"hello", b"a"*1000, bytes(range(256))]:
        py = hashlib.sha256(data).hexdigest()
        rust = _native.sha256_hex(data)  # type: ignore[union-attr]
        assert py == rust
