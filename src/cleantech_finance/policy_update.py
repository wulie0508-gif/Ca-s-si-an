"""Official-source policy refresh with change isolation and review gating.

This module deliberately writes a separate candidate feed. A network refresh can
never mutate or silently replace the hash-attested policy catalog used by the
workbench. New or changed official pages remain ``candidate_pending_review``
until a project owner promotes them through a separate reviewed-catalog process.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

POLICY_UPDATE_SCHEMA_VERSION = "1.0.0"
POLICY_UPDATE_PARSER_VERSION = "shanghai-official-html-1.0.0"
DEFAULT_ALLOWED_HOSTS = frozenset(
    {
        "fgw.sh.gov.cn",
        "kjgl.stcsm.sh.gov.cn",
        "sheitc.sh.gov.cn",
        "stcsm.sh.gov.cn",
        "www.shanghai.gov.cn",
        "www.sheitc.sh.gov.cn",
    }
)
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = (
    "CleanTech-Finance-Policy-Monitor/0.4 "
    "(+local evidence workspace; contact repository owner)"
)

LIST_FIELDS = (
    "eligible_regions",
    "eligible_entities",
    "eligible_stages",
    "sectors",
    "industry_tags",
    "stage_tags",
    "need_tags",
    "technology_tags",
    "geography_tags",
    "market_tags",
    "must_conditions",
    "exclusion_conditions",
    "evidence_required",
    "related_result_urls",
)

CANDIDATE_COLUMNS = (
    "policy_id",
    "title",
    "issuer",
    "document_number",
    "source_url",
    "published_at",
    "effective_from",
    "effective_to",
    "application_open_at",
    "application_close_at",
    "document_status",
    "application_status",
    "opportunity_type",
    *LIST_FIELDS,
    "benefit_summary",
    "application_channel",
    "supersedes",
    "http_status",
    "etag",
    "last_modified",
    "fetched_at",
    "raw_sha256",
    "normalized_sha256",
    "change_status",
    "review_status",
    "reviewer",
    "reviewed_at",
    "data_class",
    "simulation_only",
    "disclosure_label",
    "legal_disclaimer",
    "parser_version",
)


class PolicyUpdateError(ValueError):
    """Raised when a policy source or refresh output is unsafe to use."""


def _clean(value: Any, *, limit: int = 20_000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_text(value: str) -> str:
    return _digest_bytes(value.encode("utf-8"))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else re.split(r"[,，;；|\n]+", str(value))
    result: list[str] = []
    for item in raw:
        cleaned = _clean(item, limit=500)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _iso_date(value: Any, *, field: str) -> str:
    cleaned = _clean(value, limit=40)
    if not cleaned:
        return ""
    try:
        return date.fromisoformat(cleaned[:10]).isoformat()
    except ValueError as exc:
        raise PolicyUpdateError(f"{field} must be an ISO date") from exc


def _allowed_url(url: str, allowed_hosts: set[str] | frozenset[str]) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or host not in allowed_hosts
        or parsed.fragment
    ):
        raise PolicyUpdateError(f"Official source URL is not allowlisted: {url}")
    return parsed.geturl()


def load_policy_source_manifest(path: str | Path) -> dict[str, Any]:
    """Load and fail closed on the curated official-source manifest."""

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyUpdateError(f"Policy source manifest is unreadable: {source_path}") from exc
    if not isinstance(payload, dict):
        raise PolicyUpdateError("Policy source manifest root must be an object")
    if payload.get("schema_version") != POLICY_UPDATE_SCHEMA_VERSION:
        raise PolicyUpdateError("Unsupported policy source manifest schema_version")
    raw_hosts = payload.get("allowed_hosts") or sorted(DEFAULT_ALLOWED_HOSTS)
    if not isinstance(raw_hosts, list) or not raw_hosts:
        raise PolicyUpdateError("allowed_hosts must be a non-empty string array")
    allowed_hosts = {
        _clean(item, limit=253).casefold()
        for item in raw_hosts
        if isinstance(item, str) and _clean(item, limit=253)
    }
    if not allowed_hosts or not allowed_hosts.issubset(DEFAULT_ALLOWED_HOSTS):
        raise PolicyUpdateError("allowed_hosts may only contain approved Shanghai hosts")

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise PolicyUpdateError("sources must be a non-empty array")
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    sources: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_sources, start=1):
        if not isinstance(raw, dict):
            raise PolicyUpdateError(f"sources[{index}] must be an object")
        policy_id = _clean(raw.get("policy_id"), limit=120)
        title = _clean(raw.get("title"), limit=500)
        source_url = _allowed_url(
            _clean(raw.get("source_url"), limit=2_000),
            allowed_hosts,
        )
        if not policy_id or not title:
            raise PolicyUpdateError(f"sources[{index}] requires policy_id and title")
        id_key = policy_id.casefold()
        url_key = source_url.casefold()
        if id_key in seen_ids:
            raise PolicyUpdateError(f"Duplicate policy_id: {policy_id}")
        if url_key in seen_urls:
            raise PolicyUpdateError(f"Duplicate source_url: {source_url}")
        seen_ids.add(id_key)
        seen_urls.add(url_key)
        normalized = dict(raw)
        normalized["policy_id"] = policy_id
        normalized["title"] = title
        normalized["source_url"] = source_url
        for field in (
            "published_at",
            "effective_from",
            "effective_to",
            "application_open_at",
            "application_close_at",
        ):
            normalized[field] = _iso_date(raw.get(field), field=field)
        for field in LIST_FIELDS:
            normalized[field] = _as_list(raw.get(field))
        normalized["review_status"] = "candidate_pending_review"
        normalized["data_class"] = "official_source_candidate"
        normalized["simulation_only"] = False
        sources.append(normalized)
    return {
        **payload,
        "path": str(source_path.resolve()),
        "allowed_hosts": sorted(allowed_hosts),
        "sources": sources,
    }


def _meta_content(soup: Any, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
        if tag and tag.get("content"):
            return _clean(tag.get("content"), limit=2_000)
    return ""


def _first_text(soup: Any, selectors: Iterable[str], *, limit: int) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = _clean(node.get_text(" ", strip=True), limit=limit)
            if value:
                return value
    return ""


def parse_official_policy_page(payload: bytes, *, source_url: str) -> dict[str, Any]:
    """Extract stable metadata and visible body text from one official article."""

    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - exercised only without policy extra
        raise PolicyUpdateError(
            "Policy sync requires the 'policy' optional dependencies"
        ) from exc
    if not payload or len(payload) > MAX_PAGE_BYTES:
        raise PolicyUpdateError("Official policy page is empty or exceeds the size limit")
    soup = BeautifulSoup(payload, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "template"]):
        node.decompose()
    title = _meta_content(soup, "ArticleTitle") or _first_text(
        soup,
        (
            "#ivs_title",
            ".xxgk_content_title",
            ".info-title-con span",
            "h1",
        ),
        limit=500,
    )
    published = _meta_content(soup, "PubDate") or _first_text(
        soup,
        ("#ivs_date", ".xxgk_content_time", ".info-title-con b", "time"),
        limit=120,
    )
    issuer = _meta_content(soup, "ContentSource")
    body = _first_text(
        soup,
        (
            "#ivs_content",
            ".Article_content",
            ".xxgk_content_nr",
            ".txt-con",
            "article",
            "main",
        ),
        limit=500_000,
    )
    if not title or len(body) < 80:
        raise PolicyUpdateError("Official policy page structure is not recognized")
    attachments: list[str] = []
    allowed_hosts = DEFAULT_ALLOWED_HOSTS
    for link in soup.find_all("a", href=True):
        href = urljoin(source_url, str(link.get("href")))
        parsed = urlsplit(href)
        suffix = Path(parsed.path).suffix.casefold()
        if (
            parsed.scheme == "https"
            and (parsed.hostname or "").casefold() in allowed_hosts
            and ("/cmsres/" in parsed.path or suffix in {".pdf", ".doc", ".docx", ".wps", ".xlsx"})
            and href not in attachments
        ):
            attachments.append(href)
    normalized_text = "\n".join((title, published, issuer, body))
    return {
        "title": title,
        "published_text": published,
        "issuer": issuer,
        "body_text": body,
        "attachments": attachments[:50],
        "normalized_sha256": _digest_text(normalized_text),
    }


def _date_status(
    *,
    as_of: date,
    start: str,
    end: str,
    ongoing_when_missing: bool,
) -> str:
    start_date = date.fromisoformat(start) if start else None
    end_date = date.fromisoformat(end) if end else None
    if start_date and as_of < start_date:
        return "upcoming"
    if end_date and as_of > end_date:
        return "closed"
    if start_date or end_date or ongoing_when_missing:
        return "open"
    return "not_applicable"


def _candidate_record(
    source: Mapping[str, Any],
    *,
    parsed: Mapping[str, Any],
    fetched_at: str,
    http_status: int,
    headers: Mapping[str, str],
    raw_sha256: str,
    previous_digest: str,
    as_of: date,
) -> dict[str, Any]:
    normalized_sha256 = str(parsed["normalized_sha256"])
    if not previous_digest:
        change_status = "new"
    elif previous_digest == normalized_sha256:
        change_status = "unchanged"
    else:
        change_status = "changed"
    document_status = _date_status(
        as_of=as_of,
        start=str(source.get("effective_from") or ""),
        end=str(source.get("effective_to") or ""),
        ongoing_when_missing=True,
    )
    status_mode = _clean(source.get("status_mode"), limit=40) or "framework_only"
    if status_mode == "application_window":
        application_status = _date_status(
            as_of=as_of,
            start=str(source.get("application_open_at") or ""),
            end=str(source.get("application_close_at") or ""),
            ongoing_when_missing=False,
        )
    elif status_mode in {"ongoing", "framework_only", "closed_historical"}:
        application_status = status_mode
    else:
        raise PolicyUpdateError(
            f"Unsupported status_mode for {source['policy_id']}: {status_mode}"
        )
    extracted_title = _clean(parsed.get("title"), limit=500)
    expected_title = _clean(source.get("title"), limit=500)
    record: dict[str, Any] = {
        **source,
        "title": extracted_title or expected_title,
        "expected_title": expected_title,
        "issuer": _clean(parsed.get("issuer"), limit=300)
        or _clean(source.get("issuer"), limit=300),
        "document_status": document_status,
        "application_status": application_status,
        "http_status": http_status,
        "etag": _clean(headers.get("etag"), limit=500),
        "last_modified": _clean(headers.get("last-modified"), limit=500),
        "fetched_at": fetched_at,
        "raw_sha256": raw_sha256,
        "normalized_sha256": normalized_sha256,
        "change_status": change_status,
        "review_status": "candidate_pending_review",
        "reviewer": "",
        "reviewed_at": "",
        "data_class": "official_source_candidate",
        "simulation_only": False,
        "disclosure_label": "官方来源更新候选，尚未进入企业匹配",
        "legal_disclaimer": (
            "仅作政策信息与材料准备参考，不构成申报资格、法律、税务或获批意见。"
        ),
        "parser_version": POLICY_UPDATE_PARSER_VERSION,
        "attachments": list(parsed.get("attachments") or []),
        "title_changed_from_manifest": bool(
            extracted_title and expected_title and extracted_title != expected_title
        ),
    }
    for field in LIST_FIELDS:
        record[field] = _as_list(source.get(field))
    return record


def _fetch(
    client: Any,
    url: str,
    *,
    allowed_hosts: set[str] | frozenset[str],
    conditional_headers: Mapping[str, str],
) -> Any:
    current = url
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    headers.update(conditional_headers)
    for _ in range(MAX_REDIRECTS + 1):
        response = client.get(current, headers=headers, follow_redirects=False)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise PolicyUpdateError("Official source returned a redirect without Location")
            current = _allowed_url(urljoin(current, location), allowed_hosts)
            continue
        if current != url:
            _allowed_url(current, allowed_hosts)
        return response
    raise PolicyUpdateError("Official source exceeded the redirect limit")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _csv_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ";".join(_clean(item, limit=2_000) for item in value)
    return _clean(value)


def _write_candidate_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {column: _csv_value(record.get(column)) for column in CANDIDATE_COLUMNS}
            )


def sync_policy_sources(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    as_of: str | date | None = None,
    timeout_seconds: float = 20.0,
    min_interval_seconds: float = 2.0,
    client: Any | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Refresh curated URLs and write a quarantined candidate feed plus receipt."""

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without policy extra
        raise PolicyUpdateError(
            "Policy sync requires the 'policy' optional dependencies"
        ) from exc
    manifest = load_policy_source_manifest(manifest_path)
    evaluation_date = (
        date.fromisoformat(as_of) if isinstance(as_of, str) else as_of or date.today()
    )
    if timeout_seconds <= 0 or min_interval_seconds < 0:
        raise PolicyUpdateError("timeout_seconds must be positive and interval non-negative")
    root = Path(output_dir)
    state_path = root / "state.json"
    records_path = root / "records.json"
    feed_path = root / "candidate-feed.csv"
    receipt_path = root / "sync-receipt.json"
    previous_state = _read_json(state_path, {})
    previous_by_id = {
        str(item.get("policy_id")): item
        for item in previous_state.get("sources", [])
        if isinstance(item, dict) and item.get("policy_id")
    }
    previous_records = {
        str(item.get("policy_id")): item
        for item in _read_json(records_path, {}).get("records", [])
        if isinstance(item, dict) and item.get("policy_id")
    }
    allowed_hosts = set(manifest["allowed_hosts"])
    fetched_at = now or _utc_now()
    own_client = client is None
    http_client = client or httpx.Client(timeout=timeout_seconds)
    records: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    last_request_by_host: dict[str, float] = {}
    try:
        for source in manifest["sources"]:
            policy_id = source["policy_id"]
            source_url = source["source_url"]
            host = (urlsplit(source_url).hostname or "").casefold()
            previous = previous_by_id.get(policy_id, {})
            conditional: dict[str, str] = {}
            if previous.get("etag"):
                conditional["If-None-Match"] = str(previous["etag"])
            if previous.get("last_modified"):
                conditional["If-Modified-Since"] = str(previous["last_modified"])
            elapsed = time.monotonic() - last_request_by_host.get(host, 0.0)
            if elapsed < min_interval_seconds:
                time.sleep(min_interval_seconds - elapsed)
            try:
                response = _fetch(
                    http_client,
                    source_url,
                    allowed_hosts=allowed_hosts,
                    conditional_headers=conditional,
                )
                last_request_by_host[host] = time.monotonic()
                if response.status_code == 304:
                    prior_record = previous_records.get(policy_id)
                    if not isinstance(prior_record, dict):
                        raise PolicyUpdateError(
                            "Received 304 without a prior local policy snapshot"
                        )
                    record = dict(prior_record)
                    record.update(
                        {
                            "http_status": 304,
                            "fetched_at": fetched_at,
                            "change_status": "not_modified",
                        }
                    )
                else:
                    response.raise_for_status()
                    raw = bytes(response.content)
                    if len(raw) > MAX_PAGE_BYTES:
                        raise PolicyUpdateError("Official policy page exceeds the size limit")
                    parsed = parse_official_policy_page(raw, source_url=source_url)
                    record = _candidate_record(
                        source,
                        parsed=parsed,
                        fetched_at=fetched_at,
                        http_status=int(response.status_code),
                        headers=response.headers,
                        raw_sha256=_digest_bytes(raw),
                        previous_digest=str(previous.get("normalized_sha256") or ""),
                        as_of=evaluation_date,
                    )
                    raw_dir = root / "raw"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    (raw_dir / f"{policy_id}.html").write_bytes(raw)
                records.append(record)
                events.append(
                    {
                        "policy_id": policy_id,
                        "source_url": source_url,
                        "status": "ok",
                        "http_status": record["http_status"],
                        "change_status": record["change_status"],
                        "normalized_sha256": record["normalized_sha256"],
                    }
                )
            except (PolicyUpdateError, httpx.HTTPError, OSError) as exc:
                prior_record = previous_records.get(policy_id)
                if isinstance(prior_record, dict):
                    stale = dict(prior_record)
                    stale.update(
                        {
                            "http_status": 0,
                            "fetched_at": fetched_at,
                            "change_status": "fetch_error_previous_snapshot_retained",
                            "review_status": "candidate_pending_review",
                        }
                    )
                    records.append(stale)
                events.append(
                    {
                        "policy_id": policy_id,
                        "source_url": source_url,
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "message": _clean(exc, limit=500),
                        "previous_snapshot_retained": isinstance(prior_record, dict),
                    }
                )
    finally:
        if own_client:
            http_client.close()

    records.sort(key=lambda item: str(item["policy_id"]).casefold())
    events.sort(key=lambda item: str(item["policy_id"]).casefold())
    state = {
        "schema_version": POLICY_UPDATE_SCHEMA_VERSION,
        "parser_version": POLICY_UPDATE_PARSER_VERSION,
        "generated_at": fetched_at,
        "evaluated_as_of": evaluation_date.isoformat(),
        "manifest_path": manifest["path"],
        "manifest_sha256": _digest_bytes(Path(manifest_path).read_bytes()),
        "sources": [
            {
                key: record.get(key)
                for key in (
                    "policy_id",
                    "source_url",
                    "etag",
                    "last_modified",
                    "fetched_at",
                    "raw_sha256",
                    "normalized_sha256",
                    "change_status",
                    "review_status",
                )
            }
            for record in records
        ],
    }
    _write_json(state_path, state)
    _write_json(
        records_path,
        {
            "schema_version": POLICY_UPDATE_SCHEMA_VERSION,
            "generated_at": fetched_at,
            "records": records,
        },
    )
    _write_candidate_csv(feed_path, records)
    counts = Counter(event["status"] for event in events)
    changes = Counter(
        str(record.get("change_status") or "unknown") for record in records
    )
    receipt = {
        "schema_version": POLICY_UPDATE_SCHEMA_VERSION,
        "generated_at": fetched_at,
        "evaluated_as_of": evaluation_date.isoformat(),
        "source_count": len(manifest["sources"]),
        "candidate_count": len(records),
        "status_counts": dict(sorted(counts.items())),
        "change_counts": dict(sorted(changes.items())),
        "events": events,
        "outputs": {
            "candidate_feed": str(feed_path.resolve()),
            "records": str(records_path.resolve()),
            "state": str(state_path.resolve()),
        },
        "authority": "official_source_refresh_candidates_only",
        "human_review_required": True,
        "automatic_catalog_promotion": False,
        "eligibility_determination": False,
    }
    _write_json(receipt_path, receipt)
    return receipt


