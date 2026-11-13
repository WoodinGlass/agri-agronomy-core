use pyo3::prelude::*;

fn py_to_json_value(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    let json_mod = py.import("json")?;
    let s: String = json_mod.call_method1("dumps", (obj,))?.extract()?;
    serde_json::from_str(&s).map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))
}

#[pyfunction]
fn canonical_json(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let value = py_to_json_value(py, obj)?;
    agri_kernel::canonical::canonical_json(&value)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))
}

#[pyfunction]
fn sha256_hex(data: &[u8]) -> String {
    agri_kernel::hash::sha256_hex(data)
}

#[pyfunction]
#[pyo3(signature = (subject, inputs, engine_version, pack_hash=None))]
fn compute_request_id(
    py: Python<'_>,
    subject: Option<&Bound<'_, PyAny>>,
    inputs: &Bound<'_, PyAny>,
    engine_version: String,
    pack_hash: Option<String>,
) -> PyResult<String> {
    let subject_v: Option<serde_json::Value> = match subject {
        Some(s) => Some(py_to_json_value(py, s)?),
        None => None,
    };
    let inputs_v = py_to_json_value(py, inputs)?;
    agri_kernel::request_id::compute_request_id(
        subject_v.as_ref(),
        &inputs_v,
        &engine_version,
        pack_hash.as_deref(),
    )
    .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(canonical_json, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_hex, m)?)?;
    m.add_function(wrap_pyfunction!(compute_request_id, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
