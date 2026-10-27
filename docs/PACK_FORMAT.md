# Pack format

A pack is a directory that holds a manifest (`pack.toml`) and a set of
CSV tables. The engine reads it exactly once at load into an immutable
`KnowledgeSet` (see `docs/decisions/ADR-001-knowledge-set.md`). A pack
is data, not code.

This document is the reference for the format. It is authoritative for
what `read_pack_bytes`, `load_knowledge_set`, and `agri-core pack lock`
accept.

## Allowlist

Only the following files are read. Everything else at the pack root is
ignored (not read, not hashed, not size-accounted).

| File | Required | Notes |
|---|---|---|
| `pack.toml` | yes | manifest |
| `taxa.csv` | yes | at least a header row |
| `names.csv` | yes | |
| `hazards.csv` | yes | |
| `datasets.csv` | yes | |
| `sources.csv` | yes | |
| `advisories.csv` | no | fail-closed; content non-empty -> `PACK_FEATURE_UNSUPPORTED` |
| `facts/<taxon_id>.csv` | no | one file per taxon; filename must equal the row's `taxon_id` |

**Rejected** (not ignored):

- Symlinks anywhere inside the pack (files and directories).
- Non-regular files (FIFOs, devices, sockets).
- A `facts/` entry that is not a `.csv` file, or whose stem does not
  match `^T[0-9A-HJKMNP-TV-Z]{9}$`.

## `pack.toml`

Required fields, in the order `agri-core pack lock` writes them:

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string, `^[a-z][a-z0-9_-]{0,63}$` | yes | pack name (not a taxon name) |
| `version` | `X.Y.Z` | yes | SemVer, exactly three components |
| `schema_version` | integer >= 1 | yes | currently `1` |
| `engine_min` | `X.Y.Z` | yes | minimum engine version |
| `dictionary_min` | `X.Y.Z` | yes | minimum dictionary; MAJOR must match the running dictionary's MAJOR |
| `synthetic` | boolean | no, default `false` | requires `allow_synthetic=True` at load |
| `content_hash` | `sha256:<64 lowercase hex>` | no | verified when present; absent means unverified |

Example:

```toml
name = "agri-knowledge"
version = "2026.10.0"
schema_version = 1
engine_min = "0.1.0"
dictionary_min = "1.0.0"
synthetic = false
content_hash = "sha256:..."
```

Comments and arbitrary key order in a hand-edited file are tolerated at
read time, but `agri-core pack lock` rewrites `pack.toml` with the fixed
key order above and drops comments. See "Regenerating content_hash".

## Content hash

The hash pins the pack contents. Algorithm, P1:

```
h = sha256(b"agri-pack-hash-v1\n")
for relpath in sorted(files):
    content = normalize(relpath, files[relpath])
    h.update(sha256(content).hexdigest() + "  " + relpath + "\n")
return "sha256:" + h.hexdigest()
```

- `files` is the allowlist set above.
- `relpath` uses POSIX `/` regardless of the host OS.
- `normalize()` is:
  - for `pack.toml`: parse TOML, drop `content_hash`, encode via
    canonical JSON (sorted keys, compact separators, UTF-8). Comments
    and key order therefore do not affect the hash.
  - for every other file: raw bytes with CRLF and bare CR normalized
    to LF. Nothing else is changed.

The `agri-pack-hash-v1\n` prefix is domain separation: a future v2
algorithm changes the prefix as well as the rule.

## Regenerating `content_hash`

Use the CLI, never a hand-edit:

```
agri-core pack lock --pack PATH
```

Behavior:

- Reads the pack via the allowlist, validates it structurally (same
  checks as `agri-core validate`), then recomputes the hash from the
  bytes it is about to write.
- Rewrites `pack.toml` atomically via `pack.toml.tmp` + `os.replace`.
  On any error the tmp file is removed and `pack.toml` is unchanged.
- Fixed key order as in the table above; comments are not preserved.
- Idempotent: a second run writes identical bytes.
- Rejects keyword `sample` with exit code 2 -- pass an explicit path.
- Exits 3 on any structural error (nothing is written).

