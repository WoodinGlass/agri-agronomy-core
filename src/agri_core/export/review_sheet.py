"""Generate a review sheet (``review_sheet.csv``) and its manifest.

M16. See ADR-021 (planned) and ``docs/EXPORTS.md`` for the design.

Design summary:
- **One row per live fact.** Not "taxa x facts" cartesian product.
- **Read-only columns** carry what a reviewer needs to decide: fact value
  (pretty + JSON), unit, scope, evidence, status, safety class, tier,
  source citation / url / license, current reviewers.
- **Fill-in columns** are empty and clearly separated: reviewer_id,
  decision, corrected_value_json, comment, reviewed_on.
- **Deterministic**: same pack + dictionary + filters give byte-identical
  UTF-8 / LF output. No timestamps.
- **CSV injection defense**: any cell starting with ``= + - @``, tab,
  CR or LF is prefixed with a tab; the field is written quoted (see
  ``QUOTE_ALL``). The ingest side strips one leading tab, then rejects
  any remaining dangerous prefix.
- **Sidecar manifest**: ``review_sheet.manifest.json`` carries
  ``pack_hash`` + ``csv_sha256`` + ``sheet_schema_version`` + row count
  + filters, so an ingest step can verify it was generated against the
  same pack.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow, format_value
from agri_core.models.taxon import TaxonRow
from agri_core.pack import KnowledgeSet
from agri_core.pack.tiers import TierResult, derive_all_tiers

__all__ = [
    "SHEET_SCHEMA_VERSION",
    "ReviewSheetFilters",
    "generate_review_sheet",
    "write_review_sheet",
]

#: Independent SemVer for the review-sheet contract.
SHEET_SCHEMA_VERSION = "1.0.0"

#: Read-only columns. Populated from the pack.
READONLY_COLUMNS = (
    "fact_id",
    "taxon_id",
    "scientific_name",
    "parameter",
    "phase",
    "value_pretty",
    "value_json",
    "unit",
    "scope",
    "evidence",
    "status",
    "safety_class",
    "taxon_tier",
    "source_citation",
    "source_url",
    "source_license",
    "current_reviewed_by",
)

#: Fill-in columns. Empty in the generated sheet; filled by a reviewer.
FILLIN_COLUMNS = (
    "reviewer_id",
    "decision",
    "corrected_value_json",
    "comment",
    "reviewed_on",
)

ALL_COLUMNS = READONLY_COLUMNS + FILLIN_COLUMNS

_STATUS_ORDER = {"imported": 0, "draft": 1, "reviewed": 2, "approved": 3}
_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _sanitize_cell(value: str) -> str:
    """CSV injection defense: prefix dangerous cells with a tab.

    The tab prefix ensures the field is written quoted (see ``QUOTE_ALL``
    below) and that spreadsheet applications treat the cell as text. The
    ingest side strips one leading tab and rejects any remaining
    dangerous prefix, so the round trip is lossless for legitimate values.
    """
    if not value:
        return value
    if value[0] in _DANGEROUS_PREFIXES:
        return "\t" + value
    return value


def _as_cell(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return _sanitize_cell(value)


@dataclass(frozen=True)
class ReviewSheetFilters:
    """Filter options for a review sheet.

    ``max_status`` is inclusive: ``"reviewed"`` (the default) includes
    ``imported``, ``draft`` and ``reviewed`` facts, i.e. everything not
    yet ``approved``. That is what a reviewer typically wants: the facts
    that still need a decision.
    """

    max_status: str = "reviewed"
    tiers: tuple[str, ...] | None = None
    taxon_ids: tuple[str, ...] | None = None
    safety_critical_only: bool = False


def _value_json(fact: FactRow) -> str:
    payload = fact.value.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _scope_json(scope: dict[str, Any]) -> str:
    return json.dumps(scope, sort_keys=True, separators=(",", ":"))


def _value_unit(fact: FactRow) -> str:
    return getattr(fact.value, "unit", "") or ""


def _source_fields(ks: KnowledgeSet, fact: FactRow) -> tuple[str, str, str]:
    """Return ``(citation, url, license)`` for a fact's source(s)."""
    citations: list[str] = []
    urls: list[str] = []
    licenses: set[str] = set()

    if fact.src:
        for sid in fact.src:
            try:
                source = ks.source(sid)
            except KeyError:
                continue
            citations.append(source.citation)
            urls.append(source.url)
            licenses.add(source.license)
    elif fact.dataset_id:
        try:
            dataset = ks.dataset(fact.dataset_id)
        except KeyError:
            dataset = None
        if dataset is not None:
            citations.append(f"{dataset.name} {dataset.version}".strip())
            if dataset.url is not None:
                urls.append(dataset.url)
            licenses.add(dataset.license)

    return (
        "; ".join(citations),
        "; ".join(urls),
        "; ".join(sorted(licenses)),
    )


