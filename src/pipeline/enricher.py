"""Enrichment pipeline for post-scoring job enhancement.

Defines the Enricher protocol and a no-op default implementation.
Future enrichers (AI summary, semantic re-scoring, relevance explanation)
implement the same interface.

Hook point: after dedup, before notification in src/main.py.
"""
from typing import Protocol, runtime_checkable

from src.collectors.base import JobData
from src.matching.keyword_matcher import MatchResult


@runtime_checkable
class Enricher(Protocol):
    """Protocol for job enrichment pipeline stages."""

    def enrich(self, job: JobData, match: MatchResult) -> tuple[JobData, MatchResult]:
        """Enrich a job and its match result.

        Returns the (possibly modified) job and match result.
        """
        ...


class NoOpEnricher:
    """Default enricher that passes data through unchanged."""

    def enrich(self, job: JobData, match: MatchResult) -> tuple[JobData, MatchResult]:
        return job, match
