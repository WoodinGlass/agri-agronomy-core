"""Reserved safety classes (ADR-018)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
PARAMS = ROOT / "dictionary" / "parameters.core.yaml"
RESERVED = frozenset({"toxicity_limit", "regulatory"})


def test_no_parameter_uses_reserved_safety_classes() -> None:
    """No parameter may use `toxicity_limit` or `regulatory` (ADR-018).

    Enabling either class requires a new ADR that defines the hazard model,
    the source class and the review workflow.
    """
    data = yaml.safe_load(PARAMS.read_text(encoding="utf-8"))
    offenders = sorted(
        key for key, param in data["parameters"].items() if param.get("safety_class") in RESERVED
    )
    assert not offenders, (
        f"parameters use reserved safety classes (ADR-018): {offenders}. "
        "Write an ADR before enabling a reserved class."
    )


def test_dose_cap_is_the_only_active_safety_class() -> None:
    """`dose_cap` is the only safety-critical class in use (ADR-018)."""
    data = yaml.safe_load(PARAMS.read_text(encoding="utf-8"))
    used = {
        param.get("safety_class")
        for param in data["parameters"].values()
        if param.get("safety_class") not in (None, "none")
    }
    assert used == {"dose_cap"}, f"expected only dose_cap in use, found {sorted(used)}"
