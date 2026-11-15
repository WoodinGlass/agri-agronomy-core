"""Parity: native `hash_pack_files` vs pure-Python `_hash_pack_files_py`.

Gate per ADR-019 amendment 2026-11-15:
- sample pack: byte-identical for both hash_alg values
- 10k synthetic pack: byte-identical for both hash_alg values
- Hypothesis differential fuzz: 1000 examples (small mappings)
- `meta().backends["hash_pack_files"]` reports "python" (ADR-019
  stop-loss; see amendment 2026-11-15 §9)

The 10k pack is generated once per test session via
`tests/perf/_gen_pack.py::generate_perf_pack` and cached in a module-scoped
fixture. Cost ~5s generation + ~2s hash, acceptable inside the PR run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agri_core.pack.files import read_pack_bytes
from agri_core.pack.verify import _hash_pack_files_py, hash_pack_files

# Import _gen_pack as a plain module (tests/perf is not a package).
_PERF = Path(__file__).resolve().parents[1] / "perf"
if str(_PERF) not in sys.path:
    sys.path.insert(0, str(_PERF))

try:
    from agri_core import _native

    _NATIVE_AVAILABLE = hasattr(_native, "hash_pack_files")
except ImportError:
    _native = None  # type: ignore[assignment]
    _NATIVE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _NATIVE_AVAILABLE, reason="agri_core._native.hash_pack_files not built"
)

_SAMPLE = Path(__file__).resolve().parents[2] / "src" / "agri_core" / "_samples" / "sample_pack"
_SAMPLE_CONTENT_HASH = "sha256:4ca67c008ae0abbc1218b16f570770bdc00069a686d5dee2c0154e03b08204f1"


@pytest.fixture(scope="module")
def pack_10k() -> dict[str, bytes]:
    """10k synthetic pack as a files mapping (session-scoped)."""
    import tempfile

    from _gen_pack import generate_perf_pack  # type: ignore[import-not-found]

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "source"
        generate_perf_pack(src, n_taxa=10_000)
        return dict(read_pack_bytes(src))


# ---------------------------------------------------------------------------
# Sample pack
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hash_alg", ["pre-rfc8785", "rfc8785"])
def test_sample_pack_parity(hash_alg: str) -> None:
    files = dict(read_pack_bytes(_SAMPLE))
    py = _hash_pack_files_py(files, hash_alg=hash_alg)
    native = _native.hash_pack_files(files, hash_alg=hash_alg)  # type: ignore[union-attr]
    assert py == native
    assert py == _SAMPLE_CONTENT_HASH  # external KAT


# ---------------------------------------------------------------------------
# 10k synthetic pack
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hash_alg", ["pre-rfc8785", "rfc8785"])
def test_10k_pack_parity(pack_10k: dict[str, bytes], hash_alg: str) -> None:
    py = _hash_pack_files_py(pack_10k, hash_alg=hash_alg)
    native = _native.hash_pack_files(pack_10k, hash_alg=hash_alg)  # type: ignore[union-attr]
    assert py == native
    assert py.startswith("sha256:")
    assert len(py) == len("sha256:") + 64


# ---------------------------------------------------------------------------
# Hypothesis differential fuzz
# ---------------------------------------------------------------------------


def test_hypothesis_small_mappings() -> None:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    # Values that round-trip through Rust `toml::Value`: strings, ints,
    # booleans, nested arrays of scalars. Floats are supported but cause
    # TOML/JSON number-format churn; leave them out of the fuzz (covered
    # by the vectors).
    # Alphabet: printable-only. Excludes:
    #   Cs (surrogate), Cc (control incl \x00-\x1f, \x7f),
    #   Cf (format incl bidi/zero-width), Cn (unassigned),
    #   Co (private use), Zl (line sep), Zp (paragraph sep).
    # Leaves: letters, marks, numbers, punctuation, symbols, Zs (space).
    # All safe for TOML basic strings when JSON-escaped with
    # ensure_ascii=False. The property under test is canonicalization
    # parity, not TOML encoding; problematic code points belong in the
    # fixed vectors (which cover surrogate rejection separately), not
    # in the fuzz corpus.
    _SAFE_CATEGORIES = (
        "Lu",
        "Ll",
        "Lt",
        "Lm",
        "Lo",
        "Mn",
        "Mc",
        "Me",
        "Nd",
        "Nl",
        "No",
        "Pc",
        "Pd",
        "Ps",
        "Pe",
        "Pi",
        "Pf",
        "Po",
        "Sm",
        "Sc",
        "Sk",
        "So",
        "Zs",
    )
    _RESERVED_TOML_KEYS = frozenset(
        {
            "name",
            "version",
            "schema_version",
            "engine_min",
            "dictionary_min",
        }
    )
    scalar = st.one_of(
        st.text(
            min_size=0,
            max_size=20,
            alphabet=st.characters(whitelist_categories=_SAFE_CATEGORIES),
        ),
        st.integers(min_value=-(10**9), max_value=10**9),
        st.booleans(),
    )
    value = st.recursive(
        scalar,
        lambda c: st.one_of(
            st.lists(c, min_size=0, max_size=3),
            st.dictionaries(
                st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,15}", fullmatch=True),
                c,
                min_size=0,
                max_size=3,
            ),
        ),
        max_leaves=8,
    )

    name_st = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz-_",
        min_size=1,
        max_size=12,
    )
    # `extra` must not collide with the hardcoded reserved keys above:
    # duplicate TOML keys are invalid per TOML spec, and `_pack_toml_content`
    # correctly rejects them. Filter them out of the key strategy so the
    # fuzz exercises canonicalization parity, not TOML parse rejection.
    extra_key_st = name_st.filter(lambda k: k not in _RESERVED_TOML_KEYS)

    @given(
        name=name_st,
        version=st.from_regex(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}", fullmatch=True),
        extra=st.dictionaries(extra_key_st, value, min_size=0, max_size=3),
        hash_alg=st.sampled_from(["pre-rfc8785", "rfc8785"]),
    )
    @settings(max_examples=1000, deadline=None)
    def _check(
        name: str,
        version: str,
        extra: dict,
        hash_alg: str,
    ) -> None:
        import json as _json

        # Build a pack.toml via json.dumps then a tiny TOML serializer
        # restricted to string/int/bool/array/nested-table. Enough for
        # the fuzz; canonicalization is the property under test.
        def to_toml(v) -> str:
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, int):
                return str(v)
            if isinstance(v, str):
                # ensure_ascii=False: TOML treats non-BMP chars as UTF-8
                # literal, not `\uXXXX` JSON escapes. json.dumps with
                # ensure_ascii=True would emit surrogate pairs that
                # tomllib rejects.
                return _json.dumps(v, ensure_ascii=False)
            if isinstance(v, list):
                return "[" + ", ".join(to_toml(x) for x in v) + "]"
            if isinstance(v, dict):
                # inline table
                return "{" + ", ".join(f"{k} = {to_toml(x)}" for k, x in v.items()) + "}"
            raise TypeError(type(v))

        lines = [
            f'name = "{name}"',
            f'version = "{version}"',
            "schema_version = 1",
            'engine_min = "0.0.0"',
            'dictionary_min = "1.0.0"',
        ]
        for k, v in extra.items():
            lines.append(f"{k} = {to_toml(v)}")
        pack_toml = ("\n".join(lines) + "\n").encode()
        files = {"pack.toml": pack_toml, "sources.csv": b""}

        py = _hash_pack_files_py(files, hash_alg=hash_alg)
        native = _native.hash_pack_files(files, hash_alg=hash_alg)  # type: ignore[union-attr]
        assert py == native, f"divergence: files={files!r} hash_alg={hash_alg}"

    _check()


# ---------------------------------------------------------------------------
# meta().backends reflects the actual backend
# ---------------------------------------------------------------------------


def test_meta_backends_reports_python_stop_loss() -> None:
    """ADR-019 stop-loss (Phase B): backends report "python" even with native.

    Native is importable as `_native.hash_pack_files` for opt-in
    benchmarks; the public wrapper uses pure Python until the 0.5x
    gate passes (see ADR-019 amendment 2026-11-15 §9).
    """
    from agri_core.pack.loader import load_knowledge_set
    from agri_core.registry import meta

    ks = load_knowledge_set(_SAMPLE, allow_synthetic=True)
    m = meta(ks)
    # A1b stop-loss (ADR-019 §5, §10): all three A1b backends report "python"
    # even though native impl is available. Native is opt-in via
    # `_native.build_sqlite_bytes` / `_native.validate_pack_findings`.
    assert m.backends["hash_pack_files"] == "python"
    assert m.backends["build_pack"] == "python"
    assert m.backends["validate_pack"] == "python"


def test_public_and_native_hash_match_stop_loss() -> None:
    """Public wrapper (pure Python) matches direct native call byte-for-byte.

    ADR-019 stop-loss (Phase B): the public wrapper uses pure Python;
    native remains importable as `_native.hash_pack_files` for opt-in
    benchmarks. Both produce identical `sha256:` output (parity KAT).
    """
    files = dict(read_pack_bytes(_SAMPLE))
    direct = _native.hash_pack_files(files, hash_alg="rfc8785")  # type: ignore[union-attr]
    public = hash_pack_files(files, hash_alg="rfc8785")
    assert public == direct
