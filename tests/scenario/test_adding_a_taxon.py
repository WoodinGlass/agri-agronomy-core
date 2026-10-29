"""End-to-end test for docs/ADDING_A_TAXON.md (M9 PR-C).

Parses fenced ```bash blocks from the walkthrough, extracts every
`agri-core` invocation, substitutes the `<PACK>` and `<OUT>` placeholders
with temporary paths, and runs each command via Typer's CliRunner against
a copy of the sample pack. The manual "add facts" step is not executed —
the runner only verifies that the CLI sequence in the doc produces a new
taxon row.
"""

from __future__ import annotations

import shlex
import shutil
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import TABLES
from agri_core.pack.tables import read_table

pytestmark = pytest.mark.scenario

_DOC = Path(__file__).resolve().parents[2] / "docs" / "ADDING_A_TAXON.md"


def _sample_source(dst: Path) -> Path:
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    shutil.copytree(src, dst)
    return dst


def _bash_lines(doc_path: Path) -> list[str]:
    """Return non-empty, non-comment lines inside fenced ```bash blocks."""
    lines: list[str] = []
    in_block = False
    for raw in doc_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```bash"):
            in_block = True
            continue
        if in_block and stripped == "```":
            in_block = False
            continue
        if in_block and stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def test_doc_has_runnable_commands() -> None:
    """Sanity: the doc must expose scaffold, build and validate commands."""
    lines = _bash_lines(_DOC)
    agri_lines = [ln for ln in lines if ln.startswith("agri-core ")]
    assert agri_lines, f"no `agri-core ...` line found in {_DOC}"
    assert any("pack scaffold" in ln for ln in agri_lines), agri_lines
    assert any("pack build" in ln for ln in agri_lines), agri_lines
    assert any("validate" in ln for ln in agri_lines), agri_lines


def test_adding_a_taxon_workflow(tmp_path: Path) -> None:
    """Run every command from the doc, then verify the new row exists."""
    pack = _sample_source(tmp_path / "src")
    out_dir = tmp_path / "built"
    out_dir.mkdir()

    runner = CliRunner()
    for line in _bash_lines(_DOC):
        if not line.startswith("agri-core "):
            continue
        argv = shlex.split(line)
        assert argv[0] == "agri-core"
        args = [a.replace("<PACK>", str(pack)).replace("<OUT>", str(out_dir)) for a in argv[1:]]
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (
            f"command from doc failed (exit={result.exit_code}): {line}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    raw = (pack / "taxa.csv").read_bytes()
    table = read_table(TABLES["taxa"], raw, source_name="taxa.csv")
    rows = [dict(r) for r in table.rows]
    scientific_names = [r["scientific_name"] for r in rows]
    assert "Foo bar" in scientific_names, (
        f"scaffolded taxon not in taxa.csv after workflow; got {scientific_names}"
    )

    new_row = next(r for r in rows if r["scientific_name"] == "Foo bar")
    new_id = new_row["taxon_id"]
    assert (pack / "facts" / f"{new_id}.csv").is_file(), (
        f"facts/{new_id}.csv missing after scaffold"
    )
