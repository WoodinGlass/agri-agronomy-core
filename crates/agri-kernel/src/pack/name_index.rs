//! Name index: normalized taxon name -> entries for resolution.
//!
//! Pure function of (`taxa`, `names`). Mirrors pack/name_index.py.
//! Built at load from raw rows (never stored, never tied to a
//! KnowledgeSet across backend switches; see ADR-019 §11.5).

use std::collections::BTreeMap;

use crate::pack::normalize::normalize_name;
use crate::pack::row_types::{NameRow, TaxonRow};

const SYNTHETIC_LANGUAGE: &str = "la";

/// How a `NameIndexEntry` matched the query.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum MatchedVia {
    ScientificName,
    AcceptedName,
    Names,
}

impl MatchedVia {
    pub fn as_str(self) -> &'static str {
        match self {
            MatchedVia::ScientificName => "scientific_name",
            MatchedVia::AcceptedName => "accepted_name",
            MatchedVia::Names => "names",
        }
    }
}

/// One entry in the name index.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NameIndexEntry {
    pub taxon_id: String,
    pub name: String,
    pub normalized_name: String,
    pub language: String,
    pub kind: String,
    pub preferred: bool,
    pub matched_via: MatchedVia,
    pub rank: String,
    pub scientific_name: String,
}

impl Ord for NameIndexEntry {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        (
            &self.taxon_id,
            self.matched_via.as_str(),
            &self.language,
            &self.name,
        )
            .cmp(&(
                &other.taxon_id,
                other.matched_via.as_str(),
                &other.language,
                &other.name,
            ))
    }
}

