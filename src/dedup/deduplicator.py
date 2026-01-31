"""Job deduplication."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.matching.scorer import ScoredJob
from src.persistence.models import Job


class Deduplicator:
    """Deduplicate jobs based on fingerprint."""

    def __init__(self, session: Session, lookback_days: int = 30):
        """
        Initialize deduplicator.

        Args:
            session: Database session
            lookback_days: How far back to check for duplicates
        """
        self.session = session
        self.lookback_days = lookback_days
        self._seen_fingerprints: set[str] = set()

    def load_existing_fingerprints(self) -> None:
        """Load fingerprints from existing jobs in database."""
        cutoff = datetime.utcnow() - timedelta(days=self.lookback_days)

        stmt = select(Job.fingerprint).where(
            Job.discovered_at >= cutoff,
            Job.fingerprint.isnot(None),
        )

        result = self.session.execute(stmt)
        self._seen_fingerprints = {row[0] for row in result if row[0]}

    def is_duplicate(self, fingerprint: str) -> bool:
        """Check if a fingerprint has been seen."""
        return fingerprint in self._seen_fingerprints

    def mark_seen(self, fingerprint: str) -> None:
        """Mark a fingerprint as seen."""
        self._seen_fingerprints.add(fingerprint)

    def deduplicate(
        self,
        scored_jobs: list[ScoredJob],
        check_db: bool = True,
    ) -> list[ScoredJob]:
        """
        Remove duplicates from scored jobs.

        Args:
            scored_jobs: List of scored jobs
            check_db: Whether to check database for existing jobs

        Returns:
            Deduplicated list of scored jobs
        """
        if check_db:
            self.load_existing_fingerprints()

        unique_jobs: list[ScoredJob] = []
        batch_seen: set[str] = set()

        for job in scored_jobs:
            fp = job.fingerprint

            # Skip if seen in database or this batch
            if fp in self._seen_fingerprints or fp in batch_seen:
                continue

            batch_seen.add(fp)
            unique_jobs.append(job)

        return unique_jobs

    def filter_new_only(
        self,
        scored_jobs: list[ScoredJob],
    ) -> list[ScoredJob]:
        """Filter to only jobs not in database."""
        self.load_existing_fingerprints()

        return [
            job
            for job in scored_jobs
            if job.fingerprint not in self._seen_fingerprints
        ]
