# Evidence review guide

**Status:** skeleton. Expanded at M9 alongside `PACK_FORMAT`, `DICTIONARY`,
`RESOLUTION_POLICY`, `SAFETY` and `ADDING_A_TAXON` (see `README.md` →
Milestones → M9).

## What this document is

`EvidenceGrade` is defined in `src/agri_core/models/notices.py` as one of
`A`, `B`, `C`, `D`. It is part of the public contract: every `Result`
carries the grades of the facts that fed it, and reviewers use the grade
to decide whether a value is safe to use.

This document defines **how maintainers assign each grade**. It is a
rubric, not a numeric score. It does not rank crops, judge sources or
replace a domain expert.

## The four grades

| Grade | Meaning | Typical source |
|---|---|---|
| `A` | Strongest. Direct empirical or official guidance. | Peer-reviewed field trial with replication; a national extension service publication; an official standards body (ISO, FAO, national ministry). |
| `B` | Strong but indirect. Expert consensus without a single authoritative source. | Reviewed agronomy handbook; widely adopted commercial growing guide from a recognised institution; extension service fact sheet for a neighbouring region. |
| `C` | Weak. Single-source, context-bound, or product-specific. | One field trial with no replication; a single producer's documented practice; a manufacturer datasheet for a specific product. |
| `D` | Weakest. Anecdotal. | Blog post, forum thread, personal communication, marketing copy, unsourced claim. |

Grades are attached to **individual facts**, not to sources. The same
source can produce an `A` fact for one parameter and a `C` fact for
another, because the source's confidence is not uniform across its
content.

## Minimum bar for `approved` facts

A fact marked `approved` in a pack that is intended for decisions
affecting real crops must:

1. Have evidence grade `A` or `B`.
2. Cite a source whose `commercial_use` field is `yes` **or** whose
   license already permits redistribution (CC0, CC BY, public domain,
   or a compatible permissive license).
3. Declare an honest scope (country, elevation, system, variety) that
   covers the caller's context, or leave the scope key empty on purpose
   as a wildcard.

Facts graded `C` or `D` are allowed in packs marked `reviewed` or
`draft`, and are intended for development, pilots with human oversight,
or internal review — never for production decisions.

## What this guide is not

- **Not legal advice.** It documents how evidence grades are assigned.
  It does not state which crops are legal to cultivate, transport or
  sell in any jurisdiction.
- **Not a licence gate.** License compatibility (CC BY-NC, ShareAlike,
  NoDerivatives) is checked separately during pack build (M7). See
  `README.md` → Data and provenance.
- **Not a protected-species policy.** The rules for CITES, Permen LHK
  106/2018 and the IUCN Red List live in
  `docs/design/plant_wishlist_v4_rationale.md`. A fact can have grade
  `A` and still describe a taxon that must not be included in a pack.
- **Not a substitute for a domain expert.** A reviewer assigns grades;
  a local agronomist or extension service decides whether a value is
  correct for a specific site.

## Related documents

- `README.md` → Data and provenance — license policy for sources.
- `docs/design/plant_wishlist_v4_rationale.md` — protected-species
  policy and per-taxon decisions.
- `src/agri_core/models/notices.py` — `EvidenceGrade` type and its
  contract-level definition.
- `src/agri_core/registry/sources.py` — source schema and lint rules
  used by `agri-core lint-sources`.

## Review checklist (short form)

For every fact proposed for `approved`:

- [ ] Grade is `A` or `B`, assigned by a reviewer, with reasoning in the
      commit message or the review sheet.
- [ ] Source is cited in `sources.csv`, with URL, license,
      `commercial_use`, access date and citation.
- [ ] Scope is honest: the fields filled match the source's actual
      context, and the fields left empty are empty on purpose.
- [ ] Units are canonical per `dictionary/unit_registry.yaml`.
- [ ] If the fact touches a species subject to CITES, Permen LHK
      106/2018 or IUCN CR/EN/VU, the pathway is documented in
      `docs/design/plant_wishlist_v4_rationale.md`.
## Tier derivation (T0–T3)

Tiers measure how complete and how reviewed a taxon's data is. They
are derived by `agri-core coverage` (and `pack.tiers.derive_tier`),
never declared in the pack. See ADR-003 for the design.

| Tier | Meaning | Reached when |
|---|---|---|
| **T0** | Identity only | Taxon in `taxa.csv`, no live facts |
| **T1** | Has data | >=1 live fact at any status (`imported`/`draft`/`reviewed`/`approved`) |
| **T2** | Reviewed core | All `tier_required=True` parameters at >= `reviewed` (weakest-link per fact); phase-bearing params require all phases; `unknown`-with-reason counts only at >= `reviewed` |
| **T3** | Approved + safety-checked | T2 + all `tier_required=True` params `approved` + every safety-critical fact `approved` with >=2 distinct reviewers |

**What T2/T3 do NOT certify**: parameters with `applies_to.systems`
(irrigation modes, media, fertilizer products scoped to a growing
system). These appear in `TierResult.system_gaps` and are shown by
`coverage`, but they never gate the tier. A T3 taxon can be missing
every irrigation fact — that is expected.

**Review checklist for a T3 promotion**:

1. Every `tier_required=True` parameter has a live `approved` fact.
2. Safety-critical facts (dose caps) are `approved` and have two
   distinct reviewers in `reviewed_by`.
3. No superseded fact holds the only copy of a required value.
4. `agri-core validate` exits 0; `agri-core coverage` shows T3.
