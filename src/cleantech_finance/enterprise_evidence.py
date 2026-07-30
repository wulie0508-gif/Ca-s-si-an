"""Unified evidence adapters for enterprise assessment inputs."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SOURCE_LEVELS = {"L1", "L2", "L3", "L4"}
EVIDENCE_TYPES = {"fact", "opinion", "owner_statement"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
REVIEW_STATUSES = {"verified", "pending"}
LEVEL_STRENGTH = {"L1": 4, "L2": 3, "L3": 2, "L4": 1}
NOISE_MARKERS = (
    "/.cache/",
    "\\.cache\\",
    "/__pycache__/",
    "\\__pycache__\\",
    "/build/",
    "\\build\\",
    "/dist/",
    "\\dist\\",
    "/outputs/",
    "\\outputs\\",
)
NOISE_SUFFIXES = (".py", ".pyc", ".js.map", ".lock")
OFFICIAL_DOMAIN_SUFFIXES = (
    ".gov",
    ".gov.cn",
    ".gov.au",
    ".gov.uk",
    ".europa.eu",
    ".org.au",
)
OFFICIAL_KIND_MARKERS = (
    "official",
    "regulatory",
    "government",
    "registry",
    "filing",
)
TENCENT_CORPUS_MARKERS = ("tencent", "external_research")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_evidence_key(claim: str, source: str, locator: str) -> str:
    value = "\x1f".join((claim, source, locator)).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:24]


def normalize_evidence(
    evidence: dict[str, Any],
    *,
    default_entity_id: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize the public evidence contract."""

    if not isinstance(evidence, dict):
        raise ValueError("Evidence must be an object")
    value = dict(evidence)
    required_text = ("claim", "source", "locator")
    for field in required_text:
        value[field] = _clean(value.get(field))
        if not value[field]:
            raise ValueError(f"Evidence requires non-empty {field}")
    value["entity_id"] = _clean(value.get("entity_id") or default_entity_id)
    if not value["entity_id"]:
        raise ValueError("Evidence requires entity_id")
    value["source_level"] = _clean(value.get("source_level")).upper()
    value["type"] = _clean(value.get("type") or value.get("evidence_type"))
    value["confidence"] = _clean(value.get("confidence")).lower()
    value["review_status"] = _clean(value.get("review_status")).lower()
    if value["source_level"] not in SOURCE_LEVELS:
        raise ValueError("source_level must be L1, L2, L3 or L4")
    if value["type"] not in EVIDENCE_TYPES:
        raise ValueError("type must be fact, opinion or owner_statement")
    if value["confidence"] not in CONFIDENCE_LEVELS:
        raise ValueError("confidence must be high, medium or low")
    if value["review_status"] not in REVIEW_STATUSES:
        raise ValueError("review_status must be verified or pending")
    value["date"] = _clean(value.get("date")) or None
    value["source_url"] = _clean(value.get("source_url") or value.get("url")) or None
    value["sha256"] = _clean(value.get("sha256")) or None
    metadata = value.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Evidence metadata must be an object")
    value["metadata"] = metadata
    value["evidence_key"] = _clean(value.get("evidence_key")) or _stable_evidence_key(
        value["claim"], value["source"], value["locator"]
    )
    return value


