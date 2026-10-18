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

- Python requirement raised to 3.11 or newer.
- Public output contract clarified as an `Outcome` discriminated union; `result.schema.json` renamed to `outcome.schema.json`.

## [0.0.0] - 2026-10-17

- Repository created.
