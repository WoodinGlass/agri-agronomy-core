# ADR-013: Thermal time, generic climate index engine, and bioclimatic variables

## Status

Accepted 2026-11-09. Implemented in milestone M12.

## Context

M12 adds three groups of calculations that did not exist before:

1. **Thermal time.** GDD (two documented methods), chilling accumulation
   (chill hours, Utah chill units), and photothermal units. These are
   time-series calculations over daily or hourly inputs; a gap in the
   series must not be silently filled.
2. **A generic climate index engine.** The milestone asks for "one
   generic index engine (threshold, window, aggregation) driven by a
   documented registry". The engine accepts a daily series plus an index
   name; the index's threshold, operator, aggregation, and window come
   from a registry.
3. **Bioclimatic variables.** A subset of the Nix 1986 BIO01–BIO19
   variables, computed from 12 monthly values.

Each of these exposes design questions the code needs answered before
implementation.

## Decision

### Thermal time (M12b)

- **GDD methods 1 and 2** (McMaster & Wilhelm 1997) are separate
  functions (`gdd_method_1`, `gdd_method_2`) rather than one function
  with a `method` parameter. Callers see the method name at the call
  site; a result cannot silently change method. Both accept an optional
  `tupper_c` upper cutoff (method 1 caps the daily mean; method 2 caps
  Tmax after flooring Tmin at Tbase).
- **Series input.** `gdd_series` accepts `dates: Sequence[date]` plus
  parallel `temp_max_c` / `temp_min_c`. Dates must be strictly
  consecutive; any gap returns `insufficient_input` with the gap
  description in `missing`. Nothing is interpolated.
- **Chilling is hourly only.** `chill_hours` (Weinberger 1950) and
  `utah_chill_units` (Richardson et al. 1974) require consecutive
  hourly timestamps. Daily data is not sufficient; the engine refuses
  rather than interpolate. The `agri-knowledge` pack will need hourly
  series to populate these facts; that is a data problem, not an engine
  problem.
- **Dynamic Model (chill portions) is backlog.** The Fishman et al.
  1987a/b two-pool state equations involve parameters that must be
  verified against the original paper before shipping. A simplified
  implementation would mislead breeding decisions; the catalog row
  `compute_chill_portions` sits in `backlog` until paper access is
  available. See ADR-012 §Enforcement.

### Generic index engine (M12c)

- **Registry file.** `dictionary/vocab/climate_indices.yaml` ships 13
  indices: 4 day counts (`frost_days`, `heat_days`, `dry_days`,
  `wet_days`), 4 spells (`frost_spell_max`, `heat_spell_max`,
  `dry_spell_max`, `wet_spell_max`), 2 rolling sums
  (`rolling_sum_7d_max`, `rolling_sum_30d_max`), and 3 aggregates
  (`precip_total`, `temp_min`, `temp_max`). Each entry names unit,
  operator, threshold, aggregation, and window_days.
- **Engine.** `threshold_index(*, index_name, dates, values,
  threshold_override=None)` reads the registry (packaged path with
  source-tree fallback), validates consecutive dates, and applies the
  recipe. `threshold_override` replaces the registry threshold (for a
  crop-specific frost tolerance, for example) and emits an assumption
  `threshold_override_applied`.
- **Gap refusal.** A gap in `dates` returns `insufficient_input` with
  the gap description; no value is filled.
- **Unit output.** `count` and `max_run` return days; `sum`, `min`,
  `max`, and `max_rolling_sum` return the registry unit.
- **Registry is a closed set.** Adding an index is a `dictionary_version`
  minor bump (`1.0.0` → `1.1.0` in this release); the YAML file is the
  single source.

### Bioclimatic variables (M12c)

- **Separate functions.** `bio_01`, `bio_06`, `bio_07`, `bio_12`,
  `bio_13`, `bio_14`, `bio_15` are seven public functions, not a single
  wrapper returning a dict. This matches the catalog one-row-per-parameter
  structure and keeps each function independently testable.
