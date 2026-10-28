"""TOCTOU: SQLite artifact changed after load must raise (M8-1)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agri_core.pack import PackStaleArtifactError, load_knowledge_set, read_pack_bytes
from agri_core.pack.sqlite_schema import write_built_pack

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"


def _build_sample(tmp_path: Path) -> Path:
    files = read_pack_bytes(_SRC)
    out = tmp_path / "built"
    write_built_pack(files, out_dir=out)
    return out


def test_names_index_works_before_tamper(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    taxa = list(ks.taxa())
    assert len(taxa) >= 1
    hits = ks.names_index(taxa[0].scientific_name)
    assert len(hits) >= 1


def test_names_index_raises_after_artifact_replaced(tmp_path: Path) -> None:
    built = _build_sample(tmp_path)
    ks = load_knowledge_set(built, allow_synthetic=True)
    sqlite_path = built / "pack.sqlite"

    # Append a byte -> st_size changes (and st_mtime_ns, though size is the
    # decisive signal if the FS timestamp resolution is coarse). Sleep briefly
    # to make mtime_ns reliably different on filesystems with coarse clocks.
    time.sleep(0.01)
    with sqlite_path.open("ab") as f:
        f.write(b"\x00")

    with pytest.raises(PackStaleArtifactError, match=r"changed since load"):
        ks.names_index("anything")