`content_hash` is optional until the M6 build pipeline lands. When it is
absent, `verify_pack_hash_full()` returns `verified=False`; the CLI
prints `PACK_UNVERIFIED` on stderr but still loads.

## Load order

`load_knowledge_set(path)` and `load_knowledge_set_from_files(files)`
follow this order. First failure wins; structural findings are collected
up to 20 before raising.

1. **Size check.** Sum of allowlist files must not exceed
   `DEFAULT_MAX_BYTES = 100 MiB`. Enforced during read, not by a prior
   `stat` walk; a file that grows mid-read triggers `PACK_TOO_LARGE`.
2. **Read allowlist once.** Every file is read exactly once; symlinks
   and non-regular files rejected here.
3. **Hash.** Compute per the section above. If `pack.toml` declares
   `content_hash` and it does not match, raise `PACK_HASH_MISMATCH`.
   A caller-supplied `expected_hash` has the same effect.
4. **Manifest compatibility.** `schema_version` supported; engine at or
   above `engine_min`; running dictionary at or above `dictionary_min`
   with the same MAJOR. Violations raise `PACK_SCHEMA_UNSUPPORTED`,
   `PACK_ENGINE_TOO_OLD`, `PACK_DICTIONARY_INCOMPATIBLE`.
5. **Synthetic gate.** `synthetic = true` requires
   `allow_synthetic=True`; otherwise `PACK_SYNTHETIC_NOT_ALLOWED`.
6. **Advisories fail-closed.** `advisories.csv` present and its content
   is not whitespace-only -> `PACK_FEATURE_UNSUPPORTED`.
7. **Parse tables.** Strict CSV parse per table (see "CSV codec").
8. **Structural validation.** Per-row Pydantic, then cross-row checks
   (see "Validation").

## CSV codec

- **Encoding:** UTF-8, no BOM. Invalid UTF-8 -> `PACK_TABLE_INVALID`.
- **Line endings:** LF written; LF or CRLF accepted on read; bare CR
  rejected.
- **Header:** exact column list from the table schema, same order.
  Mismatch -> `PACK_TABLE_INVALID`.
- **Cell content:**
  - No NUL bytes.
  - No control characters except tab (U+0009). U+007F rejected.
  - No multi-line cells.
- **Empty cell semantics:**
  - nullable column -> `null`
  - non-nullable `list_str` -> `[]`
  - any other non-nullable column -> `PACK_TABLE_INVALID`
- **`list_str` cells:** `|`-joined. Writer sorts items. Reader accepts
  any order but rejects empty items, items containing `|`, and
  duplicates if the model forbids them. Writer rejects `[]` on a
  nullable `list_str` column (use `null` instead) so round-trips are
  lossless.
- **`json` and `dict_str_str` cells:** canonical JSON (sorted keys,
  compact separators). Duplicate JSON keys and non-finite numbers
  (`NaN`, `Infinity`) rejected -> `PACK_TABLE_INVALID`.

## Tables

Column list and PK for each table. Column order is exact.

### `taxa.csv`

| Column | Type | Nullable | PK |
|---|---|---|---|
| `taxon_id` | `TaxonId` | no | yes |
| `rank` | enum `species`/`hybrid`/`cultivar_group`/`genus` | no | |
| `scientific_name` | str | no | |
| `accepted_name` | str | yes | |
| `organism_group` | str (vocab) | no | |
| `archetype` | str (vocab) | no | |
| `uses` | list_str | no, min 1 | |
| `traits` | list_str | no | |
| `parent_id` | `TaxonId` | yes | |
| `external_ids` | dict_str_str | yes | |
| `src` | list_str | yes | |
| `dataset_id` | `DatasetId` | yes | |

### `names.csv`

| Column | Type | Nullable | PK |
|---|---|---|---|
| `taxon_id` | `TaxonId` | no | yes (composite) |
| `name` | str | no | yes (composite) |
| `language` | BCP-47 subset | no | yes (composite) |
| `script` | ISO 15924 | no | yes (composite) |
| `kind` | enum `common`/`scientific`/`synonym`/`trade` | no | yes (composite) |
| `preferred` | bool | no | |
| `src` | list_str | yes | |
| `dataset_id` | `DatasetId` | yes | |

