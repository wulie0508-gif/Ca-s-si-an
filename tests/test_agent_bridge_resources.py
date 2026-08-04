from __future__ import annotations

import csv
import io
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from cleantech_finance.agent_bridge import (
    AgentBridgeServer,
    create_agent_bridge_server,
)
from cleantech_finance.cli import build_parser
from cleantech_finance.enterprise_matching import (
    browse_catalog_resources,
    load_catalog,
)
from cleantech_finance.mentor_matching import REQUIRED_COLUMNS, MentorCatalogError

ROOT = Path(__file__).resolve().parents[1]


def _write_rows(path: Path, fieldnames: list[str] | tuple[str, ...], rows: list[dict[str, str]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding="utf-8")


def _write_policy_catalog(path: Path, *, include_rows: bool = True) -> None:
    fieldnames = [
        "policy_id",
        "title",
        "review_status",
        "valid_until",
        "industry_tags",
        "provider",
        "source_url",
    ]
    rows = []
    if include_rows:
        rows = [
            {
                "policy_id": "POLICY-CURRENT",
                "title": "Hydrogen demonstration reference",
                "review_status": "pending_manual_review",
                "valid_until": "2999-12-31",
                "industry_tags": "hydrogen",
                "provider": "Official agency",
                "source_url": "https://official.example.test/policy-current",
            },
            {
                "policy_id": "POLICY-EXPIRED",
                "title": "Expired policy reference",
                "review_status": "pending_manual_review",
                "valid_until": "2000-01-01",
                "industry_tags": "hydrogen",
                "provider": "Official agency",
                "source_url": "https://official.example.test/policy-expired",
            },
        ]
    _write_rows(path, fieldnames, rows)


def _write_policy_update_feed(path: Path) -> None:
    _write_rows(
        path,
        [
            "policy_id",
            "title",
            "issuer",
            "source_url",
            "application_status",
            "document_status",
            "change_status",
            "fetched_at",
            "review_status",
            "normalized_sha256",
        ],
        [
            {
                "policy_id": "SH-UPDATE-001",
                "title": "上海清洁能源政策更新候选",
                "issuer": "上海市发展和改革委员会",
                "source_url": "https://fgw.sh.gov.cn/fgw_ny/update.html",
                "application_status": "open",
                "document_status": "open",
                "change_status": "new",
                "fetched_at": "2026-08-02T12:00:00Z",
                "review_status": "candidate_pending_review",
                "normalized_sha256": "a" * 64,
            }
        ],
    )


def _write_attestation(catalog_path: Path, attestation_path: Path) -> None:
    catalog = load_catalog(catalog_path)
    attestation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "catalog_sha256": catalog["sha256"],
                "byte_length": catalog["byte_length"],
                "canonical_view_sha256": catalog["canonical_view_sha256"],
                "parser_version": catalog["parser_version"],
                "source_sheet": catalog["source_sheet"],
                "header_row": catalog["header_row"],
                "record_count": len(catalog["rows"]),
                "attested_by": "project-owner",
                "attested_at": "2020-01-01T00:00:00+00:00",
                "scope": "reference_suggestions",
                "review_status": "reviewed",
                "not_eligibility_determination": True,
                "official_verification_required": True,
                "revoked": False,
                "statement": "Confirmed only as a reference catalog.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_course_catalog(path: Path, *, include_rows: bool = True) -> None:
    rows = (
        [
            {
                "course_id": "COURSE-001",
                "title": "Hydrogen commercialization workshop",
                "review_status": "published",
                "provider": "NEX Learning",
                "source_url": "https://learning.example.test/course-001",
                "industry_tags": "hydrogen",
                "stage_tags": "early commercialization",
                "need_tags": "commercialization",
                "technology_tags": "hydrogen",
                "geography_tags": "China",
                "market_tags": "industrial",
            }
        ]
        if include_rows
        else []
    )
    _write_rows(
        path,
        [
            "course_id",
            "title",
            "review_status",
            "provider",
            "source_url",
            "industry_tags",
            "stage_tags",
            "need_tags",
            "technology_tags",
            "geography_tags",
            "market_tags",
        ],
        rows,
    )


def _mentor_row(mentor_id: str, *, consent_status: str = "consented") -> dict[str, str]:
    return {
        "mentor_id": mentor_id,
        "display_name": f"Mentor {mentor_id}",
        "expertise_tags": "hydrogen|commercialization",
        "industry_tags": "clean energy",
        "stage_tags": "early commercialization",
        "geography_tags": "China|USA",
        "market_tags": "industrial",
        "languages": "Chinese|English",
        "availability_status": "available",
        "consent_status": consent_status,
        "conflict_status": "clear",
        "valid_until": "2999-12-31",
        "source": "mentor operations",
        "source_url": "https://mentors.example.test/directory",
        "updated_at": "2026-08-01T09:00:00+08:00",
    }


def _write_mentor_catalog(path: Path, *, include_rows: bool = True) -> None:
    rows = (
        [
            _mentor_row("mentor-eligible"),
            _mentor_row("mentor-unconsented", consent_status="pending"),
        ]
        if include_rows
        else []
    )
    _write_rows(path, REQUIRED_COLUMNS, rows)


def _create_profile_case(
    server: AgentBridgeServer,
    *,
    case_name: str,
    industry: str = "hydrogen",
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "company": {
                "legal_name": case_name,
                "industry": industry,
                "stage": "early commercialization",
                "technology_or_solution": industry,
                "country": "China",
                "target_markets": ["industrial"],
            }
        }
    ).encode("utf-8")
    return server.workspace.create_case(
        case_name=case_name,
        files=[("case.json", payload, "application/json")],
    )


