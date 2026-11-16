//! Rust mirrors of Python row models (pure Rust, no pyo3).
//!
//! `agri-kernel` is pure Rust (ADR-019). PyDict conversion lives in
//! `agri-py/src/pack.rs`; this module takes `serde_json::Value` which
//! `agri-py` produces via its existing `py_to_json_value` helper (from
//! Phase B).
//!
//! Purpose: Phase D rules (`rules/*.rs`) operate on these structs.
//! Pydantic validates upstream; if a dict reaches here it's already
//! schema-valid. Missing key = programmer bug → `ConvertError::MissingKey`.

use serde_json::Value;

use crate::canonical::canonical_json_rfc8785;

// ---- Errors ----

#[derive(Debug)]
pub enum ConvertError {
    MissingKey(&'static str),
    WrongType {
        key: &'static str,
        expected: &'static str,
    },
    BadShape {
        shape: String,
    },
    BadTrapezoid {
        len: usize,
    },
    Canonical(String),
}

impl std::fmt::Display for ConvertError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConvertError::MissingKey(k) => write!(f, "missing key {k:?}"),
            ConvertError::WrongType { key, expected } => {
                write!(f, "key {key:?} wrong type (expected {expected})")
            }
            ConvertError::BadShape { shape } => write!(f, "unknown FactValue shape {shape:?}"),
            ConvertError::BadTrapezoid { len } => {
                write!(f, "trapezoid pts must have 4 elements, got {len}")
            }
            ConvertError::Canonical(m) => write!(f, "canonical: {m}"),
        }
    }
}

impl std::error::Error for ConvertError {}

// ---- FactValue (8 shapes, discriminated by `shape`) ----

#[derive(Debug, Clone, PartialEq)]
pub enum FactValue {
    Trapezoid { unit: String, pts: [f64; 4] },
    Range { unit: String, min: f64, max: f64 },
    Scalar { unit: String, value: f64 },
    Enum { value: String },
    EnumSet { values: Vec<String> },
    Bool { value: bool },
    Rule { data_json: String },
    Unknown { reason: String },
}

impl FactValue {
    pub fn shape(&self) -> &'static str {
        match self {
            FactValue::Trapezoid { .. } => "trapezoid",
            FactValue::Range { .. } => "range",
            FactValue::Scalar { .. } => "scalar",
            FactValue::Enum { .. } => "enum",
            FactValue::EnumSet { .. } => "enum_set",
            FactValue::Bool { .. } => "bool",
            FactValue::Rule { .. } => "rule",
            FactValue::Unknown { .. } => "unknown",
        }
    }

    pub fn unit(&self) -> Option<&str> {
        match self {
            FactValue::Trapezoid { unit, .. } => Some(unit),
            FactValue::Range { unit, .. } => Some(unit),
            FactValue::Scalar { unit, .. } => Some(unit),
            _ => None,
        }
    }
}

fn get_str<'a>(v: &'a Value, k: &'static str) -> Result<&'a str, ConvertError> {
    v.get(k)
        .and_then(|x| x.as_str())
        .ok_or(ConvertError::MissingKey(k))
}

fn get_opt_str(v: &Value, k: &'static str) -> Option<String> {
    v.get(k).and_then(|x| x.as_str()).map(|s| s.to_string())
}

fn get_f64(v: &Value, k: &'static str) -> Result<f64, ConvertError> {
    v.get(k)
        .and_then(|x| x.as_f64())
        .ok_or(ConvertError::MissingKey(k))
}

fn get_bool(v: &Value, k: &'static str) -> Result<bool, ConvertError> {
    match v.get(k) {
        Some(Value::Bool(b)) => Ok(*b),
        Some(Value::Number(n)) => {
            if let Some(i) = n.as_i64() {
                return Ok(i != 0);
            }
            if let Some(f) = n.as_f64() {
                return Ok(f != 0.0);
            }
            Err(ConvertError::WrongType {
                key: k,
                expected: "bool",
            })
        }
        Some(Value::String(s)) => match s.as_str() {
            "true" | "1" => Ok(true),
            "false" | "0" => Ok(false),
            _ => Err(ConvertError::WrongType {
                key: k,
                expected: "bool",
            }),
        },
        _ => Err(ConvertError::MissingKey(k)),
    }
}

