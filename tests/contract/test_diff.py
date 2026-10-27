"""Pack diff (M7-6)."""

from __future__ import annotations

import csv
import io
import json
import shutil
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import TABLES, diff_packs, load_knowledge_set, write_table
from agri_core.pack.diff import FactChangeClass
from agri_core.pack.tables import read_table

pytestmark = pytest.mark.contract


def _sample_copy(tmp_path: Path, name: str = "src") -> Path:
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


def _remove_taxon_and_deps(pack: Path, taxon_id: str) -> None:
    for csvname in ("taxa", "names", "hazards"):
        spec = TABLES[csvname]
        assert spec.filename is not None
        p = pack / spec.filename
        table = read_table(spec, p.read_bytes(), source_name=spec.filename)
        rows = [dict(r) for r in table.rows if r["taxon_id"] != taxon_id]
        p.write_bytes(write_table(spec, rows))
    facts_file = pack / "facts" / f"{taxon_id}.csv"
    if facts_file.exists():
        facts_file.unlink()


def _add_taxon(pack: Path, taxon_id: str) -> None:
    spec = TABLES["taxa"]
    assert spec.filename is not None
    p = pack / spec.filename
    table = read_table(spec, p.read_bytes(), source_name=spec.filename)
    rows = [dict(r) for r in table.rows]
    rows.append(
        {
            "taxon_id": taxon_id,
            "rank": "species",
            "scientific_name": f"Added {taxon_id}",
            "accepted_name": None,
            "organism_group": "vascular_plant",
            "archetype": "annual",
            "uses": ["vegetable"],
            "traits": [],
            "parent_id": None,
            "external_ids": None,
            "src": ["S001"],
            "dataset_id": None,
        }
    )
    p.write_bytes(write_table(spec, rows))


def _mutate_fact_row(pack: Path, taxon_file: str, fact_id: str, **changes: str) -> None:
    fp = pack / "facts" / taxon_file
    reader = csv.reader(io.StringIO(fp.read_text(encoding="utf-8")))
    rows = list(reader)
    header = rows[0]
    idx = {name: header.index(name) for name in changes}
    for row in rows[1:]:
        if row[0] == fact_id:
            for name, value in changes.items():
                row[idx[name]] = value
            break
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    fp.write_text(buf.getvalue(), encoding="utf-8")


def _load(pack: Path):
    return load_knowledge_set(pack, allow_synthetic=True)


