# ADR-002: Two-hash model and deterministic SQLite build

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** agri-agronomy-core maintainers
- **Related:** M5 (pack hash), M6 (SQLite build), M7 (validate/diff)

## Context

M5 established `content_hash`: a portable sha256 over the canonical CSV
content of a pack directory (`hash_pack_files` in `pack/verify.py`),
stored in `pack.toml` and recorded in `Result.provenance.pack_hash`.

M6 adds `agri-core build`, which compiles a source pack directory into a
built pack: `pack.sqlite` + a superset `pack.toml`. Two distinct
integrity concerns appear:

1. **Semantic identity.** A given set of CSV tables should be the same
   pack no matter which backend reads it (directory or SQLite). If the
   reported hash changed depending on backend, downstream provenance
   records would fragment.
2. **File integrity.** The SQLite file is a binary artifact that can be
   corrupted or swapped. Its bytes must be verifiable on load.

One hash cannot serve both: a hash of `pack.sqlite` is not portable
across SQLite library versions, and a hash of the CSVs does not protect
the SQLite file.

## Decision

Two hashes, with distinct semantics:

- **`content_hash`** — M5 algorithm, unchanged. Computed over the
  canonical CSV content (`agri-pack-hash-v1` domain prefix, LF-normalized,
  pack.toml canonicalized as JSON with `content_hash` stripped). Stored
  in both source and built `pack.toml`. Portable across SQLite versions
  and host OSes. Recorded in `Result.provenance.pack_hash`.
- **`artifact_sha256`** — sha256 of `pack.sqlite` bytes. Present only in
  the built `pack.toml`. Not portable across SQLite library versions
  (the SQLite header records the writer's library version). Used for
  file-integrity checks.

On a **built pack**, `artifact_sha256` is the trust anchor: it pins the
exact SQLite file. `content_hash` is retained as the semantic identity
and is verified against the SQLite `metadata` table on load (see
"Consistency check" below).

On a **source pack** (no SQLite), `content_hash` is the sole trust
anchor, as in M5.

### `expected_hash` semantics

`load_knowledge_set(..., expected_hash=H)` compares `H` against the
anchor appropriate for the backend:

- Source (directory): `H == content_hash`.
- Built (SQLite): `H == artifact_sha256`. `content_hash` cannot be
  recomputed from SQLite (the CSVs are gone), so an `expected_hash`
  pointing at `content_hash` would always fail; the loader documents
  this and `pack lock` is the recommended way to pin a source pack.

### Consistency check on built-pack load

When loading a built pack, verify all three hold:

1. `pack.toml.artifact_sha256 == sha256(pack.sqlite)` (file integrity).
2. `pack.toml.content_hash == metadata.content_hash` (manifest/SQLite
   agreement).
3. `pack.toml` non-hash fields match `metadata` rows (name, version,
   schema_version, engine_min, dictionary_min, synthetic, built_by).

Failure of any of (1)–(3) raises `PackHashMismatchError` or
`PackTableInvalidError`, whichever matches the failure.

## DDL determinism

SQLite stores the text of every `CREATE` statement in `sqlite_master`
verbatim (minus the trailing `;`). Editing a comment inside the DDL
string therefore changes the artifact bytes.

- The DDL is a single string in `pack/sqlite_schema.py`, with no
  comments and no extraneous whitespace.
- `DDL_SHA256 = sha256(<all table + index DDL in fixed order>)` is
  computed at import.
- `tests/contract/test_sqlite_build.py` pins `DDL_SHA256` to a hardcoded
  value. Changing the DDL requires updating the pin and bumping
  `SQLITE_SCHEMA_VERSION` (`PRAGMA user_version`); the bump is what
  makes the change visible to older code paths.

## SQLite pragmas (fixed)

- `page_size = 4096`
- `application_id = 0x61677269` (ASCII `"agri"`)
- `user_version = SQLITE_SCHEMA_VERSION` (currently 1)

Indexes are created **after** the bulk insert for speed
(`idx_facts_taxon_param`, `idx_facts_parameter`). Table creation
precedes bulk insert.

Inserts are sorted by primary key before `executemany`, so page layout
is stable for a given SQLite version.

## WITHOUT ROWID — provisional

All tables currently use `WITHOUT ROWID`. A benchmark on 100 000
synthetic facts (SQLite 3.45.1, Colab) measured:

| Query | WITHOUT | WITH | Ratio (wo/w) |
|---|---|---|---|
| `taxon + parameter` p95 | 10.192 ms | 9.686 ms | **1.052** |
| `taxon` only p95 | 84.493 ms | 76.823 ms | 1.100 |

The hottest query (`taxon + parameter`, the shape of `facts_for`) is
within 10% of the rowid variant, so `WITHOUT ROWID` is kept. The
decision is provisional: if a future benchmark pushes the ratio above
1.10 or if `taxon`-only scans matter more than expected, migrating to
rowid tables is a v2 schema change (`user_version=2`) with its own ADR
update.

## Cross-version SQLite bytes

Byte-identical `pack.sqlite` **within a single SQLite library version**
is guaranteed by: fixed pragmas, sorted inserts, no timestamps, no
absolute paths, no hostname. `VACUUM INTO` produces a compacted,
deterministic file in that version.

Byte-identical **across SQLite library versions** is not guaranteed:
the SQLite file header records the writer's `SQLITE_VERSION_NUMBER`
(offset 96). The reproducibility gate is therefore intra-job: build
twice in the same job, with different `PYTHONHASHSEED`, `TZ`, `LANG`,
and source path, and compare bytes.

## Alternatives considered

- **Single `content_hash = sha256(pack.sqlite)`** — rejected: breaks
  provenance continuity for the same semantic pack, and is not portable
  across SQLite versions.
- **`NamedTemporaryFile(delete=False)` for `VACUUM INTO`** — rejected:
  the file handle stays open on Windows and prevents the subsequent
  read; also leaks the file on crash. `TemporaryDirectory` is used.
- **`Connection.serialize()` (Python ≥ 3.11)** — rejected: no
  `VACUUM` compaction, so the bytes are larger and less stable across
  minor SQLite changes.
- **`iterdump`** — rejected: row order depends on SQLite internals, not
  deterministic enough to pass a byte-equal gate.
- **Commit a golden `artifact_sha256`** — rejected: not portable across
  SQLite versions. Only `content_hash` is committed as a golden value.

## Consequences

- Consumers choose the hash by context: `content_hash` for semantic
  identity, `artifact_sha256` for file integrity.
- Adding a new build-time metadata field requires touching
  `PackManifest`, `metadata` SQLite rows, `dump_manifest` (implicitly),
  and the ADR decision table above.
- The DDL pin is friction by design: schema changes need explicit
  `SQLITE_SCHEMA_VERSION` bumps and pin updates in the test suite.
