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

## Decision — Language preference (added M8 follow-up)

`resolve_taxon(pack, name, *, language: str | None = None)` accepts
an optional BCP-47 tag. When `language` is set and at least one
entry in the query's match set carries that tag, the candidate set
is narrowed to those entries before the `matched_via` precedence is
applied. When the query has no entries in that language, the full
match set is used (soft preference, not a hard filter), so a
scientific-name query like `"Testus annualis"` with `language="id"`
still resolves via `scientific_name`.

Tags recognised in practice: `"la"` on the synthetic
`scientific_name` / `accepted_name` entries, and any language tag
present in `names.csv` (e.g. `"id"`, `"en"`, `"ja"`). The
`agri-core show --name ... --language LANG` flag forwards this
parameter verbatim; there is no second post-hoc name lookup in the
CLI.

## Input length guard (added M8 review G9, 2026-11-04)

`resolve_taxon` rejects raw input longer than `_MAX_INPUT_LENGTH = 200`
characters with `Unknown(code="input_too_long")`. The check runs **before**
name normalization; the raw caller-supplied string is measured, not the
normalized form.

### Why 200

`NameRow.name`, `TaxonRow.scientific_name`, and `TaxonRow.accepted_name`
all cap at `max_length=200`. A taxon name in a pack cannot exceed 200
characters, so an input string longer than 200 cannot resolve to any
taxon by construction. Rejecting early avoids the cost of `normalize_name`
+ `names_index` on inputs that cannot succeed, and short-circuits a
caller that constructs very long strings (an LLM agent composing a
prompt, a truncated prompt fragment, an adversarial payload).

### Why check before normalize

`normalize_name` applies NFKC, which can *expand* certain characters
(U+FB00 LATIN SMALL LIGATURE FF becomes "ff", doubling length; U+3316
SQUARE KIROGURAMMU becomes "kirogurammu" — 12 characters from 1). A
200-character input of ligatures normalizes to ~400 characters. If the
check ran *after* normalization, a caller who submitted 200 characters
would be rejected for a length problem the caller did not cause.

The check is on the raw input. NFKC-expanded strings are passed to
`names_index` unchanged — they simply do not match any taxon (which is
correct: no pack name can contain a 200-character ligature run).

### Why not reuse `empty_input`

`empty_input` means the query normalized to an empty string (whitespace
only). `input_too_long` means the query exceeded the length bound. A
caller that sees `empty_input` will retry with a real query; a caller
that sees `input_too_long` will shorten. Distinct problems, distinct
codes.

### Order: length before empty

Length is checked first. Input `" " * 201` yields `input_too_long`, not
`empty_input`. The length problem dominates — the caller should shorten
before worrying about emptiness. Within the length bound, whitespace-only
input still yields `empty_input` (existing behavior, unchanged).

### Policy version MINOR bump

`RESOLUTION_POLICY_VERSION` moves from `1.2.0` to `1.3.0`: a new active
`Unknown.code` is introduced and a class of previously-`no_match` or
`empty_input` queries (raw input > 200 chars) becomes `input_too_long`.
No previously-`ok` query is affected; no previously-`ambiguous` query is
affected. Callers that only branch on `isinstance(r, Unknown)` are
unaffected.


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
in `tests/perf/test_resolve_taxon_perf.py`.

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

## Semantic lock — superseded facts are never observable (added M8 review G2, 2026-11-04)

The exclusion in filter 5 is not merely a pipeline optimization. It is a
hard invariant of the resolution contract:

> **G2-1.** A `FactRow` whose `superseded_by` is not `None` MUST NOT
> appear in any output position of a `FactResolved`:
>
> - `FactResolved.fact` (the winner);
> - `FactResolved.alternatives` (other matching facts);
> - `FactResolved.provenance.fact_ids` (the winner only, by the existing
>   `Provenance` contract);
> - any `Notice.payload` carrying a `FactRow` (none exists today; this
>   forbids its future introduction).

> **G2-2.** If every `FactRow` matching `(taxon_id, parameter, ...)` is
> superseded, `resolve_fact` MUST return
> `Unknown(code="no_match")`. It MUST NOT return `FactResolved` referring
> to a superseded fact, and MUST NOT raise.

**Implementation note.** Filter 5 already enforces G2-1 structurally:
`registry/resolution.py` (the loop building `candidates`) skips superseded
rows *before* they enter the candidate list, so they cannot reach
`alternatives` (built from `candidates`) or the winner (selected from
`candidates`). G2-2 follows: if the candidate list is empty after all
filters, the existing `Unknown(code="no_match")` branch fires.

