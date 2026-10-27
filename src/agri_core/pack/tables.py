"""CSV table codec for pack files.

Row models are pure contracts (no I/O, no CSV). This module owns the
bidirectional encoding between on-disk CSV bytes and plain dicts. The
result is validated by the caller via ``Model.model_validate``.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Literal

from agri_core.models.canonical import canonical_json
from agri_core.pack.errors import PackTableInvalidError

ColumnType = Literal[
    "str",
    "int",
    "float",
    "bool",
    "date",
    "list_str",
    "dict_str_str",
    "json",
]


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """One column in a pack table."""

    name: str
    type: ColumnType
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class TableSpec:
    """Schema for one pack table.

    ``filename`` is the CSV basename inside a pack directory. It is
    ``None`` for the ``facts`` table, which is stored as one file per
    taxon under ``facts/<taxon_id>.csv``.
    """

    name: str
    filename: str | None
    columns: tuple[ColumnSpec, ...]
    primary_key: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Table:
    """A parsed table: spec, source label, rows, and their line numbers."""

    spec: TableSpec
    source_name: str
    rows: tuple[Mapping[str, Any], ...]
    line_numbers: tuple[int, ...]


TABLES: Mapping[str, TableSpec] = MappingProxyType(
    {
        "taxa": TableSpec(
            name="taxa",
            filename="taxa.csv",
            columns=(
                ColumnSpec("taxon_id", "str"),
                ColumnSpec("rank", "str"),
                ColumnSpec("scientific_name", "str"),
                ColumnSpec("accepted_name", "str", nullable=True),
                ColumnSpec("organism_group", "str"),
                ColumnSpec("archetype", "str"),
                ColumnSpec("uses", "list_str"),
                ColumnSpec("traits", "list_str"),
                ColumnSpec("parent_id", "str", nullable=True),
                ColumnSpec("external_ids", "dict_str_str", nullable=True),
                ColumnSpec("src", "list_str", nullable=True),
                ColumnSpec("dataset_id", "str", nullable=True),
            ),
            primary_key=("taxon_id",),
        ),
        "names": TableSpec(
            name="names",
            filename="names.csv",
            columns=(
                ColumnSpec("taxon_id", "str"),
                ColumnSpec("name", "str"),
                ColumnSpec("language", "str"),
                ColumnSpec("script", "str"),
                ColumnSpec("kind", "str"),
                ColumnSpec("preferred", "bool"),
                ColumnSpec("src", "list_str", nullable=True),
                ColumnSpec("dataset_id", "str", nullable=True),
            ),
            primary_key=("taxon_id", "name", "language", "script", "kind"),
        ),
        "facts": TableSpec(
            name="facts",
            filename=None,
            columns=(
                ColumnSpec("fact_id", "str"),
                ColumnSpec("taxon_id", "str"),
                ColumnSpec("parameter", "str"),
                ColumnSpec("phase", "str", nullable=True),
                ColumnSpec("value", "json"),
                ColumnSpec("scope", "json"),
                ColumnSpec("provenance_kind", "str"),
                ColumnSpec("src", "list_str", nullable=True),
                ColumnSpec("dataset_id", "str", nullable=True),
                ColumnSpec("locator", "str", nullable=True),
                ColumnSpec("evidence", "str"),
                ColumnSpec("status", "str"),
                ColumnSpec("reviewed_by", "list_str", nullable=True),
                ColumnSpec("reviewed_at", "date", nullable=True),
                ColumnSpec("superseded_by", "str", nullable=True),
            ),
            primary_key=("fact_id",),
        ),
        "hazards": TableSpec(
            name="hazards",
            filename="hazards.csv",
            columns=(
                ColumnSpec("taxon_id", "str"),
                ColumnSpec("hazard_code", "str"),
                ColumnSpec("severity", "str"),
                ColumnSpec("reason", "str"),
                ColumnSpec("as_of", "date"),
                ColumnSpec("authority", "str"),
                ColumnSpec("src", "list_str", nullable=True),
                ColumnSpec("dataset_id", "str", nullable=True),
            ),
            primary_key=("taxon_id", "hazard_code"),
        ),
        "datasets": TableSpec(
            name="datasets",
            filename="datasets.csv",
            columns=(
                ColumnSpec("dataset_id", "str"),
                ColumnSpec("name", "str"),
                ColumnSpec("version", "str"),
                ColumnSpec("license", "str"),
                ColumnSpec("checksum", "str"),
                ColumnSpec("url", "str", nullable=True),
                ColumnSpec("locator", "str", nullable=True),
                ColumnSpec("access_date", "date"),
            ),
            primary_key=("dataset_id",),
        ),
        "sources": TableSpec(
            name="sources",
            filename="sources.csv",
            columns=(
                ColumnSpec("id", "str"),
                ColumnSpec("url", "str"),
                ColumnSpec("license", "str"),
                ColumnSpec("commercial_use", "str"),
                ColumnSpec("access_date", "date"),
                ColumnSpec("citation", "str"),
            ),
            primary_key=("id",),
        ),
    }
)
"""Canonical schemas for every pack table, keyed by table name."""


ADVISORIES_FILENAME = "advisories.csv"
"""Reserved filename. Fail-closed until M8; content in this file is unsupported."""


def _reject_dup_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError(f"duplicate JSON key {k!r}")
        seen.add(k)
        out[k] = v
    return out


def _reject_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON number {value!r} not allowed")


def _decode_cell(value: str, col: ColumnSpec, *, file: str, line: int) -> Any:
    """Decode a raw CSV string cell into a Python value per column type."""
    is_empty = value == ""
    if is_empty:
        if col.nullable:
            return None
        if col.type == "list_str":
            return []
        raise PackTableInvalidError(
            f"empty cell in required column {col.name!r}",
            file=file,
            line=line,
            key=col.name,
        )
    try:
        if col.type == "str":
            return value
        if col.type == "int":
            return int(value)
        if col.type == "float":
            return float(value)
        if col.type == "bool":
            if value == "true":
                return True
            if value == "false":
                return False
            raise ValueError(f"expected 'true' or 'false', got {value!r}")
        if col.type == "date":
            return date.fromisoformat(value)
        if col.type == "list_str":
            items = value.split("|")
            for item in items:
                if item == "":
                    raise ValueError("empty item in list cell")
            return items
        if col.type == "dict_str_str":
            parsed = json.loads(
                value,
                object_pairs_hook=_reject_dup_keys,
                parse_constant=_reject_nonfinite,
            )
            if not isinstance(parsed, dict):
                raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
            for k, v in parsed.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise ValueError("dict_str_str requires string keys and values")
            return parsed
        if col.type == "json":
            return json.loads(
                value,
                object_pairs_hook=_reject_dup_keys,
                parse_constant=_reject_nonfinite,
            )
    except (ValueError, json.JSONDecodeError) as exc:
        raise PackTableInvalidError(
            f"invalid {col.type} in column {col.name!r}: {exc}",
            file=file,
            line=line,
            key=col.name,
        ) from exc
    raise PackTableInvalidError(
        f"unknown column type {col.type!r}",
        file=file,
        line=line,
        key=col.name,
    )


def _encode_cell(value: Any, col: ColumnSpec, *, line: int) -> str:
    """Encode a Python value into a raw CSV string cell per column type."""
    if value is None:
        if not col.nullable:
            raise PackTableInvalidError(
                f"None in non-nullable column {col.name!r}",
                line=line,
                key=col.name,
            )
        return ""
    if col.type == "str":
        if not isinstance(value, str):
            raise PackTableInvalidError(
                f"expected str, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        return value
    if col.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise PackTableInvalidError(
                f"expected int, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        return str(value)
    if col.type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PackTableInvalidError(
                f"expected float, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        return repr(float(value))
    if col.type == "bool":
        if not isinstance(value, bool):
            raise PackTableInvalidError(
                f"expected bool, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        return "true" if value else "false"
    if col.type == "date":
        if isinstance(value, datetime):
            raise PackTableInvalidError(
                f"expected date (not datetime), got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        if not isinstance(value, date):
            raise PackTableInvalidError(
                f"expected date, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        return value.isoformat()
    if col.type == "list_str":
        if not isinstance(value, (list, tuple)):
            raise PackTableInvalidError(
                f"expected list, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        items = list(value)
        if not items:
            if col.nullable:
                raise PackTableInvalidError(
                    f"empty list not allowed in nullable column {col.name!r}; use None",
                    line=line,
                    key=col.name,
                )
            return ""
        for item in items:
            if not isinstance(item, str):
                raise PackTableInvalidError(
                    f"list item not str ({type(item).__name__})",
                    line=line,
                    key=col.name,
                )
            if item == "":
                raise PackTableInvalidError("empty list item", line=line, key=col.name)
            if "|" in item:
                raise PackTableInvalidError("list item contains '|'", line=line, key=col.name)
        items.sort()
        return "|".join(items)
    if col.type == "dict_str_str":
        if not isinstance(value, dict):
            raise PackTableInvalidError(
                f"expected dict, got {type(value).__name__}",
                line=line,
                key=col.name,
            )
        for k, v in value.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise PackTableInvalidError(
                    "dict_str_str requires str->str",
                    line=line,
                    key=col.name,
                )
        # canonical_json returns bytes; decode for CSV cell
        return canonical_json(value).decode("utf-8")
    if col.type == "json":
        # canonical_json returns bytes; decode for CSV cell
        return canonical_json(value).decode("utf-8")
    raise PackTableInvalidError(f"unknown column type {col.type!r}", line=line, key=col.name)


def read_table(spec: TableSpec, data: bytes, *, source_name: str) -> Table:
    """Parse CSV bytes into a Table.

    Strict on encoding, headers, and cell content; does not enforce PK
    uniqueness (that check lives in the loader, K4). Every violation
    raises ``PackTableInvalidError`` with ``file``, ``line`` and (when
    applicable) ``key``.
    """
    if not isinstance(data, bytes):
        raise PackTableInvalidError(
            f"expected bytes, got {type(data).__name__}",
            file=source_name,
            line=1,
        )
    if data.startswith(b"\xef\xbb\xbf"):
        raise PackTableInvalidError("BOM not allowed", file=source_name, line=1)
    if b"\x00" in data:
        raise PackTableInvalidError("NUL byte not allowed", file=source_name, line=1)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackTableInvalidError(f"invalid UTF-8: {exc}", file=source_name, line=1) from exc
    without_crlf = text.replace("\r\n", "")
    if "\r" in without_crlf:
        raise PackTableInvalidError("bare CR not allowed", file=source_name, line=1)
    text = text.replace("\r\n", "\n")
    for offset, ch in enumerate(text, start=1):
        if ch in ("\n", "\t"):
            continue
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            line = text.count("\n", 0, offset) + 1
            raise PackTableInvalidError(
                f"control character U+{ord(ch):04X} not allowed",
                file=source_name,
                line=line,
            )

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise PackTableInvalidError("empty file", file=source_name, line=1) from None
    expected_header = [col.name for col in spec.columns]
    if header != expected_header:
        raise PackTableInvalidError(
            f"header mismatch: expected {expected_header!r}, got {header!r}",
            file=source_name,
            line=1,
        )

    records: list[dict[str, Any]] = []
    line_numbers: list[int] = []
    for raw_row in reader:
        line_num = reader.line_num
        if not raw_row or all(cell == "" for cell in raw_row):
            continue
        if len(raw_row) != len(spec.columns):
            raise PackTableInvalidError(
                f"row has {len(raw_row)} fields, expected {len(spec.columns)}",
                file=source_name,
                line=line_num,
            )
        for cell in raw_row:
            if "\n" in cell or "\r" in cell:
                raise PackTableInvalidError(
                    "multiline cell not allowed",
                    file=source_name,
                    line=line_num,
                )
        record: dict[str, Any] = {}
        for col, cell in zip(spec.columns, raw_row, strict=True):
            record[col.name] = _decode_cell(cell, col, file=source_name, line=line_num)
        records.append(record)
        line_numbers.append(line_num)

    return Table(
        spec=spec,
        source_name=source_name,
        rows=tuple(MappingProxyType(r) for r in records),
        line_numbers=tuple(line_numbers),
    )


def write_table(spec: TableSpec, rows: Iterable[Mapping[str, Any]]) -> bytes:
    """Serialise rows to canonical CSV bytes (LF endings, sorted list cells)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([col.name for col in spec.columns])
    for i, row in enumerate(rows, start=2):
        encoded: list[str] = []
        for col in spec.columns:
            if col.name not in row:
                raise PackTableInvalidError(f"missing column {col.name!r}", line=i, key=col.name)
            encoded.append(_encode_cell(row[col.name], col, line=i))
        writer.writerow(encoded)
    return buf.getvalue().encode("utf-8")
