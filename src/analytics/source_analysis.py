"""Source effectiveness analytics."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistence.models import Application


@dataclass
class SourceStats:
    """Statistics for an application source."""

    source: str
    total_applications: int
    responses: int
    response_rate: float
    interviews: int
    interview_rate: float
    offers: int
    offer_rate: float


class SourceAnalytics:
    """Analyze effectiveness of different application sources."""

    def __init__(self, session: Session):
        """
        Initialize source analytics.

        Args:
            session: Database session
        """
        self.session = session

    def get_source_stats(
        self,
        start_date: Optional[datetime] = None,
    ) -> list[SourceStats]:
        """
        Get statistics by application source.

        Args:
            start_date: Start date for analysis

        Returns:
            List of SourceStats
        """
        # Get all applications grouped by source
        stmt = select(Application.source, func.count(Application.id))

        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)

        stmt = stmt.group_by(Application.source)

        result = self.session.execute(stmt)
        source_totals = dict(result.all())

        stats: list[SourceStats] = []

        for source, total in source_totals.items():
            if source is None:
                source = "Unknown"

            # Get response count
            response_statuses = [
                "phone_screen",
                "interviewing",
                "offer",
                "accepted",
                "rejected",
            ]
            responses = self._count_by_source_status(source, response_statuses, start_date)

            # Get interview count
            interview_statuses = ["phone_screen", "interviewing", "offer", "accepted"]
            interviews = self._count_by_source_status(source, interview_statuses, start_date)

            # Get offer count
            offer_statuses = ["offer", "accepted"]
            offers = self._count_by_source_status(source, offer_statuses, start_date)

            stats.append(
                SourceStats(
                    source=source or "Unknown",
                    total_applications=total,
                    responses=responses,
                    response_rate=(responses / total * 100) if total > 0 else 0,
                    interviews=interviews,
                    interview_rate=(interviews / total * 100) if total > 0 else 0,
                    offers=offers,
                    offer_rate=(offers / total * 100) if total > 0 else 0,
                )
            )

        # Sort by response rate (descending)
        stats.sort(key=lambda x: x.response_rate, reverse=True)

        return stats

    def _count_by_source_status(
        self,
        source: str,
        statuses: list[str],
        start_date: Optional[datetime],
    ) -> int:
        """Count applications by source and status."""
        stmt = select(func.count(Application.id)).where(
            Application.status.in_(statuses)
        )

        if source == "Unknown":
            stmt = stmt.where(Application.source.is_(None))
        else:
            stmt = stmt.where(Application.source == source)

        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)

        result = self.session.execute(stmt)
        return result.scalar() or 0

    def get_best_source(self) -> Optional[SourceStats]:
        """
        Get the best performing source by response rate.

        Only considers sources with >= 5 applications.

        Returns:
            SourceStats for best source or None
        """
        stats = self.get_source_stats()

        # Filter to sources with enough applications
        qualified = [s for s in stats if s.total_applications >= 5]

        if not qualified:
            # Fall back to any source with applications
            return stats[0] if stats else None

        return qualified[0]  # Already sorted by response rate

    def get_source_comparison(self) -> dict:
        """
        Get comparison data for all sources.

        Returns:
            Dictionary with comparison metrics
        """
        stats = self.get_source_stats()

        if not stats:
            return {
                "sources": [],
                "best_response_rate": None,
                "best_interview_rate": None,
                "best_offer_rate": None,
            }

        return {
            "sources": stats,
            "best_response_rate": max(stats, key=lambda x: x.response_rate),
            "best_interview_rate": max(stats, key=lambda x: x.interview_rate),
            "best_offer_rate": max(stats, key=lambda x: x.offer_rate),
            "total_applications": sum(s.total_applications for s in stats),
            "total_responses": sum(s.responses for s in stats),
            "total_interviews": sum(s.interviews for s in stats),
            "total_offers": sum(s.offers for s in stats),
        }

    def get_source_trend(
        self,
        source: str,
        weeks: int = 8,
    ) -> list[dict]:
        """
        Get weekly trend for a specific source.

        Args:
            source: Source name
            weeks: Number of weeks to analyze

        Returns:
            List of weekly data points
        """
        from datetime import timedelta

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=weeks)

        # Get applications by week
        stmt = select(
            func.date(Application.applied_date),
            func.count(Application.id),
        ).where(
            Application.applied_date >= start_date,
        )

        if source == "Unknown":
            stmt = stmt.where(Application.source.is_(None))
        else:
            stmt = stmt.where(Application.source == source)

        stmt = stmt.group_by(
            func.date(Application.applied_date)
        ).order_by(
            func.date(Application.applied_date)
        )

        result = self.session.execute(stmt)
        daily_counts = dict(result.all())

        # Aggregate by week
        weekly_data = []
        current_date = start_date

        while current_date <= end_date:
            week_start = current_date - timedelta(days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            week_count = 0
            day = week_start
            while day <= week_end and day <= end_date:
                week_count += daily_counts.get(day.date(), 0)
                day += timedelta(days=1)

            weekly_data.append({
                "week_start": week_start.date(),
                "count": week_count,
            })

            current_date = week_end + timedelta(days=1)

        return weekly_data
