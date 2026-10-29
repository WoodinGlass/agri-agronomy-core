# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

## [0.1.1] - 2026-10-29

### Fixed

- `agri-core pack lock` now repairs a stale or missing `content_hash`
  instead of rejecting it with `PACK_HASH_MISMATCH`. Structural
  validation still runs; only the hash-consistency check is dropped
  before rewriting, matching `agri-core pack build --update-source-hash`.

## [0.1.0] - 2026-10-29

Foundation release. **Data contract, pack lifecycle, and deterministic
resolution.** The calculation engine (VPD, GDD, ET0, irrigation,
fertilizer, media, suitability, propagation) ships in v0.2+; at v0.1.0
the library loads a verified knowledge pack, resolves a taxon name and
a fact deterministically, and refuses to guess.

### Highlights

- Offline by construction: `--disable-socket` and a `unshare -n` CI
  job. The full test suite runs with the network blocked.
- Deterministic fact resolution (`resolve_taxon`, `resolve_fact`)
  following a fixed policy, with 12 worked examples, each backed by a
  test in the repository.
- 10k-taxa built-pack load: min-of-5 895.6 ms, peak `tracemalloc`
  61.7 MB (measured on Colab-class CPU). A Windows smoke job runs the
  full suite on `windows-latest`.

### Added (M9)

- **Offline guard.** `pytest-socket` with `--disable-socket` in
  `addopts`. `tests/offline/test_socket_guard.py` is the permanent
  negative control; the `offline-wheel` CI job runs `agri-core validate`
  under `unshare -n`. The full suite passes with no network access.
- **Performance budget tests.** Synthetic 10k-taxa pack (30k names,
  200k facts): built-pack load min-of-5 <= 1 s (measured 895.6 ms),
  peak `tracemalloc` <= 200 MB (measured 61.7 MB); source-pack canary
  <= 40 s (measured 25.6 s). New `perf` CI job runs with `--no-cov` so
  timing is not distorted by coverage instrumentation.
- **Built-pack load fast path.** `_read_raw_rows_for_index` passes every
  defaulted field explicitly to `model_construct`, sidestepping
  Pydantic 2.14's per-call `default_factory` resolution. Measured
  2726 ms -> 917 ms (3.0x). The SQLite artifact is hashed in 1 MiB
  chunks instead of `read_bytes()`: identical digest, safe for larger
  packs.
- **Docs skeleton, anti-drift.** `docs/DICTIONARY.md` is generated from
  `dictionary/parameters.core.yaml` by `scripts/gen_dictionary_doc.py`
  with a `--check` pre-commit hook. `docs/RESOLUTION_POLICY.md` is the
  normative spec with 12 worked examples, each naming the enforcing
  test. `docs/SAFETY.md` separates enforced-now from planned-M11+ and
  names the test for each claim. `docs/ADDING_A_TAXON.md` is executed
  end-to-end by `tests/scenario/test_adding_a_taxon.py` via
  `CliRunner`. `tests/unit/test_docs_links.py` verifies every relative
  link and README anchor.
- **Windows CI.** New `windows-smoke` job (`windows-latest`,
  Python 3.11) runs the full non-perf suite, `agri-core validate`, and
  a cross-OS `pack lock` + `git diff` determinism check.
  `_sqlite_uri` emits `file:///C:/...` for drive-letter paths so the
  SQLite artifact opens on Windows; three POSIX-only tests are skipped
  on `os.name == "nt"`.
- **Release workflow.** `release.yml` calls `ci.yml` via `workflow_call`
  as the release gate (no duplicated checks). `workflow_dispatch`
  provides a dry-run; the tag-triggered path creates a draft GitHub
  Release with wheel, sdist, `sample_pack.zip`, `SHA256SUMS`, and the
  `agri-knowledge` built pack when a matching release exists.
- **Dependency pin.** `tornado>=6.6` pinned in dev extras to close
  CVE-2026-116577 / -115927 / -116578 (transitive via nbmake).

### Added (M0-M8, pre-release development)

