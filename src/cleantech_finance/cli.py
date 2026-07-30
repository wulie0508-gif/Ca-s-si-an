"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .audit import run_audit, validate_audit
from .enterprise_assessment import (
    EnterpriseAssessmentEngine,
    load_assessment_config,
)
from .enterprise_evidence import (
    CompanyDirectoryAdapter,
    EnergyAssetAdapter,
    NexSidecarClient,
    evidence_from_owner_statement,
)
from .enterprise_interview import transcribe_media
from .enterprise_matching import load_matching_config
from .enterprise_reporting import write_enterprise_report
from .enterprise_store import AssessmentStore
from .finance_framework import FINANCE_DIMENSIONS
from .framework import DIMENSIONS
from .ingest import ManifestError
from .onboarding import build_agent_tasks, new_company_case, validate_company_case
from .onboarding_reporting import write_onboarding_artifacts
from .qa_diagnostics import new_qa_case, next_qa_question_status, validate_qa_case
from .qa_reporting import write_qa_artifacts
from .reporting import write_artifacts


def _framework_payload() -> dict[str, object]:
    def item(dimension: object) -> dict[str, object]:
        return {
            "id": dimension.id,
            "category": dimension.category,
            "name": dimension.name,
            "objective": dimension.objective,
            "review_questions": list(dimension.review_questions),
        }

    return {
        "finance": [item(dimension) for dimension in FINANCE_DIMENSIONS],
        "adoption_risk": [item(dimension) for dimension in DIMENSIONS],
    }


