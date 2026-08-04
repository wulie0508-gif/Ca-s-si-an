from __future__ import annotations

import json
from pathlib import Path

import pytest

import cleantech_finance.valuation_workflow as valuation_workflow_module
from cleantech_finance.deal_service import (
    DealConflictError,
    DealIntegrityError,
    DealPermissionError,
    DealServiceError,
    DealStore,
)

HUMAN = {"id": "fa-001", "role": "fa"}
REVIEWER = {"id": "reviewer-001", "role": "fa_reviewer"}
DEAL_LEAD = {"id": "lead-001", "role": "deal_lead"}
APPROVER = {"id": "approver-001", "role": "approver"}
AGENT = {"id": "codex-001", "role": "codex_agent"}


def _patch_trusted_calculator(
    monkeypatch: pytest.MonkeyPatch,
    calculation: dict,
) -> None:
    monkeypatch.setattr(
        valuation_workflow_module,
        "calculate_screen_from_version",
        lambda _valuation, _version: json.loads(json.dumps(calculation)),
    )


def _create_deal(store: DealStore, *, key: str = "deal-create-001") -> dict:
    return store.create_deal(
        company_id="company-shared-001",
        buyer="Buyer Holdings",
        target="Target CleanTech",
        transaction_scope="100% equity acquisition",
        currency="usd",
        valuation_date="2026-08-03",
        owner="FA Team",
        confidentiality_level="confidential",
        actor=HUMAN,
        reason="Open a separately scoped transaction record",
        idempotency_key=key,
    )


def _create_valuation(store: DealStore, deal: dict, *, key: str = "valuation-create-001") -> dict:
    return store.create_valuation_case(
        deal["deal_id"],
        target_legal_entity="Target CleanTech Co., Ltd.",
        transaction_scope="100% equity acquisition",
        valuation_date="2026-08-03",
        base_currency="USD",
        methods=["trading_comps", "dcf_fcff"],
        actor=HUMAN,
        reason="Start an auditable valuation case",
        idempotency_key=key,
        expected_deal_revision=deal["revision"],
        expected_deal_hash=deal["record_hash"],
    )


