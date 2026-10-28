# ADR-004: Taxon and fact resolution policy

Status: Accepted (M8-PR-1). Updated as M8 sub-PRs land.

## Context

The `Registry` feature (README row 3) promises `resolve_taxon` and
later `resolve_fact` and `meta()`. Resolution is a decision procedure
over a loaded `KnowledgeSet`: a caller supplies a free-form name or a
`(taxon_id, parameter, ...)` query, and the resolver returns either a
concrete answer with provenance or a structured refusal. Three
concerns drive the design.

1. **Non-authoritative matching.** `taxon.csv` records
   `scientific_name` and `accepted_name`; `names.csv` records aliases
   in many languages. Any of these is a valid way to reach a taxon,
   but none of them is "the" answer when multiple rows disagree.
2. **Determinism.** Two callers must get the same outcome for the
   same query against the same pack, independent of iteration order,
   Unicode representation, or filesystem timestamp resolution.
3. **Fail-closed on ambiguity.** When more than one taxon matches, the
   resolver must **refuse** and let the caller choose, not pick a
   winner by accident.

## Decision — Name normalization (finalized M8-1a)

`pack/normalize.py` exposes two pure functions:

- `normalize_name(s)` for taxon names: NFKC, then `str.casefold()`,
  then multiplication-sign `×` (U+00D7) folded to ASCII `x`, then
  whitespace collapse (any Unicode whitespace run, including NBSP,
  becomes one ASCII space; leading and trailing are stripped). Empty
  input normalizes to `""`.
- `normalize_scope_value(s)` for scope keys: same pipeline without
  the hybrid lift. Scope keys are lowercase ASCII in practice;
  folding `×` there would surprise nobody and help nobody.

The hybrid lift is **matching-only**. Display (`TaxonOk.name`,
`Ambiguous.candidates[].name`) uses the string from the pack
unchanged. Rationale: users type `x` on a US keyboard; `×` is the
correct botanical convention, and both spellings should match.

## Decision — Match set is the union, not authoritative (finalized M8-1b)

`names_index(query)` is defined on the `KnowledgeSet` Protocol and
both backends. The set of entries that can match a query is:

    scientific_name ∪ accepted_name ∪ names.csv

Every entry is a `NameIndexEntry` (see `pack/name_index.py`) with
`matched_via ∈ {scientific_name, accepted_name, names}`.

**None of the three is authoritative.** A `scientific_name` in
`taxon.csv` is not a better match than the same string appearing as a
`names.csv` entry; both reach the same taxon. Conversely, a
`scientific_name` in one row and the same string as `accepted_name`
in another row means **two distinct taxa**, and the resolver reports
that as ambiguity (see next section).

## Decision — Ambiguity (finalized M8-1b)

- **One distinct `taxon_id`** in the match set yields `TaxonOk`.
- **More than one distinct `taxon_id`** yields `Ambiguous` with
  `candidates` sorted by `taxon_id`. The list is capped at
  `Ambiguous.candidates` `max_length` (20). When the cap is hit,
  `Ambiguous.truncated=True` and the first 20 sorted candidates are
  kept.
- **`accepted_name` collision** — a row whose `accepted_name` equals
  another row's `scientific_name` yields **two** taxon IDs and
  therefore `Ambiguous`. This case is tested via a real loader
  fixture, not `from_rows`.
- **Empty query after normalization** yields
  `Unknown(code="empty_input")`. `names_index("")` returns `()`;
  the resolver short-circuits earlier so the caller sees the
  specific reason.
- **No match** yields `Unknown(code="no_match")`.

## Decision — `matched_via` precedence and reporting (finalized M8-2a)

`TaxonOk` carries one `matched_via`. When multiple entries from the
**same** taxon match, the resolver picks the highest-precedence
entry:

    scientific_name > accepted_name > names

Within the same `matched_via`, an entry with `preferred=True` wins.
Final tie-break is `name` (deterministic). `Ambiguous.candidates[].note`
records the matched path of each candidate so a caller can see
whether the candidates agree or disagree on the route.

## Decision — Name index design (finalized M8-1b)

- **Built eagerly at load**, never persisted. Unicode normalization
  differs between Python versions; an on-disk index would need a
  version tag and a rebuild path that no consumer needs.
- **InMemory backend.** `_name_index` is a `MappingProxyType` of
  `{normalized_name: tuple[NameIndexEntry, ...]}`. Sort key per
  bucket is `(taxon_id, matched_via, language, name)`.