- `agri-core pack build --pack PATH --out DIR` validates a source pack
  and writes `pack.sqlite` plus a built `pack.toml`. Prints
  `content_hash` and `artifact_sha256` for the resulting artifact.
  Refuses to run if DIR already contains `pack.sqlite` or `pack.toml`,
  or if it looks like a source pack (contains `taxa.csv`).
  `--update-source-hash` rewrites a stale or non-canonical source
  `pack.toml` before building; without the flag a stale hash is
  reported as `PACK_HASH_MISMATCH`. Keyword `sample` is rejected —
  pass an explicit path.
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
- `docs/PACK_FORMAT.md` -- pack format reference: allowlist,
  `pack.toml` fields, content-hash algorithm, load order, CSV codec,
  table schemas, error codes, size limits, synthetic packs.
- `docs/decisions/ADR-001-knowledge-set.md` -- why `KnowledgeSet` is
  a Protocol and not a base class, and how M6's SQLite backend will
  implement it.
- README `Pack format` section now points at `docs/PACK_FORMAT.md`;
  M5 milestone marked Done.
- `pack/sqlite_schema.py`: deterministic SQLite build from pack CSV
  bytes. DDL pinned by `DDL_SHA256`; `WITHOUT ROWID` for all tables
  (benchmarked within 10% of rowid on the hottest query at 100k
  facts); indexes created after bulk insert; `VACUUM INTO` via
  `TemporaryDirectory`; `application_id=0x61677269` ("agri"),
  `user_version=1`; sqlite >= 3.27 required for `VACUUM INTO`.
- `pack/toml_writer.py`: deterministic TOML serializer for built
  manifests, iterating `PackManifest.model_fields`.
- `PackManifest` gains `artifact_sha256`, `sqlite_schema_version`,
  `built_by` (all-or-none; source manifests must not declare them).
- ADR-002: two-hash model (`content_hash` semantic,
  `artifact_sha256` file integrity), DDL pinning, `WITHOUT ROWID`
  benchmark, cross-version SQLite caveat.
- `SQLiteKnowledgeSet` in `pack/knowledge_set.py`: read-only SQLite
  backend implementing the `KnowledgeSet` Protocol. Per-call
  connection in `mode=ro&immutable=1` with `query_only=ON` and
  `trusted_schema=OFF`; no cache; thread-safe by construction. Rows
  are `model_validate`'d on read; the writer's encoding (pipe-joined
  lists, canonical JSON for value/scope, ISO dates) is decoded by
  `_row_to_dict`.
- `load_knowledge_set` now detects the pack kind from directory
  contents: `pack.sqlite` + `pack.toml` selects the SQLite backend;
  `taxa.csv` + `pack.toml` selects the CSV backend. Both or neither
  raises `InvalidPackError`. On a built pack, `expected_hash`
  compares against `artifact_sha256` (the file hash); `pack_hash`
  on the returned `KnowledgeSet` remains `content_hash` on both
  backends for provenance consistency.
- Built-pack load verification is 3 layers: `artifact_sha256` vs
  sha256(`pack.sqlite`), `content_hash` vs `metadata.content_hash`,
  and `PRAGMA user_version` vs `manifest.sqlite_schema_version`
  plus 8 metadata rows vs `pack.toml` fields.
- Wheel builds are verified to be reproducible in CI: the
  `build-wheel` job builds the wheel a second time (into `dist2/`)
  with `SOURCE_DATE_EPOCH=0`, compares `sha256sum` of both wheels,
  and fails the job on mismatch. The second wheel is uploaded as
  artifact `wheel-mismatch` on reproducibility failure for post-mortem.
- `docs/PACK_FORMAT.md` gains a `Built packs (SQLite)` section:
  on-disk layout, SQLite schema (6 data tables + `metadata`, all
  `WITHOUT ROWID`, `application_id=0x61677269`, `user_version=1`,
  `DDL_SHA256` pin, SQLite >= 3.27 for `VACUUM INTO`), the three
  build-only manifest fields, the two-hash model (`content_hash`
  semantic vs `artifact_sha256` file integrity), three-layer load
  verification, and row encoding. Cross-links `ADR-002`.
