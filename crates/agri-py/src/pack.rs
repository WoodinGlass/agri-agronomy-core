//! PyO3 bindings for `agri_kernel::pack::tables` (read_table, write_table,
//! find_forbidden).
//!
//! Purpose: (1) enable Python↔Rust parity tests in cell 6, (2) enable
//! future `scaffold_taxon` port (M22). Runtime path for `build_pack` and
//! `validate_pack` calls the Rust functions directly (not via Python), so
//! these bindings do not affect Phase C/D perf.
//!
//! PyO3 0.30: `PyObject` was removed; use `Py<PyAny>` for owned refs and
//! `Bound<'py, T>` for borrowed refs. Use `.into_any().unbind()` to
//! convert `Bound<'py, T>` → `Py<PyAny>`. `downcast_into` → `cast_into`.

use std::collections::BTreeMap;

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBool, PyBytes, PyDict, PyList};
use serde_json::Value as JsonValue;

use agri_kernel::pack::errors::PackError;
use agri_kernel::pack::tables::{
    find_forbidden, parse_json_no_dup, read_table, table_spec, write_table, CellValue, ColumnType,
};

// ---- Error mapping ----

/// Build a Python exception matching the Rust `PackError.code`.
fn raise_pack_error(py: Python<'_>, e: PackError) -> PyErr {
    let cls_name = e.python_class();
    let msg = format!("{e}");
    let file = e.file.clone();
    let line = e.line;
    let key = e.key.clone();

    let exc_type: Option<Bound<'_, PyAny>> = py
        .import("agri_core.pack.errors")
        .ok()
        .and_then(|m| m.getattr(cls_name).ok());

    let kwargs = PyDict::new(py);
    if let Some(f) = file {
        let _ = kwargs.set_item("file", f);
    }
    if let Some(l) = line {
        let _ = kwargs.set_item("line", l);
    }
    if let Some(k) = key {
        let _ = kwargs.set_item("key", k);
    }

    match exc_type {
        Some(cls) => match cls.call((msg.clone(),), Some(&kwargs)) {
            Ok(inst) => PyErr::from_value(inst),
            Err(err) => err,
        },
        None => pyo3::exceptions::PyRuntimeError::new_err(msg),
    }
}

// ---- JSON -> Py<PyAny> (recursive) ----

fn json_to_py(py: Python<'_>, v: &JsonValue) -> PyResult<Py<PyAny>> {
    match v {
        JsonValue::Null => Ok(py.None()),
        JsonValue::Bool(b) => Ok(PyBool::new(py, *b).to_owned().into_any().unbind()),
        JsonValue::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.into_pyobject(py)?.into_any().unbind())
            } else if let Some(u) = n.as_u64() {
                Ok(u.into_pyobject(py)?.into_any().unbind())
            } else if let Some(f) = n.as_f64() {
                Ok(f.into_pyobject(py)?.into_any().unbind())
            } else {
                Err(pyo3::exceptions::PyValueError::new_err(
                    "unrepresentable JSON number",
                ))
            }
        }
        JsonValue::String(s) => Ok(s.as_str().into_pyobject(py)?.into_any().unbind()),
        JsonValue::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(json_to_py(py, item)?)?;
            }
            Ok(list.into_any().unbind())
        }
        JsonValue::Object(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(k, json_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
    }
}

// ---- CellValue -> Py<PyAny> (column-type aware for Date) ----

fn cell_to_py(py: Python<'_>, v: &CellValue, col_ty: ColumnType) -> PyResult<Py<PyAny>> {
    match (col_ty, v) {
        (ColumnType::Date, CellValue::Str(s)) => {
            let dt_mod = py.import("datetime")?;
            let date_cls = dt_mod.getattr("date")?;
            let date_obj = date_cls.call_method1("fromisoformat", (s.as_str(),))?;
            Ok(date_obj.unbind())
        }
        (_, CellValue::Null) => Ok(py.None()),
        (_, CellValue::Str(s)) => Ok(s.as_str().into_pyobject(py)?.into_any().unbind()),
        (_, CellValue::Int(i)) => Ok(i.into_pyobject(py)?.into_any().unbind()),
        (_, CellValue::Float(f)) => Ok(f.into_pyobject(py)?.into_any().unbind()),
        (_, CellValue::Bool(b)) => Ok(PyBool::new(py, *b).to_owned().into_any().unbind()),
        (_, CellValue::ListStr(items)) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(item.as_str())?;
            }
            Ok(list.into_any().unbind())
        }
        (_, CellValue::DictStrStr(m)) => {
            let dict = PyDict::new(py);
            for (k, v) in m {
                dict.set_item(k.as_str(), v.as_str())?;
            }
            Ok(dict.into_any().unbind())
        }
        (_, CellValue::Json(v)) => json_to_py(py, v),
    }
}

