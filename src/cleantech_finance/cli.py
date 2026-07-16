"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import run_audit, validate_audit
from .finance_framework import FINANCE_DIMENSIONS
from .framework import DIMENSIONS
from .ingest import ManifestError
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
    except (ManifestError, FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
