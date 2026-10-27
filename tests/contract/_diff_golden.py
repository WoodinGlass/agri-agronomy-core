"""Helpers for golden diff fixtures.

Not collected by pytest (leading underscore). Reused by
``tests/contract/test_diff_golden.py`` and ``scripts/gen_diff_golden.py``.

Each case builds two sample copies under a tmp dir, mutates one or both,
runs ``diff_packs``, and returns a payload with the two ``pack_hash``
values normalized so the fixture is stable across sample-pack maintenance.
"""

from __future__ import annotations

import csv
import io
import shutil
from collections.abc import Callable
from importlib.resources import files as pkg_files
from pathlib import Path
from typing import Any

from agri_core.pack import (
    TABLES,
    KnowledgeSet,
    diff_packs,
    load_knowledge_set,
    write_table,
)
from agri_core.pack.tables import read_table

__all__ = [
    "CASES",
    "add_fact_row",
    "build_case",
    "load",
    "mutate_fact_row",
    "remove_taxon_and_deps",
    "sample_copy",
]

_HASH_PLACEHOLDER_OLD = "<old_pack_hash>"
_HASH_PLACEHOLDER_NEW = "<new_pack_hash>"


def sample_copy(tmp_path: Path, name: str) -> Path:
    """Copy the synthetic sample pack; strip content_hash so mutations load."""
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    dst = tmp_path / name
    shutil.copytree(src, dst)
    toml = dst / "pack.toml"
    lines = [
        ln
        for ln in toml.read_text(encoding="utf-8").splitlines()
        if not ln.startswith("content_hash")
    ]
    toml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dst


def load(pack: Path) -> KnowledgeSet:
    return load_knowledge_set(pack, allow_synthetic=True)


def mutate_fact_row(pack: Path, taxon_file: str, fact_id: str, **changes: str) -> None:
    """Replace cells in the matching fact row (csv roundtrip, quoting-safe)."""
    fp = pack / "facts" / taxon_file
    text = fp.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    idx = {col: header.index(col) for col in changes}
    fid_idx = header.index("fact_id")
    for row in rows[1:]:
        if row[fid_idx] == fact_id:
            for col, val in changes.items():
                row[idx[col]] = val
            break
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    fp.write_text(buf.getvalue(), encoding="utf-8")


def add_fact_row(pack: Path, taxon_file: str, row: dict[str, str]) -> None:
    """Append a fact row; missing columns become empty."""
    fp = pack / "facts" / taxon_file
    text = fp.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    rows.append([row.get(col, "") for col in header])
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    fp.write_text(buf.getvalue(), encoding="utf-8")


def remove_taxon_and_deps(pack: Path, taxon_id: str) -> None:
    for fname, spec in [
        ("taxa.csv", TABLES["taxa"]),
        ("names.csv", TABLES["names"]),
        ("hazards.csv", TABLES["hazards"]),
    ]:
        p = pack / fname
        table = read_table(spec, p.read_bytes(), source_name=fname)
        rows = [dict(r) for r in table.rows if r["taxon_id"] != taxon_id]
        p.write_bytes(write_table(spec, rows))
    facts_file = pack / "facts" / f"{taxon_id}.csv"
    if facts_file.exists():
        facts_file.unlink()


# ---- Case mutators ---------------------------------------------------------


def _case_identical(_old: Path, _new: Path) -> None:
    pass


def _case_fact_added(_old: Path, new: Path) -> None:
    add_fact_row(
        new,
        "T000000001.csv",
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "phase": "",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":9.0}',
            "scope": "{}",
            "provenance_kind": "curated",
            "src": "S001",
            "locator": "x",
            "evidence": "A",
            "status": "approved",
            "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-01-01",
        },
    )


def _case_fact_value_changed_draft(old: Path, new: Path) -> None:
    for pack in (old, new):
        mutate_fact_row(pack, "T000000001.csv", "F00000000002", status="draft")
    mutate_fact_row(
        new,
        "T000000001.csv",
        "F00000000002",
        value='{"shape":"scalar","unit":"degree_Celsius","value":9.5}',
    )


def _case_fact_value_changed_reviewed(old: Path, new: Path) -> None:
    for pack in (old, new):
        mutate_fact_row(pack, "T000000001.csv", "F00000000002", status="reviewed")
    mutate_fact_row(
        new,
        "T000000001.csv",
        "F00000000002",
        value='{"shape":"scalar","unit":"degree_Celsius","value":9.5}',
    )


def _case_taxon_removed(_old: Path, new: Path) -> None:
    remove_taxon_and_deps(new, "T000000005")


CASES: dict[str, Callable[[Path, Path], None]] = {
    "identical": _case_identical,
    "fact_added": _case_fact_added,
    "fact_value_changed_draft": _case_fact_value_changed_draft,
    "fact_value_changed_reviewed": _case_fact_value_changed_reviewed,
    "taxon_removed": _case_taxon_removed,
}


def build_case(case_name: str, tmp_path: Path) -> dict[str, Any]:
    """Build a case, run ``diff_packs``, return normalized payload."""
    old = sample_copy(tmp_path, "old")
    new = sample_copy(tmp_path, "new")
    CASES[case_name](old, new)
    report = diff_packs(load(old), load(new))
    payload = report.model_dump(mode="json")
    payload["old_pack_hash"] = _HASH_PLACEHOLDER_OLD
    payload["new_pack_hash"] = _HASH_PLACEHOLDER_NEW
    return payload
