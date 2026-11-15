//! CSV table codec: read_table, decode_cell, find_forbidden.
//!
//! Byte-identical parity with `src/agri_core/pack/tables.py` for the
//! read path. Write path (encode_cell, write_table) ships in cell 3b.
//!
//! See ADR-019 and `docs/PACK_FORMAT.md` §CSV codec. Security checks
//! (BOM, NUL, control chars, forbidden unicode, size limits) run before
//! row data reaches Pydantic.

use std::collections::BTreeMap;
use std::sync::LazyLock;

use crate::canonical::{canonical_json_rfc8785, py_float_repr};
use crate::pack::errors::PackError;

// ---- Public types ----

/// One column in a pack table.
#[derive(Debug, Clone, Copy)]
pub struct ColumnSpec {
    pub name: &'static str,
    pub ty: ColumnType,
    pub nullable: bool,
}

/// The eight cell types (mirrors Python `ColumnType` Literal).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColumnType {
    Str,
    Int,
    Float,
    Bool,
    Date,
    ListStr,
    DictStrStr,
    Json,
}

/// A parsed table cell value.
///
/// `Date` is ISO `YYYY-MM-DD` string (Pydantic parses on receipt).
/// `Json` uses `serde_json::Value` for shape-typed values and scopes;
/// this cannot hold non-finite floats (serde_json rejects them), which
/// matches Python's `json.loads` rejecting `NaN`/`Infinity` literals.
#[derive(Debug, Clone, PartialEq)]
pub enum CellValue {
    Null,
    Str(String),
    Int(i64),
    Float(f64),
    Bool(bool),
    ListStr(Vec<String>),
    DictStrStr(BTreeMap<String, String>),
    Json(serde_json::Value),
}

/// Schema for one pack table.
#[derive(Debug)]
pub struct TableSpec {
    pub name: &'static str,
    /// `None` for the `facts` table (stored as one file per taxon).
    pub filename: Option<&'static str>,
    pub columns: &'static [ColumnSpec],
    pub primary_key: &'static [&'static str],
}

/// A parsed table: spec, source label, rows, and their line numbers.
#[derive(Debug)]
pub struct Table {
    pub spec: &'static TableSpec,
    pub source_name: String,
    pub rows: Vec<BTreeMap<String, CellValue>>,
    pub line_numbers: Vec<usize>,
}

// ---- Limits (mirror tables.py) ----

pub const MAX_FIELD_BYTES: usize = 16 * 1024;
pub const MAX_ROW_BYTES: usize = 64 * 1024;

// ---- Table definitions ----

static TAXA_COLUMNS: &[ColumnSpec] = &[
    ColumnSpec {
        name: "taxon_id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "rank",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "scientific_name",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "accepted_name",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "organism_group",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "archetype",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "uses",
        ty: ColumnType::ListStr,
        nullable: false,
    },
    ColumnSpec {
        name: "traits",
        ty: ColumnType::ListStr,
        nullable: false,
    },
    ColumnSpec {
        name: "parent_id",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "external_ids",
        ty: ColumnType::DictStrStr,
        nullable: true,
    },
    ColumnSpec {
        name: "src",
        ty: ColumnType::ListStr,
        nullable: true,
    },
    ColumnSpec {
        name: "dataset_id",
        ty: ColumnType::Str,
        nullable: true,
    },
];

static NAMES_COLUMNS: &[ColumnSpec] = &[
    ColumnSpec {
        name: "taxon_id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "name",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "language",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "script",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "kind",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "preferred",
        ty: ColumnType::Bool,
        nullable: false,
    },
    ColumnSpec {
        name: "src",
        ty: ColumnType::ListStr,
        nullable: true,
    },
    ColumnSpec {
        name: "dataset_id",
        ty: ColumnType::Str,
        nullable: true,
    },
];

static FACTS_COLUMNS: &[ColumnSpec] = &[
    ColumnSpec {
        name: "fact_id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "taxon_id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "parameter",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "phase",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "value",
        ty: ColumnType::Json,
        nullable: false,
    },
    ColumnSpec {
        name: "scope",
        ty: ColumnType::Json,
        nullable: false,
    },
    ColumnSpec {
        name: "provenance_kind",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "src",
        ty: ColumnType::ListStr,
        nullable: true,
    },
    ColumnSpec {
        name: "dataset_id",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "locator",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "evidence",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "status",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "reviewed_by",
        ty: ColumnType::ListStr,
        nullable: true,
    },
    ColumnSpec {
        name: "reviewed_at",
        ty: ColumnType::Date,
        nullable: true,
    },
    ColumnSpec {
        name: "superseded_by",
        ty: ColumnType::Str,
        nullable: true,
    },
];

static HAZARDS_COLUMNS: &[ColumnSpec] = &[
    ColumnSpec {
        name: "taxon_id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "hazard_code",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "severity",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "reason",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "as_of",
        ty: ColumnType::Date,
        nullable: false,
    },
    ColumnSpec {
        name: "authority",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "src",
        ty: ColumnType::ListStr,
        nullable: true,
    },
    ColumnSpec {
        name: "dataset_id",
        ty: ColumnType::Str,
        nullable: true,
    },
];

static DATASETS_COLUMNS: &[ColumnSpec] = &[
    ColumnSpec {
        name: "dataset_id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "name",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "version",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "license",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "checksum",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "url",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "locator",
        ty: ColumnType::Str,
        nullable: true,
    },
    ColumnSpec {
        name: "access_date",
        ty: ColumnType::Date,
        nullable: false,
    },
];

