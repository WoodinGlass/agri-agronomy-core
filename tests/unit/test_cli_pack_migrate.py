"""CLI agri-core pack migrate behavior."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agri_core.cli import app
from agri_core.pack import (
    TABLES,
    compute_pack_hash,
    load_knowledge_set,
    write_table,
)

pytestmark = pytest.mark.unit


def _make_pack(root: Path, *, hash_alg: str | None = None) -> None:
    """Minimal 0-taxa source pack, content_hash computed for declared alg."""
    root.mkdir(parents=True, exist_ok=True)
    body = (
        'name = "mig-test"\n'
        'version = "1.0.0"\n'
        "schema_version = 1\n"
        'engine_min = "0.0.0"\n'
        'dictionary_min = "1.0.0"\n'
        "synthetic = true\n"
    )
    if hash_alg is not None:
        body += f'hash_alg = "{hash_alg}"\n'
    (root / "pack.toml").write_text(body, encoding="utf-8")
    for name in ("taxa", "names", "hazards", "datasets", "sources"):
        spec = TABLES[name]
        assert spec.filename is not None
        (root / spec.filename).write_bytes(write_table(spec, []))
    (root / "ids.lock").write_text("", encoding="utf-8")
    digest = compute_pack_hash(root, hash_alg=hash_alg or "pre-rfc8785")
    final = body + f'content_hash = "{digest}"\n'
    (root / "pack.toml").write_text(final, encoding="utf-8")


def _manifest(root: Path) -> dict:
    return tomllib.loads((root / "pack.toml").read_text(encoding="utf-8"))


def test_migrate_rejects_sample() -> None:
    result = CliRunner().invoke(app, ["pack", "migrate", "--pack", "sample"])
    assert result.exit_code == 2
    assert "explicit path" in result.stderr


def test_migrate_from_v1_adds_hash_alg(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    assert "hash_alg" not in _manifest(root)

    result = CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "hash_alg=rfc8785" in result.stdout

    m = _manifest(root)
    assert m["hash_alg"] == "rfc8785"
    assert m["content_hash"].startswith("sha256:")


def test_migrate_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    before = (root / "pack.toml").read_bytes()

    result = CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    assert result.exit_code == 0
    assert "already migrated" in result.stdout
    assert (root / "pack.toml").read_bytes() == before


def test_migrate_from_explicit_legacy(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root, hash_alg="pre-rfc8785")
    assert _manifest(root)["hash_alg"] == "pre-rfc8785"

    result = CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    assert result.exit_code == 0
    assert _manifest(root)["hash_alg"] == "rfc8785"


def test_migrate_pack_loadable_after(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    _make_pack(root)
    CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    ks = load_knowledge_set(root, allow_synthetic=True)
    assert ks.pack_hash.startswith("sha256:")
    assert ks.manifest.hash_alg == "rfc8785"


def test_migrate_preserves_content_hash_for_ascii_int_pack(tmp_path: Path) -> None:
    """Migration does not change content_hash when pack.toml has no floats.

    Both canonicalizers produce identical bytes for ASCII strings and
    integers; hash_alg is stripped from _pack_toml_content.
    """
    root = tmp_path / "pack"
    _make_pack(root)
    before = _manifest(root)["content_hash"]
    CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    assert _manifest(root)["content_hash"] == before


def test_pack_lock_preserves_rfc8785_after_migrate(tmp_path: Path) -> None:
    """pack_lock does not revert hash_alg once migrated."""
    root = tmp_path / "pack"
    _make_pack(root)
    CliRunner().invoke(app, ["pack", "migrate", "--pack", str(root)])
    assert _manifest(root)["hash_alg"] == "rfc8785"

    # Damage content_hash to force recompute
    text = (root / "pack.toml").read_text()
    text = re.sub(
        r'content_hash = "[^"]*"',
        'content_hash = "sha256:' + "0" * 64 + '"',
        text,
    )
    (root / "pack.toml").write_text(text)

    result = CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert result.exit_code == 0, result.stdout + result.stderr
    m = _manifest(root)
    assert m["hash_alg"] == "rfc8785"
    assert m["content_hash"] != "sha256:" + "0" * 64


def test_pack_lock_legacy_pack_has_no_hash_alg_line(tmp_path: Path) -> None:
    """A1 default: pack with no hash_alg stays legacy after lock."""
    root = tmp_path / "pack"
    _make_pack(root)
    assert "hash_alg" not in _manifest(root)
    CliRunner().invoke(app, ["pack", "lock", "--pack", str(root)])
    assert "hash_alg" not in _manifest(root)


def test_meta_reports_hash_alg_and_backends(tmp_path: Path) -> None:
    """meta() includes hash_alg + backends (per ADR-019 amendment #7)."""
    from agri_core.registry import meta

    root = tmp_path / "pack"
    _make_pack(root)
    ks = load_knowledge_set(root, allow_synthetic=True)
    m = meta(ks)
    assert m.hash_alg == "pre-rfc8785"
    # ADR-019 stop-loss: hash_pack_files (Phase B), build_pack +
    # validate_pack (Phase D), load_knowledge_set (Phase G4-4, §11.12)
    # remain Python by design (perf gate not met; native still importable
    # for opt-in benchmarks via `_NATIVE_LOAD=True` or `_native.*`).
    assert m.backends["hash_pack_files"] == "python"
    assert m.backends["build_pack"] == "python"
    assert m.backends["validate_pack"] == "python"
    assert m.backends["load_knowledge_set"] == "python"
    # Not yet ported (Phase E/F): remain Python.
    assert m.backends["diff_packs"] == "python"
    assert m.backends["derive_all_tiers"] == "python"
