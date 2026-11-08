# ADR-012: Climate parameter catalog and contract

## Status

Accepted 2026-11-09. Implemented in milestone M10.

## Context

M11 (atmosphere, radiation and ET0) and M12 (thermal time and climate indices) are the first milestones that compute climate quantities. They share three traits that need a contract before any code ships:

1. **Mixed sources.** Some parameters are computed by the engine, some are supplied by the caller, and some are crop- or region-specific values that belong in a pack. Without a contract, it is easy to duplicate a value that should live in `agri-knowledge`, or to compute one that should be an input.
2. **Mixed safety profiles.** Some are ordinary climatic variables; others carry material safety or legal risk (UV-C dosing, lamp recipes, pesticide doses). A parameter that fails a safety check must be rejected before it reaches the engine.
3. **Mixed license status.** Some parameters can be computed from primary literature; others would need data from a source that does not permit commercial use. The license gate must run on the catalog, not on the code.

Without a catalog and a gate, a future contributor could add a UV-C dosing parameter, or a `computed` VPD whose method cites a handbook table, with no mechanical way to catch the error.

## Decision

1. **One catalog.** Every climate parameter the engine computes, expects as input, or reads from a pack appears as exactly one row in `docs/design/climate_catalog_v1.csv`. Its columns are `param_id`, `group`, `kind`, `unit`, `method_ref`, `owner_repo`, `commercial_use`, `safety_tier`, `status`, `milestone`, `test_id`, `checked_on`, `reason`.

2. **Three kinds.** `computed` (the engine implements the method; a `method_ref` names the primary literature), `input` (the caller supplies the value; the engine checks type and unit), `pack_value` (the value lives in an `agri-knowledge` pack; `param_id` is the dictionary key that carries it).

3. **Four statuses.** `planned` (in the roadmap, not implemented), `implemented` (code and test exist), `backlog` (considered, not scheduled), `excluded` (will not be added). `excluded` and `backlog` rows must record a `reason`.

4. **Two safety tiers.** `low` (ordinary) and `high` (material safety or legal risk). A row with `safety_tier = high` **must** be `excluded`; `lint-catalog` fails otherwise. This is the mechanical form of the "safety and legal risk" rule in the handoff.

5. **License gate.** Every non-`excluded` row must have `commercial_use = yes`. This is the same default-deny rule as ADR-005, applied to the catalog. A `checked_on` value older than 365 days produces a warning, not a failure, because terms change.

6. **Status-aware test gate.** `lint-catalog` requires a real `method_ref` and `test_id` for `computed` rows **only when `status = implemented`**. `planned` rows may carry `TBD` or be empty. This lets the catalog grow before the code does, without letting an implemented parameter ship untested.

7. **Generated document.** `docs/CLIMATE_CATALOG.md` is generated from the CSV by `scripts/gen_climate_catalog_doc.py`, which runs in CI with `--check` (as `gen_dictionary_doc.py` does for `docs/DICTIONARY.md`). A stale generated document fails CI. No one edits `docs/CLIMATE_CATALOG.md` by hand.

8. **Shipped excluded list.** The list of `excluded` rows is generated into `src/agri_core/catalog/_excluded_generated.py` and shipped with the package. `validate` uses it to reject extension parameters in a pack that match an excluded `param_id`. This mirrors the ADR-007 pattern (`check_protection_out_of_scope`, `check_hazard_code_out_of_scope`): the guard is a rule in `validate.py` that emits a `PACK_*` finding.

9. **Three-way drift test.** A contract test enforces three-way consistency: catalog CSV ↔ generated `docs/CLIMATE_CATALOG.md` ↔ shipped `_excluded_generated.py`. A drift in any direction fails CI.

10. **`param_id` is stable.** Never reused. A `pack_value` row's `param_id` must match a key in `dictionary/parameters.core.yaml`; adding the key is a dictionary change (engine minor release), supplying the value is a data change in `agri-knowledge`.

## Alternatives considered

- **No catalog; add parameters as code lands.** Rejected: it defers the safety and license checks until the code is written, which is too late. The catalog-first rule is what lets the checks run before code.
- **Catalog only; no generated document or shipped excluded list.** Rejected: the generated document keeps the human-readable view in sync, and the shipped excluded list lets `validate` reject an excluded extension parameter at the CLI, not only in CI.
- **Computed rows require `method_ref` and `test_id` at every status.** Rejected: it makes M10 unmergeable, because the catalog M10 ships is mostly `planned`. The status-aware rule is what the milestone needs.
- **Safety tier as a free-text field.** Rejected: a closed set of two values (`low`, `high`) is enforceable; a free-text field is not.
- **Store the excluded list as a CSV inside the package.** Considered; rejected because a Python module is simpler to import and to test, and the file is small.

## Consequences

- **Positive.** A UV-C or pesticide-dose parameter cannot enter the catalog undetected. A `computed` parameter cannot ship without a test once it is `implemented`. A `pack_value` parameter cannot drift from its dictionary key. An extension parameter in a pack that matches an excluded row is rejected at `validate` time.
- **Positive.** The generated document and the shipped excluded list are always current; the three-way test fails when either is stale.
- **Positive.** The catalog-first rule makes M11 and M12 additive: each milestone adds rows to the catalog and code alongside them, in the same shape.
- **Negative.** Adding a new `computed` parameter touches the catalog, the generator, and the test list. The catalog is a coordination point, not just documentation.
- **Negative.** A `planned` row with a stale `checked_on` will warn at 365 days. This is a feature, not a bug; it forces a periodic re-read of the license.

## Enforcement

| Item | Mechanism | When |
|---|---|---|
| 1. One catalog per parameter | Three-way drift test | M10 |
| 2. Three kinds | `lint-catalog` schema check | M10 |
| 3. Four statuses | `lint-catalog` schema check | M10 |
| 4. Safety tiers: `high` must be `excluded` | `lint-catalog` | M10 |
| 5. License gate: `commercial_use = yes` for non-excluded | `lint-catalog` | M10 |
| 6. Status-aware `method_ref` + `test_id` | `lint-catalog` | M10 |
| 7. Generated document in sync | `gen_climate_catalog_doc.py --check` in CI | M10 |
| 8. Shipped excluded list in sync | `_excluded_generated.py` drift test | M10 |
| 9. `pack_value` param_id matches dictionary key | `lint-catalog` | M10 |
| 10. `param_id` never reused | `lint-catalog` (uniqueness) | M10 |
| 11. Extension parameter matching excluded row rejected | `validate` rule + test | M10 |
| 12. `checked_on` > 365 days | `lint-catalog` warning | M10 |

## Revisit when

- A third `kind` or a fifth `status` is needed. Today the sets are closed.
- A new category of safety risk emerges that does not fit `low`/`high` (today the two-tier model is sufficient).
- The excluded list grows large enough that a CSV is preferable to a Python module.
- The catalog starts to be read by `agri-knowledge` (to validate a pack_value row before it is written), which would make it a shared contract rather than an engine-local one.

## References

- `docs/design/climate_catalog_v1.csv` — the catalog.
- `docs/design/climate_catalog_v1_rationale.md` — the rationale.
- `docs/CLIMATE_CATALOG.md` — the generated document.
- `docs/decisions/ADR-005-license-allowlist.md` — the license gate.
- `docs/decisions/ADR-007-plant-protection-scope.md` — the pattern the `validate` rule mirrors.
- `dictionary/parameters.core.yaml` — the dictionary keys that `pack_value` rows reference.
- `scripts/gen_dictionary_doc.py` — the generator pattern this ADR follows.
- README — the milestone table (M10).
