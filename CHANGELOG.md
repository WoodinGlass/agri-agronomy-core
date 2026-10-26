# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


### Added

- `agri-core pack lock --pack PATH` regenerates `content_hash` in
  `pack.toml` atomically. Validates structurally before writing and
  is idempotent; comments and non-fixed key order are not preserved.
  Keyword `sample` is rejected — pass an explicit path.
- Sample pack now ships 8 synthetic taxa (one per base
  archetype), 19 names (EN/ID/JA, one non-ASCII and one
  comma+quote to exercise CSV quoting), 3 sources, 1 dataset,
  2 hazards, and 20 facts covering 6 of the 8 fact value
  shapes. T000000005 (fungal) has no facts file to exercise
  empty `facts_for` behavior. All three sources S001-S003
  are used across facts and hazards.
### Added

- Dictionary `1.0.0` finalized (c-3b): `dictionary_version: 1.0.0`
  (was `1.0.0-dev`). 31 parameters.
- `dictionary/dictionary.lock` (new) — append-only log of
  `<version> <contract_hash>` per release, sorted by SemVer.
  `contract_hash` = SHA-256 of canonical JSON of
  `{parameters, vocab, units}`; version is checked separately.
- `dictionary/history/1.0.0.json` (new) — frozen snapshot of
  `{version, parameters, vocab, units}`. Older snapshots are never
  edited; a change to `1.0.0` requires a version bump and a new snapshot.
- `classify_change(old_bundle, new_bundle)` (c-3b-1) — fail-closed SemVer
  classifier used by `test_semver_compat` to verify each consecutive
  snapshot pair. With 1.0.0 as the only snapshot the test currently has
  no pairs and skips; the machinery is ready for 1.0.1 / 1.1.0.
- Wheel allowlist gains `agri_core/_dictionary/dictionary.lock` and
  `agri_core/_dictionary/history/1.0.0.json`.
- 7 parameters in c-3a (fertilizer, `1.0.0-dev` total now 31):
  `n_fertilizer_rate`, `p2o5_fertilizer_rate`, `k2o_fertilizer_rate`,
  `plant_density`, and safety-critical dose caps
  `n_max_per_application`, `p2o5_max_per_application`,
  `k2o_max_per_application`.
- Renamed (pre-release) `n_requirement` -> `n_fertilizer_rate`,
  `p2o5_requirement` -> `p2o5_fertilizer_rate`, `k2o_requirement` ->
  `k2o_fertilizer_rate`. Old names were ambiguous between crop uptake and
  fertilizer recommendation; the fertilizer module reads the recommended
  amount to apply.
- `managed_cycle.used_by` now includes `fertilizer` (rate period depends
  on `single_season` vs `multi_season`).
- Added `dictionary/vocab/safety_classes.yaml` documenting the safety
  class taxonomy (`none`, `dose_cap`, `toxicity_limit`, `regulatory`).
  `dose_cap` is functional (amount constraint); `toxicity_limit` and
  `regulatory` are by hazard type. Salinity (`soil_ec`, `water_ec_max`)
  remains `none` (tolerance condition, not an applied amount).
- New mechanical rule enforced by tests: a parameter whose
  `applies_to.systems` contains more than one value must have `system`
  in `scope_keys`.
- 12 parameters in c-2b: irrigation (`kc`, `kc_stage_length`, `root_depth`, `depletion_fraction`, `awd_reflood_depth`, `ponding_depth`, `percolation_rate`, `predrain_days`, `must_flood_phases`, `moisture_band`) and media/air (`water_ec_max`, `water_temp_max`). `modules.reads` updated for irrigation, media, thresholds.
- Initial repository scaffold: package layout (`src/agri_core`), `py.typed` marker, packaging via hatchling.
- Dual licensing: Apache-2.0 for code, CC BY 4.0 for profiles (`LICENSE`, `LICENSE-DATA`).
- Development tooling: ruff, mypy (strict), pytest, hypothesis, pytest-cov, pre-commit, pip-audit.
- GitHub Actions: CI matrix (Python 3.11–3.14, latest and lowest-direct dependencies), wheel build and clean-venv smoke test, weekly `pip-audit`.
- Dependabot for `pip` and `github-actions`.
- `registry` module with `resolve_data_root()` (source-tree and packaged detection,
  explicit override, no cwd or env-var input) and `DataRoot`.
- `SourceRow` model with SPDX-shaped license vocabulary, token-based NC detection,
  and strict URL/date/citation validation.
- `lint_csv_text()` and `lint_csv_file()` returning stable `SRC###` findings.
- `profiles/sources.csv` (header only) and `schema/source.schema.json`.
- CLI (`agri-core`) with `validate`, `lint-sources`, and `--version`.
  `--data-dir` accepts an explicit data root. Output includes a `data: <kind>` line
  (`override`, `source_tree`, or `packaged`).
  Exit codes: `0` ok, `1` validation error, `2` usage error (Typer), `3` data not found.
- `[project.scripts]` entry point `agri-core = agri_core.cli:app`.
- Wheel `force-include` bundles `profiles/` and `schema/` into `agri_core/_data/`.
- sdist `include` list now ships `profiles/`, `schema/`, and `Makefile` so the wheel
  can be built from the sdist without a source checkout.
- pre-commit local hook `agri-core-validate` runs `agri-core validate --data-dir .`
  when files under `profiles/` or `schema/` change.
- CI job `pre-commit` runs all hooks on all files.

### Changed

- Package license is now `Apache-2.0` only. Previously
  `Apache-2.0 AND CC-BY-4.0`; the CC-BY-4.0 half applied to `profiles/`,
  which no longer exists in this repository.

- `Outcome` union widened: added `ambiguous` (with `candidates`) and
  `refer_to_authority` (with `reason` and `flags`). Contract change for
  consumers that exhaustively handle every status.

- Python requirement raised to 3.11 or newer.
- Public output contract clarified as an `Outcome` discriminated union; `result.schema.json` renamed to `outcome.schema.json`.

### Removed

- `resolve_data_root()` and its tests. Replaced by explicit pack loading
  (`load_pack`, `load_sample_pack`). No released API depended on it.
- CLI option `--data-dir` (both `validate` and `lint-sources`). Use `--pack`.

### Deprecated

- `profiles/` and `LICENSE-DATA` are no longer read by the CLI. They stay in
  the repository for now and will move to the `agri-knowledge` repo (M1-0).

### Changed (dictionary 1.0.0-dev, pre-release)

- `enum_set` added to `ParameterShape` in c-1 and `EnumSetValue` added to
  the `FactValue` union in c-2a. Needed by `must_flood_phases` (c-2b) to
  avoid FACT_CONFLICT from multiple facts with identical scope. This is a
  change to the W2 shape list.
- `ParameterDef` fields renamed / added: `name` -> `key`,
  `safety_critical` -> `safety_class` (with `safety_critical` derived),
  `physical_range` required for numeric shapes, `applies_to.organism_groups`
  required, `enum_source` added, `scope_keys` added.

### Removed

- `Pack`, `PackKind`, `load_pack()`, and `load_sample_pack()` are removed
  from `agri_core.pack`. Use `load_knowledge_set(path)` for a full pack
  load, or `load_knowledge_set_from_files(files)` when the caller already
  has the allowlist bytes (for example from `read_pack_bytes`). Pre-1.0;
  no released API depended on the removed names.

## [0.0.0] - 2026-10-17

- Repository created.