### `facts/<taxon_id>.csv`

| Column | Type | Nullable | PK |
|---|---|---|---|
| `fact_id` | `FactId` | no | yes |
| `taxon_id` | `TaxonId` | no | |
| `parameter` | str (core parameter) | no | |
| `phase` | str | yes | |
| `value` | json (discriminated `FactValue`) | no | |
| `scope` | json | no, default `{}` | |
| `provenance_kind` | enum `curated`/`imported`/`derived` | no | |
| `src` | list_str | yes | |
| `dataset_id` | `DatasetId` | yes | |
| `locator` | str | yes | |
| `evidence` | enum `A`/`B`/`C`/`D` | no | |
| `status` | enum `imported`/`draft`/`reviewed`/`approved` | no | |
| `reviewed_by` | str | yes | |
| `reviewed_at` | date | yes | |
| `superseded_by` | `FactId` | yes | |

### `hazards.csv`

| Column | Type | Nullable | PK |
|---|---|---|---|
| `taxon_id` | `TaxonId` | no | yes (composite) |
| `hazard_code` | str, snake_case | no | yes (composite) |
| `severity` | enum `info`/`warning`/`critical` | no | |
| `reason` | str | no | |
| `as_of` | date | no | |
| `authority` | str | no | |
| `src` | list_str | yes | |
| `dataset_id` | `DatasetId` | yes | |

### `datasets.csv`

| Column | Type | Nullable | PK |
|---|---|---|---|
| `dataset_id` | `DatasetId` | no | yes |
| `name` | str | no | |
| `version` | str | no | |
| `license` | SPDX-like / `LicenseRef-` / `unclear` | no | |
| `checksum` | `sha256:<64 hex>` | no | |
| `url` | http(s) | yes | |
| `locator` | str | yes | |
| `access_date` | date | no | |

At least one of `url` or `locator` must be set.

### `sources.csv`

| Column | Type | Nullable | PK |
|---|---|---|---|
| `id` | `SourceId` | no | yes |
| `url` | http(s) | no | |
| `license` | SPDX-like / `LicenseRef-` / `unclear` | no | |
| `commercial_use` | enum `yes`/`no`/`unclear` | no | |
| `access_date` | date | no | |
| `citation` | str | no | |

## `facts/<taxon_id>.csv`

One file per taxon. The filename stem must match the row's `taxon_id`
for every row in that file. A file for `T000000001` that contains a row
with `taxon_id = T000000002` raises `PACK_FK_VIOLATION` at load.

A taxon with no facts simply has no file.

## Dictionary compatibility

`dictionary_min` must:

- share the MAJOR component with the running dictionary's version, and
- be `<=` the running dictionary's version.

Otherwise `PACK_DICTIONARY_INCOMPATIBLE`. This is checked before any
fact is read.

## Validation

Structural checks that run at load (all collected up to 20 findings,
then raised as the first finding with `.findings` attached):

- primary key uniqueness per table
- foreign keys:
  - `names.taxon_id`, `facts.taxon_id`, `hazards.taxon_id` are in `taxa`
  - `taxa.parent_id`, when set, is a known taxon and not itself
  - `facts.superseded_by`, when set, is a known fact
  - `*.src[]` are in `sources`
  - `*.dataset_id`, when set, is in `datasets`
  - `facts/<taxon_id>.csv` rows all have that `taxon_id`
- per fact, against the dictionary:
  - `parameter` is a core parameter
  - `value.shape` matches `parameter.shape` (except `shape = unknown`)
  - `unit` matches `parameter.unit` (scalar/range/trapezoid only)
  - numeric values lie inside `parameter.physical_range`
  - `enum` value is in `parameter.enum_values`
  - `enum_set` values are all in the allowed set (from `enum_values`,
    or from `phases_by_archetype[taxon.archetype]` when
    `enum_source = phases:biological`)
  - `phase` is valid for `parameter.phase_set`
  - `scope` keys are a subset of `parameter.scope_keys`
  - `safety_class = dose_cap` requires `status` of `reviewed` or
    `approved`