def _create_empty_profile_case(
    server: AgentBridgeServer,
    *,
    case_name: str,
) -> dict[str, Any]:
    return server.workspace.create_case(
        case_name=case_name,
        files=[("notes.txt", b"general notes only", "text/plain")],
    )


@contextmanager
def _running_server(server: AgentBridgeServer) -> Iterator[str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request_json(
    url: str,
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _request_bytes(url: str) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def test_resource_endpoint_returns_real_policy_course_and_safe_mentor_rows(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    attestation = tmp_path / "policy-attestation.json"
    course = tmp_path / "course.csv"
    mentor = tmp_path / "mentor.csv"
    _write_policy_catalog(policy)
    _write_attestation(policy, attestation)
    _write_course_catalog(course)
    _write_mentor_catalog(mentor)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
        policy_attestation=attestation,
        course_catalog=course,
        mentor_catalog=mentor,
    )

    with _running_server(server) as base_url:
        status, result = _request_json(f"{base_url}/api/ui/resources")

    assert status == 200
    policy_resource = result["resources"]["policy"]
    assert policy_resource["status"] == "ready"
    assert [item["id"] for item in policy_resource["items"]] == ["POLICY-CURRENT"]
    policy_item = policy_resource["items"][0]
    assert policy_item == {
        "id": "POLICY-CURRENT",
        "title": "Hydrogen demonstration reference",
        "source_url": "https://official.example.test/policy-current",
        "provider": "Official agency",
        "effective_status": (
            "within_catalog_date_window_requires_official_verification"
        ),
        "effective_status_label_zh": "目录时效未见过期，仍须按官方原文核验",
        "review_status": "项目方确认可作参考",
        "source_review_status": "pending_manual_review",
        "review_status_authority": "catalog_sha256_attestation_reference_only",
        "source_row": 2,
        "source_sheet": None,
        "catalog_sha256": policy_resource["catalog_metadata"]["sha256"],
        "authority": "reference_catalog_entry_only",
        "not_eligibility_determination": True,
        "requires_live_official_verification": True,
    }
    assert policy_resource["attestation"]["status"] == "confirmed_for_reference_only"
    assert policy_resource["attestation"]["not_eligibility_determination"] is True
    assert policy_resource["attestation"]["official_live_verification_required"] is True
    assert "不确认单条政策资格" in policy_resource["attestation"]["meaning_zh"]
    assert policy_item["source_review_status"] == "pending_manual_review"
    assert policy_item["review_status"] != policy_item["source_review_status"]
    assert policy_item["not_eligibility_determination"] is True
    assert policy_item["requires_live_official_verification"] is True
    assert policy_resource["excluded_reason_counts"] == {"expired": 1}

    course_resource = result["resources"]["course"]
    assert course_resource["status"] == "ready"
    assert course_resource["template_url"] == "/templates/course-catalog-template.csv"
    assert course_resource["items"][0]["id"] == "COURSE-001"
    assert course_resource["items"][0]["provider"] == "NEX Learning"

    mentor_resource = result["resources"]["mentor"]
    assert mentor_resource["status"] == "ready"
    assert mentor_resource["template_url"] == "/templates/mentor-catalog-template.csv"
    assert [item["mentor_id"] for item in mentor_resource["items"]] == [
        "mentor-eligible"
    ]
    assert mentor_resource["excluded_reason_counts"] == {"consent_not_granted": 1}
    assert mentor_resource["boundaries"]["matching_performed"] is False
    assert mentor_resource["boundaries"]["automatic_assignment"] is False

    keys = _all_keys(result)
    assert "score" not in keys
    assert "relevance_score" not in keys
    assert "assigned_mentor_id" not in keys
    assert result["boundaries"]["real_catalog_rows_only"] is True
    assert result["boundaries"]["examples_generated"] is False


def test_agent_resource_tools_are_scoped_and_keep_updates_and_simulation_explicit(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    attestation = tmp_path / "policy-attestation.json"
    update_feed = tmp_path / "policy-update-feed.csv"
    _write_policy_catalog(policy)
    _write_attestation(policy, attestation)
    _write_policy_update_feed(update_feed)
    course = ROOT / "examples" / "resource-catalog" / "synthetic-courses.csv"
    mentor = ROOT / "examples" / "resource-catalog" / "synthetic-mentors.csv"
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
        policy_attestation=attestation,
        policy_update_feed=update_feed,
        course_catalog=course,
        mentor_catalog=mentor,
    )
    read_grant = server.registry.issue(
        actor="read-agent",
        scopes={"resource:read"},
        acknowledge_human_review=True,
    )
    match_grant = server.registry.issue(
        actor="match-agent",
        scopes={"resource:read", "resource:match"},
        acknowledge_human_review=True,
    )
    profile_tags = {
        "industry": ["清洁能源"],
        "stage": ["早期商业化"],
        "need": ["融资"],
        "technology": ["光伏"],
        "geography": ["上海"],
        "market": ["工业脱碳"],
    }

    with _running_server(server) as base_url:
        no_consent_status, _ = _request_json(f"{base_url}/api/agent/resources")
        read_status, directory = _request_json(
            f"{base_url}/api/agent/resources",
            token=read_grant["token"],
        )
        wrong_scope_status, _ = _post_json(
            f"{base_url}/api/agent/resource-match",
            {"category": "course", "profile_tags": profile_tags},
            token=read_grant["token"],
        )
        course_status, course_result = _post_json(
            f"{base_url}/api/agent/resource-match",
            {"category": "course", "profile_tags": profile_tags},
            token=match_grant["token"],
        )
        mentor_status, mentor_result = _post_json(
            f"{base_url}/api/agent/resource-match",
            {"category": "mentor", "profile_tags": profile_tags},
            token=match_grant["token"],
        )
        policy_status, policy_result = _post_json(
            f"{base_url}/api/agent/resource-match",
            {"category": "policy", "profile_tags": profile_tags},
            token=match_grant["token"],
        )

    assert no_consent_status == 403
    assert read_status == 200
    updates = directory["resources"]["policy"]["updates"]
    assert updates["items"][0]["id"] == "SH-UPDATE-001"
    assert updates["items"][0]["review_status"] == "candidate_pending_review"
    assert updates["boundaries"]["automatic_catalog_promotion"] is False
    assert directory["boundaries"]["synthetic_fixture_count"] == 22
    assert directory["boundaries"]["synthetic_fixtures_are_people_or_live_courses"] is False

    assert wrong_scope_status == 403
    assert course_status == 200
    assert course_result["matches"]
    assert all(item["simulation_only"] is True for item in course_result["matches"])
    assert course_result["agent_can_enroll"] is False
    assert course_result["human_confirmation_required"] is True

    assert mentor_status == 200
    assert mentor_result["candidate_matches"]
    assert all(
        item["simulation_only"] is True
        and item["contactable"] is False
        and item["display_name"].startswith("模拟导师")
        for item in mentor_result["candidate_matches"]
    )
    assert mentor_result["ordering"] == "mentor_id_casefold_ascending_not_ranked"
    assert mentor_result["agent_can_assign"] is False
    assert mentor_result["agent_can_contact"] is False

    assert policy_status == 400
    assert policy_result["error"] == "invalid_resource_match_request"


def test_policy_browser_hides_placeholder_provider_and_keeps_official_url(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy-cn.csv"
    attestation = tmp_path / "policy-cn-attestation.json"
    _write_rows(
        policy,
        [
            "policy_id",
            "政策名称",
            "发布机构",
            "有效期/申报窗口",
            "复核状态",
            "原文来源 URL",
        ],
        [
            {
                "policy_id": "P001",
                "政策名称": "中华人民共和国能源法",
                "发布机构": "待人工从原文确认",
                "有效期/申报窗口": "原文待人工核验",
                "复核状态": "待复核",
                "原文来源 URL": "https://www.gov.cn/example",
            }
        ],
    )
    _write_attestation(policy, attestation)

    result = browse_catalog_resources(
        policy,
        category="policy",
        attestation_path=attestation,
    )

    item = result["items"][0]
    assert item["provider"] == ""
    assert item["source_url"] == "https://www.gov.cn/example"
    assert item["review_status"] == "项目方确认可作参考"
    assert item["source_review_status"] == "待复核"
    assert item["effective_status_label_zh"] == "时效字段需按官方原文核验"
    assert item["requires_live_official_verification"] is True


def test_resource_endpoint_distinguishes_not_connected_from_empty_catalogs(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    attestation = tmp_path / "policy-attestation.json"
    _write_policy_catalog(policy, include_rows=False)
    _write_attestation(policy, attestation)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace-not-connected",
        policy_attestation=attestation,
    )
    with _running_server(server) as base_url:
        status, result = _request_json(f"{base_url}/api/ui/resources")

    assert status == 200
    assert result["resources"]["policy"]["status"] == "empty_catalog"
    assert result["resources"]["course"]["status"] == "not_connected"
    assert result["resources"]["course"]["template_url"] == (
        "/templates/course-catalog-template.csv"
    )
    assert result["resources"]["course"]["items"] == []
    assert result["resources"]["mentor"]["status"] == "not_connected"
    assert result["resources"]["mentor"]["template_url"] == (
        "/templates/mentor-catalog-template.csv"
    )
    assert result["resources"]["mentor"]["items"] == []

    course = tmp_path / "empty-course.csv"
    mentor = tmp_path / "empty-mentor.csv"
    _write_course_catalog(course, include_rows=False)
    _write_mentor_catalog(mentor, include_rows=False)
    connected_server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace-empty",
        policy_attestation=attestation,
        course_catalog=course,
        mentor_catalog=mentor,
    )
    with _running_server(connected_server) as base_url:
        status, connected_result = _request_json(f"{base_url}/api/ui/resources")

    assert status == 200
    assert connected_result["resources"]["course"]["status"] == "empty_catalog"
    assert connected_result["resources"]["mentor"]["status"] == "empty_catalog"
    assert connected_result["resources"]["course"]["items"] == []
    assert connected_result["resources"]["mentor"]["items"] == []


def test_catalog_templates_download_with_fixed_attachment_headers(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    _write_policy_catalog(policy)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
    )

    with _running_server(server) as base_url:
        for file_name in (
            "course-catalog-template.csv",
            "mentor-catalog-template.csv",
        ):
            status, payload, headers = _request_bytes(
                f"{base_url}/templates/{file_name}"
            )
            repository_payload = (ROOT / "templates" / file_name).read_bytes()
            packaged_payload = (
                files("cleantech_finance").joinpath("templates", file_name).read_bytes()
            )

            assert status == 200
            assert payload == repository_payload == packaged_payload
            assert headers["Content-Type"] == "text/csv; charset=utf-8"
            assert headers["Content-Disposition"] == (
                f'attachment; filename="{file_name}"'
            )
            assert payload.decode("utf-8").count("\n") == 1


def test_template_download_route_rejects_listing_unknown_names_and_traversal(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    _write_policy_catalog(policy)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
    )
    rejected_paths = (
        "/templates/",
        "/templates/unknown.csv",
        "/templates/../pyproject.toml",
        "/templates/%2e%2e/pyproject.toml",
        "/templates/course-catalog-template.csv/extra",
    )

    with _running_server(server) as base_url:
        responses = [_request_bytes(f"{base_url}{path}") for path in rejected_paths]

    assert all(status == 404 for status, _, _ in responses)
    assert all(b"build-system" not in payload for _, payload, _ in responses)


def test_policy_rows_are_hidden_without_hash_attestation(tmp_path: Path) -> None:
    policy = tmp_path / "policy.csv"
    _write_policy_catalog(policy)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
    )

    with _running_server(server) as base_url:
        status, result = _request_json(f"{base_url}/api/ui/resources")

    assert status == 200
    policy_resource = result["resources"]["policy"]
    assert policy_resource["status"] == "attestation_required"
    assert policy_resource["items"] == []
    assert policy_resource["attestation"] is None
    assert policy_resource["boundaries"]["eligibility_determination"] is False


def test_create_server_fails_closed_for_bad_optional_catalogs_and_attestation(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    attestation = tmp_path / "policy-attestation.json"
    _write_policy_catalog(policy)
    _write_attestation(policy, attestation)
    attestation_payload = json.loads(attestation.read_text(encoding="utf-8"))
    attestation_payload["catalog_sha256"] = "0" * 64
    attestation.write_text(json.dumps(attestation_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        create_agent_bridge_server(policy, port=0, policy_attestation=attestation)

    with pytest.raises(ValueError, match="Course catalog does not exist"):
        create_agent_bridge_server(
            policy,
            port=0,
            course_catalog=tmp_path / "missing-course.csv",
        )

    invalid_mentor = tmp_path / "invalid-mentor.csv"
    invalid_row = _mentor_row("")
    _write_rows(invalid_mentor, REQUIRED_COLUMNS, [invalid_row])
    with pytest.raises(MentorCatalogError, match="mentor_id"):
        create_agent_bridge_server(policy, port=0, mentor_catalog=invalid_mentor)


def test_resource_endpoint_detects_policy_change_after_attestation(tmp_path: Path) -> None:
    policy = tmp_path / "policy.csv"
    attestation = tmp_path / "policy-attestation.json"
    _write_policy_catalog(policy)
    _write_attestation(policy, attestation)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
        policy_attestation=attestation,
    )
    policy.write_text(policy.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with _running_server(server) as base_url:
        status, result = _request_json(f"{base_url}/api/ui/resources")

    assert status == 500
    assert result["error"] == "resource_catalog_unavailable"
    assert "does not match" in result["message"]


def test_bridge_cli_accepts_optional_course_and_mentor_catalogs() -> None:
    args = build_parser().parse_args(
        [
            "bridge",
            "policy.csv",
            "--course-catalog",
            "courses.csv",
            "--mentor-catalog",
            "mentors.xlsx",
            "--policy-update-feed",
            "policy-updates.csv",
        ]
    )

    assert args.catalog == "policy.csv"
    assert args.course_catalog == "courses.csv"
    assert args.mentor_catalog == "mentors.xlsx"
    assert args.policy_update_feed == "policy-updates.csv"


def test_case_get_adds_course_and_unranked_mentor_candidates_from_profile_hints(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    attestation = tmp_path / "policy-attestation.json"
    course = tmp_path / "course.csv"
    mentor = tmp_path / "mentor.csv"
    _write_policy_catalog(policy)
    _write_attestation(policy, attestation)
    _write_course_catalog(course)
    _write_mentor_catalog(mentor)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
        policy_attestation=attestation,
        course_catalog=course,
        mentor_catalog=mentor,
    )
    created = _create_profile_case(server, case_name="Hydrogen Company")

    with _running_server(server) as base_url:
        status, case_payload = _request_json(
            f"{base_url}/api/ui/cases/{created['case_id']}"
        )

    assert status == 200
    recommendations = case_payload["resource_recommendations"]
    assert recommendations["input"]["authority"] == "routing_hint_only"
    assert recommendations["input"]["human_confirmed_as_fact"] is False
    assert "hydrogen" in recommendations["input"]["profile_tags"]["industry"]

    course_result = recommendations["course"]
    assert course_result["status"] == "matched"
    assert [item["item_id"] for item in course_result["matches"]] == ["COURSE-001"]
    course_match = course_result["matches"][0]
    assert course_match["match_score"] > 0
    assert course_match["match_score_authority"] == (
        "weighted_exact_catalog_tag_overlap_only"
    )
    assert course_match["not_company_score"] is True
    assert course_match["not_investment_score"] is True
    assert course_match["not_credit_score"] is True
    assert course_match["not_risk_score"] is True
    assert "目录标签相关性" in course_result["rules"]["match_score_semantics"]

    mentor_result = recommendations["mentor"]
    assert mentor_result["status"] == "candidate_matches_ready"
    assert [item["mentor_id"] for item in mentor_result["candidate_matches"]] == [
        "mentor-eligible"
    ]
    assert mentor_result["ordering"] == "mentor_id_casefold_ascending_not_ranked"
    assert mentor_result["boundaries"]["mentor_ranked"] is False
    assert mentor_result["boundaries"]["automatic_assignment"] is False
    assert mentor_result["boundaries"]["automatic_contact"] is False
    assert "hard_exclusions" not in mentor_result
    assert mentor_result["hard_exclusion_reason_counts"] == {
        "consent_not_granted": 1
    }
    assert "mentor-unconsented" not in json.dumps(recommendations)

    policy_result = recommendations["policy"]
    assert policy_result["status"] == "available_for_explicit_reference_query"
    assert policy_result["automatic_reference_query_run"] is False
    assert policy_result["profile_tags_used"] is False
    assert "matches" not in policy_result
    assert "suggestions" not in policy_result
    assert recommendations["boundaries"]["agent_can_upgrade_fact"] is False


def test_case_resource_recommendations_report_not_connected_catalogs(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    _write_policy_catalog(policy)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
    )
    created = _create_profile_case(server, case_name="No Resources Company")

    with _running_server(server) as base_url:
        status, case_payload = _request_json(
            f"{base_url}/api/ui/cases/{created['case_id']}"
        )

    assert status == 200
    recommendations = case_payload["resource_recommendations"]
    assert recommendations["course"]["status"] == "not_connected"
    assert recommendations["course"]["matches"] == []
    assert recommendations["mentor"]["status"] == "not_connected"
    assert recommendations["mentor"]["candidate_matches"] == []
    assert recommendations["mentor"]["boundaries"]["automatic_contact"] is False
    assert recommendations["policy"]["status"] == "attestation_required"
    assert recommendations["policy"]["automatic_reference_query_run"] is False


def test_empty_case_profile_does_not_create_course_or_mentor_candidates(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    course = tmp_path / "course.csv"
    mentor = tmp_path / "mentor.csv"
    _write_policy_catalog(policy)
    _write_course_catalog(course)
    _write_mentor_catalog(mentor)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
        course_catalog=course,
        mentor_catalog=mentor,
    )
    created = _create_empty_profile_case(server, case_name="Empty Profile")

    with _running_server(server) as base_url:
        status, case_payload = _request_json(
            f"{base_url}/api/ui/cases/{created['case_id']}"
        )

    assert status == 200
    recommendations = case_payload["resource_recommendations"]
    assert not any(recommendations["input"]["profile_tags"].values())
    assert recommendations["course"]["status"] == "insufficient_profile"
    assert recommendations["course"]["matches"] == []
    assert recommendations["mentor"]["status"] == "insufficient_profile"
    assert recommendations["mentor"]["candidate_matches"] == []
    assert recommendations["boundaries"]["profile_hints_human_confirmed_as_fact"] is False


def test_agent_case_recommendations_are_bound_to_the_consented_case(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.csv"
    course = tmp_path / "course.csv"
    mentor = tmp_path / "mentor.csv"
    _write_policy_catalog(policy)
    _write_course_catalog(course)
    _write_mentor_catalog(mentor)
    server = create_agent_bridge_server(
        policy,
        port=0,
        workspace_root=tmp_path / "workspace",
        course_catalog=course,
        mentor_catalog=mentor,
    )
    case_a = _create_profile_case(server, case_name="Case A", industry="hydrogen")
    case_b = _create_profile_case(server, case_name="Case B", industry="solar")
    grant = server.registry.issue(
        actor="case-scoped-agent",
        scopes={"case:read"},
        acknowledge_human_review=True,
        case_id=case_a["case_id"],
    )

    with _running_server(server) as base_url:
        ui_status, ui_case = _request_json(
            f"{base_url}/api/ui/cases/{case_a['case_id']}"
        )
        agent_status, agent_case = _request_json(
            f"{base_url}/api/agent/cases/{case_a['case_id']}",
            token=grant["token"],
        )
        list_status, scoped_list = _request_json(
            f"{base_url}/api/agent/cases",
            token=grant["token"],
        )
        denied_status, denied = _request_json(
            f"{base_url}/api/agent/cases/{case_b['case_id']}",
            token=grant["token"],
        )

    assert ui_status == 200
    assert agent_status == 200
    assert list_status == 200
    assert agent_case["resource_recommendations"] == ui_case[
        "resource_recommendations"
    ]
    assert scoped_list["resource_recommendations"] == ui_case[
        "resource_recommendations"
    ]
    assert scoped_list["access"]["case_id"] == case_a["case_id"]
    assert denied_status == 403
    assert denied["error"] == "consent_required"
