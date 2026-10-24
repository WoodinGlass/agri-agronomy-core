"""Identifier types and shared rules."""

from __future__ import annotations

import re

import pytest
from pydantic import BaseModel, ValidationError

from agri_core.models.ids import (
    CROCKFORD_ALPHABET,
    CROCKFORD_CHARS,
    DatasetId,
    FactId,
    SourceId,
    TaxonId,
    ensure_src_or_dataset,
)

pytestmark = pytest.mark.unit


# --- alphabet sanity ---


def test_alphabet_length() -> None:
    assert len(CROCKFORD_ALPHABET) == 32


def test_alphabet_excludes_ambiguous_chars() -> None:
    for ch in "ILOU":
        assert ch not in CROCKFORD_ALPHABET


def test_alphabet_unique() -> None:
    assert len(set(CROCKFORD_ALPHABET)) == 32


def test_chars_pattern_matches_every_alphabet_char() -> None:
    for ch in CROCKFORD_ALPHABET:
        assert re.match(rf"^[{CROCKFORD_CHARS}]$", ch)


def test_chars_pattern_rejects_ambiguous_letters() -> None:
    for ch in "ILOU":
        assert not re.match(rf"^[{CROCKFORD_CHARS}]$", ch)


# --- helper models ---


class _Taxon(BaseModel):
    id: TaxonId


class _Fact(BaseModel):
    id: FactId


class _Dataset(BaseModel):
    id: DatasetId


class _Source(BaseModel):
    id: SourceId


# --- TaxonId ---


@pytest.mark.parametrize(
    "value",
    [
        "T012345678",
        "TABCDEFGHJ",
        "T01234ABCD",
        "TZZZZZZZZZ",
    ],
)
def test_taxon_id_valid(value: str) -> None:
    _Taxon(id=value)


@pytest.mark.parametrize(
    "value",
    [
        "T01234567",
        "T0123456789",
        "X012345678",
        "t012345678",
        "T01234567I",
        "T01234567L",
        "T01234567O",
        "T01234567U",
        "T-12345678",
        "T 12345678",
        "T012345678 ",
    ],
)
def test_taxon_id_invalid(value: str) -> None:
    with pytest.raises(ValidationError):
        _Taxon(id=value)


# --- FactId ---


@pytest.mark.parametrize(
    "value",
    [
        "F01234567890",
        "F012345678901",
        "F0123456789012345",
        "FABCDEFGHJKM",
    ],
)
def test_fact_id_valid(value: str) -> None:
    _Fact(id=value)


@pytest.mark.parametrize(
    "value",
    [
        "F0123456789",
        "F01234ABCDE",
        "X01234567890",
        "f01234567890",
        "F0123456789I",
    ],
)
def test_fact_id_invalid(value: str) -> None:
    with pytest.raises(ValidationError):
        _Fact(id=value)


# --- DatasetId ---


@pytest.mark.parametrize(
    "value",
    [
        "D012345678",
        "DABCDEFGHJ",
    ],
)
def test_dataset_id_valid(value: str) -> None:
    _Dataset(id=value)


@pytest.mark.parametrize(
    "value",
    [
        "D01234567",
        "D0123456789",
        "X012345678",
        "d012345678",
    ],
)
def test_dataset_id_invalid(value: str) -> None:
    with pytest.raises(ValidationError):
        _Dataset(id=value)


# --- SourceId ---


@pytest.mark.parametrize(
    "value",
    [
        "S001",
        "S999",
        "S12345",
        "S0000001",
    ],
)
def test_source_id_valid(value: str) -> None:
    _Source(id=value)


@pytest.mark.parametrize(
    "value",
    [
        "S01",
        "S1",
        "s001",
        "X001",
        "S00A",
    ],
)
def test_source_id_invalid(value: str) -> None:
    with pytest.raises(ValidationError):
        _Source(id=value)


# --- ensure_src_or_dataset ---


def test_src_or_dataset_both_present() -> None:
    ensure_src_or_dataset(["S001"], "D012345678")


def test_src_or_dataset_src_only() -> None:
    ensure_src_or_dataset(["S001"], None)


def test_src_or_dataset_dataset_only() -> None:
    ensure_src_or_dataset(None, "D012345678")


def test_src_or_dataset_neither() -> None:
    with pytest.raises(ValueError, match="at least one of src or dataset_id"):
        ensure_src_or_dataset(None, None)


def test_src_or_dataset_empty_list_treated_as_missing() -> None:
    with pytest.raises(ValueError, match="at least one of src or dataset_id"):
        ensure_src_or_dataset([], None)


def test_src_or_dataset_empty_list_with_dataset_ok() -> None:
    ensure_src_or_dataset([], "D012345678")
