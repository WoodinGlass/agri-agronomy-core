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
    raise AssertionError("agri-core-validate hook not found")


def test_local_repo_is_last(config: dict[str, Any]) -> None:
    assert config["repos"][-1]["repo"] == "local"


@pytest.mark.parametrize(
    "path",
    [
        "src/agri_core/_samples/sample_pack/pack.toml",
        "src/agri_core/_samples/sample_pack/sources.csv",
        "schema/outcome.schema.json",
        "schema/manifest.schema.json",
    ],
)
def test_hook_files_regex_matches(hook: dict[str, Any], path: str) -> None:
    assert re.match(hook["files"], path)


@pytest.mark.parametrize(
    "path",
    ["README.md", "src/agri_core/cli.py", "tests/fixtures/sources/valid.csv"],
)
def test_hook_files_regex_rejects(hook: dict[str, Any], path: str) -> None:
    assert not re.match(hook["files"], path)


def test_hook_attributes(hook: dict[str, Any]) -> None:
    assert hook["pass_filenames"] is False
    assert hook["verbose"] is True
    assert "src/agri_core/_samples/sample_pack" in hook["entry"]
    assert hook["language"] == "system"
