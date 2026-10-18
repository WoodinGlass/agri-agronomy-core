"""Resolve where profiles and JSON schemas live on disk."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agri_core.registry.errors import DataNotFoundError

DataRootKind = Literal["override", "source_tree", "packaged"]
"""How a data root was found."""

_PROJECT_NAME = "agri-agronomy-core"
_REQUIRED_MARKERS: tuple[str, ...] = ("profiles/sources.csv", "schema")


@dataclass(frozen=True)
class DataRoot:
    """A resolved location for profile data and JSON schemas.

    ``kind`` says how the path was chosen:

    - ``"override"``: the caller supplied an explicit directory.
    - ``"source_tree"``: this module lives inside a source checkout.
    - ``"packaged"``: the data ships inside the installed wheel.
    """

    path: Path
    kind: DataRootKind


def _validate_root(path: Path, *, kind: DataRootKind) -> DataRoot:
    if not path.is_dir():
        raise DataNotFoundError(f"data directory not found: {path}")
    missing = [m for m in _REQUIRED_MARKERS if not (path / m).exists()]
    if missing:
        raise DataNotFoundError(f"data directory {path} is missing: {', '.join(missing)}")
    return DataRoot(path=path, kind=kind)


def _is_source_tree(module_file: Path) -> Path | None:
    """Return the repo root if ``module_file`` sits at ``<repo>/src/agri_core/registry/data.py``.

    Returns ``None`` in every other case, including a wheel installed inside a
    ``.venv`` located under a source checkout.
    """
    try:
        parents = module_file.resolve().parents
        if len(parents) < 4:
            return None
        repo_root = parents[3]
        src_dir = parents[2]
        if src_dir.name != "src":
            return None
        pyproject = repo_root / "pyproject.toml"
        if not pyproject.is_file():
            return None
        with pyproject.open("rb") as f:
            meta = tomllib.load(f)
        project = meta.get("project")
        if not isinstance(project, dict):
            return None
        if project.get("name") != _PROJECT_NAME:
            return None
        _validate_root(repo_root, kind="source_tree")
        return repo_root
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _detect(module_file: Path) -> DataRoot:
    """Pure detection: source tree first, then packaged data."""
    repo_root = _is_source_tree(module_file)
    if repo_root is not None:
        return DataRoot(path=repo_root, kind="source_tree")
    packaged = module_file.resolve().parents[1] / "_data"
    return _validate_root(packaged, kind="packaged")


def resolve_data_root(*, override: Path | None = None) -> DataRoot:
    """Locate the data root.

    Priority: explicit ``override`` (validated), source checkout, packaged data.
    Never uses the current working directory or environment variables.
    """
    if override is not None:
        return _validate_root(override.resolve(), kind="override")
    return _detect(Path(__file__))
