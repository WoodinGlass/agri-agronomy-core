# Adding a taxon

This walkthrough adds one taxon to a source pack. Each `bash` block is a
runnable command; `tests/scenario/test_adding_a_taxon.py` executes these
blocks against a copy of the sample pack, with `<PACK>` and `<OUT>`
substituted for temporary paths. The prose steps (adding facts) are
manual and not exercised by the runner.

## 1. Scaffold a new taxon

Adds one row to `taxa.csv` and creates an empty `facts/<new_id>.csv`.
The new taxon id is printed to stdout.

```bash
agri-core pack scaffold --pack <PACK> --scientific-name "Foo bar" --archetype annual --use vegetable
```

## 2. Add at least one fact

Open `facts/<new_id>.csv` (the filename is the taxon id printed in step 1)
and add one row per fact. Minimum for T1 coverage is one live fact. Every
row needs:

- `fact_id` — unique, 11 characters (Crockford base32, `F` prefix)
- `taxon_id` — the id from step 1
- `parameter` — a key from [DICTIONARY.md](DICTIONARY.md)
- `phase` — empty for `phase_set: none`; otherwise a phase from the
  archetype's phase set
- `value` — JSON; the shape depends on the parameter (see
  [DICTIONARY.md](DICTIONARY.md) and
  [PACK_FORMAT.md](PACK_FORMAT.md#csv-codec))
- `scope` — JSON object; `{}` is wildcard
- `provenance_kind`, `src`, `locator`, `evidence`, `status`, `reviewed_by`,
  `reviewed_at`

Example row for a `gdd_base` scalar fact:

```csv
F00000009999,T000000099,gdd_base,,"{""shape"":""scalar"",""unit"":""degree_Celsius"",""value"":10.0}",{},curated,S001,Synthetic table,B,reviewed,alice,2026-01-01,
```

## 3. Build (and refresh the content hash)

Validates the pack, writes `pack.sqlite` into `<OUT>`, and rewrites
`content_hash` in `pack.toml` when the source has changed.

```bash
agri-core pack build --pack <PACK> --out <OUT> --update-source-hash
```

## 4. Verify

Re-validate the source pack. This re-checks the manifest, the sources
file, and the per-taxon facts, and will fail if the hash is stale.

```bash
agri-core validate --pack <PACK>
```

## Troubleshooting

- **`PACK_HASH_MISMATCH` on `agri-core pack lock`**: `pack lock` verifies
  the existing hash before rewriting it, so it refuses to re-lock a pack
  whose content changed. Use `agri-core pack build --update-source-hash`
  (step 3) instead; the built pack is written and the source hash is
  refreshed in the same call.
- **`PACK_HASH_MISMATCH` on `agri-core validate`**: the pack was edited
  after the last lock. Re-run step 3.
- **`PACK_FK_VIOLATION: fact.src Sxxx not in sources`**: the `src` column
  on a fact references a source id that is not in `sources.csv`. Add it
  there first.

## See also

- [DICTIONARY.md](DICTIONARY.md) — parameter keys, shapes, phases, safety classes
- [PACK_FORMAT.md](PACK_FORMAT.md) — CSV codec, fact fields, pack layout
- [RESOLUTION_POLICY.md](RESOLUTION_POLICY.md) — how a fact is resolved at query time