// ---- PyAny -> CellValue (column-type aware for Date, Json) ----

fn py_to_cell(py: Python<'_>, value: &Bound<'_, PyAny>, ty: ColumnType) -> PyResult<CellValue> {
    if value.is_none() {
        return Ok(CellValue::Null);
    }
    match ty {
        ColumnType::Str => Ok(CellValue::Str(value.extract::<String>()?)),
        ColumnType::Int => Ok(CellValue::Int(value.extract::<i64>()?)),
        ColumnType::Float => Ok(CellValue::Float(value.extract::<f64>()?)),
        ColumnType::Bool => Ok(CellValue::Bool(value.extract::<bool>()?)),
        ColumnType::Date => {
            // Reject datetime (subclass of date but not valid for pack dates).
            let type_name = value.get_type().name()?.extract::<String>()?;
            if type_name == "datetime" {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "expected date (not datetime)",
                ));
            }
            let iso: String = value.call_method0("isoformat")?.extract()?;
            Ok(CellValue::Str(iso))
        }
        ColumnType::ListStr => {
            let items: Vec<String> = value.extract()?;
            Ok(CellValue::ListStr(items))
        }
        ColumnType::DictStrStr => {
            let d: BTreeMap<String, String> = value.extract()?;
            Ok(CellValue::DictStrStr(d))
        }
        ColumnType::Json => {
            // Serialize Python object via json.dumps, then parse with dup-check.
            let json_mod = py.import("json")?;
            let s: String = json_mod.call_method1("dumps", (value,))?.extract()?;
            let v = parse_json_no_dup(&s).map_err(pyo3::exceptions::PyValueError::new_err)?;
            Ok(CellValue::Json(v))
        }
    }
}

// ---- Bindings ----

/// Parse CSV bytes into `(rows, line_numbers)`.
///
/// `rows` is `list[dict[str, Any]]` (per-cell Python values matching
/// `_decode_cell` output; `date` objects for Date columns, plain
/// dicts/lists for Json). `line_numbers` is parallel to `rows`.
#[pyfunction]
#[pyo3(name = "read_table")]
pub fn py_read_table(
    py: Python<'_>,
    spec_name: &str,
    data: &[u8],
    source_name: &str,
) -> PyResult<(Vec<Py<PyAny>>, Vec<usize>)> {
    let spec = table_spec(spec_name).ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!("unknown table {spec_name:?}"))
    })?;
    let table = read_table(spec, data, source_name).map_err(|e| raise_pack_error(py, e))?;
    let rows = table.rows;
    let line_numbers = table.line_numbers;
    let mut py_rows: Vec<Py<PyAny>> = Vec::with_capacity(rows.len());
    for row in &rows {
        let dict = PyDict::new(py);
        for colspec in spec.columns.iter() {
            let key = colspec.name;
            let v = row.get(key).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("missing key {key:?} in row"))
            })?;
            dict.set_item(key, cell_to_py(py, v, colspec.ty)?)?;
        }
        py_rows.push(dict.into_any().unbind());
    }
    Ok((py_rows, line_numbers))
}

/// Serialise Python rows to canonical CSV bytes.
#[pyfunction]
#[pyo3(name = "write_table")]
pub fn py_write_table<'py>(
    py: Python<'py>,
    spec_name: &str,
    rows: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    let spec = table_spec(spec_name).ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!("unknown table {spec_name:?}"))
    })?;

    let mut rust_rows: Vec<BTreeMap<String, CellValue>> = Vec::new();
    for row_any in rows.try_iter()? {
        let row_any = row_any?;
        let row_dict = row_any.cast_into::<PyDict>()?;
        let mut row_map: BTreeMap<String, CellValue> = BTreeMap::new();
        for colspec in spec.columns.iter() {
            let key = colspec.name;
            let value = row_dict.get_item(key)?.ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("missing column {key:?}"))
            })?;
            let cv = py_to_cell(py, &value, colspec.ty)?;
            row_map.insert(key.to_string(), cv);
        }
        rust_rows.push(row_map);
    }

    let bytes = write_table(spec, &rust_rows).map_err(|e| raise_pack_error(py, e))?;
    Ok(PyBytes::new(py, &bytes))
}

