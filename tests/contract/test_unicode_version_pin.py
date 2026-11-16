"""Tripwire: Unicode pin consistency (ADR-019 §11.1, §11.13).

Checks the pin is consistent across `agri_core._native.unicode_version()`,
`MetaInfo.unicode_version`, `Cargo.lock`, ADR-019 §11.1, and the source
constant. Any divergence is a bug: pin drift, crate upgrade without ADR
amendment, or `.so` rebuilt against a different crate version.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agri_core.registry import MetaInfo

pytestmark = pytest.mark.contract
_REPO = Path(__file__).resolve().parents[2]
_PIN = "16.0.0"


def test_meta_field_exists_and_is_str() -> None:
    assert "unicode_version" in MetaInfo.model_fields
    f = MetaInfo.model_fields["unicode_version"]
    assert f.annotation is str
    assert f.is_required()


def test_native_unicode_version_matches_pin() -> None:
    try:
        from agri_core import _native
    except ImportError:
        pytest.skip("native extension not built; run `pip install -e .`")
    assert hasattr(_native, "unicode_version")
    assert _native.unicode_version() == _PIN


def test_cargo_lock_caseless_is_16_0_0_capable() -> None:
    lock = (_REPO / "Cargo.lock").read_text()
    m = re.search(r'name = "caseless"\nversion = "([^"]+)"', lock)
    assert m, "caseless not in Cargo.lock"
    assert m.group(1) == "0.2.2", f"caseless = {m.group(1)}, expected 0.2.2 (pins Unicode 16.0.0)"


def test_unicode_normalization_at_least_0_1_26() -> None:
    """unicode-normalization 0.1.26 ships Unicode 18.0 tables. Strict mode
    restricts input to <=16.0, so 17.0/18.0 tables are dead for accepted
    input (ADR-019 §11.1 + stability policy)."""
    lock = (_REPO / "Cargo.lock").read_text()
    m = re.search(r'name = "unicode-normalization"\nversion = "([^"]+)"', lock)
    assert m, "unicode-normalization not in Cargo.lock"
    ver = m.group(1)
    mm = re.match(r"^(\d+)\.(\d+)\.(\d+)", ver)
    assert mm, f"unparseable version: {ver!r}"
    v = tuple(int(x) for x in mm.groups())
    assert v >= (0, 1, 26), f"unicode-normalization = {ver}, expected >= 0.1.26 (ships 18.0 tables)"


def test_adr_pin_mentions_16_0_0() -> None:
    txt = (_REPO / "docs" / "decisions" / "ADR-019-rust-native-kernel.md").read_text()
    assert _PIN in txt, f"ADR-019 does not mention {_PIN!r}"


def test_unicode_pin_rs_constant_matches() -> None:
    txt = (_REPO / "crates" / "agri-kernel" / "src" / "pack" / "unicode_pin.rs").read_text()
    assert 'pub const UNICODE_VERSION: &str = "16.0.0";' in txt


def test_icu4x_pinned_dev_only() -> None:
    lock = (_REPO / "Cargo.lock").read_text()
    for name in ["icu_casemap", "icu_normalizer"]:
        m = re.search(rf'name = "{re.escape(name)}"\nversion = "([^"]+)"', lock)
        assert m, f"{name} not in Cargo.lock — dev-dep not fetched"
        assert m.group(1) == "2.4.0", f"{name} = {m.group(1)}, expected 2.4.0 (ADR-019 §11.13 pin)"
