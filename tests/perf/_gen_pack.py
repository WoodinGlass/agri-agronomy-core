"""Synthetic 10k-taxa pack generator for perf tests (M9 PR-B).

Workload (matches README Performance section):

- ``n_taxa`` taxa (default 10,000)
- 3 names per taxon (en common, id common, la scientific)
- 20 facts per taxon (every parameter with ``phase_set == "none"`` in
  ``dictionary/parameters.core.yaml``), so facts need no phase.

Total for 10k: 10,000 taxa, 30,000 names, 200,000 facts.

Fact values are taken from ``src/agri_core/_samples/sample_pack`` where
present, otherwise synthesized from ``physical_range`` (midpoint for
scalars, ``[min, 33%, 66%, max]`` for trapezoids, ``{min, max}`` for
ranges). Every fact carries ``locator``, ``src``, ``evidence`` and
``status="reviewed"`` so ``agri-core validate --strict`` passes.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from agri_core.models.dictionary import Dictionary
from agri_core.models.parameter import ParameterDef
from agri_core.pack import compute_pack_hash

_N_FACTS_PER_TAXON = 20
_N_NAMES_PER_TAXON = 3

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PACK = _REPO_ROOT / "src" / "agri_core" / "_samples" / "sample_pack"
_DICT_PATH = _REPO_ROOT / "dictionary" / "parameters.core.yaml"

_FACT_HEADER = (
    "fact_id",
    "taxon_id",
    "parameter",
    "phase",
    "value",
    "scope",
    "provenance_kind",
    "src",
    "dataset_id",
    "locator",
    "evidence",
    "status",
    "reviewed_by",
    "reviewed_at",
    "superseded_by",
)
_NAME_HEADER = (
    "taxon_id",
    "name",
    "language",
    "script",
    "kind",
    "preferred",
    "src",
    "dataset_id",
)
_TAXA_HEADER = (
    "taxon_id",
    "rank",
    "scientific_name",
    "accepted_name",
    "organism_group",
    "archetype",
    "uses",
    "traits",
    "parent_id",
    "external_ids",
    "src",
    "dataset_id",
)


def _fallback_value(pr: ParameterDef) -> str:
    # physical_range is ``tuple[float, float] | None`` (see ParameterDef),
    # not a Pydantic model; unpack directly.
    mn: float | None = None
    mx: float | None = None
    if pr.physical_range is not None:
        mn, mx = pr.physical_range
    shape = pr.shape
    if shape == "scalar":
        v = 1.0 if mn is None or mx is None else (mn + mx) / 2.0
        return json.dumps({"shape": "scalar", "unit": pr.unit, "value": v})
    if shape == "trapezoid":
        lo = mn if mn is not None else 0.0
        hi = mx if mx is not None else 1.0
        pts = [lo, lo + (hi - lo) * 0.33, lo + (hi - lo) * 0.66, hi]
        return json.dumps({"pts": pts, "shape": "trapezoid", "unit": pr.unit})
    if shape == "range":
        lo = mn if mn is not None else 0.0
        hi = mx if mx is not None else 1.0
        return json.dumps({"min": lo, "max": hi, "shape": "range", "unit": pr.unit})
    raise RuntimeError(f"shape {shape!r} not handled for parameter {pr.key!r}")


def _load_templates() -> list[dict[str, str]]:
    """Return 20 (parameter, value, scope, provenance, locator) templates."""
    dictionary = Dictionary.load(_DICT_PATH)
    phase_none = [k for k, p in dictionary.parameters.items() if p.phase_set == "none"]
    assert len(phase_none) == _N_FACTS_PER_TAXON, (
        f"expected {_N_FACTS_PER_TAXON} phase_set=none parameters in dictionary "
        f"v{dictionary.version}, got {len(phase_none)} — update _N_FACTS_PER_TAXON"
    )

    sample_values: dict[str, dict[str, str]] = {}
    for f in sorted((_SAMPLE_PACK / "facts").glob("*.csv")):
        with f.open() as fh:
            for row in csv.DictReader(fh):
                sample_values.setdefault(row["parameter"], row)

    templates: list[dict[str, str]] = []
    for p in phase_none:
        if p in sample_values:
            s = sample_values[p]
            templates.append(
                {
                    "parameter": p,
                    "value": s["value"],
                    "scope": s.get("scope") or "{}",
                    "provenance_kind": s.get("provenance_kind") or "curated",
                    "locator": s.get("locator") or f"Synthetic table for {p}",
                }
            )
        else:
            pr = dictionary.parameters[p]
            templates.append(
                {
                    "parameter": p,
                    "value": _fallback_value(pr),
                    "scope": "{}",
                    "provenance_kind": "curated",
                    "locator": f"Synthetic table for {p}",
                }
            )
    return templates


def generate_perf_pack(dest: Path, *, n_taxa: int = 10_000) -> Path:
    """Write a synthetic source pack at ``dest`` and lock it.

    Returns ``dest`` for chaining. The caller is expected to feed ``dest``
    to ``agri-core pack build`` for a built-pack test.
    """
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "facts").mkdir(exist_ok=True)

    (dest / "sources.csv").write_text(
        "id,url,license,commercial_use,access_date,citation\n"
        "S001,https://example.org/synthetic/s001,CC0-1.0,yes,2026-01-01,Synthetic A\n"
        "S002,https://example.org/synthetic/s002,CC0-1.0,yes,2026-01-01,Synthetic B\n"
        "S003,https://example.org/synthetic/s003,CC0-1.0,yes,2026-01-01,Synthetic C\n",
        encoding="utf-8",
    )
    (dest / "datasets.csv").write_text(
        "dataset_id,name,version,license,checksum,url,locator,access_date\n",
        encoding="utf-8",
    )
    (dest / "hazards.csv").write_text(
        "taxon_id,hazard_code,severity,reason,as_of,authority,src,dataset_id\n",
        encoding="utf-8",
    )

    with (dest / "taxa.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_TAXA_HEADER)
        w.writeheader()
        for i in range(1, n_taxa + 1):
            w.writerow(
                {
                    "taxon_id": f"T{i:09d}",
                    "rank": "species",
                    "scientific_name": f"Perfus{i}",
                    "accepted_name": "",
                    "organism_group": "vascular_plant",
                    "archetype": "annual",
                    "uses": "vegetable",
                    "traits": "",
                    "parent_id": "",
                    "external_ids": "",
                    "src": "S001",
                    "dataset_id": "",
                }
            )

    with (dest / "names.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_NAME_HEADER)
        w.writeheader()
        for i in range(1, n_taxa + 1):
            tid = f"T{i:09d}"
            w.writerow(
                {
                    "taxon_id": tid,
                    "name": f"Test plant {i}",
                    "language": "en",
                    "script": "Latn",
                    "kind": "common",
                    "preferred": "false",
                    "src": "S001",
                    "dataset_id": "",
                }
            )
            w.writerow(
                {
                    "taxon_id": tid,
                    "name": f"Tanaman {i}",
                    "language": "id",
                    "script": "Latn",
                    "kind": "common",
                    "preferred": "false",
                    "src": "S001",
                    "dataset_id": "",
                }
            )
            w.writerow(
                {
                    "taxon_id": tid,
                    "name": f"Perfus{i}",
                    "language": "la",
                    "script": "Latn",
                    "kind": "scientific",
                    "preferred": "true",
                    "src": "S001",
                    "dataset_id": "",
                }
            )

    templates = _load_templates()
    for i in range(1, n_taxa + 1):
        tid = f"T{i:09d}"
        with (dest / "facts" / f"{tid}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_FACT_HEADER)
            w.writeheader()
            for j, tpl in enumerate(templates):
                w.writerow(
                    {
                        "fact_id": f"F{(i * 100 + j):011d}",
                        "taxon_id": tid,
                        "parameter": tpl["parameter"],
                        "phase": "",
                        "value": tpl["value"],
                        "scope": tpl["scope"],
                        "provenance_kind": tpl["provenance_kind"],
                        "src": "S001",
                        "dataset_id": "",
                        "locator": tpl["locator"],
                        "evidence": "B",
                        "status": "reviewed",
                        "reviewed_by": "perf-gen",
                        "reviewed_at": "2026-01-01",
                        "superseded_by": "",
                    }
                )

    # Write pack.toml with placeholder, compute hash, rewrite with real hash.
    (dest / "pack.toml").write_text(
        f'name = "perf-pack-{n_taxa}"\n'
        'version = "1.0.0"\n'
        "schema_version = 1\n"
        'engine_min = "0.0.0"\n'
        'dictionary_min = "1.0.0"\n'
        "synthetic = true\n"
        'content_hash = "sha256:' + "0" * 64 + '"\n',
        encoding="utf-8",
    )
    new_hash = compute_pack_hash(dest)
    text = (dest / "pack.toml").read_text(encoding="utf-8")
    (dest / "pack.toml").write_text(
        re.sub(r'content_hash = "sha256:[0-9a-f]+"', f'content_hash = "{new_hash}"', text),
        encoding="utf-8",
    )
    return dest
