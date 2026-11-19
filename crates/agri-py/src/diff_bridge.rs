//! PyO3 adapters for Phase E diff.
//!
//! Two entry points:
//! - py_diff_pack_paths: path-based (streams built packs in Rust)
//! - py_diff_loaded:     rows-based (in-memory rows from Python)
//!
//! Both return a PyDict that Python's `_render_diff_payload` turns into a
//! `DiffReport`. Message rendering lives on the Python side (N17); this
//! module emits structured ViolationMeta only.

use std::collections::BTreeSet;
use std::path::Path;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFrozenSet, PyList};

use agri_kernel::pack::build::ManifestFields;
use agri_kernel::pack::diff::{
    diff_rows, stream_diff_rows_from_iterators, DiffConfig, DiffOutcome, ViolationMeta,
};
use agri_kernel::pack::errors::PackError;
use agri_kernel::pack::row_types::{fact_from_json, taxon_from_json, FactRow, TaxonRow};
use agri_kernel::pack::stream::PackStream;

fn err_to_py(e: PackError) -> PyErr {
    pyo3::exceptions::PyValueError::new_err(format!("{}: {}", e.code, e.message))
}

fn manifest_fields_from_pydict(d: &Bound<'_, PyDict>) -> PyResult<ManifestFields> {
    let get_str = |k: &str| -> PyResult<String> {
        d.get_item(k)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
            .extract::<String>()
    };
    let get_opt_str = |k: &str| -> PyResult<Option<String>> {
        match d.get_item(k)? {
            Some(v) if !v.is_none() => Ok(Some(v.extract::<String>()?)),
            _ => Ok(None),
        }
    };
    let get_i64 = |k: &str| -> PyResult<i64> {
        d.get_item(k)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
            .extract::<i64>()
    };
    let get_opt_i64 = |k: &str| -> PyResult<Option<i64>> {
        match d.get_item(k)? {
            Some(v) if !v.is_none() => Ok(Some(v.extract::<i64>()?)),
            _ => Ok(None),
        }
    };
    let get_bool = |k: &str| -> PyResult<bool> {
        match d.get_item(k)? {
            Some(v) if !v.is_none() => v.extract::<bool>(),
            _ => Ok(false),
        }
    };

    Ok(ManifestFields {
        name: get_str("name")?,
        version: get_str("version")?,
        schema_version: get_i64("schema_version")?,
        engine_min: get_str("engine_min")?,
        dictionary_min: get_str("dictionary_min")?,
        content_hash: get_opt_str("content_hash")?,
        synthetic: get_bool("synthetic")?,
        artifact_sha256: get_opt_str("artifact_sha256")?,
        sqlite_schema_version: get_opt_i64("sqlite_schema_version")?,
        built_by: get_opt_str("built_by")?,
        hash_alg: get_opt_str("hash_alg")?,
    })
}

fn extract_str_set(s: &Bound<'_, PyFrozenSet>) -> PyResult<BTreeSet<String>> {
    let mut out: BTreeSet<String> = BTreeSet::new();
    for item in s.iter() {
        out.insert(item.extract::<String>()?);
    }
    Ok(out)
}