/// Return `(codepoint, category)` of the first forbidden char, or None.
/// Build SQLite bytes from a source pack.
///
/// Returns the serialized SQLite file. `content_hash` is verified inside
/// (against the source manifest) but NOT returned; callers should call
/// `hash_pack_files` separately to get the canonical hash (byte-identical
/// to Python's `_build_sqlite_and_hash` content_hash).
///
/// `artifact_sha256` (sha256 of the returned bytes) MAY differ from
/// Python's value because SQLite header records the writer library version
/// (rusqlite bundled vs Python stdlib sqlite3). This is documented as
/// once-per-engine-version change in ADR-019 §10.
#[pyfunction]
#[pyo3(name = "build_sqlite_bytes")]
pub fn py_build_sqlite_bytes<'py>(
    py: Python<'py>,
    files: &Bound<'py, PyDict>,
    engine_version: &str,
) -> PyResult<Bound<'py, PyBytes>> {
    use std::collections::HashMap;
    let mut map: HashMap<String, Vec<u8>> = HashMap::with_capacity(files.len());
    for (k, v) in files.iter() {
        let key: String = k.extract()?;
        let bytes: Vec<u8> = v.extract()?;
        map.insert(key, bytes);
    }
    let out = agri_kernel::pack::build::build_sqlite_bytes(&map, engine_version)
        .map_err(|e| raise_pack_error(py, e))?;
    Ok(PyBytes::new(py, &out))
}

#[pyfunction]
#[pyo3(name = "find_forbidden")]
pub fn py_find_forbidden(text: &str) -> Option<(u32, String)> {
    find_forbidden(text).map(|(cp, cat)| (cp, cat.to_string()))
}

/// Run 16 rules on files + dictionary; return sorted findings.
///
/// Caller: `validate_pack_report` in `agri_core.pack.validate`. The ks
/// returned by `load_knowledge_set_from_files` already validated rows
/// via Pydantic and structure — so this binding re-parses tables (fast)
/// and runs rules only. Structure findings come via the Python exception
/// path in `validate_pack_report`.
#[pyfunction]
#[pyo3(name = "validate_pack_findings")]
pub fn py_validate_pack_findings<'py>(
    py: Python<'py>,
    files: &Bound<'py, PyDict>,
    dictionary: &Bound<'py, PyDict>,
) -> PyResult<Vec<Py<PyAny>>> {
    use std::collections::HashMap;

    // Convert files
    let mut files_map: HashMap<String, Vec<u8>> = HashMap::new();
    for (k, v) in files.iter() {
        let key: String = k.extract()?;
        let bytes: Vec<u8> = v.extract()?;
        files_map.insert(key, bytes);
    }

    // Convert dictionary
    let dict_info = dict_info_from_pydict(dictionary)?;

    // Parse tables + convert to row structs
    let tables = agri_kernel::pack::build::parse_all_tables(&files_map)
        .map_err(|e| raise_pack_error(py, e))?;

    let mut taxa: Vec<agri_kernel::pack::row_types::TaxonRow> = Vec::new();
    let mut names: Vec<agri_kernel::pack::row_types::NameRow> = Vec::new();
    let mut facts: Vec<agri_kernel::pack::row_types::FactRow> = Vec::new();
    let mut hazards: Vec<agri_kernel::pack::row_types::HazardRow> = Vec::new();
    let mut sources: Vec<agri_kernel::pack::row_types::SourceRow> = Vec::new();
    let mut datasets: Vec<agri_kernel::pack::row_types::DatasetRow> = Vec::new();

    use agri_kernel::pack::row_types::{
        dataset_from_json, fact_from_json, hazard_from_json, name_from_json, source_from_json,
        taxon_from_json,
    };
    use agri_kernel::pack::tables::cellmap_to_json;

    for (key, table) in tables.iter() {
        if key == "taxa" {
            for row in &table.rows {
                taxa.push(
                    taxon_from_json(&cellmap_to_json(row)).map_err(|e| {
                        pyo3::exceptions::PyValueError::new_err(format!("taxa: {e}"))
                    })?,
                );
            }
        } else if key == "names" {
            for row in &table.rows {
                names.push(
                    name_from_json(&cellmap_to_json(row)).map_err(|e| {
                        pyo3::exceptions::PyValueError::new_err(format!("names: {e}"))
                    })?,
                );
            }
        } else if key == "hazards" {
            for row in &table.rows {
                hazards.push(hazard_from_json(&cellmap_to_json(row)).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!("hazards: {e}"))
                })?);
            }
        } else if key == "sources" {
            for row in &table.rows {
                sources.push(source_from_json(&cellmap_to_json(row)).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!("sources: {e}"))
                })?);
            }
        } else if key == "datasets" {
            for row in &table.rows {
                datasets.push(dataset_from_json(&cellmap_to_json(row)).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!("datasets: {e}"))
                })?);
            }
        } else if key.starts_with("facts/") {
            for row in &table.rows {
                facts.push(fact_from_json(&cellmap_to_json(row)).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!("facts/{key}: {e}"))
                })?);
            }
        }
    }

    let findings = agri_kernel::pack::validate::run_rules(
        &taxa, &names, &facts, &hazards, &sources, &datasets, &files_map, &dict_info,
    );

    findings
        .into_iter()
        .map(|f| finding_to_pydict(py, f))
        .collect()
}

