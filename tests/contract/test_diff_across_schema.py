"""Cross-schema diff: pack v1 vs migrated v2 (ADR-019 Phase E).

Migrating a v1 pack to v2 only changes the manifest (schema_version,
hash_alg, content_hash); the rows are untouched. The DiffReport
contract does not compare manifest fields, so diff(v1, v2) must be
``identical=True`` with zero violations, and the same holds for the
built (SQLite) artifacts.

The mutation case at the bottom proves the test is not vacuous: after
migrating, changing one CSV fact field still flips the report to
``identical=False``, so a bug that silently elides row changes would
be caught here.

Skip guard: any CI image without ``agri-core`` on PATH skips cleanly
rather than failing. Colab and the locked CI image both have the
binary installed editable, so the tests actually run there.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from agri_core.pack import KnowledgeSet, diff_packs, load_knowledge_set

pytestmark = pytest.mark.contract

_SAMPLE_PACK = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
_BIN_OR_NONE = shutil.which("agri-core")
_SKIP_NO_BIN = pytest.mark.skipif(_BIN_OR_NONE is None, reason="agri-core binary not on PATH")


def _load(p: Path) -> KnowledgeSet:
    return load_knowledge_set(p, allow_synthetic=True)


def _make_v1(tmp_path: Path, name: str = "v1") -> Path:
    dst = tmp_path / name
    shutil.copytree(_SAMPLE_PACK, dst)
    toml = dst / "pack.toml"
    lines = [
        ln
        for ln in toml.read_text(encoding="utf-8").splitlines()
        if not ln.startswith("content_hash") and not ln.startswith("hash_alg")
    ]
    lines = [ln.replace("schema_version = 2", "schema_version = 1") for ln in lines]
    toml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dst


def _migrate(v1: Path, dst: Path) -> Path:
    assert _BIN_OR_NONE is not None
    shutil.copytree(v1, dst)
    subprocess.run(
        [_BIN_OR_NONE, "pack", "migrate", "--pack", str(dst)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [_BIN_OR_NONE, "pack", "lock", "--pack", str(dst)],
        check=True,
        capture_output=True,
    )
    return dst


def _build(src: Path, out: Path) -> Path:
    assert _BIN_OR_NONE is not None
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [_BIN_OR_NONE, "pack", "build", "--pack", str(src), "--out", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def _mutate_fact(pack: Path, taxon_file: str, fact_id: str, **changes: str) -> None:
    fp = pack / "facts" / taxon_file
    rows = list(csv.reader(io.StringIO(fp.read_text(encoding="utf-8"))))
    header = rows[0]
    idx = {col: header.index(col) for col in changes}
    for row in rows[1:]:
        if row[0] == fact_id:
            for col, val in changes.items():
                row[idx[col]] = val
            break
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    fp.write_text(buf.getvalue(), encoding="utf-8")


@_SKIP_NO_BIN
def test_diff_v1_vs_migrated_source_identical(tmp_path: Path) -> None:
    v1 = _make_v1(tmp_path)
    v2 = _migrate(v1, tmp_path / "v2")
    report = diff_packs(_load(v1), _load(v2))
    assert report.identical
    assert report.ok


@_SKIP_NO_BIN
def test_diff_migrated_vs_sample_identical(tmp_path: Path) -> None:
    v1 = _make_v1(tmp_path)
    v2 = _migrate(v1, tmp_path / "v2")
    report = diff_packs(_load(v2), _load(_SAMPLE_PACK))
    assert report.identical


@_SKIP_NO_BIN
def test_diff_v1_vs_migrated_built_identical(tmp_path: Path) -> None:
    v1 = _make_v1(tmp_path)
    v2 = _migrate(v1, tmp_path / "v2")
    v1_built = _build(v1, tmp_path / "v1_built")
    v2_built = _build(v2, tmp_path / "v2_built")
    report = diff_packs(_load(v1_built), _load(v2_built))
    assert report.identical


@_SKIP_NO_BIN
def test_diff_detects_mutation_across_schema(tmp_path: Path) -> None:
    v1 = _make_v1(tmp_path)
    v2 = _migrate(v1, tmp_path / "v2")
    _mutate_fact(v2, "T000000001.csv", "F00000000002", parameter="gdd_upper")
    assert _BIN_OR_NONE is not None
    subprocess.run(
        [_BIN_OR_NONE, "pack", "lock", "--pack", str(v2)],
        check=True,
        capture_output=True,
    )
    report = diff_packs(_load(v1), _load(v2))
    assert not report.identical
