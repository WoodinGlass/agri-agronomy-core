"""Broken corpus: CSV and TOML strictness as contract.

Fixtures live in tests/fixtures/broken_csv/ and tests/fixtures/broken_toml/.
Each directory has an ``expected.json`` mapping filename to an expectation:

  - broken_csv:  {"exception": <class name>, "match": <regex-safe string>}
  - broken_toml: {"match": <regex-safe string>}

The Python reader must raise the specified exception with a matching
message. Rust parity for these cases ships with Phase B (validate port).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agri_core.pack.errors import (
    PackFieldTooLargeError,
    PackRowTooLargeError,
    PackTableInvalidError,
)
from agri_core.pack.tables import TABLES, read_table
from agri_core.pack.verify import hash_pack_files

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_CSV_EXCEPTIONS = {
    "PackTableInvalidError": PackTableInvalidError,
    "PackFieldTooLargeError": PackFieldTooLargeError,
    "PackRowTooLargeError": PackRowTooLargeError,
}


def _load_expected(kind: str) -> dict[str, dict[str, str]]:
    return json.loads((FIXTURES / kind / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case_id", sorted(_load_expected("broken_csv")))
def test_broken_csv(case_id: str) -> None:
    spec = _load_expected("broken_csv")[case_id]
    data = (FIXTURES / "broken_csv" / case_id).read_bytes()
    exc_cls = _CSV_EXCEPTIONS[spec["exception"]]
    with pytest.raises(exc_cls, match=re.escape(spec["match"])):
        read_table(TABLES["sources"], data, source_name=case_id)


@pytest.mark.parametrize("case_id", sorted(_load_expected("broken_toml")))
def test_broken_toml(case_id: str) -> None:
    spec = _load_expected("broken_toml")[case_id]
    data = (FIXTURES / "broken_toml" / case_id).read_bytes()
    with pytest.raises(PackTableInvalidError, match=re.escape(spec["match"])):
        hash_pack_files({"pack.toml": data}, hash_alg="pre-rfc8785")