A fact with `value.shape = unknown` skips every value-level check
(`unit`, `physical_range`, `enum`, `enum_set`); it is exempt by design.

M7 rules (run by `agri-core validate` after structural load):

- **Non-degenerate trapezoid.** A `trapezoid` fact must have
  `pts[0] < pts[-1]`. The model already enforces `a <= b <= c <= d`
  at load; this rule rejects collapsed trapezoids where all four
  points are equal (`abs_min == abs_max`), which have no
  suboptimal zone. Use `shape=scalar` instead. Code:
  `PACK_TRAPEZOID_DEGENERATE`.
- Range `min <= max` is enforced at load by `RangeValue._check_order`
  (`PACK_TABLE_INVALID`); there is no separate M7 rule for range.
- **`superseded_by` invariants.** FK existence is enforced at load
  (`PACK_FK_VIOLATION`). A fact cannot supersede itself
  (`PACK_SUPERSEDED_SELF`). Cycles in the chain are rejected
  (`PACK_SUPERSEDED_CYCLE`, one finding per cycle anchored at the
  smallest `fact_id`).
- **Fact key duplicates.** Two live facts with identical
  `(taxon_id, parameter, phase, canonical_scope)` and different
  `value` are rejected (`PACK_FACT_KEY_DUPLICATE`). Same key with
  same value across different `src` is corroboration, not a
  duplicate. Superseded facts are excluded.

Not yet validated (M7): `tier_required`, safety `toxicity_limit` and
`regulatory` semantics, license gate for `commercial_use`.

## Validation findings

Since M7-1, `agri-core validate` and `validate_pack_report` return a
`ValidationReport`: an ordered tuple of `Finding` values with stable
codes, a severity (`error` / `warning`), a message, and an optional
location.

Findings are data, not exceptions. A pack that cannot be *loaded*
(structural failure) still produces a report with `ok = false`, but
`knowledge_set` is `None`. A pack that loads but fails an M7 rule
produces a report with `ok = false` and a non-`None` `knowledge_set`.

Codes are grouped by source:

- `PACK_*` — engine validation (structural + rules). Full list in
  `## Error code reference`.
- `SRC###` — source-row and license-gate findings.

M7-2..M7-4 will append codes; each new code is listed here and in
`## Error code reference` in the same PR. `REPORT_VERSION` starts at
`1` and increments only on a breaking change to the Finding or
ValidationReport schema.

## Pack identity invariants

Fact IDs and taxon IDs are never reused. `agri-core diff` enforces
three invariants when comparing two packs:

- **Fact IDs are never removed.** A fact that is obsolete is marked
  with `superseded_by`, not deleted.
- **Taxon IDs are never removed** for the same reason.
- **Fact IDs are never reused for different content once reviewed.**
  If a fact's `value`, `scope`, `parameter`, `taxon_id`, or `phase`
  changes **and its OLD status was `reviewed` or `approved`**, the
  change must be a new `fact_id` with `superseded_by` on the old one.
  `draft` and `imported` facts may be edited in place; they are
  still under editorial control.

Acceptable in-place changes for an existing `fact_id`: `status`,
`evidence`, `reviewed_by`, `reviewed_at`, `locator`, `superseded_by`,
`src`, `dataset_id`, `provenance_kind`.

A change that violates an invariant is reported as `fact_id_reused`,
`fact_removed`, or `taxon_removed`. `agri-core diff` exits 1 for any
violation, regardless of `--exit-code`.

## Advisories

`advisories.csv` is reserved. Until M8, any non-whitespace content
triggers `PACK_FEATURE_UNSUPPORTED`. A header-only file or no file at
all is accepted.

## Error code reference

