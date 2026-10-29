# Resolution policy

Normative specification for `resolve_taxon` and `resolve_fact`. Rationale
and trade-offs are in [`decisions/ADR-004-resolution-policy.md`](decisions/ADR-004-resolution-policy.md).
This page specifies **what** the engine does, with worked examples that
name the tests enforcing each behavior.

## `resolve_taxon`

### Return union

`resolve_taxon` returns a `TaxonOutcome`, one of:

- **`TaxonOk`**: `taxon_id`, `name`, `matched_via` (`scientific_name`,
  `accepted_name` or `names`), `scientific_name`, `rank`.
- **`Ambiguous`**: `candidates` (capped at 20, sorted by `taxon_id`) and
  `truncated` (true when the cap was hit).
- **`Unknown`**: `reason` (mandatory) and optional `code` from
  `schema/unknown_code_registry.json`.

### Matching order

1. Normalize the query: Unicode NFC, casefold, strip.
2. Look up the normalized string in the name index built at load time.
3. Rank candidates by `matched_via` precedence: `scientific_name` →
   `accepted_name` → `names`.
4. When multiple candidates share the top precedence, `preferred=true`
   wins. If a tie remains, all candidates at the top tier are returned as
   `Ambiguous`.
5. If `language` is provided and at least one candidate carries that tag,
   the candidate set is narrowed to those entries **before** step 3. When
   no entry matches, the full set is used (soft preference — a
   scientific-name query with `language="id"` still resolves via
   `scientific_name`).

### Worked examples

| # | Query | Result | Test |
|---|---|---|---|
| 1 | Exact scientific name | `TaxonOk`, `matched_via="scientific_name"` | `tests/contract/test_resolve_taxon.py::test_taxon_ok_exact_scientific_name` |
| 2 | Exact `accepted_name` (differs from scientific) | `TaxonOk`, `matched_via="accepted_name"` | `tests/contract/test_resolve_taxon.py::test_taxon_ok_exact_accepted_name` |
| 3 | Alias from `names.csv` | `TaxonOk`, `matched_via="names"` | `tests/contract/test_resolve_taxon.py::test_taxon_ok_exact_name_from_names_csv` |
| 4 | Different case (`TomatO` vs `tomato`) | `TaxonOk` (case-insensitive) | `tests/contract/test_resolve_taxon.py::test_taxon_ok_case_insensitive` |
| 5 | Two taxa sharing one name | `Ambiguous`, 2 candidates, sorted by `taxon_id` | `tests/contract/test_resolve_taxon.py::test_taxon_ambiguous_two_taxa` |
| 6 | 25 taxa sharing one name | `Ambiguous`, 20 candidates, `truncated=True` | `tests/contract/test_resolve_taxon.py::test_taxon_ambiguous_truncated_at_20` |
| 7 | `language="id"` prefers the Indonesian alias | `TaxonOk` to the Indonesian taxon | `tests/contract/test_resolve_taxon.py::test_taxon_ok_language_prefers_id` |
| 8 | `language="id"` when no candidate has that tag | Falls back to the full set | `tests/contract/test_resolve_taxon.py::test_taxon_ok_language_fallback_when_no_match` |

## `resolve_fact`

### Return union

`resolve_fact` returns a `FactOutcome`, one of:

- **`FactResolved`**: `fact` (the winning `FactRow`), `value`,
  `value_pretty`, `alternatives` (other non-superseded matches),
  `provenance`, `warnings`.
- **`Unknown`**: `reason` and optional `code`.
- **`NotApplicable`**: the parameter does not apply to this taxon
  (`applies_to` mismatch).
- **`InsufficientInput`**: required input missing (for example a
  biological phase on a phased parameter).

### Filters (in order)

1. **Parameter lookup**: the parameter must exist in the dictionary.
   Missing → `Unknown(code="unknown_parameter")`.
2. **`applies_to` match**: `organism_groups`, `archetypes`, `uses`,
   `systems`, `traits`. Mismatch → `NotApplicable`.
3. **Phase validation**: a biological or kc parameter requires a phase in
   `allowed_phases`. Missing → `InsufficientInput`.
4. **Superseded exclusion**: facts with `superseded_by` set are dropped.
5. **Status floor**: facts below the caller's `min_status` are dropped;
   default is `approved`. For safety-critical parameters the floor is
   raised to `reviewed` regardless of caller input, and a
   `safety_min_status_raised` warning is recorded.
6. **Phase match**: fact's phase must equal the requested phase (for
   phase-bearing parameters).
7. **Scope match**: union semantics (see below).
8. **License gate**: sources with `commercial_use="no"` are excluded when
   `require_commercial=True`.

### Scope matching (union semantics)

A fact matches the request when its `scope` keys are a **subset** *or* a
**superset** of the request keys; partial overlap is rejected. Per-key
comparison on the intersection:

- **range** values: fact covers the request.
- **enum_set** and multi-valued string scopes: set equality.
- **scalar** and single-enum scopes: exact equality.
- **empty key**: wildcard on both sides.

The intersection rule makes `{system="field"}` match `{}` (subset) and
`{system="field", variety="roma"}` match `{system="field"}` (superset).
But `{system="field"}` does not match `{region="ID"}` (partial overlap —
different keys).

### Tie-break

Among matching facts, the winner is:

1. The **most specific** candidate (largest `len(scope)`).
2. Then **highest status** (`approved` > `reviewed` > `draft` > `imported`).
3. Then **most recent review date**.
4. Then **smallest `fact_id`**.

If two or more facts tie at (1) with different values, a `fact_conflict`
warning is recorded and the alternatives are returned. A missing match
gives `Unknown(code="no_match")`; the engine never borrows a value from
another taxon or region.

### Worked examples

| # | Situation | Result | Test |
|---|---|---|---|
| 9 | Fact's scope `{system="field"}` matches request scope `{}` | `FactResolved` (subset) | `tests/contract/test_resolve_fact.py::test_scope_fact_subset_of_request` |
| 10 | Safety-critical parameter with `reviewed` status, default `min_status` | `FactResolved` + `safety_min_status_raised` warning | `tests/contract/test_resolve_fact.py::test_safety_floor_raised` |
| 11 | Two facts with different values at the same specificity | `FactResolved` + `fact_conflict` warning, alternatives listed | `tests/contract/test_resolve_fact.py::test_fact_conflict_warning` |
| 12 | `require_commercial=True` and source is `commercial_use="no"` | `Unknown(code="license_excluded")` | `tests/contract/test_resolve_fact.py::test_license_gate_excludes_nc` |

## Error codes

`Unknown.code` values are tracked in `schema/unknown_code_registry.json`.
Active codes at v0.1.0:

- `no_match` — no fact covers the requested scope
- `empty_input` — the query was empty
- `license_excluded` — the only match was excluded by the license gate
- `unknown_parameter` — the parameter is not in the dictionary

Drift is caught by `tests/contract/test_unknown_code_registry.py`.

## See also

- [`decisions/ADR-004-resolution-policy.md`](decisions/ADR-004-resolution-policy.md) — rationale and trade-offs
- [`DICTIONARY.md`](DICTIONARY.md) — parameters, phases, safety classes
- [`SAFETY.md`](SAFETY.md) — status floors and safety-critical behavior
