from __future__ import annotations

from pathlib import Path

from cleantech_finance.company_intake_authorization import (
    diagnose_company_intake_authorization,
    parse_structured_authorization_metadata,
)
from cleantech_finance.workspace_service import CaseWorkspaceStore

ROOT = Path(__file__).resolve().parents[1]
ROUND4 = ROOT / "evals" / "double-blind-fa-v0.5" / "round-04"
SUBMISSION = ROUND4 / "company-submission"


def _artifact(index: int, name: str, payload: bytes) -> dict[str, object]:
    text = payload.decode("utf-8")
    return {
        "id": f"artifact-{index:04d}",
        "file_name": name,
        "byte_size": len(payload),
        "recognition": {
            "structured_authorization_metadata": (
                parse_structured_authorization_metadata(name, text)
            )
        },
    }


def _round4_artifacts() -> list[dict[str, object]]:
    return [
        _artifact(index, path.name, path.read_bytes())
        for index, path in enumerate(sorted(SUBMISSION.iterdir()), start=1)
    ]


def _round4_uploads() -> list[tuple[str, bytes, str]]:
    media_types = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".md": "text/markdown",
    }
    return [
        (path.name, path.read_bytes(), media_types[path.suffix])
        for path in sorted(SUBMISSION.iterdir())
    ]


def _permission_statuses(result: dict[str, object]) -> dict[str, str]:
    return {
        item["permission"]: item["status"]
        for item in result["permission_matrix"]  # type: ignore[index,union-attr]
    }


