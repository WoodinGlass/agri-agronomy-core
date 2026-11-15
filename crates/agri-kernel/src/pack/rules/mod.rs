//! Validation rules (mirror of `src/agri_core/pack/validate.py` RULES).
//!
//! Each rule is a standalone function `fn(ctx: &RuleContext) -> Vec<Finding>`.
//! The orchestrator (`validate.rs`) collects findings from all rules, then
//! sorts by `_sort_key` (file, line, key, taxon_id, code) to match Python's
//! `ValidationReport` ordering exactly.
//!
//! Findings carry `code: &'static str` matching Python's `Finding.code`.
//! Messages are formatted to be byte-identical to Python's f-strings; the
//! helpers `py_float_str`, `py_repr_str`, `py_repr_opt_str` reproduce
//! Python's `str(float)` / `repr(str)` / `repr(Optional[str])` semantics.
//!
//! First 4 rules (this module + trapezoid.rs + superseded.rs + fact_key.rs):
//! - `check_trapezoid_not_degenerate`
//! - `check_superseded_self`
//! - `check_superseded_cycle`
//! - `check_fact_key_duplicate`
//!
//! Remaining 12 rules (license, safety, protection, id_ledger, catalog)
//! ship in cell 5c; orchestrator + `_validate_structure` in cell 5d.

pub mod catalog;
pub mod fact_key;
pub mod id_ledger;
pub mod license;
pub mod protection;
pub mod safety;
pub mod superseded;
pub mod trapezoid;

use std::collections::HashMap;
use std::sync::LazyLock;

use crate::pack::dict_info::DictionaryInfo;
use crate::pack::row_types::{DatasetRow, FactRow, HazardRow, NameRow, SourceRow, TaxonRow};

// Shared empty constants for tests and (cell 5d) `validate.rs` defaults.
// Production `validate.rs` will pass these when no files/dictionary are
// available; until then only tests use them, so dead_code fires without
// the allow. Removed in cell 5d once production references exist.
#[allow(dead_code)]
pub(crate) static EMPTY_FILES: LazyLock<HashMap<String, Vec<u8>>> = LazyLock::new(HashMap::new);
#[allow(dead_code)]
pub(crate) static EMPTY_DICT: LazyLock<DictionaryInfo> = LazyLock::new(DictionaryInfo::empty);

// ---- Finding types ----

/// Severity, mirrors `FindingSeverity` (Python StrEnum).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
}

impl Severity {
    pub fn as_str(self) -> &'static str {
        match self {
            Severity::Error => "error",
            Severity::Warning => "warning",
        }
    }
}

/// Location, mirrors `FindingLocation` (Python Pydantic model).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FindingLocation {
    pub file: Option<String>,
    pub line: Option<usize>,
    pub key: Option<String>,
    pub taxon_id: Option<String>,
    pub fact_id: Option<String>,
    pub parameter: Option<String>,
    pub phase: Option<String>,
}

impl FindingLocation {
    pub fn with_taxon_fact_param(taxon_id: String, fact_id: String, parameter: String) -> Self {
        Self {
            taxon_id: Some(taxon_id),
            fact_id: Some(fact_id),
            parameter: Some(parameter),
            ..Default::default()
        }
    }

    pub fn with_taxon_fact_param_phase(
        taxon_id: String,
        fact_id: String,
        parameter: String,
        phase: Option<String>,
    ) -> Self {
        Self {
            taxon_id: Some(taxon_id),
            fact_id: Some(fact_id),
            parameter: Some(parameter),
            phase,
            ..Default::default()
        }
    }
}

/// One validation finding, mirrors `Finding` (Python Pydantic model).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    pub code: &'static str,
    pub severity: Severity,
    pub message: String,
    pub location: FindingLocation,
}

impl Finding {
    pub fn error(code: &'static str, message: String, location: FindingLocation) -> Self {
        Self {
            code,
            severity: Severity::Error,
            message,
            location,
        }
    }
}

// ---- RuleContext ----

/// Bundles validated rows for rules to scan.
///
/// Extended in cell 5c with `files: &HashMap<String, Vec<u8>>` and
/// `dictionary: &DictionaryInfo` (for license/protection/catalog rules).
pub struct RuleContext<'a> {
    pub taxa: &'a [TaxonRow],
    pub names: &'a [NameRow],
    pub facts: &'a [FactRow],
    pub hazards: &'a [HazardRow],
    pub sources: &'a [SourceRow],
    pub datasets: &'a [DatasetRow],
    pub files: &'a HashMap<String, Vec<u8>>,
    pub dictionary: &'a DictionaryInfo,
}

