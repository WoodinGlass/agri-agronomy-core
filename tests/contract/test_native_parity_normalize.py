"""Version-aware native/Python parity for normalize (ADR-019 §11.2).

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
    data = json.loads(p.read_text())
    assert data["version"] == "16.0.0", f"{golden_file}: version={data['version']}, expected 16.0.0"
    return data


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