static SOURCES_COLUMNS: &[ColumnSpec] = &[
    ColumnSpec {
        name: "id",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "url",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "license",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "commercial_use",
        ty: ColumnType::Str,
        nullable: false,
    },
    ColumnSpec {
        name: "access_date",
        ty: ColumnType::Date,
        nullable: false,
    },
    ColumnSpec {
        name: "citation",
        ty: ColumnType::Str,
        nullable: false,
    },
];

static TAXA_PK: &[&str] = &["taxon_id"];
static NAMES_PK: &[&str] = &["taxon_id", "name", "language", "script", "kind"];
static FACTS_PK: &[&str] = &["fact_id"];
static HAZARDS_PK: &[&str] = &["taxon_id", "hazard_code"];
static DATASETS_PK: &[&str] = &["dataset_id"];
static SOURCES_PK: &[&str] = &["id"];

static TAXA_SPEC: TableSpec = TableSpec {
    name: "taxa",
    filename: Some("taxa.csv"),
    columns: TAXA_COLUMNS,
    primary_key: TAXA_PK,
};
static NAMES_SPEC: TableSpec = TableSpec {
    name: "names",
    filename: Some("names.csv"),
    columns: NAMES_COLUMNS,
    primary_key: NAMES_PK,
};
static FACTS_SPEC: TableSpec = TableSpec {
    name: "facts",
    filename: None,
    columns: FACTS_COLUMNS,
    primary_key: FACTS_PK,
};
static HAZARDS_SPEC: TableSpec = TableSpec {
    name: "hazards",
    filename: Some("hazards.csv"),
    columns: HAZARDS_COLUMNS,
    primary_key: HAZARDS_PK,
};
static DATASETS_SPEC: TableSpec = TableSpec {
    name: "datasets",
    filename: Some("datasets.csv"),
    columns: DATASETS_COLUMNS,
    primary_key: DATASETS_PK,
};
static SOURCES_SPEC: TableSpec = TableSpec {
    name: "sources",
    filename: Some("sources.csv"),
    columns: SOURCES_COLUMNS,
    primary_key: SOURCES_PK,
};

/// All 6 table specs, keyed by table name.
pub static TABLES: LazyLock<BTreeMap<&'static str, &'static TableSpec>> = LazyLock::new(|| {
    let mut m = BTreeMap::new();
    m.insert("taxa", &TAXA_SPEC);
    m.insert("names", &NAMES_SPEC);
    m.insert("facts", &FACTS_SPEC);
    m.insert("hazards", &HAZARDS_SPEC);
    m.insert("datasets", &DATASETS_SPEC);
    m.insert("sources", &SOURCES_SPEC);
    m
});

/// Look up a table spec by name. Returns None for unknown tables.
pub fn table_spec(name: &str) -> Option<&'static TableSpec> {
    TABLES.get(name).copied()
}

// ---- find_forbidden (mirror unicode_guard.py) ----

/// Return `(codepoint, category)` of the first forbidden char.
///
/// Categories: `"bidi-control"`, `"zero-width"`, `"invisible"`.
pub fn find_forbidden(text: &str) -> Option<(u32, &'static str)> {
    for ch in text.chars() {
        let cp = ch as u32;
        match cp {
            0x202A | 0x202B | 0x202C | 0x202D | 0x202E | 0x2066 | 0x2067 | 0x2068 | 0x2069 => {
                return Some((cp, "bidi-control"));
            }
            0x200B | 0x200C | 0x200D | 0x200E | 0x200F | 0xFEFF | 0x2060 | 0x2061 | 0x2062
            | 0x2063 | 0x2064 => {
                return Some((cp, "zero-width"));
            }
            0x00AD | 0x180E => return Some((cp, "invisible")),
            0xFE00..=0xFE0F => return Some((cp, "invisible")),
            _ => {}
        }
    }
    None
}

// ---- JSON dup-key detection (custom recursive visitor) ----

struct RejectDupSeed;

impl<'de> serde::de::DeserializeSeed<'de> for RejectDupSeed {
    type Value = serde_json::Value;
    fn deserialize<D>(self, d: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        d.deserialize_any(RejectDupValue)
    }
}

struct RejectDupValue;

impl<'de> serde::de::Visitor<'de> for RejectDupValue {
    type Value = serde_json::Value;
    fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str("a JSON value with no duplicate object keys")
    }
    fn visit_bool<E: serde::de::Error>(self, v: bool) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Bool(v))
    }
    fn visit_i64<E: serde::de::Error>(self, v: i64) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Number(v.into()))
    }
    fn visit_u64<E: serde::de::Error>(self, v: u64) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Number(v.into()))
    }
    fn visit_f64<E: serde::de::Error>(self, v: f64) -> Result<Self::Value, E> {
        serde_json::Number::from_f64(v)
            .map(serde_json::Value::Number)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }
    fn visit_str<E: serde::de::Error>(self, v: &str) -> Result<Self::Value, E> {
        Ok(serde_json::Value::String(v.to_string()))
    }
    fn visit_string<E: serde::de::Error>(self, v: String) -> Result<Self::Value, E> {
        Ok(serde_json::Value::String(v))
    }
    fn visit_unit<E: serde::de::Error>(self) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Null)
    }
    fn visit_none<E: serde::de::Error>(self) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Null)
    }
    fn visit_some<D: serde::Deserializer<'de>>(self, d: D) -> Result<Self::Value, D::Error> {
        d.deserialize_any(RejectDupValue)
    }
    fn visit_seq<A: serde::de::SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
        let mut out = Vec::new();
        while let Some(item) = seq.next_element_seed(RejectDupSeed)? {
            out.push(item);
        }
        Ok(serde_json::Value::Array(out))
    }
    fn visit_map<A: serde::de::MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        let mut out = serde_json::Map::new();
        while let Some(k) = map.next_key::<String>()? {
            if out.contains_key(&k) {
                return Err(serde::de::Error::custom(format!(
                    "duplicate JSON key {k:?}"
                )));
            }
            let v = map.next_value_seed(RejectDupSeed)?;
            out.insert(k, v);
        }
        Ok(serde_json::Value::Object(out))
    }
}