fn finding_to_pydict(py: Python<'_>, f: agri_kernel::pack::rules::Finding) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    d.set_item("code", f.code)?;
    d.set_item("severity", f.severity.as_str())?;
    d.set_item("message", f.message)?;
    let loc = PyDict::new(py);
    if let Some(v) = f.location.file {
        loc.set_item("file", v)?;
    }
    if let Some(v) = f.location.line {
        loc.set_item("line", v)?;
    }
    if let Some(v) = f.location.key {
        loc.set_item("key", v)?;
    }
    if let Some(v) = f.location.taxon_id {
        loc.set_item("taxon_id", v)?;
    }
    if let Some(v) = f.location.fact_id {
        loc.set_item("fact_id", v)?;
    }
    if let Some(v) = f.location.parameter {
        loc.set_item("parameter", v)?;
    }
    if let Some(v) = f.location.phase {
        loc.set_item("phase", v)?;
    }
    d.set_item("location", loc)?;
    Ok(d.into_any().unbind())
}

fn dict_info_from_pydict(
    dict_dict: &Bound<'_, PyDict>,
) -> PyResult<agri_kernel::pack::dict_info::DictionaryInfo> {
    use agri_kernel::pack::dict_info::{AppliesToInfo, DictionaryInfo, ParameterInfo};
    use std::collections::BTreeMap;

    let version: String = dict_dict
        .get_item("version")?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("version"))?
        .extract()?;

    let params_obj = dict_dict
        .get_item("parameters")?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("parameters"))?;
    let params_dict = params_obj
        .cast::<PyDict>()
        .map_err(|_| pyo3::exceptions::PyTypeError::new_err("parameters not dict"))?;

    let mut parameters: BTreeMap<String, ParameterInfo> = BTreeMap::new();
    for (k, v) in params_dict.iter() {
        let key: String = k.extract()?;
        let pd = v
            .cast::<PyDict>()
            .map_err(|_| pyo3::exceptions::PyTypeError::new_err("param not dict"))?;

        let get_str = |name: &str| -> PyResult<String> {
            pd.get_item(name)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(name.to_string()))?
                .extract()
        };
        let get_opt_str = |name: &str| -> PyResult<Option<String>> {
            match pd.get_item(name)? {
                Some(x) if !x.is_none() => Ok(Some(x.extract()?)),
                _ => Ok(None),
            }
        };
        let get_opt_list = |name: &str| -> PyResult<Option<Vec<String>>> {
            match pd.get_item(name)? {
                Some(x) if !x.is_none() => Ok(Some(x.extract()?)),
                _ => Ok(None),
            }
        };
        let get_list = |name: &str| -> PyResult<Vec<String>> {
            match pd.get_item(name)? {
                Some(x) if !x.is_none() => x.extract(),
                _ => Ok(vec![]),
            }
        };
        let get_bool = |name: &str, default: bool| -> PyResult<bool> {
            match pd.get_item(name)? {
                Some(x) if !x.is_none() => x.extract(),
                _ => Ok(default),
            }
        };

        let pr_obj = pd.get_item("physical_range")?;
        let physical_range: Option<(f64, f64)> = match pr_obj {
            Some(x) if !x.is_none() => {
                let tuple: (f64, f64) = x.extract()?;
                Some(tuple)
            }
            _ => None,
        };

        let applies_to_obj = pd.get_item("applies_to")?;
        let applies_to = match applies_to_obj {
            Some(x) if !x.is_none() => {
                let ad = x
                    .cast::<PyDict>()
                    .map_err(|_| pyo3::exceptions::PyTypeError::new_err("applies_to not dict"))?;
                let organism: Vec<String> = match ad.get_item("organism_groups")? {
                    Some(g) if !g.is_none() => g.extract()?,
                    _ => vec![],
                };
                AppliesToInfo {
                    organism_groups: organism,
                    archetypes: match ad.get_item("archetypes")? {
                        Some(a) if !a.is_none() => Some(a.extract()?),
                        _ => None,
                    },
                    uses: match ad.get_item("uses")? {
                        Some(a) if !a.is_none() => Some(a.extract()?),
                        _ => None,
                    },
                    systems: match ad.get_item("systems")? {
                        Some(a) if !a.is_none() => Some(a.extract()?),
                        _ => None,
                    },
                    traits: match ad.get_item("traits")? {
                        Some(a) if !a.is_none() => Some(a.extract()?),
                        _ => None,
                    },
                }
            }
            _ => AppliesToInfo::default(),
        };

        let p = ParameterInfo {
            key,
            stage: get_str("stage")?,
            shape: get_str("shape")?,
            unit: get_opt_str("unit")?,
            physical_range,
            enum_values: get_opt_list("enum_values")?,
            enum_source: get_opt_str("enum_source")?,
            phase_set: get_str("phase_set")?,
            allowed_phases: get_opt_list("allowed_phases")?,
            applies_to,
            scope_keys: get_list("scope_keys")?,
            used_by: get_list("used_by")?,
            tier_required: get_bool("tier_required", false)?,
            safety_class: get_str("safety_class")?,
            kind: get_str("kind")?,
        };
        parameters.insert(p.key.clone(), p);
    }

    let mut phases_by_archetype: BTreeMap<String, Vec<String>> = BTreeMap::new();
    if let Some(pba) = dict_dict.get_item("phases_by_archetype")? {
        if !pba.is_none() {
            let pd = pba.cast::<PyDict>().map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("phases_by_archetype not dict")
            })?;
            for (k, v) in pd.iter() {
                let key: String = k.extract()?;
                let vals: Vec<String> = v.extract()?;
                phases_by_archetype.insert(key, vals);
            }
        }
    }

    Ok(DictionaryInfo {
        version,
        parameters,
        phases_by_archetype,
    })
}

