"""Unit tests for CSV injection sanitization (M16).

The sanitizer prefixes dangerous first characters with a tab, and the
CSV writer uses ``QUOTE_ALL`` so the field is stored as text. Together
this defends against formula injection (``= + - @``), tab/CR/LF smuggling,
and DDE / command execution via legacy Excel behaviour.
"""

from __future__ import annotations

import csv
import io

import pytest

from agri_core.export.review_sheet import _sanitize_cell

pytestmark = pytest.mark.unit


# ---- direct behavior ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("normal", "normal"),
        ("abc=def", "abc=def"),
        ("=SUM(A1)", "\t=SUM(A1)"),
        ("+HYPERLINK()", "\t+HYPERLINK()"),
        ("-40.0 x", "\t-40.0 x"),
        ("@user", "\t@user"),
        ("\tfoo", "\t\tfoo"),
        ("\rbar", "\t\rbar"),
        ("\nbaz", "\t\nbaz"),
        ("=1+1", "\t=1+1"),
        ("=", "\t="),
        ("+", "\t+"),
        ("-", "\t-"),
        ("@", "\t@"),
    ],
)
def test_sanitize_cases(raw: str, expected: str) -> None:
    assert _sanitize_cell(raw) == expected


def test_sanitize_does_not_touch_later_chars() -> None:
    """Only the first character triggers the prefix."""
    assert _sanitize_cell("a=b") == "a=b"
    assert _sanitize_cell("abc+def") == "abc+def"
    assert _sanitize_cell("abc\tdef") == "abc\tdef"


def test_sanitize_preserves_unicode() -> None:
    assert _sanitize_cell("=x") == "\t=x"
    assert _sanitize_cell("caf\u00e9") == "caf\u00e9"


# ---- csv writer round-trip ----------------------------------------------


def test_csv_round_trip_preserves_tab_prefix() -> None:
    """A sanitized cell must survive csv writer + reader unchanged."""
    dangerous = "=SUM(A1)"
    sanitized = _sanitize_cell(dangerous)
    assert sanitized == "\t=SUM(A1)"

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["v"], quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    writer.writerow({"v": sanitized})

    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert len(rows) == 1
    assert rows[0]["v"] == "\t=SUM(A1)"


def test_csv_round_trip_preserves_normal_value() -> None:
    sanitized = _sanitize_cell("normal text")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["v"], quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    writer.writerow({"v": sanitized})
    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert rows[0]["v"] == "normal text"


def test_ingest_side_recovery() -> None:
    """Simulate the ingest rule: trust the generator's tab prefix; reject raw.

    The generator (``_sanitize_cell``) prefixes a tab to any cell that
    starts with ``= + - @``, tab, CR or LF. That prefix is our marker:
    the ingest step strips one leading tab and accepts the value, because
    it can only have come from our own writer. A cell with no tab prefix
    that starts with a dangerous character is rejected as untrusted.
    """

    def ingest(value: str) -> str:
        # Trusted: our generator added this prefix.
        if value.startswith("\t"):
            return value[1:]
        # Untrusted: no tab prefix but dangerous.
        if value and value[0] in ("=", "+", "-", "@", "\r", "\n"):
            raise ValueError(f"rejected: {value!r}")
        return value

    # Round-trip: sanitized dangerous value recovers its original.
    assert ingest(_sanitize_cell("=SUM(A1)")) == "=SUM(A1)"
    assert ingest(_sanitize_cell("+X")) == "+X"
    assert ingest(_sanitize_cell("-40.0")) == "-40.0"
    assert ingest(_sanitize_cell("@user")) == "@user"

    # Round-trip: normal value passes through unchanged.
    assert ingest(_sanitize_cell("normal")) == "normal"
    assert ingest(_sanitize_cell("abc=def")) == "abc=def"

    # Direct attack (no tab prefix, dangerous first char) is rejected.
    with pytest.raises(ValueError, match="rejected"):
        ingest("=SUM(A1)")
    with pytest.raises(ValueError, match="rejected"):
        ingest("+HYPERLINK()")
    with pytest.raises(ValueError, match="rejected"):
        ingest("-cmd")
    with pytest.raises(ValueError, match="rejected"):
        ingest("@x")


# ---- M16 coverage gap: _as_cell None / non-str ----


def test_as_cell_none_returns_empty() -> None:
    from agri_core.export.review_sheet import _as_cell

    assert _as_cell(None) == ""


def test_as_cell_non_str_converts() -> None:
    from agri_core.export.review_sheet import _as_cell

    assert _as_cell(42) == "42"
    assert _as_cell(3.14) == "3.14"