def evidence_from_owner_statement(
    *,
    claim: str,
    source: str,
    locator: str,
    case_id: str,
    date: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a non-factual interview evidence object."""

    return normalize_evidence(
        {
            "claim": claim,
            "source": source,
            "locator": locator,
            "date": date,
            "entity_id": case_id,
            "source_level": "L4",
            "type": "owner_statement",
            "confidence": "medium",
            "review_status": "pending",
            "metadata": {"bearing_fact": False, **(metadata or {})},
        }
    )


def evaluate_claim_burden(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply L1-single/L2-double support burden without using L3/L4 as proof."""

    verified_facts = [
        item
        for item in evidence
        if item.get("type") == "fact" and item.get("review_status") == "verified"
    ]

    def independent_sources(level: str) -> set[str]:
        return {
            "\x1f".join(
                (
                    _clean(item.get("source_url")),
                    _clean(item.get("source")),
                )
            )
            for item in verified_facts
            if item.get("source_level") == level
        }

    l1_sources = independent_sources("L1")
    l2_sources = independent_sources("L2")
    if l1_sources:
        status = "supported"
        basis = "one_or_more_verified_L1_sources"
    elif len(l2_sources) >= 2:
        status = "supported"
        basis = "two_or_more_independent_verified_L2_sources"
    else:
        status = "not_supported"
        basis = "source_burden_not_met"
    return {
        "status": status,
        "basis": basis,
        "verified_L1_source_count": len(l1_sources),
        "verified_L2_source_count": len(l2_sources),
        "reference_only_L3_L4_count": sum(
            item.get("source_level") in {"L3", "L4"} for item in evidence
        ),
        "owner_statement_count": sum(
            item.get("type") == "owner_statement" for item in evidence
        ),
    }


def _citation_source_level(citation: dict[str, Any]) -> str:
    explicit = _clean(citation.get("source_level")).upper()
    if explicit in SOURCE_LEVELS:
        return explicit
    source_kind = _clean(citation.get("source_kind")).lower()
    publisher = _clean(citation.get("publisher")).lower()
    hostname = urlparse(_clean(citation.get("source_url"))).hostname or ""
    if any(marker in source_kind for marker in OFFICIAL_KIND_MARKERS):
        return "L1"
    if hostname.endswith(OFFICIAL_DOMAIN_SUFFIXES):
        return "L1"
    if any(
        marker in publisher
        for marker in ("reuters", "bloomberg", "associated press", "行业协会", "association")
    ):
        return "L2"
    if _clean(citation.get("corpus_role")).lower() == "internal":
        return "L3"
    return "L3"


def _is_noise(citation: dict[str, Any]) -> bool:
    path = _clean(citation.get("original_path") or citation.get("file_name")).lower()
    return any(marker in path for marker in NOISE_MARKERS) or path.endswith(NOISE_SUFFIXES)


def _is_tencent_background(citation: dict[str, Any]) -> bool:
    fields = (
        citation.get("source_kind"),
        citation.get("corpus_role"),
        citation.get("publisher"),
        citation.get("source_id"),
    )
    text = " ".join(_clean(field).lower() for field in fields)
    return any(marker in text for marker in TENCENT_CORPUS_MARKERS)


def _lexical_relevance(question: str, snippet: str) -> float:
    ascii_tokens = set(re.findall(r"[a-z0-9]{2,}", question.lower()))
    ascii_snippet = set(re.findall(r"[a-z0-9]{2,}", snippet.lower()))
    cjk_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,4}", question))
    if not ascii_tokens and not cjk_tokens:
        return 0.5
    hits = len(ascii_tokens & ascii_snippet)
    hits += sum(token in snippet for token in cjk_tokens)
    return hits / max(1, len(ascii_tokens) + len(cjk_tokens))


