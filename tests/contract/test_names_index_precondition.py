"""Stop-loss precondition: name index built from raw rows, at runtime only.

ADR-019 section 11.5 and section 11.7 require the index to be built
eagerly at load time from the same TaxonRow / NameRow rows the set
holds, so flipping normalize + name_index back to Python (stop-loss)
can never see a half-native / half-Python state. This test locks three
invariants:

1. Load does not persist any index on disk.
2. Two independent loads of the same built pack give the same answers
   (no ambient state, no module-level cache).
3. The index reflects the raw names rows: mutating a name and rebuilding
   changes the answer accordingly.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pytest

from agri_core.pack import load_knowledge_set, read_pack_bytes
from agri_core.pack.build import strip_content_hash
from agri_core.pack.sqlite_schema import write_built_pack

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"


def _build_sample(tmp_path: Path) -> Path:
    files = read_pack_bytes(_SRC)
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    return out


def _entry_signature(e: Any) -> tuple[Any, ...]:
    if isinstance(e, dict):
        return (
            e.get("taxon_id"),
            e.get("name"),
            e.get("normalized_name"),
            e.get("language"),
            str(e.get("kind")),
            bool(e.get("preferred")),
            str(e.get("matched_via")),
            str(e.get("rank")),
            e.get("scientific_name"),
        )
    return (
        e.taxon_id,
        e.name,
        e.normalized_name,
        e.language,
        str(e.kind),
        bool(e.preferred),
        str(e.matched_via),
        str(e.rank),
        e.scientific_name,
    )


def test_load_does_not_persist_index(tmp_path: Path) -> None:
    """No new file appears under the built pack dir after loading + querying."""
    built = _build_sample(tmp_path)
    before = sorted(p.name for p in built.iterdir())
    ks = load_knowledge_set(built, allow_synthetic=True)
    for t in list(ks.taxa())[:3]:
        ks.names_index(t.scientific_name)
    after = sorted(p.name for p in built.iterdir())
    added = sorted(set(after) - set(before))
    assert before == after, "load created files: " + repr(added)


def test_two_loads_agree(tmp_path: Path) -> None:
    """Two independent loads give the same index answers (no ambient cache)."""
    built = _build_sample(tmp_path)
    k1 = load_knowledge_set(built, allow_synthetic=True)
    k2 = load_knowledge_set(built, allow_synthetic=True)
    for t in list(k1.taxa())[:5]:
        q = t.scientific_name
        a = [_entry_signature(e) for e in k1.names_index(q)]
        b = [_entry_signature(e) for e in k2.names_index(q)]
        assert a == b, "nondeterministic index for " + repr(q)


def test_index_reflects_mutated_names_row(tmp_path: Path) -> None:
    """Mutate a names.csv row, rebuild, reload: index reflects the change.

    Proves the index derives from raw rows, not from a cached or stored
    artifact. content_hash covers names.csv, so it is stripped before
    rebuilding.
    """
    files = dict(read_pack_bytes(_SRC))
    reader = csv.reader(io.StringIO(files["names.csv"].decode("utf-8")))
    rows = list(reader)
    assert len(rows) >= 2, "sample names.csv must have a header and one row"
    header = rows[0]
    body = [list(r) for r in rows[1:]]
    alias = "Syntheticus preconditions"
    body[0][1] = alias
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows([header, *body])
    files["names.csv"] = buf.getvalue().encode("utf-8")
    files["pack.toml"] = strip_content_hash(files["pack.toml"])

    out = tmp_path / "built2"
    write_built_pack(files, out_dir=out)
    ks = load_knowledge_set(out, allow_synthetic=True)
    hits = ks.names_index(alias)
    assert hits, "mutated alias not present in index: " + repr(alias)
