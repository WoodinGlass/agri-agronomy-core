"""Fuzz tests: read_table must never crash on arbitrary input."""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agri_core.pack.errors import PackError
from agri_core.pack.tables import TABLES, read_table

pytestmark = pytest.mark.property

_SPEC = TABLES["sources"]


@given(data=st.binary(min_size=0, max_size=4096))
@settings(max_examples=50, deadline=None)
def test_arbitrary_bytes_never_crash(data: bytes) -> None:
    """Any byte sequence either parses or raises PackError. No other exception."""
    with contextlib.suppress(PackError):
        read_table(_SPEC, data, source_name="fuzz.csv")


@given(
    text=st.text(
        alphabet=st.characters(codec="utf-8", blacklist_categories=("Cc", "Cn")),
        min_size=0,
        max_size=512,
    )
)
@settings(max_examples=50, deadline=None)
def test_random_text_never_crash(text: str) -> None:
    data = text.encode("utf-8")
    with contextlib.suppress(PackError):
        read_table(_SPEC, data, source_name="fuzz.csv")


@given(header=st.text(min_size=0, max_size=64), row=st.text(min_size=0, max_size=64))
@settings(max_examples=30, deadline=None)
def test_header_mismatch_is_pack_error(header: str, row: str) -> None:
    data = f"{header}\n{row}\n".encode("utf-8", errors="replace")
    with contextlib.suppress(PackError):
        read_table(_SPEC, data, source_name="fuzz.csv")
