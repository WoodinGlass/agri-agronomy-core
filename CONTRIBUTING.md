# Contributing

Thanks for considering a contribution. This project has two parts: the engine (this repository) and the data (`agri-knowledge`). Read the relevant section below before opening a pull request.


Contributions are welcome. Data contributions go to [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge); code contributions go here.

Data contributions (`agri-knowledge`):

- corrections to values, with a citation
- new facts with sources, evidence grades and an honest scope
- taxon aliases in other languages
- new taxa at any rank, with an honest `parent_id`

Code contributions (this repository):

- improvements to the pack loader, validator and diff
- new irrigation modes, calculation archetypes or parameter types, registered in the appropriate registry
- tests and golden vectors derived independently: a hand derivation from
  published equations, or the output of a permissively licensed
  implementation whose name and version are recorded

Rules:

1. **Facts and citations only.** Do not paste text, tables or figures from sources, and do not bulk-import datasets. Pull requests that do will be declined.
2. **Every new fact needs** a `src` (added to `sources.csv` with URL, license, `commercial_use` and access date), an `evidence` grade, a `scope`, and a status. Imported facts start at `imported`; entered facts start at `draft`.
3. **Unknown stays unknown.** If no reliable source exists, write the fact with `unknown: true` and a reason.
4. **Everything is in English:** code, schema keys, identifiers and documentation. Local-language taxon names go in `names.csv`.
5. **Code changes need tests.** Changes under `safety/` also need 100% coverage, a maintainer review and, for safety-critical parameters, a second independent review.
6. **Licensing.** By submitting a contribution you confirm that you have the right to contribute it and that it is licensed under the same terms as the files it changes.
7. **Protected species need a documented pathway.** Before proposing a taxon
   listed on CITES (any appendix) or protected under a national regulation
   such as Permen LHK 106/2018, cite the lawful cultivation pathway (an
   artificial-propagation exemption, a cultivated variety, or equivalent).
   Wild-collected material is not accepted. Conservation status from
   restricted databases is not used as an input. A maintainer decision
   may only ADD an exclusion, never justify the inclusion of a taxon that
   would otherwise be protected; per-taxon decisions are recorded in
   `docs/design/`, not in `CHANGELOG.md`.

Domain experts can review through `review_sheet.csv` without a GitHub account, and the maintainer records the outcome. Code owners are listed in `.github/CODEOWNERS`.


## Data source license policy

Every source in a pack's `sources.csv` must have `commercial_use=yes`
(`unclear` counts as `no`) and a license on the allowlist below.
`datasets.csv` uses a narrower allowlist: `LicenseRef-PublicDomain` is
not supported for datasets in 0.1.2 because the dataset row has no
`citation` column to record the required `basis:` prefix.

A dual-license source is recorded as the single license the pack relies
on; composite SPDX expressions (`AND`, `OR`, `WITH`, `+`) are rejected.
CC BY 4.0 is preferred over CC BY 3.0 for datasets: CC BY 3.0 unported
does not explicitly cover database rights, while 4.0 does.

The allowlist (exact-match SPDX canonical identifiers):

- CC0-1.0, CC-BY-3.0, CC-BY-4.0
- MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0
- `LicenseRef-PublicDomain` (sources only; requires a `citation`
  beginning with `basis:`)

See `docs/decisions/ADR-005-license-allowlist.md`.
