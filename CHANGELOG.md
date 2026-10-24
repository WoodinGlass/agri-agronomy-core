# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- Added `enum_set` shape to the fact value union (8th shape). Needed by
  `must_flood_phases` in c-2 to avoid FACT_CONFLICT from multiple
  facts with identical scope. This is a change to the W2 shape list.
- `ParameterDef` fields renamed / added: `name` -> `key`,
  `safety_critical` -> `safety_class` (with `safety_critical` derived),
  `physical_range` required for numeric shapes, `applies_to.organism_groups`
  required, `enum_source` added, `scope_keys` added.

## [0.0.0] - 2026-10-17

- Repository created.