- **Nix 1986 subset.** The seven shipped variables cover annual mean
  temperature, coldest-month minimum, annual range, annual
  precipitation, wettest and driest months, and precipitation
  seasonality (CV %). `bio_15` uses sample standard deviation
  (`ddof=1`); a zero precipitation mean returns `not_applicable` (CV is
  undefined).
- **Full BIO01–BIO19 is backlog.** The remaining 12 variables
  (`bio_02`–`bio_05`, `bio_08`–`bio_11`, `bio_16`–`bio_19`) will land in
  a later release.

### Known limitations (recorded here, to be fixed later)

- **`classify_change` treats a new vocab file as `PATCH`, not `MINOR`.**
  Semantically, adding `climate_indices.yaml` is a new dimension
  (MINOR). `classify_change` scans values within existing vocab files,
  not new files. `test_semver_compat` uses `rank[declared] >=
  rank[required]`, so declaring `1.1.0` satisfies it — but the
  classification itself is wrong. Fixing it is a breaking change to
  `classify_change`; scheduled for M12.1 / M13.
- **`millimeter` was missing from `CANONICAL_UNITS`.** The bio_12,
  bio_13, and bio_14 functions need a `millimeter` unit, and the catalog
  had already used it in M12a. Adding it is a `MINOR` change to
  `units.py` (`CANONICAL_UNITS` grows). This is a pre-existing
  vocabulary gap surfaced by M12c.
- **Registry entries have no `method_ref` field in the YAML.** The
  milestone criterion "every registry entry has a reference and a test"
  is satisfied at the **catalog level**: each of the 11 flipped catalog
  rows carries `method_ref` (McMaster & Wilhelm 1997, Weinberger 1950,
  Richardson et al. 1974, Nix 1986) plus a `test_id`. The YAML registry
  itself carries only `description`. Adding a `reference` field per
  entry would be a new `dictionary_version` bump; deferred.

## Consequences

- **Positive.** The 13-index registry is one YAML file; a new index is a
  data change (dictionary minor) without touching code. The engine
  refuses gaps rather than interpolating. Thermal time, chilling, and
  bioclim variables are composable across releases.
- **Positive.** `test_semver_compat` now runs (it had one snapshot before
  M12); with two snapshots, the compatibility check is active.
- **Negative.** Dynamic Model (chill portions) is deferred; callers who
  need it must wait for a later release.
- **Negative.** The `classify_change` limitation means future vocab-file
  additions will require manual version bumps and an ADR note until the
  classifier is fixed.

## References

- McMaster, G. S., & Wilhelm, W. W. (1997). Growing degree-days: one
  equation, two interpretations. *Agricultural and Forest Meteorology*,
  87(4), 291–300.
- Weinberger, J. H. (1950). Chilling requirements of peach varieties.
  *Proceedings of the American Society for Horticultural Science*, 56,
  122–128.
- Richardson, E. A., Seeley, S. D., & Walker, D. R. (1974). A model for
  estimating the completion of rest for "Redhaven" and "Elberta" peach
  trees. *HortScience*, 9(4), 331–332.
- Nix, H. A. (1986). A biogeographic analysis of Australian elapid
  snakes. In R. Longley (Ed.), *Atlas of Australian Elapid Snakes*
  (pp. 4–15). Australian Government Publishing Service.
- Fishman, S., Erez, A., & Couvillon, G. A. (1987a, 1987b). The
  temperature dependence of dormancy breaking in plants: computer
  simulation of processes studied under controlled temperatures; and
  mathematical analysis of a two-step model involving a cooperative
  transition. *Journal of Theoretical Biology* (two papers). Deferred to
  a later release: parameters need paper verification.

## See also

- ADR-012 — Climate parameter catalog and contract (the excluded list
  and `lint-catalog` gate).
- ADR-004 §G3 — Advisory contract (not used by M12).
- `dictionary/vocab/climate_indices.yaml` — the 13-index registry.
- `docs/CLIMATE_CATALOG.md` — generated catalog view.
