//! Minimal mirror of Python `Dictionary` (`models/dictionary.py`) +
//! `ParameterDef` (`models/parameter.py`) for rules and `_validate_structure`.
//!
//! Conversion from Python dict happens in `agri-py` (cell 5d); this module
//! is pure Rust.

use std::collections::BTreeMap;

/// `applies_to` sub-struct (mirror of `ParameterDef.applies_to`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct AppliesToInfo {
    pub organism_groups: Vec<String>,
    pub archetypes: Option<Vec<String>>,
    pub uses: Option<Vec<String>>,
    pub systems: Option<Vec<String>>,
    pub traits: Option<Vec<String>>,
}

/// `ParameterDef` (mirror of `models/parameter.py::ParameterDef`).
///
/// Only fields used by `rules/*.rs` and `_validate_structure` are mirrored.
/// `description`, `rationale`, `introduced_in`, `deprecated_in`,
/// `replaced_by`, `rule_schema` are dropped (not used by validation).
#[derive(Debug, Clone, PartialEq)]
pub struct ParameterInfo {
    pub key: String,
    pub stage: String,
    pub shape: String,
    pub unit: Option<String>,
    pub physical_range: Option<(f64, f64)>,
    pub enum_values: Option<Vec<String>>,
    pub enum_source: Option<String>,
    pub phase_set: String,
    pub allowed_phases: Option<Vec<String>>,
    pub applies_to: AppliesToInfo,
    pub scope_keys: Vec<String>,
    pub used_by: Vec<String>,
    pub tier_required: bool,
    pub safety_class: String,
    pub kind: String,
}

/// Mirror of `models/dictionary.py::Dictionary`.
#[derive(Debug, Clone, PartialEq)]
pub struct DictionaryInfo {
    pub version: String,
    pub parameters: BTreeMap<String, ParameterInfo>,
    pub phases_by_archetype: BTreeMap<String, Vec<String>>,
}

impl DictionaryInfo {
    pub fn empty() -> Self {
        Self {
            version: String::new(),
            parameters: BTreeMap::new(),
            phases_by_archetype: BTreeMap::new(),
        }
    }
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod tests {
    use super::*;

    #[test]
    fn empty_dictionary_has_zero_params() {
        let d = DictionaryInfo::empty();
        assert!(d.parameters.is_empty());
        assert!(d.phases_by_archetype.is_empty());
        assert!(d.version.is_empty());
    }

    #[test]
    fn applies_to_default_all_none_except_organism() {
        let a = AppliesToInfo::default();
        assert!(a.organism_groups.is_empty());
        assert!(a.archetypes.is_none());
        assert!(a.uses.is_none());
        assert!(a.systems.is_none());
        assert!(a.traits.is_none());
    }
}
