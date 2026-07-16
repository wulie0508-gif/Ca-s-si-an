"""Load manifest-backed public documents into traceable text chunks."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .identity import resolve_entity_identity
from .models import Chunk, Source


class ManifestError(ValueError):
    """Raised when an audit manifest is incomplete or inconsistent."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden = 0
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._hidden:
            self._hidden -= 1

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if not self._hidden and text:
            self.blocks.append(text)


def load_manifest(path: str | Path) -> tuple[dict[str, Any], list[Source], Path]:
    manifest_path = Path(path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read manifest {manifest_path}: {exc}") from exc

    required = {"subject", "assessment", "sources"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ManifestError(f"Manifest missing required keys: {', '.join(missing)}")
    if not isinstance(manifest["sources"], list) or not manifest["sources"]:
        raise ManifestError("Manifest 'sources' must be a non-empty list")

    source_ids: set[str] = set()
    sources: list[Source] = []
    for index, raw in enumerate(manifest["sources"], start=1):
        for key in ("id", "path", "title", "url", "publisher", "kind"):
            if not raw.get(key):
                raise ManifestError(f"Source {index} missing '{key}'")
        if raw["id"] in source_ids:
            raise ManifestError(f"Duplicate source id: {raw['id']}")
        role = raw.get("role", "subject")
        if role not in {"subject", "benchmark", "auxiliary", "identity"}:
            raise ManifestError(f"Source {index} has unsupported role '{role}'")
        source_ids.add(raw["id"])
        source_path = (manifest_path.parent / raw["path"]).resolve()
        if not source_path.is_file():
            raise ManifestError(f"Source file not found: {source_path}")
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        sources.append(
            Source(
                id=raw["id"],
                path=str(source_path),
                title=raw["title"],
                url=raw["url"],
                publisher=raw["publisher"],
                published=raw.get("published"),
                kind=raw["kind"],
                role=role,
                sha256=digest,
            )
        )
    try:
        resolve_entity_identity(manifest)
    except ValueError as exc:
        raise ManifestError(f"Invalid subject identity: {exc}") from exc
    return manifest, sources, manifest_path


def _paragraphs_from_text(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []
    buffer: list[str] = []
    start = 1
    for index, line in enumerate(lines, start=1):
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            if not buffer:
                start = index
            buffer.append(cleaned)
        elif buffer:
            blocks.append((" ".join(buffer), f"lines {start}-{index - 1}"))
            buffer = []
    if buffer:
        blocks.append((" ".join(buffer), f"lines {start}-{len(lines)}"))
    return blocks


def _read_blocks(path: Path) -> list[tuple[str, str]]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json"}:
        return _paragraphs_from_text(path.read_text(encoding="utf-8", errors="replace"))
    if suffix in {".html", ".htm"}:
        parser = _VisibleTextParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return [(block, f"text block {index}") for index, block in enumerate(parser.blocks, 1)]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ManifestError(
                "PDF input requires the optional dependency: pip install 'cleantech-finance[pdf]'"
            ) from exc
        blocks: list[tuple[str, str]] = []
        for page_number, page in enumerate(PdfReader(str(path)).pages, start=1):
            text = page.extract_text() or ""
            for paragraph, _ in _paragraphs_from_text(text):
                blocks.append((paragraph, f"page {page_number}"))
        return blocks
    raise ManifestError(f"Unsupported source format '{suffix}' for {path}")


def _pack_blocks(
    blocks: Iterable[tuple[str, str]], target_chars: int = 1100, overlap_blocks: int = 1
) -> list[tuple[str, str]]:
    clean = [(text, locator) for text, locator in blocks if len(text.strip()) >= 30]
    section_markers = (
        "consolidated income statement",
        "consolidated statement of operations",
        "consolidated statements of operations",
        "consolidated statement of cash flows",
        "consolidated statements of cash flows",
        "consolidated cash flow statement",
        "consolidated balance sheet",
        "consolidated balance sheets",
        "income statement of parent company",
        "statement of cash flows of parent company",
        "balance sheet of parent company",
    )

    def starts_statement(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in section_markers)

    chunks: list[tuple[str, str]] = []
    index = 0
    while index < len(clean):
        selected: list[tuple[str, str]] = []
        size = 0
        cursor = index
        while cursor < len(clean) and (size < target_chars or not selected):
            if selected and starts_statement(clean[cursor][0]):
                break
            selected.append(clean[cursor])
            size += len(clean[cursor][0])
            cursor += 1
            if starts_statement(selected[-1][0]):
                break
        text = "\n".join(block[0] for block in selected)
        locators = [block[1] for block in selected]
        locator = locators[0] if len(set(locators)) == 1 else f"{locators[0]} to {locators[-1]}"
        chunks.append((text, locator))
        next_index = cursor - overlap_blocks
        index = next_index if next_index > index else cursor
    return chunks


def ingest_sources(sources: list[Source]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for source in sources:
        if source.role in {"auxiliary", "identity"}:
            continue
        packed = _pack_blocks(_read_blocks(Path(source.path)))
        for ordinal, (text, locator) in enumerate(packed, start=1):
            chunks.append(
                Chunk(
                    id=f"{source.id}:{ordinal}",
                    source_id=source.id,
                    text=text,
                    locator=locator,
                    ordinal=ordinal,
                )
            )
    if not chunks:
        raise ManifestError("No usable text chunks were extracted from the sources")
    return chunks