- **SQLite backend.** `_build` runs two raw `SELECT`s (`taxa`,
  `names`), wraps each row with `model_construct` (rows were
  validated at build time; `model_validate` per row is unnecessary
  I/O) and feeds them through the same `build_name_index` used by
  the in-memory backend. The result is the same `MappingProxyType`.
- **No `_iter_models`** in the index build path. `_iter_models`
  validates each row through Pydantic; the index build deliberately
  bypasses that because the pack was already validated by
  `agri-core validate` / `agri-core pack build` before the loader
  saw it.

## Decision — TOCTOU detection (finalized M8-1b)

`SQLiteKnowledgeSet` snapshots `(st_size, st_mtime_ns, st_ino)` of
`pack.sqlite` at `_build` time. `_check_not_stale()` compares the
snapshot against the current `stat`; it is called from `_connect()`
and from `names_index()`. Any difference raises
`PackStaleArtifactError(code="PACK_STALE_ARTIFACT")`, which the
caller handles by re-loading the pack.

**Limits.** This catches accidental replacement (for example,
`agri-core pack build` writing into a directory whose pack is still
loaded) and detects mismatched-load scenarios. It does not defend
against a malicious local attacker who can rewrite both the file and
its timestamp; that is out of scope for a library.

**Why `_connect` and `names_index` both check.** `names_index` reads
only from the in-memory index and never touches SQLite; without an
explicit check it would happily answer from a stale index. The 1 µs
`stat` cost is negligible against the ~12 µs p95 baseline measured
in `tests/perf/test_resolve_taxon.py`.

## Decision — `TaxonOutcome` union (finalized M8-2a)

`resolve_taxon` returns:

    TaxonOutcome = Annotated[
        TaxonOk | Ambiguous | Unknown,
        Field(discriminator="status"),
    ]

`TaxonOutcome` is a **separate** discriminated union from `Outcome`:

- `TaxonOk.status` is `"ok"`, but so is `Result.status`
  (`models/result.py`). Putting both in one union would make the
  discriminator ambiguous.
- `TaxonOutcomeAdapter = TypeAdapter(TaxonOutcome)` is the
  caller-facing validator; `OutcomeAdapter` is unchanged.
- A future `FactOutcome` will be a third union. The pattern is
  "one union per resolution function", not "one giant union".

## Decision — `Unknown.code` semantics (finalized M8-2a)

`Unknown` gains an **optional** `code: str | None = None`,
constrained to `^[a-z][a-z0-9_]*$` (same shape as `Notice.code`).
The `reason` remains mandatory and human-readable; `code` is the
stable machine handle.

PR-1 populates two codes:

- `"empty_input"` — the query was empty after normalization.
- `"no_match"` — the query normalized fine but nothing matched.

A separate PR (`chore/m8-unknown-code-registry`, a PR-mini in the
M8 plan) will ship a registry file plus a drift test once PR-2's
codes (`below_min_status`, `scope_not_covered`, `license_excluded`,
`value_unknown`) are also in place. Until then, `code` is a
free-form lowercase string, and the schema's `pattern` (not a
`Literal`) is the contract.

## Consequences

- `resolve_taxon` is **pure**: no filesystem or clock access; all I/O
  happened when the `KnowledgeSet` was loaded.
- `Unknown.code` and `Ambiguous.truncated` are the only additions to
  the refusal models that `resolve_taxon` needs; both are
  nullable/defaulted to keep existing call sites working.
- `Outcome` and `OutcomeAdapter` are untouched;
  `outcome.schema.json` regenerates with the additive fields only.
- Every new behavior has a test: `test_name_index.py`,
  `test_names_index.py`, `test_resolve_taxon.py`,
  `test_stale_artifact.py`, `test_pack_hash_validation.py`,
  `tests/perf/test_resolve_taxon.py`.
- **Breaking:** `from_rows` / `_build` now require `dictionary=`,
  and `from_rows` defaults `verified=False`. The loader continues
  to pass `verified=True` after verifying `content_hash` or
  `artifact_sha256`.

## Deferred to PR-2 and PR-3

The following are **not** part of PR-1 and are recorded here so the
scope boundary is explicit:

- **PR-2** — `resolve_fact`: scope matching (range = cover, multi =
  intersection, string/enum = equality), `min_status` default plus
  safety floor, license gate, phase-missing to `InsufficientInput`,
  `NotApplicable` semantics, `FACT_CONFLICT` handling,
  `FactResolved` model, `format_value` helper, `Provenance`
  validator.
- **PR-3** — `meta()` and the `show` CLI: output shape, exit codes,
  `taxon_outcome` / `fact_outcome` / `meta_info` JSON schemas.
