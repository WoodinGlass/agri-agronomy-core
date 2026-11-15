//! Pack kernel: content hashing over an allowlist of CSV/TOML files.
//!
//! See ADR-002 (two-hash model) and the Python oracle in
//! `src/agri_core/pack/verify.py` (`hash_pack_files`). Byte-identical to
//! Python for the same input + hash_alg.

pub mod build;
pub mod dict_info;
pub mod errors;
pub mod knowledge_set;
pub mod loader;
pub mod name_index;
pub mod normalize;
pub mod row_types;
pub mod rules;
pub mod tables;
pub mod unicode_pin;
pub mod validate;
pub mod verify;