def test_diff_identical_packs_empty_report(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    report = diff_packs(_load(a), _load(b))
    assert report.identical is True
    assert report.ok is True
    assert report.violations == ()
    assert report.facts_added == ()
    assert report.facts_removed == ()


def test_diff_taxon_added_not_violation(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _add_taxon(b, "TAAAAAAAAA")
    report = diff_packs(_load(a), _load(b))
    assert "TAAAAAAAAA" in report.taxa.added
    assert report.violations == ()
    assert report.ok is True


def test_diff_taxon_removed_is_violation(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _remove_taxon_and_deps(b, "T000000005")
    report = diff_packs(_load(a), _load(b))
    assert "T000000005" in report.taxa.removed
    assert any(v.kind == "taxon_removed" and v.entity_id == "T000000005" for v in report.violations)
    assert report.ok is False


def test_diff_fact_added_not_violation(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    fp = b / "facts" / "T000000001.csv"
    with fp.open("a", encoding="utf-8") as fh:
        fh.write(
            'F99999999999,T000000001,gdd_base,,"{""shape"":""scalar"",'
            '""unit"":""degree_Celsius"",""value"":9.0}","{}",curated,S001,,x,'
            "A,approved,reviewer,2026-01-01,\n"
        )
    report = diff_packs(_load(a), _load(b))
    assert "F99999999999" in report.facts_added
    assert report.violations == ()
    assert report.ok is True


def test_diff_fact_removed_is_violation(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    fp = b / "facts" / "T000000001.csv"
    lines = [
        ln
        for ln in fp.read_text(encoding="utf-8").splitlines()
        if not ln.startswith("F00000000002,")
    ]
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = diff_packs(_load(a), _load(b))
    assert "F00000000002" in report.facts_removed
    assert any(
        v.kind == "fact_removed" and v.entity_id == "F00000000002" for v in report.violations
    )
    assert report.ok is False


def test_diff_fact_value_changed_is_violation(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _mutate_fact_row(
        b,
        "T000000001.csv",
        "F00000000001",
        value='{"pts":[4.0,6.0,7.0,8.0],"shape":"trapezoid","unit":"pH"}',
    )
    report = diff_packs(_load(a), _load(b))
    changes = [fc for fc in report.facts_changed if fc.fact_id == "F00000000001"]
    assert len(changes) == 1
    assert changes[0].classification == FactChangeClass.VIOLATION
    assert "value" in changes[0].fields_changed
    assert any(
        v.kind == "fact_id_reused" and v.entity_id == "F00000000001" for v in report.violations
    )


def test_diff_fact_parameter_changed_is_violation(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _mutate_fact_row(b, "T000000001.csv", "F00000000002", parameter="gdd_upper")
    report = diff_packs(_load(a), _load(b))
    changes = [fc for fc in report.facts_changed if fc.fact_id == "F00000000002"]
    assert len(changes) == 1
    assert "parameter" in changes[0].fields_changed
    assert changes[0].classification == FactChangeClass.VIOLATION


def test_diff_fact_status_changed_is_acceptable(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _mutate_fact_row(b, "T000000001.csv", "F00000000002", status="reviewed")
    report = diff_packs(_load(a), _load(b))
    changes = [fc for fc in report.facts_changed if fc.fact_id == "F00000000002"]
    assert len(changes) == 1
    assert changes[0].classification == FactChangeClass.ACCEPTABLE
    assert "status" in changes[0].fields_changed
    assert report.violations == ()


def test_diff_fact_supersede_is_acceptable(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _mutate_fact_row(b, "T000000001.csv", "F00000000002", superseded_by="F00000000001")
    report = diff_packs(_load(a), _load(b))
    changes = [fc for fc in report.facts_changed if fc.fact_id == "F00000000002"]
    assert len(changes) == 1
    assert changes[0].classification == FactChangeClass.ACCEPTABLE
    assert "superseded_by" in changes[0].fields_changed


def test_diff_deterministic_ordering(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _remove_taxon_and_deps(b, "T000000005")
    r1 = diff_packs(_load(a), _load(b))
    r2 = diff_packs(_load(a), _load(b))
    assert r1.model_dump_json() == r2.model_dump_json()


def test_diff_json_serialization(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    report = diff_packs(_load(a), _load(b))
    data = json.loads(report.model_dump_json())
    assert data["identical"] is True
    assert data["ok"] is True
    assert "violations" in data


def test_diff_cli_json_output(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    result = CliRunner().invoke(app, ["diff", "--old", str(a), "--new", str(b), "--json"])
    assert result.exit_code == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["identical"] is True
    assert data["ok"] is True


def test_diff_cli_violation_exits_1(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _remove_taxon_and_deps(b, "T000000005")
    result = CliRunner().invoke(app, ["diff", "--old", str(a), "--new", str(b)])
    assert result.exit_code == 1
    assert "violations" in result.stdout


def test_diff_cli_exit_code_flag(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    b = _sample_copy(tmp_path, "b")
    _add_taxon(b, "TAAAAAAAAA")
    r0 = CliRunner().invoke(app, ["diff", "--old", str(a), "--new", str(b)])
    assert r0.exit_code == 0
    r1 = CliRunner().invoke(app, ["diff", "--old", str(a), "--new", str(b), "--exit-code"])
    assert r1.exit_code == 1


def test_diff_cli_unreadable_exits_3(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["diff", "--old", str(tmp_path / "nope"), "--new", str(tmp_path / "nope2")],
    )
    assert result.exit_code == 3
    assert "PACK_NOT_FOUND" in result.stderr


def test_diff_same_pack_twice_identical(tmp_path: Path) -> None:
    a = _sample_copy(tmp_path, "a")
    report = diff_packs(_load(a), _load(a))
    assert report.identical is True
    assert report.violations == ()
    assert report.old_pack_hash == report.new_pack_hash