pub fn parse_json_no_dup(s: &str) -> Result<serde_json::Value, String> {
    use serde::de::Deserializer as _;
    let mut de = serde_json::Deserializer::from_str(s);
    let v = de
        .deserialize_any(RejectDupValue)
        .map_err(|e| e.to_string())?;
    de.end().map_err(|e| e.to_string())?;
    Ok(v)
}

// ---- decode_cell (mirror _decode_cell) ----

/// Parse a strict YYYY-MM-DD date and validate month/day ranges.
///
/// Mirrors Python's `date.fromisoformat` for the pack's date columns:
/// rejects impossible dates (2026-02-29 non-leap, 2026-04-31).
/// Uses `split_once` (no indexing) so it passes clippy::indexing_slicing.
fn parse_iso_date(value: &str) -> Result<(), String> {
    let (year_part, rest) = value
        .split_once('-')
        .ok_or_else(|| format!("expected ISO date YYYY-MM-DD, got {value:?}"))?;
    let (month_part, day_part) = rest
        .split_once('-')
        .ok_or_else(|| format!("expected ISO date YYYY-MM-DD, got {value:?}"))?;
    if year_part.len() != 4 || month_part.len() != 2 || day_part.len() != 2 {
        return Err(format!("expected ISO date YYYY-MM-DD, got {value:?}"));
    }
    if !year_part.chars().all(|c| c.is_ascii_digit())
        || !month_part.chars().all(|c| c.is_ascii_digit())
        || !day_part.chars().all(|c| c.is_ascii_digit())
    {
        return Err(format!("expected ISO date YYYY-MM-DD, got {value:?}"));
    }
    let year: u32 = year_part
        .parse()
        .map_err(|e: std::num::ParseIntError| e.to_string())?;
    let month: u32 = month_part
        .parse()
        .map_err(|e: std::num::ParseIntError| e.to_string())?;
    let day: u32 = day_part
        .parse()
        .map_err(|e: std::num::ParseIntError| e.to_string())?;
    if !(1..=12).contains(&month) {
        return Err(format!("invalid date components {value:?}"));
    }
    let days_in_month = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if (year.is_multiple_of(4) && !year.is_multiple_of(100)) || year.is_multiple_of(400) {
                29
            } else {
                28
            }
        }
        _ => return Err(format!("invalid date components {value:?}")),
    };
    if !(1..=days_in_month).contains(&day) {
        return Err(format!("invalid date components {value:?}"));
    }
    Ok(())
}

fn decode_cell(
    value: &str,
    col: &ColumnSpec,
    file: &str,
    line: usize,
) -> Result<CellValue, PackError> {
    let is_empty = value.is_empty();
    if is_empty {
        if col.nullable {
            return Ok(CellValue::Null);
        }
        if col.ty == ColumnType::ListStr {
            return Ok(CellValue::ListStr(Vec::new()));
        }
        return Err(PackError::table_invalid(format!(
            "empty cell in required column {:?}",
            col.name
        ))
        .with_file(file)
        .with_line(line)
        .with_key(col.name));
    }
    let err = |msg: String| {
        PackError::table_invalid(format!(
            "invalid {:?} in column {:?}: {msg}",
            col.ty, col.name
        ))
        .with_file(file)
        .with_line(line)
        .with_key(col.name)
    };
    match col.ty {
        ColumnType::Str => Ok(CellValue::Str(value.to_string())),
        ColumnType::Int => value
            .parse::<i64>()
            .map(CellValue::Int)
            .map_err(|e| err(e.to_string())),
        ColumnType::Float => value
            .parse::<f64>()
            .map(CellValue::Float)
            .map_err(|e| err(e.to_string())),
        ColumnType::Bool => match value {
            "true" => Ok(CellValue::Bool(true)),
            "false" => Ok(CellValue::Bool(false)),
            _ => Err(err(format!("expected 'true' or 'false', got {value:?}"))),
        },
        ColumnType::Date => {
            parse_iso_date(value).map_err(err)?;
            Ok(CellValue::Str(value.to_string()))
        }
        ColumnType::ListStr => {
            let parts: Vec<&str> = value.split('|').collect();
            let mut out: Vec<String> = Vec::with_capacity(parts.len());
            for item in parts {
                if item.is_empty() {
                    return Err(err("empty item in list cell".to_string()));
                }
                out.push(item.to_string());
            }
            Ok(CellValue::ListStr(out))
        }
        ColumnType::DictStrStr => {
            let v = parse_json_no_dup(value).map_err(err)?;
            let obj = v
                .as_object()
                .ok_or_else(|| err(format!("expected JSON object, got {:?}", v)))?;
            let mut out = BTreeMap::new();
            for (k, vv) in obj {
                let s = vv.as_str().ok_or_else(|| {
                    err("dict_str_str requires string keys and values".to_string())
                })?;
                out.insert(k.clone(), s.to_string());
            }
            Ok(CellValue::DictStrStr(out))
        }
        ColumnType::Json => parse_json_no_dup(value).map(CellValue::Json).map_err(err),
    }
}

