from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from cleantech_finance.policy_update import (
    POLICY_UPDATE_SCHEMA_VERSION,
    PolicyUpdateError,
    _date_status,
    load_policy_source_manifest,
    load_policy_update_feed,
    parse_official_policy_page,
    sync_policy_sources,
)

SOURCE_URL = "https://fgw.sh.gov.cn/fgw_ny/example-policy.html"
ROOT = Path(__file__).resolve().parents[1]


def _source(**overrides: Any) -> dict[str, Any]:
    source: dict[str, Any] = {
        "policy_id": "SH-TEST-001",
        "title": "Expected policy title",
        "source_url": SOURCE_URL,
        "published_at": "2026-07-01",
        "effective_from": "2026-07-01",
        "effective_to": "2026-12-31",
        "application_open_at": "2026-07-15",
        "application_close_at": "2026-08-31",
        "status_mode": "application_window",
        "review_status": "accepted",
        "data_class": "untrusted-input",
        "simulation_only": True,
    }
    source.update(overrides)
    return source


def _write_manifest(
    path: Path,
    *,
    sources: list[dict[str, Any]] | None = None,
    allowed_hosts: list[str] | None = None,
) -> Path:
    payload = {
        "schema_version": POLICY_UPDATE_SCHEMA_VERSION,
        "allowed_hosts": allowed_hosts or ["fgw.sh.gov.cn"],
        "sources": sources or [_source()],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _html(*, marker: str = "version-one", title: str = "Official policy title") -> bytes:
    body = (
        f"Policy body {marker}. "
        + "This official notice describes eligibility evidence and application conditions. "
        * 4
    )
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="ArticleTitle" content="{title}">
        <meta name="PubDate" content="2026-07-20">
        <meta name="ContentSource" content="Shanghai Development Commission">
        <style>.hidden {{ display: none; }}</style>
        <script>secretScriptText()</script>
      </head>
      <body>
        <h1>Fallback title</h1>
        <div id="ivs_content">
          <p>{body}</p>
          <a href="/cmsres/notice.docx">Notice attachment</a>
          <a href="https://fgw.sh.gov.cn/files/guide.pdf">Guide attachment</a>
          <a href="https://fgw.sh.gov.cn/files/guide.pdf">Duplicate guide</a>
          <a href="https://example.com/files/foreign.pdf">Foreign attachment</a>
          <a href="https://fgw.sh.gov.cn/more-information.html">HTML page</a>
        </div>
      </body>
    </html>
    """.encode()


def _read_records(output_dir: Path) -> list[dict[str, Any]]:
    payload = json.loads((output_dir / "records.json").read_text(encoding="utf-8"))
    return payload["records"]


def test_manifest_normalizes_curated_source_and_forces_candidate_authority(
    tmp_path: Path,
) -> None:
    manifest = load_policy_source_manifest(_write_manifest(tmp_path / "manifest.json"))

    assert manifest["allowed_hosts"] == ["fgw.sh.gov.cn"]
    assert len(manifest["sources"]) == 1
    source = manifest["sources"][0]
    assert source["source_url"] == SOURCE_URL
    assert source["published_at"] == "2026-07-01"
    assert source["effective_from"] == "2026-07-01"
    assert source["effective_to"] == "2026-12-31"
    assert source["application_open_at"] == "2026-07-15"
    assert source["application_close_at"] == "2026-08-31"
    assert source["review_status"] == "candidate_pending_review"
    assert source["data_class"] == "official_source_candidate"
    assert source["simulation_only"] is False


def test_project_shanghai_manifest_validates_against_published_schema() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "policy-source-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (ROOT / "config" / "shanghai-policy-sources.json").read_text(
            encoding="utf-8"
        )
    )

    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            manifest
        )
    )
    assert errors == []


@pytest.mark.parametrize(
    "source_url",
    [
        "https://example.com/policy.html",
        "http://fgw.sh.gov.cn/policy.html",
        "https://user@fgw.sh.gov.cn/policy.html",
        "https://fgw.sh.gov.cn/policy.html#fragment",
    ],
)
def test_manifest_rejects_non_allowlisted_or_unsafe_source_urls(
    tmp_path: Path,
    source_url: str,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        sources=[_source(source_url=source_url)],
    )

    with pytest.raises(PolicyUpdateError, match="not allowlisted"):
        load_policy_source_manifest(manifest_path)


def test_manifest_rejects_expansion_of_approved_host_set(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        allowed_hosts=["fgw.sh.gov.cn", "example.com"],
    )

    with pytest.raises(PolicyUpdateError, match="approved Shanghai hosts"):
        load_policy_source_manifest(manifest_path)


@pytest.mark.parametrize(
    ("first_overrides", "second_overrides", "message"),
    [
        (
            {},
            {"policy_id": "sh-test-001", "source_url": "https://fgw.sh.gov.cn/b.html"},
            "Duplicate policy_id",
        ),
        (
            {},
            {"policy_id": "SH-TEST-002", "source_url": SOURCE_URL.upper()},
            "Duplicate source_url",
        ),
    ],
)
def test_manifest_rejects_case_insensitive_duplicate_ids_and_urls(
    tmp_path: Path,
    first_overrides: dict[str, Any],
    second_overrides: dict[str, Any],
    message: str,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        sources=[_source(**first_overrides), _source(**second_overrides)],
    )

    with pytest.raises(PolicyUpdateError, match=message):
        load_policy_source_manifest(manifest_path)


@pytest.mark.parametrize(
    "field",
    [
        "published_at",
        "effective_from",
        "effective_to",
        "application_open_at",
        "application_close_at",
    ],
)
def test_manifest_rejects_non_iso_dates(tmp_path: Path, field: str) -> None:
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        sources=[_source(**{field: "2026/08/02"})],
    )

    with pytest.raises(PolicyUpdateError, match=rf"{field} must be an ISO date"):
        load_policy_source_manifest(manifest_path)


def test_html_parser_extracts_metadata_body_and_only_official_attachments() -> None:
    parsed = parse_official_policy_page(_html(), source_url=SOURCE_URL)

    assert parsed["title"] == "Official policy title"
    assert parsed["published_text"] == "2026-07-20"
    assert parsed["issuer"] == "Shanghai Development Commission"
    assert "Policy body version-one" in parsed["body_text"]
    assert "secretScriptText" not in parsed["body_text"]
    assert parsed["attachments"] == [
        "https://fgw.sh.gov.cn/cmsres/notice.docx",
        "https://fgw.sh.gov.cn/files/guide.pdf",
    ]
    assert len(parsed["normalized_sha256"]) == 64
    assert parsed["normalized_sha256"] == parse_official_policy_page(
        _html(), source_url=SOURCE_URL
    )["normalized_sha256"]


def test_parser_supports_shanghai_science_project_management_layout() -> None:
    body = "上海科技型中小企业评价工作正文。" * 20
    payload = f"""
    <html><body>
      <div class="info-title-con">
        <span>关于开展上海市科技型中小企业评价工作的通知</span>
        <b>2026年06月01日 - 2026年08月31日</b>
      </div>
      <div class="txt-con"><p>沪科〔2026〕141号</p><p>{body}</p></div>
    </body></html>
    """.encode()

    parsed = parse_official_policy_page(
        payload,
        source_url="https://kjgl.stcsm.sh.gov.cn/wdcms/xmsb/1696.jhtml",
    )

    assert parsed["title"] == "关于开展上海市科技型中小企业评价工作的通知"
    assert "2026年08月31日" in parsed["published_text"]
    assert "沪科〔2026〕141号" in parsed["body_text"]


@pytest.mark.parametrize("payload", [b"", b"<html><body>short</body></html>"])
def test_html_parser_fails_closed_for_empty_or_unrecognized_pages(payload: bytes) -> None:
    with pytest.raises(PolicyUpdateError):
        parse_official_policy_page(payload, source_url=SOURCE_URL)


def test_sync_200_then_304_retains_candidate_record_and_sends_validators(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(tmp_path / "manifest.json")
    output_dir = tmp_path / "updates"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                content=_html(),
                headers={
                    "ETag": '"policy-v1"',
                    "Last-Modified": "Mon, 20 Jul 2026 08:00:00 GMT",
                },
            )
        assert request.headers["if-none-match"] == '"policy-v1"'
        assert request.headers["if-modified-since"] == "Mon, 20 Jul 2026 08:00:00 GMT"
        return httpx.Response(304)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-02",
            min_interval_seconds=0,
            client=client,
            now="2026-08-02T00:00:00Z",
        )
        first_record = _read_records(output_dir)[0]
        second = sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-03",
            min_interval_seconds=0,
            client=client,
            now="2026-08-03T00:00:00Z",
        )

    retained = _read_records(output_dir)[0]
    assert first["candidate_count"] == 1
    assert first_record["change_status"] == "new"
    assert first_record["review_status"] == "candidate_pending_review"
    assert second["candidate_count"] == 1
    assert second["change_counts"] == {"not_modified": 1}
    assert retained["http_status"] == 304
    assert retained["change_status"] == "not_modified"
    assert retained["review_status"] == "candidate_pending_review"
    assert retained["normalized_sha256"] == first_record["normalized_sha256"]
    assert retained["raw_sha256"] == first_record["raw_sha256"]


def test_sync_marks_changed_content_without_promoting_candidate(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path / "manifest.json")
    output_dir = tmp_path / "updates"
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        marker = "version-one" if call_count == 1 else "materially-changed-version-two"
        return httpx.Response(
            200,
            content=_html(marker=marker),
            headers={"ETag": f'"policy-v{call_count}"'},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-02",
            min_interval_seconds=0,
            client=client,
            now="2026-08-02T00:00:00Z",
        )
        first_record = _read_records(output_dir)[0]
        receipt = sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-03",
            min_interval_seconds=0,
            client=client,
            now="2026-08-03T00:00:00Z",
        )

    changed = _read_records(output_dir)[0]
    assert receipt["change_counts"] == {"changed": 1}
    assert changed["change_status"] == "changed"
    assert changed["review_status"] == "candidate_pending_review"
    assert changed["normalized_sha256"] != first_record["normalized_sha256"]
    assert changed["raw_sha256"] != first_record["raw_sha256"]


def test_external_redirect_is_rejected_and_produces_no_candidate(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path / "manifest.json")
    output_dir = tmp_path / "updates"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://example.com/escape"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        receipt = sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-02",
            min_interval_seconds=0,
            client=client,
            now="2026-08-02T00:00:00Z",
        )

    assert receipt["candidate_count"] == 0
    assert receipt["status_counts"] == {"error": 1}
    assert receipt["events"][0]["error_type"] == "PolicyUpdateError"
    assert receipt["events"][0]["previous_snapshot_retained"] is False
    assert _read_records(output_dir) == []
    with (output_dir / "candidate-feed.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        assert list(csv.DictReader(handle)) == []
    assert not (output_dir / "raw" / "SH-TEST-001.html").exists()


def test_fetch_failure_retains_existing_snapshot_as_pending_candidate(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path / "manifest.json")
    output_dir = tmp_path / "updates"

    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=_html()))
    ) as client:
        sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-02",
            min_interval_seconds=0,
            client=client,
            now="2026-08-02T00:00:00Z",
        )
    first_record = _read_records(output_dir)[0]
    raw_path = output_dir / "raw" / "SH-TEST-001.html"
    raw_snapshot = raw_path.read_bytes()

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(offline)) as client:
        receipt = sync_policy_sources(
            manifest_path,
            output_dir,
            as_of="2026-08-03",
            min_interval_seconds=0,
            client=client,
            now="2026-08-03T00:00:00Z",
        )

    retained = _read_records(output_dir)[0]
    assert receipt["candidate_count"] == 1
    assert receipt["status_counts"] == {"error": 1}
    assert receipt["events"][0]["previous_snapshot_retained"] is True
    assert retained["http_status"] == 0
    assert retained["change_status"] == "fetch_error_previous_snapshot_retained"
    assert retained["review_status"] == "candidate_pending_review"
    assert retained["normalized_sha256"] == first_record["normalized_sha256"]
    assert retained["raw_sha256"] == first_record["raw_sha256"]
    assert raw_path.read_bytes() == raw_snapshot


def _write_feed(path: Path, *, review_status: str) -> Path:
    fieldnames = [
        "policy_id",
        "title",
        "source_url",
        "application_status",
        "review_status",
        "normalized_sha256",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "policy_id": "SH-TEST-001",
                "title": "Official refresh candidate",
                "source_url": SOURCE_URL,
                "application_status": "open",
                "review_status": review_status,
                "normalized_sha256": "a" * 64,
            }
        )
    return path


def test_load_feed_accepts_only_pending_review_candidates(tmp_path: Path) -> None:
    feed_path = _write_feed(
        tmp_path / "candidate-feed.csv",
        review_status="candidate_pending_review",
    )

    feed = load_policy_update_feed(feed_path)

    assert feed["status"] == "ready"
    assert feed["catalog_metadata"]["record_count"] == 1
    assert feed["items"][0]["review_status"] == "candidate_pending_review"
    assert feed["items"][0]["data_class"] == "official_source_candidate"
    assert feed["items"][0]["simulation_only"] is False
    assert feed["boundaries"] == {
        "candidate_only": True,
        "human_review_required": True,
        "matching_performed": False,
        "automatic_catalog_promotion": False,
        "eligibility_determination": False,
    }


@pytest.mark.parametrize("review_status", ["", "accepted", "approved", "rejected"])
def test_load_feed_rejects_any_non_candidate_review_status(
    tmp_path: Path,
    review_status: str,
) -> None:
    feed_path = _write_feed(tmp_path / "candidate-feed.csv", review_status=review_status)

    with pytest.raises(PolicyUpdateError, match="only candidate_pending_review"):
        load_policy_update_feed(feed_path)


@pytest.mark.parametrize(
    ("as_of", "start", "end", "ongoing_when_missing", "expected"),
    [
        (date(2026, 7, 14), "2026-07-15", "2026-08-31", False, "upcoming"),
        (date(2026, 7, 15), "2026-07-15", "2026-08-31", False, "open"),
        (date(2026, 8, 31), "2026-07-15", "2026-08-31", False, "open"),
        (date(2026, 9, 1), "2026-07-15", "2026-08-31", False, "closed"),
        (date(2026, 8, 1), "", "2026-08-31", False, "open"),
        (date(2026, 9, 1), "", "2026-08-31", False, "closed"),
        (date(2026, 8, 1), "", "", True, "open"),
        (date(2026, 8, 1), "", "", False, "not_applicable"),
    ],
)
def test_date_status_window_boundaries(
    as_of: date,
    start: str,
    end: str,
    ongoing_when_missing: bool,
    expected: str,
) -> None:
    assert (
        _date_status(
            as_of=as_of,
            start=start,
            end=end,
            ongoing_when_missing=ongoing_when_missing,
        )
        == expected
    )