fn get_list_str(v: &Value, k: &'static str) -> Result<Vec<String>, ConvertError> {
    let arr = v
        .get(k)
        .and_then(|x| x.as_array())
        .ok_or(ConvertError::MissingKey(k))?;
    let mut out = Vec::with_capacity(arr.len());
    for item in arr {
        out.push(
            item.as_str()
                .ok_or(ConvertError::WrongType {
                    key: k,
                    expected: "str",
                })?
                .to_string(),
        );
    }
    Ok(out)
}

fn get_opt_list_str(v: &Value, k: &'static str) -> Result<Option<Vec<String>>, ConvertError> {
    match v.get(k) {
        None | Some(Value::Null) => Ok(None),
        Some(_) => Ok(Some(get_list_str(v, k)?)),
    }
}

pub fn fact_value_from_json(v: &Value) -> Result<FactValue, ConvertError> {
    let shape = get_str(v, "shape")?.to_string();
    match shape.as_str() {
        "trapezoid" => {
            let unit = get_str(v, "unit")?.to_string();
            let pts_arr = v
                .get("pts")
                .and_then(|x| x.as_array())
                .ok_or(ConvertError::MissingKey("pts"))?;
            let pts_vec: Vec<f64> = pts_arr
                .iter()
                .map(|x| {
                    x.as_f64().ok_or(ConvertError::WrongType {
                        key: "pts",
                        expected: "f64",
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            let pts: [f64; 4] = pts_vec
                .try_into()
                .map_err(|v: Vec<f64>| ConvertError::BadTrapezoid { len: v.len() })?;
            Ok(FactValue::Trapezoid { unit, pts })
        }
        "range" => Ok(FactValue::Range {
            unit: get_str(v, "unit")?.to_string(),
            min: get_f64(v, "min")?,
            max: get_f64(v, "max")?,
        }),
        "scalar" => Ok(FactValue::Scalar {
            unit: get_str(v, "unit")?.to_string(),
            value: get_f64(v, "value")?,
        }),
        "enum" => Ok(FactValue::Enum {
            value: get_str(v, "value")?.to_string(),
        }),
        "enum_set" => Ok(FactValue::EnumSet {
            values: get_list_str(v, "values")?,
        }),
        "bool" => Ok(FactValue::Bool {
            value: get_bool(v, "value")?,
        }),
        "rule" => {
            let data = v.get("data").ok_or(ConvertError::MissingKey("data"))?;
            let bytes = canonical_json_rfc8785(data)
                .map_err(|e| ConvertError::Canonical(format!("{e}")))?;
            let s =
                String::from_utf8(bytes).map_err(|e| ConvertError::Canonical(format!("{e}")))?;
            Ok(FactValue::Rule { data_json: s })
        }
        "unknown" => Ok(FactValue::Unknown {
            reason: get_str(v, "reason")?.to_string(),
        }),
        other => Err(ConvertError::BadShape {
            shape: other.to_string(),
        }),
    }
}

// ---- Row structs ----

#[derive(Debug, Clone)]
pub struct TaxonRow {
    pub taxon_id: String,
    pub rank: String,
    pub scientific_name: String,
    pub accepted_name: Option<String>,
    pub organism_group: String,
    pub archetype: String,
    pub uses: Vec<String>,
    pub traits: Vec<String>,
    pub parent_id: Option<String>,
    pub external_ids: Option<std::collections::BTreeMap<String, String>>,
    pub src: Option<Vec<String>>,
    pub dataset_id: Option<String>,
}

#[derive(Debug, Clone)]
pub struct NameRow {
    pub taxon_id: String,
    pub name: String,
    pub language: String,
    pub script: String,
    pub kind: String,
    pub preferred: bool,
    pub src: Option<Vec<String>>,
    pub dataset_id: Option<String>,
}

#[derive(Debug, Clone)]
pub struct FactRow {
    pub fact_id: String,
    pub taxon_id: String,
    pub parameter: String,
    pub phase: Option<String>,
    pub value: FactValue,
    pub scope_json: String,
    pub provenance_kind: String,
    pub src: Option<Vec<String>>,
    pub dataset_id: Option<String>,
    pub locator: Option<String>,
    pub evidence: String,
    pub status: String,
    pub reviewed_by: Option<Vec<String>>,
    pub reviewed_at: Option<String>,
    pub superseded_by: Option<String>,
}

#[derive(Debug, Clone)]
pub struct HazardRow {
    pub taxon_id: String,
    pub hazard_code: String,
    pub severity: String,
    pub reason: String,
    pub as_of: String,
    pub authority: String,
    pub src: Option<Vec<String>>,
    pub dataset_id: Option<String>,
}

#[derive(Debug, Clone)]
pub struct SourceRow {
    pub id: String,
    pub url: String,
    pub license: String,
    pub commercial_use: String,
    pub access_date: String,
    pub citation: String,
}

#[derive(Debug, Clone)]
pub struct DatasetRow {
    pub dataset_id: String,
    pub name: String,
    pub version: String,
    pub license: String,
    pub checksum: String,
    pub url: Option<String>,
    pub locator: Option<String>,
    pub access_date: String,
}

// ---- Conversions ----

pub fn taxon_from_json(v: &Value) -> Result<TaxonRow, ConvertError> {
    let traits = match v.get("traits").and_then(|x| x.as_array()) {
        Some(arr) => arr
            .iter()
            .filter_map(|x| x.as_str().map(String::from))
            .collect::<Vec<String>>(),
        None => Vec::new(),
    };
    let external_ids = match v.get("external_ids").and_then(|x| x.as_object()) {
        Some(obj) => {
            let mut m = std::collections::BTreeMap::new();
            for (k, vv) in obj {
                if let Some(s) = vv.as_str() {
                    m.insert(k.clone(), s.to_string());
                }
            }
            Some(m)
        }
        None => None,
    };
    Ok(TaxonRow {
        taxon_id: get_str(v, "taxon_id")?.to_string(),
        rank: get_str(v, "rank")?.to_string(),
        scientific_name: get_str(v, "scientific_name")?.to_string(),
        accepted_name: get_opt_str(v, "accepted_name"),
        organism_group: get_str(v, "organism_group")?.to_string(),
        archetype: get_str(v, "archetype")?.to_string(),
        uses: get_list_str(v, "uses")?,
        traits,
        parent_id: get_opt_str(v, "parent_id"),
        external_ids,
        src: get_opt_list_str(v, "src")?,
        dataset_id: get_opt_str(v, "dataset_id"),
    })
}

pub fn name_from_json(v: &Value) -> Result<NameRow, ConvertError> {
    Ok(NameRow {
        taxon_id: get_str(v, "taxon_id")?.to_string(),
        name: get_str(v, "name")?.to_string(),
        language: get_str(v, "language")?.to_string(),
        script: get_str(v, "script")?.to_string(),
        kind: get_str(v, "kind")?.to_string(),
        preferred: get_bool(v, "preferred")?,
        src: get_opt_list_str(v, "src")?,
        dataset_id: get_opt_str(v, "dataset_id"),
    })
}

pub fn fact_from_json(v: &Value) -> Result<FactRow, ConvertError> {
    let value_obj = v.get("value").ok_or(ConvertError::MissingKey("value"))?;
    let value = fact_value_from_json(value_obj)?;

    let scope_obj = v.get("scope").ok_or(ConvertError::MissingKey("scope"))?;
    let scope_bytes =
        canonical_json_rfc8785(scope_obj).map_err(|e| ConvertError::Canonical(format!("{e}")))?;
    let scope_json =
        String::from_utf8(scope_bytes).map_err(|e| ConvertError::Canonical(format!("{e}")))?;

    Ok(FactRow {
        fact_id: get_str(v, "fact_id")?.to_string(),
        taxon_id: get_str(v, "taxon_id")?.to_string(),
        parameter: get_str(v, "parameter")?.to_string(),
        phase: get_opt_str(v, "phase"),
        value,
        scope_json,
        provenance_kind: get_str(v, "provenance_kind")?.to_string(),
        src: get_opt_list_str(v, "src")?,
        dataset_id: get_opt_str(v, "dataset_id"),
        locator: get_opt_str(v, "locator"),
        evidence: get_str(v, "evidence")?.to_string(),
        status: get_str(v, "status")?.to_string(),
        reviewed_by: get_opt_list_str(v, "reviewed_by")?,
        reviewed_at: get_opt_str(v, "reviewed_at"),
        superseded_by: get_opt_str(v, "superseded_by"),
    })
}

pub fn hazard_from_json(v: &Value) -> Result<HazardRow, ConvertError> {
    Ok(HazardRow {
        taxon_id: get_str(v, "taxon_id")?.to_string(),
        hazard_code: get_str(v, "hazard_code")?.to_string(),
        severity: get_str(v, "severity")?.to_string(),
        reason: get_str(v, "reason")?.to_string(),
        as_of: get_str(v, "as_of")?.to_string(),
        authority: get_str(v, "authority")?.to_string(),
        src: get_opt_list_str(v, "src")?,
        dataset_id: get_opt_str(v, "dataset_id"),
    })
}

pub fn source_from_json(v: &Value) -> Result<SourceRow, ConvertError> {
    Ok(SourceRow {
        id: get_str(v, "id")?.to_string(),
        url: get_str(v, "url")?.to_string(),
        license: get_str(v, "license")?.to_string(),
        commercial_use: get_str(v, "commercial_use")?.to_string(),
        access_date: get_str(v, "access_date")?.to_string(),
        citation: get_str(v, "citation")?.to_string(),
    })
}

pub fn dataset_from_json(v: &Value) -> Result<DatasetRow, ConvertError> {
    Ok(DatasetRow {
        dataset_id: get_str(v, "dataset_id")?.to_string(),
        name: get_str(v, "name")?.to_string(),
        version: get_str(v, "version")?.to_string(),
        license: get_str(v, "license")?.to_string(),
        checksum: get_str(v, "checksum")?.to_string(),
        url: get_opt_str(v, "url"),
        locator: get_opt_str(v, "locator"),
        access_date: get_str(v, "access_date")?.to_string(),
    })
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
    use serde_json::json;

    #[test]
    fn fact_value_scalar() {
        let v = json!({"shape":"scalar","unit":"pH","value":7.0});
        let fv = fact_value_from_json(&v).unwrap();
        assert_eq!(fv.shape(), "scalar");
        assert_eq!(fv.unit(), Some("pH"));
        match fv {
            FactValue::Scalar { value, .. } => assert!((value - 7.0).abs() < 1e-9),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn fact_value_trapezoid() {
        let v = json!({"shape":"trapezoid","unit":"pH","pts":[4.5,6.0,7.0,8.5]});
        let fv = fact_value_from_json(&v).unwrap();
        assert_eq!(fv.shape(), "trapezoid");
        match fv {
            FactValue::Trapezoid { pts, .. } => {
                assert!((pts[0] - 4.5).abs() < 1e-9);
                assert!((pts[3] - 8.5).abs() < 1e-9);
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn fact_value_trapezoid_wrong_len() {
        let v = json!({"shape":"trapezoid","unit":"pH","pts":[4.5,6.0,7.0]});
        let e = fact_value_from_json(&v).unwrap_err();
        assert!(matches!(e, ConvertError::BadTrapezoid { len: 3 }));
    }

    #[test]
    fn fact_value_unknown() {
        let v = json!({"shape":"unknown","reason":"no data"});
        let fv = fact_value_from_json(&v).unwrap();
        assert_eq!(fv.shape(), "unknown");
        match fv {
            FactValue::Unknown { reason } => assert_eq!(reason, "no data"),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn fact_value_bad_shape() {
        let v = json!({"shape":"bogus"});
        let e = fact_value_from_json(&v).unwrap_err();
        assert!(matches!(e, ConvertError::BadShape { .. }));
    }

    #[test]
    fn source_roundtrip() {
        let v = json!({
            "id": "S001",
            "url": "https://x",
            "license": "CC0-1.0",
            "commercial_use": "yes",
            "access_date": "2026-01-01",
            "citation": "Test"
        });
        let s = source_from_json(&v).unwrap();
        assert_eq!(s.id, "S001");
        assert_eq!(s.license, "CC0-1.0");
        assert_eq!(s.commercial_use, "yes");
    }

    #[test]
    fn source_missing_key_errors() {
        let v = json!({"id": "S001"});
        let e = source_from_json(&v).unwrap_err();
        assert!(matches!(e, ConvertError::MissingKey(_)));
    }

    #[test]
    fn fact_scope_canonical() {
        let v = json!({
            "fact_id": "F00000000001",
            "taxon_id": "T000000001",
            "parameter": "soil_ph",
            "phase": null,
            "value": {"shape":"scalar","unit":"pH","value":7.0},
            "scope": {"system": "field", "country": "ID"},
            "provenance_kind": "curated",
            "src": ["S001"],
            "dataset_id": null,
            "locator": "Table 1",
            "evidence": "A",
            "status": "approved",
            "reviewed_by": ["r1"],
            "reviewed_at": "2026-01-01",
            "superseded_by": null
        });
        let f = fact_from_json(&v).unwrap();
        assert_eq!(f.fact_id, "F00000000001");
        // scope_json must be sorted by key (rfc8785)
        assert_eq!(f.scope_json, r#"{"country":"ID","system":"field"}"#);
    }
}