fn py_to_json(obj: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    use pyo3::types::{PyBool, PyDict as PyDictT, PyFloat, PyInt, PyList as PyListT, PyString};
    use serde_json::{Map, Number, Value};

    if obj.is_none() {
        return Ok(Value::Null);
    }
    if let Ok(b) = obj.cast::<PyBool>() {
        return Ok(Value::Bool(b.is_true()));
    }
    if let Ok(i) = obj.cast::<PyInt>() {
        if let Ok(v) = i.extract::<i64>() {
            return Ok(Value::Number(Number::from(v)));
        }
        if let Ok(v) = i.extract::<u64>() {
            return Ok(Value::Number(Number::from(v)));
        }
        return Err(pyo3::exceptions::PyValueError::new_err(
            "int outside i64/u64 range",
        ));
    }
    if let Ok(f) = obj.cast::<PyFloat>() {
        let v: f64 = f.extract()?;
        let num = Number::from_f64(v)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("NaN/inf not valid JSON"))?;
        return Ok(Value::Number(num));
    }
    if let Ok(s) = obj.cast::<PyString>() {
        return Ok(Value::String(s.extract()?));
    }
    if let Ok(lst) = obj.cast::<PyListT>() {
        let mut arr = Vec::new();
        for item in lst.iter() {
            arr.push(py_to_json(&item)?);
        }
        return Ok(Value::Array(arr));
    }
    if let Ok(d) = obj.cast::<PyDictT>() {
        let mut map = Map::new();
        for (k, v) in d.iter() {
            let key: String = k.extract()?;
            map.insert(key, py_to_json(&v)?);
        }
        return Ok(Value::Object(map));
    }
    let tname = obj
        .get_type()
        .name()
        .map(|n| n.to_string())
        .unwrap_or_else(|_| "__unknown__".to_string());
    Err(pyo3::exceptions::PyTypeError::new_err(format!(
        "unsupported type: {tname}"
    )))
}

fn rows_from_pylist_taxa(lst: &Bound<'_, PyList>) -> PyResult<Vec<TaxonRow>> {
    let mut out: Vec<TaxonRow> = Vec::new();
    for item in lst.iter() {
        let json_val = py_to_json(&item)?;
        let row = taxon_from_json(&json_val)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("taxon: {e}")))?;
        out.push(row);
    }
    Ok(out)
}

fn rows_from_pylist_facts(lst: &Bound<'_, PyList>) -> PyResult<Vec<FactRow>> {
    let mut out: Vec<FactRow> = Vec::new();
    for item in lst.iter() {
        let json_val = py_to_json(&item)?;
        let row = fact_from_json(&json_val)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("fact: {e}")))?;
        out.push(row);
    }
    Ok(out)
}

fn ids_lock_from_opt(obj: Option<&Bound<'_, PyAny>>) -> PyResult<Option<BTreeSet<String>>> {
    match obj {
        None => Ok(None),
        Some(o) if o.is_none() => Ok(None),
        Some(o) => {
            let mut out: BTreeSet<String> = BTreeSet::new();
            for item in o.try_iter()? {
                out.insert(item?.extract::<String>()?);
            }
            Ok(Some(out))
        }
    }
}

fn diff_outcome_to_pydict<'py>(py: Python<'py>, out: &DiffOutcome) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("identical", out.identical)?;
    d.set_item("taxa_added", out.taxa_added.clone())?;
    d.set_item("taxa_removed", out.taxa_removed.clone())?;
    d.set_item("taxa_changed", out.taxa_changed.clone())?;
    d.set_item("facts_added", out.facts_added.clone())?;
    d.set_item("facts_removed", out.facts_removed.clone())?;

    let fc_list = PyList::empty(py);
    for fc in &out.facts_changed {
        let entry = PyDict::new(py);
        entry.set_item("fact_id", &fc.fact_id)?;
        entry.set_item("fields_changed", fc.fields_changed.clone())?;
        entry.set_item("classification", fc.classification.as_str())?;
        entry.set_item("old_status", &fc.old_status)?;
        entry.set_item("new_status", &fc.new_status)?;
        fc_list.append(entry)?;
    }
    d.set_item("facts_changed", fc_list)?;

    let v_list = PyList::empty(py);
    for v in &out.violations {
        let entry = PyDict::new(py);
        entry.set_item("kind", v.kind.as_str())?;
        entry.set_item("entity_id", &v.entity_id)?;
        match &v.meta {
            ViolationMeta::FactIdReused { fields_changed } => {
                let m = PyDict::new(py);
                m.set_item("fields_changed", fields_changed.clone())?;
                entry.set_item("meta", m)?;
            }
            ViolationMeta::Empty => {
                entry.set_item("meta", py.None())?;
            }
        }
        v_list.append(entry)?;
    }
    d.set_item("violations", v_list)?;

    Ok(d)
}

