"""Table codec contract tests."""

from __future__ import annotations

from datetime import date

import pytest

from agri_core.models.dataset import DatasetRow
from agri_core.models.fact import FactRow
from agri_core.models.hazard import HazardRow
from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack import (
    TABLES,
    InvalidPackError,
    PackError,
    PackTableInvalidError,
    read_table,
    write_table,
)
from agri_core.registry.sources import CSV_HEADER, SourceRow

pytestmark = pytest.mark.contract


# ---- catalog consistency -------------------------------------------------


def test_tables_catalog_complete() -> None:
    assert set(TABLES) == {"taxa", "names", "facts", "hazards", "datasets", "sources"}


@pytest.mark.parametrize("name", sorted(TABLES))
def test_table_has_columns(name: str) -> None:
    spec = TABLES[name]
    assert spec.columns, f"{name} has no columns"
    assert spec.name == name


@pytest.mark.parametrize("name", sorted(TABLES))
def test_column_names_unique(name: str) -> None:
    spec = TABLES[name]
    names = [c.name for c in spec.columns]
    assert len(names) == len(set(names)), f"{name} has duplicate column names"


@pytest.mark.parametrize("name", sorted(TABLES))
def test_primary_key_columns_exist(name: str) -> None:
    spec = TABLES[name]
    cols = {c.name for c in spec.columns}
    for pk_col in spec.primary_key:
        assert pk_col in cols, f"{name}: pk column {pk_col!r} not in spec"


@pytest.mark.parametrize(
    ("table_name", "model"),
    [
        ("taxa", TaxonRow),
        ("names", NameRow),
        ("facts", FactRow),
        ("hazards", HazardRow),
        ("datasets", DatasetRow),
    ],
)
def test_table_columns_match_model(table_name: str, model: type) -> None:
    expected = list(model.model_fields.keys())
    actual = [c.name for c in TABLES[table_name].columns]
    assert actual == expected, (
        f"{table_name}: column order differs from {model.__name__}.model_fields. "
        f"expected={expected} actual={actual}"
    )


def test_sources_columns_match_csv_header() -> None:
    actual = [c.name for c in TABLES["sources"].columns]
    assert actual == list(CSV_HEADER)


# ---- round-trip per table -------------------------------------------------


def test_roundtrip_taxa() -> None:
    row = TaxonRow(
        taxon_id="T000000001",
        rank="species",
        scientific_name="Testus annualis",
        organism_group="plant",
        archetype="annual",
        uses=["vegetable"],
        traits=["drought_tolerant"],
        src=["S001"],
    )
    table = read_table(
        TABLES["taxa"],
        write_table(TABLES["taxa"], [row.model_dump()]),
        source_name="taxa.csv",
    )
    assert len(table.rows) == 1
    assert TaxonRow.model_validate(dict(table.rows[0])) == row


def test_roundtrip_names() -> None:
    row = NameRow(
        taxon_id="T000000001",
        name="Testus annualis",
        language="en",
        script="Latn",
        kind="scientific",
        preferred=True,
        src=["S001"],
    )
    table = read_table(
        TABLES["names"],
        write_table(TABLES["names"], [row.model_dump()]),
        source_name="names.csv",
    )
    assert NameRow.model_validate(dict(table.rows[0])) == row


def test_roundtrip_facts() -> None:
    row = FactRow(
        fact_id="F00000000001",
        taxon_id="T000000001",
        parameter="base_temp_c",
        value={"shape": "scalar", "unit": "degC", "value": 10.0},
        scope={},
        provenance_kind="curated",
        src=["S001"],
        locator="Table 1",
        evidence="B",
        status="reviewed",
        reviewed_by="reviewer-1",
        reviewed_at=date(2026, 1, 1),
    )
    table = read_table(
        TABLES["facts"],
        write_table(TABLES["facts"], [row.model_dump()]),
        source_name="facts/T000000001.csv",
    )
    assert FactRow.model_validate(dict(table.rows[0])) == row


def test_roundtrip_hazards() -> None:
    row = HazardRow(
        taxon_id="T000000001",
        hazard_code="toxicity_mild",
        severity="warning",
        reason="Mild toxicity if ingested",
        as_of=date(2026, 1, 1),
        authority="Synthetic test authority",
        src=["S001"],
    )
    table = read_table(
        TABLES["hazards"],
        write_table(TABLES["hazards"], [row.model_dump()]),
        source_name="hazards.csv",
    )
    assert HazardRow.model_validate(dict(table.rows[0])) == row


def test_roundtrip_datasets() -> None:
    row = DatasetRow(
        dataset_id="D000000001",
        name="Synthetic reference set",
        version="1.0",
        license="CC0-1.0",
        checksum="sha256:" + "0" * 64,
        url="https://example.org/ds",
        access_date=date(2026, 1, 1),
    )
    table = read_table(
        TABLES["datasets"],
        write_table(TABLES["datasets"], [row.model_dump()]),
        source_name="datasets.csv",
    )
    assert DatasetRow.model_validate(dict(table.rows[0])) == row


