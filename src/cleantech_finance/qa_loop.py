"""Failure-driven five-company loop for human-supplied QA cases."""

from __future__ import annotations

import ast
import html
import json
import math
import os
import re
import tempfile
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from scripts.evaluate_audit import evaluate as evaluate_financial_audit
from scripts.evaluate_cards import evaluate_cards as evaluate_financial_cards

from .audit import run_audit
from .qa_diagnostics import (
    PROFILE_FIELDS,
    PROFILE_LABELS,
    QA_RULE_DIGEST,
    QA_RULE_VERSION,
    validate_qa_case,
)
from .qa_reporting import write_qa_artifacts
from .reporting import write_artifacts

VALIDATED_FINANCE_DIMENSIONS = {
    "profitability-unit-economics",
    "cash-runway",
}

REQUIRED_FINANCIAL_FACTS = {
    "revenue",
    "operating_cost",
    "operating_cash_flow",
    "capex",
    "cash_and_equivalents",
}
REQUIRED_FINANCIAL_METRICS = {
    "revenue-growth",
    "gross-margin",
    "free-cash-flow",
    "capex-to-revenue",
}
FINANCIAL_SIGNALS = {"red", "amber", "green", None}
MIN_EXTRACTION_CHECKS = 28
MIN_CARD_CHECKS = 27
HISTORY_FILENAME = "qa-loop-history.json"
HISTORY_SCHEMA_VERSION = "2.0.0"
LOCK_FILENAME = ".qa-loop.lock"


class _RuntimeSnapshotIntegrityError(ValueError):
    """Raised when the private volatile input snapshot no longer matches its digest."""


@dataclass
class _RuntimeInputSnapshot:
    """Volatile, content-addressed copies of every user-supplied runtime input."""

    temporary_directory: tempfile.TemporaryDirectory
    registry: dict[str, Any]
    registry_path: Path
    registry_sha256: str
    registry_size: int
    manifest_rows: list[dict[str, Any]]
    files: dict[str, Path]
    origins: dict[str, Path]
    origin_paths: set[Path]
    input_hashes: dict[str, str]
    source_files: dict[str, list[Path | None]]
    source_hashes: dict[str, list[str | None]]
    runtime_manifests: dict[str, Path]
    runtime_manifest_payloads: dict[str, bytes]
    protected_files: dict[Path, str]
    cleaned: bool = False

    @property
    def root(self) -> Path:
        return Path(self.temporary_directory.name).resolve()

    def cleanup(self) -> None:
        if not self.cleaned:
            self.temporary_directory.cleanup()
            self.cleaned = True