def test_deal_header_is_separate_from_company_and_stage_is_human_only(
    tmp_path: Path,
) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)

    assert deal["deal_id"] != deal["company_id"]
    assert deal["company_id"] == "company-shared-001"
    assert deal["deal_header"] == {
        "buyer": "Buyer Holdings",
        "target": "Target CleanTech",
        "transaction_scope": "100% equity acquisition",
        "currency": "USD",
        "valuation_date": "2026-08-03",
        "owner": "FA Team",
        "confidentiality_level": "confidential",
    }
    assert deal["human_confirmed_stage"] is None
    assert deal["workplan"] == []
    assert deal["materials"] == []
    assert deal["issues"] == []
    assert deal["decisions"] == []
    assert "_idempotency" not in deal
    assert "storage_version" not in deal

    with pytest.raises(DealPermissionError, match="human"):
        store.confirm_stage(
            deal["deal_id"],
            stage="shortlist_and_preliminary_valuation",
            actor=AGENT,
            reason="Agent inferred this from documents",
            idempotency_key="stage-agent-denied",
            expected_revision=deal["revision"],
            expected_record_hash=deal["record_hash"],
        )

    confirmed = store.confirm_stage(
        deal["deal_id"],
        stage="shortlist_and_preliminary_valuation",
        actor=HUMAN,
        reason="Deal lead confirmed the live process stage",
        idempotency_key="stage-human-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )

    assert confirmed["revision"] == 2
    assert confirmed["human_confirmed_stage"]["stage"] == ("shortlist_and_preliminary_valuation")
    audit = confirmed["audit_trail"][-1]
    assert audit["old"] is None
    assert audit["new"]["stage"] == "shortlist_and_preliminary_valuation"
    assert audit["reason"] == "Deal lead confirmed the live process stage"
    assert audit["actor"]["type"] == "human"
    assert audit["time"].endswith("Z")

    replay = store.confirm_stage(
        deal["deal_id"],
        stage="shortlist_and_preliminary_valuation",
        actor=HUMAN,
        reason="Deal lead confirmed the live process stage",
        idempotency_key="stage-human-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )
    assert replay == confirmed

    changed_preconditions = (
        (confirmed["revision"], deal["record_hash"]),
        (deal["revision"], confirmed["record_hash"]),
    )
    for expected_revision, expected_record_hash in changed_preconditions:
        with pytest.raises(DealConflictError, match="Idempotency"):
            store.confirm_stage(
                deal["deal_id"],
                stage="shortlist_and_preliminary_valuation",
                actor=HUMAN,
                reason="Deal lead confirmed the live process stage",
                idempotency_key="stage-human-001",
                expected_revision=expected_revision,
                expected_record_hash=expected_record_hash,
            )


def test_create_deal_idempotency_replays_and_rejects_key_reuse(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")
    first = _create_deal(store, key="same-create-key")
    replay = _create_deal(store, key="same-create-key")

    assert replay == first
    assert len(store.list_deals()) == 1

    with pytest.raises(DealConflictError, match="Idempotency"):
        store.create_deal(
            company_id="company-other",
            buyer="Different Buyer",
            target="Different Target",
            transaction_scope="Asset acquisition",
            currency="CNY",
            valuation_date="2026-08-03",
            owner="FA Team",
            confidentiality_level="internal",
            actor=HUMAN,
            reason="Different request",
            idempotency_key="same-create-key",
        )


def test_internal_only_confidentiality_alias_persists_canonical_internal(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")

    deal = store.create_deal(
        company_id="company-internal-only",
        buyer="Buyer Holdings",
        target="Target CleanTech",
        transaction_scope="Internal synthetic screen",
        currency="CNY",
        valuation_date="2026-06-30",
        owner="FA Team",
        confidentiality_level="internal_only",
        actor=HUMAN,
        reason="Accept the documented internal-only vocabulary",
        idempotency_key="internal-only-alias",
    )

    assert deal["deal_header"]["confidentiality_level"] == "internal"
    assert deal["audit_trail"][0]["new"]["confidentiality_level"] == "internal"


def test_create_valuation_idempotency_binds_deal_concurrency_preconditions(
    tmp_path: Path,
) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    first = _create_valuation(store, deal, key="valuation-concurrency-key")
    replay = _create_valuation(store, deal, key="valuation-concurrency-key")

    assert replay == first
    current_deal = store.get_deal(deal["deal_id"])
    with pytest.raises(DealConflictError, match="Idempotency"):
        store.create_valuation_case(
            deal["deal_id"],
            target_legal_entity="Target CleanTech Co., Ltd.",
            transaction_scope="100% equity acquisition",
            valuation_date="2026-08-03",
            base_currency="USD",
            methods=["trading_comps", "dcf_fcff"],
            actor=HUMAN,
            reason="Start an auditable valuation case",
            idempotency_key="valuation-concurrency-key",
            expected_deal_revision=current_deal["revision"],
            expected_deal_hash=current_deal["record_hash"],
        )


def test_valuation_case_rejects_unimplemented_methods(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)

    with pytest.raises(DealServiceError, match="Unsupported P0 valuation methods"):
        store.create_valuation_case(
            deal["deal_id"],
            target_legal_entity="Target CleanTech Co., Ltd.",
            transaction_scope="100% equity acquisition",
            valuation_date="2026-08-03",
            base_currency="USD",
            methods=["precedent_transactions"],
            actor=HUMAN,
            reason="Attempt an unimplemented P0 method",
            idempotency_key="valuation-method-rejected",
            expected_deal_revision=deal["revision"],
            expected_deal_hash=deal["record_hash"],
        )


def test_deal_collections_have_minimum_operating_and_audit_fields(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)

    deal = store.add_task(
        deal["deal_id"],
        title="Confirm LTM financials",
        owner="Analyst A",
        due_date="2026-08-10",
        dependencies=["VDR access"],
        status="in_progress",
        evidence_ids=["material-legacy-1"],
        escalation="Escalate if the ledger is not delivered",
        actor=HUMAN,
        reason="Add the first valuation workplan item",
        idempotency_key="task-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )
    deal = store.add_material(
        deal["deal_id"],
        file_name="financials.xlsx",
        version=1,
        sha256="a" * 64,
        source="Target VDR",
        disclosure_level="clean_team",
        parse_status="parsed_candidate",
        review_status="pending_human",
        actor=AGENT,
        reason="Register file metadata without promoting its contents",
        idempotency_key="material-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )
    deal = store.add_issue(
        deal["deal_id"],
        kind="supplement_request",
        title="Provide debt schedule",
        owner="Target CFO",
        due_date="2026-08-12",
        status="open",
        actor=HUMAN,
        reason="Net debt bridge is incomplete",
        idempotency_key="issue-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )
    deal = store.record_decision(
        deal["deal_id"],
        decision="hold",
        quote_range=None,
        valuation_id=None,
        valuation_version_number=None,
        valuation_version_hash=None,
        actor=DEAL_LEAD,
        reason="Hold until the debt schedule is reviewed",
        idempotency_key="decision-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )

    assert deal["revision"] == 5
    assert deal["workplan"][0]["task_id"].startswith("task-")
    assert deal["materials"][0]["sha256"] == "a" * 64
    assert deal["materials"][0]["created_by"]["type"] == "agent"
    assert deal["issues"][0]["status"] == "open"
    assert deal["decisions"][0]["decision"] == "hold"
    assert all(
        {"old", "new", "reason", "actor", "time"} <= set(event) for event in deal["audit_trail"]
    )


def test_stale_deal_revision_or_hash_is_rejected(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    changed = store.confirm_stage(
        deal["deal_id"],
        stage="strategy_and_mandate",
        actor=HUMAN,
        reason="Mandate confirmed",
        idempotency_key="stage-001",
        expected_revision=deal["revision"],
        expected_record_hash=deal["record_hash"],
    )
    assert changed["revision"] == deal["revision"] + 1

    with pytest.raises(DealConflictError, match="stale"):
        store.add_task(
            deal["deal_id"],
            title="Stale update",
            owner="Analyst",
            due_date=None,
            actor=HUMAN,
            reason="This caller did not refresh",
            idempotency_key="stale-task",
            expected_revision=deal["revision"],
            expected_record_hash=deal["record_hash"],
        )


def test_valuation_inputs_are_immutable_versions_and_agent_stays_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)
    initial_hash = valuation["versions"][0]["version_hash"]

    with pytest.raises(DealPermissionError, match="candidate_input"):
        store.update_valuation_inputs(
            valuation["valuation_id"],
            inputs=[
                {
                    "input_id": "ltm-revenue",
                    "name": "LTM Revenue",
                    "value": 100.0,
                    "status": "confirmed_input",
                }
            ],
            actor=AGENT,
            reason="Agent may not self-confirm an extracted number",
            idempotency_key="input-agent-confirm-denied",
            expected_version_number=1,
            expected_version_hash=initial_hash,
        )

    candidate = store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=[
            {
                "input_id": "ltm-revenue",
                "name": "LTM Revenue",
                "value": 100.0,
                "currency": "USD",
                "unit": "million",
                "source_id": "material-001",
            }
        ],
        actor=AGENT,
        reason="Extract a candidate number from the VDR file",
        idempotency_key="input-agent-001",
        expected_version_number=1,
        expected_version_hash=initial_hash,
    )
    assert candidate["version_number"] == 2
    assert candidate["status"] == "inputs_incomplete"
    assert candidate["inputs"][0]["status"] == "candidate_input"
    assert candidate["inputs"][0]["human_confirmed"] is False
    assert candidate["previous_version_hash"] == initial_hash

    _patch_trusted_calculator(
        monkeypatch,
        {
            "used_input_ids": ["ltm-revenue"],
            "hard_failures": [],
            "placeholders": [],
            "calculation_integrity": {"status": "passed"},
            "decision_readiness": {"blocking_reasons": [], "warnings": []},
        },
    )
    with pytest.raises(DealPermissionError, match="Candidate inputs"):
        store.calculate_valuation(
            valuation["valuation_id"],
            actor=AGENT,
            reason="Run deterministic screen",
            idempotency_key="calc-candidate-denied",
            expected_version_number=2,
            expected_version_hash=candidate["version_hash"],
        )

    confirmed = store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=[
            {
                "input_id": "ltm-revenue",
                "name": "LTM Revenue",
                "value": 100.0,
                "currency": "USD",
                "unit": "million",
                "source_id": "material-001",
                "status": "confirmed_input",
                "human_confirmed": True,
            }
        ],
        actor=HUMAN,
        reason="FA checked the source and confirmed the input",
        idempotency_key="input-human-001",
        expected_version_number=2,
        expected_version_hash=candidate["version_hash"],
    )
    assert confirmed["version_number"] == 3
    assert confirmed["inputs"][0]["authority"] == "human_confirmed"

    persisted = store.get_valuation(valuation["valuation_id"])
    assert len(persisted["versions"]) == 3
    assert persisted["versions"][0]["version_hash"] == initial_hash
    assert persisted["versions"][1] == candidate
    assert persisted["versions"][2] == confirmed
    input_audit = persisted["audit_trail"][-1]
    assert input_audit["old"]["inputs"][0]["status"] == "candidate_input"
    assert input_audit["new"]["inputs"][0]["status"] == "confirmed_input"

    replay = store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=[
            {
                "input_id": "ltm-revenue",
                "name": "LTM Revenue",
                "value": 100.0,
                "currency": "USD",
                "unit": "million",
                "source_id": "material-001",
                "status": "confirmed_input",
                "human_confirmed": True,
            }
        ],
        actor=HUMAN,
        reason="FA checked the source and confirmed the input",
        idempotency_key="input-human-001",
        expected_version_number=2,
        expected_version_hash=candidate["version_hash"],
    )
    assert replay == confirmed

    changed_preconditions = (
        (confirmed["version_number"], candidate["version_hash"]),
        (candidate["version_number"], confirmed["version_hash"]),
    )
    for expected_version_number, expected_version_hash in changed_preconditions:
        with pytest.raises(DealConflictError, match="Idempotency"):
            store.update_valuation_inputs(
                valuation["valuation_id"],
                inputs=[
                    {
                        "input_id": "ltm-revenue",
                        "name": "LTM Revenue",
                        "value": 100.0,
                        "currency": "USD",
                        "unit": "million",
                        "source_id": "material-001",
                        "status": "confirmed_input",
                        "human_confirmed": True,
                    }
                ],
                actor=HUMAN,
                reason="FA checked the source and confirmed the input",
                idempotency_key="input-human-001",
                expected_version_number=expected_version_number,
                expected_version_hash=expected_version_hash,
            )


def test_valuation_state_machine_review_and_approval_are_human_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)
    draft = valuation["versions"][-1]
    input_version = store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=[
            {
                "input_id": "ltm-ebitda",
                "name": "LTM EBITDA",
                "value": 20.0,
                "source_id": "material-001",
                "status": "confirmed_input",
                "human_confirmed": True,
            }
        ],
        actor=HUMAN,
        reason="Confirm an input for the screen",
        idempotency_key="input-001",
        expected_version_number=draft["version_number"],
        expected_version_hash=draft["version_hash"],
    )
    _patch_trusted_calculator(
        monkeypatch,
        {
            "used_input_ids": ["ltm-ebitda"],
            "enterprise_value_range": [140.0, 180.0],
            "hard_failures": [],
            "placeholders": [],
            "calculation_integrity": {"status": "passed"},
            "decision_readiness": {
                "status": "screen_grade",
                "blocking_reasons": [],
                "warnings": ["FA review has not been recorded."],
                "human_review_required": True,
            },
        },
    )
    calculated = store.calculate_valuation(
        valuation["valuation_id"],
        actor=AGENT,
        reason="Execute deterministic formulas only",
        idempotency_key="calc-001",
        expected_version_number=input_version["version_number"],
        expected_version_hash=input_version["version_hash"],
    )
    assert calculated["status"] == "calculated_screen_grade"
    assert calculated["calculation"]["authority"] == "screen_grade_only"
    assert calculated["calculation"]["formal_valuation_opinion"] is False

    with pytest.raises(DealServiceError, match="review.decision"):
        store.review_valuation(
            valuation["valuation_id"],
            review={},
            actor=APPROVER,
            reason="An empty review must not advance the lifecycle",
            idempotency_key="review-empty-denied",
            expected_version_number=calculated["version_number"],
            expected_version_hash=calculated["version_hash"],
        )

    with pytest.raises(DealPermissionError, match="human"):
        store.review_valuation(
            valuation["valuation_id"],
            review={"decision": "accepted_for_review"},
            actor=AGENT,
            reason="Agent may not review",
            idempotency_key="review-agent-denied",
            expected_version_number=calculated["version_number"],
            expected_version_hash=calculated["version_hash"],
        )

    reviewed = store.review_valuation(
        valuation["valuation_id"],
        review={"decision": "accepted", "notes": "Inputs and bridge checked"},
        actor=APPROVER,
        reason="FA completed model review",
        idempotency_key="review-human-001",
        expected_version_number=calculated["version_number"],
        expected_version_hash=calculated["version_hash"],
    )
    assert reviewed["status"] == "fa_reviewed"
    assert reviewed["calculation"]["decision_readiness"] == {
        "status": "fa_reviewed",
        "blocking_reasons": [],
        "warnings": [],
        "human_review_required": False,
    }

    with pytest.raises(DealPermissionError, match="human"):
        store.approve_valuation(
            valuation["valuation_id"],
            use="internal",
            actor=AGENT,
            reason="Agent may not approve",
            idempotency_key="approve-agent-denied",
            expected_version_number=reviewed["version_number"],
            expected_version_hash=reviewed["version_hash"],
        )

    with pytest.raises(DealConflictError, match="External approval requires"):
        store.approve_valuation(
            valuation["valuation_id"],
            use="external",
            actor=APPROVER,
            reason="Attempt to skip internal approval",
            idempotency_key="approve-external-too-early",
            expected_version_number=reviewed["version_number"],
            expected_version_hash=reviewed["version_hash"],
        )

    internal = store.approve_valuation(
        valuation["valuation_id"],
        use="internal",
        actor=APPROVER,
        reason="Approve for internal deal-team discussion",
        idempotency_key="approve-internal-001",
        expected_version_number=reviewed["version_number"],
        expected_version_hash=reviewed["version_hash"],
    )
    assert internal["calculation"]["decision_readiness"]["status"] == (
        "approved_for_internal_use"
    )
    external = store.approve_valuation(
        valuation["valuation_id"],
        use="external",
        actor=APPROVER,
        reason="Approve this reviewed version for controlled external use",
        idempotency_key="approve-external-001",
        expected_version_number=internal["version_number"],
        expected_version_hash=internal["version_hash"],
    )
    assert external["calculation"]["decision_readiness"]["status"] == (
        "approved_for_external_use"
    )
    superseded = store.supersede_valuation(
        valuation["valuation_id"],
        actor=REVIEWER,
        reason="A new valuation date will be used",
        idempotency_key="supersede-001",
        expected_version_number=external["version_number"],
        expected_version_hash=external["version_hash"],
    )

    assert [
        version["status"] for version in store.get_valuation(valuation["valuation_id"])["versions"]
    ] == [
        "draft",
        "inputs_incomplete",
        "calculated_screen_grade",
        "fa_reviewed",
        "approved_for_internal_use",
        "approved_for_external_use",
        "superseded",
    ]
    assert superseded["status"] == "superseded"


def test_each_calculation_is_a_new_version_but_same_key_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)
    first_input = store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=[
            {
                "input_id": "revenue",
                "name": "Revenue",
                "value": 10,
                "source_id": "source-1",
                "status": "confirmed_input",
                "human_confirmed": True,
            }
        ],
        actor=HUMAN,
        reason="Confirm revenue",
        idempotency_key="input-001",
        expected_version_number=1,
        expected_version_hash=valuation["current_version_hash"],
    )
    _patch_trusted_calculator(
        monkeypatch,
        {
            "used_input_ids": ["revenue"],
            "enterprise_value": 50,
            "hard_failures": [],
            "placeholders": [],
            "calculation_integrity": {"status": "passed"},
            "decision_readiness": {"blocking_reasons": [], "warnings": []},
        },
    )
    first = store.calculate_valuation(
        valuation["valuation_id"],
        actor=AGENT,
        reason="First deterministic calculation",
        idempotency_key="calc-same",
        expected_version_number=first_input["version_number"],
        expected_version_hash=first_input["version_hash"],
    )
    replay = store.calculate_valuation(
        valuation["valuation_id"],
        actor=AGENT,
        reason="First deterministic calculation",
        idempotency_key="calc-same",
        expected_version_number=first_input["version_number"],
        expected_version_hash=first_input["version_hash"],
    )
    second = store.calculate_valuation(
        valuation["valuation_id"],
        actor=AGENT,
        reason="Explicitly create another calculation snapshot",
        idempotency_key="calc-new",
        expected_version_number=first["version_number"],
        expected_version_hash=first["version_hash"],
    )

    assert replay == first
    assert second["version_number"] == first["version_number"] + 1
    assert second["previous_version_hash"] == first["version_hash"]
    assert second["calculation_hash"] == first["calculation_hash"]
    assert second["version_hash"] != first["version_hash"]


def test_internal_approval_is_blocked_by_hard_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)
    input_version = store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=[],
        actor=HUMAN,
        reason="Record that required inputs remain absent",
        idempotency_key="empty-input-version",
        expected_version_number=1,
        expected_version_hash=valuation["current_version_hash"],
    )
    _patch_trusted_calculator(
        monkeypatch,
        {
            "used_input_ids": [],
            "enterprise_value": None,
            "hard_failures": ["missing_net_debt_bridge"],
            "placeholders": [],
            "calculation_integrity": {"status": "failed"},
            "decision_readiness": {
                "status": "not_ready",
                "blocking_reasons": ["Missing net debt bridge"],
                "warnings": [],
                "human_review_required": True,
            },
        },
    )
    calculated = store.calculate_valuation(
        valuation["valuation_id"],
        actor=AGENT,
        reason="Return a screen with an explicit hard failure",
        idempotency_key="failed-calc",
        expected_version_number=input_version["version_number"],
        expected_version_hash=input_version["version_hash"],
    )
    assert calculated["status"] == "inputs_incomplete"
    assert calculated["calculation"]["decision_readiness"]["status"] == "not_ready"
    with pytest.raises(DealConflictError, match="calculated screen-grade"):
        store.review_valuation(
            valuation["valuation_id"],
            review={"decision": "reviewed_with_failure"},
            actor=REVIEWER,
            reason="A failed calculation must not enter the review lifecycle",
            idempotency_key="failed-review",
            expected_version_number=calculated["version_number"],
            expected_version_hash=calculated["version_hash"],
        )