// ---- Python-compatible formatting helpers ----

/// Python `str(float)`: `4.5` → `"4.5"`, `NaN` → `"nan"`, `inf` → `"inf"`.
///
/// Delegates to `canonical::py_float_repr` for finite values (already
/// byte-identical to Python `repr(float)`); handles non-finite explicitly
/// because Python prints `"nan"` (lowercase) while Rust `{:?}` prints
/// `"NaN"`.
pub(crate) fn py_float_str(f: f64) -> String {
    if f.is_nan() {
        "nan".to_string()
    } else if f.is_infinite() {
        if f > 0.0 {
            "inf".to_string()
        } else {
            "-inf".to_string()
        }
    } else {
        crate::canonical::py_float_repr(f)
    }
}

/// Python `repr(str)`: `'value'` with single quotes, escapes `\\`, `'`,
/// `\n`, `\r`, `\t`, control chars as `\xNN`.
pub(crate) fn py_repr_str(s: &str) -> String {
    use std::fmt::Write;
    let mut out = String::with_capacity(s.len() + 2);
    out.push('\'');
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 || (c as u32) == 0x7F => {
                let _ = write!(out, "\\x{:02x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('\'');
    out
}

/// Python `repr(Optional[str])`: `None` → `"None"`, `Some(s)` → `repr(s)`.
pub(crate) fn py_repr_opt_str(s: Option<&str>) -> String {
    match s {
        None => "None".to_string(),
        Some(v) => py_repr_str(v),
    }
}

/// Format a 4-tuple like Python `repr((a, b, c, d))` for floats.
pub(crate) fn py_tuple4_f64(pts: &[f64; 4]) -> String {
    format!(
        "({}, {}, {}, {})",
        py_float_str(pts[0]),
        py_float_str(pts[1]),
        py_float_str(pts[2]),
        py_float_str(pts[3])
    )
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

    #[test]
    fn py_float_str_finite() {
        assert_eq!(py_float_str(4.5), "4.5");
        assert_eq!(py_float_str(4.0), "4.0");
        assert_eq!(py_float_str(-1.25), "-1.25");
        assert_eq!(py_float_str(0.0), "0.0");
    }

    #[test]
    fn py_float_str_exponent() {
        // Python repr(1e-7) = "1e-07" (2-digit zero-padded exp)
        assert_eq!(py_float_str(1e-7), "1e-07");
        assert_eq!(py_float_str(1e21), "1e+21");
    }

    #[test]
    fn py_float_str_nonfinite() {
        assert_eq!(py_float_str(f64::NAN), "nan");
        assert_eq!(py_float_str(f64::INFINITY), "inf");
        assert_eq!(py_float_str(f64::NEG_INFINITY), "-inf");
    }

    #[test]
    fn py_repr_str_simple() {
        assert_eq!(py_repr_str("hello"), "'hello'");
        assert_eq!(py_repr_str(""), "''");
    }

    #[test]
    fn py_repr_str_escapes() {
        assert_eq!(py_repr_str("it's"), "'it\\'s'");
        assert_eq!(py_repr_str("a\\b"), "'a\\\\b'");
        assert_eq!(py_repr_str("a\nb"), "'a\\nb'");
        assert_eq!(py_repr_str("a\tb"), "'a\\tb'");
    }

    #[test]
    fn py_repr_str_control() {
        assert_eq!(py_repr_str("\x00"), "'\\x00'");
        assert_eq!(py_repr_str("\x1f"), "'\\x1f'");
        assert_eq!(py_repr_str("\x7f"), "'\\x7f'");
    }

    #[test]
    fn py_repr_opt_str_none() {
        assert_eq!(py_repr_opt_str(None), "None");
    }

    #[test]
    fn py_repr_opt_str_some() {
        assert_eq!(py_repr_opt_str(Some("midseason")), "'midseason'");
    }

    #[test]
    fn test_py_tuple4_f64_helper() {
        assert_eq!(py_tuple4_f64(&[4.5, 6.0, 7.0, 8.5]), "(4.5, 6.0, 7.0, 8.5)");
    }

    #[test]
    fn severity_as_str() {
        assert_eq!(Severity::Error.as_str(), "error");
        assert_eq!(Severity::Warning.as_str(), "warning");
    }
}