**Scope — what is *not* enforced here.** The resolver does not follow
the `superseded_by` chain transitively. If `F1.superseded_by = F2` and
`F2.superseded_by = F3`, `F1` is invisible (correct) and `F2` is invisible
(correct) — both are correctly excluded because both have a non-`None`
pointer. Chain depth is irrelevant; a single hop suffices. FK existence
and cycle-freedom are load-time invariants (`PACK_FK_VIOLATION`,
`PACK_SUPERSEDED_SELF`, `PACK_SUPERSEDED_CYCLE`) and are not re-checked
at resolution time.

**Test coverage.** `tests/contract/test_resolve_fact.py` contains
`test_superseded_excluded` (winner), `test_superseded_never_in_alternatives`
(G2-1), and `test_superseded_only_match_returns_no_match` (G2-2).

## Semantic lock — advisories are warnings, not blockers (added M8 review G3, 2026-11-04)

`advisories.csv` is reserved for **safety-critical corrections keyed by
`fact_id`**. Two correction mechanisms exist in the pack format, and they
are **not** interchangeable:

- **Supersession** (`fact.superseded_by` set) retires a fact: the old
  fact is invisible at resolution (G2-1, G2-2), and a new `fact_id`
  replaces it (ADR-003). Use it when the *value* is wrong.
- **Advisory** (a row in `advisories.csv` keyed by `fact_id`) annotates a
  fact that remains valid. The fact still participates in tie-breaking
  and can win. The advisory surfaces as a `Notice` warning on the
  result. Use it when the value is *correct* but a safety condition,
  restriction, or caveat applies.

### G3-1 — Warning, never a blocker

When advisory loading ships, an advisory attached to a fact MUST:

- **not** remove the fact from `candidates`;
- **not** affect tie-breaking, `fact` selection, or `alternatives`;
- **surface** as `Notice(code=<advisory.code>, message=<advisory.message>)`
  in `FactResolved.warnings`;
- have `code` satisfy the `Notice.code` regex (`^[a-z][a-z0-9_]*$`) and
  not collide with the reserved codes `safety_min_status_raised` and
  `fact_conflict`.

Multiple advisories per fact are additive: all surface, in pack order.
An advisory whose `fact_id` refers to a fact with `superseded_by` set
is contradictory and MUST be rejected at load time
(`PACK_ADVISORY_ON_SUPERSEDED`); its `fact_id` MUST also satisfy the
existing FK rule (`PACK_FK_VIOLATION`).

### G3-2 — License gate: advisory sources are gated stricter than fact sources

Every advisory row MUST carry `src` (list of `source_id`). The license
gate applies to advisory sources **more strictly** than to fact sources:

- A fact whose `src` is non-commercial may still exist in a pack and be
  surfaced when `require_commercial=False` (existing behavior, ADR-005).
- An advisory whose `src` is non-commercial is **invalid at load time**:
  the pack MUST be rejected with `PACK_ADVISORY_NC_SOURCE`. Non-commercial
  advisory text never enters a loadable pack, regardless of
  `require_commercial`.

This asymmetry is deliberate. Advisory text is a **safety warning
attached to a fact**; shipping a warning whose own provenance is
non-commercial is a license violation that no runtime flag can undo. The
fact-side gate, by contrast, can be enforced at resolution time because
the fact is a value claim whose data license may be stricter than the
engine's use of it. No exception is made for advisory sources.

### G3-3 — Current state: fail-closed until implementation ships

`pack/loader.py` and `pack/sqlite_schema.py` reject any non-whitespace
`advisories.csv` with `PACK_FEATURE_UNSUPPORTED`. This is a **gate until
implementation ships**, not a semantic decision that advisories would
block resolution. Today: an advisory cannot be carried in a loadable
pack; `resolve_fact` can never see one; G3-1 and G3-2 are **forward
commitments** that fire when load support ships.

### Deferred to the advisory-loading milestone

Deliberately omitted from this decision (listed so future readers know
the omission is intentional):

- `advisories.csv` schema — columns, PK, `issued_at` semantics.
- `advisory_code_registry.json` — whether codes are enumerated
  (current direction: no, mirror `Notice.code`).
- `advisory_id` membership in `ids.lock` (ADR-011).
- `KnowledgeSet.advisories_for(fact_id)` API surface.
- `show` text mode surfacing (current direction: `--json` only, via the
  existing `warnings` field).
- Advisory propagation to `alternatives` entries (current direction:
  per-query, no propagation).

## Specificity policy — target partial order, current cardinality (added M8 review G4, 2026-11-04)