def load_policy_update_feed(path: str | Path) -> dict[str, Any]:
    """Read the quarantined CSV feed for a safe workbench status view."""

    source = Path(path)
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            required = {
                "policy_id",
                "title",
                "source_url",
                "application_status",
                "review_status",
                "normalized_sha256",
            }
            missing = sorted(required - set(headers))
            if missing:
                raise PolicyUpdateError(
                    f"Policy update feed is missing required columns: {missing}"
                )
            items = []
            seen_ids: set[str] = set()
            for row_number, raw in enumerate(reader, start=2):
                policy_id = _clean(raw.get("policy_id"), limit=120)
                title = _clean(raw.get("title"), limit=500)
                source_url = _allowed_url(
                    _clean(raw.get("source_url"), limit=2_000),
                    DEFAULT_ALLOWED_HOSTS,
                )
                if not policy_id or not title:
                    raise PolicyUpdateError(
                        f"Policy update feed row {row_number} requires id and title"
                    )
                key = policy_id.casefold()
                if key in seen_ids:
                    raise PolicyUpdateError(f"Duplicate policy_id in update feed: {policy_id}")
                seen_ids.add(key)
                review_status = _clean(raw.get("review_status"), limit=80)
                if review_status != "candidate_pending_review":
                    raise PolicyUpdateError(
                        "Policy update feed may contain only candidate_pending_review rows"
                    )
                items.append(
                    {
                        "id": policy_id,
                        "title": title,
                        "issuer": _clean(raw.get("issuer"), limit=300),
                        "source_url": source_url,
                        "published_at": _clean(raw.get("published_at"), limit=40),
                        "application_close_at": _clean(
                            raw.get("application_close_at"), limit=40
                        ),
                        "document_status": _clean(
                            raw.get("document_status"), limit=80
                        ),
                        "application_status": _clean(
                            raw.get("application_status"), limit=80
                        ),
                        "change_status": _clean(raw.get("change_status"), limit=80),
                        "fetched_at": _clean(raw.get("fetched_at"), limit=80),
                        "normalized_sha256": _clean(
                            raw.get("normalized_sha256"), limit=64
                        ),
                        "review_status": review_status,
                        "data_class": "official_source_candidate",
                        "simulation_only": False,
                        "disclosure_label": (
                            "官方来源更新候选，尚未进入企业匹配"
                        ),
                        "authority": "refresh_candidate_only",
                    }
                )
    except PolicyUpdateError:
        raise
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise PolicyUpdateError(f"Policy update feed is unreadable: {source}") from exc
    payload = source.read_bytes()
    return {
        "schema_version": POLICY_UPDATE_SCHEMA_VERSION,
        "status": "ready" if items else "empty_feed",
        "items": items,
        "catalog_metadata": {
            "file_name": source.name,
            "sha256": _digest_bytes(payload),
            "record_count": len(items),
        },
        "authority": "refresh_candidates_only",
        "boundaries": {
            "candidate_only": True,
            "human_review_required": True,
            "matching_performed": False,
            "automatic_catalog_promotion": False,
            "eligibility_determination": False,
        },
    }