def test_calculation_output_cannot_be_injected_through_deal_store(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")
    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)

    with pytest.raises(TypeError, match="unexpected keyword argument 'calculation'"):
        store.calculate_valuation(
            valuation["valuation_id"],
            calculation={
                "used_input_ids": [],
                "enterprise_value": 999999999,
                "hard_failures": [],
            },
            actor=AGENT,
            reason="Attempt to inject a forged valuation output",
            idempotency_key="forged-calculation",
            expected_version_number=1,
            expected_version_hash=valuation["current_version_hash"],
        )


def test_persisted_hash_and_version_concurrency_detect_tampering(tmp_path: Path) -> None:
    root = tmp_path / "deals"
    store = DealStore(root)
    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)

    with pytest.raises(DealConflictError, match="stale"):
        store.update_valuation_inputs(
            valuation["valuation_id"],
            inputs=[],
            actor=HUMAN,
            reason="Use a deliberately stale version hash",
            idempotency_key="stale-input",
            expected_version_number=1,
            expected_version_hash="0" * 64,
        )

    path = root / deal["deal_id"] / "deal.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["deal_header"]["buyer"] = "Tampered Buyer"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DealIntegrityError, match="hash mismatch"):
        store.get_deal(deal["deal_id"])


def test_invalid_actor_type_and_non_finite_json_are_rejected(tmp_path: Path) -> None:
    store = DealStore(tmp_path / "deals")
    with pytest.raises(DealPermissionError, match="conflicts"):
        store.create_deal(
            company_id="company-1",
            buyer="Buyer",
            target="Target",
            transaction_scope="Shares",
            currency="USD",
            valuation_date="2026-08-03",
            owner="FA",
            confidentiality_level="internal",
            actor={"id": "agent", "role": "fa", "type": "agent"},
            reason="Actor declaration conflicts",
            idempotency_key="actor-conflict",
        )

    deal = _create_deal(store)
    valuation = _create_valuation(store, deal)
    with pytest.raises(DealServiceError, match="finite JSON"):
        store.update_valuation_inputs(
            valuation["valuation_id"],
            inputs=[{"name": "Bad value", "value": float("nan")}],
            actor=AGENT,
            reason="Reject NaN before persistence",
            idempotency_key="nan-input",
            expected_version_number=1,
            expected_version_hash=valuation["current_version_hash"],
        )
