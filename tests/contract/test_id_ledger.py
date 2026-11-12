"""Append-only taxon ID ledger (ADR-011)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agri_core.pack import TABLES, read_pack_bytes, read_table, validate_pack_report

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


def _copy_sample(tmp_path: Path, *, strip_lock: bool = False) -> Path:
    dst = tmp_path / "pack"
    shutil.copytree(SAMPLE, dst)
    if strip_lock:
        (dst / "ids.lock").unlink()
        toml = dst / "pack.toml"
        lines = [ln for ln in toml.read_text().splitlines() if not ln.startswith("content_hash")]
        toml.write_text("\n".join(lines) + "\n")
    return dst


def _read_lock(path: Path) -> list[str]:
    return [ln for ln in (path / "ids.lock").read_text(encoding="utf-8").splitlines() if ln]


def _write_lock(path: Path, ids: list[str]) -> None:
    (path / "ids.lock").write_text("\n".join(ids) + "\n", encoding="utf-8")


def _relock(pack: Path) -> None:
    subprocess.run(
        ["agri-core", "pack", "lock", "--pack", str(pack)],
        capture_output=True,
        text=True,
        check=True,
    )


def _strip_hash(pack: Path) -> None:
    """Drop content_hash so validate runs without the hash check.

    Used by tests that deliberately create drift: `pack lock` runs
    validate first and would refuse a pack with drift. Stripping the
    hash lets `validate_pack_report` exercise its rules directly.
    """
    toml = pack / "pack.toml"
    lines = [ln for ln in toml.read_text().splitlines() if not ln.startswith("content_hash")]
    toml.write_text("\n".join(lines) + "\n")


def _scaffold(pack: Path, name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "agri-core",
            "pack",
            "scaffold",
            "--pack",
            str(pack),
            "--scientific-name",
            name,
            "--archetype",
            "annual",
            "--use",
            "vegetable",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ===== Sample pack =====


def test_sample_pack_has_ids_lock() -> None:
    assert (SAMPLE / "ids.lock").is_file()


def test_ids_lock_sorted_no_dupes() -> None:
    ids = _read_lock(SAMPLE)
    assert ids == sorted(ids), "ids.lock not sorted"
    assert len(ids) == len(set(ids)), "ids.lock has duplicates"


def test_ids_lock_matches_taxa() -> None:
    files = read_pack_bytes(SAMPLE)
    taxa = read_table(TABLES["taxa"], files["taxa.csv"], source_name="taxa.csv")
    taxa_ids = {str(r["taxon_id"]) for r in taxa.rows if r.get("taxon_id")}
    lock_ids = set(_read_lock(SAMPLE))
    assert taxa_ids <= lock_ids, f"taxa IDs missing from lock: {taxa_ids - lock_ids}"


# ===== Validate: absent =====


def test_validate_rejects_missing_ids_lock(tmp_path: Path) -> None:
    pack = _copy_sample(tmp_path, strip_lock=True)
    files = read_pack_bytes(pack)
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.errors]
    assert "PACK_ID_LEDGER_ABSENT" in codes


def test_bootstrap_hint_does_not_suggest_raw_sort(tmp_path: Path) -> None:
    """The PACK_ID_LEDGER_ABSENT hint must not suggest a command that copies
    full CSV rows into ids.lock (header + commas), which would fail drift
    and the sorted-no-dupes contract test."""
    pack = _copy_sample(tmp_path, strip_lock=True)
    files = read_pack_bytes(pack)
    report, _ = validate_pack_report(files, allow_synthetic=True)
    absent = [f for f in report.errors if f.code == "PACK_ID_LEDGER_ABSENT"]
    assert absent, "expected PACK_ID_LEDGER_ABSENT finding"
    msg = absent[0].message
    assert "`sort taxa.csv > ids.lock`" not in msg, (
        f"hint suggests raw `sort taxa.csv > ids.lock` (produces CSV rows, not IDs): {msg!r}"
    )
    assert "cut -d, -f1" in msg, (
        f"hint should mention `cut -d, -f1` to extract the taxon_id column: {msg!r}"
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX shell pipeline (tail/cut/sort); Windows uses `agri-core pack scaffold`",
)
def test_bootstrap_hint_command_produces_id_only_lines(tmp_path: Path) -> None:
    """The corrected hint command must emit one taxon_id per line, no header,
    no commas, sorted."""
    pack = _copy_sample(tmp_path, strip_lock=True)
    taxa = pack / "taxa.csv"
    header = taxa.read_text().splitlines()[0]
    assert header.startswith("taxon_id,"), "taxa.csv first column must be taxon_id"
    taxa.write_text(
        "\n".join(
            [
                header,
                "T000000001,species,Fakeus one,,",
                "T000000002,species,Fakeus two,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        "tail -n +2 taxa.csv | cut -d, -f1 | sort",
        shell=True,
        cwd=pack,
        capture_output=True,
        text=True,
        check=True,
    )
    out = [ln for ln in result.stdout.splitlines() if ln]
    assert out == ["T000000001", "T000000002"], f"unexpected output: {out!r}"
    for line in out:
        assert "," not in line, f"line contains comma (CSV row leaked): {line!r}"
        assert line.startswith("T"), f"line does not start with T: {line!r}"


# ===== Validate: drift =====


def test_validate_rejects_taxa_id_missing_from_lock(tmp_path: Path) -> None:
    pack = _copy_sample(tmp_path)
    ids = _read_lock(pack)
    removed = ids[0]
    _write_lock(pack, ids[1:])
    _strip_hash(pack)  # drift breaks validate; pack lock would refuse
    files = read_pack_bytes(pack)
    report, _ = validate_pack_report(files, allow_synthetic=True)
    drift = [f for f in report.errors if f.code == "PACK_ID_LEDGER_DRIFT"]
    assert drift, "expected drift finding"
    assert any(removed in (f.message or "") for f in drift)


def test_validate_accepts_reserved_ids(tmp_path: Path) -> None:
    pack = _copy_sample(tmp_path)
    ids = _read_lock(pack)
    _write_lock(pack, [*ids, "TZZZZZZZZZ"])
    _relock(pack)
    files = read_pack_bytes(pack)
    report, _ = validate_pack_report(files, allow_synthetic=True)
    assert report.ok


# ===== Scaffold =====


def test_scaffold_appends_to_ids_lock(tmp_path: Path) -> None:
    pack = _copy_sample(tmp_path)
    before = set(_read_lock(pack))
    r = _scaffold(pack, "Testus novus")
    assert r.returncode == 0, r.stderr
    after = set(_read_lock(pack))
    added = after - before
    assert len(added) == 1
    new_id = next(iter(added))
    files = read_pack_bytes(pack)
    taxa = read_table(TABLES["taxa"], files["taxa.csv"], source_name="taxa.csv")
    taxa_ids = {str(row["taxon_id"]) for row in taxa.rows if row.get("taxon_id")}
    assert new_id in taxa_ids


def test_scaffold_bootstraps_missing_ids_lock(tmp_path: Path) -> None:
    pack = _copy_sample(tmp_path, strip_lock=True)
    r = _scaffold(pack, "Testus novus")
    assert r.returncode == 0, r.stderr
    ids = _read_lock(pack)
    assert len(ids) >= 9  # 8 original + 1 new


def test_scaffold_never_regenerates_reserved_id(tmp_path: Path) -> None:
    pack = _copy_sample(tmp_path)
    reserved = "TZZZZZZZZZ"
    ids = _read_lock(pack)
    _write_lock(pack, [*ids, reserved])
    _relock(pack)
    for i in range(5):
        r = _scaffold(pack, f"Testus{i}")
        assert r.returncode == 0, r.stderr
        _relock(pack)
    ids_after = _read_lock(pack)
    assert reserved in ids_after
    assert ids_after.count(reserved) == 1


# ===== Perf pack generator =====


def test_perf_pack_includes_ids_lock(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "tests" / "perf"))
    from _gen_pack import generate_perf_pack

    pack = tmp_path / "perf"
    pack.mkdir()
    generate_perf_pack(pack, n_taxa=5)
    assert (pack / "ids.lock").is_file()
    ids = _read_lock(pack)
    assert len(ids) == 5
    assert ids == sorted(ids)
