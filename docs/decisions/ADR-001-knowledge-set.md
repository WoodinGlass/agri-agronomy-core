# ADR-001: KnowledgeSet is a Protocol

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** agri-agronomy-core maintainers
- **Related:** M5-2b, M6 (SQLite backend)

## Context

The engine loads a pack directory into an immutable view that calculations
read. Two constraints pull in opposite directions:

1. **Determinism and immutability.** A calculation must return the same
   answer for the same inputs, regardless of how many times it runs or
   who calls it. Mutable state inside the loader would break this.
2. **Scale.** A real pack (`agri-knowledge`) may hold tens to hundreds
   of thousands of facts. Eager Pydantic validation of every row into a
   Pydantic object costs memory and time. Measured informally: 10 000
   taxa with their facts are on the order of hundreds of MB as Pydantic
   objects, against a README budget of <= 200 MB.

M6 will add a built SQLite pack: the same data, opened read-only with
`trusted_schema=OFF`. Resolvers in M8 must work against both.

## Decision

`KnowledgeSet` is a **Protocol** in `agri_core.pack.knowledge_set`, not a
base class. It defines a read-only surface:

- properties: `manifest`, `pack_hash`, `dictionary_version`, `verified`
- per-item lookups: `taxon`, `source`, `dataset`
- iterators: `taxa`, `facts`, `names`, `hazards` (sorted by primary key)
- per-taxon helpers: `facts_for`, `names_for`, `hazards_for` (return
  empty tuples when the taxon is known but has no attached rows; raise
  `KeyError` when the taxon is unknown)

**`InMemoryKnowledgeSet`** (M5) implements the Protocol for the directory
form. It builds all indices eagerly at load, wraps them in
`MappingProxyType`, stores row collections as tuples, and is frozen.

**The SQLite-backed implementation** (M6) will implement the same
Protocol without eager Pydantic row materialization.

Resolvers (M8) depend **only** on the Protocol, never on a concrete class.

`_conforms(ks: InMemoryKnowledgeSet) -> KnowledgeSet` lives at module
scope so mypy strict verifies structural conformance at CI. It is never
called at runtime.

## Consequences

**Positive**

- Resolvers are decoupled from the storage strategy. M6 can swap in
  SQLite without touching M8.
- The public surface is *read methods*, not exposed tuples or dicts.
  No caller iterates `ks.taxa_by_id`. This keeps implementations free to
  index differently (hash map, B-tree, cursor).
- Protocol is not a base class: no inheritance, no `__init_subclass__`,
  no MRO coupling. `InMemoryKnowledgeSet` remains a plain frozen
  dataclass with `init=False`.

**Negative**

- Protocol conformance is checked at CI time via `_conforms`, not at
  instantiation. A new implementation must remember to add the same
  `_conforms` helper (or be reviewed against the Protocol manually).
- Eager build of `InMemoryKnowledgeSet` is not lazy. For very large
  packs this may be the wrong choice; that is why the SQLite backend
  exists at M6.
- Dropping `@dataclass(slots=True)` on Python 3.10/3.11 avoids a known
  `frozen + slots + init=False` bug that turns `FrozenInstanceError`
  into `TypeError` on assignment. The cost is about 150 bytes per
  instance; with exactly one KnowledgeSet per loaded pack this is
  negligible.

## Alternatives considered

**Lazy `InMemoryKnowledgeSet`.** Read CSV on first access. Rejected: it
makes the "immutable" guarantee conditional on filesystem state, and it
couples every read to the loader's I/O code.

**Concrete base class instead of Protocol.** Rejected: `agri_core.models`
is a pure-Pydantic contract layer. A base class would drag methods
(non-Pydantic) into that layer and force subclasses to inherit state
they do not need.

**SQLite-first.** Rejected for M5: a built SQLite pack is M6 work, and
the directory form is still useful for pack authors. Two implementations
behind one Protocol lets both exist.

**Expose tuples as attributes (`ks.taxa`, `ks.facts`).** Rejected:
collides with the iterator methods, forces a distinction between
"attribute view" and "method view", and pushes memory-shape decisions
onto callers.