**Target.** Two facts with scopes `A` and `B` are comparable when one is
strictly narrower than the other: `A ⊃ B` or `B ⊃ A` in the
subset-of-keys sense, with narrower (or equal) value ranges on shared
keys. Under the target policy, the more specific fact wins.
**Incomparable** facts (neither strictly narrower) MUST surface as a
dedicated `FactConflict` outcome, not be resolved by an arbitrary
tie-break.

**Current implementation.** `_fact_sort_key` uses a total order:

1. larger `len(fact.scope)` (cardinality, not subset-of-keys);
2. higher status (`approved > reviewed > draft > imported`);
3. more recent `reviewed_at`;
4. smaller `fact_id`.

**Known deviation.** Two facts with **same cardinality but disjoint
scope keys** (for example `{country: ID}` vs `{system: field}`) are
**incomparable** under the target policy, but are resolved today by the
`fact_id` tie-break. This is deterministic but arbitrary — it does not
reflect a specificity ordering.

**Migration path.** M9+ will introduce:

- a partial-order comparator over scope keys and value ranges;
- a `FactConflict` outcome kind (new `$defs` member in
  `schema/fact_outcome.schema.json`, new `oneOf` branch);
- a MAJOR bump of `resolution_policy_version` (per the policy version
  section below), because a previously-`ok` query on incomparable facts
  becomes a `FactConflict` outcome.

**Executable documentation.**
`tests/contract/test_resolve_fact.py::test_incomparable_scope_arbitrary_tiebreak_documented`
encodes this gap as an `xfail(strict=False)` test: it fails today (the
resolver returns `FactResolved` for two incomparable facts) and will
pass automatically when M9+ implements the target policy. When that
happens, the xfail marker should be removed and the test becomes a
positive assertion that `FactConflict` is returned.

## Status policy — default minimum, safety floor, and applied floor (added M8 review G5, 2026-11-04)

`resolve_fact` applies a **status floor**: a fact whose `status` ranks
below the floor is excluded. The floor has three parts.

### G5-1 — Default minimum is `approved`

`min_status` defaults to `"approved"`. A caller who does not pass
`min_status` sees only approved facts. Lower-status facts (`reviewed`,
`draft`, `imported`) are excluded silently; the caller learns nothing
about them from the result.

`min_status=None` disables the filter entirely — every non-superseded,
scope-matching fact is a candidate, whatever its status. `"imported"` is
the lowest status rank, so `min_status=None` and `min_status="imported"`
yield identical candidate sets; the difference is caller intent, not
behavior.

### G5-2 — Safety floor raises the minimum to `reviewed`

Parameters with `safety_critical=True` raise the effective floor to
`"reviewed"` regardless of `min_status`:

- `min_status=None` or any rank below `"reviewed"` → effective floor
  becomes `"reviewed"`;
- `min_status="approved"` → effective floor stays `"approved"` (already
  above);
- the raise emits `Notice(code="safety_min_status_raised")` so a caller
  can tell the floor was elevated.

### G5-3 — `FactResolved.min_status_applied` records the effective floor

`FactResolved` gains a required field `min_status_applied: FactStatus`.
Its value is the **effective** floor after all adjustments (default,
safety raise), not the caller-supplied `min_status`. When the effective
floor is "no filter" (`min_status=None` and no safety raise), the field
is `"imported"` — the lowest rank — so the field is always a concrete
`FactStatus`, never `None`.

A caller that wants to know *what floor actually applied* (rather than
recompute it from arguments) reads this field directly.

### G5-4 — `FactResolved.fact.status` reflects the winner's actual status, not the floor

`fact.status` is the **actual** status of the winning `FactRow`; it is
not rewritten to the floor value. The two fields can differ: a
`reviewed` fact can win under `min_status="reviewed"` (or under a safety
raise), in which case `fact.status == "reviewed"` and
`min_status_applied == "reviewed"`. Under the default
`min_status="approved"`, `fact.status` is always `"approved"` and
`min_status_applied` is `"approved"`.

**Why both fields.** `fact.status` describes the chosen fact;
`min_status_applied` describes the filter. A caller who cares "is this
fact approved?" reads `fact.status`. A caller who cares "what floor did
the resolver use?" reads `min_status_applied`.

### G5-5 — Policy version MINOR bump

This is a **MINOR** change per §"resolution policy version": existing
behavior is unchanged (default floor was already `"approved"`, safety
raise was already in place); the change is the addition of a field that
exposes existing behavior. `RESOLUTION_POLICY_VERSION` moves from
`1.0.0` to `1.1.0`.