// ---- read_table ----

pub fn read_table(
    spec: &'static TableSpec,
    data: &[u8],
    source_name: &str,
) -> Result<Table, PackError> {
    // BOM check
    if data.starts_with(b"\xef\xbb\xbf") {
        return Err(PackError::table_invalid("BOM not allowed".to_string())
            .with_file(source_name)
            .with_line(1));
    }
    // NUL check
    if data.contains(&0u8) {
        return Err(PackError::table_invalid("NUL byte not allowed".to_string())
            .with_file(source_name)
            .with_line(1));
    }
    // UTF-8 decode
    let text = std::str::from_utf8(data).map_err(|e| {
        PackError::table_invalid(format!("invalid UTF-8: {e}"))
            .with_file(source_name)
            .with_line(1)
    })?;
    // Bare CR check + CRLF -> LF
    let without_crlf = text.replace("\r\n", "");
    if without_crlf.contains('\r') {
        return Err(PackError::table_invalid("bare CR not allowed".to_string())
            .with_file(source_name)
            .with_line(1));
    }
    let text = text.replace("\r\n", "\n");
    // Per-char: allow LF, TAB; reject control chars and forbidden unicode.
    let mut line_count = 1usize;
    for ch in text.chars() {
        if ch == '\n' {
            line_count += 1;
            continue;
        }
        if ch == '\t' {
            continue;
        }
        let cp = ch as u32;
        if cp < 0x20 || cp == 0x7F {
            return Err(PackError::table_invalid(format!(
                "control character U+{cp:04X} not allowed"
            ))
            .with_file(source_name)
            .with_line(line_count));
        }
        if let Some((bad_cp, cat)) = find_forbidden(&ch.to_string()) {
            return Err(PackError::table_invalid(format!(
                "{cat} character U+{bad_cp:04X} not allowed"
            ))
            .with_file(source_name)
            .with_line(line_count));
        }
    }
    // CSV parse (flexible=true; per-row count checked below)
    let mut rdr = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .from_reader(text.as_bytes());
    let mut records = rdr.records();
    let header = match records.next() {
        Some(Ok(h)) => h,
        Some(Err(e)) => {
            return Err(PackError::table_invalid(format!("CSV parse: {e}"))
                .with_file(source_name)
                .with_line(1));
        }
        None => {
            return Err(PackError::table_invalid("empty file".to_string())
                .with_file(source_name)
                .with_line(1));
        }
    };
    let expected_header: Vec<&str> = spec.columns.iter().map(|c| c.name).collect();
    let got_header: Vec<&str> = header.iter().collect();
    if got_header != expected_header {
        return Err(PackError::table_invalid(format!(
            "header mismatch: expected {expected_header:?}, got {got_header:?}"
        ))
        .with_file(source_name)
        .with_line(1));
    }
    // Rows
    let mut rows: Vec<BTreeMap<String, CellValue>> = Vec::new();
    let mut line_numbers: Vec<usize> = Vec::new();
    // csv reader line_num is 1-based including header
    let mut current_line = 1usize;
    for raw_row in records {
        let rec = raw_row.map_err(|e| {
            PackError::table_invalid(format!("CSV parse: {e}"))
                .with_file(source_name)
                .with_line(current_line)
        })?;
        current_line += 1;
        // Skip blank rows (all cells empty)
        if rec.iter().all(|c| c.is_empty()) {
            continue;
        }
        if rec.len() != spec.columns.len() {
            return Err(PackError::table_invalid(format!(
                "row has {} fields, expected {}",
                rec.len(),
                spec.columns.len()
            ))
            .with_file(source_name)
            .with_line(current_line));
        }
        // Multiline / row-size check
        let mut row_bytes = 0usize;
        for cell in rec.iter() {
            if cell.contains('\n') || cell.contains('\r') {
                return Err(
                    PackError::table_invalid("multiline cell not allowed".to_string())
                        .with_file(source_name)
                        .with_line(current_line),
                );
            }
            let n = cell.len();
            if n > MAX_FIELD_BYTES {
                return Err(PackError::field_too_large(format!(
                    "cell exceeds {MAX_FIELD_BYTES} bytes (got {n})"
                ))
                .with_file(source_name)
                .with_line(current_line));
            }
            row_bytes = row_bytes.saturating_add(n);
        }
        if row_bytes > MAX_ROW_BYTES {
            return Err(PackError::row_too_large(format!(
                "row exceeds {MAX_ROW_BYTES} bytes (got {row_bytes})"
            ))
            .with_file(source_name)
            .with_line(current_line));
        }
        // Decode each cell
        let mut row: BTreeMap<String, CellValue> = BTreeMap::new();
        for (col, cell) in spec.columns.iter().zip(rec.iter()) {
            let v = decode_cell(cell, col, source_name, current_line)?;
            row.insert(col.name.to_string(), v);
        }
        rows.push(row);
        line_numbers.push(current_line);
    }
    Ok(Table {
        spec,
        source_name: source_name.to_string(),
        rows,
        line_numbers,
    })
}

