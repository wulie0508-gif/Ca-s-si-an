from __future__ import annotations

import hashlib
from pathlib import Path

from cleantech_finance.company_intake_evidence_control import (
    diagnose_company_intake_evidence_control,
    parse_structured_evidence_metadata,
)
from cleantech_finance.workspace_service import CaseWorkspaceStore

ROOT = Path(__file__).resolve().parents[1]
ROUND3 = ROOT / "evals" / "double-blind-fa-v0.5" / "round-03"
WEB_ROOT = ROOT / "src" / "cleantech_finance" / "web"


def _artifact(index: int, name: str, payload: bytes) -> dict[str, object]:
    text = payload.decode("utf-8")
    return {
        "id": f"artifact-{index:04d}",
        "file_name": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_size": len(payload),
        "recognition": {
            "structured_evidence_metadata": parse_structured_evidence_metadata(
                name, text
            )
        },
    }


def _round3_artifacts() -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    index = 0
    for directory in ("company-submission", "company-supplement"):
        for path in sorted((ROUND3 / directory).iterdir()):
            index += 1
            artifacts.append(_artifact(index, path.name, path.read_bytes()))
    return artifacts


def _round3_uploads() -> list[tuple[str, bytes, str]]:
    uploads: list[tuple[str, bytes, str]] = []
    media = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
    }
    for directory in ("company-submission", "company-supplement"):
        for path in sorted((ROUND3 / directory).iterdir()):
            uploads.append((path.name, path.read_bytes(), media[path.suffix]))
    return uploads


def test_round3_integrity_authority_duplicates_and_conflicts_fail_closed() -> None:
    result = diagnose_company_intake_evidence_control(_round3_artifacts())

    assert result["applicability"]["status"] == "applicable"
    reconciliation = result["manifest_reconciliation"]
    assert reconciliation["status"] == "blocked"
    assert reconciliation["status_counts"] == {"matched": 18, "mismatch": 1}
    mismatch = [
        item for item in reconciliation["entries"] if item["status"] == "mismatch"
    ]
    assert len(mismatch) == 1
    assert mismatch[0]["filename"] == "07-artifact-provenance-and-duplicates.csv"
    assert mismatch[0]["declared_sha256"].endswith("d0b4")
    assert mismatch[0]["actual_sha256_candidates"] == [
        "ac19fdbb06dee9cad677bb45288588f3fe395efbedee0ee71a5d1e6a0913d0b3"
    ]
    assert len(reconciliation["quarantined_artifact_ids"]) == 2
    assert reconciliation["declaration_or_payload_auto_repaired"] is False

    payload_groups = result["actual_payload_duplicate_groups"]
    duplicated_07 = [
        group
        for group in payload_groups
        if group["sha256"].endswith("d0b3")
    ]
    assert len(duplicated_07) == 1
    assert duplicated_07[0]["artifact_count"] == 2
    assert duplicated_07[0]["candidate_evidence_unit_count"] == 1
    assert duplicated_07[0]["accepted_evidence_unit_count"] == 0
    assert duplicated_07[0]["canonical_artifact_id"] is None

    declared_groups = result["declared_underlying_candidate_groups"]
    assert len(declared_groups) == 1
    p2602 = [
        group
        for group in declared_groups
        if group["declared_underlying_sha256"].startswith("8c0f7a")
    ]
    assert len(p2602) == 1
    assert p2602[0]["underlying_payload_status"] == "missing"
    assert p2602[0]["source_index_quarantined"] is True
    assert p2602[0]["candidate_evidence_unit_count"] == 0
    assert p2602[0]["accepted_evidence_unit_count"] == 0

    forecast_families = [
        family
        for family in result["document_control_families"]
        if family["family_key"].startswith("forecast:")
    ]
    assert forecast_families
    assert all(family["requires_human_selection"] for family in forecast_families)
    assert all(
        family["selected_authoritative_artifact_id"] is None
        for family in result["document_control_families"]
    )
    assert {candidate["version"] for candidate in forecast_families[0]["candidates"]} == {
        "1.0",
        "1.1",
    }

    conflicts = result["structured_conflicts"]
    assert any(item["claim_key"] == "forecast:fy2027e:revenue" for item in conflicts)
    assert any(
        item["claim_key"] == "record:cap table:ceo-founder:percentage"
        for item in conflicts
    )
    assert all(item["resolution_status"] == "unresolved" for item in conflicts)
    assert all(item["selected_candidate"] is None for item in conflicts)

    assert [item["id"] for item in result["questions"]] == [
        "R03-Q01",
        "R03-Q02",
        "R03-Q03",
        "R03-Q04",
    ]
    assert result["integrity_gate"]["status"] == "blocked"
    assert result["selected_authoritative_artifact_id"] is None
    assert result["candidate_response_receipts"]
    assert all(
        item["accepted_as_truth"] is False
        and item["question_closed"] is False
        for item in result["candidate_response_receipts"]
    )
    assert result["boundaries"]["financial_calculation_performed"] is False
    assert result["boundaries"]["deal_or_valuation_created"] is False
    assert result["boundaries"]["aggregate_rating_produced"] is False


def test_result_is_invariant_to_artifact_input_order() -> None:
    artifacts = _round3_artifacts()
    assert diagnose_company_intake_evidence_control(artifacts) == (
        diagnose_company_intake_evidence_control(list(reversed(artifacts)))
    )