## Semantic lock — unknown at more specific scope beats value at general (added M8 review G6, 2026-11-04)

A fact whose `value` is an `UnknownValue` (`shape="unknown"`) carries the
same weight in winner selection as any other value shape. The specificity
of the scope, not the concreteness of the value, decides the winner.

### G6-1 — Scope specificity precedes value concreteness

When two approved facts match a query, the one with the **larger
`len(scope)`** wins — even if its value is `UnknownValue` and the other
carries a concrete value at a broader scope. Concretely:

- Fact A: `value=UnknownValue(reason="…")`, `scope={country: ID}`;
- Fact B: `value=ScalarValue(6.5)`, `scope={}`;
- query: `scope={country: ID}`.

A wins. The caller receives `FactResolved(fact=A,
value=UnknownValue(reason="…"))`, **not** a fallback to Fact B. The
answer to "what is the value for Indonesia?" is "unknown for Indonesia",
which is more informative than "the world-wide default is 6.5".

### G6-2 — `FactResolved.value_pretty` renders the unknown

`value_pretty` for an `UnknownValue` is `format_value(value)` — the
deterministic display string `unknown (<reason>)`. A caller that expects
a numeric string must handle the unknown case explicitly; the resolver
does not substitute a fallback value.

### G6-3 — `Unknown(code="value_unknown")` is not emitted

