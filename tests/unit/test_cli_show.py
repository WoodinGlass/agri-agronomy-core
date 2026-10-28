"""CLI ``show`` behavior (M8-4c)."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.unit


def _sample_pack_path() -> Path:
    return Path(str(files("agri_core") / "_samples" / "sample_pack"))


def _invoke(*args: str):
    return CliRunner().invoke(app, ["show", *args])


def _first_taxon():
    ks = load_knowledge_set(_sample_pack_path(), allow_synthetic=True)
    return next(iter(ks.taxa()))


def _first_fact():
    ks = load_knowledge_set(_sample_pack_path(), allow_synthetic=True)
    return next(iter(ks.facts()))


# ---- 3 modes -------------------------------------------------------------


def test_show_by_name_ok() -> None:
    t = _first_taxon()
    result = _invoke("--pack", "sample", "--name", t.scientific_name)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "ok:" in result.stdout
    assert t.taxon_id in result.stdout
    assert "via=" in result.stdout


def test_show_by_taxon_ok() -> None:
    t = _first_taxon()
    result = _invoke("--pack", "sample", "--taxon", t.taxon_id)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "taxon:" in result.stdout
    assert t.taxon_id in result.stdout
    assert t.scientific_name in result.stdout


def test_show_by_fact_ok() -> None:
    f = _first_fact()
    result = _invoke("--pack", "sample", "--fact", f.fact_id)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "fact:" in result.stdout
    assert f.fact_id in result.stdout
    assert f.parameter in result.stdout


# ---- JSON mode ------------------------------------------------------------


def test_show_json_name() -> None:
    t = _first_taxon()
    result = _invoke("--pack", "sample", "--name", t.scientific_name, "--json")
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["taxon_id"] == t.taxon_id
    assert "matched_via" in payload


# ---- exit codes -----------------------------------------------------------


def test_show_name_unknown_exit_1() -> None:
    result = _invoke("--pack", "sample", "--name", "__no_such_taxon__")
    assert result.exit_code == 1, result.stdout + result.stderr
    assert "unknown:" in result.stdout
    assert "code=no_match" in result.stdout


def test_show_pack_not_found_exit_3(tmp_path: Path) -> None:
    result = _invoke("--pack", str(tmp_path / "nonexistent"), "--name", "x")
    assert result.exit_code == 3
    assert "PACK_NOT_FOUND" in result.stderr
