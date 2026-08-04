from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_company_loop_index import build_index
from scripts.run_company_loop_case import run_case

ROOT = Path(__file__).parents[1]
REGISTERED_CASE_COUNT = len(
    json.loads((ROOT / "evals" / "company-loops-v0.3.json").read_text(encoding="utf-8"))
)


def test_bilingual_index_is_strict_offline_and_contains_registered_cases(
    tmp_path: Path,
) -> None:
    path = build_index(tmp_path / "index.html")
    text = path.read_text(encoding="utf-8")

    assert text.count('class="case-card"') == REGISTERED_CASE_COUNT
    assert "Registered company-loop validation" in text
    assert "辅助来源选择" in text
    assert "Draft, not applied / 草稿，尚未应用" in text
    assert "--aux-source" in text
    assert "--disable-auxiliary" in text
    assert "fetch(" not in text
    assert "cdn" not in text.lower()
    assert "http://" not in text
    assert "https://" not in text
    assert "N/A / 不适用" in text


def test_registered_auxiliary_source_runner_is_whitelist_checked(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="not available"):
        run_case(
            "albemarle",
            selected_source_ids=["not-a-source"],
            output_dir=tmp_path / "invalid",
        )

    result = run_case(
        "albemarle",
        selected_source_ids=["albemarle-2025-results"],
        output_dir=tmp_path / "selected",
    )
    assert result["auxiliary_status"] == "warning"
    assert result["selected_source_ids"] == ["albemarle-2025-results"]
    assert result["signals"] == {
        "profitability-unit-economics": "amber",
        "cash-runway": "amber",
    }
    assert result["outcomes"] == {
        "profitability-unit-economics": {
            "status": "evaluated",
            "signal": "amber",
        },
        "cash-runway": {"status": "evaluated", "signal": "amber"},
    }
    assert (tmp_path / "selected" / "report.html").is_file()
    assert not list(
        (ROOT / "examples" / "company-loops" / "albemarle").glob(".manifest-selection-*.json")
    )
