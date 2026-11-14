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
    // Rust's Debug for f64 uses core::fmt's shortest-roundtrip algorithm,
    // which matches Python's repr for finite floats (both are David Gay's
    // shortest-representation family). `ryu::format_finite` has roundtrip
    // bugs for near-subnormal values (M20b diagnosis: 283/1000 random f64
    // failed to roundtrip via ryu). See ADR-019 section P2.
    let raw = format!("{:?}", f);
    // Python always uses 2+ digit zero-padded exponent with explicit sign:
    // e-08 (not e-8), e+16 (not e16). Apply only when there is an exponent.
    if let Some(e_pos) = raw.find(['e', 'E']) {
        let (mantissa, exp_part) = raw.split_at(e_pos);
        let exp_str = exp_part.get(1..).unwrap_or("");
        let (sign, digits) = if let Some(rest) = exp_str.strip_prefix('-') {
            ("-", rest)
        } else if let Some(rest) = exp_str.strip_prefix('+') {
            ("+", rest)
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

// ============================================================================
// RFC 8785 (JCS) canonical JSON
// ============================================================================
// See ADR-020. Mirrors src/agri_core/models/canonical.py::canonical_json_rfc8785.
// Cross-checked against Node.js JSON.stringify on 101 boundary cases
// (tests/vectors/canonical_rfc8785.json).

fn rfc8785_int(i: i64) -> Result<String, CanonicalError> {
    // Integers exact as IEEE 754 double format via rfc8785_float;
    // integers that lose precision are rejected.
    if i.unsigned_abs() < (1u64 << 53) {
        return Ok(i.to_string());
    }
    let f = i as f64;
    let f_back = f as i128;
    let i_128 = i as i128;
    if f_back != i_128 {
        return Err(CanonicalError::Serde(format!(
            "RFC 8785: integer {} loses precision as IEEE 754 double",
            i
        )));
    }
    rfc8785_float(f)
}

fn rfc8785_uint(u: u64) -> Result<String, CanonicalError> {
    if u < (1u64 << 53) {
        return Ok(u.to_string());
    }
    let f = u as f64;
    let f_back = f as u128;
    let u_128 = u as u128;
    if f_back != u_128 {
        return Err(CanonicalError::Serde(format!(
            "RFC 8785: integer {} loses precision as IEEE 754 double",
            u
        )));
    }
    rfc8785_float(f)
}

/// ECMA-262 section 7.1.12.1 Number.prototype.toString (RFC 8785 s3.2.2.3).
fn rfc8785_float(f: f64) -> Result<String, CanonicalError> {
    if f.is_nan() {
        return Err(CanonicalError::NonFinite);
    }
    if f.is_infinite() {
        return Err(CanonicalError::NonFinite);
    }
    if f == 0.0 {
        // Covers both +0.0 and -0.0.
        return Ok("0".to_string());
    }
    let sign = if f < 0.0 { "-" } else { "" };
    let abs = f.abs();
    // Shortest-roundtrip exponential form: "<mantissa>e<exp>".
    // For -0.0 we already returned early; abs > 0 here.
    let sci = format!("{:e}", abs);
    let (mant_str, exp_str) = sci
        .split_once('e')
        .ok_or_else(|| CanonicalError::Serde(format!("unexpected sci form: {sci}")))?;
    let exp: i32 = exp_str
        .parse()
        .map_err(|_| CanonicalError::Serde(format!("bad exp in sci: {exp_str}")))?;

    let digits: String = mant_str.chars().filter(|c| *c != '.').collect();
    let k = digits.len() as i32;
    // ECMA's `n`: position of the decimal point relative to the first
    // significant digit. For `m x 10^exp` with 1 <= m < 10, n = exp + 1.
    let n = exp + 1;

    let body = if n > 0 && n <= 21 {
        // Plain decimal notation.
        if n >= k {
            let pad = (n - k) as usize;
            let mut s = digits;
            s.push_str(&"0".repeat(pad));
            s
        } else {
            let head: String = digits.chars().take(n as usize).collect();
            let tail: String = digits.chars().skip(n as usize).collect();
            format!("{head}.{tail}")
        }
    } else if n > -6 && n <= 0 {
        // Small decimal: 0.000...digits.
        let zeros = "0".repeat((-n) as usize);
        format!("0.{zeros}{digits}")
    } else {
        // Scientific notation: d[.ddd]e+/-NN.
        let exp_val = n - 1;
        let sign_exp = if exp_val >= 0 { "+" } else { "-" };
        let abs_exp = exp_val.unsigned_abs();
        if k == 1 {
            format!("{digits}e{sign_exp}{abs_exp}")
        } else {
            let head: String = digits.chars().take(1).collect();
            let tail: String = digits.chars().skip(1).collect();
            format!("{head}.{tail}e{sign_exp}{abs_exp}")
        }
    };
    Ok(format!("{sign}{body}"))
}

fn werr(e: std::io::Error) -> CanonicalError {
    CanonicalError::Serde(e.to_string())
}

fn serr(e: serde_json::Error) -> CanonicalError {
    CanonicalError::Serde(e.to_string())
}

fn write_rfc8785<W: std::io::Write>(w: &mut W, v: &Value) -> Result<(), CanonicalError> {
    match v {
        Value::Null => w.write_all(b"null").map_err(werr),
        Value::Bool(true) => w.write_all(b"true").map_err(werr),
        Value::Bool(false) => w.write_all(b"false").map_err(werr),
        Value::Number(n) => {
            let s = if let Some(i) = n.as_i64() {
                rfc8785_int(i)?
            } else if let Some(u) = n.as_u64() {
                rfc8785_uint(u)?
            } else if let Some(f) = n.as_f64() {
                rfc8785_float(f)?
            } else {
                return Err(CanonicalError::Serde("unrepresentable number".into()));
            };
            w.write_all(s.as_bytes()).map_err(werr)
        }
        Value::String(s) => {
            // serde_json::to_string matches RFC 8785 s3.2.2.2:
            // escapes ", \, control chars; leaves non-ASCII as UTF-8.
            let esc = serde_json::to_string(s).map_err(serr)?;
            w.write_all(esc.as_bytes()).map_err(werr)
        }
        Value::Array(arr) => {
            w.write_all(b"[").map_err(werr)?;
            for (i, item) in arr.iter().enumerate() {
                if i > 0 {
                    w.write_all(b",").map_err(werr)?;
                }
                write_rfc8785(w, item)?;
            }
            w.write_all(b"]").map_err(werr)
        }
        Value::Object(map) => {
            w.write_all(b"{").map_err(werr)?;
            // Sort keys by UTF-16 code units (RFC 8785 s3.2.3).
            let mut entries: Vec<(Vec<u16>, &String, &Value)> = map
                .iter()
                .map(|(k, v)| (k.encode_utf16().collect::<Vec<u16>>(), k, v))
                .collect();
            entries.sort_by(|a, b| a.0.cmp(&b.0));
            let mut first = true;
            for (_, k, v) in entries {
                if !first {
                    w.write_all(b",").map_err(werr)?;
                }
                first = false;
                let esc_key = serde_json::to_string(k).map_err(serr)?;
                w.write_all(esc_key.as_bytes()).map_err(werr)?;
                w.write_all(b":").map_err(werr)?;
                write_rfc8785(w, v)?;
            }
            w.write_all(b"}").map_err(werr)
        }
    }
}

/// Return RFC 8785 (JCS) canonical JSON bytes for a serde_json Value.
///
/// Implements:
///   - Number per ECMA-262 s7.1.12.1 (1.0 -> "1", 1e-7 -> "1e-7",
///     -0.0 -> "0", 1e21 -> "1e+21").
///   - Object key sort by UTF-16 code units.
///   - Reject: NaN, Infinity, integers losing double precision.
///
/// Byte-identical to Python `canonical_json_rfc8785`.
pub fn canonical_json_rfc8785(v: &Value) -> Result<Vec<u8>, CanonicalError> {
    let mut out = Vec::new();
    write_rfc8785(&mut out, v)?;
    Ok(out)
}