def _build_row(
    fact: FactRow,
    taxon: TaxonRow,
    tier: str,
    safety_class: str,
    ks: KnowledgeSet,
) -> dict[str, str]:
    citation, url, license_ = _source_fields(ks, fact)
    reviewed_by = "; ".join(fact.reviewed_by) if fact.reviewed_by else ""
    row: dict[str, str] = {
        "fact_id": _as_cell(fact.fact_id),
        "taxon_id": _as_cell(fact.taxon_id),
        "scientific_name": _as_cell(taxon.scientific_name),
        "parameter": _as_cell(fact.parameter),
        "phase": _as_cell(fact.phase or ""),
        "value_pretty": _as_cell(format_value(fact.value)),
        "value_json": _as_cell(_value_json(fact)),
        "unit": _as_cell(_value_unit(fact)),
        "scope": _as_cell(_scope_json(fact.scope)),
        "evidence": _as_cell(fact.evidence),
        "status": _as_cell(fact.status),
        "safety_class": _as_cell(safety_class),
        "taxon_tier": _as_cell(tier),
        "source_citation": _as_cell(citation),
        "source_url": _as_cell(url),
        "source_license": _as_cell(license_),
        "current_reviewed_by": _as_cell(reviewed_by),
    }
    for col in FILLIN_COLUMNS:
        row[col] = ""
    return row


def _should_include(
    fact: FactRow,
    tier: str,
    safety_class: str,
    filters: ReviewSheetFilters,
) -> bool:
    if fact.superseded_by is not None:
        return False

    max_idx = _STATUS_ORDER.get(filters.max_status, 2)
    fact_idx = _STATUS_ORDER.get(fact.status, -1)
    if fact_idx > max_idx:
        return False

    if filters.tiers is not None and tier not in filters.tiers:
        return False

    if filters.taxon_ids is not None and fact.taxon_id not in filters.taxon_ids:
        return False

    return not (filters.safety_critical_only and safety_class == "none")


def generate_review_sheet(
    ks: KnowledgeSet,
    dictionary: Dictionary,
    filters: ReviewSheetFilters,
) -> tuple[str, dict[str, Any]]:
    """Return ``(csv_text, manifest_dict)`` for a review sheet.

    Deterministic: same knowledge set, dictionary, and filters give
    byte-identical output (UTF-8, LF line endings, every cell quoted).
    """
    tier_by_taxon: dict[str, TierResult] = derive_all_tiers(ks, dictionary)
    taxa_by_id: dict[str, TaxonRow] = {t.taxon_id: t for t in ks.taxa()}

    included: list[tuple[FactRow, TaxonRow, str, str]] = []
    for fact in ks.facts():
        tier_res = tier_by_taxon.get(fact.taxon_id)
        tier = tier_res.tier.value if tier_res is not None else "T0"
        param = dictionary.parameters.get(fact.parameter)
        safety: str = param.safety_class if param is not None else "none"
        if not _should_include(fact, tier, safety, filters):
            continue
        taxon = taxa_by_id[fact.taxon_id]
        included.append((fact, taxon, tier, safety))

    included.sort(key=lambda item: (item[0].taxon_id, item[0].fact_id))

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(ALL_COLUMNS),
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )
    writer.writeheader()
    for fact, taxon, tier, safety in included:
        writer.writerow(_build_row(fact, taxon, tier, safety, ks))

    csv_text = buf.getvalue()
    csv_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()

    manifest: dict[str, Any] = {
        "sheet_schema_version": SHEET_SCHEMA_VERSION,
        "pack_name": ks.manifest.name,
        "pack_version": ks.manifest.version,
        "pack_hash": ks.pack_hash,
        "synthetic": ks.manifest.synthetic,
        "csv_sha256": csv_sha,
        "row_count": len(included),
        "filters": {
            "max_status": filters.max_status,
            "tiers": list(filters.tiers) if filters.tiers is not None else None,
            "taxon_ids": (list(filters.taxon_ids) if filters.taxon_ids is not None else None),
            "safety_critical_only": filters.safety_critical_only,
        },
    }
    return csv_text, manifest


def write_review_sheet(
    ks: KnowledgeSet,
    dictionary: Dictionary,
    out_dir: Path,
    filters: ReviewSheetFilters | None = None,
) -> tuple[Path, Path]:
    """Generate and write CSV + manifest. Returns ``(csv_path, manifest_path)``."""
    if filters is None:
        filters = ReviewSheetFilters()
    csv_text, manifest = generate_review_sheet(ks, dictionary, filters)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "review_sheet.csv"
    manifest_path = out_dir / "review_sheet.manifest.json"

    csv_path.write_bytes(csv_text.encode("utf-8"))
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return csv_path, manifest_path