#[pyfunction]
#[pyo3(name = "diff_pack_paths")]
#[allow(clippy::too_many_arguments)]
pub fn py_diff_pack_paths<'py>(
    py: Python<'py>,
    old_path: &str,
    old_manifest: &Bound<'py, PyDict>,
    new_path: &str,
    new_manifest: &Bound<'py, PyDict>,
    acceptable_fields: &Bound<'py, PyFrozenSet>,
    violation_fields: &Bound<'py, PyFrozenSet>,
    protected_statuses: &Bound<'py, PyFrozenSet>,
) -> PyResult<Bound<'py, PyDict>> {
    let old_mf = manifest_fields_from_pydict(old_manifest)?;
    let new_mf = manifest_fields_from_pydict(new_manifest)?;

    let old_stream = PackStream::open(Path::new(old_path), &old_mf).map_err(err_to_py)?;
    let new_stream = PackStream::open(Path::new(new_path), &new_mf).map_err(err_to_py)?;

    let cfg = DiffConfig {
        acceptable_fields: extract_str_set(acceptable_fields)?,
        violation_fields: extract_str_set(violation_fields)?,
        protected_statuses: extract_str_set(protected_statuses)?,
    };

    let out = stream_diff_rows_from_iterators(
        old_stream.open_taxa_producer().map_err(err_to_py)?,
        new_stream.open_taxa_producer().map_err(err_to_py)?,
        old_stream.open_facts_producer().map_err(err_to_py)?,
        new_stream.open_facts_producer().map_err(err_to_py)?,
        None,
        None,
        &cfg,
    )
    .map_err(err_to_py)?;

    let d = diff_outcome_to_pydict(py, &out)?;
    d.set_item("old_pack_hash", &old_stream.pack_hash)?;
    d.set_item("new_pack_hash", &new_stream.pack_hash)?;
    Ok(d)
}

#[pyfunction]
#[pyo3(name = "diff_loaded")]
#[allow(clippy::too_many_arguments)]
pub fn py_diff_loaded<'py>(
    py: Python<'py>,
    old_taxa: &Bound<'py, PyList>,
    old_facts: &Bound<'py, PyList>,
    old_ids_lock: Option<&Bound<'py, PyAny>>,
    old_pack_hash: &str,
    new_taxa: &Bound<'py, PyList>,
    new_facts: &Bound<'py, PyList>,
    new_ids_lock: Option<&Bound<'py, PyAny>>,
    new_pack_hash: &str,
    acceptable_fields: &Bound<'py, PyFrozenSet>,
    violation_fields: &Bound<'py, PyFrozenSet>,
    protected_statuses: &Bound<'py, PyFrozenSet>,
) -> PyResult<Bound<'py, PyDict>> {
    let old_taxa_rows = rows_from_pylist_taxa(old_taxa)?;
    let old_facts_rows = rows_from_pylist_facts(old_facts)?;
    let new_taxa_rows = rows_from_pylist_taxa(new_taxa)?;
    let new_facts_rows = rows_from_pylist_facts(new_facts)?;

    let old_lock = ids_lock_from_opt(old_ids_lock)?;
    let new_lock = ids_lock_from_opt(new_ids_lock)?;

    let cfg = DiffConfig {
        acceptable_fields: extract_str_set(acceptable_fields)?,
        violation_fields: extract_str_set(violation_fields)?,
        protected_statuses: extract_str_set(protected_statuses)?,
    };

    let out = diff_rows(
        &old_taxa_rows,
        &new_taxa_rows,
        &old_facts_rows,
        &new_facts_rows,
        old_lock.as_ref(),
        new_lock.as_ref(),
        &cfg,
    );

    let d = diff_outcome_to_pydict(py, &out)?;
    d.set_item("old_pack_hash", old_pack_hash)?;
    d.set_item("new_pack_hash", new_pack_hash)?;
    Ok(d)
}
