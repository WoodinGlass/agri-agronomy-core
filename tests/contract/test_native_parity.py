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
    from hypothesis import given
    from hypothesis import strategies as st

    scalar = st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(10**6), max_value=10**6),
        st.floats(allow_nan=False, allow_infinity=False, width=64),
        st.text(max_size=20),
    )
    value = st.recursive(
        scalar,
        lambda c: st.one_of(
            st.lists(c, max_size=4),
            st.dictionaries(st.text(max_size=8), c, max_size=4),
        ),
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

    for data in [b"", b"hello", b"a" * 1000, bytes(range(256))]:
        py = hashlib.sha256(data).hexdigest()
        rust = _native.sha256_hex(data)  # type: ignore[union-attr]
        assert py == rust


# ---------------------------------------------------------------------------
# RFC 8785 parity (A1b)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native not built")
def test_canonical_json_rfc8785_parity_golden() -> None:
    from agri_core.models.canonical import canonical_json_rfc8785 as py_rfc8785

    cases = [
        {},
        [],
        {"b": 2, "a": 1, "c": [3, 1, 2]},
        {"v": 1.0},
        {"v": -0.0},
        {"v": 1.5},
        {"v": 1e-7},
        {"v": 1e16},
        {"v": 1e20},
        {"v": 1e21},
        {"v": 5e-324},
        {"v": 1.7976931348623157e308},
        {"v": 2**53 - 1},
        {"v": 2**53},
        {"n": "tomato", "id": "ID"},
        {"nested": {"x": [1, 2, 3]}, "y": "v"},
        {"\ufffd": 1, "\U00010000": 2},  # UTF-16 order vs code point order
        {"unicode": "caf\u00e9"},
        {"emoji": "\U0001f600"},
        # Even tiebreak (ECMA-262 s7.1.12.1)
        {"v": 70368744177664.125},
        {"v": 1125899906842624.2},
        {"v": -70368744177664.125},
    ]
    for case in cases:
        py_out = py_rfc8785(case)
        rust_out = _native.canonical_json_rfc8785(case)  # type: ignore[union-attr]
        assert py_out == rust_out, f"divergence on {case!r}: py={py_out!r} rust={rust_out!r}"


@pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native not built")
def test_canonical_json_rfc8785_parity_hypothesis() -> None:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    from agri_core.models.canonical import canonical_json_rfc8785 as py_rfc8785

    scalar = st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1),
        st.floats(allow_nan=False, allow_infinity=False, width=64),
        st.text(max_size=20),
    )
    value = st.recursive(
        scalar,
        lambda c: st.one_of(
            st.lists(c, max_size=4),
            st.dictionaries(st.text(max_size=8), c, max_size=4),
        ),
        max_leaves=20,
    )

    @given(value)
    @settings(max_examples=1000)
    def _check(v: object) -> None:
        py_out = py_rfc8785(v)
        rust_out = _native.canonical_json_rfc8785(v)  # type: ignore[union-attr]
        assert py_out == rust_out, f"divergence on {v!r}"

    _check()


# ---------------------------------------------------------------------------
# request_id parity (A2: Python envelope + Rust use RFC 8785)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _NATIVE_AVAILABLE, reason="agri_core._native not built")
def test_compute_request_id_parity() -> None:
    from agri_core import __version__
    from agri_core.models.envelope import Subject
    from agri_core.models.envelope import compute_request_id as py_rid

    cases = [
        (None, {"x": 1.0}),
        (
            Subject(taxon_id="T000000001", calculation="vpd", calculation_version="0.1.0"),
            {"temp": 20.0, "rh": 60.0},
        ),
        (
            Subject(taxon_id="T000000001", calculation="gdd", calculation_version="0.1.0"),
            {"tmin": 10.0, "tmax": 25.0},
        ),
    ]
    pack_hash = "sha256:" + "0" * 64
    for subj, inp in cases:
        py_out = py_rid(subject=subj, inputs=inp, pack_hash=pack_hash)
        subj_json = subj.model_dump(mode="json") if subj is not None else None
        rust_out = _native.compute_request_id(  # type: ignore[union-attr]
            subj_json, inp, __version__, pack_hash
        )
        assert py_out == rust_out, f"divergence: py={py_out} rust={rust_out}"
