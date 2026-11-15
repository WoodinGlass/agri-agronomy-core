//! Pack-error types (mirror of `src/agri_core/pack/errors.py`).
//!
//! Python uses one Exception subclass per code; Rust uses one `PackError`
//! struct with a `code: &'static str` field. The PyO3 binding in
//! `crates/agri-py/src/lib.rs` maps each `code` back to the correct Python
//! exception class, so callers see identical Python exceptions whether
//! they went through Python or Rust.
//!
//! Codes are stable public identifiers (see `docs/PACK_FORMAT.md`); they
//! are part of the CLI JSON contract (`agri-core validate --json`) and
//! are tested by `tests/contract/test_native_parity_validate.py`.

use std::fmt;

/// A pack-loading or pack-validation failure.
///
/// `findings` holds additional `PackError` instances when a batch check
/// collects more than one problem (up to 20 per Python `_MAX_FINDINGS`).
#[derive(Debug, Clone)]
pub struct PackError {
    pub code: &'static str,
    pub message: String,
    pub file: Option<String>,
    pub line: Option<usize>,
    pub key: Option<String>,
    pub findings: Vec<PackError>,
}

impl PackError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            file: None,
            line: None,
            key: None,
            findings: Vec::new(),
        }
    }

    /// Attach a `file` location (chainable).
    pub fn with_file(mut self, file: impl Into<String>) -> Self {
        self.file = Some(file.into());
        self
    }

    /// Attach a `line` location (chainable).
    pub fn with_line(mut self, line: usize) -> Self {
        self.line = Some(line);
        self
    }

    /// Attach a `key` location (chainable).
    pub fn with_key(mut self, key: impl Into<String>) -> Self {
        self.key = Some(key.into());
        self
    }

    /// Attach a batch of related findings.
    pub fn with_findings(mut self, findings: Vec<PackError>) -> Self {
        self.findings = findings;
        self
    }

    /// Return the Python exception class name for this code.
    ///
    /// Used by the PyO3 binding to raise the matching Python exception
    /// so callers see identical behavior between Rust and Python paths.
    pub fn python_class(&self) -> &'static str {
        match self.code {
            "PACK_NOT_FOUND" => "PackNotFoundError",
            "PACK_INVALID" => "InvalidPackError",
            "PACK_SCHEMA_UNSUPPORTED" => "UnsupportedSchemaVersionError",
            "PACK_ENGINE_TOO_OLD" => "EngineTooOldError",
            "PACK_TABLE_INVALID" => "PackTableInvalidError",
            "PACK_DUPLICATE_KEY" => "PackDuplicateKeyError",
            "PACK_FK_VIOLATION" => "PackFKViolationError",
            "PACK_UNKNOWN_PARAMETER" => "PackUnknownParameterError",
            "PACK_SHAPE_MISMATCH" => "PackShapeMismatchError",
            "PACK_PHASE_INVALID" => "PackPhaseInvalidError",
            "PACK_SCOPE_INVALID" => "PackScopeInvalidError",
            "PACK_HASH_MISMATCH" => "PackHashMismatchError",
            "PACK_TOO_LARGE" => "PackTooLargeError",
            "PACK_FEATURE_UNSUPPORTED" => "PackFeatureUnsupportedError",
            "PACK_DICTIONARY_INCOMPATIBLE" => "PackDictionaryIncompatibleError",
            "PACK_SYNTHETIC_NOT_ALLOWED" => "PackSyntheticNotAllowedError",
            "PACK_VALUE_OUT_OF_RANGE" => "PackValueOutOfRangeError",
            "PACK_ENUM_INVALID" => "PackEnumInvalidError",
            "PACK_UNIT_MISMATCH" => "PackUnitMismatchError",
            "PACK_SAFETY_VIOLATION" => "PackSafetyViolationError",
            "PACK_STALE_ARTIFACT" => "PackStaleArtifactError",
            "PACK_FIELD_TOO_LARGE" => "PackFieldTooLargeError",
            "PACK_ROW_TOO_LARGE" => "PackRowTooLargeError",
            _ => "PackError",
        }
    }

    // ---- Typed constructors (mirror Python subclass names) ----

    pub fn pack_not_found(msg: impl Into<String>) -> Self {
        Self::new("PACK_NOT_FOUND", msg)
    }
    pub fn pack_invalid(msg: impl Into<String>) -> Self {
        Self::new("PACK_INVALID", msg)
    }
    pub fn schema_unsupported(msg: impl Into<String>) -> Self {
        Self::new("PACK_SCHEMA_UNSUPPORTED", msg)
    }
    pub fn engine_too_old(msg: impl Into<String>) -> Self {
        Self::new("PACK_ENGINE_TOO_OLD", msg)
    }
    pub fn table_invalid(msg: impl Into<String>) -> Self {
        Self::new("PACK_TABLE_INVALID", msg)
    }
    pub fn duplicate_key(msg: impl Into<String>) -> Self {
        Self::new("PACK_DUPLICATE_KEY", msg)
    }
    pub fn fk_violation(msg: impl Into<String>) -> Self {
        Self::new("PACK_FK_VIOLATION", msg)
    }
    pub fn unknown_parameter(msg: impl Into<String>) -> Self {
        Self::new("PACK_UNKNOWN_PARAMETER", msg)
    }
    pub fn shape_mismatch(msg: impl Into<String>) -> Self {
        Self::new("PACK_SHAPE_MISMATCH", msg)
    }
    pub fn phase_invalid(msg: impl Into<String>) -> Self {
        Self::new("PACK_PHASE_INVALID", msg)
    }
    pub fn scope_invalid(msg: impl Into<String>) -> Self {
        Self::new("PACK_SCOPE_INVALID", msg)
    }
    pub fn hash_mismatch(msg: impl Into<String>) -> Self {
        Self::new("PACK_HASH_MISMATCH", msg)
    }
    pub fn too_large(msg: impl Into<String>) -> Self {
        Self::new("PACK_TOO_LARGE", msg)
    }
    pub fn feature_unsupported(msg: impl Into<String>) -> Self {
        Self::new("PACK_FEATURE_UNSUPPORTED", msg)
    }
    pub fn dictionary_incompatible(msg: impl Into<String>) -> Self {
        Self::new("PACK_DICTIONARY_INCOMPATIBLE", msg)
    }
    pub fn synthetic_not_allowed(msg: impl Into<String>) -> Self {
        Self::new("PACK_SYNTHETIC_NOT_ALLOWED", msg)
    }
    pub fn value_out_of_range(msg: impl Into<String>) -> Self {
        Self::new("PACK_VALUE_OUT_OF_RANGE", msg)
    }
    pub fn enum_invalid(msg: impl Into<String>) -> Self {
        Self::new("PACK_ENUM_INVALID", msg)
    }
    pub fn unit_mismatch(msg: impl Into<String>) -> Self {
        Self::new("PACK_UNIT_MISMATCH", msg)
    }
    pub fn safety_violation(msg: impl Into<String>) -> Self {
        Self::new("PACK_SAFETY_VIOLATION", msg)
    }
    pub fn stale_artifact(msg: impl Into<String>) -> Self {
        Self::new("PACK_STALE_ARTIFACT", msg)
    }
    pub fn field_too_large(msg: impl Into<String>) -> Self {
        Self::new("PACK_FIELD_TOO_LARGE", msg)
    }
    pub fn row_too_large(msg: impl Into<String>) -> Self {
        Self::new("PACK_ROW_TOO_LARGE", msg)
    }
}

