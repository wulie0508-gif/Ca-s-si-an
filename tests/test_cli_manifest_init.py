from __future__ import annotations

import json
from pathlib import Path

from cleantech_finance.cli import _init_manifest


def test_manifest_starter_never_fabricates_missing_revenue_as_zero(
    tmp_path: Path,
) -> None:
    path = tmp_path / "manifest.json"

    _init_manifest(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "financials" not in payload
    assert payload["financial_extraction"] == {
        "enabled": True,
        "source_id": "annual-report",
        "currency": "USD",
        "years": [2024, 2025],
        "fiscal_year_end": "12-31",
    }
    assert '"value": 0' not in path.read_text(encoding="utf-8")
