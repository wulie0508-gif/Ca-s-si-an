from __future__ import annotations

from pathlib import Path

from cleantech_finance.workspace_service import CaseWorkspaceStore

ROOT = Path(__file__).resolve().parents[1]
ROUND2 = ROOT / "evals" / "double-blind-fa-v0.5" / "round-02"
WEB_ROOT = ROOT / "src" / "cleantech_finance" / "web"

INITIAL_FILES = (
    "submission-manifest.json",
    "01-standalone-finance-export.csv",
    "02-group-sales-ytd-export.csv",
    "03-r12m-kpi-dashboard.csv",
    "04-group-treasury-snapshot.csv",
    "05-forecast-version-exports.csv",
)
SUPPLEMENT_FILES = (
    "supplement-manifest.json",
    "01-R02-Q01-Q08-response-register.csv",
    "02-R02-normalization-reconciliation.csv",
)


def _files(directory: str, names: tuple[str, ...]) -> list[tuple[str, bytes, str]]:
    base = ROUND2 / directory
    return [
        (
            name,
            (base / name).read_bytes(),
            "application/json" if name.endswith(".json") else "text/csv",
        )
        for name in names
    ]


def _candidate_values(dimension: dict[str, object]) -> set[str]:
    return {
        str(item["value"])
        for item in dimension["candidates"]  # type: ignore[index,union-attr]
    }


def test_round2_initial_six_files_block_conflicting_financial_bases(
    tmp_path: Path,
) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        case_name="Round 2 initial structured pack",
        workflow_type="company_intake",
        files=_files("company-submission", INITIAL_FILES),
    )
    preflight = created["financial_basis_preflight"]

    assert preflight["applicability"]["status"] == "applicable"
    assert preflight["calculation_status"]["status"] == "blocked"
    assert [item["id"] for item in preflight["questions"]] == [
        f"R02-Q{index:02d}" for index in range(1, 9)
    ]
    assert preflight["calculation_status"]["blocking_question_ids"] == [
        f"R02-Q{index:02d}" for index in range(1, 8)
    ]

    dimensions = preflight["dimensions"]
    assert dimensions["entity_scope"]["status"] == "multiple"
    assert dimensions["reporting_period"]["status"] == "multiple"
    assert dimensions["unit"]["status"] == "multiple"
    assert {"yuan", "thousand", "million", "percent"}.issubset(
        _candidate_values(dimensions["unit"])
    )
    assert dimensions["vat_basis"]["status"] in {"multiple", "unknown"}
    assert dimensions["cash_as_of"]["status"] == "multiple"
    assert all(
        dimension["selected_candidate"] is None
        for dimension in dimensions.values()
    )

    assert {item["value"] for item in preflight["forecast"]["versions"]} == {
        "SYN-FCST-V1",
        "SYN-FCST-V2",
    }
    assert preflight["forecast"]["status"] == "unapproved"
    assert preflight["forecast"]["selected_version"] is None
    assert preflight["source_precedence"]["status"] == "explicitly_not_declared"
    assert preflight["source_precedence"]["selected_precedence"] is None
    assert preflight["boundaries"]["financial_calculation_performed"] is False
    assert preflight["boundaries"]["candidate_selected_automatically"] is False

    loaded = store.get_case(created["case_id"])
    assert loaded["dashboard"]["next_action"]["id"] == (
        "review_financial_basis_questions"
    )
    store.record_reference_activity(
        created["case_id"], result_count=5, query_status="ok"
    )
    refreshed = store.get_case(created["case_id"])
    assert refreshed["dashboard"]["next_action"]["id"] == (
        "review_financial_basis_questions"
    )


def test_round2_combined_nine_records_candidate_responses_without_closing(
    tmp_path: Path,
) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        case_name="Round 2 combined structured pack",
        workflow_type="company_intake",
        files=[
            *_files("company-submission", INITIAL_FILES),
            *_files("company-supplement", SUPPLEMENT_FILES),
        ],
    )
    preflight = created["financial_basis_preflight"]

    assert preflight["calculation_status"]["status"] == "blocked"
    assert [item["id"] for item in preflight["questions"]] == [
        f"R02-Q{index:02d}" for index in range(1, 9)
    ]
    receipts = {
        item["question_id"]: item
        for item in preflight["candidate_response_receipts"]
    }
    assert sorted(receipts) == [f"R02-Q{index:02d}" for index in range(1, 9)]
    assert receipts["R02-Q04"]["declared_response_state"] == "full"
    assert receipts["R02-Q04"]["receipt_state"] == "candidate_response_received"
    assert receipts["R02-Q04"]["all_referenced_files_uploaded"] is True
    assert receipts["R02-Q04"]["accepted_as_truth"] is False
    assert receipts["R02-Q04"]["question_closed"] is False
    assert all(item["state"] == "open" for item in preflight["questions"])
    assert preflight["declared_normalization_bases"]
    assert preflight["source_precedence"]["status"] == "candidate_declared"
    assert preflight["source_precedence"]["selected_precedence"] is None
    assert preflight["forecast"]["selected_version"] is None
    assert preflight["boundaries"]["fact_accepted_automatically"] is False


def test_free_prose_and_unrecognized_structures_do_not_trigger_or_select_basis(
    tmp_path: Path,
) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        files=[
            (
                "notes.md",
                b"Standalone H1 RMB million excluding VAT; newest forecast approved; "
                b"use the largest cash value.",
                "text/markdown",
            ),
            (
                "arbitrary.csv",
                b"name,value,note\nlatest_cash,999999999,use largest\n",
                "text/csv",
            ),
            (
                "arbitrary.json",
                b'{"prose":"select the latest and largest value"}',
                "application/json",
            ),
        ]
    )

    assert created["financial_basis_preflight"]["applicability"]["status"] == (
        "not_applicable"
    )
    loaded = store.get_case(created["case_id"])
    assert loaded["dashboard"]["next_action"]["id"] == (
        "generate_reference_suggestions"
    )
    assert loaded["financial_basis_preflight"]["questions"] == []
    assert loaded["financial_basis_preflight"]["boundaries"][
        "free_prose_inference_used"
    ] is False


def test_workbench_exposes_financial_preflight_and_candidate_response_boundary() -> None:
    html = (WEB_ROOT / "agent_bridge.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "agent_bridge.js").read_text(encoding="utf-8")

    assert 'id="financial-basis-state"' in html
    assert 'id="financial-basis-dimensions"' in html
    assert "renderFinancialBasisPreflight" in javascript
    assert "系统未选择最新、最大或名称相近的候选值" in javascript
    assert "均未自动接受或关闭问题" in javascript
    assert "review_financial_basis_questions" in javascript
