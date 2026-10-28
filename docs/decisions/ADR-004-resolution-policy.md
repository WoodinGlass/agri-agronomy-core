# ADR-004: Taxon and fact resolution policy

Status: Accepted (M8-PR-3, final).

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

A separate PR-mini (`chore/m8-unknown-code-registry`) ships
`schema/unknown_code_registry.json` with every planned code, each
carrying a status: `active` means the code is already emitted by
the resolver; `planned` means the code is reserved for a later PR
and not yet emitted. `below_min_status`, `scope_not_covered`,
`value_unknown`, and `license_excluded` are `planned` until PR-2.
A drift test (`tests/contract/test_unknown_code_registry.py`)
keeps the registry, the source, and this section in sync. Until
every code is `active`, the wire contract remains the schema's
`pattern` (not a `Literal`).

## Decision — `resolve_fact` pipeline (finalized M8-3b)

`resolve_fact(pack, taxon_id, parameter, *, phase=None, scope=None,
min_status="approved", require_commercial=False)` returns
`FactResolved | Unknown | NotApplicable | InsufficientInput`.

Filters in fixed order:

1. `taxon_id` must exist in the pack; else `Unknown(code="no_match")`.
2. `parameter` must exist in the dictionary; else
   `Unknown(code="no_match")`.
3. `parameter.applies_to` must match the taxon (organism_group,
   archetype, uses intersection, traits intersection); else
   `NotApplicable`.
4. If `parameter.phase_set != "none"` and `phase` is `None`,
   `InsufficientInput(missing=["phase"])`. If `phase` is provided but
   is not in `parameter.allowed_phases` (or, when that is `None`, in
   `dictionary.phases_by_archetype[taxon.archetype]`), the same
   `InsufficientInput` is returned.
5. Superseded facts are excluded.
6. Facts below `min_status` are excluded. For safety-critical
   parameters (`safety_class != "none"`) the effective floor is
   raised to `"reviewed"`; the elevation is recorded as
   `Notice(code="safety_min_status_raised")`.
7. Facts whose `phase` does not match the requested `phase` are
   excluded (only for phase-bearing parameters).
8. Facts whose `scope` does not match the requested `scope` are
   excluded (see next section).
9. If `require_commercial=True`, facts whose sources are not all
   `commercial_use="yes"` are excluded; if no fact survives, the
   result is `Unknown(code="license_excluded")`.

If no candidate survives filters 1-8, the result is
`Unknown(code="no_match")`. The winner is the most specific candidate
(largest `len(fact.scope)`), then highest status
(`approved > reviewed > draft > imported`), then most recent
`reviewed_at`, then smallest `fact_id`. The remaining candidates
become `alternatives` (same sort order, winner excluded).

`Unknown.code` grows by one active entry in this PR:
`license_excluded` is promoted from `planned` to `active` in
`schema/unknown_code_registry.json`. The other three planned codes
(`below_min_status`, `scope_not_covered`, `value_unknown`) stay
`planned` until a later PR; the drift test rejects any of them
appearing in source before then.

## Decision — Scope matching (finalized M8-3b)

Scope matching uses **union semantics** (informally, "A \u222a B"):
a fact matches when its scope keys are a subset of the request keys,
**or** the request keys are a subset of the fact keys. Both
directions are allowed because a fact without `country` is a global
claim and a fact with `country: ID` is a specific one; a request with
`country` should find both, and a request without `country` should
still find the global one.

Per-key value check runs only on the intersection. For each shared
key:

- **`range`** (`elevation_m`): fact `[lo_f, hi_f]` covers request
  `[lo_r, hi_r]` when `lo_f <= lo_r` and `hi_f >= hi_r`.
- **`multi` string/enum** (`system`, `climate_zone`, `country`,
  `variety`, ...): fact and request lists are compared as sets.
- **scalar string/enum**: equality.

**Partial overlap is rejected**: if neither side's keys are a subset
of the other's, the fact is not returned. This is intentional. The
fact requires a constraint the caller did not supply, and that
constraint cannot be verified from the available data. A permissive
intersection rule would silently match facts whose applicability the
resolver cannot check. Callers that want broader matching should
supply the constraint.

A fact with an empty scope matches any request. A request with an
empty scope matches every fact; the tie-break makes the most
specific fact win.

## Decision — `FactResolved` and warnings (finalized M8-3b)

`FactResolved` is a success model, parallel to `TaxonOk` and
`Result` but for fact queries. It is **not** part of the `Outcome`
union (like `TaxonOutcome`, it has its own adapter-free usage for
now; a `FactOutcome` adapter is deferred to PR-3 when the `show`
CLI needs to serialize it).

Fields:

- `fact: FactRow` — the winning fact.
- `value: FactValue` and `value_pretty: str` — `value` mirrors
  `fact.value`; `value_pretty` is `format_value(fact.value)` (a
  deterministic display string, not a wire format).
- `alternatives: list[FactRow]` — non-superseded other matches,
  sorted by the same tie-break as the winner (winner excluded).
- `provenance: Provenance` — `fact_ids` names **only** the winner;
  `pack_version`, `pack_hash`, and `source_ids` follow the existing
  `Provenance` contract.
- `warnings: list[Notice]` — populated in three cases:
  - `Notice(code="fact_conflict")` — an alternative carries a
    different `value` than the winner. Same `value` with a different
    `src` is corroboration, not a conflict.
  - `Notice(code="safety_min_status_raised")` — the safety floor
    (filter 6) was raised.
  - No other warning codes are emitted by `resolve_fact`.

## Decision — `meta()` and show CLI (finalized M8-4)

`meta(pack) -> MetaInfo` is a pure function over the loaded pack:

- `engine_version` — running `agri-core.__version__`.
- `pack_version` — `pack.manifest.version`.
- `schema_version` — `pack.manifest.schema_version`.
- `dictionary_version` — `pack.dictionary_version`.
- `content_hash` — `pack.pack_hash` (semantic pin).
- `artifact_sha256` — `pack.manifest.artifact_sha256` (source packs: `None`).
- `synthetic` — `pack.manifest.synthetic`.
- `verified` — `pack.verified`.

`FactOutcome = Annotated[FactResolved | Ambiguous | Unknown,
Field(discriminator="status")]` and `FactOutcomeAdapter` live in
`registry/resolution.py`. Kept separate from `Outcome` and
`TaxonOutcome` for the same `status="ok"` collision reason.

`agri-core show` has three modes, exactly one required:

- `--name NAME` — resolves via `resolve_taxon`, prints `ok:` /
  `ambiguous:` / `unknown:` in text mode or the `TaxonOutcome` JSON.
  `--language LANG` optionally swaps the display name for a
  `names.csv` entry in that language.
- `--taxon TAXON_ID` — prints the taxon row and its facts.
  `--min-status` filters by minimum status; `--require-commercial`
  keeps only facts whose sources are all `commercial_use="yes"`.
- `--fact FACT_ID` — prints one fact by `fact_id`.

Exit codes: 0 success; 1 not-found / unknown / ambiguous; 2 usage
(no/both modes, invalid `--min-status`, mode-mismatched flags); 3
unreadable pack. `--json` swaps text for the model's
`model_dump(mode="json")` for all three modes.

JSON Schemas for the resolution types ship in `schema/` and are
kept in sync by `tests/contract/test_resolution_schemas.py`:
`taxon_outcome.schema.json`, `fact_outcome.schema.json`,
`meta_info.schema.json`.

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

## Completed

All three PRs (M8-PR-1, M8-PR-2, M8-PR-3) have landed. The M8
resolution policy is stable; a change requires a superseding ADR.