// ---- Tests ----

// ---- encode_cell (mirror _encode_cell) ----

fn encode_cell(value: &CellValue, col: &ColumnSpec, line: usize) -> Result<String, PackError> {
    let err = |msg: String| {
        PackError::table_invalid(msg)
            .with_line(line)
            .with_key(col.name)
    };
    if matches!(value, CellValue::Null) {
        if !col.nullable {
            return Err(err(format!("None in non-nullable column {:?}", col.name)));
        }
        return Ok(String::new());
    }
    match (col.ty, value) {
        (ColumnType::Str, CellValue::Str(s)) => Ok(s.clone()),
        (ColumnType::Int, CellValue::Int(i)) => Ok(i.to_string()),
        (ColumnType::Float, CellValue::Float(f)) => {
            if f.is_nan() {
                Ok("nan".to_string())
            } else if f.is_infinite() {
                Ok(if *f > 0.0 {
                    "inf".to_string()
                } else {
                    "-inf".to_string()
                })
            } else {
                Ok(py_float_repr(*f))
            }
        }
        (ColumnType::Bool, CellValue::Bool(b)) => Ok(if *b {
            "true".to_string()
        } else {
            "false".to_string()
        }),
        (ColumnType::Date, CellValue::Str(s)) => {
            parse_iso_date(s).map_err(err)?;
            Ok(s.clone())
        }
        (ColumnType::ListStr, CellValue::ListStr(items)) => {
            if items.is_empty() {
                if col.nullable {
                    return Err(err(format!(
                        "empty list not allowed in nullable column {:?}; use None",
                        col.name
                    )));
                }
                return Ok(String::new());
            }
            let mut sorted: Vec<&str> = Vec::with_capacity(items.len());
            for item in items {
                if item.is_empty() {
                    return Err(err("empty list item".to_string()));
                }
                if item.contains('|') {
                    return Err(err("list item contains '|'".to_string()));
                }
                sorted.push(item.as_str());
            }
            sorted.sort();
            Ok(sorted.join("|"))
        }
        (ColumnType::DictStrStr, CellValue::DictStrStr(m)) => {
            let mut obj = serde_json::Map::with_capacity(m.len());
            for (k, v) in m {
                obj.insert(k.clone(), serde_json::Value::String(v.clone()));
            }
            let v = serde_json::Value::Object(obj);
            let bytes = canonical_json_rfc8785(&v).map_err(|e| err(format!("canonical: {e}")))?;
            String::from_utf8(bytes).map_err(|e| err(format!("utf8: {e}")))
        }
        (ColumnType::Json, CellValue::Json(v)) => {
            let bytes = canonical_json_rfc8785(v).map_err(|e| err(format!("canonical: {e}")))?;
            String::from_utf8(bytes).map_err(|e| err(format!("utf8: {e}")))
        }
        _ => Err(err(format!(
            "column {:?} expects {:?}, got {:?}",
            col.name,
            column_type_tag(col.ty),
            value_tag(value)
        ))),
    }
}

fn column_type_tag(t: ColumnType) -> &'static str {
    match t {
        ColumnType::Str => "str",
        ColumnType::Int => "int",
        ColumnType::Float => "float",
        ColumnType::Bool => "bool",
        ColumnType::Date => "date",
        ColumnType::ListStr => "list_str",
        ColumnType::DictStrStr => "dict_str_str",
        ColumnType::Json => "json",
    }
}

fn value_tag(v: &CellValue) -> &'static str {
    match v {
        CellValue::Null => "null",
        CellValue::Str(_) => "str",
        CellValue::Int(_) => "int",
        CellValue::Float(_) => "float",
        CellValue::Bool(_) => "bool",
        CellValue::ListStr(_) => "list_str",
        CellValue::DictStrStr(_) => "dict_str_str",
        CellValue::Json(_) => "json",
    }
}

// ---- write_table ----

/// Serialise rows to canonical CSV bytes (LF line endings, sorted list cells).
///
/// Mirror of Python `write_table`. Uses `py_float_repr` so float cells are
/// byte-identical to Python's `repr(float())` (2-digit exponent padding).
pub fn write_table(
    spec: &'static TableSpec,
    rows: &[BTreeMap<String, CellValue>],
) -> Result<Vec<u8>, PackError> {
    let mut wtr = csv::WriterBuilder::new()
        .terminator(csv::Terminator::Any(b'\n'))
        .quote_style(csv::QuoteStyle::Necessary)
        .from_writer(Vec::new());

    let header: Vec<&str> = spec.columns.iter().map(|c| c.name).collect();
    wtr.write_record(&header)
        .map_err(|e| PackError::table_invalid(format!("CSV header: {e}")).with_file(spec.name))?;

    for (i, row) in rows.iter().enumerate() {
        let line = i + 2;
        let mut encoded = Vec::with_capacity(spec.columns.len());
        for col in spec.columns.iter() {
            let v = row.get(col.name).ok_or_else(|| {
                PackError::table_invalid(format!("missing column {:?}", col.name))
                    .with_line(line)
                    .with_key(col.name)
            })?;
            encoded.push(encode_cell(v, col, line)?);
        }
        wtr.write_record(&encoded).map_err(|e| {
            PackError::table_invalid(format!("CSV row {line}: {e}")).with_line(line)
        })?;
    }

    wtr.into_inner()
        .map_err(|e| PackError::table_invalid(format!("CSV flush: {e}")))
}