def test_roundtrip_sources() -> None:
    row = SourceRow(
        id="S001",
        url="https://example.org/s",
        license="CC0-1.0",
        commercial_use="yes",
        access_date=date(2026, 1, 1),
        citation="Synthetic source",
    )
    table = read_table(
        TABLES["sources"],
        write_table(TABLES["sources"], [row.model_dump()]),
        source_name="sources.csv",
    )
    assert SourceRow.model_validate(dict(table.rows[0])) == row


# ---- reader strictness ----------------------------------------------------


def _header_for(name: str) -> bytes:
    cols = [c.name for c in TABLES[name].columns]
    return (",".join(cols) + "\n").encode("utf-8")


def _make_row(name: str, cells: list[str]) -> bytes:
    """Build one data row (no header) with proper CSV quoting."""
    import csv as _csv
    import io as _io

    cols = [c.name for c in TABLES[name].columns]
    assert len(cells) == len(cols), f"{name}: {len(cells)} cells, expected {len(cols)}"
    buf = _io.StringIO()
    _csv.writer(buf, lineterminator="\n").writerow(cells)
    return buf.getvalue().encode("utf-8")


def test_reader_rejects_empty_file() -> None:
    with pytest.raises(PackTableInvalidError, match="empty file"):
        read_table(TABLES["sources"], b"", source_name="sources.csv")


