"""Resolve a subject across legal-name changes using stable identifiers."""

from __future__ import annotations

import re
from typing import Any


def _source_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(source.get("id")): source
        for source in manifest.get("sources", [])
        if source.get("id")
    }


def resolve_entity_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate and render the optional stable-identity contract.

    Older manifests remain supported and are explicitly labelled ``legacy``.
    Once an identity contract is present, every source about the subject must
    carry the same stable entity id; name similarity is never used as proof.
    """

    subject = manifest.get("subject") or {}
    identity = subject.get("identity")
    if not identity:
        return {
            "status": "legacy",
            "status_zh": "旧版清单（未声明稳定实体标识）",
            "match_method": None,
            "entity_id": None,
            "summary": "No stable entity identity contract was supplied.",
            "summary_zh": "该清单未提供稳定实体身份契约；仅保留向后兼容。",
            "aliases": [],
            "source_bindings": [],
        }

    required = {
        "entity_id",
        "scheme",
        "value",
        "legal_name",
        "display_name",
        "display_name_zh",
        "legal_name_citation",
        "aliases",
    }
    missing = sorted(required - set(identity))
    if missing:
        raise ValueError(
            "Subject identity missing required field(s): " + ", ".join(missing)
        )

    entity_id = str(identity["entity_id"])
    scheme = str(identity["scheme"])
    value = str(identity["value"])
    if scheme != "sec_cik":
        raise ValueError(f"Unsupported subject identity scheme '{scheme}'")
    if not re.fullmatch(r"\d{10}", value):
        raise ValueError("SEC CIK identity value must contain exactly 10 digits")
    expected_entity_id = f"sec-cik-{value}"
    if entity_id != expected_entity_id:
        raise ValueError(
            f"Identity entity_id '{entity_id}' does not match '{expected_entity_id}'"
        )
    subject_cik = str(subject.get("cik") or "").zfill(10)
    if subject_cik != value:
        raise ValueError(
            f"Subject CIK '{subject.get('cik')}' does not match identity value '{value}'"
        )
    if identity["legal_name"] != subject.get("organization"):
        raise ValueError("Identity legal_name must equal subject.organization")

    sources = _source_map(manifest)
    source_bindings: list[dict[str, Any]] = []
    for source in manifest.get("sources", []):
        role = source.get("role", "subject")
        if role not in {"subject", "auxiliary", "identity"}:
            continue
        bound_entity_id = source.get("subject_entity_id")
        if not bound_entity_id:
            raise ValueError(
                f"Source '{source.get('id')}' must declare subject_entity_id"
            )
        if bound_entity_id != entity_id:
            raise ValueError(
                f"Source '{source.get('id')}' belongs to '{bound_entity_id}', "
                f"not '{entity_id}'"
            )
        source_bindings.append(
            {
                "source_id": source["id"],
                "publisher": source["publisher"],
                "role": role,
                "subject_entity_id": bound_entity_id,
                "matched_by": "entity_id",
            }
        )

    def validate_citation(citation: dict[str, Any], label: str) -> None:
        source_id = citation.get("source_id")
        if source_id not in sources:
            raise ValueError(f"{label} cites unknown source '{source_id}'")
        if not citation.get("locator"):
            raise ValueError(f"{label} citation requires a locator")
        if sources[source_id].get("subject_entity_id") != entity_id:
            raise ValueError(f"{label} citation is not bound to '{entity_id}'")

    validate_citation(identity["legal_name_citation"], "Legal name")
    aliases = identity["aliases"]
    if not isinstance(aliases, list):
        raise ValueError("Identity aliases must be an array")
    names: set[str] = {str(identity["legal_name"]).casefold()}
    for index, alias in enumerate(aliases, start=1):
        name = str(alias.get("name") or "").strip()
        if not name:
            raise ValueError(f"Identity alias {index} requires a name")
        folded = name.casefold()
        if folded in names:
            raise ValueError(f"Duplicate identity name or alias '{name}'")
        names.add(folded)
        validate_citation(alias, f"Identity alias {index}")

    return {
        "status": "passed",
        "status_zh": "已通过",
        "match_method": "stable_identifier",
        "match_method_zh": "稳定标识符匹配",
        "entity_id": entity_id,
        "scheme": scheme,
        "value": value,
        "legal_name": identity["legal_name"],
        "display_name": identity["display_name"],
        "display_name_zh": identity["display_name_zh"],
        "summary": (
            f"{len(source_bindings)} source(s) and {len(aliases)} former-name "
            "alias(es) resolve to one stable entity."
        ),
        "summary_zh": (
            f"{len(source_bindings)} 个来源及 {len(aliases)} 个历史名称均解析为同一稳定实体。"
        ),
        "aliases": aliases,
        "source_bindings": source_bindings,
    }
