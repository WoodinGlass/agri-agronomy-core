# ADR-011: Append-only taxon ID ledger (ids.lock)

## Status

Proposed 2026-11-04. Required from this release onward.

## Context

ADR-002 states "taxon IDs are never reused". `diff` reports
`taxon_removed` when a taxon disappears, but that is advisory: after
removal, nothing prevents a later `scaffold` from regenerating the
same opaque ID, because `_generate_taxon_id` only knows about the
current `taxa.csv`.

Three concrete failure modes:

1. Remove taxon B from `taxa.csv`, then scaffold a new taxon. The
   generator picks a random ID from the Crockford space; by
   construction a removed ID is now available.
2. A manual `taxa.csv` edit that assigns an ID from another pack or
   another branch. No check catches this until downstream consumers
   start cross-referencing.
3. Remove taxon B from both `taxa.csv` and any record of it. Once
   gone, no on-disk artifact remembers the ID ever existed.

## Decision

1. **`ids.lock`** at the pack root. **Format:** one taxon ID per line,
   sorted ascending, UTF-8, LF endings, no header. It is a **set**,
   not a history — contrast `dictionary.lock`, which is a per-release
   history (`<version> <hash>`). Different role, different format.

2. **Required from this release onward.** `agri-core validate` raises
   `PACK_ID_LEDGER_ABSENT` when the file is missing. Migration for
   older packs: `agri-core pack scaffold` (auto-bootstraps from
   current `taxa.csv` before appending), or `sort taxa.csv > ids.lock`
   manually.

3. **Append-only.** Only `scaffold` writes the file. A taxon removal
   leaves its ID in `ids.lock` permanently. `scaffold` generates new
   IDs against `taxa.csv ∪ ids.lock`, so a previously-removed ID is
   never regenerated.

4. **Validation: one direction.** `check_id_ledger_drift` emits
   `PACK_ID_LEDGER_DRIFT` for every `taxa.csv` ID **missing from**
   `ids.lock`. The reverse (ID in lock, not in taxa) is **not** a
   violation — that ID is a reserved historical slot.

5. **Diff: no removal from ledger.** `diff` gains a new violation
   kind `id_removed_from_ledger`, emitted when an ID is in `old`'s
   lock but not in `new`'s. Complementary to `taxon_removed`; the two
   fire independently. `KnowledgeSet.ids_lock()` returns `None` for
   built packs (ledger is a source artifact, not a SQLite table), so
   diff of two built packs skips this check.

6. **Content hash covers the file.** `ids.lock` is on the pack root
   allowlist and participates in `content_hash`. Adding an ID changes
   the hash (expected). The sample pack's KAT
   (`tests/contract/test_sample_pack.py`) is updated in the same PR.

7. **No `schema_version` bump.** `ids.lock` is additive: a pack with
   `schema_version = 1` and `ids.lock` is valid; the requirement is
   enforced by `validate`, not by `schema_version`. Older packs
   migrate via bootstrap.

## Consequences

- One more required file per source pack. A manual `taxa.csv` edit
  that skips `ids.lock` fails `validate` with a clear code.
- `scaffold` writes `taxa.csv`, `facts/<id>.csv`, and `ids.lock`
  atomically per file. The bootstrap path validates with an in-memory
  lock first so a broken pack is not mutated.
- Sample pack's `content_hash` changes; the KAT updates in the same PR.
- `diff` gains a new kind; tests for it are in the same PR.
- On Windows, `os.replace` is atomic only within a filesystem; the
  three replaces are not a single transaction. A crash between them
  could leave `taxa.csv` written but `ids.lock` stale; `validate`
  catches this state (drift).

## Follow-up

- **Fact IDs** stay out of scope. Fact IDs are per-taxon and cannot be
  reused across taxa; a fact-level ledger would be a separate ADR if
  ever needed.
- **`agri-knowledge` K0** must include `ids.lock` before shipping
  data. Bootstrap covers the first taxon.

## References

- ADR-002 (two-hash model; "taxon IDs are never reused")
- ADR-003 (tiers, license, duplicates)
- `src/agri_core/pack/scaffold.py`, `validate.py`, `diff.py`, `files.py`
