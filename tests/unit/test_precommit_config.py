"""Verify the local agri-core-validate hook contract in .pre-commit-config.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

pytestmark = pytest.mark.unit

CONFIG_PATH = Path(__file__).resolve().parents[2] / ".pre-commit-config.yaml"


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")),
    )


@pytest.fixture(scope="module")
def hook(config: dict[str, Any]) -> dict[str, Any]:
    for repo in config["repos"]:
        if repo.get("repo") == "local":
            for h in repo.get("hooks", []):
                if h.get("id") == "agri-core-validate":
                    return cast(dict[str, Any], h)
    raise AssertionError("agri-core-validate hook not found in .pre-commit-config.yaml")


def test_local_repo_is_last(config: dict[str, Any]) -> None:
    repos = config["repos"]
    assert repos[-1]["repo"] == "local", "local repo must be the last entry"


@pytest.mark.parametrize(
    "path",
    [
        "profiles/sources.csv",
        "profiles/crops/tomato.yaml",
        "profiles/fertilizers.yaml",
        "profiles/media/cocopeat.yaml",
        "schema/source.schema.json",
    ],
)
def test_hook_files_regex_matches(hook: dict[str, Any], path: str) -> None:
    assert re.match(hook["files"], path), f"{path!r} should match hook regex"


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "src/agri_core/cli.py",
        "docs/REVIEW_GUIDE.md",
        "tests/fixtures/sources_invalid.csv",
    ],
)
def test_hook_files_regex_rejects(hook: dict[str, Any], path: str) -> None:
    assert not re.match(hook["files"], path), f"{path!r} should not match"


def test_hook_attributes(hook: dict[str, Any]) -> None:
    assert hook["pass_filenames"] is False
    assert hook["verbose"] is True
    assert "--data-dir ." in hook["entry"]
    assert hook["language"] == "system"
