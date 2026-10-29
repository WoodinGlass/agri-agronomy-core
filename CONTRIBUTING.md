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
- tests and golden vectors from published worked examples or independent permissively licensed implementations

Rules:

1. **Facts and citations only.** Do not paste text, tables or figures from sources, and do not bulk-import datasets. Pull requests that do will be declined.
2. **Every new fact needs** a `src` (added to `sources.csv` with URL, license, `commercial_use` and access date), an `evidence` grade, a `scope`, and a status. Imported facts start at `imported`; entered facts start at `draft`.
3. **Unknown stays unknown.** If no reliable source exists, write the fact with `unknown: true` and a reason.
4. **Everything is in English:** code, schema keys, identifiers and documentation. Local-language taxon names go in `names.csv`.
5. **Code changes need tests.** Changes under `safety/` also need 100% coverage, a maintainer review and, for safety-critical parameters, a second independent review.
6. **Licensing.** By submitting a contribution you confirm that you have the right to contribute it and that it is licensed under the same terms as the files it changes.
7. **Protected species need a documented pathway.** Before proposing a taxon listed on CITES (any appendix), Permen LHK 106/2018 or the IUCN Red List at CR, EN or VU, cite the lawful cultivation pathway (an artificial-propagation exemption, a cultivated variety, or equivalent). Wild-collected material is not accepted.

Domain experts can review through `review_sheet.csv` without a GitHub account, and the maintainer records the outcome. Code owners are listed in `.github/CODEOWNERS`.