QA_GAP_QUESTION_RECOMMENDATIONS = {
    "product_technology": {
        "question_id": "product-core",
        "text": "Ask what the customer actually buys and require one exact product statement.",
        "text_zh": "补问客户实际购买什么，并保留一条精确的产品原话。",
    },
    "subindustry": {
        "question_id": "product-core",
        "text": "Ask for the narrowest applicable subindustry and the product/use-case basis.",
        "text_zh": "补问最窄的适用子行业，并保留产品与使用场景依据。",
    },
    "target_markets": {
        "question_id": "market-core",
        "text": "Separate desired markets from evidence-backed targets and cite the basis.",
        "text_zh": "区分想去的市场与有依据的目标市场，并引用选择依据。",
    },
    "export_stage": {
        "question_id": "export-stage",
        "text": "Ask for completed export actions, not aspirations, before assigning a stage.",
        "text_zh": "按已完成的出海动作补问，不以愿望或计划代替阶段证据。",
    },
    "core_gaps": {
        "question_id": "gap-core",
        "text": "Ask for one concrete blocker and the evidence needed to resolve it.",
        "text_zh": "补问一个具体阻碍，以及消除该不确定性所需的证据。",
    },
    "resource_needs": {
        "question_id": "resource-core",
        "text": "Tie each requested resource to a milestone and timing.",
        "text_zh": "把每项资源需求绑定到具体里程碑与时间。",
    },
}


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _object_from_bytes(raw: bytes, path: Path) -> dict[str, Any]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _load_object_exact(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    actual_sha256 = sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Input changed after the execution snapshot: {path} "
            f"({actual_sha256} != {expected_sha256})"
        )
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _resolve_snapshot_input_path(value: str, base: Path) -> Path:
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else base / candidate
    absolute = candidate.absolute()
    raw_path = str(absolute)
    if raw_path.startswith(("\\\\", "//")):
        raise ValueError("Runtime input snapshots reject UNC and device paths")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and (current.is_symlink() or _is_reparse_point(current)):
            raise ValueError(f"Runtime input path may not traverse a reparse point: {current}")
    if os.name == "nt" and absolute.anchor:
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(Path(absolute.anchor)))
        if drive_type == 4:
            raise ValueError("Runtime input snapshots reject mapped remote drives")
    return absolute.resolve()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_runtime_input_snapshot(
    registry_path: str | Path,
    *,
    project_root: Path,
    output_dir: Path,
) -> _RuntimeInputSnapshot:
    """Capture the complete input graph once and execute only those exact bytes.

    The snapshot lives in the current user's OS temporary directory, outside the
    repository and run artifact tree. It is removed in ``run_qa_registry``'s
    ``finally`` block and only hashes/sizes are retained in history.
    """

    registry_origin = _resolve_snapshot_input_path(str(registry_path), Path.cwd())
    volatile_parent = Path(tempfile.gettempdir()).resolve()
    for forbidden_root, label in (
        (project_root.resolve(), "project"),
        (output_dir.resolve(), "output"),
    ):
        try:
            volatile_parent.relative_to(forbidden_root)
        except ValueError:
            continue
        raise ValueError(
            f"The OS temporary directory is inside the QA {label} tree; "
            "refusing to snapshot private inputs there"
        )
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="cleantech-qa-runtime-inputs-",
        dir=volatile_parent,
    )
    snapshot_root = Path(temporary_directory.name).resolve()
    os.chmod(snapshot_root, 0o700)
    blob_root = snapshot_root / "blobs"
    derived_manifest_root = snapshot_root / "derived-manifests"
    blob_root.mkdir(parents=True, exist_ok=False)
    derived_manifest_root.mkdir(parents=True, exist_ok=False)

    manifest_rows: list[dict[str, Any]] = []
    files: dict[str, Path] = {}
    origins: dict[str, Path] = {}
    origin_paths: set[Path] = set()
    input_hashes: dict[str, str] = {}
    source_files: dict[str, list[Path | None]] = {}
    source_hashes: dict[str, list[str | None]] = {}
    runtime_manifests: dict[str, Path] = {}
    runtime_manifest_payloads: dict[str, bytes] = {}
    protected_files: dict[Path, str] = {}

    def capture(
        label: str,
        origin: Path,
        *,
        raw: bytes | None = None,
        indexed: bool = True,
    ) -> tuple[Path | None, bytes | None, str | None]:
        resolved = origin.resolve()
        if raw is None:
            if not resolved.is_file():
                manifest_rows.append(
                    {"label": label, "exists": False, "sha256": None, "size": None}
                )
                return None, None, None
            raw = resolved.read_bytes()
        digest = sha256(raw).hexdigest()
        origin_paths.add(resolved)
        suffix = resolved.suffix.lower()
        blob_path = blob_root / f"{digest}{suffix}"
        if blob_path.exists():
            if blob_path.read_bytes() != raw:
                raise ValueError("Runtime input snapshot digest collision")
        else:
            blob_path.write_bytes(raw)
        protected_files[blob_path] = digest
        manifest_rows.append(
            {
                "label": label,
                "exists": True,
                "sha256": digest,
                "size": len(raw),
            }
        )
        if indexed:
            if label in files:
                raise ValueError(f"Duplicate runtime input label: {label}")
            files[label] = blob_path
            origins[label] = resolved
            input_hashes[label] = digest
        return blob_path, raw, digest

    try:
        registry_raw = registry_origin.read_bytes()
        registry = _object_from_bytes(registry_raw, registry_origin)
        _, _, registry_sha256 = capture(
            "registry",
            registry_origin,
            raw=registry_raw,
        )
        assert registry_sha256 is not None
        registry_schema_errors = _schema_errors(
            registry,
            project_root / "schemas" / "qa-loop.schema.json",
        )
        if registry_schema_errors:
            raise ValueError("Invalid QA registry: " + "; ".join(registry_schema_errors))
        _validate_registry(registry)

        for row in registry["cases"]:
            case_id = str(row["id"])
            case_origin = _resolve_snapshot_input_path(row["input"], registry_origin.parent)
            case_snapshot, case_raw, _ = capture(f"case:{case_id}", case_origin)

            review_value = row.get("profile_ground_truth")
            if isinstance(review_value, str) and review_value:
                capture(
                    f"profile_ground_truth:{case_id}",
                    _resolve_snapshot_input_path(review_value, registry_origin.parent),
                )

            if case_snapshot is None or case_raw is None:
                continue
            try:
                case = _object_from_bytes(case_raw, case_origin)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                continue
            if _schema_errors(case, project_root / "schemas" / "qa-case.schema.json"):
                continue
            financial = case.get("financial_evidence")
            if (
                not isinstance(financial, dict)
                or financial.get("annual_report_status") != "available"
            ):
                continue

            financial_raw: dict[str, bytes | None] = {}
            financial_origins: dict[str, Path] = {}
            for key in ("manifest", "ground_truth", "card_ground_truth"):
                value = financial.get(key)
                if not isinstance(value, str) or not value:
                    continue
                origin = _resolve_snapshot_input_path(value, case_origin.parent)
                financial_origins[key] = origin
                _, raw, _ = capture(f"financial:{case_id}:{key}", origin)
                financial_raw[key] = raw

            manifest_raw = financial_raw.get("manifest")
            manifest_origin = financial_origins.get("manifest")
            if manifest_raw is None or manifest_origin is None:
                continue
            try:
                manifest_payload = _object_from_bytes(manifest_raw, manifest_origin)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                continue
            if _schema_errors(
                manifest_payload,
                project_root / "schemas" / "manifest.schema.json",
            ):
                continue

            case_source_files: list[Path | None] = []
            case_source_hashes: list[str | None] = []
            rewritten_manifest = deepcopy(manifest_payload)
            all_sources_captured = True
            seen_source_ids: set[str] = set()
            seen_source_origins: set[Path] = set()
            seen_source_file_ids: set[tuple[int, int]] = set()
            for index, source in enumerate(manifest_payload.get("sources", [])):
                source_id = str(source.get("id", ""))
                if source_id in seen_source_ids:
                    raise ValueError(f"Duplicate manifest source id in {case_id}: {source_id}")
                seen_source_ids.add(source_id)
                source_value = source.get("path")
                source_snapshot: Path | None = None
                source_digest: str | None = None
                if isinstance(source_value, str) and source_value:
                    source_origin = _resolve_snapshot_input_path(
                        source_value,
                        manifest_origin.parent,
                    )
                    if source_origin in seen_source_origins:
                        raise ValueError(
                            f"Multiple manifest source ids resolve to the same file in {case_id}"
                        )
                    seen_source_origins.add(source_origin)
                    if source_origin.is_file():
                        source_stat = source_origin.stat()
                        source_file_id = (source_stat.st_dev, source_stat.st_ino)
                        if source_file_id in seen_source_file_ids:
                            raise ValueError(
                                f"Multiple manifest source ids resolve to one physical file in {case_id}"
                            )
                        seen_source_file_ids.add(source_file_id)
                    source_snapshot, _, source_digest = capture(
                        f"financial:{case_id}:source:{source_id}",
                        source_origin,
                        indexed=False,
                    )
                if source_snapshot is None:
                    all_sources_captured = False
                else:
                    rewritten_manifest["sources"][index]["path"] = str(source_snapshot)
                case_source_files.append(source_snapshot)
                case_source_hashes.append(source_digest)
            source_files[case_id] = case_source_files
            source_hashes[case_id] = case_source_hashes
            if not all_sources_captured:
                continue

            runtime_manifest_path = derived_manifest_root / f"{case_id}.json"
            runtime_manifest_payload = (
                json.dumps(rewritten_manifest, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            runtime_manifest_path.write_bytes(runtime_manifest_payload)
            protected_files[runtime_manifest_path] = _file_sha256(runtime_manifest_path)
            runtime_manifests[case_id] = runtime_manifest_path
            runtime_manifest_payloads[case_id] = runtime_manifest_payload

        snapshot = _RuntimeInputSnapshot(
            temporary_directory=temporary_directory,
            registry=registry,
            registry_path=registry_origin,
            registry_sha256=registry_sha256,
            registry_size=len(registry_raw),
            manifest_rows=sorted(manifest_rows, key=lambda item: item["label"]),
            files=files,
            origins=origins,
            origin_paths=origin_paths,
            input_hashes=input_hashes,
            source_files=source_files,
            source_hashes=source_hashes,
            runtime_manifests=runtime_manifests,
            runtime_manifest_payloads=runtime_manifest_payloads,
            protected_files=protected_files,
        )
        _verify_runtime_input_snapshot(snapshot)
        return snapshot
    except Exception:
        temporary_directory.cleanup()
        raise


def _verify_runtime_input_snapshot(snapshot: _RuntimeInputSnapshot) -> None:
    for path, expected_sha256 in snapshot.protected_files.items():
        try:
            path.resolve().relative_to(snapshot.root)
        except ValueError as exc:
            raise _RuntimeSnapshotIntegrityError(
                "Volatile runtime input snapshot path escaped its private root"
            ) from exc
        invalid = (
            not path.is_file()
            or path.is_symlink()
            or _is_reparse_point(path)
            or path.stat().st_nlink != 1
            or _file_sha256(path) != expected_sha256
        )
        if invalid:
            raise _RuntimeSnapshotIntegrityError(
                "Volatile runtime input snapshot changed after capture; "
                "no history entry was committed"
            )


def _reject_runtime_snapshot_path_leaks(
    artifact_root: Path,
    snapshot: _RuntimeInputSnapshot,
) -> None:
    needles = {str(snapshot.root), snapshot.root.as_posix()}
    for origin in snapshot.origin_paths:
        needles.update((str(origin), origin.as_posix()))
    for path in artifact_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            payload = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(needle and needle in payload for needle in needles):
            raise ValueError(
                f"Volatile runtime snapshot path leaked into a retained artifact: {path}"
            )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _is_reparse_point(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _require_contained_directory(path: Path, parent: Path) -> Path:
    if _is_reparse_point(path):
        raise ValueError(f"QA loop directories may not be symlinks or junctions: {path}")
    resolved_parent = parent.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_parent)
    except ValueError as exc:
        raise ValueError(f"QA loop directory escapes its expected root: {path}") from exc
    if not resolved.is_dir():
        raise ValueError(f"QA loop directory is missing: {path}")
    return resolved


def _artifact_tree_manifest(root: Path) -> list[dict[str, Any]]:
    if _is_reparse_point(root):
        raise ValueError(f"Run artifact root may not be a junction: {root}")
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Run artifact root must be a real local directory: {root}")
    rows: list[dict[str, Any]] = []
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        _require_contained_directory(current_path, root)
        for name in list(directory_names):
            child = current_path / name
            if _is_reparse_point(child):
                raise ValueError(f"Run artifact tree may not contain junctions: {child}")
            _require_contained_directory(child, root)
        for name in file_names:
            path = current_path / name
            if _is_reparse_point(path):
                raise ValueError(f"Run artifact tree may not contain links: {path}")
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Run artifact escapes its run directory: {path}") from exc
            if not resolved.is_file():
                raise ValueError(f"Run artifact is not a regular file: {path}")
            rows.append(
                {
                    "path": relative.as_posix(),
                    "sha256": _file_sha256(resolved),
                    "size": resolved.stat().st_size,
                }
            )
    rows.sort(key=lambda item: item["path"])
    return rows


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{stamp}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _qa_rule_bundle_paths(project_root: Path) -> tuple[Path, ...]:
    return tuple(sorted((project_root / "src" / "cleantech_finance").glob("*.py"))) + (
        project_root / "scripts" / "evaluate_audit.py",
        project_root / "scripts" / "evaluate_cards.py",
        project_root / "schemas" / "qa-case.schema.json",
        project_root / "schemas" / "qa-loop.schema.json",
        project_root / "schemas" / "qa-profile-ground-truth.schema.json",
        project_root / "schemas" / "financial-ground-truth.schema.json",
        project_root / "schemas" / "card-ground-truth.schema.json",
        project_root / "schemas" / "manifest.schema.json",
    )


def _qa_rule_bundle_digest(project_root: Path) -> str:
    """Bind history to every deterministic QA rule and contract file."""
    paths = _qa_rule_bundle_paths(project_root)
    return _canonical_sha256(
        [
            {"path": path.relative_to(project_root).as_posix(), "sha256": _file_sha256(path)}
            for path in paths
        ]
    )


IMPORTED_QA_RULE_BUNDLE_DIGEST = _qa_rule_bundle_digest(Path(__file__).resolve().parents[2])


def _load_history(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": HISTORY_SCHEMA_VERSION, "runs": []}
    history = _load_object(path)
    if history.get("schema_version") != HISTORY_SCHEMA_VERSION or not isinstance(
        history.get("runs"), list
    ):
        raise ValueError("Invalid QA loop history structure")
    output_root = path.parent.resolve()
    previous_hash: str | None = None
    for number, entry in enumerate(history["runs"], start=1):
        if not isinstance(entry, dict):
            raise ValueError("Invalid QA loop history entry")
        if entry.get("run_number") != number:
            raise ValueError("QA loop history run numbers are not contiguous")
        if entry.get("previous_run_hash") != previous_hash:
            raise ValueError("QA loop history hash chain is broken")
        claimed = entry.get("run_hash")
        unsigned = {key: value for key, value in entry.items() if key != "run_hash"}
        if claimed != _canonical_sha256(unsigned):
            raise ValueError("QA loop history entry hash is invalid")
        run_output = entry.get("run_output")
        if not isinstance(run_output, str) or not run_output:
            raise ValueError("QA loop history run_output is missing")
        relative = Path(run_output)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("QA loop history run_output must be a safe relative path")
        run_root = (output_root / relative).resolve()
        try:
            run_root.relative_to(output_root)
        except ValueError as exc:
            raise ValueError("QA loop history run_output escapes its output directory") from exc
        if not run_root.is_dir():
            raise ValueError(f"QA loop history artifact directory is missing: {run_output}")
        if _is_reparse_point(output_root / relative):
            raise ValueError(f"QA loop history run_output may not be a junction: {run_output}")
        actual_manifest = _artifact_tree_manifest(run_root)
        if entry.get("artifact_manifest") != actual_manifest:
            raise ValueError(f"QA loop artifact manifest is invalid: {run_output}")
        if entry.get("artifact_tree_sha256") != _canonical_sha256(actual_manifest):
            raise ValueError(f"QA loop artifact tree digest is invalid: {run_output}")
        previous_hash = claimed
    return history


def _append_history(path: Path, history: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(history)
    runs = updated["runs"]
    unsigned = {
        **entry,
        "run_number": len(runs) + 1,
        "previous_run_hash": runs[-1]["run_hash"] if runs else None,
    }
    signed = {**unsigned, "run_hash": _canonical_sha256(unsigned)}
    runs.append(signed)
    _atomic_write_json(path, updated)
    history.clear()
    history.update(updated)
    return signed


def _reconcile_run_storage(output_dir: Path, history: dict[str, Any]) -> list[str]:
    """Quarantine uncommitted staging/final directories without deleting evidence."""
    runs_root = output_dir / "runs"
    staging_root = runs_root / ".staging"
    orphan_root = runs_root / "_orphaned"
    runs_root.mkdir(parents=True, exist_ok=True)
    _require_contained_directory(runs_root, output_dir)
    staging_root.mkdir(parents=True, exist_ok=True)
    _require_contained_directory(staging_root, runs_root)
    known = {(output_dir / str(run["run_output"])).resolve() for run in history.get("runs", [])}
    candidates: list[Path] = []
    for item in staging_root.iterdir():
        if _is_reparse_point(item):
            raise ValueError(f"Uncommitted run may not be a junction: {item}")
        if item.is_dir():
            _require_contained_directory(item, staging_root)
            candidates.append(item)
    for item in runs_root.iterdir():
        if item.name in {".staging", "_orphaned"}:
            continue
        if _is_reparse_point(item):
            raise ValueError(f"Run storage may not contain a junction: {item}")
        if item.is_dir() and item.resolve() not in known:
            _require_contained_directory(item, runs_root)
            candidates.append(item)
    quarantined: list[str] = []
    for candidate in candidates:
        orphan_root.mkdir(parents=True, exist_ok=True)
        _require_contained_directory(orphan_root, runs_root)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = orphan_root / f"{candidate.name}-{stamp}"
        if target.exists() or _is_reparse_point(target):
            raise ValueError(f"Unsafe orphan quarantine target: {target}")
        candidate.replace(target)
        quarantined.append(target.relative_to(output_dir).as_posix())
    return quarantined


def _replace_path_prefix(value: Any, old_root: Path, new_root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _replace_path_prefix(item, old_root, new_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_path_prefix(item, old_root, new_root) for item in value]
    if isinstance(value, str):
        try:
            path = Path(value)
            relative = path.resolve().relative_to(old_root.resolve())
        except (OSError, ValueError):
            return value
        return str((new_root / relative).resolve())
    return value


def _history_case_rows(history: dict[str, Any], case_id: str) -> list[dict[str, Any]]:
    return [
        row for run in history["runs"] for row in run.get("cases", []) if row.get("id") == case_id
    ]


def _build_regression_evidence(
    history: dict[str, Any],
    current_cases: list[dict[str, Any]],
    *,
    rules_changed: bool,
    current_rule_digest: str,
) -> dict[str, Any]:
    """Describe observed replay coverage for the latest prior pass of each case."""

    latest_prior_passes: dict[str, dict[str, Any]] = {}
    for run in history.get("runs", []):
        for row in run.get("cases", []):
            if row.get("execution_passed") is not True or not row.get("id"):
                continue
            latest_prior_passes[str(row["id"])] = {
                "case_id": str(row["id"]),
                "iteration": row.get("iteration"),
                "run_number": run.get("run_number"),
                "rule_digest": run.get("rule_digest"),
                "input_bundle_sha256": row.get("input_bundle_sha256"),
            }

    pending_evidence: dict[str, Any] | None = None
    if not rules_changed:
        for run in reversed(history.get("runs", [])):
            if run.get("rule_digest") != current_rule_digest:
                break
            candidate = run.get("regression_evidence")
            if not isinstance(candidate, dict) or candidate.get("required") is not True:
                continue
            if candidate.get("complete") is True:
                break
            pending_evidence = candidate
            break
    regression_required = bool(rules_changed or pending_evidence)
    baseline_source = (
        pending_evidence.get("baseline_cases", [])
        if pending_evidence is not None
        else latest_prior_passes.values()
    )
    baseline_cases = sorted(
        (dict(item) for item in baseline_source if isinstance(item, dict)),
        key=lambda item: (
            item["iteration"] if isinstance(item.get("iteration"), int) else 10**9,
            str(item.get("case_id", "")),
        ),
    )
    required_case_ids = [item["case_id"] for item in baseline_cases]
    current_by_id = {str(row["id"]): row for row in current_cases}
    executed_case_ids = [case_id for case_id in required_case_ids if case_id in current_by_id]
    passed_case_ids = [
        case_id
        for case_id in executed_case_ids
        if current_by_id[case_id].get("execution_passed") is True
    ]
    failed_case_ids = [
        case_id
        for case_id in executed_case_ids
        if current_by_id[case_id].get("execution_passed") is not True
    ]
    missing_case_ids = [
        case_id for case_id in required_case_ids if case_id not in current_by_id
    ]
    input_changed_case_ids: list[str] = []
    input_unverifiable_case_ids: list[str] = []
    for baseline in baseline_cases:
        case_id = baseline["case_id"]
        current = current_by_id.get(case_id)
        if current is None:
            continue
        baseline_hash = baseline.get("input_bundle_sha256")
        current_hash = current.get("input_bundle_sha256")
        if not isinstance(baseline_hash, str) or not isinstance(current_hash, str):
            input_unverifiable_case_ids.append(case_id)
        elif baseline_hash != current_hash:
            input_changed_case_ids.append(case_id)

    complete = bool(
        regression_required
        and required_case_ids
        and not failed_case_ids
        and not missing_case_ids
        and not input_changed_case_ids
        and not input_unverifiable_case_ids
        and passed_case_ids == required_case_ids
    )
    if not regression_required:
        status = (
            "not_required_initial_run"
            if not history.get("runs")
            else "not_required_rules_unchanged"
        )
    elif not required_case_ids:
        status = "not_established_no_prior_passes"
    elif failed_case_ids or missing_case_ids:
        status = "incomplete_failed_or_missing"
    elif input_changed_case_ids or input_unverifiable_case_ids:
        status = "incomplete_input_not_comparable"
    else:
        status = "complete"

    return {
        "scope": "latest_prior_execution_pass_per_case",
        "required": regression_required,
        "complete": complete,
        "status": status,
        "from_rule_digests": sorted(
            {
                str(item["rule_digest"])
                for item in baseline_cases
                if item.get("rule_digest")
            }
        ),
        "to_rule_digest": current_rule_digest,
        "baseline_cases": baseline_cases,
        "required_case_ids": required_case_ids,
        "executed_case_ids": executed_case_ids,
        "passed_case_ids": passed_case_ids,
        "failed_case_ids": failed_case_ids,
        "missing_case_ids": missing_case_ids,
        "input_changed_case_ids": input_changed_case_ids,
        "input_unverifiable_case_ids": input_unverifiable_case_ids,
    }


def _schema_errors(payload: dict[str, Any], schema_path: Path) -> list[str]:
    schema = _load_object(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(payload), key=lambda item: list(item.absolute_path)
        )
    ]


def _selection_material(registry: dict[str, Any], registry_path: Path) -> list[dict[str, Any]]:
    material: list[dict[str, Any]] = []
    for row in registry["cases"]:
        case_path = _resolve_path(row["input"], registry_path.parent)
        if not case_path.is_file():
            raise ValueError(f"QA case input does not exist: {case_path}")
        actual_input_hash = _file_sha256(case_path)
        expected_input_hash = row.get("input_sha256")
        if expected_input_hash is not None and expected_input_hash != actual_input_hash:
            raise ValueError(
                f"QA case input hash mismatch for {row['id']}: "
                f"expected {expected_input_hash}, got {actual_input_hash}"
            )
        review_hash = row.get("profile_ground_truth_sha256")
        review_value = row.get("profile_ground_truth")
        if review_value is not None:
            review_path = _resolve_path(review_value, registry_path.parent)
            if not review_path.is_file():
                raise ValueError(f"Profile ground truth does not exist: {review_path}")
            actual_review_hash = _file_sha256(review_path)
            if review_hash != actual_review_hash:
                raise ValueError(
                    f"Profile ground-truth hash mismatch for {row['id']}: "
                    f"expected {review_hash}, got {actual_review_hash}"
                )
        material.append(
            {
                "iteration": row["iteration"],
                "id": row["id"],
                "entity_scheme": row["entity_scheme"],
                "entity_id": row["entity_id"],
                "company": row["company"],
                "input_sha256": actual_input_hash,
                "profile_ground_truth_sha256": review_hash,
            }
        )
    return material


def selection_material_report(
    registry: dict[str, Any],
    registry_path: str | Path,
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    """Inspect the five selection inputs without creating a human attestation.

    This is the operator bootstrap for ``qa_delivery``. It reports the actual
    case/profile-review hashes and the aggregate digest that a human can review,
    while deliberately leaving the attestation unconfirmed and the registry
    unchanged.
    """

    path = Path(registry_path).resolve()
    root = Path(project_root).resolve()
    _validate_registry(registry)
    issues: list[dict[str, str]] = []
    material: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    def issue(code: str, case_id: str, message: str) -> None:
        issues.append({"code": code, "case_id": case_id, "message": message})

    for row in registry["cases"]:
        case_id = str(row["id"])
        actual_case_hash: str | None = None
        actual_review_hash: str | None = None
        case_payload: dict[str, Any] | None = None
        try:
            case_path = _resolve_snapshot_input_path(str(row["input"]), path.parent)
            case_raw = case_path.read_bytes()
            actual_case_hash = sha256(case_raw).hexdigest()
            case_payload = _object_from_bytes(case_raw, case_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            issue("case_input_unreadable", case_id, str(exc))
        if case_payload is not None:
            for message in _schema_errors(
                case_payload,
                root / "schemas" / "qa-case.schema.json",
            ):
                issue("case_schema", case_id, message)
            company = (
                case_payload.get("company")
                if isinstance(case_payload.get("company"), dict)
                else {}
            )
            stable = (
                company.get("stable_identifier")
                if isinstance(company.get("stable_identifier"), dict)
                else {}
            )
            case_block = (
                case_payload.get("case")
                if isinstance(case_payload.get("case"), dict)
                else {}
            )
            expected_identity = (
                str(row["entity_scheme"]),
                str(row["entity_id"]),
                str(row["company"]).strip(),
                case_id,
            )
            actual_identity = (
                str(stable.get("scheme", "")),
                str(stable.get("value", "")),
                str(company.get("legal_name", "")).strip(),
                str(case_block.get("id", "")),
            )
            if actual_identity != expected_identity:
                issue(
                    "case_registry_identity_mismatch",
                    case_id,
                    "QA case id and full legal-entity identity must exactly match the registry.",
                )

        review_value = row.get("profile_ground_truth")
        review_payload: dict[str, Any] | None = None
        if isinstance(review_value, str) and review_value:
            try:
                review_path = _resolve_snapshot_input_path(review_value, path.parent)
                review_raw = review_path.read_bytes()
                actual_review_hash = sha256(review_raw).hexdigest()
                review_payload = _object_from_bytes(review_raw, review_path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                issue("profile_ground_truth_unreadable", case_id, str(exc))
        elif registry.get("run_mode") == "qa_delivery":
            issue(
                "profile_ground_truth_missing",
                case_id,
                "qa_delivery needs one independently human-reviewed profile ground truth.",
            )
        if review_payload is not None:
            for message in _schema_errors(
                review_payload,
                root / "schemas" / "qa-profile-ground-truth.schema.json",
            ):
                issue("profile_ground_truth_schema", case_id, message)
            expected_review_entity = {
                "scheme": row["entity_scheme"],
                "value": row["entity_id"],
                "legal_name": row["company"],
            }
            if (
                review_payload.get("case_id") != case_id
                or review_payload.get("entity") != expected_review_entity
            ):
                issue(
                    "profile_ground_truth_identity_mismatch",
                    case_id,
                    "Profile ground truth must bind the registry case id and full entity identity.",
                )

        declared_case_hash = row.get("input_sha256")
        declared_review_hash = row.get("profile_ground_truth_sha256")
        case_hash_matches = bool(
            actual_case_hash is not None and declared_case_hash == actual_case_hash
        )
        review_hash_matches = bool(
            (review_value is None and declared_review_hash is None)
            or (
                actual_review_hash is not None
                and declared_review_hash == actual_review_hash
            )
        )
        if not case_hash_matches:
            issue(
                "case_hash_update_required",
                case_id,
                "Copy the reported actual input_sha256 into the registry, then rerun this command.",
            )
        if not review_hash_matches:
            issue(
                "profile_ground_truth_hash_update_required",
                case_id,
                "Copy the reported actual profile_ground_truth_sha256 into the registry, then rerun this command.",
            )
        material_row = {
            "iteration": row["iteration"],
            "id": row["id"],
            "entity_scheme": row["entity_scheme"],
            "entity_id": row["entity_id"],
            "company": row["company"],
            "input_sha256": actual_case_hash,
            "profile_ground_truth_sha256": actual_review_hash,
        }
        material.append(material_row)
        cases.append(
            {
                **material_row,
                "declared_input_sha256": declared_case_hash,
                "declared_profile_ground_truth_sha256": declared_review_hash,
                "declared_hashes_match": case_hash_matches and review_hash_matches,
            }
        )

    complete_material = bool(
        len(material) == 5
        and all(item["input_sha256"] for item in material)
        and (
            registry.get("run_mode") != "qa_delivery"
            or all(item["profile_ground_truth_sha256"] for item in material)
        )
    )
    case_set_sha256 = _canonical_sha256(material) if complete_material else None
    if registry.get("run_mode") != "qa_delivery":
        issue(
            "run_mode_not_delivery",
            "",
            "Only qa_delivery inputs can become a countable five-company delivery.",
        )
    ready = bool(case_set_sha256 and not issues)
    return {
        "schema_version": "1.0.0",
        "mode": "selection_material_preview",
        "ready_for_human_attestation": ready,
        "creates_human_attestation": False,
        "case_set_sha256": case_set_sha256,
        "cases": cases,
        "issues": issues,
        "unconfirmed_attestation_template": (
            {
                "actor_type": "human",
                "confirmed_by": "REPLACE_WITH_HUMAN_REVIEWER",
                "confirmed_at": "REPLACE_WITH_RFC3339_DATE_TIME",
                "selection_batch_id": "REPLACE_WITH_NEW_BATCH_ID",
                "case_set_sha256": case_set_sha256,
                "statement": (
                    "I selected these five companies and supplied their case inputs; "
                    "the Evidence Agent did not discover or choose them."
                ),
            }
            if case_set_sha256
            else None
        ),
        "warning": (
            "This report computes hashes only. It does not prove a person's identity, "
            "select companies, accept profile fields, or create an attestation."
        ),
    }


def _runtime_input_manifest(
    registry: dict[str, Any],
    registry_path: Path,
    *,
    registry_snapshot: tuple[str, int] | None = None,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Hash every file the loop can read so commit detects mid-run drift."""
    rows: list[dict[str, Any]] = []

    def add(label: str, path: Path) -> None:
        resolved = path.resolve()
        exists = resolved.is_file()
        rows.append(
            {
                "label": label,
                "exists": exists,
                "sha256": _file_sha256(resolved) if exists else None,
                "size": resolved.stat().st_size if exists else None,
            }
        )

    if registry_snapshot is None:
        add("registry", registry_path)
    else:
        registry_sha256, registry_size = registry_snapshot
        rows.append(
            {
                "label": "registry",
                "exists": True,
                "sha256": registry_sha256,
                "size": registry_size,
            }
        )
    for row in registry["cases"]:
        case_id = str(row["id"])
        case_path = _resolve_path(row["input"], registry_path.parent)
        add(f"case:{case_id}", case_path)
        review_value = row.get("profile_ground_truth")
        if isinstance(review_value, str) and review_value:
            add(
                f"profile_ground_truth:{case_id}",
                _resolve_path(review_value, registry_path.parent),
            )
        if not case_path.is_file():
            continue
        case = _load_object(case_path)
        if project_root is not None and _schema_errors(
            case,
            project_root / "schemas" / "qa-case.schema.json",
        ):
            continue
        financial = case.get("financial_evidence")
        if not isinstance(financial, dict):
            continue
        financial_paths: dict[str, Path] = {}
        for key in ("manifest", "ground_truth", "card_ground_truth"):
            value = financial.get(key)
            if isinstance(value, str) and value:
                path = _resolve_path(value, case_path.parent)
                financial_paths[key] = path
                add(f"financial:{case_id}:{key}", path)
        manifest_path = financial_paths.get("manifest")
        if manifest_path is None or not manifest_path.is_file():
            continue
        manifest = _load_object(manifest_path)
        if project_root is not None and _schema_errors(
            manifest,
            project_root / "schemas" / "manifest.schema.json",
        ):
            continue
        for source in manifest.get("sources", []):
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("id", ""))
            source_value = source.get("path")
            if isinstance(source_value, str) and source_value:
                add(
                    f"financial:{case_id}:source:{source_id}",
                    _resolve_path(source_value, manifest_path.parent),
                )
    return sorted(rows, key=lambda item: item["label"])


def _selection_material_from_runtime_manifest(
    registry: dict[str, Any],
    runtime_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hashes = {row["label"]: row.get("sha256") for row in runtime_manifest}
    material: list[dict[str, Any]] = []
    for row in registry["cases"]:
        case_id = str(row["id"])
        case_hash = hashes.get(f"case:{case_id}")
        review_hash = hashes.get(f"profile_ground_truth:{case_id}")
        if case_hash is None:
            raise ValueError(f"QA case input disappeared before execution: {case_id}")
        if row.get("input_sha256") is not None and row["input_sha256"] != case_hash:
            raise ValueError(f"QA case input changed during selection confirmation: {case_id}")
        if (
            row.get("profile_ground_truth_sha256") is not None
            and row["profile_ground_truth_sha256"] != review_hash
        ):
            raise ValueError(
                f"Profile ground truth changed during selection confirmation: {case_id}"
            )
        material.append(
            {
                "iteration": row["iteration"],
                "id": row["id"],
                "entity_scheme": row["entity_scheme"],
                "entity_id": row["entity_id"],
                "company": row["company"],
                "input_sha256": case_hash,
                "profile_ground_truth_sha256": review_hash,
            }
        )
    return material


def selection_digest(registry: dict[str, Any], registry_path: str | Path) -> str:
    """Return the digest a human confirms before a delivery run.

    This helper computes a digest only. It does not create or claim the human
    attestation and therefore cannot satisfy the external-selection boundary by
    itself.
    """
    path = Path(registry_path).resolve()
    return _canonical_sha256(_selection_material(registry, path))


def _validate_selection_attestation(
    registry: dict[str, Any],
    registry_path: Path,
    *,
    allow_contract_test: bool,
    material_digest: str | None = None,
) -> tuple[str, bool]:
    run_mode = registry.get("run_mode")
    if material_digest is None:
        material_digest = _canonical_sha256(_selection_material(registry, registry_path))
    if run_mode == "contract_test":
        if not allow_contract_test:
            raise ValueError(
                "contract_test registries are library-test fixtures and cannot be run as a delivery"
            )
        return material_digest, False
    if run_mode != "qa_delivery":
        raise ValueError("run_mode must be qa_delivery or contract_test")
    attestation = registry.get("selection_attestation")
    if not isinstance(attestation, dict):
        raise ValueError("qa_delivery requires an external human selection attestation")
    if attestation.get("case_set_sha256") != material_digest:
        raise ValueError(
            "Human selection attestation does not match the five immutable case inputs"
        )
    return material_digest, True


def _schema_failure_validation(
    case: dict[str, Any],
    schema_errors: list[str],
) -> dict[str, Any]:
    issues = [
        {
            "code": "qa_schema",
            "text": error,
            "text_zh": f"QA Schema 校验失败：{error}",
            "field": "",
            "subject": "",
        }
        for error in schema_errors
    ]
    fields = [
        {
            "id": field,
            "label": PROFILE_LABELS[field][0],
            "label_zh": PROFILE_LABELS[field][1],
            "status": "gap",
            "value": None,
            "candidate_value": None,
            "conclusion_type": None,
            "rationale": None,
            "evidence_refs": [],
            "errors": issues,
        }
        for field in PROFILE_FIELDS
    ]
    gaps = [
        {
            "id": f"gap-profile-{field}",
            "field": field,
            "status": "gap",
            "reasons": issues,
            "recommended_question_topic": field,
        }
        for field in PROFILE_FIELDS
    ]
    profile = {
        "schema_version": "1.0.0",
        "rule_version": QA_RULE_VERSION,
        "rule_digest": QA_RULE_DIGEST,
        "case_id": (case.get("case") or {}).get("id")
        if isinstance(case.get("case"), dict)
        else None,
        "company": case.get("company") if isinstance(case.get("company"), dict) else {},
        "passed": False,
        "fields": fields,
        "gap_queue": gaps,
        "errors": issues,
        "guardrails": {
            "traceability_is_structural_not_truth_verification": True,
            "company_statement_is_not_verified_fact": True,
            "no_investment_or_credit_rating": True,
            "no_aggregate_score": True,
        },
    }
    return {
        "schema_version": "1.0.0",
        "rule_version": QA_RULE_VERSION,
        "rule_digest": QA_RULE_DIGEST,
        "passed": False,
        "validation_scope": "structural_traceability_only",
        "delivery_eligible": False,
        "human_profile_review_required_for_delivery": True,
        "qa": {"complete": False, "answer_count": 0, "next_question": None},
        "profile": profile,
        "triage": {
            "rule_version": QA_RULE_VERSION,
            "rule_digest": QA_RULE_DIGEST,
            "eligible": False,
            "upstream_validation": {
                "passed": False,
                "error_codes": ["qa_schema"],
            },
            "routes": [
                {"line": line, "status": "stub_only", "selected": False, "reasons": []}
                for line in ("expert", "map", "radar")
            ],
            "guardrail": "Routing not run because the QA case failed schema validation.",
        },
        "errors": issues,
        "guardrails": {
            "human_selected_company_required": True,
            "unsupported_profile_fields_fail_closed": True,
            "financial_core_unchanged": True,
            "expert_map_radar_stub_only": True,
            "private_data_must_not_be_committed": True,
        },
    }


def _validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("selection_policy") != "human_supplied_only":
        raise ValueError("QA registry must use selection_policy=human_supplied_only")
    cases = registry.get("cases")
    if not isinstance(cases, list) or len(cases) != 5:
        raise ValueError("QA registry must contain exactly five human-supplied cases")
    if not all(isinstance(item, dict) for item in cases):
        raise ValueError("Every QA registry case must be an object")
    iterations = [item.get("iteration") for item in cases]
    if iterations != [1, 2, 3, 4, 5]:
        raise ValueError("QA registry iterations must be exactly 1 through 5 in order")
    ids = [str(item.get("id", "")) for item in cases]
    entities = [
        (str(item.get("entity_scheme", "")), str(item.get("entity_id", ""))) for item in cases
    ]
    if len(set(ids)) != 5 or len(set(entities)) != 5:
        raise ValueError("QA registry ids and stable entity ids must be unique")
    for item in cases:
        if item.get("selection_origin") != "human_supplied":
            raise ValueError("Every QA company must declare selection_origin=human_supplied")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", str(item.get("id", ""))):
            raise ValueError(
                "QA case ids may contain only lowercase letters, digits, dot, dash, and underscore"
            )


def _reject_company_specific_qa_rules(
    registry: dict[str, Any],
    project_root: Path,
) -> None:
    """Reject decision/contract literals keyed to a selected company identity."""

    literals: dict[str, set[str]] = {}
    for path in _qa_rule_bundle_paths(project_root):
        if not path.is_file():
            continue
        values: set[str] = set()
        if path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            decision_nodes: list[ast.AST] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    decision_nodes.append(node)
                elif isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
                    decision_nodes.append(node.test)
                elif isinstance(node, ast.comprehension):
                    decision_nodes.extend(node.ifs)
                elif isinstance(node, ast.MatchValue):
                    decision_nodes.append(node.value)
                elif isinstance(node, ast.Dict):
                    decision_nodes.extend(key for key in node.keys if key is not None)
            for decision in decision_nodes:
                values.update(
                    str(child.value).strip().casefold()
                    for child in ast.walk(decision)
                    if isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and child.value.strip()
                )
        elif path.suffix == ".json":
            payload = _load_object(path)

            def collect_contract_values(
                value: Any,
                target_values: set[str] = values,
            ) -> None:
                if isinstance(value, dict):
                    const = value.get("const")
                    if isinstance(const, str) and const.strip():
                        target_values.add(const.strip().casefold())
                    enum = value.get("enum")
                    if isinstance(enum, list):
                        target_values.update(
                            item.strip().casefold()
                            for item in enum
                            if isinstance(item, str) and item.strip()
                        )
                    for child in value.values():
                        collect_contract_values(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_contract_values(child)

            collect_contract_values(payload)
        if values:
            literals[path.relative_to(project_root).as_posix()] = values

    hits: list[str] = []
    for row in registry["cases"]:
        for value in (row["company"], row["entity_id"], row["id"]):
            needle = str(value).strip().casefold()
            if len(needle) < 8:
                continue
            for relative_path, path_literals in literals.items():
                if needle in path_literals:
                    hits.append(f"{value} ({relative_path})")
    if hits:
        raise ValueError(
            "Company-specific QA rule literals are forbidden: " + ", ".join(sorted(set(hits)))
        )


def _profile_review_result(
    row: dict[str, Any],
    validation: dict[str, Any],
    *,
    registry_path: Path,
    project_root: Path,
    delivery_eligible: bool,
    review_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    if not delivery_eligible:
        return {
            "status": "contract_test_not_human_reviewed",
            "contract_check_passed": True,
            "passed": False,
            "delivery_eligible": False,
            "errors": [],
        }
    review_origin = _resolve_path(row["profile_ground_truth"], registry_path.parent)
    review_path = review_snapshot_path or review_origin
    review = _load_object_exact(review_path, row["profile_ground_truth_sha256"])
    errors = _schema_errors(
        review,
        project_root / "schemas" / "qa-profile-ground-truth.schema.json",
    )
    if review.get("case_id") != row["id"]:
        errors.append("case_id: profile ground truth must match the registry case id")
    expected_entity = {
        "scheme": row["entity_scheme"],
        "value": row["entity_id"],
        "legal_name": row["company"],
    }
    if review.get("entity") != expected_entity:
        errors.append(
            "entity: profile ground truth must exactly match registry scheme, value, and legal name"
        )

    expected_fields = review.get("fields") if isinstance(review.get("fields"), list) else []
    expected_by_id = {item.get("field"): item for item in expected_fields if isinstance(item, dict)}
    if set(expected_by_id) != set(PROFILE_FIELDS) or len(expected_fields) != len(PROFILE_FIELDS):
        errors.append("fields: profile ground truth must contain each profile field exactly once")
    actual_by_id = {
        item.get("id"): item
        for item in validation.get("profile", {}).get("fields", [])
        if isinstance(item, dict)
    }
    for field in PROFILE_FIELDS:
        expected = expected_by_id.get(field)
        actual = actual_by_id.get(field)
        if expected is None or actual is None:
            continue
        if actual.get("status") != "supported":
            errors.append(f"{field}: generated profile field is not supported")
        if actual.get("value") != expected.get("value"):
            errors.append(f"{field}: generated value does not match human ground truth")
        if actual.get("conclusion_type") != expected.get("conclusion_type"):
            errors.append(f"{field}: conclusion_type does not match human ground truth")
        actual_refs = sorted(
            (
                {"source_id": ref.get("source_id"), "quote": ref.get("quote")}
                for ref in actual.get("evidence_refs", [])
                if isinstance(ref, dict)
            ),
            key=lambda item: (str(item["source_id"]), str(item["quote"])),
        )
        expected_refs = sorted(
            (
                {"source_id": ref.get("source_id"), "quote": ref.get("quote")}
                for ref in expected.get("evidence_refs", [])
                if isinstance(ref, dict)
            ),
            key=lambda item: (str(item["source_id"]), str(item["quote"])),
        )
        if actual_refs != expected_refs:
            errors.append(f"{field}: exact evidence references do not match human ground truth")
    return {
        "status": "passed" if not errors else "failed",
        "contract_check_passed": not errors,
        "passed": not errors,
        "delivery_eligible": True,
        "path_ref": f"profile-ground-truth:{row['id']}",
        "sha256": row["profile_ground_truth_sha256"],
        "review": review.get("review"),
        "errors": errors,
    }


def _validate_financial_ground_truth(
    ground: dict[str, Any],
    card_ground: dict[str, Any],
    expected_entity: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(ground.get("case"), str) or not ground["case"].strip():
        errors.append("extraction ground truth needs a non-empty case label")
    tolerance = ground.get("tolerance")
    if (
        not isinstance(tolerance, (int, float))
        or isinstance(tolerance, bool)
        or not math.isfinite(tolerance)
        or tolerance <= 0
        or tolerance > 0.01
    ):
        errors.append("extraction ground-truth tolerance must be in (0, 0.01]")
    facts = ground.get("facts")
    if not isinstance(facts, list):
        errors.append("extraction ground truth needs a facts array")
        facts = []
    fact_keys: list[tuple[str, str]] = []
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict):
            errors.append(f"facts[{index}] must be an object")
            continue
        period = fact.get("period")
        name = fact.get("name")
        value = fact.get("value")
        locator = fact.get("locator")
        if not isinstance(period, str) or not period.strip():
            errors.append(f"facts[{index}].period must be non-empty")
        if name not in REQUIRED_FINANCIAL_FACTS:
            errors.append(f"facts[{index}].name is not a required validated fact")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            errors.append(f"facts[{index}].value must be numeric")
        if not isinstance(locator, str) or not locator.strip():
            errors.append(f"facts[{index}].locator must be non-empty")
        if isinstance(period, str) and isinstance(name, str):
            fact_keys.append((period, name))
    if len(fact_keys) != len(set(fact_keys)):
        errors.append("extraction ground-truth fact period/name keys must be unique")
    periods = {period for period, _ in fact_keys}
    expected_fact_keys = {(period, name) for period in periods for name in REQUIRED_FINANCIAL_FACTS}
    if len(periods) != 2 or set(fact_keys) != expected_fact_keys:
        errors.append(
            "extraction ground truth must be exactly two common periods by five validated facts"
        )

    metrics = ground.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("extraction ground truth needs a metrics object")
        metrics = {}
    if set(metrics) != REQUIRED_FINANCIAL_METRICS:
        errors.append("extraction ground truth must contain exactly the four validated metrics")
    for metric_id, value in metrics.items():
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            errors.append(f"metric {metric_id} must be numeric")

    if not isinstance(card_ground.get("case"), str) or not card_ground["case"].strip():
        errors.append("card ground truth needs a non-empty case label")
    signals = card_ground.get("signals")
    if not isinstance(signals, dict):
        errors.append("card ground truth needs a signals object")
        signals = {}
    if set(signals) != VALIDATED_FINANCE_DIMENSIONS:
        errors.append("card ground truth must cover exactly the two validated dimensions")
    for dimension, signal in signals.items():
        if signal not in FINANCIAL_SIGNALS:
            errors.append(f"card ground-truth signal is invalid for {dimension}")
    if ground.get("entity") != expected_entity:
        errors.append("extraction ground-truth entity must exactly match the QA company")
    if card_ground.get("entity") != expected_entity:
        errors.append("card ground-truth entity must exactly match the QA company")
    return errors


def _snapshot_subject_source_hashes(
    manifest: dict[str, Any],
    *,
    case_id: str,
    snapshot: _RuntimeInputSnapshot,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    captured_hashes = snapshot.source_hashes.get(case_id, [])
    for index, source in enumerate(manifest.get("sources", [])):
        if not isinstance(source, dict) or source.get("role", "subject") != "subject":
            continue
        digest = captured_hashes[index] if index < len(captured_hashes) else None
        if digest is None:
            raise ValueError(
                f"Manifest subject source was not captured in the runtime snapshot: "
                f"{source.get('id', '')}"
            )
        rows.append({"source_id": str(source.get("id", "")), "sha256": digest})
    return sorted(rows, key=lambda item: item["source_id"])


def _snapshot_all_source_hashes(
    manifest: dict[str, Any],
    *,
    case_id: str,
    snapshot: _RuntimeInputSnapshot,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    captured_hashes = snapshot.source_hashes.get(case_id, [])
    for index, source in enumerate(manifest.get("sources", [])):
        digest = captured_hashes[index] if index < len(captured_hashes) else None
        if not isinstance(source, dict) or digest is None:
            raise ValueError("Every manifest source must be captured with a stable digest")
        rows.append(
            {
                "source_id": str(source.get("id", "")),
                "role": str(source.get("role", "subject")),
                "sha256": digest,
            }
        )
    return sorted(rows, key=lambda item: (item["source_id"], item["role"]))


def _validate_financial_review(
    case: dict[str, Any],
    review: Any,
    *,
    manifest_sha256: str,
    ground_sha256: str,
    card_ground_sha256: str,
    subject_sources: list[dict[str, str]],
    all_sources: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(review, dict):
        return ["available annual-report evidence needs a human review attestation"]
    company = case.get("company") or {}
    stable_identifier = company.get("stable_identifier") or {}
    expected_entity = {
        "scheme": stable_identifier.get("scheme"),
        "value": stable_identifier.get("value"),
        "legal_name": company.get("legal_name"),
    }
    expected = {
        "actor_type": "human",
        "scope": "financial_ground_truth_and_entity_binding",
        "status": "approved",
        "entity": expected_entity,
        "manifest_sha256": manifest_sha256,
        "ground_truth_sha256": ground_sha256,
        "card_ground_truth_sha256": card_ground_sha256,
        "subject_sources": subject_sources,
        "all_sources": all_sources,
    }
    for key, expected_value in expected.items():
        if review.get(key) != expected_value:
            errors.append(f"financial review {key} does not match the immutable input")
    if not isinstance(review.get("reviewed_by"), str) or not review["reviewed_by"].strip():
        errors.append("financial review needs a non-empty human reviewer identifier")
    if not isinstance(review.get("reviewed_at"), str) or not review["reviewed_at"].strip():
        errors.append("financial review needs reviewed_at")
    if not isinstance(review.get("approval_id"), str) or not review["approval_id"].strip():
        errors.append("financial review needs approval_id")
    return errors


def _run_financial_evidence(
    case: dict[str, Any],
    *,
    case_id: str,
    output_dir: Path,
    project_root: Path,
    runtime_snapshot: _RuntimeInputSnapshot,
) -> dict[str, Any]:
    contract = case.get("financial_evidence") or {}
    annual_report_status = contract.get("annual_report_status")
    manifest_value = contract.get("manifest")
    ground_value = contract.get("ground_truth")
    card_ground_value = contract.get("card_ground_truth")
    if annual_report_status == "not_available":
        waiver = contract.get("profile_only_waiver")
        errors: list[str] = []
        if any(value is not None for value in (manifest_value, ground_value, card_ground_value)):
            errors.append(
                "not_available annual-report status requires all financial paths to be null"
            )
        if contract.get("review") is not None:
            errors.append("not_available annual-report status cannot carry a financial review")
        if not isinstance(waiver, dict):
            errors.append("profile-only execution requires a human waiver")
        else:
            company = case.get("company") or {}
            stable_identifier = company.get("stable_identifier") or {}
            expected_entity = {
                "scheme": stable_identifier.get("scheme"),
                "value": stable_identifier.get("value"),
                "legal_name": company.get("legal_name"),
            }
            if waiver.get("actor_type") != "human":
                errors.append("profile-only waiver actor_type must be human")
            if waiver.get("status") != "approved":
                errors.append("profile-only waiver status must be approved")
            if waiver.get("scope") != "profile_only_annual_report_waiver":
                errors.append("profile-only waiver scope is invalid")
            if waiver.get("entity") != expected_entity:
                errors.append("profile-only waiver entity must match the QA company")
            if not str(waiver.get("approval_id", "")).strip():
                errors.append("profile-only waiver needs approval_id")
            if not str(waiver.get("approved_by", "")).strip():
                errors.append("profile-only waiver needs approved_by")
            if not str(waiver.get("approved_at", "")).strip():
                errors.append("profile-only waiver needs approved_at")
            if waiver.get("reason_code") != "annual_report_not_available_to_run":
                errors.append("profile-only waiver reason_code is invalid")
            if not str(waiver.get("rationale", "")).strip():
                errors.append("profile-only waiver needs a rationale")
            basis_refs = waiver.get("basis_evidence_refs")
            source_index = {
                source.get("id"): source
                for source in case.get("sources", [])
                if isinstance(source, dict)
            }
            if not isinstance(basis_refs, list) or not basis_refs:
                errors.append("profile-only waiver needs exact basis evidence")
            else:
                for ref in basis_refs:
                    if not isinstance(ref, dict):
                        errors.append("profile-only waiver evidence must be an object")
                        continue
                    source = source_index.get(ref.get("source_id"))
                    quote = ref.get("quote")
                    if source is None:
                        errors.append("profile-only waiver cites an unknown source")
                    elif (
                        not isinstance(quote, str)
                        or not quote.strip()
                        or quote not in str(source.get("excerpt", ""))
                    ):
                        errors.append("profile-only waiver quote must be an exact source substring")
        if errors:
            return {
                "status": "invalid_profile_only_waiver",
                "passed": False,
                "reason": "; ".join(errors),
            }
        return {
            "status": "profile_only_waived",
            "passed": True,
            "reason": (
                "A human documented that an annual report was not available and "
                "approved profile-only execution; no financial card was fabricated."
            ),
            "waiver": waiver,
            "model_calls": 0,
            "network_calls": 0,
        }
    if annual_report_status != "available":
        return {
            "status": "invalid_financial_contract",
            "passed": False,
            "reason": "annual_report_status must be available or not_available.",
        }
    if not all(
        isinstance(value, str) and value.strip()
        for value in (manifest_value, ground_value, card_ground_value)
    ):
        return {
            "status": "invalid_financial_contract",
            "passed": False,
            "reason": "manifest, ground_truth, and card_ground_truth must be supplied together.",
        }

    input_labels = {
        "manifest": f"financial:{case_id}:manifest",
        "ground_truth": f"financial:{case_id}:ground_truth",
        "card_ground_truth": f"financial:{case_id}:card_ground_truth",
    }
    manifest = runtime_snapshot.files.get(input_labels["manifest"])
    ground = runtime_snapshot.files.get(input_labels["ground_truth"])
    card_ground = runtime_snapshot.files.get(input_labels["card_ground_truth"])
    missing = [
        label
        for label, snapshot_path in (
            ("manifest", manifest),
            ("ground_truth", ground),
            ("card_ground_truth", card_ground),
        )
        if snapshot_path is None
    ]
    if missing:
        return {
            "status": "financial_input_missing",
            "passed": False,
            "reason": "Missing human-supplied financial input(s): " + ", ".join(missing),
        }

    assert manifest is not None and ground is not None and card_ground is not None
    try:
        _verify_runtime_input_snapshot(runtime_snapshot)
        manifest_payload = _load_object_exact(
            manifest,
            runtime_snapshot.input_hashes[input_labels["manifest"]],
        )
        ground_payload = _load_object_exact(
            ground,
            runtime_snapshot.input_hashes[input_labels["ground_truth"]],
        )
        card_ground_payload = _load_object_exact(
            card_ground,
            runtime_snapshot.input_hashes[input_labels["card_ground_truth"]],
        )
    except _RuntimeSnapshotIntegrityError:
        raise
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid_financial_ground_truth",
            "passed": False,
            "reason": f"Financial input JSON failed closed: {exc}",
        }
    company = case.get("company") or {}
    stable_identifier = company.get("stable_identifier") or {}
    expected_entity = {
        "scheme": stable_identifier.get("scheme"),
        "value": stable_identifier.get("value"),
        "legal_name": company.get("legal_name"),
    }
    financial_input_errors = [
        *(
            "manifest schema: " + error
            for error in _schema_errors(
                manifest_payload,
                project_root / "schemas" / "manifest.schema.json",
            )
        ),
        *(
            "extraction-ground-truth schema: " + error
            for error in _schema_errors(
                ground_payload,
                project_root / "schemas" / "financial-ground-truth.schema.json",
            )
        ),
        *(
            "card-ground-truth schema: " + error
            for error in _schema_errors(
                card_ground_payload,
                project_root / "schemas" / "card-ground-truth.schema.json",
            )
        ),
    ]
    financial_input_errors.extend(
        _validate_financial_ground_truth(
            ground_payload,
            card_ground_payload,
            expected_entity,
        )
    )
    source_snapshots = runtime_snapshot.source_files.get(case_id, [])
    manifest_sources = manifest_payload.get("sources", [])
    if len(source_snapshots) != len(manifest_sources) or any(
        path is None for path in source_snapshots
    ):
        financial_input_errors.append(
            "every manifest source must exist in the volatile runtime input snapshot"
        )
    try:
        subject_sources = _snapshot_subject_source_hashes(
            manifest_payload,
            case_id=case_id,
            snapshot=runtime_snapshot,
        )
        all_sources = _snapshot_all_source_hashes(
            manifest_payload,
            case_id=case_id,
            snapshot=runtime_snapshot,
        )
    except ValueError as exc:
        subject_sources = []
        all_sources = []
        financial_input_errors.append(str(exc))
    financial_input_errors.extend(
        _validate_financial_review(
            case,
            contract.get("review"),
            manifest_sha256=runtime_snapshot.input_hashes[input_labels["manifest"]],
            ground_sha256=runtime_snapshot.input_hashes[input_labels["ground_truth"]],
            card_ground_sha256=runtime_snapshot.input_hashes[input_labels["card_ground_truth"]],
            subject_sources=subject_sources,
            all_sources=all_sources,
        )
    )
    if contract.get("profile_only_waiver") is not None:
        financial_input_errors.append(
            "available annual-report status cannot carry a profile-only waiver"
        )
    if financial_input_errors:
        return {
            "status": "invalid_financial_ground_truth",
            "passed": False,
            "reason": "; ".join(financial_input_errors),
        }
    subject = manifest_payload.get("subject") or {}
    identity = subject.get("identity") or {}
    qa_identifier = str(stable_identifier.get("value", ""))
    qa_scheme = str(stable_identifier.get("scheme", ""))
    if identity:
        identity_matches = (
            (qa_scheme == "entity_id" and qa_identifier == str(identity.get("entity_id", "")))
            or (
                qa_scheme == str(identity.get("scheme", ""))
                and qa_identifier == str(identity.get("value", ""))
            )
        ) and str(company.get("legal_name", "")).strip() == str(
            identity.get("legal_name", "")
        ).strip()
        identity_basis = "stable_identifier"
    else:
        identity_matches = (
            str(company.get("legal_name", "")).strip()
            == str(subject.get("organization", "")).strip()
        )
        identity_basis = "exact_legacy_legal_name"
    if not identity_matches:
        return {
            "status": "financial_entity_mismatch",
            "passed": False,
            "reason": "QA company identity does not exactly match the supplied financial manifest.",
            "identity_basis": identity_basis,
        }

    runtime_manifest = runtime_snapshot.runtime_manifests.get(case_id)
    if runtime_manifest is None:
        return {
            "status": "financial_input_missing",
            "passed": False,
            "reason": "A complete runtime snapshot could not be built for every manifest source.",
            "identity_basis": identity_basis,
        }
    try:
        _verify_runtime_input_snapshot(runtime_snapshot)
        audit = run_audit(
            str(runtime_manifest),
            only_dimensions=VALIDATED_FINANCE_DIMENSIONS,
            allowed_input_root=str(runtime_snapshot.root),
            manifest_bytes=runtime_snapshot.runtime_manifest_payloads[case_id],
        )
        _verify_runtime_input_snapshot(runtime_snapshot)
        audit["manifest"] = (
            "input-sha256:" + runtime_snapshot.input_hashes[input_labels["manifest"]]
        )
        audit.setdefault("execution", {})["runtime_input_snapshot"] = {
            "enabled": True,
            "content_addressed": True,
            "volatile": True,
            "retained": False,
            "manifest_sha256": runtime_snapshot.input_hashes[input_labels["manifest"]],
        }
        financial_dir = output_dir / "financial"
        artifacts = write_artifacts(audit, financial_dir)
    except _RuntimeSnapshotIntegrityError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {
            "status": "failed",
            "passed": False,
            "reason": f"Financial audit failed closed: {exc}",
            "identity_basis": identity_basis,
        }
    try:
        extraction_evaluation = evaluate_financial_audit(audit, ground_payload)
        extraction_evaluation["exit_code"] = 0
        card_evaluation = evaluate_financial_cards(audit, card_ground_payload)
        card_evaluation["exit_code"] = 0
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "status": "failed",
            "passed": False,
            "reason": f"Financial ground-truth evaluator failed closed: {exc}",
            "identity_basis": identity_basis,
        }
    _verify_runtime_input_snapshot(runtime_snapshot)
    model_calls = audit.get("execution", {}).get("model_calls")
    network_calls = audit.get("execution", {}).get("network_calls")
    passed = bool(
        audit.get("validation", {}).get("passed")
        and extraction_evaluation.get("passed")
        and card_evaluation.get("passed")
        and extraction_evaluation.get("exit_code") == 0
        and card_evaluation.get("exit_code") == 0
        and extraction_evaluation.get("total_checks", 0) >= MIN_EXTRACTION_CHECKS
        and card_evaluation.get("total_checks", 0) >= MIN_CARD_CHECKS
        and model_calls == 0
        and network_calls == 0
    )
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "manifest_ref": "financial-manifest:" + case_id,
        "manifest_sha256": runtime_snapshot.input_hashes[input_labels["manifest"]],
        "artifacts": artifacts,
        "extraction_evaluation": extraction_evaluation,
        "card_evaluation": card_evaluation,
        "model_calls": model_calls,
        "network_calls": network_calls,
        "selected_dimensions": sorted(VALIDATED_FINANCE_DIMENSIONS),
        "identity_basis": identity_basis,
        "ground_truth_review": contract.get("review"),
        "runtime_input_snapshot": {
            "used": True,
            "content_addressed": True,
            "volatile": True,
            "retained": False,
        },
        "minimum_checks": {
            "extraction": MIN_EXTRACTION_CHECKS,
            "cards": MIN_CARD_CHECKS,
        },
    }


def _profile_values(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        field["id"]: {
            "status": field["status"],
            "value": field["value"],
            "conclusion_type": field["conclusion_type"],
            "evidence_refs": field["evidence_refs"],
        }
        for field in validation["profile"]["fields"]
    }


def _durable_case_view(case: dict[str, Any]) -> dict[str, Any]:
    """Remove local input paths while retaining the evidence needed for review."""
    durable = deepcopy(case)
    financial = durable.get("financial_evidence")
    if isinstance(financial, dict):
        for key in ("manifest", "ground_truth", "card_ground_truth"):
            if isinstance(financial.get(key), str):
                financial[key] = f"runtime-input-ref:{key}"
    return durable


def _input_bundle_material(
    row: dict[str, Any],
    case: dict[str, Any],
    case_path: Path,
    *,
    case_sha256: str | None = None,
) -> dict[str, Any]:
    financial = case.get("financial_evidence")
    financial = financial if isinstance(financial, dict) else {}
    review = financial.get("review")
    review = review if isinstance(review, dict) else {}
    return {
        "entity": {
            "scheme": row["entity_scheme"],
            "value": row["entity_id"],
            "legal_name": row["company"],
        },
        "case_sha256": case_sha256 or _file_sha256(case_path),
        "profile_ground_truth_sha256": row.get("profile_ground_truth_sha256"),
        "financial": {
            "annual_report_status": financial.get("annual_report_status"),
            "manifest_sha256": review.get("manifest_sha256"),
            "ground_truth_sha256": review.get("ground_truth_sha256"),
            "card_ground_truth_sha256": review.get("card_ground_truth_sha256"),
            "subject_sources": deepcopy(review.get("subject_sources", [])),
            "all_sources": deepcopy(review.get("all_sources", [])),
        },
    }


def _markdown_evidence_ref(ref: dict[str, Any]) -> str:
    target = str(ref.get("url_or_source_id") or "").strip()
    location = f"{ref.get('source_id', '')} @ {ref.get('locator', '')}"
    if target.lower().startswith(("https://", "http://")):
        location = f"[{location}]({target})"
    elif target:
        location += f" [{target}]"
    return f"{location}: {ref.get('quote', '')}"


def _html_evidence_ref(ref: dict[str, Any]) -> str:
    target = str(ref.get("url_or_source_id") or "").strip()
    location = (
        f"{html.escape(str(ref.get('source_id', '')))} @ {html.escape(str(ref.get('locator', '')))}"
    )
    if target.lower().startswith(("https://", "http://")):
        location = (
            f'<a href="{html.escape(target, quote=True)}" rel="noopener noreferrer">{location}</a>'
        )
    elif target:
        location += f" [{html.escape(target)}]"
    return f"{location}: {html.escape(str(ref.get('quote', '')))}"


def _markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# CleanTech Evidence QA｜五家公司自迭代报告",
        "",
        "> 企业均须由人工指定。画像通过只表示字段具有精确来源引用，不表示企业陈述已被证实，也不构成投资、信用或综合风险评级。",
        "",
        f"- Deliverable status: {result['deliverable_status']}",
        f"- Contract execution: {'passed' if result['execution_passed'] else 'failed'}",
        f"- Human-input delivery eligible: {result['delivery_eligible']}",
        f"- Completed execution checks: {result['completed_execution_count']}/5",
        f"- Completed delivery cases: {result['completed_case_count']}/5",
        f"- Run: {result['run_number']} ({result.get('run_hash') or result['run_content_id']})",
        "- Data classification: internal_restricted; publication is not authorized",
        f"- Rule version: {result['rule_version']}",
        f"- Rule digest: {result['rule_digest']}",
        (
            "- Regression evidence: "
            f"{result['regression_evidence']['status']}; "
            f"required={result['regression_evidence']['required']}; "
            f"complete={result['regression_evidence']['complete']}"
        ),
        (
            "- Human attestation assurance: "
            f"{result['human_attestation_assurance']['status']}; "
            "cryptographic_identity_verified="
            f"{result['human_attestation_assurance']['cryptographic_identity_verified']}"
        ),
        f"- Financial traceability: {result['financial_summary']['status']}",
        "",
    ]
    for row in result["cases"]:
        lines.extend(
            [
                f"## {row['iteration']}. {row['company']}",
                "",
                f"- Execution status: {'passed' if row['execution_passed'] else 'failed'}",
                f"- Delivery status: {'passed' if row['passed'] else 'not passed'}",
                f"- Selection: {row['selection_origin']}",
                f"- QA report: {row['qa_artifacts'].get('report_html', '')}",
                f"- Human profile review: {row['profile_review']['status']}",
                f"- Financial: {row['financial']['status']}",
                "",
                "### 画像卡 / Profile card",
                "",
                "| 字段 | 状态 | 值 | 出处 |",
                "|---|---|---|---|",
            ]
        )
        for field, value in row["profile"].items():
            refs = "；".join(_markdown_evidence_ref(ref) for ref in value["evidence_refs"]) or "—"
            lines.append(
                f"| {field} | {value['status']} | {json.dumps(value['value'], ensure_ascii=False)} | {refs} |"
            )
        lines.extend(["", "### 分诊 / Triage", ""])
        for route in row["triage"]:
            if route["selected"]:
                reasons = "；".join(
                    reason["text_zh"]
                    + (
                        " ["
                        + "；".join(
                            _markdown_evidence_ref(ref) for ref in reason.get("evidence_refs", [])
                        )
                        + "]"
                        if reason.get("evidence_refs")
                        else ""
                    )
                    for reason in route["reasons"]
                )
                lines.append(f"- {route['line']}: {reasons}")
        lines.extend(["", "### 缺口 / Gaps", ""])
        if row["gaps"]:
            for gap in row["gaps"]:
                lines.append(
                    f"- {gap['field']}: "
                    + "；".join(reason["text_zh"] for reason in gap["reasons"])
                )
        else:
            lines.append("- 无画像出处缺口 / No profile traceability gaps.")
        log = row["iteration_log"]
        lines.extend(
            [
                "",
                "### 通用性记录 / Generalization log",
                "",
                f"- Initial failure: {log['initial_failure_zh']} / {log['initial_failure']}",
                f"- General fix: {log['general_fix_zh']} / {log['general_fix']}",
                f"- Initial missing-source fields: {', '.join(log['initial_gap_fields']) or 'none'}",
                f"- Residual risk: {log['residual_risk_zh']} / {log['residual_risk']}",
                "",
            ]
        )
    lines.extend(["## 高频出处缺口 / Frequent missing-source fields", ""])
    if result["frequent_gap_fields"]:
        for item in result["frequent_gap_fields"]:
            recommendation = item["recommended_question"]
            lines.append(
                f"- {item['field']}: {item['count']}；补问 `{recommendation['question_id']}`："
                f"{recommendation['text_zh']} / {recommendation['text']}"
            )
    else:
        lines.append("- 当前已完成案例没有画像出处缺口。")
    lines.extend(["", "## 通用性问题及修法 / Generalization fixes", ""])
    if result["generalization_issues"]:
        for issue in result["generalization_issues"]:
            lines.append(
                f"- {issue['case_id']}: {', '.join(issue['failure_codes'])} → "
                f"{issue['general_fix_zh']} / {issue['general_fix']}；"
                f"regressed={', '.join(issue['regressed_prior_passes']) or 'none'}; "
                f"regression={issue['regression_status']}; "
                f"complete={issue['regression_complete']}"
            )
    else:
        lines.append("- 当前哈希链中没有‘失败 → 通用规则变更 → 通过’事件。")
    lines.extend(["", "## 输入修订 / Input corrections", ""])
    if result["input_corrections"]:
        for issue in result["input_corrections"]:
            lines.append(
                f"- {issue['case_id']}: {issue['classification']} "
                f"({issue['from_input_bundle_sha256']} → {issue['to_input_bundle_sha256']})"
            )
    else:
        lines.append("- None recorded; input changes are not counted as general rule fixes.")
    lines.extend(
        [
            "",
            "## 财务回归 / Financial regression",
            "",
            f"- {result['financial_summary']['text_zh']}",
            f"- {result['financial_summary']['text']}",
            f"- Checks: {result['financial_summary']['passed_checks']}/{result['financial_summary']['total_checks']}；traceability={result['financial_summary']['traceability_percent']}",
            "",
            "Expert、Map、Radar 均未执行；本报告只包含确定性分诊留桩。",
        ]
    )
    return "\n".join(lines) + "\n"


def _html_report(markdown_result: dict[str, Any]) -> str:
    sections = [
        '<style id="responsive-safety">p,li{overflow-wrap:anywhere}'
        "section{min-width:0}</style>"
    ]
    for row in markdown_result["cases"]:
        fields = "".join(
            f"<tr><td>{html.escape(field)}</td><td>{html.escape(value['status'])}</td><td>{html.escape(json.dumps(value['value'], ensure_ascii=False))}</td><td>"
            + "<br>".join(_html_evidence_ref(ref) for ref in value["evidence_refs"])
            + "</td></tr>"
            for field, value in row["profile"].items()
        )
        routes = "".join(
            f"<li><strong>{html.escape(route['line'])}</strong>: "
            + "；".join(
                html.escape(reason["text_zh"])
                + (
                    "<ul>"
                    + "".join(
                        "<li>" + _html_evidence_ref(ref) + "</li>"
                        for ref in reason.get("evidence_refs", [])
                    )
                    + "</ul>"
                    if reason.get("evidence_refs")
                    else ""
                )
                for reason in route["reasons"]
            )
            + "</li>"
            for route in row["triage"]
            if route["selected"]
        )
        gaps = (
            "".join(f"<li>{html.escape(gap['field'])}</li>" for gap in row["gaps"])
            or "<li>无画像出处缺口</li>"
        )
        log = row["iteration_log"]
        sections.append(
            f"<section><h2>{row['iteration']}. {html.escape(row['company'])}</h2><p>Execution: {'passed' if row['execution_passed'] else 'failed'} · Delivery: {'passed' if row['passed'] else 'not passed'} · Human profile review: {html.escape(row['profile_review']['status'])} · Financial: {html.escape(row['financial']['status'])}</p><table><thead><tr><th>字段</th><th>状态</th><th>值</th><th>出处</th></tr></thead><tbody>{fields}</tbody></table><h3>分诊</h3><ul>{routes}</ul><h3>缺口</h3><ul>{gaps}</ul><h3>通用性记录</h3><ul><li>初始失败：{html.escape(log['initial_failure_zh'])}</li><li>通用修法：{html.escape(log['general_fix_zh'])}</li><li>初始出处缺口：{html.escape(', '.join(log['initial_gap_fields']) or 'none')}</li><li>残余风险：{html.escape(log['residual_risk_zh'])}</li><li>历史尝试：{log['attempt_count']}</li></ul></section>"
        )
    frequent = (
        "".join(
            f"<li>{html.escape(item['field'])}: {item['count']} · "
            f"<code>{html.escape(item['recommended_question']['question_id'])}</code> · "
            f"{html.escape(item['recommended_question']['text_zh'])}</li>"
            for item in markdown_result["frequent_gap_fields"]
        )
        or "<li>当前已完成案例没有画像出处缺口。</li>"
    )
    generalization = (
        "".join(
            "<li>"
            + html.escape(issue["case_id"])
            + ": "
            + html.escape(", ".join(issue["failure_codes"]))
            + " → "
            + html.escape(issue["general_fix_zh"])
            + " | regression="
            + html.escape(issue["regression_status"])
            + " | complete="
            + str(issue["regression_complete"]).lower()
            + "</li>"
            for issue in markdown_result["generalization_issues"]
        )
        or "<li>当前哈希链中没有‘失败 → 通用规则变更 → 通过’事件。</li>"
    )
    input_corrections = (
        "".join(
            "<li>"
            + html.escape(issue["case_id"])
            + ": "
            + html.escape(issue["classification"])
            + "</li>"
            for issue in markdown_result["input_corrections"]
        )
        or "<li>None recorded; input changes are not counted as general rule fixes.</li>"
    )
    financial = markdown_result["financial_summary"]
    run_reference = str(markdown_result.get("run_hash") or markdown_result["run_content_id"])
    regression = markdown_result["regression_evidence"]
    assurance = markdown_result["human_attestation_assurance"]
    run_reference = (
        f"{run_reference} | Regression: {regression['status']} "
        f"(required={str(regression['required']).lower()}, "
        f"complete={str(regression['complete']).lower()}) | "
        f"Human attestation: {assurance['status']} "
        "(cryptographic identity verified=false)"
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CleanTech Evidence QA loop</title><style>body{{margin:0;background:#f4f7fb;color:#172235;font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}}header{{background:#10243e;color:white;padding:28px max(20px,calc((100vw - 1100px)/2))}}main{{max-width:1100px;margin:20px auto;padding:0 18px 40px}}section{{background:white;border:1px solid #dbe3ee;border-radius:12px;padding:20px;margin:16px 0}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid #dbe3ee;text-align:left;vertical-align:top}}@media(max-width:700px){{table{{display:block;overflow:auto}}}}</style></head><body><header><h1>CleanTech Evidence QA｜五家公司自迭代</h1><p>人工指定企业 · 字段级可追溯 · 分诊留桩</p></header><main><section><p>Deliverable: {html.escape(markdown_result["deliverable_status"])} · Contract execution: {"passed" if markdown_result["execution_passed"] else "failed"} · Human-input eligible: {markdown_result["delivery_eligible"]} · Execution completed: {markdown_result["completed_execution_count"]}/5 · Delivery completed: {markdown_result["completed_case_count"]}/5</p><p>Run {markdown_result["run_number"]} · {html.escape(run_reference)}</p><p>内部受限资料；未经单独授权和人工审核不得公开。不构成投资、信用、综合风险、ESG 或 ARL 评级。</p></section>{"".join(sections)}<section><h2>高频出处缺口与补问建议</h2><ul>{frequent}</ul></section><section><h2>通用性问题及修法</h2><ul>{generalization}</ul></section><section><h2>输入修订</h2><ul>{input_corrections}</ul></section><section><h2>财务可追溯</h2><p>{html.escape(financial["text_zh"])}</p><p>Checks: {financial["passed_checks"]}/{financial["total_checks"]} · Traceability: {financial["traceability_percent"]}</p></section></main></body></html>"""


def _run_qa_registry_unlocked(
    registry_path: str | Path,
    output_dir: str | Path,
    *,
    project_root: str | Path,
    runtime_snapshot: _RuntimeInputSnapshot,
    allow_contract_test: bool = False,
    change_note: str = "",
    change_note_zh: str = "",
) -> dict[str, Any]:
    """Run five externally selected cases, stopping at the first failure.

    ``contract_test`` is available only through the explicit library flag. It
    exercises orchestration but can never produce a delivery pass. A real
    ``qa_delivery`` additionally requires immutable input hashes, an external
    human selection attestation, and per-field human profile ground truth.
    """
    registry_path = Path(registry_path).resolve()
    output_dir = Path(output_dir).resolve()
    project_root = Path(project_root).resolve()
    if runtime_snapshot.registry_path != registry_path:
        raise ValueError("Runtime input snapshot belongs to a different QA registry")
    _verify_runtime_input_snapshot(runtime_snapshot)
    registry = runtime_snapshot.registry
    registry_snapshot_sha256 = runtime_snapshot.registry_sha256
    registry_schema_errors = _schema_errors(
        registry,
        project_root / "schemas" / "qa-loop.schema.json",
    )
    if registry_schema_errors:
        raise ValueError("Invalid QA registry: " + "; ".join(registry_schema_errors))
    _validate_registry(registry)
    _reject_company_specific_qa_rules(registry, project_root)
    starting_runtime_inputs = runtime_snapshot.manifest_rows
    starting_runtime_inputs_sha256 = _canonical_sha256(starting_runtime_inputs)
    starting_input_hashes = {item["label"]: item.get("sha256") for item in starting_runtime_inputs}
    runtime_selection_material = _selection_material_from_runtime_manifest(
        registry, starting_runtime_inputs
    )
    runtime_selection_hash = _canonical_sha256(runtime_selection_material)
    selection_hash, delivery_eligible = _validate_selection_attestation(
        registry,
        registry_path,
        allow_contract_test=allow_contract_test,
        material_digest=runtime_selection_hash,
    )
    if delivery_eligible:
        try:
            output_dir.relative_to(project_root)
        except ValueError:
            pass
        else:
            raise ValueError(
                "qa_delivery output must be outside the project tree so restricted "
                "company evidence cannot enter the repository"
            )
    output_dir.mkdir(parents=True, exist_ok=True)

    history_path = output_dir / HISTORY_FILENAME
    history = _load_history(history_path)
    orphaned_runs = _reconcile_run_storage(output_dir, history)
    rule_digest = _qa_rule_bundle_digest(project_root)
    if rule_digest != IMPORTED_QA_RULE_BUNDLE_DIGEST:
        raise ValueError(
            "The on-disk QA/financial rule bundle differs from the code imported by "
            "this process; start a fresh process before running the loop"
        )
    company_set = [
        {
            "iteration": row["iteration"],
            "id": row["id"],
            "entity_scheme": row["entity_scheme"],
            "entity_id": row["entity_id"],
            "company": row["company"],
        }
        for row in registry["cases"]
    ]
    selection_batch_id = (registry.get("selection_attestation") or {}).get("selection_batch_id")
    selection_attestation_sha256 = (
        _canonical_sha256(registry["selection_attestation"]) if delivery_eligible else None
    )
    previous_run = history["runs"][-1] if history["runs"] else None
    if previous_run and previous_run.get("run_mode") != registry["run_mode"]:
        raise ValueError(
            "contract_test and qa_delivery histories must use separate output directories"
        )
    if previous_run and previous_run.get("company_set") != company_set:
        raise ValueError(
            "An existing QA loop history belongs to a different five-company set; "
            "use a separate output directory"
        )
    if delivery_eligible and previous_run:
        if previous_run.get("selection_digest") != selection_hash:
            raise ValueError(
                "An existing qa_delivery history is bound to different immutable inputs; "
                "use a new output directory and selection batch"
            )
        if previous_run.get("selection_batch_id") != selection_batch_id:
            raise ValueError(
                "An existing qa_delivery history is bound to a different selection batch"
            )
        if previous_run.get("selection_attestation_sha256") != selection_attestation_sha256:
            raise ValueError(
                "An existing qa_delivery history is bound to a different human selection attestation"
            )
    rules_changed = bool(previous_run and previous_run.get("rule_digest") != rule_digest)
    if rules_changed and (not change_note.strip() or not change_note_zh.strip()):
        raise ValueError(
            "A changed QA rule bundle requires bilingual change notes before rerunning regressions"
        )
    prior_execution_passed_ids = {
        row["id"]
        for run in history["runs"]
        for row in run.get("cases", [])
        if row.get("execution_passed") is True
    }
    run_number = len(history["runs"]) + 1
    run_started_at = datetime.now(timezone.utc)
    run_stamp = run_started_at.strftime("%Y%m%dT%H%M%S%fZ")
    run_name = f"{run_number:04d}-{rule_digest[:12]}-{run_stamp}"
    staging_output = output_dir / "runs" / ".staging" / run_name
    final_output = output_dir / "runs" / run_name
    staging_output.mkdir(parents=True, exist_ok=False)

    case_results: list[dict[str, Any]] = []
    for row in registry["cases"]:
        case_path = _resolve_path(row["input"], registry_path.parent)
        expected_case_sha256 = starting_input_hashes[f"case:{row['id']}"]
        case_snapshot_path = runtime_snapshot.files[f"case:{row['id']}"]
        case = _load_object_exact(case_snapshot_path, expected_case_sha256)
        durable_case = _durable_case_view(case)
        case_schema_errors = _schema_errors(
            case,
            project_root / "schemas" / "qa-case.schema.json",
        )
        case_company = case.get("company") or {}
        case_identifier = case_company.get("stable_identifier") or {}
        if str(row["company"]).strip() != str(case_company.get("legal_name", "")).strip():
            case_schema_errors.append(
                "company/legal_name: registry company must exactly match the QA case legal_name"
            )
        if str(row["entity_id"]) != str(case_identifier.get("value", "")):
            case_schema_errors.append(
                "company/stable_identifier: registry entity_id must exactly match the QA case identifier value"
            )
        if str(row["entity_scheme"]) != str(case_identifier.get("scheme", "")):
            case_schema_errors.append(
                "company/stable_identifier: registry entity_scheme must exactly match the QA case identifier scheme"
            )
        case_output = staging_output / f"{row['iteration']:02d}-{row['id']}"
        qa_output = case_output / "qa"
        if case_schema_errors:
            qa_validation = _schema_failure_validation(case, case_schema_errors)
            qa_output.mkdir(parents=True, exist_ok=True)
            case_json = qa_output / "qa_case.json"
            validation_json = qa_output / "qa_validation.json"
            _atomic_write_json(case_json, durable_case)
            _atomic_write_json(validation_json, qa_validation)
            qa_artifacts = {
                "case_json": str(case_json.resolve()),
                "validation_json": str(validation_json.resolve()),
            }
        else:
            qa_validation = validate_qa_case(case)
            qa_artifacts = {}
        profile_review = (
            _profile_review_result(
                row,
                qa_validation,
                registry_path=registry_path,
                project_root=project_root,
                delivery_eligible=delivery_eligible,
                review_snapshot_path=runtime_snapshot.files.get(
                    f"profile_ground_truth:{row['id']}"
                ),
            )
            if not case_schema_errors and qa_validation["passed"]
            else {
                "status": "not_run_due_to_qa_failure",
                "contract_check_passed": False,
                "passed": False,
                "delivery_eligible": delivery_eligible,
                "errors": ["Fix the QA/schema failure before profile review."],
            }
        )
        external_gate_passed = bool(delivery_eligible and profile_review["passed"])
        qa_validation["delivery_eligible"] = external_gate_passed
        qa_validation["human_profile_review_required_for_delivery"] = not external_gate_passed
        qa_validation["delivery_gate"] = {
            "passed": external_gate_passed,
            "status": (
                "human_profile_review_passed" if external_gate_passed else profile_review["status"]
            ),
            "delivery_eligible": delivery_eligible,
        }
        if not external_gate_passed:
            qa_validation["triage"]["eligible"] = False
            error_codes = ["delivery_gate_not_passed"]
            if delivery_eligible and not profile_review["passed"]:
                error_codes.append("profile_ground_truth_failure")
            qa_validation["triage"]["upstream_validation"] = {
                "passed": False,
                "error_codes": error_codes,
            }
            qa_validation["triage"]["routes"] = [
                {**route, "selected": False, "reasons": []}
                for route in qa_validation["triage"]["routes"]
            ]
            qa_validation["triage"]["guardrail"] = (
                "Routing blocked until the external human profile-review gate passes; "
                "contract fixtures never become delivery inputs."
            )
        if not case_schema_errors:
            qa_artifacts = write_qa_artifacts(
                durable_case,
                qa_output,
                validation_result=qa_validation,
            )
        financial = (
            _run_financial_evidence(
                case,
                case_id=row["id"],
                output_dir=case_output,
                project_root=project_root,
                runtime_snapshot=runtime_snapshot,
            )
            if (
                not case_schema_errors
                and qa_validation["passed"]
                and profile_review["contract_check_passed"]
            )
            else {
                "status": "not_run_due_to_upstream_failure",
                "passed": False,
                "reason": (
                    "Fix the QA/schema/profile-review failure before running financial evidence."
                ),
            }
        )
        financial_contract_check_passed = financial.get("passed") is True
        financial["contract_check_passed"] = financial_contract_check_passed
        financial["delivery_eligible"] = delivery_eligible
        financial["passed"] = bool(financial_contract_check_passed and delivery_eligible)
        financial["delivery_status"] = (
            "passed"
            if financial["passed"]
            else "contract_fixture_only"
            if financial_contract_check_passed and not delivery_eligible
            else "failed"
        )
        case_execution_passed = bool(
            not case_schema_errors
            and qa_validation["passed"]
            and profile_review["contract_check_passed"]
            and financial_contract_check_passed
        )
        case_delivery_passed = bool(case_execution_passed and delivery_eligible)
        qa_error_codes = [
            str(item.get("code"))
            for item in qa_validation["errors"]
            if isinstance(item, dict) and item.get("code")
        ]
        failure_codes = list(qa_error_codes)
        if (
            delivery_eligible
            and not profile_review["contract_check_passed"]
            and qa_validation["passed"]
        ):
            failure_codes.append("profile_ground_truth_failure")
        if profile_review["contract_check_passed"] and not financial_contract_check_passed:
            failure_codes.append(f"financial:{financial['status']}")
        input_material = _input_bundle_material(
            row,
            case,
            case_path,
            case_sha256=expected_case_sha256,
        )
        case_result = {
            "iteration": row["iteration"],
            "id": row["id"],
            "entity_scheme": row["entity_scheme"],
            "entity_id": row["entity_id"],
            "company": row["company"],
            "selection_origin": row["selection_origin"],
            "execution_passed": case_execution_passed,
            "passed": case_delivery_passed,
            "case_schema_errors": case_schema_errors,
            "qa_artifacts": qa_artifacts,
            "profile": _profile_values(qa_validation),
            "triage": qa_validation["triage"]["routes"],
            "gaps": qa_validation["profile"]["gap_queue"],
            "qa_errors": qa_validation["errors"],
            "profile_review": profile_review,
            "financial": financial,
            "failure_codes": failure_codes,
            "regression_of_prior_execution_pass": row["id"] in prior_execution_passed_ids,
            "input_material": input_material,
            "input_bundle_sha256": _canonical_sha256(input_material),
            "input_sha256": input_material["case_sha256"],
        }
        case_results.append(case_result)
        if not case_execution_passed:
            break

    case_results = _replace_path_prefix(case_results, staging_output, final_output)
    financial_rows = [item["financial"] for item in case_results]
    financial_audits = [item for item in financial_rows if item["status"] in {"passed", "failed"}]
    financial_passed_checks = sum(
        int(item.get("extraction_evaluation", {}).get("passed_checks", 0))
        + int(item.get("card_evaluation", {}).get("passed_checks", 0))
        for item in financial_audits
    )
    financial_total_checks = sum(
        int(item.get("extraction_evaluation", {}).get("total_checks", 0))
        + int(item.get("card_evaluation", {}).get("total_checks", 0))
        for item in financial_audits
    )
    financial_contract_checks_passed = bool(
        len(case_results) == 5 and all(item.get("contract_check_passed") for item in financial_rows)
    )
    financial_evidence_exercised = bool(financial_audits)
    actual_financial_failure = any(item.get("status") == "failed" for item in financial_rows)
    if actual_financial_failure:
        financial_status = "financial_ground_truth_failure"
        financial_text = (
            "At least one supplied annual-report case failed financial ground truth "
            "or offline execution checks."
        )
        financial_text_zh = "至少一个提供年报的案例未通过财务 ground truth 或离线执行检查。"
    elif not financial_contract_checks_passed:
        financial_status = "financial_not_run_or_contract_failure"
        financial_text = (
            "Financial evidence was not run for every case because an upstream QA/profile "
            "gate or financial input contract failed."
        )
        financial_text_zh = "并非每个案例都运行了财务证据；上游 QA/画像闸门或财务输入合同存在失败。"
    elif not financial_evidence_exercised:
        financial_status = "financial_not_exercised"
        financial_text = (
            "Every case used a human-approved profile-only waiver. No annual-report case "
            "exercised the validated financial core, so this batch cannot claim financial "
            "traceability or become a complete delivery."
        )
        financial_text_zh = (
            "所有案例均使用人工批准的画像模式 waiver；没有年报案例实际运行已验证财务内核，"
            "因此本批次不能声称财务可追溯，也不能成为完整交付。"
        )
    else:
        financial_status = "all_supplied_financial_cases_traceable"
        financial_text = (
            "Every supplied annual-report case passed extraction/card ground truth with "
            "zero model and network calls; other cases, if any, used approved profile-only waivers."
        )
        financial_text_zh = (
            "所有提供年报的案例均通过抽取与卡片 ground truth，模型和网络调用均为零；"
            "其余案例（如有）使用人工批准的画像模式 waiver。"
        )
    execution_passed = bool(
        len(case_results) == 5 and all(item["execution_passed"] for item in case_results)
    )
    delivery_passed = bool(
        execution_passed and delivery_eligible and financial_evidence_exercised
    )
    regression_evidence = _build_regression_evidence(
        history,
        case_results,
        rules_changed=rules_changed,
        current_rule_digest=rule_digest,
    )
    draft_history_entry = {
        "run_number": run_number,
        "started_at": run_started_at.isoformat(),
        "run_mode": registry["run_mode"],
        "delivery_eligible": delivery_eligible,
        "selection_batch_id": selection_batch_id,
        "selection_digest": selection_hash,
        "selection_attestation_sha256": selection_attestation_sha256,
        "company_set": company_set,
        "registry_sha256": registry_snapshot_sha256,
        "runtime_input_manifest": starting_runtime_inputs,
        "runtime_input_tree_sha256": starting_runtime_inputs_sha256,
        "runtime_input_snapshot": {
            "content_addressed": True,
            "volatile": True,
            "retained": False,
        },
        "rule_version": QA_RULE_VERSION,
        "rule_digest": rule_digest,
        "rules_changed": rules_changed,
        "change_note": change_note.strip() if rules_changed else "",
        "change_note_zh": change_note_zh.strip() if rules_changed else "",
        "execution_passed": execution_passed,
        "delivery_passed": delivery_passed,
        "regression_evidence": regression_evidence,
        "cases": [
            {
                "iteration": item["iteration"],
                "id": item["id"],
                "entity_scheme": item["entity_scheme"],
                "entity_id": item["entity_id"],
                "input_sha256": item["input_sha256"],
                "input_bundle_sha256": item["input_bundle_sha256"],
                "execution_passed": item["execution_passed"],
                "delivery_passed": item["passed"],
                "failure_codes": item["failure_codes"],
                "gap_fields": sorted(gap["field"] for gap in item["gaps"]),
                "profile_review_status": item["profile_review"]["status"],
                "financial_status": item["financial"]["status"],
                "regression_of_prior_execution_pass": item["regression_of_prior_execution_pass"],
            }
            for item in case_results
        ],
    }
    run_content_id = _canonical_sha256(draft_history_entry)
    draft_history_entry["run_content_id"] = run_content_id
    analysis_history = deepcopy(history)
    analysis_history["runs"].append(draft_history_entry)

    generalization_issues: list[dict[str, Any]] = []
    input_corrections: list[dict[str, Any]] = []
    for index, run in enumerate(analysis_history["runs"]):
        if index == 0:
            continue
        for passed_row in sorted(
            (item for item in run.get("cases", []) if item.get("execution_passed")),
            key=lambda item: item["id"],
        ):
            case_id = passed_row["id"]
            prior_failure: dict[str, Any] | None = None
            prior_failure_run: dict[str, Any] | None = None
            for prior_run in reversed(analysis_history["runs"][:index]):
                prior_row = next(
                    (item for item in prior_run.get("cases", []) if item.get("id") == case_id),
                    None,
                )
                if prior_row is None:
                    continue
                if not prior_row.get("execution_passed"):
                    prior_failure = prior_row
                    prior_failure_run = prior_run
                break
            if prior_failure is None or prior_failure_run is None:
                continue
            if prior_failure.get("input_bundle_sha256") != passed_row.get("input_bundle_sha256"):
                input_corrections.append(
                    {
                        "case_id": case_id,
                        "failure_codes": prior_failure.get("failure_codes", []),
                        "from_input_bundle_sha256": prior_failure.get("input_bundle_sha256"),
                        "to_input_bundle_sha256": passed_row.get("input_bundle_sha256"),
                        "classification": "input_changed_not_general_rule_fix",
                    }
                )
                continue
            if not run.get("rules_changed") or not run.get("delivery_eligible"):
                continue
            run_regression = run.get("regression_evidence") or {
                "complete": False,
                "status": "not_recorded",
            }
            generalization_issues.append(
                {
                    "case_id": case_id,
                    "failure_codes": prior_failure.get("failure_codes", []),
                    "from_rule_digest": prior_failure_run.get("rule_digest"),
                    "to_rule_digest": run.get("rule_digest"),
                    "general_fix": run.get("change_note"),
                    "general_fix_zh": run.get("change_note_zh"),
                    "regression_complete": run_regression["complete"],
                    "regression_status": run_regression["status"],
                    "regressed_prior_passes": [
                        item["id"]
                        for item in run.get("cases", [])
                        if item.get("regression_of_prior_execution_pass")
                        and item.get("execution_passed")
                    ],
                }
            )

    gap_counter: Counter[str] = Counter()
    for row in registry["cases"]:
        historical_rows = _history_case_rows(analysis_history, row["id"])
        gap_fields = {field for item in historical_rows for field in item.get("gap_fields", [])}
        for field in gap_fields:
            gap_counter[field] += 1
        initial_failed = next(
            (item for item in historical_rows if not item.get("execution_passed")),
            None,
        )
        current = next(
            (item for item in case_results if item["id"] == row["id"]),
            None,
        )
        if current is None:
            continue
        relevant_fixes = [issue for issue in generalization_issues if issue["case_id"] == row["id"]]
        relevant_corrections = [
            issue for issue in input_corrections if issue["case_id"] == row["id"]
        ]
        current["iteration_log"] = {
            "attempt_count": len(historical_rows),
            "initial_failure": (
                ", ".join(initial_failed.get("failure_codes", []))
                if initial_failed
                else "none recorded"
            ),
            "initial_failure_zh": (
                "、".join(initial_failed.get("failure_codes", []))
                if initial_failed
                else "无机器记录的初始失败"
            ),
            "general_fix": (
                relevant_fixes[-1]["general_fix"] if relevant_fixes else "none recorded"
            ),
            "general_fix_zh": (
                relevant_fixes[-1]["general_fix_zh"] if relevant_fixes else "无机器记录的通用修复"
            ),
            "input_correction": bool(relevant_corrections),
            "initial_gap_fields": (initial_failed.get("gap_fields", []) if initial_failed else []),
            "residual_risk": (
                "Exact quote relevance and company selection remain human-reviewed boundaries."
            ),
            "residual_risk_zh": "精确引文的相关性与企业选择仍是人工审核边界。",
            "run_content_id": run_content_id,
        }

    result = {
        "schema_version": "1.0.0",
        "passed": delivery_passed,
        "execution_passed": execution_passed,
        "delivery_eligible": delivery_eligible,
        "deliverable_status": (
            "passed"
            if delivery_passed
            else "contract_fixture_only"
            if execution_passed and not delivery_eligible
            else "failed"
        ),
        "run_mode": registry["run_mode"],
        "selection_policy": "human_supplied_only",
        "selection_digest": selection_hash,
        "human_attestation_assurance": {
            "status": (
                "unsigned_claim_only"
                if delivery_eligible
                else "not_applicable_contract_fixture"
            ),
            "cryptographic_identity_verified": False,
            "meaning": (
                "Hashes bind the declared selection material but do not verify the "
                "identity of a claimed human reviewer."
            ),
        },
        "rule_version": QA_RULE_VERSION,
        "rule_digest": rule_digest,
        "run_number": run_number,
        "run_content_id": run_content_id,
        "run_hash": None,
        "data_classification": "internal_restricted",
        "publication_authorized": False,
        "human_publication_review_required": True,
        "runtime_input_snapshot": {
            "content_addressed": True,
            "volatile": True,
            "retained": False,
            "input_tree_sha256": starting_runtime_inputs_sha256,
        },
        "completed_execution_count": sum(item["execution_passed"] for item in case_results),
        "completed_case_count": sum(item["passed"] for item in case_results),
        "cases": case_results,
        "frequent_gap_fields": [
            {
                "field": field,
                "count": count,
                "recommended_question": QA_GAP_QUESTION_RECOMMENDATIONS[field],
            }
            for field, count in sorted(gap_counter.items(), key=lambda item: (-item[1], item[0]))
        ],
        "generalization_issues": generalization_issues,
        "regression_evidence": regression_evidence,
        "input_corrections": input_corrections,
        "financial_summary": {
            "status": financial_status,
            "passed": bool(
                financial_contract_checks_passed
                and delivery_eligible
                and financial_evidence_exercised
            ),
            "contract_checks_passed": financial_contract_checks_passed,
            "delivery_eligible": delivery_eligible,
            "audited_case_count": len(financial_audits),
            "profile_only_case_count": sum(
                item.get("status") == "profile_only_waived" for item in financial_rows
            ),
            "skipped_case_count": sum(
                item.get("status") == "not_run_due_to_upstream_failure" for item in financial_rows
            ),
            "passed_checks": financial_passed_checks,
            "total_checks": financial_total_checks,
            "traceability_percent": (
                round(financial_passed_checks / financial_total_checks * 100, 2)
                if financial_total_checks
                else None
            ),
            "text": financial_text,
            "text_zh": financial_text_zh,
        },
        "orphaned_runs_quarantined": orphaned_runs,
        "loop_policy": {
            "stop_on_first_execution_failure": True,
            "general_rules_only": True,
            "company_name_branches_forbidden": True,
            "rerun_registry_after_every_rule_change": True,
            "observed_regression_evidence_recorded": True,
            "history_hash_chain": True,
            "artifact_tree_hash": True,
            "immutable_delivery_selection": True,
            "contract_test_never_counts_as_delivery": True,
            "audited_financial_case_required_for_delivery": True,
            "volatile_content_addressed_input_snapshot": True,
            "raw_financial_files_excluded_from_run_artifacts": True,
        },
    }
    canonical_paths = {
        "report_json": staging_output / "qa-loop-report.json",
        "report_markdown": staging_output / "qa-loop-report.md",
        "report_html": staging_output / "qa-loop-report.html",
    }
    _atomic_write_json(canonical_paths["report_json"], result)
    _atomic_write_text(canonical_paths["report_markdown"], _markdown_report(result))
    _atomic_write_text(canonical_paths["report_html"], _html_report(result))
    ending_runtime_inputs = _runtime_input_manifest(
        registry,
        registry_path,
        project_root=project_root,
    )
    if ending_runtime_inputs != starting_runtime_inputs:
        raise ValueError("QA loop inputs changed during execution; no history entry was committed")
    if _qa_rule_bundle_digest(project_root) != rule_digest:
        raise ValueError(
            "QA/financial rule files changed during execution; no history entry was committed"
        )
    _verify_runtime_input_snapshot(runtime_snapshot)
    _reject_runtime_snapshot_path_leaks(staging_output, runtime_snapshot)
    snapshot_root = runtime_snapshot.root
    runtime_snapshot.cleanup()
    if snapshot_root.exists():
        raise ValueError(
            "Volatile runtime input snapshot cleanup failed; no history entry was committed"
        )
    artifact_manifest = _artifact_tree_manifest(staging_output)
    artifact_tree_sha256 = _canonical_sha256(artifact_manifest)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    staging_output.replace(final_output)
    committed_history_entry = _append_history(
        history_path,
        history,
        {
            **draft_history_entry,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "run_output": final_output.relative_to(output_dir).as_posix(),
            "artifact_manifest": artifact_manifest,
            "artifact_tree_sha256": artifact_tree_sha256,
            "orphaned_runs_quarantined": orphaned_runs,
        },
    )
    result["run_hash"] = committed_history_entry["run_hash"]
    result["artifact_tree_sha256"] = artifact_tree_sha256
    final_paths = {
        key: final_output / path.relative_to(staging_output)
        for key, path in canonical_paths.items()
    }
    latest_paths = {
        "latest_report_json": output_dir / "qa-loop-report.json",
        "latest_report_markdown": output_dir / "qa-loop-report.md",
        "latest_report_html": output_dir / "qa-loop-report.html",
    }
    result["artifacts"] = {
        **{key: str(path) for key, path in final_paths.items()},
        **{key: str(path) for key, path in latest_paths.items()},
        "history_json": str(history_path),
        "run_output": str(final_output),
    }
    latest_errors: list[str] = []
    for key, source_key in (
        ("latest_report_markdown", "report_markdown"),
        ("latest_report_html", "report_html"),
    ):
        try:
            _atomic_write_text(
                latest_paths[key],
                final_paths[source_key].read_text(encoding="utf-8"),
            )
        except OSError as exc:
            latest_errors.append(f"{key}: {exc}")
    result["latest_alias_status"] = "partial_failure" if latest_errors else "updated"
    result["latest_alias_errors"] = latest_errors
    try:
        _atomic_write_json(latest_paths["latest_report_json"], result)
    except OSError as exc:
        latest_errors.append(f"latest_report_json: {exc}")
        result["latest_alias_status"] = "partial_failure"
    return result


def run_qa_registry(
    registry_path: str | Path,
    output_dir: str | Path,
    *,
    project_root: str | Path,
    allow_contract_test: bool = False,
    change_note: str = "",
    change_note_zh: str = "",
) -> dict[str, Any]:
    """Run one serialized five-company QA batch and fail closed on stale locks."""
    resolved_output = Path(output_dir).resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    lock_path = resolved_output / LOCK_FILENAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError(
            f"QA loop output is locked by another or interrupted run: {lock_path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
                handle,
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        runtime_snapshot = _prepare_runtime_input_snapshot(
            registry_path,
            project_root=Path(project_root).resolve(),
            output_dir=resolved_output,
        )
        try:
            return _run_qa_registry_unlocked(
                registry_path,
                resolved_output,
                project_root=project_root,
                runtime_snapshot=runtime_snapshot,
                allow_contract_test=allow_contract_test,
                change_note=change_note,
                change_note_zh=change_note_zh,
            )
        finally:
            runtime_snapshot.cleanup()
    finally:
        lock_path.unlink(missing_ok=True)


def preflight_qa_registry(
    registry_path: str | Path,
    *,
    project_root: str | Path,
    intended_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Dry-run a formal delivery in disposable local storage.

    The exact production runner is used, including the volatile input snapshot,
    human-review gates, optional financial audit, evaluators, and stop-first
    semantics. Temporary artifacts and history are removed before returning;
    the intended formal output directory is checked but never created.
    """

    root = Path(project_root).resolve()
    intended_output: Path | None = None
    if intended_output_dir is not None:
        intended_output = Path(intended_output_dir).resolve()
        try:
            intended_output.relative_to(root)
        except ValueError:
            pass
        else:
            raise ValueError(
                "The intended qa_delivery output must be outside the project tree"
            )
    with tempfile.TemporaryDirectory(prefix="cleantech-qa-preflight-") as temporary:
        disposable_output = Path(temporary) / "run"
        result = run_qa_registry(
            registry_path,
            disposable_output,
            project_root=root,
        )
        case_rows = [
            {
                "iteration": item["iteration"],
                "id": item["id"],
                "company": item["company"],
                "execution_passed": item["execution_passed"],
                "delivery_passed": item["passed"],
                "failure_codes": item["failure_codes"],
                "gap_fields": sorted(gap["field"] for gap in item["gaps"]),
                "profile_review_status": item["profile_review"]["status"],
                "financial_status": item["financial"]["status"],
            }
            for item in result["cases"]
        ]
        return {
            "schema_version": "1.0.0",
            "mode": "qa_delivery_preflight",
            "passed": result["passed"],
            "execution_passed": result["execution_passed"],
            "delivery_eligible": result["delivery_eligible"],
            "deliverable_status": result["deliverable_status"],
            "completed_execution_count": result["completed_execution_count"],
            "completed_case_count": result["completed_case_count"],
            "selection_digest": result["selection_digest"],
            "rule_digest": result["rule_digest"],
            "human_attestation_assurance": result[
                "human_attestation_assurance"
            ],
            "regression_evidence": result["regression_evidence"],
            "cases": case_rows,
            "financial_summary": result["financial_summary"],
            "stop_on_first_execution_failure": True,
            "intended_output_checked": intended_output is not None,
            "intended_output_ref": (
                "external-local-output" if intended_output is not None else None
            ),
            "formal_output_created": False,
            "formal_history_created": False,
            "temporary_artifacts_retained": False,
            "warning": (
                "Preflight proves the current packet can pass the deterministic runner. "
                "It does not create a formal run or prove the identity of a claimed human reviewer."
            ),
        }
