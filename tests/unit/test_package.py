"""Smoke tests for the installed package."""

from __future__ import annotations

import re

import pytest

from agri_core import __version__


@pytest.mark.unit
def test_version_is_non_empty_string() -> None:
    assert isinstance(__version__, str)
    assert __version__ != ""


@pytest.mark.unit
def test_version_matches_semver_pattern() -> None:
    assert re.match(r"^\d+\.\d+\.\d+", __version__)