- `ValidationReport` and `Finding` data models (`agri_core.models.finding`)
  with stable code pattern, severity, optional `FindingLocation`, and
  `REPORT_VERSION` wire version. `validate_pack_report(files)` in
  `pack/validate.py` is the single validation pipeline (load + rules);
  returns `(report, knowledge_set | None)`. `validate_pack` (M6-4) is
  preserved as a wrapper with identical load-error behavior and a new
  rule-error path. `RULES` is an explicit tuple, empty in M7-1;
  M7-2..M7-4 append. `schema/finding.schema.json` and
  `schema/validation_report.schema.json` generated by
  `scripts/gen_schemas.py`, with drift tests. `docs/decisions/ADR-003`
  records the M7 decisions on tiers, license gate, duplicates, and
  exit codes.
- `agri-core diff --old A --new B [--json] [--exit-code]` compares two
  source or built packs. Enforces M6 identity invariants: fact and
  taxon IDs are never removed or reused for different content. Exits 1
  on any violation by default; `--exit-code` also promotes normal
  differences to exit 1 for CI. `DiffReport` is JSON-safe and
  deterministic; fact changes are classified per field (violation vs
  acceptable). 16 new contract tests.
- `PACK_TRAPEZOID_DEGENERATE` validation rule: trapezoid facts must
  have `pts[0] < pts[-1]`. The model already enforces
  `a <= b <= c <= d`; this rule additionally rejects collapsed
  trapezoids where all four points are equal. Range `min <= max` is
  already enforced at load and gets no separate rule. 5 new contract
  tests.
- Three new validation rules: `PACK_SUPERSEDED_SELF` (fact
  supersedes itself), `PACK_SUPERSEDED_CYCLE` (cycle in
  `superseded_by` chain, one finding per cycle anchored at the
  smallest `fact_id`), and `PACK_FACT_KEY_DUPLICATE` (two live
  facts with the same `(taxon, parameter, phase,
  canonical_scope)` and different values). Same key with same
  value across different `src` is corroboration, not a duplicate.
  Superseded facts are excluded from the duplicate check. FK for
  `superseded_by` remains `PACK_FK_VIOLATION` at load time. 8 new
  contract tests.
- `tests/contract/test_finding_registry.py`: registry-vs-docs
  drift test. Every `PackError` subclass code and every `Finding`
  code emitted by a rule in `pack/validate.py` must appear in
  `PACK_FORMAT.md §Error code reference`; every code in the docs
  (except `PACK_ERROR`, the base class) must have an
  implementation. New codes cannot land without a doc line, and
  doc lines cannot be added without an implementation. 4 new
  contract tests.
- Two new validation rules for license compliance:
  `PACK_LICENSE_NC_COMMERCIAL` (non-commercial source with
  `commercial_use=yes`) and `PACK_LICENSE_DATASET_SA_ND` (SA/ND
  dataset referenced by any fact). `is_sa_license` and
  `is_nd_license` helpers added to `registry.sources` alongside
  `is_nc_license`. These rules run in `validate_pack_report` and
  therefore in `agri-core validate`, `agri-core pack build`, and
  `agri-core coverage`. 10 new tests (8 contract, 2 parametrized
  unit).
- `tests/contract/test_finding_registry.py` gains
  `test_each_rule_code_has_contract_fixture`: every rule-specific
  `Finding` code (a code emitted by a `Finding(code=...)` in
  `pack/validate.py` that is not a `PackError` subclass) must
  appear in at least one `tests/contract/*.py` file other than the
  registry meta-test. A rule without a fixture is untested dead
  code, so this makes "add a rule, add a fixture" a mechanical
  requirement.
