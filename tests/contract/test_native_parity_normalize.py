"""Version-aware native/Python parity for normalize (ADR-019 §11.2, §11.14).

Native is authoritative (Unicode 16.0). Python is checked only for
codepoints assigned in the running interpreter's Unicode version;
unassigned codepoints (`unicodedata.category(chr(cp)) == "Cn"`) are
skipped because their behavior is not a contract until assigned
(Unicode stability policy).

Golden files are generated from Python 3.14.9 / Unicode 16.0.0 by
`scripts/gen_normalize_vectors.py`; see `tests/vectors/UNICODE_VERSION.md`.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from agri_core.pack.normalize import normalize_name, normalize_scope_value

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_VECTORS = _REPO / "tests" / "vectors"

try:
    from agri_core import _native

    _NATIVE_HAS_NORMALIZE = hasattr(_native, "normalize_name")
except ImportError:
    _native = None  # type: ignore[assignment]
    _NATIVE_HAS_NORMALIZE = False

_SKIP_NATIVE = pytest.mark.skipif(
    not _NATIVE_HAS_NORMALIZE,
    reason="native normalize_name not exported (rebuild with pip install -e .)",
)


def _load(golden_file: str) -> dict:
    p = _VECTORS / golden_file
    assert p.exists(), f"golden file missing: {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == "16.0.0", f"{golden_file}: version={data['version']}, expected 16.0.0"
    return data


def _golden_map(data: dict) -> dict[int, str]:
    return {int(e["cp"].replace("U+", ""), 16): e["expected"] for e in data["entries"]}


@_SKIP_NATIVE
@pytest.mark.parametrize(
    ("golden_file", "fn_name"),
    [
        ("normalize_name_16_0.json", "normalize_name"),
        ("normalize_scope_value_16_0.json", "normalize_scope_value"),
    ],
)
def test_native_matches_16_0_golden(golden_file: str, fn_name: str) -> None:
    """Native must match the pinned 16.0.0 oracle bit-for-bit for every entry."""
    data = _load(golden_file)
    native_fn = getattr(_native, fn_name)
    failures = []
    for entry in data["entries"]:
        got = native_fn(entry["input"])
        if got != entry["expected"]:
            failures.append((entry["cp"], entry["expected"], got))
            if len(failures) >= 20:
                break
    assert not failures, (
        f"{len(failures)} native mismatches in {golden_file}; first: {failures[:5]}"
    )


@pytest.mark.parametrize(
    ("golden_file", "py_fn"),
    [
        ("normalize_name_16_0.json", normalize_name),
        ("normalize_scope_value_16_0.json", normalize_scope_value),
    ],
)
def test_python_version_aware(golden_file: str, py_fn) -> None:
    """Python matches golden only for codepoints assigned in this runtime."""
    data = _load(golden_file)
    failures = []
    skipped_cn = 0
    for entry in data["entries"]:
        cp = int(entry["cp"].replace("U+", ""), 16)
        if unicodedata.category(chr(cp)) == "Cn":
            skipped_cn += 1
            continue
        got = py_fn(entry["input"])
        if got != entry["expected"]:
            failures.append((entry["cp"], entry["expected"], got))
            if len(failures) >= 20:
                break
    assert not failures, (
        f"{len(failures)} py mismatches in {golden_file} "
        f"(skipped {skipped_cn} Cn); first: {failures[:5]}"
    )


def test_meta_unicode_version_field() -> None:
    """`MetaInfo.unicode_version` exists and equals the pin (ADR-019 §11.1)."""
    from agri_core.registry import MetaInfo

    assert "unicode_version" in MetaInfo.model_fields
    f = MetaInfo.model_fields["unicode_version"]
    assert f.annotation is str
    assert f.is_required()


# ---- D4 additions: full sweep + adversarial + real corpus + hypothesis ----


@_SKIP_NATIVE
@pytest.mark.parametrize(
    ("golden_file", "fn_name", "is_scope"),
    [
        ("normalize_name_16_0.json", "normalize_name", False),
        ("normalize_scope_value_16_0.json", "normalize_scope_value", True),
    ],
)
def test_sweep_version_aware(golden_file: str, fn_name: str, is_scope: bool) -> None:
    """Full scalar sweep, version-aware: skip Cn in this runtime.

    Iterates 0..=0x10FFFF; for each codepoint assigned in this interpreter
    (category != "Cn"), asserts native(cp) == expected (golden or identity).
    Codepoints that are Cn here (unassigned in this runtime) are skipped:
    they are authoritative in native 16.0 (covered by test_native_matches).
    """
    _ = is_scope  # parametrized name for clarity
    data = _load(golden_file)
    golden = _golden_map(data)
    native_fn = getattr(_native, fn_name)
    failures = []
    cn_skipped = 0
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        ch = chr(cp)
        if ch.isspace():
            # Python str.split() collapses to "", but golden (generator
            # skipped isspace) has no entry → identity fallback wrong. Skip.
            continue
        if unicodedata.category(ch) == "Cn":
            cn_skipped += 1
            continue
        expected = golden.get(cp, ch)
        got = native_fn(ch)
        if got != expected:
            failures.append((f"U+{cp:04X}", expected, got))
            if len(failures) >= 20:
                break
    assert not failures, (
        f"{len(failures)} mismatches in {golden_file} "
        f"(skipped {cn_skipped} Cn); first: {failures[:5]}"
    )


_ADVERSARIAL = (
    [cp for cp in range(0x202A, 0x202E + 1)]  # bidi embedding
    + [cp for cp in range(0x2066, 0x2069 + 1)]  # bidi isolate
    + [0x200C, 0x200D]  # ZWNJ, ZWJ
    + [cp for cp in range(0xFE00, 0xFE0F + 1)]  # VS BMP
    + [cp for cp in range(0xE0100, 0xE01EF + 1)]  # VS supplemental
    + [0x00AD]  # SHY
    + [0xE0001]
    + list(range(0xE0020, 0xE007F + 1))  # tag
    + [cp for cp in range(0xFDD0, 0xFDEF + 1)]  # noncharacter BMP
    + [0xFFFE, 0xFFFF, 0x1FFFE, 0x10FFFF]  # noncharacter last
    + [0x0000]  # NUL
)


@_SKIP_NATIVE
def test_adversarial_no_panic_and_idempotent() -> None:
    for cp in _ADVERSARIAL:
        ch = chr(cp)
        once = _native.normalize_name(ch)
        twice = _native.normalize_name(once)
        assert once == twice, f"U+{cp:04X} not idempotent: once={once!r}, twice={twice!r}"


def test_real_corpus_idempotent() -> None:
    """Sample pack + wishlist names: normalize twice == normalize once."""
    corpus: list[str] = []

    sample = _REPO / "src" / "agri_core" / "_samples" / "sample_pack" / "names.csv"
    if sample.exists():
        import csv

        with sample.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("name"):
                    corpus.append(row["name"])

    wishlist = _REPO / "docs" / "design" / "plant_wishlist_v4.csv"
    if wishlist.exists():
        import csv

        with wishlist.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                for cell in row:
                    if cell and cell.strip():
                        corpus.append(cell)

    assert len(corpus) > 20, f"corpus too small: {len(corpus)}"

    for name in corpus:
        once = normalize_name(name)
        twice = normalize_name(once)
        assert once == twice, f"not idempotent: {name!r} -> {once!r} -> {twice!r}"


@pytest.mark.property
def test_hypothesis_idempotent_and_expansion_bounded() -> None:
    """Hypothesis: idempotence + expansion <= MAX_EXPANSION_FACTOR (18.0)."""
    from hypothesis import example, given, settings
    from hypothesis import strategies as st

    MAX_FACTOR = 18.0  # matches crates/agri-kernel/tests/normalize_proptest.rs

    @settings(max_examples=500, deadline=None)
    @example("\u00d7\u0307")  # ADR-019 §11.3 regression (NFC after hybrid lift)
    @example("\u00d7\u0308")
    @example("\u01f0")
    @example("j\u030c")
    @given(st.text())
    def _check(s: str) -> None:
        once = normalize_name(s)
        twice = normalize_name(once)
        assert once == twice, f"idempotence: {s!r}"
        if s and once:
            factor = len(once) / len(s)
            assert factor <= MAX_FACTOR, f"expansion {factor:.2} > {MAX_FACTOR} on {s!r}"

    _check()


@pytest.mark.property
def test_idempotent_known_regressions() -> None:
    """Explicit regressions for non-idempotent inputs found by Hypothesis.

    See ADR-019 §11.3 step 4: casefold + hybrid lift can produce a
    decomposed combining sequence (e.g. U+00D7 U+0307 -> x U+0307) that
    NFKC did not see; NFC re-canonicalization closes the class.
    """
    cases = [
        "\u00d7\u0307",
        "\u00d7\u0308",
        "\u01f0",
        "j\u030c",
    ]
    for s in cases:
        once = normalize_name(s)
        twice = normalize_name(once)
        assert once == twice, f"idempotence regression: {s!r} -> {once!r} -> {twice!r}"
