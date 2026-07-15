"""Transparent lexical retrieval for candidate evidence passages."""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date

from .models import Candidate, Chunk, Dimension, Source

TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{1,}|[\u3400-\u9fff]{2,}", re.IGNORECASE)
NUMBER_SIGNAL = re.compile(
    r"(?:[$€£¥]\s?\d|\d[\d,]{2,}(?:\.\d+)?|\d(?:[\d,.]*)(?:\s?%|\s?(?:million|billion|mw|mwh|gw|gwh|years?)))",
    re.IGNORECASE,
)
EVIDENCE_WORDS = {
    "reported",
    "recognized",
    "measured",
    "tested",
    "certified",
    "contracted",
    "completed",
    "commissioned",
    "filed",
    "recorded",
    "报告",
    "确认",
    "测试",
    "认证",
    "签署",
    "投运",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "were",
    "with",
    "year",
}

SOURCE_QUALITY = {
    "audited_financial": "high",
    "regulatory_filing": "high",
    "government": "high",
    "regulator": "high",
    "standard": "high",
    "independent_research": "medium",
    "company_report": "medium",
    "investor_presentation": "medium",
    "product_documentation": "medium",
    "press_release": "context",
    "media": "context",
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOPWORDS]


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _freshness(published: str | None, as_of: str) -> str:
    if not published:
        return "undated"
    try:
        published_date = date.fromisoformat(published[:10])
        as_of_date = date.fromisoformat(as_of[:10])
    except ValueError:
        return "unknown"
    age_days = (as_of_date - published_date).days
    if age_days < -31:
        return "future-dated"
    if age_days <= 730:
        return "current"
    if age_days <= 1826:
        return "aging"
    return "stale"


def _excerpt(text: str, needles: tuple[str, ...], limit: int = 420) -> str:
    flat = _normalized(text)
    positions: list[int] = []
    for needle in needles:
        pattern = re.escape(needle.lower()).replace(r"\ ", r"\s*")
        match = re.search(pattern, flat)
        if match:
            positions.append(match.start())
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(flat), start + limit)
    snippet = flat[start:end].strip()
    if start:
        snippet = "…" + snippet
    if end < len(flat):
        snippet += "…"
    return snippet


class EvidenceRetriever:
    def __init__(self, chunks: list[Chunk], sources: list[Source], as_of: str) -> None:
        self.chunks = chunks
        self.sources = {source.id: source for source in sources}
        self.as_of = as_of
        self.doc_tokens = [tokenize(chunk.text) for chunk in chunks]
        self.statement_scope = self._statement_scopes(chunks)
        self.doc_freq: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            self.doc_freq.update(set(tokens))
        self.avg_length = sum(len(tokens) for tokens in self.doc_tokens) / max(len(chunks), 1)

    @staticmethod
    def _statement_scopes(chunks: list[Chunk]) -> list[str]:
        scopes: list[str] = []
        current = "unknown"
        consolidated_markers = (
            "consolidated income statement",
            "consolidated statement of cash flows",
            "consolidated cash flow statement",
            "consolidated balance sheet",
        )
        parent_markers = (
            "income statement of parent company",
            "statement of cash flows of parent company",
            "balance sheet of parent company",
        )
        for chunk in chunks:
            text = _normalized(chunk.text)
            compact = re.sub(r"\s+", "", text)
            consolidated_positions = [
                compact.find(re.sub(r"\s+", "", marker))
                for marker in consolidated_markers
                if re.sub(r"\s+", "", marker) in compact
            ]
            parent_positions = [
                compact.find(re.sub(r"\s+", "", marker))
                for marker in parent_markers
                if re.sub(r"\s+", "", marker) in compact
            ]
            if consolidated_positions and parent_positions:
                scopes.append("mixed")
                current = (
                    "consolidated"
                    if max(consolidated_positions) > max(parent_positions)
                    else "parent_company"
                )
            elif consolidated_positions:
                current = "consolidated"
                scopes.append(current)
            elif parent_positions:
                crossing_from_consolidated = (
                    current == "consolidated" and min(parent_positions) > 400
                )
                current = "parent_company"
                scopes.append("mixed" if crossing_from_consolidated else current)
            else:
                scopes.append(current)
        return scopes

    def _bm25(self, query: set[str], index: int) -> float:
        tokens = self.doc_tokens[index]
        counts = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in query:
            frequency = counts[term]
            if not frequency:
                continue
            documents_with_term = self.doc_freq[term]
            idf = math.log(
                1 + (len(self.chunks) - documents_with_term + 0.5) / (documents_with_term + 0.5)
            )
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * length / max(self.avg_length, 1))
            score += idf * (frequency * 2.5) / denominator
        return score

    def candidates_for(
        self, dimension: Dimension, top_k: int = 3, minimum_raw_score: float = 1.25
    ) -> tuple[Candidate, ...]:
        query = set(tokenize(" ".join(dimension.query_terms + dimension.cues)))
        ranked: list[tuple[float, Candidate]] = []
        for index, chunk in enumerate(self.chunks):
            source = self.sources[chunk.source_id]
            if source.role != "subject":
                continue
            if (
                dimension.category == "Financial & Bankability"
                and self.statement_scope[index] == "parent_company"
            ):
                continue
            normalized = _normalized(chunk.text)
            compact = re.sub(r"\s+", "", normalized)
            cue_hits = tuple(
                cue
                for cue in dimension.cues
                if cue.lower() in normalized or re.sub(r"\s+", "", cue.lower()) in compact
            )
            token_hits = query.intersection(self.doc_tokens[index])
            if not cue_hits and len(token_hits) < 2:
                continue
            evidence_signal = bool(NUMBER_SIGNAL.search(chunk.text)) or bool(
                EVIDENCE_WORDS.intersection(self.doc_tokens[index])
            )
            statement_bonus = 0.0
            if dimension.category == "Financial & Bankability":
                if self.statement_scope[index] == "consolidated":
                    statement_bonus = 16.0
                elif self.statement_scope[index] == "mixed":
                    statement_bonus = 3.0
            raw = (
                self._bm25(query, index)
                + 2.2 * len(cue_hits)
                + (0.65 if evidence_signal else 0)
                + statement_bonus
            )
            if raw < minimum_raw_score:
                continue
            if cue_hits and evidence_signal:
                directness = "high"
            elif cue_hits or len(token_hits) >= 4:
                directness = "medium"
            else:
                directness = "low"
            relevance = round(100.0 * (1.0 - math.exp(-raw / 12.0)), 1)
            candidate = Candidate(
                dimension_id=dimension.id,
                source_id=source.id,
                source_title=source.title,
                source_url=source.url,
                locator=chunk.locator,
                excerpt=_excerpt(chunk.text, cue_hits or tuple(sorted(token_hits))),
                relevance=relevance,
                directness=directness,
                source_quality=SOURCE_QUALITY.get(source.kind, "unknown"),
                freshness=_freshness(source.published, self.as_of),
                matched_cues=cue_hits or tuple(sorted(token_hits)[:8]),
            )
            ranked.append((raw, candidate))
        ranked.sort(key=lambda item: (-item[0], item[1].source_id, item[1].locator))
        return tuple(candidate for _, candidate in ranked[:top_k])
