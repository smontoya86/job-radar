"""Scorer protocol for pluggable scoring engines.

Defines the interface that all scoring implementations must satisfy.
KeywordMatcher is the heuristic implementation; future AI/hybrid
scorers will implement the same protocol.
"""
from typing import Protocol, runtime_checkable

from src.collectors.base import JobData
from src.matching.keyword_matcher import MatchResult


@runtime_checkable
class Scorer(Protocol):
    """Protocol for job scoring engines.

    Any class implementing this protocol can be used as a drop-in
    replacement for the heuristic KeywordMatcher.
    """

    def score(self, job: JobData) -> MatchResult:
        """Score a single job and return a MatchResult."""
        ...