- Tier derivation for taxa: `pack/tiers.py` exposes `Tier` (T0–T3),
  `TierResult` (tier + required/missing params + `system_gaps` +
  detail), `derive_tier`, and `derive_all_tiers`. Tiers are
  derived from fact coverage: T0 = no live facts, T1 = >=1 fact
  (any status), T2 = all `tier_required=True` params >= `reviewed`
  (weak-link, phase coverage required), T3 = T2 + all such params
  `approved` + every safety-critical fact `approved` with >=2
  distinct reviewers. Parameters with `applies_to.systems` never
  gate tier; they appear in `system_gaps` for `coverage` (M7-7)
  to display. See ADR-003.
- `FactRow.reviewed_by` is now `list[str] | None` (was
  `str | None`), encoded as `list_str` in CSV. Single reviewer is
  byte-identical to before; two reviewers encoded as `a|b`; model
  canonicalizes to sorted unique. No CSV migration needed. New
  rule `PACK_SAFETY_DOUBLE_REVIEW_MISSING` fires for a
  safety-critical fact that is `approved` with <2 reviewers.
  `RuleFn` signature extended with a `dictionary` argument.
- `agri-core coverage --pack PATH [--tier T0|T1|T2|T3 ...] [--json] [--verbose]`
  reports tier distribution and per-taxon coverage. Uses
  `pack.tiers.derive_all_tiers`; the summary always counts every
  taxon in the pack, while `--tier` (exact, repeatable) filters
  only the detail rows. `--json` emits `{pack, summary, taxa}`
  for programmatic use. Default truncates each list to 3 entries
  plus `(+N more)`; `--verbose` shows full lists. Exit 3 on any
  `PackError`. 12 new unit tests.
- Golden diff fixtures under `tests/golden/diff/<case>/expected.json`.
  Five cases (`identical`, `fact_added`, `fact_value_changed_draft`,
  `fact_value_changed_reviewed`, `taxon_removed`) built from the
  sample pack via `tests/contract/_diff_golden.py` and regenerated
  by `scripts/gen_diff_golden.py`. `test_diff_golden.py` compares
  `DiffReport.model_dump(mode="json")` and enforces idempotent
  regeneration — a `DiffReport` field addition or rename now fails
  CI until the fixtures are regenerated and committed.
- `pack/normalize.py` -- name and scope-value normalization for
  resolution: NFKC, case-fold, whitespace collapse (including NBSP),
  and multiplication-sign `×` folded to ASCII `x` (matching-only).
  `normalize_name` (with hybrid lift) and `normalize_scope_value`
  (without).
- `pack/name_index.py` -- `NameIndexEntry`, `MatchedVia`, and
  `build_name_index()`: name-to-taxon index built eagerly from
  `taxon.csv` + `names.csv` at pack load. Never persisted (Unicode
  normalization varies across Python versions).
- `KnowledgeSet` Protocol gains a `dictionary` property and a
  `names_index(query)` method; `InMemoryKnowledgeSet` and
  `SQLiteKnowledgeSet` implement both. `from_rows` and `_build` now
  require `dictionary=`; `from_rows` also validates `pack_hash` and
  `dictionary_version`.
- `SQLiteKnowledgeSet` TOCTOU detection: `_build` snapshots
  `(st_size, st_mtime_ns, st_ino)`; `_connect` and `names_index`
  raise `PackStaleArtifactError` (`PACK_STALE_ARTIFACT`) if
  `pack.sqlite` changed since load. Documented in `PACK_FORMAT.md`.
- `agri_core.registry.resolve_taxon(name)` returns
  `TaxonOk | Ambiguous | Unknown`. `TaxonOk` carries `taxon_id`,
  display `name`, `matched_via`, `scientific_name`, `rank`.
  `TaxonOutcome` is a discriminated union with its own
  `TaxonOutcomeAdapter`, kept separate from `Outcome` to avoid a
  `status="ok"` collision.
- `Unknown.code` (nullable lowercase snake_case) and
  `Ambiguous.truncated` are additive fields on the refusal models;
  `outcome.schema.json` regenerated. PR-1 populates `no_match` and
  `empty_input`; a follow-up PR-mini will ship the code registry.
