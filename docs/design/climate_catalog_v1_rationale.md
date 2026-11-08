# Climate parameter catalog — rationale (v1)

<!-- Companion to `climate_catalog_v1.csv`. Prose is hand-written; the CSV is the source of truth. -->

## Purpose

Every climate parameter the engine computes, expects as input, or reads from a pack appears in exactly one catalog. The catalog is a gate: a parameter enters it (with its license status and safety tier) **before** any code is written for it. The gate runs on the catalog, so a parameter that fails the license or safety rules never reaches the engine.

This is the M10 deliverable. It ships before M11 (atmosphere, radiation and ET0) and M12 (thermal time and climate indices), which are the first milestones that use it.

## Three kinds

| Kind | Meaning | Example |
|---|---|---|
| `computed` | The engine implements the method. A `method_ref` names the primary literature; a `test_id` (once `implemented`) names the test that validates it. | `compute_vpd`, `compute_gdd` |
| `input` | The caller supplies the value. The engine checks type and unit and applies its range. | `input_air_temp_c`, `input_rh_pct` |
| `pack_value` | A crop- or region-specific number (a base temperature, a threshold, a stage length) that lives in an `agri-knowledge` pack. The `param_id` is the dictionary key that carries the value. | `gdd_base`, `gdd_upper` |

## Four statuses

| Status | Meaning |
|---|---|
| `planned` | In the roadmap, not yet implemented. `method_ref` and `test_id` may be `TBD` or empty for `computed` rows until `implemented`. |
| `implemented` | Code and a test exist. For `computed` rows, `method_ref` and `test_id` are required (enforced by `lint-catalog`). |
| `backlog` | Considered, not scheduled. A `reason` records why. |
| `excluded` | Will not be added. A `reason` records why. |

The gate is status-aware: `computed` rows are only required to have a real `method_ref` and `test_id` once they are `implemented`. This lets the catalog grow before the code does, without letting an implemented parameter ship untested.

## Two safety tiers

| Tier | Meaning | Constraint |
|---|---|---|
| `low` | Ordinary climatic variables. | None beyond the license gate. |
| `high` | Anything with material safety or legal risk (UV-C dosing, lamp recipes, pesticide doses). | **Must** be `excluded`. `lint-catalog` fails otherwise. |

## License gate

Every non-`excluded` row must have `commercial_use = yes`. Excluded rows are records of a decision, not sources, and are not subject to this check. No input may come from a source whose license forbids commercial use (see ADR-005). The `checked_on` column records when the license was last read; a warning fires at 365 days.

## Excluded by design (M10)

The M10 excluded rows record decisions already made elsewhere:

- `exclude_uv_c_dosing`, `exclude_uv_ab_dosing`, `exclude_lamp_spectrum_recipe`: UV dosing and lamp/spectrum recipes are out of scope for safety reasons (README "Not a UV or lamp-design tool").
- `exclude_pesticide_dose`, `exclude_herbicide_dose`, `exclude_fungicide_dose`, `exclude_insecticide_dose`: pesticide doses are out of scope (ADR-007); they return `refer_to_label` or `refer_to_authority`.
- `exclude_postharvest_chemical`: post-harvest chemical treatment is out of scope (ADR-007).

## Sources cited

Every `computed` row cites primary literature (a paper that defines the method), not handbook tables or worked examples. Where the catalog cites Allen 1996, it cites the primary methodology paper; no FAO-56 tables are reproduced (ADR-005). `method_ref` values are bibliographic, not URLs.

## Maintenance

- `param_id` is stable and never reused.
- `checked_on` is refreshed at least every 12 months and on every PR that touches the catalog.
- Three-way drift tests enforce that the CSV, the generated `docs/CLIMATE_CATALOG.md`, and the in-code list of excluded parameters stay in sync.
- A `pack_value` row's `param_id` must match a key in `dictionary/parameters.core.yaml`. Adding the key is a dictionary change (engine minor release); supplying the value is a data change in `agri-knowledge`.

## Link to `agri-knowledge`

The catalog names the dictionary key for every `pack_value`. Adding that key is a dictionary change here; supplying values is a data change there. A new pack-supplied parameter starts with `tier_required: false`, so existing tiers do not drop; making it required later changes derived tiers and needs a coordinated release of both repositories. Without a pack value the answer is `unknown` or `insufficient_input`; the engine never falls back to a built-in number.

## See also

- `docs/decisions/ADR-012-climate-catalog.md` — the decision record.
- `docs/CLIMATE_CATALOG.md` — generated from the CSV.
- `docs/decisions/ADR-005-license-allowlist.md` — the license gate.
- `docs/decisions/ADR-007-plant-protection-scope.md` — the plant-protection guard.
