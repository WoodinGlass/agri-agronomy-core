"""Data-root resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.registry.data import DataRoot, _detect, resolve_data_root
from agri_core.registry.errors import DataNotFoundError

pytestmark = pytest.mark.unit


def _make_source_tree(root: Path, project_name: str = "agri-agronomy-core") -> Path:
    module = root / "src" / "agri_core" / "registry" / "data.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.touch()
    (root / "pyproject.toml").write_text(f'[project]\nname = "{project_name}"\n', encoding="utf-8")
    (root / "profiles").mkdir(exist_ok=True)
    (root / "profiles" / "sources.csv").write_text("", encoding="utf-8")
    (root / "schema").mkdir(exist_ok=True)
    return module


def _make_packaged_agri_core(root: Path) -> Path:
    agri_core = root / "agri_core"
    (agri_core / "registry").mkdir(parents=True)
    module = agri_core / "registry" / "data.py"
    module.touch()
    data = agri_core / "_data"
    (data / "profiles").mkdir(parents=True)
    (data / "profiles" / "sources.csv").write_text("", encoding="utf-8")
    (data / "schema").mkdir()
    return module


def test_detect_source_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = _make_source_tree(repo)
    root = _detect(module)
    assert root.kind == "source_tree"
    assert root.path == repo.resolve()


def test_detect_source_tree_wrong_project_name_falls_back(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = _make_source_tree(repo, project_name="something-else")
    with pytest.raises(DataNotFoundError):
        _detect(module)


def test_detect_packaged(tmp_path: Path) -> None:
    module = _make_packaged_agri_core(tmp_path)
    root = _detect(module)
    assert root.kind == "packaged"
    assert root.path == (tmp_path / "agri_core" / "_data").resolve()


def test_detect_packaged_missing_raises(tmp_path: Path) -> None:
    agri_core = tmp_path / "agri_core"
    (agri_core / "registry").mkdir(parents=True)
    module = agri_core / "registry" / "data.py"
    module.touch()
    with pytest.raises(DataNotFoundError):
        _detect(module)


def test_detect_venv_wheel_is_packaged(tmp_path: Path) -> None:
    """A wheel installed into a .venv under a source checkout must resolve to packaged."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "agri-agronomy-core"\n', encoding="utf-8"
    )
    (repo / "profiles").mkdir()
    (repo / "profiles" / "sources.csv").write_text("", encoding="utf-8")
    (repo / "schema").mkdir()

    site_packages = repo / ".venv" / "lib" / "python3.12" / "site-packages"
    agri_core = site_packages / "agri_core"
    (agri_core / "registry").mkdir(parents=True)
    module = agri_core / "registry" / "data.py"
    module.touch()
    data = agri_core / "_data"
    (data / "profiles").mkdir(parents=True)
    (data / "profiles" / "sources.csv").write_text("", encoding="utf-8")
    (data / "schema").mkdir()

    root = _detect(module)
    assert root.kind == "packaged"
    assert root.path == data.resolve()


def test_override_valid(tmp_path: Path) -> None:
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "sources.csv").write_text("", encoding="utf-8")
    (tmp_path / "schema").mkdir()
    root = resolve_data_root(override=tmp_path)
    assert root.kind == "override"
    assert root.path == tmp_path.resolve()


def test_override_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(DataNotFoundError):
        resolve_data_root(override=tmp_path)


def test_override_not_a_dir_raises(tmp_path: Path) -> None:
    target = tmp_path / "not-a-dir"
    target.write_text("", encoding="utf-8")
    with pytest.raises(DataNotFoundError):
        resolve_data_root(override=target)


def test_data_root_is_frozen() -> None:
    root = DataRoot(path=Path("/tmp"), kind="packaged")
    with pytest.raises((AttributeError, TypeError)):
        root.kind = "override"  # type: ignore[misc]
