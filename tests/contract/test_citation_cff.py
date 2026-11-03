"""CITATION.cff consistency with pyproject.toml and CHANGELOG.md."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
CITATION = ROOT / "CITATION.cff"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


@pytest.fixture(scope="module")
def cff() -> dict:
    assert CITATION.is_file(), f"missing {CITATION}"
    return yaml.safe_load(CITATION.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_cff_version(cff: dict) -> None:
    assert cff["cff-version"] == "1.2.0"


def test_cff_required_fields(cff: dict) -> None:
    required = (
        "cff-version",
        "message",
        "title",
        "type",
        "authors",
        "version",
        "date-released",
        "license",
        "repository-code",
        "url",
    )
    missing = [k for k in required if k not in cff]
    assert not missing, f"missing required fields: {missing}"


def test_cff_title_matches_pyproject_name(cff: dict, project: dict) -> None:
    assert cff["title"] == project["project"]["name"]


def test_cff_version_matches_pyproject(cff: dict, project: dict) -> None:
    assert cff["version"] == project["project"]["version"]


def test_cff_license_matches_pyproject(cff: dict, project: dict) -> None:
    assert cff["license"] == project["project"]["license"]


def test_cff_repository_matches_pyproject(cff: dict, project: dict) -> None:
    assert cff["repository-code"] == project["project"]["urls"]["Repository"]


def test_cff_url_matches_homepage(cff: dict, project: dict) -> None:
    assert cff["url"] == project["project"]["urls"]["Homepage"]


def test_cff_date_released_matches_changelog(cff: dict) -> None:
    version = cff["version"]
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$",
        re.MULTILINE,
    )
    m = pattern.search(CHANGELOG.read_text(encoding="utf-8"))
    assert m, f"CHANGELOG has no dated '## [{version}]' section"
    assert cff["date-released"] == m.group(1), (
        f"CITATION.cff date-released={cff['date-released']!r} != CHANGELOG date {m.group(1)!r}"
    )


def test_cff_authors_schema_form(cff: dict) -> None:
    authors = cff["authors"]
    assert isinstance(authors, list), "authors must be a list"
    assert authors, "authors must be non-empty"
    for a in authors:
        has_collective = "name" in a
        has_person = "given-names" in a and "family-names" in a
        assert has_collective or has_person, (
            f"author entry needs either 'name' (collective) or "
            f"'given-names'+'family-names' (person): {a!r}"
        )


def test_cff_keywords_match_pyproject(cff: dict, project: dict) -> None:
    cff_kw = set(cff.get("keywords", []))
    proj_kw = set(project["project"].get("keywords", []))
    assert cff_kw == proj_kw, (
        f"keywords drift: only in CITATION.cff={cff_kw - proj_kw}, "
        f"only in pyproject.toml={proj_kw - cff_kw}"
    )


def test_cff_type_is_software(cff: dict) -> None:
    assert cff["type"] == "software"