// ============================================================================
// M21 G4-3b: PyRustKnowledgeSet — eager in-memory load_knowledge_set backend.
// ============================================================================
//
// Per ADR-019 §11.5, normalize + name_index ship as one backend unit.
// The RustKnowledgeSet built by `load_built_pack` holds all rows in Rust
// memory; iterators yield per-row dicts lazily to keep memory bounded.

use std::sync::Arc;

use agri_kernel::pack::knowledge_set::RustKnowledgeSet;
use agri_kernel::pack::loader::load_built_pack;
use agri_kernel::pack::name_index::NameIndexEntry;
use agri_kernel::pack::row_types::{
    DatasetRow, FactRow, FactValue, HazardRow, NameRow, SourceRow, TaxonRow,
};

// ---- Row -> PyDict converters ----

fn taxon_to_pydict(py: Python<'_>, t: &TaxonRow) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("taxon_id", &t.taxon_id)?;
    d.set_item("rank", &t.rank)?;
    d.set_item("scientific_name", &t.scientific_name)?;
    d.set_item("accepted_name", t.accepted_name.as_deref())?;
    d.set_item("organism_group", &t.organism_group)?;
    d.set_item("archetype", &t.archetype)?;
    let uses = PyList::empty(py);
    for u in &t.uses {
        uses.append(u)?;
    }
    d.set_item("uses", uses)?;
    let traits = PyList::empty(py);
    for tr in &t.traits {
        traits.append(tr)?;
    }
    d.set_item("traits", traits)?;
    d.set_item("parent_id", t.parent_id.as_deref())?;
    match &t.external_ids {
        None => d.set_item("external_ids", py.None())?,
        Some(m) => {
            let d2 = PyDict::new(py);
            for (k, v) in m {
                d2.set_item(k, v)?;
            }
            d.set_item("external_ids", d2)?;
        }
    }
    match &t.src {
        None => d.set_item("src", py.None())?,
        Some(s) => {
            let l = PyList::empty(py);
            for x in s {
                l.append(x)?;
            }
            d.set_item("src", l)?;
        }
    }
    d.set_item("dataset_id", t.dataset_id.as_deref())?;
    Ok(d.unbind())
}

fn name_to_pydict(py: Python<'_>, n: &NameRow) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("taxon_id", &n.taxon_id)?;
    d.set_item("name", &n.name)?;
    d.set_item("language", &n.language)?;
    d.set_item("script", &n.script)?;
    d.set_item("kind", &n.kind)?;
    d.set_item("preferred", PyBool::new(py, n.preferred).to_owned())?;
    match &n.src {
        None => d.set_item("src", py.None())?,
        Some(s) => {
            let l = PyList::empty(py);
            for x in s {
                l.append(x)?;
            }
            d.set_item("src", l)?;
        }
    }
    d.set_item("dataset_id", n.dataset_id.as_deref())?;
    Ok(d.unbind())
}