def _init_manifest(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    template = {
        "subject": {
            "organization": "Example Clean Energy Company",
            "technology": "Define the exact product and use case",
            "ticker": None,
        },
        "assessment": {
            "as_of": "YYYY-MM-DD",
            "horizon_years": 5,
            "geography": "Target market",
            "value_chain_scope": "Define included upstream and downstream activities",
        },
        "sources": [
            {
                "id": "annual-report",
                "path": "sources/annual-report.txt",
                "title": "Annual report",
                "url": "https://example.com/annual-report",
                "publisher": "Example Clean Energy Company",
                "published": "YYYY-MM-DD",
                "kind": "regulatory_filing",
                "role": "subject",
            }
        ],
        "financials": {
            "currency": "USD",
            "periods": [
                {
                    "period": "FY2025",
                    "fiscal_year": 2025,
                    "period_type": "annual",
                    "start_date": "2025-01-01",
                    "end_date": "2025-12-31",
                    "duration_days": 365,
                    "facts": {
                        "revenue": {
                            "value": 0,
                            "source_id": "annual-report",
                            "locator": "page or line",
                        }
                    },
                }
            ],
        },
        "auxiliary_validation": {
            "enabled": False,
            "selected_source_ids": [],
            "relative_tolerance": 0.001,
            "absolute_tolerance": 0,
            "facts": [],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")


def _init_company_case(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(new_company_case(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _init_qa_case(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(new_qa_case(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_json_object(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _load_json_value(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleantech-finance",
        description="Evidence-first finance and bankability research for clean energy companies.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Run an evidence audit from a manifest")
    audit_parser.add_argument("manifest", help="Path to manifest.json")
    audit_parser.add_argument("--out", default="output", help="Output directory")
    audit_parser.add_argument("--top-k", type=int, default=3, help="Candidates per research lens")
    audit_parser.add_argument(
        "--only",
        nargs="+",
        metavar="DIMENSION_ID",
        help="Run only selected dimension ids (space separated)",
    )

    init_parser = subparsers.add_parser("init", help="Write a starter manifest")
    init_parser.add_argument("path", nargs="?", default="manifest.json")

    framework_parser = subparsers.add_parser("framework", help="Print the research framework")
    framework_parser.add_argument("--json", action="store_true", help="Emit JSON")

    validate_parser = subparsers.add_parser("validate", help="Validate a generated audit.json")
    validate_parser.add_argument("audit_json")

    case_parser = subparsers.add_parser(
        "case",
        help="Create and run the local company interview, evidence and readiness workbench",
    )
    case_subparsers = case_parser.add_subparsers(dest="case_command", required=True)
    case_init = case_subparsers.add_parser("init", help="Write a bilingual company-case template")
    case_init.add_argument("path", nargs="?", default="case.json")
    case_validate = case_subparsers.add_parser("validate", help="Validate a local company case")
    case_validate.add_argument("case_json")
    case_report = case_subparsers.add_parser(
        "report", help="Write the local bilingual evidence-workbench packet"
    )
    case_report.add_argument("case_json")
    case_report.add_argument("--out", default="output-case", help="Output directory")
    case_tasks = case_subparsers.add_parser(
        "agent-tasks", help="Emit optional local-agent evidence task contracts"
    )
    case_tasks.add_argument("case_json")
    case_tasks.add_argument("--out", help="Optional JSON output path; stdout when omitted")

    qa_parser = subparsers.add_parser(
        "qa",
        help="Run the traceable company-entry QA diagnostic and routing layer",
    )
    qa_subparsers = qa_parser.add_subparsers(dest="qa_command", required=True)
    qa_init = qa_subparsers.add_parser(
        "init",
        help="Write an empty QA case for a human-selected company",
    )
    qa_init.add_argument("path", nargs="?", default="qa-case.json")
    qa_next = qa_subparsers.add_parser(
        "next",
        help="Choose the next question from prior structured answers",
    )
    qa_next.add_argument("qa_case_json")
    qa_validate = qa_subparsers.add_parser(
        "validate",
        help="Validate dynamic-QA completeness and field-level traceability",
    )
    qa_validate.add_argument("qa_case_json")
    qa_report = qa_subparsers.add_parser(
        "report",
        help="Write the bilingual profile, triage, gaps, and QA report packet",
    )
    qa_report.add_argument("qa_case_json")
    qa_report.add_argument("--out", default="output-qa", help="Output directory")

    enterprise_parser = subparsers.add_parser(
        "enterprise",
        help="Run the local enterprise assessment and human-review workflow",
    )
    enterprise_subparsers = enterprise_parser.add_subparsers(
        dest="enterprise_command",
        required=True,
    )
    enterprise_init = enterprise_subparsers.add_parser(
        "init-store",
        help="Initialize the authoritative SQLite assessment store",
    )
    enterprise_init.add_argument("database")

    enterprise_create = enterprise_subparsers.add_parser(
        "create",
        help="Create or reuse a Company master and create one assessment Case",
    )
    enterprise_create.add_argument("database")
    enterprise_create.add_argument("intake_json")

    enterprise_ingest = enterprise_subparsers.add_parser(
        "ingest-evidence",
        help="Validate and persist one or more unified evidence objects",
    )
    enterprise_ingest.add_argument("database")
    enterprise_ingest.add_argument("case_id")
    enterprise_ingest.add_argument("evidence_json")

    enterprise_transcribe = enterprise_subparsers.add_parser(
        "transcribe",
        help="Transcribe local interview media and attach case-owned artifacts",
    )
    enterprise_transcribe.add_argument("database")
    enterprise_transcribe.add_argument("case_id")
    enterprise_transcribe.add_argument("media")
    enterprise_transcribe.add_argument("--out", required=True)
    enterprise_transcribe.add_argument("--consent-ref", required=True)
    enterprise_transcribe.add_argument("--language")
    enterprise_transcribe.add_argument("--model", default="base")
    enterprise_transcribe.add_argument("--model-cache")

    enterprise_interview = enterprise_subparsers.add_parser(
        "add-interview",
        help="Attach an existing transcript and optional timestamped owner statements",
    )
    enterprise_interview.add_argument("database")
    enterprise_interview.add_argument("case_id")
    enterprise_interview.add_argument("transcript")
    enterprise_interview.add_argument("--consent-ref", required=True)
    enterprise_interview.add_argument("--language")
    enterprise_interview.add_argument("--model", default="base")
    enterprise_interview.add_argument("--audio")
    enterprise_interview.add_argument("--segments-json")
    enterprise_interview.add_argument("--points-json")

    enterprise_sidecar = enterprise_subparsers.add_parser(
        "sidecar-query",
        help="Query NEX for candidate citations and store only valid unified evidence",
    )
    enterprise_sidecar.add_argument("database")
    enterprise_sidecar.add_argument("case_id")
    enterprise_sidecar.add_argument("question")
    enterprise_sidecar.add_argument("--base-url", default="http://127.0.0.1:8000")
    enterprise_sidecar.add_argument(
        "--mode",
        choices=("internal", "external", "hybrid"),
        default="hybrid",
    )
    enterprise_sidecar.add_argument("--top-k", type=int, default=5)
    enterprise_sidecar.add_argument(
        "--purpose",
        choices=("enterprise_fact", "industry_background"),
        default="enterprise_fact",
    )
    enterprise_sidecar.add_argument("--time-sensitive", action="store_true")

    enterprise_assess = enterprise_subparsers.add_parser(
        "assess",
        help="Run deterministic dimensions, gaps, matching and draft recommendation",
    )
    enterprise_assess.add_argument("database")
    enterprise_assess.add_argument("case_id")
    enterprise_assess.add_argument("--financial-audit")
    enterprise_assess.add_argument("--course-catalog")
    enterprise_assess.add_argument("--policy-catalog")
    enterprise_assess.add_argument("--config")
    enterprise_assess.add_argument("--sidecar-check", action="store_true")
    enterprise_assess.add_argument("--sidecar-url", default="http://127.0.0.1:8000")
    enterprise_assess.add_argument("--actor")
    enterprise_assess.add_argument("--out", default="output-enterprise")

    enterprise_decision = enterprise_subparsers.add_parser(
        "decision",
        help="Submit, approve or reject the latest draft through the locked workflow",
    )
    enterprise_decision.add_argument("database")
    enterprise_decision.add_argument("case_id")
    enterprise_decision.add_argument(
        "action",
        choices=("submit", "approve", "reject"),
    )
    enterprise_decision.add_argument("--actor", required=True)
    enterprise_decision.add_argument("--reason")
    enterprise_decision.add_argument("--eval-dir")

    enterprise_show = enterprise_subparsers.add_parser(
        "show",
        help="Print the complete traceable case bundle",
    )
    enterprise_show.add_argument("database")
    enterprise_show.add_argument("case_id")

    enterprise_company_candidates = enterprise_subparsers.add_parser(
        "company-candidates",
        help="Search the NEX company directory without automatic entity merging",
    )
    enterprise_company_candidates.add_argument("directory_database")
    enterprise_company_candidates.add_argument("name")
    enterprise_company_candidates.add_argument("--limit", type=int, default=10)

    enterprise_asset_candidates = enterprise_subparsers.add_parser(
        "asset-candidates",
        help="Search NEX energy assets and emit candidate evidence",
    )
    enterprise_asset_candidates.add_argument("asset_database")
    enterprise_asset_candidates.add_argument("case_id")
    enterprise_asset_candidates.add_argument("query")
    enterprise_asset_candidates.add_argument("--limit", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "audit":
            if args.top_k < 1 or args.top_k > 10:
                raise ValueError("--top-k must be between 1 and 10")
            audit = run_audit(
                args.manifest,
                top_k=args.top_k,
                only_dimensions=set(args.only) if args.only else None,
            )
            paths = write_artifacts(audit, args.out)
            print(json.dumps({"validation": audit["validation"], "artifacts": paths}, indent=2))
            return 0 if audit["validation"]["passed"] else 2
        if args.command == "init":
            _init_manifest(Path(args.path))
            print(f"Created {Path(args.path).resolve()}")
            return 0
        if args.command == "framework":
            payload = _framework_payload()
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                for section, dimensions in payload.items():
                    print(section.replace("_", " ").title())
                    for dimension in dimensions:
                        print(f"  {dimension['id']}: {dimension['name']}")
            return 0
        if args.command == "validate":
            audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8"))
            result = validate_audit(audit)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 2
        if args.command == "case":
            if args.case_command == "init":
                _init_company_case(Path(args.path))
                print(f"Created {Path(args.path).resolve()}")
                return 0
            case = _load_json_object(args.case_json)
            if args.case_command == "validate":
                result = validate_company_case(case)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0 if result["passed"] else 2
            if args.case_command == "report":
                paths = write_onboarding_artifacts(case, args.out)
                validation = validate_company_case(case)
                print(json.dumps({"validation": validation, "artifacts": paths}, indent=2, ensure_ascii=False))
                return 0 if validation["passed"] else 2
            if args.case_command == "agent-tasks":
                tasks = build_agent_tasks(case)
                payload = json.dumps(tasks, indent=2, ensure_ascii=False) + "\n"
                if args.out:
                    path = Path(args.out)
                    if path.exists():
                        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(payload, encoding="utf-8")
                    print(path.resolve())
                else:
                    print(payload, end="")
                return 0
        if args.command == "qa":
            if args.qa_command == "init":
                _init_qa_case(Path(args.path))
                print(f"Created {Path(args.path).resolve()}")
                return 0
            case = _load_json_object(args.qa_case_json)
            if args.qa_command == "next":
                status = next_qa_question_status(case)
                if status["status"] == "blocked_by_replay_errors":
                    print(json.dumps(status, indent=2, ensure_ascii=False))
                    return 2
                print(
                    json.dumps(
                        {
                            "complete": status["complete"],
                            "next_question": status["next_question"],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0
            if args.qa_command == "validate":
                result = validate_qa_case(case)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0 if result["passed"] else 2
            if args.qa_command == "report":
                paths = write_qa_artifacts(case, args.out)
                result = validate_qa_case(case)
                print(
                    json.dumps(
                        {"validation": result, "artifacts": paths},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0 if result["passed"] else 2
        if args.command == "enterprise":
            if args.enterprise_command == "init-store":
                store = AssessmentStore(args.database)
                store.initialize()
                print(json.dumps({"database": str(store.path.resolve()), "initialized": True}))
                return 0
            if args.enterprise_command == "create":
                intake = _load_json_object(args.intake_json)
                company = intake.get("company")
                case = intake.get("case")
                if not isinstance(company, dict) or not isinstance(case, dict):
                    raise ValueError("Intake requires company and case objects")
                store = AssessmentStore(args.database)
                company_id = store.upsert_company(
                    canonical_name=str(company.get("canonical_name") or ""),
                    legal_name=(
                        str(company["legal_name"]) if company.get("legal_name") else None
                    ),
                    jurisdiction=(
                        str(company["jurisdiction"]) if company.get("jurisdiction") else None
                    ),
                    registry_id=(
                        str(company["registry_id"]) if company.get("registry_id") else None
                    ),
                    aliases=[str(item) for item in company.get("aliases") or []],
                )
                case_id = store.create_case(
                    company_id=company_id,
                    stage=str(case.get("stage") or ""),
                    as_of=str(case.get("as_of") or ""),
                    profile=case.get("profile") if isinstance(case.get("profile"), dict) else {},
                    owner=str(case["owner"]) if case.get("owner") else None,
                    external_id=str(case["external_id"]) if case.get("external_id") else None,
                    source_case_path=(
                        str(case["source_case_path"]) if case.get("source_case_path") else None
                    ),
                )
                print(
                    json.dumps(
                        {"database": str(store.path.resolve()), "company_id": company_id, "case_id": case_id},
                        ensure_ascii=False,
                    )
                )
                return 0
            if args.enterprise_command == "ingest-evidence":
                store = AssessmentStore(args.database)
                raw = _load_json_value(args.evidence_json)
                items = raw if isinstance(raw, list) else [raw]
                if any(not isinstance(item, dict) for item in items):
                    raise ValueError("Evidence JSON must be an object or array of objects")
                identifiers = [
                    store.add_evidence(args.case_id, item)
                    for item in items
                    if isinstance(item, dict)
                ]
                print(json.dumps({"evidence_ids": identifiers}, ensure_ascii=False))
                return 0
            if args.enterprise_command == "transcribe":
                result = transcribe_media(
                    args.media,
                    args.out,
                    model_name=args.model,
                    language=args.language,
                    model_cache=args.model_cache,
                )
                store = AssessmentStore(args.database)
                interview_id = store.add_interview(
                    args.case_id,
                    transcript_path=result["transcript_path"],
                    consent_ref=args.consent_ref,
                    language=result["language"],
                    model=result["model"],
                    audio_path=str(Path(args.media).resolve()),
                    segments=result["segments"],
                )
                print(
                    json.dumps(
                        {**result, "interview_id": interview_id},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0
            if args.enterprise_command == "add-interview":
                segments = _load_json_value(args.segments_json) if args.segments_json else []
                points = _load_json_value(args.points_json) if args.points_json else []
                if not isinstance(segments, list) or not isinstance(points, list):
                    raise ValueError("segments and points JSON roots must be arrays")
                store = AssessmentStore(args.database)
                interview_id = store.add_interview(
                    args.case_id,
                    transcript_path=args.transcript,
                    consent_ref=args.consent_ref,
                    language=args.language,
                    model=args.model,
                    audio_path=args.audio,
                    segments=segments,
                    structured_points=points,
                )
                evidence_ids = []
                for point in points:
                    if not isinstance(point, dict):
                        raise ValueError("Every structured interview point must be an object")
                    evidence = evidence_from_owner_statement(
                        claim=str(point.get("claim") or ""),
                        source=str(Path(args.transcript).resolve()),
                        locator=str(point.get("locator") or ""),
                        case_id=args.case_id,
                        date=str(point["date"]) if point.get("date") else None,
                        metadata={
                            "input_module": "interview",
                            **(
                                point.get("metadata")
                                if isinstance(point.get("metadata"), dict)
                                else {}
                            ),
                        },
                    )
                    evidence_ids.append(store.add_evidence(args.case_id, evidence))
                print(
                    json.dumps(
                        {"interview_id": interview_id, "owner_statement_ids": evidence_ids},
                        ensure_ascii=False,
                    )
                )
                return 0
            if args.enterprise_command == "sidecar-query":
                client = NexSidecarClient(
                    args.base_url,
                    api_key=os.environ.get("NEX_API_KEY"),
                )
                result = client.query(
                    question=args.question,
                    case_id=args.case_id,
                    mode=args.mode,
                    top_k=args.top_k,
                    purpose=args.purpose,
                    time_sensitive=args.time_sensitive,
                )
                store = AssessmentStore(args.database)
                identifiers = [
                    store.add_evidence(args.case_id, evidence)
                    for evidence in result["evidence"]
                ]
                print(
                    json.dumps(
                        {**result, "stored_evidence_ids": identifiers},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0 if result["status"] == "ok" else 3
            if args.enterprise_command == "assess":
                store = AssessmentStore(args.database)
                assessment_config = load_assessment_config(args.config)
                matching_config = load_matching_config(args.config)
                sidecar_status = None
                if args.sidecar_check:
                    health = NexSidecarClient(
                        args.sidecar_url,
                        api_key=os.environ.get("NEX_API_KEY"),
                    ).health()
                    sidecar_status = {
                        "status": "ok" if health["available"] else "sidecar_unavailable",
                        "warnings": [health["warning"]] if health["warning"] else [],
                        "health": health["payload"],
                    }
                financial_audit = (
                    _load_json_object(args.financial_audit) if args.financial_audit else None
                )
                assessment = EnterpriseAssessmentEngine(
                    store,
                    assessment_config=assessment_config,
                    matching_config=matching_config,
                ).run(
                    args.case_id,
                    financial_audit=financial_audit,
                    course_catalog=args.course_catalog,
                    policy_catalog=args.policy_catalog,
                    sidecar_status=sidecar_status,
                    actor=args.actor,
                )
                paths = write_enterprise_report(store, assessment, args.out)
                print(
                    json.dumps(
                        {"assessment": assessment, "artifacts": paths},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0
            if args.enterprise_command == "decision":
                targets = {
                    "submit": "pending_review",
                    "approve": "approved",
                    "reject": "rejected",
                }
                result = AssessmentStore(args.database).transition_decision(
                    args.case_id,
                    targets[args.action],
                    actor=args.actor,
                    rejection_reason=args.reason,
                    eval_dir=args.eval_dir,
                )
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            if args.enterprise_command == "show":
                bundle = AssessmentStore(args.database).get_case_bundle(args.case_id)
                print(json.dumps(bundle, indent=2, ensure_ascii=False))
                return 0
            if args.enterprise_command == "company-candidates":
                candidates = CompanyDirectoryAdapter(args.directory_database).search(
                    args.name,
                    limit=args.limit,
                )
                print(json.dumps(candidates, indent=2, ensure_ascii=False))
                return 0
            if args.enterprise_command == "asset-candidates":
                candidates = EnergyAssetAdapter(args.asset_database).search(
                    args.query,
                    case_id=args.case_id,
                    limit=args.limit,
                )
                print(json.dumps(candidates, indent=2, ensure_ascii=False))
                return 0
    except (ManifestError, FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
