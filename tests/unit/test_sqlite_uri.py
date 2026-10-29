"""Unit tests for ``_sqlite_uri`` (M9 PR-D).

The Windows branch is exercised on every platform because detection uses
the posix form of the path, not ``sys.platform``. ``Path("C:/...")`` on
Linux is a relative path whose first component contains a colon; on
Windows it is a drive-letter path. Either way ``as_posix()`` yields
``"C:/..."``, so the same regex decides.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.pack.knowledge_set import _sqlite_uri

pytestmark = pytest.mark.unit


def test_posix_absolute_path() -> None:
    uri = _sqlite_uri(Path("/data/packs/pack.sqlite"))
    assert uri == "file:/data/packs/pack.sqlite?mode=ro&immutable=1"


def test_posix_relative_path() -> None:
    uri = _sqlite_uri(Path("packs/pack.sqlite"))
    assert uri == "file:packs/pack.sqlite?mode=ro&immutable=1"


def test_windows_drive_uppercase() -> None:
    uri = _sqlite_uri(Path("C:/data/pack.sqlite"))
    assert uri == "file:///C:/data/pack.sqlite?mode=ro&immutable=1"


def test_windows_drive_lowercase() -> None:
    uri = _sqlite_uri(Path("d:/work/pack.sqlite"))
    assert uri == "file:///d:/work/pack.sqlite?mode=ro&immutable=1"
