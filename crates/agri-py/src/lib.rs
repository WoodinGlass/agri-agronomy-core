use pyo3::prelude::*;

const MAX_JSON_DEPTH: usize = 1000;

fn py_to_json_value(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    py_to_json_value_at(obj, 0)
}

fn py_to_json_value_at(obj: &Bound<'_, PyAny>, depth: usize) -> PyResult<serde_json::Value> {
    use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};
    use serde_json::{Map, Number, Value};

    if depth > MAX_JSON_DEPTH {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "JSON nesting exceeds maximum depth (1000)",
        ));
    }

    // None
    if obj.is_none() {
        return Ok(Value::Null);
    }

    // bool MUST be checked before int (Python bool is a subclass of int).
    if let Ok(b) = obj.cast::<PyBool>() {
        return Ok(Value::Bool(b.is_true()));
    }

    // int -> i64 or u64. Larger integers are not supported (no arbitrary_precision).
    if let Ok(i) = obj.cast::<PyInt>() {
        if let Ok(v) = i.extract::<i64>() {
            return Ok(Value::Number(Number::from(v)));
        }
        if let Ok(v) = i.extract::<u64>() {
            return Ok(Value::Number(Number::from(v)));
        }
        return Err(pyo3::exceptions::PyValueError::new_err(
            "integer outside i64/u64 range is not supported",
        ));
    }

    // float -> f64 bits preserved via Number::from_f64.
    if let Ok(f) = obj.cast::<PyFloat>() {
        let v: f64 = f.extract()?;
        let num = Number::from_f64(v).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(
                "NaN or infinity is not valid JSON (matches Python allow_nan=False)",
            )
        })?;
        return Ok(Value::Number(num));
    }

    // str -> UTF-8 (PyO3 extract handles lone-surrogate rejection).
    if let Ok(s) = obj.cast::<PyString>() {
        return Ok(Value::String(s.extract()?));
    }

    // list and tuple -> array (json.dumps treats tuple as array).
    if let Ok(list) = obj.cast::<PyList>() {
        let mut arr = Vec::with_capacity(list.len());
        for item in list.iter() {
            arr.push(py_to_json_value_at(&item, depth + 1)?);
        }
        return Ok(Value::Array(arr));
    }
    if let Ok(tup) = obj.cast::<PyTuple>() {
        let mut arr = Vec::with_capacity(tup.len());
        for item in tup.iter() {
            arr.push(py_to_json_value_at(&item, depth + 1)?);
        }
        return Ok(Value::Array(arr));
    }

    // dict -> object with string keys only.
    if let Ok(dict) = obj.cast::<PyDict>() {
        let mut map = Map::new();
        for (k, v) in dict.iter() {
            let key: String = k.extract().map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("JSON object keys must be str")
            })?;
            map.insert(key, py_to_json_value_at(&v, depth + 1)?);
        }
        return Ok(Value::Object(map));
    }

    let type_name = obj
        .get_type()
        .name()
        .map(|n| n.to_string())
        .unwrap_or_else(|_| "<unknown>".to_string());
    Err(pyo3::exceptions::PyTypeError::new_err(format!(
        "type {type_name} is not JSON serializable"
    )))
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
