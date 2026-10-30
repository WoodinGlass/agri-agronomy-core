"""License gate rules (M7-4)."""

from __future__ import annotations

import csv
import io
import shutil
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import validate_pack_report

pytestmark = pytest.mark.contract


def _sample_files() -> dict[str, bytes]:
    from agri_core.pack import read_pack_bytes

    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    files = dict(read_pack_bytes(src))
    toml = files["pack.toml"].decode("utf-8")
    files["pack.toml"] = (
        "\n".join(ln for ln in toml.splitlines() if not ln.startswith("content_hash"))
    ).encode("utf-8") + b"\n"
    return files


def _mutate_csv(data: bytes, matcher, **changes) -> bytes:
    text = data.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    idx = {col: header.index(col) for col in header}
    for row in rows[1:]:
        row_dict = dict(zip(header, row, strict=True))
        if matcher(row_dict):
            for col, val in changes.items():
                row[idx[col]] = val
            break
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def _add_fact(data: bytes, row: dict[str, str]) -> bytes:
    text = data.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    rows.append([row.get(col, "") for col in header])
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_sample_pack_no_findings() -> None:
    files = _sample_files()
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert ks is not None
    assert report.ok is True
    assert report.findings == ()


def test_nc_source_with_commercial_yes_flagged() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="CC-BY-NC-4.0",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    nc = [f for f in report.errors if f.code == "PACK_LICENSE_NC_COMMERCIAL"]
    assert len(nc) == 1
    assert nc[0].location.key == "S001"
    assert "S001" in nc[0].message


def test_nc_source_with_commercial_no_ok() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="CC-BY-NC-4.0",
        commercial_use="no",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_NC_COMMERCIAL" not in codes


