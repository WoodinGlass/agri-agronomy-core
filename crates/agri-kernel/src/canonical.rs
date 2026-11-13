//! Deterministic JSON encoding.
//! Byte-identical to Python's `canonical_json` in `src/agri_core/models/canonical.py`.
//! See ADR-019 section P2. NOT fully RFC 8785; Python's float repr is preserved.

use serde_json::Value;

#[derive(Debug)]
pub enum CanonicalError {
    NonFinite,
    Serde(String),
}

impl std::fmt::Display for CanonicalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CanonicalError::NonFinite => write!(f, "non-finite float"),
            CanonicalError::Serde(s) => write!(f, "serde: {s}"),
        }
    }
}

/// Python `repr(float)` equivalent for finite f64.
/// Python: 1.0 -> "1.0", 1e-7 -> "1e-07", 1e-4 -> "0.0001", 1e16 -> "1e+16".
fn py_float_repr(f: f64) -> String {
    let mut buf = ryu::Buffer::new();
    let raw = buf.format_finite(f).to_string();
    if let Some(e_pos) = raw.find(['e', 'E']) {
        let (mantissa, exp_part) = raw.split_at(e_pos);
        let exp_str = &exp_part[1..];
        let (sign, digits) = if exp_str.starts_with('-') || exp_str.starts_with('+') {
            (&exp_str[..1], &exp_str[1..])
        } else {
            ("+", exp_str)
        };
        let padded = if digits.len() < 2 {
            format!("0{}", digits)
        } else {
            digits.to_string()
        };
        return format!("{}e{}{}", mantissa, sign, padded);
    }
    raw
}

fn write_value<W: std::io::Write>(w: &mut W, v: &Value) -> Result<(), CanonicalError> {
    match v {
        Value::Null => w
            .write_all(b"null")
            .map_err(|e| CanonicalError::Serde(e.to_string()))?,
        Value::Bool(true) => w
            .write_all(b"true")
            .map_err(|e| CanonicalError::Serde(e.to_string()))?,
        Value::Bool(false) => w
            .write_all(b"false")
            .map_err(|e| CanonicalError::Serde(e.to_string()))?,
        Value::Number(n) => {
            if n.is_i64() || n.is_u64() {
                w.write_all(n.to_string().as_bytes())
                    .map_err(|e| CanonicalError::Serde(e.to_string()))?;
            } else if let Some(f) = n.as_f64() {
                if !f.is_finite() {
                    return Err(CanonicalError::NonFinite);
                }
                if f == 0.0 {
                    w.write_all(b"0.0")
                        .map_err(|e| CanonicalError::Serde(e.to_string()))?;
                } else {
                    w.write_all(py_float_repr(f).as_bytes())
                        .map_err(|e| CanonicalError::Serde(e.to_string()))?;
                }
            } else {
                return Err(CanonicalError::Serde("unrepresentable number".into()));
            }
        }
        Value::String(s) => {
            let esc = serde_json::to_string(s).map_err(|e| CanonicalError::Serde(e.to_string()))?;
            w.write_all(esc.as_bytes())
                .map_err(|e| CanonicalError::Serde(e.to_string()))?;
        }
        Value::Array(arr) => {
            w.write_all(b"[")
                .map_err(|e| CanonicalError::Serde(e.to_string()))?;
            for (i, item) in arr.iter().enumerate() {
                if i > 0 {
                    w.write_all(b",")
                        .map_err(|e| CanonicalError::Serde(e.to_string()))?;
                }
                write_value(w, item)?;
            }
            w.write_all(b"]")
                .map_err(|e| CanonicalError::Serde(e.to_string()))?;
        }
        Value::Object(map) => {
            w.write_all(b"{")
                .map_err(|e| CanonicalError::Serde(e.to_string()))?;
            let mut first = true;
            let sorted: std::collections::BTreeMap<&String, &Value> = map.iter().collect();
            for (k, v) in sorted {
                if !first {
                    w.write_all(b",")
                        .map_err(|e| CanonicalError::Serde(e.to_string()))?;
                }
                first = false;
                let esc_key =
                    serde_json::to_string(k).map_err(|e| CanonicalError::Serde(e.to_string()))?;
                w.write_all(esc_key.as_bytes())
                    .map_err(|e| CanonicalError::Serde(e.to_string()))?;
                w.write_all(b":")
                    .map_err(|e| CanonicalError::Serde(e.to_string()))?;
                write_value(w, v)?;
            }
            w.write_all(b"}")
                .map_err(|e| CanonicalError::Serde(e.to_string()))?;
        }
    }
    Ok(())
}

pub fn canonical_json(v: &Value) -> Result<Vec<u8>, CanonicalError> {
    let mut out = Vec::new();
    write_value(&mut out, v)?;
    Ok(out)
}