impl PartialOrd for NameIndexEntry {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

/// Build `{normalized_name: sorted Vec<NameIndexEntry>}`.
///
/// Deterministic: `BTreeMap` outer keys, sorted `Vec` per bucket ordered by
/// `(taxon_id, matched_via, language, name)`. Matches Python's tuple-sorted
/// output exactly.
pub fn build_name_index(
    taxa: &[TaxonRow],
    names: &[NameRow],
) -> BTreeMap<String, Vec<NameIndexEntry>> {
    let mut names_by_taxon: BTreeMap<&str, Vec<&NameRow>> = BTreeMap::new();
    for row in names {
        names_by_taxon
            .entry(row.taxon_id.as_str())
            .or_default()
            .push(row);
    }

    let mut acc: BTreeMap<String, Vec<NameIndexEntry>> = BTreeMap::new();

    let mut add = |entry: NameIndexEntry| {
        acc.entry(entry.normalized_name.clone())
            .or_default()
            .push(entry);
    };

    for taxon in taxa {
        let sci_norm = normalize_name(&taxon.scientific_name);
        add(NameIndexEntry {
            taxon_id: taxon.taxon_id.clone(),
            name: taxon.scientific_name.clone(),
            normalized_name: sci_norm.clone(),
            language: SYNTHETIC_LANGUAGE.to_string(),
            kind: "scientific".to_string(),
            preferred: true,
            matched_via: MatchedVia::ScientificName,
            rank: taxon.rank.clone(),
            scientific_name: taxon.scientific_name.clone(),
        });

        if let Some(acc_name) = &taxon.accepted_name {
            let acc_norm = normalize_name(acc_name);
            if acc_norm != sci_norm {
                add(NameIndexEntry {
                    taxon_id: taxon.taxon_id.clone(),
                    name: acc_name.clone(),
                    normalized_name: acc_norm,
                    language: SYNTHETIC_LANGUAGE.to_string(),
                    kind: "scientific".to_string(),
                    preferred: false,
                    matched_via: MatchedVia::AcceptedName,
                    rank: taxon.rank.clone(),
                    scientific_name: taxon.scientific_name.clone(),
                });
            }
        }

        if let Some(rows) = names_by_taxon.get(taxon.taxon_id.as_str()) {
            for name_row in rows {
                add(NameIndexEntry {
                    taxon_id: taxon.taxon_id.clone(),
                    name: name_row.name.clone(),
                    normalized_name: normalize_name(&name_row.name),
                    language: name_row.language.clone(),
                    kind: name_row.kind.clone(),
                    preferred: name_row.preferred,
                    matched_via: MatchedVia::Names,
                    rank: taxon.rank.clone(),
                    scientific_name: taxon.scientific_name.clone(),
                });
            }
        }
    }

    for entries in acc.values_mut() {
        entries.sort();
    }
    acc
}

/// Look up entries for a query string. Returns empty slice if no match.
pub fn lookup<'a>(
    index: &'a BTreeMap<String, Vec<NameIndexEntry>>,
    query: &str,
) -> &'a [NameIndexEntry] {
    let normalized = normalize_name(query);
    index.get(&normalized).map(|v| v.as_slice()).unwrap_or(&[])
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

    fn taxon(id: &str, sci: &str, accepted: Option<&str>, rank: &str) -> TaxonRow {
        TaxonRow {
            taxon_id: id.into(),
            rank: rank.into(),
            scientific_name: sci.into(),
            accepted_name: accepted.map(|s| s.into()),
            organism_group: "vascular_plant".into(),
            archetype: "annual".into(),
            uses: vec!["vegetable".into()],
            traits: vec![],
            parent_id: None,
            external_ids: None,
            src: Some(vec!["S001".into()]),
            dataset_id: None,
        }
    }

    fn name(tid: &str, nm: &str, lang: &str, kind: &str, pref: bool) -> NameRow {
        NameRow {
            taxon_id: tid.into(),
            name: nm.into(),
            language: lang.into(),
            script: "Latn".into(),
            kind: kind.into(),
            preferred: pref,
            src: Some(vec!["S001".into()]),
            dataset_id: None,
        }
    }

    #[test]
    fn empty_input() {
        let idx = build_name_index(&[], &[]);
        assert!(idx.is_empty());
    }

    #[test]
    fn single_taxon_scientific() {
        let taxa = vec![taxon("T01", "Solanum lycopersicum", None, "species")];
        let idx = build_name_index(&taxa, &[]);
        let key = "solanum lycopersicum";
        assert!(
            idx.contains_key(key),
            "index keys: {:?}",
            idx.keys().collect::<Vec<_>>()
        );
        let entries = idx.get(key).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].taxon_id, "T01");
        assert_eq!(entries[0].matched_via, MatchedVia::ScientificName);
        assert_eq!(entries[0].language, "la");
    }

    #[test]
    fn accepted_name_distinct() {
        let taxa = vec![taxon(
            "T01",
            "Solanum lycopersicum",
            Some("Lycopersicon esculentum"),
            "species",
        )];
        let idx = build_name_index(&taxa, &[]);
        assert!(idx.contains_key("solanum lycopersicum"));
        assert!(idx.contains_key("lycopersicon esculentum"));
    }

    #[test]
    fn accepted_same_as_scientific_skipped() {
        let taxa = vec![taxon("T01", "Testus", Some("Testus"), "species")];
        let idx = build_name_index(&taxa, &[]);
        let entries = idx.get("testus").unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].matched_via, MatchedVia::ScientificName);
    }

    #[test]
    fn names_rows_added() {
        let taxa = vec![taxon("T01", "Solanum lycopersicum", None, "species")];
        let names = vec![
            name("T01", "Tomato", "en", "common", true),
            name("T01", "Tomat", "id", "common", true),
        ];
        let idx = build_name_index(&taxa, &names);
        assert!(idx.contains_key("tomato"));
        assert!(idx.contains_key("tomat"));
    }

    #[test]
    fn lookup_via_normalize() {
        let taxa = vec![taxon("T01", "Solanum lycopersicum", None, "species")];
        let idx = build_name_index(&taxa, &[]);
        let hits = lookup(&idx, "SOLANUM Lycopersicum");
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].taxon_id, "T01");
    }

    #[test]
    fn deterministic_order() {
        let taxa = vec![
            taxon("T02", "Testus", None, "species"),
            taxon("T01", "Testus", None, "species"),
        ];
        let idx = build_name_index(&taxa, &[]);
        let entries = idx.get("testus").unwrap();
        assert_eq!(entries[0].taxon_id, "T01");
        assert_eq!(entries[1].taxon_id, "T02");
    }
}