fn fact_value_to_pydict(py: Python<'_>, v: &FactValue) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    match v {
        FactValue::Trapezoid { unit, pts } => {
            d.set_item("shape", "trapezoid")?;
            d.set_item("unit", unit)?;
            d.set_item("pts", pts.to_vec())?;
        }
        FactValue::Range { unit, min, max } => {
            d.set_item("shape", "range")?;
            d.set_item("unit", unit)?;
            d.set_item("min", *min)?;
            d.set_item("max", *max)?;
        }
        FactValue::Scalar { unit, value } => {
            d.set_item("shape", "scalar")?;
            d.set_item("unit", unit)?;
            d.set_item("value", *value)?;
        }
        FactValue::Enum { value } => {
            d.set_item("shape", "enum")?;
            d.set_item("value", value)?;
        }
        FactValue::EnumSet { values } => {
            d.set_item("shape", "enum_set")?;
            let l = PyList::empty(py);
            for x in values {
                l.append(x)?;
            }
            d.set_item("values", l)?;
        }
        FactValue::Bool { value } => {
            d.set_item("shape", "bool")?;
            d.set_item("value", PyBool::new(py, *value).to_owned())?;
        }
        FactValue::Rule { data_json } => {
            d.set_item("shape", "rule")?;
            let parsed: serde_json::Value =
                serde_json::from_str(data_json).unwrap_or(serde_json::Value::Null);
            d.set_item("data", json_to_py(py, &parsed)?)?;
        }
        FactValue::Unknown { reason } => {
            d.set_item("shape", "unknown")?;
            d.set_item("reason", reason)?;
        }
    }
    Ok(d.unbind())
}

fn fact_to_pydict(py: Python<'_>, f: &FactRow) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("fact_id", &f.fact_id)?;
    d.set_item("taxon_id", &f.taxon_id)?;
    d.set_item("parameter", &f.parameter)?;
    d.set_item("phase", f.phase.as_deref())?;
    d.set_item("value", fact_value_to_pydict(py, &f.value)?)?;
    let scope: serde_json::Value =
        serde_json::from_str(&f.scope_json).unwrap_or(serde_json::Value::Null);
    d.set_item("scope", json_to_py(py, &scope)?)?;
    d.set_item("provenance_kind", &f.provenance_kind)?;
    match &f.src {
        None => d.set_item("src", py.None())?,
        Some(s) => {
            let l = PyList::empty(py);
            for x in s {
                l.append(x)?;
            }
            d.set_item("src", l)?;
        }
    }
    d.set_item("dataset_id", f.dataset_id.as_deref())?;
    d.set_item("locator", f.locator.as_deref())?;
    d.set_item("evidence", &f.evidence)?;
    d.set_item("status", &f.status)?;
    match &f.reviewed_by {
        None => d.set_item("reviewed_by", py.None())?,
        Some(s) => {
            let l = PyList::empty(py);
            for x in s {
                l.append(x)?;
            }
            d.set_item("reviewed_by", l)?;
        }
    }
    d.set_item("reviewed_at", f.reviewed_at.as_deref())?;
    d.set_item("superseded_by", f.superseded_by.as_deref())?;
    Ok(d.unbind())
}

fn hazard_to_pydict(py: Python<'_>, h: &HazardRow) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("taxon_id", &h.taxon_id)?;
    d.set_item("hazard_code", &h.hazard_code)?;
    d.set_item("severity", &h.severity)?;
    d.set_item("reason", &h.reason)?;
    d.set_item("as_of", &h.as_of)?;
    d.set_item("authority", &h.authority)?;
    match &h.src {
        None => d.set_item("src", py.None())?,
        Some(s) => {
            let l = PyList::empty(py);
            for x in s {
                l.append(x)?;
            }
            d.set_item("src", l)?;
        }
    }
    d.set_item("dataset_id", h.dataset_id.as_deref())?;
    Ok(d.unbind())
}

fn source_to_pydict(py: Python<'_>, s: &SourceRow) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("id", &s.id)?;
    d.set_item("url", &s.url)?;
    d.set_item("license", &s.license)?;
    d.set_item("commercial_use", &s.commercial_use)?;
    d.set_item("access_date", &s.access_date)?;
    d.set_item("citation", &s.citation)?;
    Ok(d.unbind())
}

