"""Run one registered company with a user-selected auxiliary-source set."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cleantech_finance.audit import run_audit
from cleantech_finance.reporting import write_artifacts

ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "evals" / "company-loops-v0.3.json"


def _cases() -> dict[str, dict[str, Any]]:
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {str(row["id"]): row for row in rows}


def run_case(
    case_id: str,
    selected_source_ids: list[str] | None = None,
    disable_auxiliary: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    cases = _cases()
    if case_id not in cases:
        raise ValueError(
            f"Unknown case '{case_id}'. Allowed cases: {', '.join(sorted(cases))}"
        )
    case = cases[case_id]
    manifest_path = (ROOT / case["manifest"]).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    available = sorted(
        source["id"]
        for source in payload["sources"]
        if source.get("role") == "auxiliary"
    )
    configured = payload.get("auxiliary_validation") or {}
    if disable_auxiliary and selected_source_ids:
        raise ValueError("Cannot combine --disable-auxiliary with --aux-source")
    if disable_auxiliary:
        selected: list[str] = []
    elif selected_source_ids is None:
        selected = sorted(set(configured.get("selected_source_ids") or []))
    else:
        selected = sorted(set(selected_source_ids))
    invalid = sorted(set(selected) - set(available))
    if invalid:
        raise ValueError(
            "Selected source(s) are not available for this case: " + ", ".join(invalid)
        )
    configured_fact_sources = {
        fact.get("source_id") for fact in configured.get("facts") or []
    }
    missing_facts = sorted(set(selected) - configured_fact_sources)
    if missing_facts:
        raise ValueError(
            "Selected source(s) have no configured auxiliary facts: "
            + ", ".join(missing_facts)
        )

    configured["enabled"] = bool(selected)
    configured["selected_source_ids"] = selected
    payload["auxiliary_validation"] = configured
    cash_context = payload.get("cash_conversion_context")
    if cash_context is not None:
        cash_fact_sources = {
            fact.get("source_id") for fact in cash_context.get("facts") or []
        }
        cash_context["enabled"] = bool(set(selected) & cash_fact_sources)

    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".manifest-selection-",
            suffix=".json",
            dir=manifest_path.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        audit = run_audit(
            str(temporary_path),
            only_dimensions={"profitability-unit-economics", "cash-runway"},
        )
        if not audit["validation"]["passed"]:
            raise ValueError(
                "Selected-source audit failed validation: "
                + "; ".join(audit["validation"]["errors"])
            )
        target = Path(output_dir) if output_dir else ROOT / case["output_dir"]
        if not target.is_absolute():
            target = ROOT / target
        artifacts = write_artifacts(audit, target)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)

    return {
        "case": case_id,
        "available_source_ids": available,
        "selected_source_ids": selected,
        "ignored_source_ids": sorted(set(available) - set(selected)),
        "auxiliary_status": audit["auxiliary_validation"]["status"],
        "signals": {
            card["dimension_id"]: card["signal"]
            for card in audit["judgment_layer"]["cards"]
        },
        "output_dir": str(target.resolve()),
        "artifacts": artifacts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a registered company case with an explicit, whitelist-checked "
            "auxiliary-source selection."
        )
    )
    parser.add_argument("--case", required=True)
    parser.add_argument(
        "--aux-source",
        action="append",
        dest="aux_sources",
        help="Repeat for each selected auxiliary source id",
    )
    parser.add_argument("--disable-auxiliary", action="store_true")
    parser.add_argument("--out")
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        result = run_case(
            args.case,
            selected_source_ids=args.aux_sources,
            disable_auxiliary=args.disable_auxiliary,
            output_dir=args.out,
        )
        if args.out is None:
            from build_company_loop_index import build_index

            result["index"] = str(build_index().resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"passed": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
