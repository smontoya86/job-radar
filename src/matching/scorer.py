"""Job scoring and ranking."""
import logging
from dataclasses import dataclass
from typing import Optional

from src.collectors.base import JobData
from src.matching.keyword_matcher import KeywordMatcher, MatchResult

logger = logging.getLogger(__name__)


@dataclass
class ScoredJob:
    """A job with its match score and details."""

    job: JobData
    match_result: MatchResult
    fingerprint: str

    @property
    def score(self) -> float:
        return self.match_result.score

    @property
    def matched_keywords(self) -> list[str]:
        return self.match_result.matched_primary + self.match_result.matched_secondary


class JobScorer:
    """Score and rank jobs based on profile match."""

    def __init__(self, matcher: KeywordMatcher, min_score: float = 0):
        """
        Initialize job scorer.

        Args:
            matcher: KeywordMatcher instance
            min_score: Minimum score to include (0-100)
        """
        self.matcher = matcher
        self.min_score = min_score

    def score_jobs(self, jobs: list[JobData]) -> list[ScoredJob]:
        """
        Score a list of jobs.

        Args:
            jobs: List of jobs to score

        Returns:
            List of ScoredJob objects, sorted by score descending
        """
        scored: list[ScoredJob] = []

        for job in jobs:
            result = self.matcher.match(job)

            # Skip if doesn't match or below minimum score
            if not result.matched or result.score < self.min_score:
                continue

            fingerprint = self._generate_fingerprint(job)

            scored.append(
                ScoredJob(
                    job=job,
                    match_result=result,
                    fingerprint=fingerprint,
                )
            )

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)

        return scored

    def _generate_fingerprint(self, job: JobData) -> str:
        """
        Generate a fingerprint for deduplication.

        Uses company name + title normalized.
        """
        # Normalize company and title
        company = job.company.lower().strip()
        title = job.title.lower().strip()

        # Remove common variations
        for word in ["inc", "inc.", "llc", "ltd", "corp", "corporation", "the"]:
            company = company.replace(word, "")

        # Remove extra whitespace
        company = " ".join(company.split())
        title = " ".join(title.split())

        return f"{company}:{title}"

    def filter_by_score(
        self,
        scored_jobs: list[ScoredJob],
        min_score: Optional[float] = None,
    ) -> list[ScoredJob]:
        """Filter scored jobs by minimum score."""
        threshold = min_score if min_score is not None else self.min_score
        return [j for j in scored_jobs if j.score >= threshold]

    def get_top_jobs(
        self,
        scored_jobs: list[ScoredJob],
        n: int = 10,
    ) -> list[ScoredJob]:
        """Get top N jobs by score."""
        return scored_jobs[:n]


def get_scorer(
    profile_path: str,
    scoring_engine: str = "heuristic",
    min_score: float = 0,
) -> JobScorer:
    """Factory: create a JobScorer based on the configured scoring engine.

    Args:
        profile_path: Path to profile.yaml
        scoring_engine: One of 'heuristic', 'ai', 'hybrid'
        min_score: Minimum score threshold

    Returns:
        A JobScorer instance (always heuristic for now;
        'ai' and 'hybrid' fall back with a warning).
    """
    if scoring_engine in ("ai", "hybrid"):
        logger.warning(
            "Scoring engine '%s' is not yet available. Falling back to heuristic.",
            scoring_engine,
        )

    matcher = KeywordMatcher(profile_path)
    return JobScorer(matcher, min_score=min_score)
