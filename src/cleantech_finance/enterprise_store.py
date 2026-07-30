"""SQLite system of record for enterprise assessment and triage cases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

CASE_STATUSES = {
    "intake",
    "evidence_collection",
    "assessment_ready",
    "draft",
    "pending_review",
    "approved",
    "rejected",
}
DECISION_TRANSITIONS = {
    "draft": {"pending_review"},
    "pending_review": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
}
JSON_COLUMNS = {
    "companies": {"aliases_json"},
    "cases": {"profile_json"},
    "evidence": {"metadata_json"},
    "interviews": {"segments_json", "structured_points_json"},
    "metrics": {"value_json", "evidence_ids_json"},
    "gaps": {"recompute_scope_json"},
    "recommendations": {"rationale_json"},
    "decisions": {"reasons_json", "human_confirmation_json"},
    "case_events": {"payload_json"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class AssessmentStore:
    """Own the authoritative Company -> Case assessment data model."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    legal_name TEXT NOT NULL,
                    jurisdiction TEXT,
                    registry_id TEXT,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS companies_canonical_name_uq
                    ON companies(lower(canonical_name));
                CREATE UNIQUE INDEX IF NOT EXISTS companies_registry_id_uq
                    ON companies(registry_id) WHERE registry_id IS NOT NULL AND registry_id <> '';

                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
                    external_id TEXT,
                    stage TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    owner TEXT,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    source_case_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (status IN (
                        'intake', 'evidence_collection', 'assessment_ready', 'draft',
                        'pending_review', 'approved', 'rejected'
                    ))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS cases_external_id_uq
                    ON cases(external_id) WHERE external_id IS NOT NULL AND external_id <> '';

                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    evidence_key TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    source TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    date TEXT,
                    entity_id TEXT NOT NULL,
                    source_level TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    source_url TEXT,
                    sha256 TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(case_id, evidence_key),
                    CHECK (source_level IN ('L1', 'L2', 'L3', 'L4')),
                    CHECK (evidence_type IN ('fact', 'opinion', 'owner_statement')),
                    CHECK (confidence IN ('high', 'medium', 'low')),
                    CHECK (review_status IN ('verified', 'pending'))
                );
                CREATE INDEX IF NOT EXISTS evidence_case_idx ON evidence(case_id);

                CREATE TABLE IF NOT EXISTS interviews (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    audio_path TEXT,
                    transcript_path TEXT NOT NULL,
                    transcript_sha256 TEXT NOT NULL,
                    language TEXT,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    consent_ref TEXT NOT NULL,
                    segments_json TEXT NOT NULL DEFAULT '[]',
                    structured_points_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    metric_id TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                    method TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(case_id, metric_id, version)
                );

                CREATE TABLE IF NOT EXISTS gaps (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    gap_key TEXT NOT NULL,
                    field TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    route TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    required_source_level TEXT,
                    owner TEXT,
                    due_at TEXT,
                    recompute_scope_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(case_id, gap_key),
                    CHECK (route IN ('interview', 'public_search', 'expert_review', 'document_request')),
                    CHECK (priority IN ('high', 'medium', 'low')),
                    CHECK (status IN ('open', 'resolved', 'waived'))
                );

                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    match_score REAL,
                    rationale_json TEXT NOT NULL DEFAULT '[]',
                    hard_filter_status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(case_id, category, item_id, version)
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    human_confirmation_json TEXT NOT NULL,
                    actor TEXT,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(case_id, version),
                    CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected')),
                    CHECK (recommendation IN ('进', '不进', '补充信息后再议'))
                );

                CREATE TABLE IF NOT EXISTS case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    actor TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )

    def _event(
        self,
        connection: sqlite3.Connection,
        case_id: str,
        event_type: str,
        payload: dict[str, Any],
        actor: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO case_events(case_id, event_type, actor, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, event_type, actor, json.dumps(payload, ensure_ascii=False), utc_now()),
        )

    def upsert_company(
        self,
        *,
        canonical_name: str,
        legal_name: str | None = None,
        jurisdiction: str | None = None,
        registry_id: str | None = None,
        aliases: list[str] | None = None,
        company_id: str | None = None,
    ) -> str:
        if not canonical_name.strip():
            raise ValueError("canonical_name is required")
        self.initialize()
        now = utc_now()
        with self.connect() as connection:
            by_name = connection.execute(
                "SELECT * FROM companies WHERE lower(canonical_name)=lower(?)",
                (canonical_name.strip(),),
            ).fetchone()
            by_registry = (
                connection.execute(
                    "SELECT * FROM companies WHERE registry_id=?",
                    (registry_id,),
                ).fetchone()
                if registry_id
                else None
            )
            if by_name and by_registry and by_name["id"] != by_registry["id"]:
                raise ValueError(
                    "Company identity conflict: canonical name and registry id resolve "
                    "to different master records"
                )
            existing = by_name or by_registry
            if existing:
                identifier = str(existing["id"])
                if (
                    registry_id
                    and existing["registry_id"]
                    and registry_id != existing["registry_id"]
                ):
                    raise ValueError(
                        "Company identity conflict: existing master has another registry id"
                    )
                if by_registry and str(existing["canonical_name"]).casefold() != (
                    canonical_name.strip().casefold()
                ):
                    raise ValueError(
                        "Company identity conflict: registry id is attached to another "
                        "canonical name; human confirmation is required"
                    )
                connection.execute(
                    """
                    UPDATE companies SET legal_name=?, jurisdiction=COALESCE(?, jurisdiction),
                        registry_id=COALESCE(?, registry_id),
                        aliases_json=?, updated_at=? WHERE id=?
                    """,
                    (
                        (legal_name or canonical_name).strip(),
                        jurisdiction,
                        registry_id,
                        json.dumps(aliases or [], ensure_ascii=False),
                        now,
                        identifier,
                    ),
                )
                return identifier
            identifier = company_id or str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO companies(
                    id, canonical_name, legal_name, jurisdiction, registry_id,
                    aliases_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    canonical_name.strip(),
                    (legal_name or canonical_name).strip(),
                    jurisdiction,
                    registry_id,
                    json.dumps(aliases or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            return identifier

    def create_case(
        self,
        *,
        company_id: str,
        stage: str,
        as_of: str,
        profile: dict[str, Any] | None = None,
        owner: str | None = None,
        external_id: str | None = None,
        source_case_path: str | None = None,
        case_id: str | None = None,
    ) -> str:
        if stage not in {
            "research_development",
            "pilot",
            "early_commercial",
            "scaling",
            "mature",
        }:
            raise ValueError("Unsupported company stage")
        try:
            date.fromisoformat(as_of)
        except ValueError as exc:
            raise ValueError("as_of must be an ISO date") from exc
        self.initialize()
        identifier = case_id or str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO cases(
                    id, company_id, external_id, stage, as_of, owner, status, version,
                    profile_json, source_case_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'intake', 1, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    company_id,
                    external_id,
                    stage,
                    as_of,
                    owner,
                    json.dumps(profile or {}, ensure_ascii=False),
                    source_case_path,
                    now,
                    now,
                ),
            )
            self._event(connection, identifier, "case_created", {"stage": stage}, owner)
        return identifier

    def add_evidence(self, case_id: str, evidence: dict[str, Any]) -> str:
        from .enterprise_evidence import normalize_evidence

        payload = dict(evidence)
        if payload.get("entity_id") in {None, "", "__CASE_ID__", "replace-with-case-id"}:
            payload["entity_id"] = case_id
        normalized = normalize_evidence(payload, default_entity_id=case_id)
        if normalized["entity_id"] != case_id:
            raise ValueError("Evidence entity_id must equal the owning case_id")
        identifier = str(normalized.get("id") or uuid.uuid4())
        evidence_key = str(normalized.get("evidence_key") or identifier)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence(
                    id, case_id, evidence_key, claim, source, locator, date, entity_id,
                    source_level, evidence_type, confidence, review_status, source_url,
                    sha256, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id, evidence_key) DO UPDATE SET
                    claim=excluded.claim, source=excluded.source, locator=excluded.locator,
                    date=excluded.date, entity_id=excluded.entity_id,
                    source_level=excluded.source_level, evidence_type=excluded.evidence_type,
                    confidence=excluded.confidence, review_status=excluded.review_status,
                    source_url=excluded.source_url, sha256=excluded.sha256,
                    metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
                """,
                (
                    identifier,
                    case_id,
                    evidence_key,
                    normalized["claim"],
                    normalized["source"],
                    normalized["locator"],
                    normalized.get("date"),
                    normalized["entity_id"],
                    normalized["source_level"],
                    normalized["type"],
                    normalized["confidence"],
                    normalized["review_status"],
                    normalized.get("source_url"),
                    normalized.get("sha256"),
                    json.dumps(normalized.get("metadata") or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            actual = connection.execute(
                "SELECT id FROM evidence WHERE case_id=? AND evidence_key=?",
                (case_id, evidence_key),
            ).fetchone()
            if not actual:
                raise RuntimeError("Evidence upsert did not produce a stored row")
            identifier = str(actual["id"])
            connection.execute(
                "UPDATE cases SET status='evidence_collection', updated_at=? WHERE id=?",
                (now, case_id),
            )
            self._event(
                connection,
                case_id,
                "evidence_upserted",
                {"evidence_id": identifier, "evidence_key": evidence_key},
            )
        return identifier

    def add_interview(
        self,
        case_id: str,
        *,
        transcript_path: str | Path,
        consent_ref: str,
        language: str | None = None,
        model: str = "base",
        audio_path: str | None = None,
        segments: list[dict[str, Any]] | None = None,
        structured_points: list[dict[str, Any]] | None = None,
        status: str = "transcribed",
    ) -> str:
        path = Path(transcript_path)
        if not path.is_file():
            raise ValueError(f"Transcript file does not exist: {path}")
        if not consent_ref.strip():
            raise ValueError("consent_ref is required for interview ingestion")
        identifier = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO interviews(
                    id, case_id, audio_path, transcript_path, transcript_sha256, language,
                    model, status, consent_ref, segments_json, structured_points_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    case_id,
                    audio_path,
                    str(path.resolve()),
                    sha256_file(path),
                    language,
                    model,
                    status,
                    consent_ref,
                    json.dumps(segments or [], ensure_ascii=False),
                    json.dumps(structured_points or [], ensure_ascii=False),
                    utc_now(),
                ),
            )
            self._event(
                connection,
                case_id,
                "interview_added",
                {"interview_id": identifier, "model": model},
            )
        return identifier

    def next_case_version(self, case_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT version FROM cases WHERE id=?", (case_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Unknown case: {case_id}")
            version = int(row["version"]) + 1
            connection.execute(
                "UPDATE cases SET version=?, updated_at=? WHERE id=?",
                (version, utc_now(), case_id),
            )
            return version

    def case_version(self, case_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT version FROM cases WHERE id=?", (case_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"Unknown case: {case_id}")
        return int(row["version"])

    def replace_assessment_outputs(
        self,
        case_id: str,
        *,
        version: int,
        metrics: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        recommendations: list[dict[str, Any]],
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE gaps SET status='resolved', updated_at=? "
                "WHERE case_id=? AND status='open'",
                (now, case_id),
            )
            for metric in metrics:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO metrics(
                        id, case_id, metric_id, dimension, value_json, status,
                        evidence_ids_json, method, version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        case_id,
                        metric["metric_id"],
                        metric["dimension"],
                        json.dumps(metric.get("value"), ensure_ascii=False),
                        metric["status"],
                        json.dumps(metric.get("evidence_ids") or [], ensure_ascii=False),
                        metric["method"],
                        version,
                        now,
                    ),
                )
            for gap in gaps:
                connection.execute(
                    """
                    INSERT INTO gaps(
                        id, case_id, gap_key, field, reason, route, priority, status,
                        required_source_level, owner, due_at, recompute_scope_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(case_id, gap_key) DO UPDATE SET
                        field=excluded.field, reason=excluded.reason, route=excluded.route,
                        priority=excluded.priority, status=excluded.status,
                        required_source_level=excluded.required_source_level,
                        owner=excluded.owner, due_at=excluded.due_at,
                        recompute_scope_json=excluded.recompute_scope_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        str(uuid.uuid4()),
                        case_id,
                        gap["gap_id"],
                        gap["missing"],
                        gap["reason"],
                        gap["route"],
                        gap["priority"],
                        gap.get("status", "open"),
                        gap.get("required_source_level"),
                        gap.get("owner"),
                        gap.get("due_at"),
                        json.dumps(gap.get("recompute_scope") or [], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            for item in recommendations:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO recommendations(
                        id, case_id, category, item_id, title, match_score, rationale_json,
                        hard_filter_status, version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        case_id,
                        item["category"],
                        item["item_id"],
                        item["title"],
                        item.get("match_score"),
                        json.dumps(item.get("rationale") or [], ensure_ascii=False),
                        item.get("hard_filter_status", "not_applicable"),
                        version,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE cases SET status='assessment_ready', updated_at=? WHERE id=?",
                (now, case_id),
            )
            self._event(
                connection,
                case_id,
                "assessment_outputs_written",
                {
                    "version": version,
                    "metric_count": len(metrics),
                    "gap_count": len(gaps),
                    "recommendation_count": len(recommendations),
                },
            )

    def create_draft_decision(
        self,
        case_id: str,
        *,
        recommendation: str,
        reasons: list[str],
        human_confirmation: list[str],
        actor: str | None = None,
        version: int | None = None,
    ) -> str:
        if recommendation not in {"进", "不进", "补充信息后再议"}:
            raise ValueError("Unsupported triage recommendation")
        version = version or self.case_version(case_id)
        identifier = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id, status FROM decisions WHERE case_id=? AND version=?",
                (case_id, version),
            ).fetchone()
            if existing and existing["status"] != "draft":
                raise ValueError("Only a draft decision can be replaced")
            if existing:
                identifier = str(existing["id"])
                connection.execute(
                    """
                    UPDATE decisions SET recommendation=?, reasons_json=?,
                        human_confirmation_json=?, actor=?, updated_at=? WHERE id=?
                    """,
                    (
                        recommendation,
                        json.dumps(reasons, ensure_ascii=False),
                        json.dumps(human_confirmation, ensure_ascii=False),
                        actor,
                        now,
                        identifier,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO decisions(
                        id, case_id, version, status, recommendation, reasons_json,
                        human_confirmation_json, actor, rejection_reason, created_at, updated_at
                    ) VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        identifier,
                        case_id,
                        version,
                        recommendation,
                        json.dumps(reasons, ensure_ascii=False),
                        json.dumps(human_confirmation, ensure_ascii=False),
                        actor,
                        now,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE cases SET status='draft', updated_at=? WHERE id=?",
                (now, case_id),
            )
            self._event(
                connection,
                case_id,
                "decision_drafted",
                {"decision_id": identifier, "version": version, "recommendation": recommendation},
                actor,
            )
        return identifier

    def transition_decision(
        self,
        case_id: str,
        target_status: str,
        *,
        actor: str,
        rejection_reason: str | None = None,
        eval_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        if target_status not in {"pending_review", "approved", "rejected"}:
            raise ValueError("Decision target must be pending_review, approved or rejected")
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM decisions WHERE case_id=?
                ORDER BY version DESC LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            if not row:
                raise ValueError("No draft decision exists for this case")
            current = str(row["status"])
            if target_status not in DECISION_TRANSITIONS[current]:
                raise ValueError(f"Invalid decision transition: {current} -> {target_status}")
            if target_status == "rejected" and not (rejection_reason or "").strip():
                raise ValueError("rejection_reason is required when rejecting a decision")
            connection.execute(
                """
                UPDATE decisions SET status=?, actor=?, rejection_reason=?, updated_at=?
                WHERE id=?
                """,
                (target_status, actor, rejection_reason, now, row["id"]),
            )
            connection.execute(
                "UPDATE cases SET status=?, updated_at=? WHERE id=?",
                (target_status, now, case_id),
            )
            self._event(
                connection,
                case_id,
                f"decision_{target_status}",
                {
                    "decision_id": row["id"],
                    "from": current,
                    "to": target_status,
                    "reason": rejection_reason,
                },
                actor,
            )
        snapshot_path = None
        if target_status == "rejected":
            snapshot_path = self.export_evaluation_snapshot(
                case_id, eval_dir or self.path.parent / "eval_cases"
            )
        return {
            "case_id": case_id,
            "decision_id": str(row["id"]),
            "from": current,
            "to": target_status,
            "rejection_reason": rejection_reason,
            "evaluation_snapshot": str(snapshot_path) if snapshot_path else None,
        }

    def get_case_bundle(self, case_id: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection:
            case = connection.execute(
                """
                SELECT cases.*, companies.canonical_name, companies.legal_name,
                    companies.jurisdiction, companies.registry_id, companies.aliases_json
                FROM cases JOIN companies ON companies.id=cases.company_id
                WHERE cases.id=?
                """,
                (case_id,),
            ).fetchone()
            if not case:
                raise ValueError(f"Unknown case: {case_id}")
            bundle: dict[str, Any] = {"case": self._row("cases", case)}
            for table in (
                "evidence",
                "interviews",
                "metrics",
                "gaps",
                "recommendations",
                "decisions",
                "case_events",
            ):
                order = "created_at, id" if table != "case_events" else "created_at, id"
                rows = connection.execute(
                    f"SELECT * FROM {table} WHERE case_id=? ORDER BY {order}",  # noqa: S608
                    (case_id,),
                ).fetchall()
                bundle[table] = [self._row(table, row) for row in rows]
        return bundle

    def _row(self, table: str, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for column in JSON_COLUMNS.get(table, set()):
            if column in value:
                value[column.removesuffix("_json")] = json.loads(value.pop(column) or "null")
        if table == "cases":
            value["company"] = {
                "id": value.pop("company_id"),
                "canonical_name": value.pop("canonical_name"),
                "legal_name": value.pop("legal_name"),
                "jurisdiction": value.pop("jurisdiction"),
                "registry_id": value.pop("registry_id"),
                "aliases": json.loads(value.pop("aliases_json") or "[]"),
            }
        if table == "evidence":
            value["type"] = value.pop("evidence_type")
        return value

    def export_evaluation_snapshot(self, case_id: str, eval_dir: str | Path) -> Path:
        target = Path(eval_dir)
        target.mkdir(parents=True, exist_ok=True)
        bundle = self.get_case_bundle(case_id)
        latest = bundle["decisions"][-1]
        if latest["status"] != "rejected":
            raise ValueError("Only rejected decisions can be exported as evaluation cases")
        path = target / f"{case_id}-v{latest['version']}-rejected.json"
        if path.exists():
            current = json.loads(path.read_text(encoding="utf-8"))
            if current != bundle:
                raise FileExistsError(f"Refusing to overwrite a different snapshot: {path}")
            return path
        path.write_text(
            json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
