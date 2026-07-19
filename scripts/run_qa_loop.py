"""Run the five human-supplied QA diagnostic cases in order."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cleantech_finance.qa_loop import (  # noqa: E402
    preflight_qa_registry,
    run_qa_registry,
    selection_material_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run exactly five human-supplied QA cases; stop on the first "
            "traceability or financial-ground-truth failure."
        )
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument(
        "--out",
        help=(
            "External local output directory; required for a formal run. With "
            "--preflight, it is optional and, when supplied, is checked but not created."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--selection-digest-only",
        action="store_true",
        help=(
            "Print actual case/profile hashes, the immutable five-case digest, and an "
            "explicitly unconfirmed attestation template; does not run cases."
        ),
    )
    mode.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Dry-run the exact qa_delivery packet in disposable local storage; "
            "does not create formal output or history."
        ),
    )
    parser.add_argument(
        "--change-note",
        default="",
        help="Required English general-rule note when the QA rule digest changed.",
    )
    parser.add_argument(
        "--change-note-zh",
        default="",
        help="Required Chinese general-rule note when the QA rule digest changed.",
    )
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        if args.selection_digest_only:
            registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
            report = selection_material_report(
                registry,
                args.registry,
                project_root=ROOT,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ready_for_human_attestation"] else 2
        if args.preflight:
            result = preflight_qa_registry(
                args.registry,
                project_root=ROOT,
                intended_output_dir=args.out,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["passed"] else 2
        if not args.out:
            raise ValueError(
                "--out is required for a formal run and must be outside the project tree"
            )
        result = run_qa_registry(
            args.registry,
            args.out,
            project_root=ROOT,
            change_note=args.change_note,
            change_note_zh=args.change_note_zh,
        )
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "execution_passed": result["execution_passed"],
                "delivery_eligible": result["delivery_eligible"],
                "deliverable_status": result["deliverable_status"],
                "completed_execution_count": result["completed_execution_count"],
                "completed_case_count": result["completed_case_count"],
                "financial_summary": result["financial_summary"],
                "artifacts": result["artifacts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
