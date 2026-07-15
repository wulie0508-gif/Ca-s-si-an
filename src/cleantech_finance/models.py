"""Typed records shared by the audit pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Dimension:
    id: str
    category: str
    name: str
    objective: str
    cues: tuple[str, ...]
    query_terms: tuple[str, ...]
    review_questions: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    id: str
    path: str
    title: str
    url: str
    publisher: str
    published: str | None
    kind: str
    role: str = "subject"
    sha256: str = ""


@dataclass(frozen=True)
class Chunk:
    id: str
    source_id: str
    text: str
    locator: str
    ordinal: int


@dataclass(frozen=True)
class Candidate:
    dimension_id: str
    source_id: str
    source_title: str
    source_url: str
    locator: str
    excerpt: str
    relevance: float
    directness: str
    source_quality: str
    freshness: str
    matched_cues: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DimensionResult:
    id: str
    category: str
    name: str
    objective: str
    status: str
    candidates: tuple[Candidate, ...]
    review_questions: tuple[str, ...]
    review_reason: str
    human_rating: None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
