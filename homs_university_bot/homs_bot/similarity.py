"""Replaceable similarity. The MVP uses lexical scores, not probabilities or embeddings."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Protocol


def lexical_score(query: str, candidate: str) -> float:
    """Return a similarity score in [0, 1]. Equal texts score 1. This is not a probability."""
    if not query or not candidate:
        return 0.0
    sequence = SequenceMatcher(None, query, candidate).ratio()
    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    union = query_tokens | candidate_tokens
    overlap = query_tokens & candidate_tokens
    jaccard = (len(overlap) / len(union)) if union else 0.0
    coverage = (len(overlap) / len(query_tokens)) if query_tokens else 0.0
    return (0.45 * sequence) + (0.35 * jaccard) + (0.20 * coverage)


class SimilarityIndex(Protocol):
    def score(self, query: str, candidate: str) -> float:
        """Score a normalized query against one normalized variant."""


class LexicalSimilarityIndex:
    """Default matcher. Swap this object when an evaluation shows embeddings help."""

    def score(self, query: str, candidate: str) -> float:
        return lexical_score(query, candidate)


class EmbeddingSimilarityIndex:
    """Extension point only. No model, GPU, or paid API is required for the MVP."""

    def score(self, query: str, candidate: str) -> float:
        raise NotImplementedError("Embeddings are not enabled. Use LexicalSimilarityIndex.")