| Code | Meaning |
|---|---|
| `PACK_ERROR` | base class; never raised directly |
| `PACK_NOT_FOUND` | path does not exist |
| `PACK_INVALID` | directory is not a pack, or manifest is unparseable |
| `PACK_SCHEMA_UNSUPPORTED` | `schema_version` not supported |
| `PACK_ENGINE_TOO_OLD` | engine below `engine_min` |
| `PACK_TABLE_INVALID` | CSV parse error, header mismatch, cell content |
| `PACK_DUPLICATE_KEY` | duplicate primary key |
| `PACK_FK_VIOLATION` | foreign key broken |
| `PACK_UNKNOWN_PARAMETER` | fact refers to a non-core parameter |
| `PACK_SHAPE_MISMATCH` | fact shape differs from parameter shape |
| `PACK_PHASE_INVALID` | fact phase invalid for the parameter |
| `PACK_SCOPE_INVALID` | fact scope key not allowed for the parameter |
| `PACK_HASH_MISMATCH` | `content_hash` (manifest or caller) mismatch |
| `PACK_TOO_LARGE` | allowlist total above `max_bytes` |
| `PACK_FEATURE_UNSUPPORTED` | pack uses a feature not yet supported |
| `PACK_DICTIONARY_INCOMPATIBLE` | running dictionary below `dictionary_min` or MAJOR mismatch |
| `PACK_SYNTHETIC_NOT_ALLOWED` | `synthetic = true` without `allow_synthetic` |
| `PACK_VALUE_OUT_OF_RANGE` | numeric value outside `physical_range` |
| `PACK_ENUM_INVALID` | enum/enum_set value not allowed |
| `PACK_UNIT_MISMATCH` | fact unit differs from parameter unit |
| `PACK_SAFETY_VIOLATION` | `dose_cap` parameter not reviewed/approved |
| `PACK_TRAPEZOID_DEGENERATE` | trapezoid `pts[0] == pts[-1]`; use `scalar` |
| `PACK_SUPERSEDED_SELF` | `superseded_by` points to the fact itself |
| `PACK_SUPERSEDED_CYCLE` | cycle in `superseded_by` chain (anchor = min `fact_id`) |
| `PACK_FACT_KEY_DUPLICATE` | two live facts share `(taxon, parameter, phase, canonical_scope)` with different values |

## Size limit

`DEFAULT_MAX_BYTES = 100 MiB`, summed over the allowlist files only.
Enforced during read; a file that grows past the remaining budget
raises `PACK_TOO_LARGE`. Callers may pass `max_bytes=` to
`load_knowledge_set` to raise or lower the limit.

## Synthetic packs

`synthetic = true` marks a pack whose contents are fictional and only
useful for testing. Loading it requires `allow_synthetic=True`:

- `agri-core validate` and `agri-core lint-sources` always allow
  synthetic; they print `SYNTHETIC DATA` on stderr.
- `agri-core pack lock` always allows synthetic.
- Any future calculation command must require the caller to opt in
  explicitly.

## Built packs (SQLite)

A source pack can be compiled into a **built pack** — a single SQLite
file plus a manifest that pins both the source content and the artifact.
This is the format `agri-core pack build` produces, and the one
`load_knowledge_set(path)` loads when `path` contains `pack.sqlite` and
`pack.toml` (see "Load order"). See
`docs/decisions/ADR-002-build-and-hash.md` for the rationale.

### Layout

```text
<pack>/
├─ pack.sqlite    # the built artifact
└─ pack.toml      # manifest with build-only fields
```

`taxa.csv` and friends are **not** present in a built pack. Having both
`pack.sqlite` and `taxa.csv` in the same directory raises
`PACK_INVALID` (`_detect_pack_kind`).

### SQLite schema

The artifact is a normal SQLite database with six data tables plus a
`metadata` table, all `WITHOUT ROWID`:

| Table | Primary key | Notes |
|---|---|---|
| `taxa` | `taxon_id` | |
| `names` | `(taxon_id, name, language, script, kind)` | |
| `facts` | `fact_id` | |
| `hazards` | `(taxon_id, hazard_code)` | |
| `datasets` | `dataset_id` | |
| `sources` | `id` | |
| `metadata` | `key` | 8 key/value rows; mirrors `pack.toml` (see below) |