def citation_to_evidence(
    citation: dict[str, Any],
    *,
    case_id: str,
    question: str,
    purpose: str = "enterprise_fact",
    time_sensitive: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Convert one sidecar citation or return a transparent discard reason."""

    snippet = _clean(citation.get("snippet") or citation.get("claim"))
    source = _clean(
        citation.get("title")
        or citation.get("file_name")
        or citation.get("publisher")
        or citation.get("source_url")
    )
    locator = _clean(citation.get("locator"))
    if not snippet:
        return None, "missing_claim"
    if not source:
        return None, "missing_source"
    if not locator:
        return None, "missing_locator"
    if _is_noise(citation):
        return None, "adapter_noise_filter"
    if purpose == "enterprise_fact" and _is_tencent_background(citation):
        return None, "background_source_not_enterprise_fact"
    relevance = _lexical_relevance(question, snippet)
    if relevance == 0:
        return None, "no_lexical_overlap"
    level = _citation_source_level(citation)
    confidence = "high" if level == "L1" and relevance >= 0.2 else "medium"
    if level in {"L3", "L4"} or relevance < 0.1:
        confidence = "low"
    metadata = {
        "adapter": "nex_sidecar",
        "candidate_only": True,
        "retrieval_score": citation.get("retrieval_score"),
        "adapter_relevance": round(relevance, 4),
        "source_kind": citation.get("source_kind"),
        "source_status": citation.get("source_status"),
        "corpus_role": citation.get("corpus_role"),
        "file_id": citation.get("file_id"),
        "chunk_id": citation.get("chunk_id"),
        "requires_live_official_verification": bool(time_sensitive),
    }
    return (
        normalize_evidence(
            {
                "claim": snippet,
                "source": source,
                "locator": locator,
                "date": citation.get("publication_date"),
                "entity_id": case_id,
                "source_level": level,
                "type": "fact",
                "confidence": confidence,
                "review_status": "pending",
                "source_url": citation.get("source_url"),
                "sha256": citation.get("sha256"),
                "metadata": metadata,
            }
        ),
        None,
    )


class NexSidecarClient:
    """Use NEX RAG as a citation cache, never as a fact or decision authority."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        api_key: str | None = None,
        timeout_seconds: float = 5,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/health",
            headers=self._headers(),
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {"available": True, "payload": payload, "warning": None}
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return {
                "available": False,
                "payload": None,
                "warning": f"本地缓存未使用：NEX sidecar unavailable ({exc})",
            }

    def query(
        self,
        *,
        question: str,
        case_id: str,
        mode: str = "hybrid",
        top_k: int = 5,
        purpose: str = "enterprise_fact",
        time_sensitive: bool = False,
        metadata_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode not in {"internal", "external", "hybrid"}:
            raise ValueError("NEX mode must be internal, external or hybrid")
        if not 1 <= top_k <= 30:
            raise ValueError("top_k must be between 1 and 30")
        body = {
            "question": question,
            "mode": mode,
            "top_k": top_k,
            "metadata_filter": metadata_filter or {},
            "include_pilot_sources": False,
            "include_unapproved_sources": False,
            "include_external_research": purpose == "industry_background",
            "use_semantic": True,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/query",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return {
                "status": "sidecar_unavailable",
                "evidence": [],
                "discarded": [],
                "warnings": [f"本地缓存未使用：NEX sidecar unavailable ({exc})"],
                "requires_live_official_search": True,
            }
        raw_citations = payload.get("citations") or []
        if not isinstance(raw_citations, list):
            raw_citations = []
        accepted: list[dict[str, Any]] = []
        discarded: list[dict[str, Any]] = []
        for index, citation in enumerate(raw_citations):
            if not isinstance(citation, dict):
                discarded.append({"index": index, "reason": "invalid_citation_shape"})
                continue
            evidence, reason = citation_to_evidence(
                citation,
                case_id=case_id,
                question=question,
                purpose=purpose,
                time_sensitive=time_sensitive,
            )
            if evidence:
                accepted.append(evidence)
            else:
                discarded.append({"index": index, "reason": reason})
        accepted.sort(
            key=lambda item: (
                -LEVEL_STRENGTH[item["source_level"]],
                -float(item["metadata"]["adapter_relevance"]),
                item["evidence_key"],
            )
        )
        warnings = list(payload.get("warnings") or [])
        if time_sensitive:
            warnings.append("时效敏感信息仅作历史参考，必须实时复核官方来源。")
        return {
            "status": "ok",
            "evidence": accepted[:top_k],
            "discarded": discarded,
            "warnings": warnings,
            "requires_live_official_search": bool(time_sensitive or not accepted),
            "sidecar_confidence": payload.get("confidence"),
            "data_freshness": payload.get("data_freshness"),
        }


def _read_only_connection(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


class CompanyDirectoryAdapter:
    """Return identity candidates for human confirmation; never merge entities."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def search(self, name: str, *, limit: int = 10) -> list[dict[str, Any]]:
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", name.lower()).strip()
        if not normalized:
            return []
        with closing(_read_only_connection(self.database_path)) as connection:
            rows = connection.execute(
                """
                SELECT * FROM entities
                WHERE normalized_name=? OR normalized_name LIKE ?
                ORDER BY
                    CASE WHEN normalized_name=? THEN 0 ELSE 1 END,
                    classification_confidence DESC,
                    entity_name
                LIMIT ?
                """,
                (normalized, f"{normalized}%", normalized, limit),
            ).fetchall()
        return [
            {
                **dict(row),
                "candidate_only": True,
                "requires_human_legal_entity_confirmation": True,
                "auto_merge_allowed": False,
            }
            for row in rows
        ]


class EnergyAssetAdapter:
    """Read approved energy-asset rows as candidate evidence."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def search(
        self,
        query: str,
        *,
        case_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        value = query.strip()
        if not value:
            return []
        pattern = f"%{value}%"
        with closing(_read_only_connection(self.database_path)) as connection:
            rows = connection.execute(
                """
                SELECT * FROM energy_assets
                WHERE asset_name LIKE ? OR operator_name LIKE ? OR utility_name LIKE ?
                ORDER BY source_date DESC, asset_name
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        evidence: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            facts = [
                f"{item['asset_name']} is listed as {item['asset_kind']}",
                f"status {item['status']}" if item.get("status") else "",
                f"technology {item['technology']}" if item.get("technology") else "",
                (
                    f"capacity {item['capacity_mw']} MW"
                    if item.get("capacity_mw") is not None
                    else ""
                ),
                f"operator {item['operator_name']}" if item.get("operator_name") else "",
            ]
            evidence.append(
                normalize_evidence(
                    {
                        "claim": "; ".join(part for part in facts if part) + ".",
                        "source": item["source_id"],
                        "locator": item["source_locator"],
                        "date": item.get("source_date"),
                        "entity_id": case_id,
                        "source_level": "L1",
                        "type": "fact",
                        "confidence": "high",
                        "review_status": "pending",
                        "source_url": item.get("source_url"),
                        "sha256": item.get("source_sha256"),
                        "metadata": {
                            "adapter": "nex_energy_assets",
                            "asset_id": item["asset_id"],
                            "candidate_only": True,
                            "requires_entity_link_confirmation": True,
                            "caveat": item.get("caveat"),
                            "source_review_status": item.get("review_status"),
                        },
                    }
                )
            )
        return evidence