def test_reader_rejects_bom() -> None:
    data = b"\xef\xbb\xbf" + _header_for("sources")
    with pytest.raises(PackTableInvalidError, match="BOM"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_rejects_nul() -> None:
    data = _header_for("sources") + b"\x00"
    with pytest.raises(PackTableInvalidError, match="NUL"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_rejects_invalid_utf8() -> None:
    data = _header_for("sources") + b"\xff\xfe"
    with pytest.raises(PackTableInvalidError, match="UTF-8"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_rejects_bare_cr() -> None:
    data = _header_for("sources").replace(b"\n", b"\r")
    with pytest.raises(PackTableInvalidError, match="bare CR"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_accepts_crlf() -> None:
    header = _header_for("sources").replace(b"\n", b"\r\n")
    table = read_table(TABLES["sources"], header, source_name="sources.csv")
    assert table.rows == ()


def test_reader_rejects_header_mismatch() -> None:
    data = b"wrong,header,line\n"
    with pytest.raises(PackTableInvalidError, match="header"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_rejects_wrong_column_count() -> None:
    data = _header_for("sources") + b"S001,https://example.org,CC0-1.0\n"
    with pytest.raises(PackTableInvalidError, match="fields"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_rejects_empty_required_cell() -> None:
    data = _header_for("sources") + b",https://example.org,CC0-1.0,yes,2026-01-01,doc\n"
    with pytest.raises(PackTableInvalidError, match="empty cell"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_accepts_empty_nullable_cell() -> None:
    data = (
        _header_for("taxa")
        + b"T000000001,species,Testus annualis,,plant,annual,vegetable,,"
        + b",,S001,\n"
    )
    table = read_table(TABLES["taxa"], data, source_name="taxa.csv")
    assert table.rows[0]["accepted_name"] is None
    assert table.rows[0]["parent_id"] is None
    assert table.rows[0]["external_ids"] is None


def test_reader_empty_list_cell_decodes_to_empty_list() -> None:
    data = (
        _header_for("taxa")
        + b"T000000001,species,Testus annualis,,plant,annual,vegetable,,"
        + b",,S001,\n"
    )
    table = read_table(TABLES["taxa"], data, source_name="taxa.csv")
    assert table.rows[0]["traits"] == []


def test_reader_empty_nullable_list_cell_decodes_to_none() -> None:
    data = (
        _header_for("taxa")
        + b"T000000001,species,Testus annualis,,plant,annual,vegetable,,"
        + b",,,\n"
    )
    table = read_table(TABLES["taxa"], data, source_name="taxa.csv")
    assert table.rows[0]["src"] is None


def test_reader_rejects_empty_item_in_list() -> None:
    data = (
        _header_for("taxa")
        + b"T000000001,species,Testus annualis,,plant,annual,a||b,,"
        + b",,S001,\n"
    )
    with pytest.raises(PackTableInvalidError, match="empty item"):
        read_table(TABLES["taxa"], data, source_name="taxa.csv")


def test_reader_rejects_invalid_bool() -> None:
    data = _header_for("names") + b"T000000001,x,en,Latn,common,yes,S001,\n"
    with pytest.raises(PackTableInvalidError, match=r"true.*false"):
        read_table(TABLES["names"], data, source_name="names.csv")


def test_reader_rejects_duplicate_json_keys() -> None:
    data = _header_for("facts") + _make_row(
        "facts",
        [
            "F00000000001",
            "T000000001",
            "base_temp_c",
            "",
            '{"shape":"scalar","shape":"range"}',
            "{}",
            "curated",
            "S001",
            "",
            "Table 1",
            "B",
            "reviewed",
            "",
            "",
            "",
        ],
    )
    with pytest.raises(PackTableInvalidError, match="duplicate JSON key"):
        read_table(TABLES["facts"], data, source_name="facts/T000000001.csv")


def test_reader_rejects_nan_in_json() -> None:
    data = _header_for("facts") + _make_row(
        "facts",
        [
            "F00000000001",
            "T000000001",
            "base_temp_c",
            "",
            '{"shape":"scalar","unit":"degC","value":NaN}',
            "{}",
            "curated",
            "S001",
            "",
            "Table 1",
            "B",
            "reviewed",
            "",
            "",
            "",
        ],
    )
    with pytest.raises(PackTableInvalidError, match="non-finite"):
        read_table(TABLES["facts"], data, source_name="facts/T000000001.csv")


def test_reader_rejects_control_char_in_cell() -> None:
    data = (
        _header_for("sources")
        + b"S001,https://example.org,CC0-1.0,yes,2026-01-01,"
        + b"bad\x07char\n"
    )
    with pytest.raises(PackTableInvalidError, match="control character"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


def test_reader_rejects_invalid_date() -> None:
    data = _header_for("sources") + b"S001,https://example.org,CC0-1.0,yes,not-a-date,doc\n"
    with pytest.raises(PackTableInvalidError, match="date"):
        read_table(TABLES["sources"], data, source_name="sources.csv")


# ---- writer properties ----------------------------------------------------


def test_writer_uses_lf_line_endings() -> None:
    row = {
        "id": "S001",
        "url": "https://example.org",
        "license": "CC0-1.0",
        "commercial_use": "yes",
        "access_date": date(2026, 1, 1),
        "citation": "synthetic",
    }
    out = write_table(TABLES["sources"], [row])
    assert b"\r" not in out
    assert out.endswith(b"\n")


def test_writer_sorts_list_items() -> None:
    row = {
        "taxon_id": "T000000001",
        "rank": "species",
        "scientific_name": "Testus annualis",
        "accepted_name": None,
        "organism_group": "plant",
        "archetype": "annual",
        "uses": ["zzz", "aaa", "mmm"],
        "traits": [],
        "parent_id": None,
        "external_ids": None,
        "src": ["S002", "S001"],
        "dataset_id": None,
    }
    out = write_table(TABLES["taxa"], [row]).decode("utf-8")
    assert "aaa|mmm|zzz" in out
    assert "S001|S002" in out


def test_writer_sorts_dict_keys() -> None:
    row = {
        "taxon_id": "T000000001",
        "rank": "species",
        "scientific_name": "Testus annualis",
        "accepted_name": None,
        "organism_group": "plant",
        "archetype": "annual",
        "uses": ["vegetable"],
        "traits": [],
        "parent_id": None,
        "external_ids": {"b": "2", "a": "1"},
        "src": ["S001"],
        "dataset_id": None,
    }
    out = write_table(TABLES["taxa"], [row]).decode("utf-8")
    # canonical_json is sorted; whether csv quotes it depends on content
    assert "a" in out
    assert "1" in out
    assert "b" in out
    assert "2" in out
    assert out.find('"a"') < out.find('"b"')


def test_writer_rejects_empty_list_in_nullable_column() -> None:
    row = {
        "taxon_id": "T000000001",
        "rank": "species",
        "scientific_name": "Testus annualis",
        "accepted_name": None,
        "organism_group": "plant",
        "archetype": "annual",
        "uses": ["vegetable"],
        "traits": [],
        "parent_id": None,
        "external_ids": None,
        "src": [],
        "dataset_id": None,
    }
    with pytest.raises(PackTableInvalidError, match="empty list not allowed"):
        write_table(TABLES["taxa"], [row])


# ---- error attributes and backward-compat --------------------------------


def test_error_has_file_line_key() -> None:
    data = _header_for("sources") + b"S001,x,CC0-1.0,yes,2026-01-01,doc,extra\n"
    with pytest.raises(PackTableInvalidError, match="fields") as exc_info:
        read_table(TABLES["sources"], data, source_name="sources.csv")
    exc = exc_info.value
    assert exc.code == "PACK_TABLE_INVALID"
    assert exc.file == "sources.csv"
    assert exc.line == 2
    assert exc.findings == ()


def test_pack_error_backward_compat() -> None:
    exc = InvalidPackError("legacy message")
    assert str(exc) == "legacy message"
    assert exc.code == "PACK_INVALID"
    assert exc.file is None
    assert exc.line is None
    assert exc.key is None
    assert exc.findings == ()
    assert isinstance(exc, PackError)


def test_pack_error_findings_roundtrip() -> None:
    a = PackTableInvalidError("first", file="a.csv", line=1)
    b = PackTableInvalidError("second", file="b.csv", line=2)
    exc = PackTableInvalidError("aggregate", findings=(a, b))
    assert exc.findings == (a, b)
    assert exc.code == "PACK_TABLE_INVALID"
