"""Trapezoid non-degenerate rule (M7-2)."""

from __future__ import annotations

import csv
import io
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from agri_core.pack import validate_pack_report

pytestmark = pytest.mark.contract


def _sample_files() -> dict[str, bytes]:
    """Read the sample pack, stripping content_hash so mutations load.

    Tests here mutate facts; a declared ``content_hash`` would otherwise
    trip ``PACK_HASH_MISMATCH`` before any rule runs.
    """
    from agri_core.pack import read_pack_bytes

    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    files = dict(read_pack_bytes(src))
    toml = files["pack.toml"].decode("utf-8")
    files["pack.toml"] = (
        "\n".join(ln for ln in toml.splitlines() if not ln.startswith("content_hash")).encode(
            "utf-8"
        )
        + b"\n"
    )
    return files


def _mutate_value(facts_bytes: bytes, fact_id: str, new_value_json: str) -> bytes:
    """Replace a fact's value cell via csv roundtrip (safe for quoting)."""
    text = facts_bytes.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    fidx = header.index("fact_id")
    vidx = header.index("value")
    for row in rows[1:]:
        if row[fidx] == fact_id:
            row[vidx] = new_value_json
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_sample_pack_no_findings() -> None:
    files = _sample_files()
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    assert report.ok is True
    assert report.findings == ()


def test_degenerate_trapezoid_flagged() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_value(
        files["facts/T000000001.csv"],
        "F00000000001",
        '{"pts":[5.0,5.0,5.0,5.0],"shape":"trapezoid","unit":"pH"}',
    )
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    assert report.ok is False
    assert len(report.errors) == 1
    err = report.errors[0]
    assert err.code == "PACK_TRAPEZOID_DEGENERATE"
    assert err.location.fact_id == "F00000000001"
    assert err.location.taxon_id == "T000000001"
    assert err.location.parameter == "soil_ph"


def test_degenerate_trapezoid_message_content() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_value(
        files["facts/T000000001.csv"],
        "F00000000001",
        '{"pts":[4.5,4.5,4.5,4.5],"shape":"trapezoid","unit":"pH"}',
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    assert len(report.errors) == 1
    msg = report.errors[0].message
    assert "pts[0]" in msg
    assert "4.5" in msg
    assert "abs_min < abs_max" in msg


def test_valid_trapezoid_no_finding() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _mutate_value(
        files["facts/T000000001.csv"],
        "F00000000001",
        '{"pts":[4.5,5.5,6.5,7.0],"shape":"trapezoid","unit":"pH"}',
    )
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    assert report.ok is True
    assert report.findings == ()


def test_no_trapezoid_in_pack_no_trapezoid_finding() -> None:
    files = _sample_files()
    # Replace the only trapezoid with a scalar. soil_ph is a trapezoid
    # parameter, so a shape mismatch fires; but our rule must not.
    files["facts/T000000001.csv"] = _mutate_value(
        files["facts/T000000001.csv"],
        "F00000000001",
        '{"shape":"scalar","unit":"pH","value":6.5}',
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = {f.code for f in report.findings}
    assert "PACK_TRAPEZOID_DEGENERATE" not in codes