def test_sa_dataset_referenced_flagged() -> None:
    files = _sample_files()
    files["datasets.csv"] = _mutate_csv(
        files["datasets.csv"],
        lambda r: r["dataset_id"] == "D000000001",
        license="CC-BY-SA-4.0",
    )
    files["facts/T000000001.csv"] = _add_fact(
        files["facts/T000000001.csv"],
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":8.0}',
            "scope": "{}",
            "provenance_kind": "imported",
            "dataset_id": "D000000001",
            "evidence": "C",
            "status": "imported",
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    sa = [f for f in report.errors if f.code == "PACK_LICENSE_DATASET_SA_ND"]
    assert len(sa) == 1
    assert sa[0].location.key == "D000000001"


def test_nd_dataset_referenced_flagged() -> None:
    files = _sample_files()
    files["datasets.csv"] = _mutate_csv(
        files["datasets.csv"],
        lambda r: r["dataset_id"] == "D000000001",
        license="CC-BY-ND-4.0",
    )
    files["facts/T000000001.csv"] = _add_fact(
        files["facts/T000000001.csv"],
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":8.0}',
            "scope": "{}",
            "provenance_kind": "imported",
            "dataset_id": "D000000001",
            "evidence": "C",
            "status": "imported",
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    nd = [f for f in report.errors if f.code == "PACK_LICENSE_DATASET_SA_ND"]
    assert len(nd) == 1


def test_sa_dataset_not_referenced_ok() -> None:
    files = _sample_files()
    files["datasets.csv"] = _mutate_csv(
        files["datasets.csv"],
        lambda r: r["dataset_id"] == "D000000001",
        license="CC-BY-SA-4.0",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_DATASET_SA_ND" not in codes


def test_cc0_dataset_referenced_ok() -> None:
    files = _sample_files()
    files["facts/T000000001.csv"] = _add_fact(
        files["facts/T000000001.csv"],
        {
            "fact_id": "F99999999999",
            "taxon_id": "T000000001",
            "parameter": "gdd_base",
            "value": '{"shape":"scalar","unit":"degree_Celsius","value":8.0}',
            "scope": "{}",
            "provenance_kind": "imported",
            "dataset_id": "D000000001",
            "evidence": "C",
            "status": "imported",
        },
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_DATASET_SA_ND" not in codes


def test_build_rejects_nc_source(tmp_path: Path) -> None:
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    dst = tmp_path / "pack"
    shutil.copytree(src, dst)
    toml = dst / "pack.toml"
    toml.write_text(
        "\n".join(
            ln
            for ln in toml.read_text(encoding="utf-8").splitlines()
            if not ln.startswith("content_hash")
        )
        + "\n",
        encoding="utf-8",
    )
    sp = dst / "sources.csv"
    sp.write_bytes(
        _mutate_csv(
            sp.read_bytes(),
            lambda r: r["id"] == "S001",
            license="CC-BY-NC-4.0",
        )
    )
    result = CliRunner().invoke(
        app, ["pack", "build", "--pack", str(dst), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "PACK_LICENSE_NC_COMMERCIAL" in combined


# ============================================================
# ADR-005: strict commercial-use allowlist (Cell C)
# ============================================================


# --- PACK_LICENSE_NOT_COMMERCIALLY_USABLE -------------------


def test_source_with_commercial_no_flagged() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        commercial_use="no",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_NOT_COMMERCIALLY_USABLE"]
    assert len(hits) == 1
    assert hits[0].location.key == "S001"
    assert "S001" in hits[0].message


def test_source_with_commercial_unclear_flagged() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S002",
        commercial_use="unclear",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_NOT_COMMERCIALLY_USABLE"]
    assert len(hits) == 1
    assert hits[0].location.key == "S002"


def test_source_with_commercial_yes_ok() -> None:
    files = _sample_files()  # sample sources are all commercial_use=yes
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_NOT_COMMERCIALLY_USABLE" not in codes


# --- PACK_LICENSE_OUTSIDE_ALLOWLIST (sources) ---------------


def test_source_odbl_rejected() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="ODbL-1.0",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_OUTSIDE_ALLOWLIST"]
    assert any(h.location.key == "S001" for h in hits)


def test_source_isc_rejected() -> None:
    """ISC was removed from the allowlist: it is not on the written policy."""
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="ISC",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_OUTSIDE_ALLOWLIST"]
    assert any(h.location.key == "S001" for h in hits)


def test_source_psf_rejected() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="PSF-2.0",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_OUTSIDE_ALLOWLIST"]
    assert any(h.location.key == "S001" for h in hits)


def test_source_composite_spdx_rejected() -> None:
    """Composite SPDX is rejected before any rule runs.

    ``SourceRow._is_valid_license`` rejects ``MIT OR Apache-2.0`` at load
    time, so the pack never reaches the allowlist rule. The test asserts
    the pack as a whole does not pass; the exact finding code depends on
    the load phase (``PACK_TABLE_INVALID`` or similar) and is not
    asserted here. The allowlist rule also rejects composite SPDX; that
    path is covered by the ``is_allowed_license`` parametrized tests.
    """
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="MIT OR Apache-2.0",
    )
    report, ks = validate_pack_report(files, allow_synthetic=True)
    assert not report.ok
    assert ks is None  # rejected at load, not at rule


def test_source_unknown_licenseref_rejected() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="LicenseRef-Apa-Saja",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_OUTSIDE_ALLOWLIST"]
    assert any(h.location.key == "S001" for h in hits)


def test_source_cc_by_4_ok() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="CC-BY-4.0",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_OUTSIDE_ALLOWLIST" not in codes


# --- PACK_LICENSE_OUTSIDE_ALLOWLIST (datasets) --------------


def test_dataset_pd_rejected() -> None:
    """Datasets cannot use LicenseRef-PublicDomain in 0.1.2 (no citation column)."""
    files = _sample_files()
    files["datasets.csv"] = _mutate_csv(
        files["datasets.csv"],
        lambda r: r["dataset_id"] == "D000000001",
        license="LicenseRef-PublicDomain",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_OUTSIDE_ALLOWLIST"]
    assert any(h.location.key == "D000000001" for h in hits)


def test_dataset_cc_by_4_ok() -> None:
    files = _sample_files()
    files["datasets.csv"] = _mutate_csv(
        files["datasets.csv"],
        lambda r: r["dataset_id"] == "D000000001",
        license="CC-BY-4.0",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_OUTSIDE_ALLOWLIST" not in codes


# --- PACK_LICENSE_PD_BASIS_MISSING --------------------------


def test_pd_source_without_basis_flagged() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="LicenseRef-PublicDomain",
        citation="Some citation without the required prefix",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    hits = [f for f in report.errors if f.code == "PACK_LICENSE_PD_BASIS_MISSING"]
    assert len(hits) == 1
    assert hits[0].location.key == "S001"


def test_pd_source_with_basis_ok() -> None:
    files = _sample_files()
    files["sources.csv"] = _mutate_csv(
        files["sources.csv"],
        lambda r: r["id"] == "S001",
        license="LicenseRef-PublicDomain",
        citation="basis: public domain under Indonesian copyright law",
    )
    report, _ = validate_pack_report(files, allow_synthetic=True)
    codes = [f.code for f in report.findings]
    assert "PACK_LICENSE_PD_BASIS_MISSING" not in codes


# --- build gate (new rules) ---------------------------------


def test_build_rejects_commercial_no_source(tmp_path: Path) -> None:
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    dst = tmp_path / "pack"
    shutil.copytree(src, dst)
    toml = dst / "pack.toml"
    toml.write_text(
        "\n".join(
            ln
            for ln in toml.read_text(encoding="utf-8").splitlines()
            if not ln.startswith("content_hash")
        )
        + "\n",
        encoding="utf-8",
    )
    sp = dst / "sources.csv"
    sp.write_bytes(
        _mutate_csv(
            sp.read_bytes(),
            lambda r: r["id"] == "S001",
            commercial_use="no",
        )
    )
    result = CliRunner().invoke(
        app, ["pack", "build", "--pack", str(dst), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "PACK_LICENSE_NOT_COMMERCIALLY_USABLE" in combined


# --- CLI: lint-sources exits non-zero for commercial_use != yes ---


def test_lint_sources_cli_exits_nonzero_for_commercial_no(tmp_path: Path) -> None:
    """``agri-core lint-sources`` must exit != 0 when a source is not
    commercial_use=yes (SRC005 is an ERROR finding)."""
    src = Path(str(pkg_files("agri_core") / "_samples" / "sample_pack"))
    dst = tmp_path / "pack"
    shutil.copytree(src, dst)
    toml = dst / "pack.toml"
    toml.write_text(
        "\n".join(
            ln
            for ln in toml.read_text(encoding="utf-8").splitlines()
            if not ln.startswith("content_hash")
        )
        + "\n",
        encoding="utf-8",
    )
    sp = dst / "sources.csv"
    sp.write_bytes(
        _mutate_csv(
            sp.read_bytes(),
            lambda r: r["id"] == "S001",
            commercial_use="no",
        )
    )
    result = CliRunner().invoke(app, ["lint-sources", "--pack", str(dst)])
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "SRC005" in combined