Two indexes are created after bulk insert:
`idx_facts_taxon_param` on `facts(taxon_id, parameter)`, and
`idx_facts_parameter` on `facts(parameter)`.

The database is written with `PRAGMA page_size = 4096`,
`PRAGMA application_id = 0x61677269` ("agri"), and
`PRAGMA user_version = 1` (the built schema version, exposed in
`pack/sqlite_schema.py` as `SQLITE_SCHEMA_VERSION`).

The exact DDL is pinned by `DDL_SHA256` in `pack/sqlite_schema.py`;
changing the DDL requires bumping `SQLITE_SCHEMA_VERSION` **and**
updating the pin in `tests/contract/test_sqlite_build.py`. `WITHOUT
ROWID` is used for every table; the schema was benchmarked within 10%
of a rowid equivalent on the hottest query at 100k facts (ADR-002).

The writer requires SQLite >= 3.27 because `VACUUM INTO` is used to
produce a deterministic artifact. Loading a built pack does **not**
require that version.

### `pack.toml` (built)

A built manifest is a source manifest **plus** three all-or-none fields.
Source manifests must not declare them; loading a source pack whose
`pack.toml` carries any of these raises `PACK_INVALID`.

| Field | Type | Notes |
|---|---|---|
| `artifact_sha256` | `sha256:<64 hex>` | sha256 of the `pack.sqlite` bytes |
| `sqlite_schema_version` | integer >= 1 | currently `1`; must equal `PRAGMA user_version` |
| `built_by` | non-empty string | e.g. `agri-core 0.1.0` |

`content_hash` and `synthetic` are inherited from the source manifest
and keep their meaning: `content_hash` pins the source bytes that went
into the build, `synthetic` is a policy gate.

### Two-hash model

A built pack carries two independent hashes (ADR-002):

- **`content_hash`** — the hash from the source pack. It pins the
  semantic content. It is not recomputable from `pack.sqlite` alone:
  SQLite row encoding (pipe-joined lists, canonical JSON, ISO dates)
  differs from the CSV bytes and this layer does not reverse it.
- **`artifact_sha256`** — the sha256 of `pack.sqlite`. It pins the
  physical artifact and is recomputable from the file on disk without
  reading `pack.toml`.

`load_knowledge_set` on a built pack returns a `KnowledgeSet` whose
`pack_hash` is `content_hash` (for provenance consistency across source
and built packs) and whose `verified` is always `True`: built packs
cannot be unverified, because both hashes are mandatory.

### Built-pack load verification

`load_knowledge_set` on a built pack checks three layers before
returning a `KnowledgeSet`:

1. **Artifact integrity.** `artifact_sha256` from `pack.toml` must
   equal `sha256(pack.sqlite)` on disk. Mismatch raises
   `PACK_HASH_MISMATCH`.
2. **Schema version.** `PRAGMA user_version` in `pack.sqlite` must
   equal `manifest.sqlite_schema_version` and equal the running
   engine's `SQLITE_SCHEMA_VERSION`. Mismatch raises
   `PACK_SCHEMA_UNSUPPORTED`.
3. **Cross-store consistency.** The `metadata` table in `pack.sqlite`
   must contain eight rows (`name`, `version`, `schema_version`,
   `engine_min`, `dictionary_min`, `synthetic`, `content_hash`,
   `built_by`) whose values match the manifest fields. Mismatch
   raises `PACK_INVALID`.

Row values read back through Pydantic row models use the same SQLite
encoding the writer applied: `list_str` as `|`-joined sorted items,
`dict_str_str` and `json` as canonical JSON, `date` as ISO-8601,
`bool` as `0`/`1`. `pack/knowledge_set.py::_row_to_dict` is the single
place that knows this encoding.

## References

- `docs/decisions/ADR-001-knowledge-set.md` -- why `KnowledgeSet` is a
  Protocol and how M6 will implement it.
- `docs/REVIEW_GUIDE.md` -- evidence grades A/B/C/D and review checklist.
- `README.md` -- `Pack format` and `Data and provenance`.
- `docs/design/plant_wishlist_v4_rationale.md` -- protected-species
  policy.