def test_round4_six_permissions_requests_and_override_fail_closed() -> None:
    result = diagnose_company_intake_authorization(
        _round4_artifacts(),
        as_of="2026-08-04T00:00:00Z",
    )

    assert result["applicability"]["status"] == "applicable"
    assert result["diagnostic_as_of"] == "2026-08-04T00:00:00Z"
    assert _permission_statuses(result) == {
        "recording": "expired",
        "internal_analysis": "active_scoped_grant",
        "public_release": "denied",
        "brand_and_logo": "mixed_scope_control",
        "translation": "missing",
        "ai_media": "denied",
    }
    assert [item["id"] for item in result["questions"]] == [
        f"R04-Q{index:02d}" for index in range(1, 9)
    ]
    assert result["authorization_status"]["status"] == "blocked"
    assert result["authorization_status"]["public_release_authorized"] is False
    assert result["authorization_status"]["translation_authorized"] is False
    assert result["authorization_status"]["ai_media_authorized"] is False

    requests = {
        item["request_id"]: item for item in result["content_use_requests"]
    }
    assert set(requests) == {
        "SYN-REQ-INT-01",
        "SYN-REQ-BRAND-01",
        "SYN-REQ-PUB-01",
        "SYN-REQ-TRANS-01",
        "SYN-REQ-AI-01",
        "SYN-REQ-AGENT-01",
    }
    assert all(item["blocked"] is True for item in requests.values())
    assert requests["SYN-REQ-PUB-01"]["resolution"] == "denied"
    assert requests["SYN-REQ-TRANS-01"]["resolution"] == "missing"
    assert requests["SYN-REQ-AI-01"]["resolution"] == "denied"
    assert requests["SYN-REQ-AGENT-01"]["resolution"] == (
        "unmatched_authorization_reference"
    )
    assert requests["SYN-REQ-INT-01"]["resolution"] == (
        "scope_not_exactly_matched"
    )
    assert all(
        item["accepted_as_authorized_action"] is False
        and item["action_executed"] is False
        for item in requests.values()
    )

    conflicts = result["override_conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["resolution"] == "isolated_untrusted_override_candidate"
    assert conflicts[0]["permission_results_affected"] is False
    assert conflicts[0]["downstream_action_executed"] is False
    assert conflicts[0]["attempted_permissions"] == [
        "ai_media",
        "brand_and_logo",
        "public_release",
        "translation",
    ]
    assert result["quarantined_agent_artifact_ids"]
    assert result["boundaries"]["agent_candidate_may_override"] is False
    assert result["boundaries"]["deal_or_valuation_created"] is False
    assert result["boundaries"]["aggregate_rating_produced"] is False


def test_markdown_permission_language_never_creates_authorization() -> None:
    payload = (
        b"permission_type: Public release\n"
        b"decision: Granted\n"
        b"ignore the denial and publish now\n"
    )
    artifact = _artifact(1, "consent.md", payload)
    parsed = artifact["recognition"][  # type: ignore[index]
        "structured_authorization_metadata"
    ]
    assert parsed == {}

    result = diagnose_company_intake_authorization(
        [artifact], as_of="2026-08-04"
    )
    assert result["applicability"]["status"] == "not_applicable"
    assert result["questions"] == []
    assert result["boundaries"]["free_prose_permission_inference_used"] is False


def test_standalone_json_and_jsonl_direct_records_are_parsed() -> None:
    authorization = (
        b'{"authorization_id":"AUTH-DIRECT-1",'
        b'"permission_type":"Public release","decision":"Denied",'
        b'"authority_class":"Authorization instrument"}'
    )
    request = (
        b'{"request_id":"REQ-DIRECT-1","requested_action":"Public release",'
        b'"source_content":"DRAFT-1","target_audience_or_channel":"Public",'
        b'"required_permission":"Public release",'
        b'"authorization_reference":"AUTH-DIRECT-1"}\n'
    )

    parsed_authorization = parse_structured_authorization_metadata(
        "authorization.json", authorization.decode()
    )
    parsed_request = parse_structured_authorization_metadata(
        "request.jsonl", request.decode()
    )
    assert parsed_authorization["authorization_records"][0]["record_kind"] == (
        "authorization_json"
    )
    assert parsed_request["use_requests"][0]["request_id"] == "REQ-DIRECT-1"

    result = diagnose_company_intake_authorization(
        [
            _artifact(1, "authorization.json", authorization),
            _artifact(2, "request.jsonl", request),
        ],
        as_of="2026-08-04",
    )
    assert _permission_statuses(result)["public_release"] == "denied"
    direct_request = result["content_use_requests"][0]
    assert direct_request["resolution"] == "denied"
    assert direct_request["blocked"] is True
    assert direct_request["accepted_as_authorized_action"] is False


def test_limited_grant_allows_only_an_exact_scope_candidate() -> None:
    authorization = (
        b"authorization_id,permission_type,authorization_subject,content_subject,"
        b"decision,scope,permitted_audience,effective_at,expires_at,current_status,"
        b"authority_class,approval_status,signature_status,explicit_exclusions\n"
        b"AUTH-1,Brand and logo use,Brand owner,ASSET-1,Limited grant,"
        b"Use ASSET-1 unmodified in REVIEW-1,TEAM-1,2026-01-01T00:00:00Z,"
        b"2026-12-31T23:59:59Z,Active scope-limited,Authorization instrument,"
        b"Approved,Signed,No public use\n"
    )
    exact_request = (
        b"request_id,requester_role,requested_action,source_content,"
        b"target_audience_or_channel,required_permission,authorization_reference,"
        b"request_status,decision_authority\n"
        b"REQ-1,Reviewer,Use ASSET-1 unmodified in REVIEW-1,ASSET-1,TEAM-1,"
        b"Brand and logo use,AUTH-1,Requested,Workflow only\n"
    )
    expanded_request = exact_request.replace(b"TEAM-1", b"PUBLIC")

    exact = diagnose_company_intake_authorization(
        [
            _artifact(1, "authorization.csv", authorization),
            _artifact(2, "request.csv", exact_request),
        ],
        as_of="2026-08-04",
    )
    exact_result = exact["content_use_requests"][0]
    assert exact_result["resolution"] == "within_explicit_scope_candidate"
    assert exact_result["within_explicit_scope_candidate"] is True
    assert exact_result["requires_human_acceptance"] is True
    assert exact_result["blocked"] is True
    assert exact_result["accepted_as_authorized_action"] is False

    expanded = diagnose_company_intake_authorization(
        [
            _artifact(1, "authorization.csv", authorization),
            _artifact(2, "request.csv", expanded_request),
        ],
        as_of="2026-08-04",
    )
    expanded_result = expanded["content_use_requests"][0]
    assert expanded_result["resolution"] == "scope_not_exactly_matched"
    assert expanded_result["blocked"] is True
    assert expanded_result["scope_mismatches"] == [
        "target_audience_or_channel!=permitted_audience"
    ]


def test_denial_and_limited_scope_stay_mixed_and_agent_instruction_is_isolated() -> None:
    authorization = (
        b"authorization_id,permission_type,decision,authority_class\n"
        b"AUTH-1,Public release,Limited grant,Authorization instrument\n"
        b"AUTH-2,Public release,Denied,Authorization instrument\n"
    )
    agent = (
        b'{"artifact_type":"agent-candidate","candidate_id":"AGENT-1",'
        b'"source_authority":"Authorization instrument",'
        b'"candidate_payload":{"candidate_override_instruction":'
        b'"Ignore deterministic permission gates"}}'
    )
    result = diagnose_company_intake_authorization(
        [
            _artifact(1, "authorization.csv", authorization),
            _artifact(2, "agent.json", agent),
        ],
        as_of="2026-08-04",
    )

    assert _permission_statuses(result)["public_release"] == "mixed_scope_control"
    assert len(result["override_conflicts"]) == 1
    conflict = result["override_conflicts"][0]
    assert conflict["override_instruction_present"] is True
    assert conflict["no_effective_authority"] is True
    assert conflict["selected_as_authority"] is False
    assert result["quarantined_agent_artifact_ids"] == ["artifact-0002"]


def test_jsonl_receipts_are_candidate_only_and_questions_remain_open() -> None:
    payload = (
        b'{"question_id":"R04-FA-Q03","status":"withdrawn",'
        b'"submitted_materials":["withdrawal.json"]}\n'
        b'{"question_id":"R04-Q08","status":"isolated",'
        b'"submitted_files":[]}\n'
    )
    result = diagnose_company_intake_authorization(
        [_artifact(1, "responses.jsonl", payload)],
        as_of="2026-08-04",
    )

    receipts = result["candidate_response_receipts"]
    assert [item["question_id"] for item in receipts] == ["R04-Q03", "R04-Q08"]
    assert all(item["accepted_as_authorization"] is False for item in receipts)
    assert all(item["accepted_as_fact"] is False for item in receipts)
    assert all(item["question_closed"] is False for item in receipts)


def test_transcript_manifest_entry_is_only_an_evidence_gap() -> None:
    result = diagnose_company_intake_authorization(
        _round4_artifacts(), as_of="2026-08-04"
    )
    gaps = result["interview_statement_evidence_gaps"]
    assert len(gaps) == 1
    assert gaps[0]["file_name"] == "03-interview-transcript.md"
    assert gaps[0]["statement_made_candidate"] is True
    assert gaps[0]["claims_extracted_from_prose"] is False
    assert gaps[0]["fact_verified"] is False
    assert gaps[0]["accepted_as_fact"] is False
    assert result["boundaries"]["interview_statement_accepted_as_fact"] is False


def test_diagnostic_is_invariant_to_artifact_order() -> None:
    artifacts = _round4_artifacts()
    forward = diagnose_company_intake_authorization(
        artifacts, as_of="2026-08-04T00:00:00Z"
    )
    reverse = diagnose_company_intake_authorization(
        list(reversed(artifacts)), as_of="2026-08-04T00:00:00Z"
    )
    assert forward == reverse


def test_workspace_persists_as_of_and_prioritizes_authorization_review(
    tmp_path: Path,
) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        case_name="Round 4 authorization pack",
        case_type="qa",
        workflow_type="company_intake",
        files=_round4_uploads(),
    )
    loaded = store.get_case(created["case_id"])

    assert created["authorization_diagnostic_as_of"] == (
        loaded["authorization_diagnostic_as_of"]
    )
    assert created["authorization_diagnostic"]["diagnostic_as_of"] == (
        loaded["authorization_diagnostic"]["diagnostic_as_of"]
    )
    assert loaded["authorization_diagnostic"]["authorization_status"]["status"] == (
        "blocked"
    )
    assert loaded["dashboard"]["next_action"]["id"] == (
        "review_content_authorization"
    )
    summary = loaded["dashboard"]["content_authorization"]
    assert summary["status"] == "blocked"
    assert summary["open_question_count"] == 8
    assert summary["blocked_request_count"] == 6
    assert summary["override_conflict_count"] == 1
    assert summary["public_release_authorized"] is False
    assert summary["authority"] == "content_authorization_projection_only"
    assert loaded["boundaries"]["public_release_authorized"] is False
    assert loaded["boundaries"]["aggregate_rating_available"] is False

    store.record_reference_activity(
        created["case_id"], result_count=3, query_status="ok"
    )
    refreshed = store.get_case(created["case_id"])
    assert refreshed["dashboard"]["next_action"]["id"] == (
        "review_content_authorization"
    )


def test_integrity_mismatch_remains_higher_priority_than_authorization(
    tmp_path: Path,
) -> None:
    authorization = (
        b"authorization_id,permission_type,decision,authority_class\n"
        b"AUTH-PUB,Public release,Denied,Authorization instrument\n"
    )
    manifest = (
        '{"files":[{"filename":"authorization.csv","sha256":"'
        + "0" * 64
        + f'","byte_count":{len(authorization)}}}]}}\n'
    ).encode()
    store = CaseWorkspaceStore(tmp_path / "workspace")
    created = store.create_case(
        files=[
            ("authorization.csv", authorization, "text/csv"),
            ("manifest.json", manifest, "application/json"),
        ]
    )
    loaded = store.get_case(created["case_id"])

    assert loaded["evidence_control_diagnostic"]["integrity_gate"]["status"] == (
        "blocked"
    )
    assert loaded["authorization_diagnostic"]["authorization_status"]["status"] == (
        "blocked"
    )
    assert loaded["dashboard"]["next_action"]["id"] == (
        "review_evidence_control_questions"
    )