fn dataset_to_pydict(py: Python<'_>, d_in: &DatasetRow) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("dataset_id", &d_in.dataset_id)?;
    d.set_item("name", &d_in.name)?;
    d.set_item("version", &d_in.version)?;
    d.set_item("license", &d_in.license)?;
    d.set_item("checksum", &d_in.checksum)?;
    d.set_item("url", d_in.url.as_deref())?;
    d.set_item("locator", d_in.locator.as_deref())?;
    d.set_item("access_date", &d_in.access_date)?;
    Ok(d.unbind())
}

fn name_index_entry_to_pydict(py: Python<'_>, e: &NameIndexEntry) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("taxon_id", &e.taxon_id)?;
    d.set_item("name", &e.name)?;
    d.set_item("normalized_name", &e.normalized_name)?;
    d.set_item("language", &e.language)?;
    d.set_item("kind", &e.kind)?;
    d.set_item("preferred", PyBool::new(py, e.preferred).to_owned())?;
    d.set_item("matched_via", e.matched_via.as_str())?;
    d.set_item("rank", &e.rank)?;
    d.set_item("scientific_name", &e.scientific_name)?;
    Ok(d.unbind())
}

// ---- Iterator classes ----

macro_rules! make_iter_class {
    ($name:ident, $row:ty, $conv:ident) => {
        #[pyclass]
        pub struct $name {
            data: std::vec::IntoIter<$row>,
        }

        #[pymethods]
        impl $name {
            fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
                slf
            }
            fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Py<PyDict>>> {
                match self.data.next() {
                    None => Ok(None),
                    Some(row) => Ok(Some($conv(py, &row)?)),
                }
            }
        }
    };
}

make_iter_class!(TaxonIterator, TaxonRow, taxon_to_pydict);
make_iter_class!(FactIterator, FactRow, fact_to_pydict);
make_iter_class!(NameIterator, NameRow, name_to_pydict);
make_iter_class!(HazardIterator, HazardRow, hazard_to_pydict);

// ---- PyRustKnowledgeSet ----

#[pyclass]
pub struct PyRustKnowledgeSet {
    inner: Arc<RustKnowledgeSet>,
}

#[pymethods]
impl PyRustKnowledgeSet {
    // ---- properties ----

    #[getter]
    fn pack_hash(&self) -> &str {
        &self.inner.pack_hash
    }

    #[getter]
    fn artifact_sha256(&self) -> &str {
        &self.inner.artifact_sha256
    }

    #[getter]
    fn dictionary_version(&self) -> &str {
        &self.inner.dictionary_version
    }

    #[getter]
    fn verified(&self) -> bool {
        self.inner.verified
    }

    // ---- per-item lookups ----

    fn taxon(&self, py: Python<'_>, taxon_id: &str) -> PyResult<Option<Py<PyDict>>> {
        match self.inner.taxon(taxon_id) {
            None => Ok(None),
            Some(t) => Ok(Some(taxon_to_pydict(py, t)?)),
        }
    }

    fn source(&self, py: Python<'_>, source_id: &str) -> PyResult<Option<Py<PyDict>>> {
        match self.inner.source(source_id) {
            None => Ok(None),
            Some(s) => Ok(Some(source_to_pydict(py, s)?)),
        }
    }

    fn dataset(&self, py: Python<'_>, dataset_id: &str) -> PyResult<Option<Py<PyDict>>> {
        match self.inner.dataset(dataset_id) {
            None => Ok(None),
            Some(d) => Ok(Some(dataset_to_pydict(py, d)?)),
        }
    }

    // ---- iterators ----

    fn taxa(&self, py: Python<'_>) -> PyResult<Py<TaxonIterator>> {
        Py::new(
            py,
            TaxonIterator {
                data: self.inner.taxa().to_vec().into_iter(),
            },
        )
    }

    fn facts(&self, py: Python<'_>) -> PyResult<Py<FactIterator>> {
        Py::new(
            py,
            FactIterator {
                data: self.inner.facts().to_vec().into_iter(),
            },
        )
    }

    fn names(&self, py: Python<'_>) -> PyResult<Py<NameIterator>> {
        Py::new(
            py,
            NameIterator {
                data: self.inner.names().to_vec().into_iter(),
            },
        )
    }

    fn hazards(&self, py: Python<'_>) -> PyResult<Py<HazardIterator>> {
        Py::new(
            py,
            HazardIterator {
                data: self.inner.hazards().to_vec().into_iter(),
            },
        )
    }

    // ---- per-taxon collections ----