The resolver does **not** short-circuit to an `Unknown` outcome when the
winner is an `UnknownValue`. `FactResolved` carries the `UnknownValue`
directly, so a caller can inspect `value.reason` and treat it differently
from a numeric result. `Unknown(code="value_unknown")` remains
`planned` in `schema/unknown_code_registry.json` for a **future**
opt-in behavior (for example, a flag that says "reject unknown-valued
winners"); today's policy is to surface, not suppress.

### G6-4 — Why this is not a `value_unknown` outcome yet

`FactResolved` with `value: UnknownValue` is the canonical "we have a
fact, and it says the value is unknown" result. Rewriting it to
`Unknown` would conflate two cases the caller must distinguish:

- "no fact exists for this query" → `Unknown(code="no_match")`;
- "a fact exists, its value is unknown for this scope" →
  `FactResolved(value=UnknownValue)`.

Collapsing them loses information. If a future milestone wants to let
callers opt into the coarser form, `value_unknown` is the reserved code
for that.

## Explainability — filter counts, refined refusal codes, more-specific warnings (added M8 review G8, 2026-11-04)

`Unknown` returned from `resolve_fact` after fact filtering now carries
explainability data. A caller can see *why* a query returned nothing —
not just *that* it returned nothing.

### G8-1 — `Unknown.filter_counts` surfaces per-stage exclusions

When `resolve_fact` returns `Unknown` after fact filtering, it MUST
populate `filter_counts: dict[str, int]` with one key per filter stage:

| Key | Counts |
|---|---|
| `total` | facts present before any filter |
| `superseded` | excluded by `fact.superseded_by` |
| `min_status` | excluded by status below `effective_min` |
| `phase` | excluded by phase mismatch (only if `phase_set != "none"`) |
| `scope` | excluded by scope mismatch |
| `license` | excluded by license gate (only if `require_commercial=True`) |

Every fact contributes to exactly one key (first filter that excludes
it wins, matching the loop order). `total == superseded + min_status +
phase + scope` always; after license gate, `license` counts the
survivors of the earlier stages that failed here.

`filter_counts` is `None` for `Unknown` returned from `resolve_taxon`
or from early-return paths (empty input, taxon not found, parameter
not found) — the concept only applies after fact filtering starts.

### G8-2 — Exclusive-stage filters refine `code`

When **all** facts are excluded by a single stage, `Unknown.code` is
the stage-specific code:

- `below_min_status` — every fact failed the status filter;
- `scope_not_covered` — every fact failed the scope filter;
- `license_excluded` — every surviving fact failed the license gate
  (existing behavior).

Combinations, superseded-only, and phase-only filters yield `no_match`.
This keeps the codes **deterministic** and **unambiguous**:
`below_min_status` means *only* status was the problem, not "status
plus something else".

### G8-3 — Superseded-only and phase-only stay `no_match`

Both are already semantically covered: a superseded fact is invisible
by design (G2-1), so "the only matching fact is superseded" is
indistinguishable from "no matching fact" for the caller. Phase-only is
an input problem surfaced as `InsufficientInput(missing=["phase"])`
at step 4, not a filter stage. No new codes are introduced for these.

### G8-4 — `Unknown.warnings` carries `scope_values_available`

When `code == "scope_not_covered"` **and** `request_scope` is
non-empty, if at least one non-superseded fact shares a scope key with
the request but has a **different scalar/enum value**, `Unknown.warnings`
contains one `Notice(code="scope_values_available",
message="scope values available: <key> in {<values>} (request: <value>)")`.

The warning is **advisory**: it names the alternative values that exist
for the shared key(s). It does not change the `Unknown` outcome, does
not affect filtering, and is only emitted for `scope_not_covered`. Range
values are excluded from the enumeration — "available range values" is
not intuitive to display and the caller can query the parameter's
physical range from the dictionary.

This targets the typo case (`country="XX"` vs `country="ID"`) that
motivated the review ask. It does **not** list facts with scope keys
the request does not share — those did not cause the miss and naming
them would be noise.

`scope_values_available` is a new `Notice.code`; the pattern
(`^[a-z][a-z0-9_]*$`) admits it without registry changes.

### G8-5 — Not in scope: scope-key vocabulary validation

Typo detection (`contry` vs `country`) requires validating request
scope keys against `scope_keys.yaml` at resolution time. That is a
**separate concern** from explainability and is deferred to a later
milestone; G8-4 only considers scope keys the fact actually shares with
the request.

### G8-6 — Policy version MINOR bump

Additive: `Unknown` gains two optional fields; exclusive-stage codes
are a refinement of a previously-`no_match` outcome. No
previously-`ok` query becomes `Unknown`, no previously-`no_match`
query changes `status`. `RESOLUTION_POLICY_VERSION` moves from
`1.1.0` to `1.2.0`.

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

## Decision — resolution policy version (added 2026-11-04)

The resolution policy — name normalization, match precedence, scope
matching, safety-min-status behavior, and every rule that decides
between competing facts — is versioned. `RESOLUTION_POLICY_VERSION`
is a SemVer string in `src/agri_core/__init__.py`, currently:

    RESOLUTION_POLICY_VERSION = "1.3.0"

It surfaces in two places:

- **`MetaInfo.resolution_policy_version`** — pack-level metadata
  returned by `meta(pack)`. Tells a consumer which policy resolved
  anything in this pack.
- **`Provenance.resolution_policy_version`** — per-result. A consumer
  that stores a result and re-reads it later can tell exactly which
  policy produced it, even after the engine has shipped a newer
  version.

**SemVer rules.**

- **MAJOR** — semantic change to an existing decision. Examples:
  changing the default status minimum, changing scope-matching
  direction, changing what counts as "more specific", adding or
  removing a refusal code from a path that previously succeeded.
- **MINOR** — new rule that does not change existing behavior.
  Examples: a new refusal code that fires only on inputs that
  previously returned `unknown` with a less specific reason; a new
  warning code that is additive.
- **PATCH** — documentation or clarity. No behavior change.

The version is a property of the policy, not of the engine. An engine
release may bump `__version__` without bumping
`RESOLUTION_POLICY_VERSION`, and vice versa. A consumer that wants
"stable resolution behavior" pins `RESOLUTION_POLICY_VERSION`, not
`__version__`.

**Drift.** The version appears in the code and in this ADR; a contract
test (`tests/contract/test_resolution_policy_version.py`) fails if the
two disagree. Changing the version without updating both is drift.

## Consequences

- `resolve_taxon` is **pure**: no filesystem or clock access; all I/O
  happened when the `KnowledgeSet` was loaded.
- `Unknown.code` and `Ambiguous.truncated` are the only additions to
  the refusal models that `resolve_taxon` needs; both are
  nullable/defaulted to keep existing call sites working.
- `Outcome` and `OutcomeAdapter` are untouched;
  `outcome.schema.json` regenerates with the additive fields only.
- Every new behavior has a test: `test_name_index.py`,
  `test_names_index.py`, `tests/contract/test_resolve_taxon.py`,
  `test_stale_artifact.py`, `test_pack_hash_validation.py`,
  `tests/perf/test_resolve_taxon_perf.py`.
- **Breaking:** `from_rows` / `_build` now require `dictionary=`,
  and `from_rows` defaults `verified=False`. The loader continues
  to pass `verified=True` after verifying `content_hash` or
  `artifact_sha256`.

## Completed

M8 is complete: M8-PR-1 (`resolve_taxon`), M8-PR-2 (`resolve_fact`),
M8-PR-3 (`meta` + `show`), plus follow-ups: the `Unknown.code`
registry (#98) and the `language` preference for `resolve_taxon`.
The policy is stable; a change requires a superseding ADR.