/// Convert a row `BTreeMap<String, CellValue>` to `serde_json::Value` object.
///
/// Used by `validate.rs` (re-parse tables → JSON → row_types conversion).
/// Deterministic ordering via serde_json::Map (no HashMap).
pub fn cellmap_to_json(map: &BTreeMap<String, CellValue>) -> serde_json::Value {
    let mut obj = serde_json::Map::with_capacity(map.len());
    for (k, v) in map {
        obj.insert(k.clone(), cell_to_json(v));
    }
    serde_json::Value::Object(obj)
}

fn cell_to_json(v: &CellValue) -> serde_json::Value {
    match v {
        CellValue::Null => serde_json::Value::Null,
        CellValue::Str(s) => serde_json::Value::String(s.clone()),
        CellValue::Int(i) => serde_json::Value::Number((*i).into()),
        CellValue::Float(f) => serde_json::Number::from_f64(*f)
            .map(serde_json::Value::Number)
            .unwrap_or(serde_json::Value::Null),
        CellValue::Bool(b) => serde_json::Value::Bool(*b),
        CellValue::ListStr(items) => serde_json::Value::Array(
            items
                .iter()
                .map(|s| serde_json::Value::String(s.clone()))
                .collect(),
        ),
        CellValue::DictStrStr(m) => {
            let mut o = serde_json::Map::with_capacity(m.len());
            for (k, v) in m {
                o.insert(k.clone(), serde_json::Value::String(v.clone()));
            }
            serde_json::Value::Object(o)
        }
        CellValue::Json(j) => j.clone(),
    }
}

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
mod tests {
    use super::*;