- Perf gate `tests/perf/test_resolve_taxon.py` enforces p95 < 5 ms
  per query on a 10k-taxa pack; marker `perf` can be excluded with
  `-m 'not perf'` on slow runners.
- `docs/decisions/ADR-004-resolution-policy.md` -- normalization,
  match set (union, not authoritative), ambiguity, `matched_via`
  precedence, name index design, TOCTOU, `TaxonOutcome` union,
  `Unknown.code` semantics. Deferral scope for PR-2 and PR-3
  recorded explicitly.
- `schema/unknown_code_registry.json` (new) -- registry for
  `Unknown.code` values with `status: "active" | "planned"`. Two
  codes are `active` (`empty_input`, `no_match`); four are
  `planned` for `resolve_fact` (PR-2): `below_min_status`,
  `scope_not_covered`, `value_unknown`, `license_excluded`.
  `tests/contract/test_unknown_code_registry.py` enforces drift
  between the registry, the emitted codes in source, and ADR-004.
- `registry/resolution.py`: `resolve_fact(pack, taxon_id, parameter, *,
  phase=None, scope=None, min_status="approved", require_commercial=False)`
  returns `FactResolved | Unknown | NotApplicable | InsufficientInput`.
  Filters in order: parameter lookup, `applies_to` match, phase
  validation, safety floor (`min_status` raised to `reviewed` for
  `safety_class != "none"`), superseded exclusion, status filter,
  scope match, license gate. Winner is the most specific candidate
  (largest `len(scope)`), then highest status, then newest review,
  then smallest `fact_id`.
- Scope matching uses union semantics: a fact matches when its scope
  keys are a subset **or** a superset of the request keys, with
  per-key value check on the intersection (range scope: fact covers
  request; multi string/enum: set equality; scalar: equality).
  Partial overlap is rejected — the fact requires a constraint the
  caller did not supply.
- `FactResolved` model: winning `fact`, its `value` / `value_pretty`,
  non-superseded `alternatives`, `Provenance` naming only the
  winner, and `warnings` (`fact_conflict`, `safety_min_status_raised`).
- `models/fact.py::format_value(value: FactValue) -> str`: deterministic
  display text for every `FactValue` shape (scalar / range / trapezoid
  / enum / enum_set / bool / rule / unknown).
- `schema/unknown_code_registry.json`: `license_excluded` promoted from
  `planned` to `active`; emitted by `resolve_fact` when
  `require_commercial=True` and no matching fact passes the gate. The
  other three `planned` codes stay reserved for a later PR.
- `registry/resolution.py`: `MetaInfo` model and `meta(pack) -> MetaInfo`
  (pure; reports engine version, pack version, schema version,
  dictionary version, content hash, artifact sha256, synthetic flag,
  verified flag). `FactOutcome` union (`FactResolved | Ambiguous |
  Unknown`) and `FactOutcomeAdapter` for CLI/JSON consumers.
- `agri-core show` command with three modes: `--name`, `--taxon`,
  `--fact`. `--json` swaps text output for model JSON.
  `--language` applies to `--name`; `--min-status` and
  `--require-commercial` apply to `--taxon`. Exit codes: 0 success,
  1 not-found/unknown/ambiguous, 2 usage, 3 unreadable pack.
- `schema/taxon_outcome.schema.json`, `schema/fact_outcome.schema.json`,
  `schema/meta_info.schema.json` (new), regenerated by
  `scripts/gen_schemas.py` and kept in sync by
  `tests/contract/test_resolution_schemas.py`.
- `docs/decisions/ADR-004-resolution-policy.md`: status moves to
  **M8-PR-3, final**. New section documenting `meta()` and `show`.
  Deferred section replaced by Completed.
- `README.md`: Registry feature row and M8 milestone move to Done.
- `resolve_taxon` gains a keyword-only `language: str | None = None`
  filter. When set and at least one matching entry carries the tag,
  the candidate set narrows to those entries before `matched_via`
  precedence; otherwise the full match set is used (soft
  preference). `agri-core show --name ... --language LANG` forwards
  the parameter to `resolve_taxon`; the post-hoc name lookup in the
  CLI is removed (single source of truth).