impl fmt::Display for PackError {
    /// Formats like Python's `str(PackError)`: only the message.
    /// Location fields are exposed as struct fields, not in the Display.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for PackError {}

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
    fn pack_error_code_and_message() {
        let e = PackError::pack_invalid("bad pack.toml");
        assert_eq!(e.code, "PACK_INVALID");
        assert_eq!(e.message, "bad pack.toml");
        assert!(e.file.is_none());
        assert!(e.line.is_none());
        assert!(e.key.is_none());
        assert!(e.findings.is_empty());
    }

    #[test]
    fn with_location_chain() {
        let e = PackError::table_invalid("bad cell")
            .with_file("facts/T000000001.csv")
            .with_line(42)
            .with_key("value");
        assert_eq!(e.file.as_deref(), Some("facts/T000000001.csv"));
        assert_eq!(e.line, Some(42));
        assert_eq!(e.key.as_deref(), Some("value"));
    }

    #[test]
    fn display_matches_python_str() {
        let e = PackError::pack_invalid("content_hash mismatch");
        assert_eq!(format!("{e}"), "content_hash mismatch");
    }

    #[test]
    fn python_class_mapping() {
        assert_eq!(
            PackError::pack_invalid("x").python_class(),
            "InvalidPackError"
        );
        assert_eq!(
            PackError::table_invalid("x").python_class(),
            "PackTableInvalidError"
        );
        assert_eq!(
            PackError::fk_violation("x").python_class(),
            "PackFKViolationError"
        );
        assert_eq!(
            PackError::safety_violation("x").python_class(),
            "PackSafetyViolationError"
        );
        assert_eq!(
            PackError::synthetic_not_allowed("x").python_class(),
            "PackSyntheticNotAllowedError"
        );
    }

    #[test]
    fn with_findings() {
        let inner = PackError::duplicate_key("dup").with_key("T000000001");
        let outer = PackError::fk_violation("multiple").with_findings(vec![inner.clone()]);
        assert_eq!(outer.findings.len(), 1);
        assert_eq!(outer.findings[0].code, "PACK_DUPLICATE_KEY");
    }

    #[test]
    fn all_24_codes_have_python_class() {
        // Every code must map to a non-default class.
        let codes: [&str; 23] = [
            "PACK_NOT_FOUND",
            "PACK_INVALID",
            "PACK_SCHEMA_UNSUPPORTED",
            "PACK_ENGINE_TOO_OLD",
            "PACK_TABLE_INVALID",
            "PACK_DUPLICATE_KEY",
            "PACK_FK_VIOLATION",
            "PACK_UNKNOWN_PARAMETER",
            "PACK_SHAPE_MISMATCH",
            "PACK_PHASE_INVALID",
            "PACK_SCOPE_INVALID",
            "PACK_HASH_MISMATCH",
            "PACK_TOO_LARGE",
            "PACK_FEATURE_UNSUPPORTED",
            "PACK_DICTIONARY_INCOMPATIBLE",
            "PACK_SYNTHETIC_NOT_ALLOWED",
            "PACK_VALUE_OUT_OF_RANGE",
            "PACK_ENUM_INVALID",
            "PACK_UNIT_MISMATCH",
            "PACK_SAFETY_VIOLATION",
            "PACK_STALE_ARTIFACT",
            "PACK_FIELD_TOO_LARGE",
            "PACK_ROW_TOO_LARGE",
        ];
        for code in codes {
            let e = PackError {
                code,
                message: "x".into(),
                file: None,
                line: None,
                key: None,
                findings: Vec::new(),
            };
            assert_ne!(
                e.python_class(),
                "PackError",
                "code {code} has no specific python_class mapping"
            );
        }
    }
}
