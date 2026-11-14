# ADR-020: Full RFC 8785 (JCS) canonical JSON

- **Status:** Accepted (2026-11-14)
- **Date:** 2026-11-14
- **Deciders:** WoodinGlass (maintainer)
- **Related:** ADR-002 (build and hash), ADR-004 (resolution policy),
  ADR-019 (native Rust kernel), ADR-021 (tool schemas)
- **Supersedes:** the RFC 8785 deferral in ADR-019 section P2
- **Superseded by:** none

## Context

ADR-019 section P2 recorded that Python's `canonical_json`
(`src/agri_core/models/canonical.py`) is **not** fully RFC 8785
compliant. It uses `json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` plus a `-0.0` to `0.0` normalization. The output
is byte-stable across Python versions and platforms, but it does not
match the RFC 8785/JCS canonical form in three places:

1. **Number serialization (RFC 8785 section 3.2.2.3).** Python's
   `json.dumps` serializes `1.0` as `"1.0"` and `1e-07` as `"1e-07"`.
   RFC 8785 requires ECMAScript `Number.prototype.toString()`:
   `1.0` to `"1"`, `1e-07` to `"1e-7"`, `1e21` to `"1e+21"`. The
   shortest-round-trip rule and the exponent format differ.
2. **Object key sorting (RFC 8785 section 3.2.3).** RFC 8785 sorts
   keys by UTF-16 code units. Python `sort_keys=True` sorts by Unicode
   code points. The two orders agree for BMP characters and differ for
   non-BMP characters that UTF-16 encodes as surrogate pairs.
3. **String escaping (RFC 8785 section 3.2.2.2).** Python
   `ensure_ascii=False` emits control characters as `\uXXXX` and
   leaves non-ASCII text as UTF-8. This matches the RFC's
   minimal-escaping intent; the current behavior is correct here.

Rust `crates/agri-kernel/src/canonical.rs` mirrors Python's behavior
for the M20 byte-identical guarantee and has the same three gaps.

`contract_hash` (dictionary bundle) and `content_hash` (pack) are both
SHA-256 over `canonical_json`. `request_id` is derived from a canonical
hash of the subject and the input. Changing the canonical form changes
all three, for every published dictionary and pack. This is a breaking
change.

ADR-019 section P2 deferred the migration to ADR-020 so that M20 could
ship byte-identical with Python rather than chase RFC 8785 mid-flight.
This is that migration plan.

## Decision

Adopt RFC 8785 (JCS) as the canonical JSON form for `contract_hash`,
`content_hash` and `request_id`. The migration has these parts.

1. **Canonical form.** Replace `canonical_json` with a full RFC 8785
   implementation on both the Python and the Rust side. Number
   serialization follows ECMAScript `Number.prototype.toString()`;
   object keys sort by UTF-16 code units; strings use minimal
   escaping.
2. **Dictionary bump.** `dictionary_version` 1.2.1 to **1.3.0**. The
   change is MINOR under `classify_change` because the keys, shapes,
   units and vocabularies are unchanged; only `contract_hash` moves.
   A new line is appended to `dictionary.lock` and a new snapshot
   `history/1.3.0.json` is added in the same commit.
3. **Pack re-tag.** Every published pack gets a new release with a new
   `content_hash`. Old releases stay online and immutable; new packs
   use the new hash. No migration of old packs is required for them to
   keep loading: the engine verifies the hash against the pack file,
   not against a hardcoded list.
4. **Request ID rotation.** `request_id` is derived from a canonical
   hash of the subject and the input. Request IDs recorded under the
   pre-RFC form will not reproduce under the RFC 8785 form. This is
   accepted. `request_id` is documented as deterministic for a given
   engine version and canonical form, not as a cross-version
   identifier.
5. **Engine minor release.** The migration ships as part of **M21**
   (`v0.1.7`), not as a standalone tag. M21 already needs the Rust
   canonical implementation for the pack kernel, so the Python and
   Rust rewrites ship together.
6. **Migration window.** `v0.1.6` and earlier use the pre-RFC form.
   `v0.1.7` and later use the RFC 8785 form. Packs released before
   `v0.1.7` are re-tagged with new `content_hash` on the `v0.1.7`
   release, so users on the new engine get the new packs. No
   dual-form loader is shipped.

## Consequences

### Positive

- The canonical form is specified by an external standard (RFC 8785)
  rather than by this project's incidental Python behavior.
- Any RFC 8785 implementation in any language produces the same
  bytes, which makes the "one implementation per behavior" rule
  verifiable against an external reference corpus.
- The `canonical.py` docstring's "NOT fully RFC 8785 compliant"
  caveat goes away.

### Negative

- Breaking change: every `contract_hash`, `content_hash` and
  `request_id` moves. Packs must be re-tagged.
- Test vectors that assert specific hashes must be regenerated:
  `tests/contract/test_dictionary_lock.py`,
  `tests/contract/test_dictionary_bundle.py`,
  `tests/contract/test_pack_hash.py` (KAT),
  `tests/unit/test_canonical_json.py`,
  `tests/vectors/canonical.json`, the sample pack `content_hash`,
  and `tests/contract/test_native_parity.py`.

### Neutral

- Two implementations (Python and Rust) still exist, but both can now
  be validated against an external RFC 8785 test corpus.

## Alternatives considered

1. **Keep the current form (Python `json.dumps` plus `-0.0`).**
   Rejected: the gaps are real, the current form is not a standard,
   and ADR-019 section P2 already recorded the migration as a
   follow-up.
2. **Use a third-party RFC 8785 library for Python.** Rejected: adds
   a runtime dependency that must be audited and pinned. The RFC is
   small enough to implement in roughly 200 lines.
3. **Migrate only the Python side, keep Rust byte-identical to the
   old form for M21.** Rejected: violates the "one implementation per
   behavior" rule and leaves the parity test with an unmaintainable
   split.
4. **Migrate only `contract_hash`, leave `content_hash` and
   `request_id` on the old form.** Rejected: all three use the same
   canonical JSON; a split form is a maintenance hazard with no
   upside.

## Open questions

- Whether to ship an RFC 8785 reference corpus
  (`tests/vectors/rfc8785/`) taken from the JCS spec examples, or to
  generate one from the Python implementation and cross-check against
  a Rust RFC 8785 crate. Recommended: external corpus first.
- Whether the migration window needs a dual-form loader (read old
  packs with old hash, write new packs with new hash). Recommended:
  no. The hash is verified against the pack file, not a global list,
  so old packs keep loading under the new engine.

## References

- RFC 8785, JSON Canonicalization Scheme (JCS).
- ADR-019 section P2 (the deferral this ADR supersedes).
- ADR-002 (two-hash model).
- ADR-004 section "resolution policy version" (SemVer for
  `RESOLUTION_POLICY_VERSION`).
- ADR-021 (tool schemas, which references ADR-020 as planned).