- `tests/contract/test_resolve_taxon.py` (new, 21 tests) closes the
  missing contract test file for `resolve_taxon`. Covers exact /
  ambiguous / unknown, case, hybrid sign, ambiguity via the real
  loader (D18), truncation at 20, accepted_name collision, and the
  five `language` cases.
- `docs/decisions/ADR-004-resolution-policy.md`: new section
  documenting `language` preference; `test_resolve_taxon.py`
  reference made explicit (`tests/contract/...`); Completed
  section notes the follow-ups.




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

- Coverage is now enforced by an explicit
  `coverage report --fail-under=90 --skip-covered` step in CI
  (`ci.yml`), run after `pytest` in the `locked`, `latest`, and
  `lowest-direct` jobs. The step reads `[tool.coverage.report]`
  from `pyproject.toml`, which now sets `precision = 2`, so the
  comparison is at full precision: `90.86 < 90` passes,
  `90.86 < 91` fails, `90.86 < 90.87` fails. Previously the gate
  used `--cov-fail-under=90` inside `addopts`, which compared
  `round(total)` instead of `total`, so a run at 89.5% (rounded
  to 90) slipped past. `addopts` no longer carries
  `--cov-fail-under`.
- Local `make check` now runs `coverage` (pytest +
  `coverage report --fail-under=90`) instead of `test`, and
  `make coverage` is a new target. `pytest` alone is still
  available and does not gate on coverage.
- `agri-core diff` is now status-aware for fact content changes.
  Changes to `value`, `scope`, `parameter`, `taxon_id`, or `phase`
  are violations only when the OLD fact was `reviewed` or
  `approved`. `draft` and `imported` facts may be edited in place
  without supersession. Fields that remain acceptable in place
  regardless of status: `status`, `evidence`, `reviewed_by`,
  `reviewed_at`, `locator`, `superseded_by`, `src`, `dataset_id`,
  `provenance_kind`.
- Unified the two finding types. `agri_core.registry.Finding`
  (dataclass) is removed; `agri_core.models.finding.Finding`
  (Pydantic) is the single type used by both
  `agri-core lint-sources` and `validate_pack_report`.
  `Finding.severity` is `FindingSeverity` (StrEnum) instead of
  `Literal`; `file` and `line` live under `.location.file` and
  `.location.line`. The unused `"info"` severity value is
  dropped (was never constructed by the linter).
- `agri-core validate` gains `--json` and `--strict`. `--json`
  emits `{pack, sources, report}` with the full findings list
  (SRC + PACK codes, sorted) and `report.ok`/`report.report_version`;
  the exit code is unchanged. `--strict` promotes warnings to exit 1
  (errors already exit 1). Load errors (unreadable pack) always
  exit 3, distinct from rule findings. Text mode is unchanged for
  the sample pack: 0 findings -> 0 errors, 0 warnings, exit 0.
- Breaking: `InMemoryKnowledgeSet.from_rows` and
  `SQLiteKnowledgeSet._build` now require a `dictionary` argument;
  `from_rows` default for `verified` changes from `True` to `False`
  (the loader still passes `verified=True` after hash verification).



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

### Fixed

- `PACK_SAFETY_VIOLATION` now fires for **all** `safety_class != "none"`
  parameters (`dose_cap`, `toxicity_limit`, `regulatory`), not only
  `dose_cap`. The load-time predicate in
  `pack/loader.py::_validate_structure` was `== "dose_cap"`, so a
  fact whose parameter was classified `toxicity_limit` or
  `regulatory` could be `draft` or `imported` without tripping the
  rule. README design #8 applies to any safety-critical parameter.
  3 new tests (`test_dose_cap_draft_violation`,
  `test_toxicity_limit_draft_violation`,
  `test_regulatory_draft_violation`).


## [0.0.0] - 2026-10-17

- Repository created.