    fn sources_spec() -> &'static TableSpec {
        table_spec("sources").expect("sources spec")
    }

    #[test]
    fn read_simple_table() {
        let csv = b"id,url,license,commercial_use,access_date,citation\n\
                    S001,https://x,CC0-1.0,yes,2026-01-01,Test\n";
        let t = read_table(sources_spec(), csv, "sources.csv").expect("read");
        assert_eq!(t.rows.len(), 1);
        assert_eq!(t.line_numbers, vec![2]);
        assert_eq!(t.rows[0].get("id"), Some(&CellValue::Str("S001".into())));
    }

    #[test]
    fn read_rejects_bom() {
        let csv = b"\xef\xbb\xbfid,url,license,commercial_use,access_date,citation\n";
        let e = read_table(sources_spec(), csv, "sources.csv").unwrap_err();
        assert_eq!(e.code, "PACK_TABLE_INVALID");
        assert!(e.message.contains("BOM"));
    }

    #[test]
    fn read_rejects_nul() {
        let csv = b"id,url,license,commercial_use,access_date,citation\nS\x00,https://x,CC0-1.0,yes,2026-01-01,x\n";
        let e = read_table(sources_spec(), csv, "sources.csv").unwrap_err();
        assert!(e.message.contains("NUL"));
    }

    #[test]
    fn read_rejects_bare_cr() {
        let csv = b"id,url,license,commercial_use,access_date,citation\rX\n";
        let e = read_table(sources_spec(), csv, "sources.csv").unwrap_err();
        assert!(e.message.contains("bare CR"));
    }

    #[test]
    fn read_accepts_crlf() {
        let csv = b"id,url,license,commercial_use,access_date,citation\r\nS001,https://x,CC0-1.0,yes,2026-01-01,x\r\n";
        let t = read_table(sources_spec(), csv, "sources.csv").expect("read");
        assert_eq!(t.rows.len(), 1);
    }

    #[test]
    fn read_rejects_header_mismatch() {
        let csv = b"wrong,header\n";
        let e = read_table(sources_spec(), csv, "sources.csv").unwrap_err();
        assert!(e.message.contains("header mismatch"));
    }

    #[test]
    fn read_rejects_wrong_field_count() {
        let csv = b"id,url,license,commercial_use,access_date,citation\nS001,https://x\n";
        let e = read_table(sources_spec(), csv, "sources.csv").unwrap_err();
        assert!(e.message.contains("fields"));
    }

    #[test]
    fn read_rejects_empty_required_cell() {
        let csv = b"id,url,license,commercial_use,access_date,citation\n,https://x,CC0-1.0,yes,2026-01-01,x\n";
        let e = read_table(sources_spec(), csv, "sources.csv").unwrap_err();
        assert!(e.message.contains("empty cell"));
    }

    #[test]
    fn decode_bool_validates() {
        let col = ColumnSpec {
            name: "preferred",
            ty: ColumnType::Bool,
            nullable: false,
        };
        let v = decode_cell("true", &col, "t.csv", 1).unwrap();
        assert_eq!(v, CellValue::Bool(true));
        let e = decode_cell("Y", &col, "t.csv", 1).unwrap_err();
        assert!(e.message.contains("true"));
    }

    #[test]
    fn find_forbidden_categories() {
        assert_eq!(find_forbidden("abc"), None);
        assert_eq!(find_forbidden("a\u{202A}b"), Some((0x202A, "bidi-control")));
        assert_eq!(find_forbidden("a\u{200B}b"), Some((0x200B, "zero-width")));
        assert_eq!(find_forbidden("a\u{00AD}b"), Some((0x00AD, "invisible")));
        assert_eq!(find_forbidden("a\u{FE00}b"), Some((0xFE00, "invisible")));
    }

    #[test]
    fn json_dup_key_rejected() {
        let col = ColumnSpec {
            name: "value",
            ty: ColumnType::Json,
            nullable: false,
        };
        let e = decode_cell(r#"{"a":1,"a":2}"#, &col, "f.csv", 1).unwrap_err();
        assert!(e.message.contains("duplicate"), "got: {}", e.message);
    }

    #[test]
    fn json_nested_dup_key_rejected() {
        let col = ColumnSpec {
            name: "value",
            ty: ColumnType::Json,
            nullable: false,
        };
        let e = decode_cell(r#"{"outer":{"a":1,"a":2}}"#, &col, "f.csv", 1).unwrap_err();
        assert!(e.message.contains("duplicate"), "got: {}", e.message);
    }

    #[test]
    fn json_ok() {
        let col = ColumnSpec {
            name: "value",
            ty: ColumnType::Json,
            nullable: false,
        };
        let v = decode_cell(r#"{"shape":"scalar","value":8.0}"#, &col, "f.csv", 1).unwrap();
        match v {
            CellValue::Json(j) => assert_eq!(j["shape"], "scalar"),
            _ => panic!("expected Json"),
        }
    }

    #[test]
    fn table_spec_lookup() {
        assert!(table_spec("taxa").is_some());
        assert!(table_spec("facts").is_some());
        assert!(table_spec("bogus").is_none());
    }

    #[test]
    fn facts_table_spec_has_no_filename() {
        let s = table_spec("facts").unwrap();
        assert!(s.filename.is_none());
    }

    #[test]
    fn date_accepts_leap_year_feb_29() {
        let col = ColumnSpec {
            name: "reviewed_at",
            ty: ColumnType::Date,
            nullable: true,
        };
        let v = decode_cell("2024-02-29", &col, "f.csv", 1).unwrap();
        assert_eq!(v, CellValue::Str("2024-02-29".to_string()));
    }

    #[test]
    fn date_rejects_non_leap_year_feb_29() {
        let col = ColumnSpec {
            name: "reviewed_at",
            ty: ColumnType::Date,
            nullable: true,
        };
        let e = decode_cell("2026-02-29", &col, "f.csv", 1).unwrap_err();
        assert!(e.message.contains("invalid date"), "got: {}", e.message);
    }
}

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
mod tests_write {
    use super::*;

    fn sources_spec() -> &'static TableSpec {
        table_spec("sources").expect("sources spec")
    }

    fn empty_sources_row() -> BTreeMap<String, CellValue> {
        let mut m = BTreeMap::new();
        m.insert("id".into(), CellValue::Str("S001".into()));
        m.insert("url".into(), CellValue::Str("https://example.org".into()));
        m.insert("license".into(), CellValue::Str("CC0-1.0".into()));
        m.insert("commercial_use".into(), CellValue::Str("yes".into()));
        m.insert("access_date".into(), CellValue::Str("2026-01-01".into()));
        m.insert("citation".into(), CellValue::Str("Test source".into()));
        m
    }

    #[test]
    fn write_header_only() {
        let out = write_table(sources_spec(), &[]).unwrap();
        let s = std::str::from_utf8(&out).unwrap();
        assert_eq!(s, "id,url,license,commercial_use,access_date,citation\n");
    }

    #[test]
    fn write_one_row() {
        let row = empty_sources_row();
        let out = write_table(sources_spec(), &[row]).unwrap();
        let s = std::str::from_utf8(&out).unwrap();
        assert_eq!(
            s,
            "id,url,license,commercial_use,access_date,citation\n\
             S001,https://example.org,CC0-1.0,yes,2026-01-01,Test source\n"
        );
    }

    #[test]
    fn write_missing_column_errors() {
        let mut row = empty_sources_row();
        row.remove("url");
        let e = write_table(sources_spec(), &[row]).unwrap_err();
        assert_eq!(e.code, "PACK_TABLE_INVALID");
        assert!(e.message.contains("missing column"), "got: {}", e.message);
        assert_eq!(e.line, Some(2));
    }

    #[test]
    fn write_null_in_non_nullable_errors() {
        let mut row = empty_sources_row();
        row.insert("id".into(), CellValue::Null);
        let e = write_table(sources_spec(), &[row]).unwrap_err();
        assert!(e.message.contains("non-nullable"), "got: {}", e.message);
    }

    #[test]
    fn encode_int() {
        let col = ColumnSpec {
            name: "n",
            ty: ColumnType::Int,
            nullable: false,
        };
        assert_eq!(encode_cell(&CellValue::Int(42), &col, 1).unwrap(), "42");
        assert_eq!(encode_cell(&CellValue::Int(-1), &col, 1).unwrap(), "-1");
    }

    #[test]
    fn encode_float_simple() {
        let col = ColumnSpec {
            name: "f",
            ty: ColumnType::Float,
            nullable: false,
        };
        assert_eq!(encode_cell(&CellValue::Float(8.0), &col, 1).unwrap(), "8.0");
        assert_eq!(
            encode_cell(&CellValue::Float(0.65), &col, 1).unwrap(),
            "0.65"
        );
    }

    #[test]
    fn encode_float_exponent_padded() {
        // Python repr(1e-7) = "1e-07" (2-digit exp). py_float_repr must match.
        let col = ColumnSpec {
            name: "f",
            ty: ColumnType::Float,
            nullable: false,
        };
        assert_eq!(
            encode_cell(&CellValue::Float(1e-7), &col, 1).unwrap(),
            "1e-07"
        );
        assert_eq!(
            encode_cell(&CellValue::Float(1e21), &col, 1).unwrap(),
            "1e+21"
        );
    }

    #[test]
    fn encode_float_nan_inf() {
        let col = ColumnSpec {
            name: "f",
            ty: ColumnType::Float,
            nullable: false,
        };
        assert_eq!(
            encode_cell(&CellValue::Float(f64::NAN), &col, 1).unwrap(),
            "nan"
        );
        assert_eq!(
            encode_cell(&CellValue::Float(f64::INFINITY), &col, 1).unwrap(),
            "inf"
        );
        assert_eq!(
            encode_cell(&CellValue::Float(f64::NEG_INFINITY), &col, 1).unwrap(),
            "-inf"
        );
    }

    #[test]
    fn encode_bool() {
        let col = ColumnSpec {
            name: "b",
            ty: ColumnType::Bool,
            nullable: false,
        };
        assert_eq!(
            encode_cell(&CellValue::Bool(true), &col, 1).unwrap(),
            "true"
        );
        assert_eq!(
            encode_cell(&CellValue::Bool(false), &col, 1).unwrap(),
            "false"
        );
    }

    #[test]
    fn encode_date_validates() {
        let col = ColumnSpec {
            name: "d",
            ty: ColumnType::Date,
            nullable: false,
        };
        assert_eq!(
            encode_cell(&CellValue::Str("2026-01-01".into()), &col, 1).unwrap(),
            "2026-01-01"
        );
        let e = encode_cell(&CellValue::Str("2026-02-30".into()), &col, 1).unwrap_err();
        assert!(e.message.contains("invalid date"), "got: {}", e.message);
    }

    #[test]
    fn encode_list_str_sorted() {
        let col = ColumnSpec {
            name: "l",
            ty: ColumnType::ListStr,
            nullable: false,
        };
        let v = CellValue::ListStr(vec!["b".into(), "a".into(), "c".into()]);
        assert_eq!(encode_cell(&v, &col, 1).unwrap(), "a|b|c");
    }

    #[test]
    fn encode_list_str_empty_non_nullable() {
        let col = ColumnSpec {
            name: "l",
            ty: ColumnType::ListStr,
            nullable: false,
        };
        let v = CellValue::ListStr(vec![]);
        assert_eq!(encode_cell(&v, &col, 1).unwrap(), "");
    }

    #[test]
    fn encode_list_str_empty_nullable_errors() {
        let col = ColumnSpec {
            name: "l",
            ty: ColumnType::ListStr,
            nullable: true,
        };
        let v = CellValue::ListStr(vec![]);
        let e = encode_cell(&v, &col, 1).unwrap_err();
        assert!(
            e.message.contains("empty list not allowed"),
            "got: {}",
            e.message
        );
    }

    #[test]
    fn encode_list_str_rejects_pipe() {
        let col = ColumnSpec {
            name: "l",
            ty: ColumnType::ListStr,
            nullable: false,
        };
        let v = CellValue::ListStr(vec!["a|b".into()]);
        let e = encode_cell(&v, &col, 1).unwrap_err();
        assert!(e.message.contains("'|'"), "got: {}", e.message);
    }

    #[test]
    fn encode_dict_str_str_canonical() {
        let col = ColumnSpec {
            name: "d",
            ty: ColumnType::DictStrStr,
            nullable: true,
        };
        let mut m = BTreeMap::new();
        m.insert("b".into(), "2".into());
        m.insert("a".into(), "1".into());
        let v = CellValue::DictStrStr(m);
        assert_eq!(encode_cell(&v, &col, 1).unwrap(), r#"{"a":"1","b":"2"}"#);
    }

    #[test]
    fn encode_json_canonical() {
        let col = ColumnSpec {
            name: "v",
            ty: ColumnType::Json,
            nullable: false,
        };
        let mut obj = serde_json::Map::new();
        obj.insert("shape".into(), serde_json::Value::String("scalar".into()));
        obj.insert(
            "value".into(),
            serde_json::Number::from_f64(8.0)
                .map(serde_json::Value::Number)
                .unwrap(),
        );
        let v = CellValue::Json(serde_json::Value::Object(obj));
        let out = encode_cell(&v, &col, 1).unwrap();
        assert!(out.contains(r#""shape":"scalar""#), "got: {out}");
    }

    #[test]
    fn encode_type_mismatch_errors() {
        let col = ColumnSpec {
            name: "i",
            ty: ColumnType::Int,
            nullable: false,
        };
        let e = encode_cell(&CellValue::Str("abc".into()), &col, 1).unwrap_err();
        assert!(e.message.contains("expects"), "got: {}", e.message);
    }

    #[test]
    fn roundtrip_sources() {
        let row = empty_sources_row();
        let bytes = write_table(sources_spec(), std::slice::from_ref(&row)).unwrap();
        let t = read_table(sources_spec(), &bytes, "sources.csv").unwrap();
        assert_eq!(t.rows.len(), 1);
        for (k, v) in &row {
            assert_eq!(t.rows[0].get(k), Some(v), "column {k}");
        }
    }
}