def test_missing_invalid_duplicate_and_unlisted_manifest_entries_block() -> None:
    actual_a = b"data_status,value\nSynthetic,1\n"
    manifest = (
        "{\n"
        '  "files": [\n'
        '    {"filename":"a.csv","declared_sha256":"bad","byte_count":30},\n'
        '    {"filename":"a.csv","declared_sha256":"bad","byte_count":30},\n'
        '    {"filename":"missing.csv","declared_sha256":"'
        + "0" * 64
        + '","byte_count":1}\n'
        "  ]\n"
        "}\n"
    ).encode()
    artifacts = [
        _artifact(1, "manifest.json", manifest),
        _artifact(2, "a.csv", actual_a),
        _artifact(3, "unlisted.csv", actual_a + b"x"),
    ]

    result = diagnose_company_intake_evidence_control(artifacts)
    reconciliation = result["manifest_reconciliation"]
    assert reconciliation["status"] == "blocked"
    assert reconciliation["status_counts"] == {
        "duplicate_manifest_entry": 2,
        "missing_upload": 1,
        "unlisted_upload": 1,
    }
    assert set(reconciliation["quarantined_artifact_ids"]) == {
        "artifact-0002",
        "artifact-0003",
    }
    assert result["questions"][0]["id"] == "R03-Q01"


def test_jsonl_response_receipts_are_candidate_only() -> None:
    payload = (
        b'{"question_id":"R03-FA-Q01","response_state":"partial",'
        b'"submitted_files":["evidence.csv"],"remaining_gap":"source missing"}\n'
        b'{"question_id":"R03-FA-Q08","response_state":"answered",'
        b'"submitted_files":[]}\n'
    )
    result = diagnose_company_intake_evidence_control(
        [_artifact(1, "responses.jsonl", payload)]
    )

    receipts = result["candidate_response_receipts"]
    assert [item["question_id"] for item in receipts] == [
        "R03-FA-Q01",
        "R03-FA-Q08",
    ]
    assert receipts[0]["all_referenced_files_uploaded"] is False
    assert all(item["accepted_as_truth"] is False for item in receipts)
    assert all(item["question_closed"] is False for item in receipts)


def test_free_prose_without_exact_structured_fields_is_not_applicable() -> None:
    result = diagnose_company_intake_evidence_control(
        [_artifact(1, "notes.md", b"latest approved signed file is authoritative")]
    )
    assert result["applicability"]["status"] == "not_applicable"
    assert result["questions"] == []
    assert result["boundaries"]["free_prose_truth_inference_used"] is False


def test_workspace_ingests_original_21_files_and_routes_controls(tmp_path: Path) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        case_name="Round 3 unchanged initial and supplement pack",
        case_type="qa",
        workflow_type="company_intake",
        files=_round3_uploads(),
    )

    assert len(created["artifacts"]) == 21
    assert sum(
        artifact["file_name"] == "07-artifact-provenance-and-duplicates.csv"
        for artifact in created["artifacts"]
    ) == 2
    evidence = created["evidence_control_diagnostic"]
    assert evidence["integrity_gate"]["status"] == "blocked"
    assert [item["id"] for item in evidence["questions"]] == [
        "R03-Q01",
        "R03-Q02",
        "R03-Q03",
        "R03-Q04",
    ]
    assert any(
        artifact["recognition"]["structured_evidence_metadata"].get(
            "source_format"
        )
        == "jsonl"
        for artifact in created["artifacts"]
    )

    financial = created["financial_basis_preflight"]
    detected_ids = set(financial["applicability"]["detected_artifact_ids"])
    detected_names = {
        artifact["file_name"]
        for artifact in created["artifacts"]
        if artifact["id"] in detected_ids
    }
    assert detected_names == {
        "03-board-plan-draft-v1.1.csv",
        "04-board-plan-approved-v1.0.csv",
    }
    assert {item["value"] for item in financial["forecast"]["versions"]} == {
        "1.0",
        "1.1",
    }
    assert financial["forecast"]["selected_version"] is None
    assert financial["cash_candidates"] == []

    loaded = store.get_case(created["case_id"])
    assert loaded["dashboard"]["next_action"]["id"] == (
        "review_evidence_control_questions"
    )
    assert loaded["dashboard"]["evidence_control"]["integrity_status"] == (
        "blocked"
    )
    assert loaded["dashboard"]["evidence_control"]["authority"] == (
        "evidence_control_projection_only"
    )


def test_non_financial_as_of_control_rows_do_not_trigger_financial_preflight(
    tmp_path: Path,
) -> None:
    source = ROUND3 / "company-submission"
    names = (
        "01-management-claims.csv",
        "02-counterparty-evidence-register.csv",
        "05-corporate-register-v1.2.csv",
        "06-corporate-register-v2.0.csv",
        "07-artifact-provenance-and-duplicates.csv",
    )
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        files=[(name, (source / name).read_bytes(), "text/csv") for name in names]
    )

    assert created["financial_basis_preflight"]["applicability"]["status"] == (
        "not_applicable"
    )
    assert created["financial_basis_preflight"]["questions"] == []


def test_workbench_exposes_evidence_control_without_auto_acceptance_language() -> None:
    html = (WEB_ROOT / "agent_bridge.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "agent_bridge.js").read_text(encoding="utf-8")

    assert 'id="evidence-control-state"' in html
    assert 'id="evidence-control-signals"' in html
    assert "renderEvidenceControlDiagnostic" in javascript
    assert "review_evidence_control_questions" in javascript
    assert "未自动修正哈希、选择权威版本或解决冲突" in javascript
    assert "均未自动接受为事实或关闭问题" in javascript
