"""Read-table limits and Unicode guard (Step 5)."""

from __future__ import annotations

import pytest

from agri_core.pack.errors import (
    PackError,
    PackFieldTooLargeError,
    PackRowTooLargeError,
    PackTableInvalidError,
)
from agri_core.pack.tables import MAX_FIELD_BYTES, TABLES, read_table

pytestmark = pytest.mark.contract

_SPEC = TABLES["sources"]
_HEADER = ",".join(c.name for c in _SPEC.columns)
_N_COLS = len(_SPEC.columns)


def _row(*cells: str) -> str:
    return ",".join(cells)


def _data(*rows: str) -> bytes:
    return (_HEADER + "\n" + "\n".join(rows) + "\n").encode("utf-8")


def _valid_row() -> str:
    # One valid sources row: all cells small.
    cells = ["S001", "https://example.org/x", "CC0-1.0", "yes", "2026-01-01", "x"]
    return _row(*cells)


# ---- Sizes ----


def test_field_too_large_rejected() -> None:
    big = "x" * (MAX_FIELD_BYTES + 1)
    row = _row("S001", "https://example.org/x", "CC0-1.0", "yes", "2026-01-01", big)
    with pytest.raises(PackFieldTooLargeError, match="cell exceeds"):
        read_table(_SPEC, _data(row), source_name="t.csv")


def test_row_too_large_rejected() -> None:
    # Each cell <= MAX_FIELD_BYTES but row total > MAX_ROW_BYTES.
    per_cell = "x" * (MAX_FIELD_BYTES - 1)
    cells = [per_cell] * _N_COLS
    row = _row(*cells)
    with pytest.raises(PackRowTooLargeError, match="row exceeds"):
        read_table(_SPEC, _data(row), source_name="t.csv")


def test_field_at_limit_ok() -> None:
    at_limit = "x" * (MAX_FIELD_BYTES // 2)  # well under
    row = _row("S001", "https://example.org/x", "CC0-1.0", "yes", "2026-01-01", at_limit)
    table = read_table(_SPEC, _data(row), source_name="t.csv")
    assert len(table.rows) == 1


# ---- Unicode guard ----


@pytest.mark.parametrize(
    ("char", "category"),
    [
        ("\u202e", "bidi-control"),  # RIGHT-TO-LEFT OVERRIDE
        ("\u202a", "bidi-control"),  # LEFT-TO-RIGHT EMBEDDING
        ("\u200b", "zero-width"),  # ZERO WIDTH SPACE
        ("\u200d", "zero-width"),  # ZERO WIDTH JOINER
        ("\ufeff", "zero-width"),  # BOM
        ("\u00ad", "invisible"),  # SOFT HYPHEN
    ],
)
def test_unicode_forbidden_rejected(char: str, category: str) -> None:
    with pytest.raises(PackTableInvalidError, match=category):
        read_table(_SPEC, _data(_valid_row() + char), source_name="t.csv")


def test_legitimate_unicode_ok() -> None:
    # Japanese, emoji, CJK, Latin diacritics — all allowed.
    row = _row("S001", "https://example.org/日本", "CC0-1.0", "yes", "2026-01-01", "café 日本語 🌱")
    table = read_table(_SPEC, _data(row), source_name="t.csv")
    assert len(table.rows) == 1


def test_newline_in_cell_still_rejected() -> None:
    # Regression: existing multiline check must stay.
    payload = (_HEADER + "\n" + _valid_row() + "\n").encode("utf-8")
    # Sanity: valid parse.
    read_table(_SPEC, payload, source_name="t.csv")
    # Now cell with embedded newline — csv.reader will split; the row
    # count check or the multiline check should fire.
    bad = (_HEADER + '\n"S001\nextra",a,b,c,d,e\n').encode("utf-8")
    with pytest.raises(PackError):
        read_table(_SPEC, bad, source_name="t.csv")