    fn facts_for(
        &self,
        py: Python<'_>,
        taxon_id: &str,
        parameter: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        match self.inner.facts_for(taxon_id, parameter) {
            Err(_) => Err(pyo3::exceptions::PyKeyError::new_err(taxon_id.to_string())),
            Ok(rows) => {
                let l = PyList::empty(py);
                for r in rows {
                    l.append(fact_to_pydict(py, r)?)?;
                }
                Ok(l.into_any().unbind())
            }
        }
    }

    fn names_for(&self, py: Python<'_>, taxon_id: &str) -> PyResult<Py<PyAny>> {
        match self.inner.names_for(taxon_id) {
            Err(_) => Err(pyo3::exceptions::PyKeyError::new_err(taxon_id.to_string())),
            Ok(rows) => {
                let l = PyList::empty(py);
                for r in rows {
                    l.append(name_to_pydict(py, r)?)?;
                }
                Ok(l.into_any().unbind())
            }
        }
    }

    fn hazards_for(&self, py: Python<'_>, taxon_id: &str) -> PyResult<Py<PyAny>> {
        match self.inner.hazards_for(taxon_id) {
            Err(_) => Err(pyo3::exceptions::PyKeyError::new_err(taxon_id.to_string())),
            Ok(rows) => {
                let l = PyList::empty(py);
                for r in rows {
                    l.append(hazard_to_pydict(py, r)?)?;
                }
                Ok(l.into_any().unbind())
            }
        }
    }

    fn ids_lock(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self.inner.ids_lock() {
            None => Ok(py.None()),
            Some(set) => {
                let l = PyList::empty(py);
                for x in set {
                    l.append(x)?;
                }
                let fset = py.import("builtins")?.getattr("frozenset")?.call1((l,))?;
                Ok(fset.unbind())
            }
        }
    }

    fn names_index(&self, py: Python<'_>, query: &str) -> PyResult<Py<PyAny>> {
        let entries = self.inner.names_index(query);
        let l = PyList::empty(py);
        for e in entries {
            l.append(name_index_entry_to_pydict(py, e)?)?;
        }
        Ok(l.into_any().unbind())
    }
}

// ---- load_built_pack_native ----

fn manifest_fields_from_pydict(
    d: &Bound<'_, PyDict>,
) -> PyResult<agri_kernel::pack::build::ManifestFields> {
    use agri_kernel::pack::build::ManifestFields;
    let get_str = |k: &str| -> PyResult<String> {
        d.get_item(k)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
            .extract()
    };
    let get_int = |k: &str| -> PyResult<i64> {
        d.get_item(k)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
            .extract()
    };
    let get_opt_str = |k: &str| -> PyResult<Option<String>> {
        match d.get_item(k)? {
            Some(x) if !x.is_none() => Ok(Some(x.extract()?)),
            _ => Ok(None),
        }
    };
    let get_opt_int = |k: &str| -> PyResult<Option<i64>> {
        match d.get_item(k)? {
            Some(x) if !x.is_none() => Ok(Some(x.extract()?)),
            _ => Ok(None),
        }
    };
    let get_bool = |k: &str| -> PyResult<bool> {
        match d.get_item(k)? {
            Some(x) if !x.is_none() => x.extract(),
            _ => Ok(false),
        }
    };
    Ok(ManifestFields {
        name: get_str("name")?,
        version: get_str("version")?,
        schema_version: get_int("schema_version")?,
        engine_min: get_str("engine_min")?,
        dictionary_min: get_str("dictionary_min")?,
        content_hash: get_opt_str("content_hash")?,
        synthetic: get_bool("synthetic")?,
        artifact_sha256: get_opt_str("artifact_sha256")?,
        sqlite_schema_version: get_opt_int("sqlite_schema_version")?,
        built_by: get_opt_str("built_by")?,
        hash_alg: get_opt_str("hash_alg")?,
    })
}

#[pyfunction]
#[pyo3(name = "load_built_pack_native")]
pub fn py_load_built_pack_native(
    py: Python<'_>,
    sqlite_path: std::path::PathBuf,
    manifest_dict: &Bound<'_, PyDict>,
    expected_content_hash: Option<String>,
    dictionary_version: String,
    max_bytes: u64,
) -> PyResult<Py<PyRustKnowledgeSet>> {
    let manifest = manifest_fields_from_pydict(manifest_dict)?;
    let set = load_built_pack(
        &sqlite_path,
        manifest,
        expected_content_hash.as_deref(),
        dictionary_version,
        max_bytes,
    )
    .map_err(|e| raise_pack_error(py, e))?;
    Py::new(
        py,
        PyRustKnowledgeSet {
            inner: Arc::new(set),
        },
    )
}
