"""Resume performance analytics."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistence.models import Application, Resume


@dataclass
class ResumeStats:
    """Statistics for a resume version."""

    resume: Resume
    total_applications: int
    responses: int
    response_rate: float
    interviews: int
    interview_rate: float
    offers: int
    offer_rate: float


class ResumeAnalytics:
    """Analyze resume version performance."""

    def __init__(self, session: Session):
        """
        Initialize resume analytics.

        Args:
            session: Database session
        """
        self.session = session

    def get_resume_stats(
        self,
        start_date: Optional[datetime] = None,
    ) -> list[ResumeStats]:
        """
        Get statistics by resume version.

        Args:
            start_date: Start date for analysis

        Returns:
            List of ResumeStats
        """
        # Get all resumes
        stmt = select(Resume).order_by(Resume.created_at.desc())
        result = self.session.execute(stmt)
        resumes = list(result.scalars().all())

        stats: list[ResumeStats] = []

        for resume in resumes:
            # Count applications with this resume
            total = self._count_applications(resume.id, start_date)

            if total == 0:
                continue

            # Count responses (any movement from "applied", excluding ghosted)
            response_statuses = [
                "phone_screen",
                "interviewing",
                "offer",
                "accepted",
                "rejected",
            ]
            responses = self._count_applications(
                resume.id, start_date, statuses=response_statuses
            )

            # Count interviews (phone_screen or beyond, excluding terminal)
            interview_statuses = ["phone_screen", "interviewing", "offer", "accepted"]
            interviews = self._count_applications(
                resume.id, start_date, statuses=interview_statuses
            )

            # Count offers
            offer_statuses = ["offer", "accepted"]
            offers = self._count_applications(
                resume.id, start_date, statuses=offer_statuses
            )

            stats.append(
                ResumeStats(
                    resume=resume,
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

    def _count_applications(
        self,
        resume_id: str,
        start_date: Optional[datetime],
        statuses: Optional[list[str]] = None,
    ) -> int:
        """Count applications by resume and optionally status."""
        stmt = select(func.count(Application.id)).where(
            Application.resume_id == resume_id
        )

        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)

        if statuses:
            stmt = stmt.where(Application.status.in_(statuses))

        result = self.session.execute(stmt)
        return result.scalar() or 0

    def get_best_resume(
        self,
        min_applications: int = 5,
    ) -> Optional[ResumeStats]:
        """
        Get the best performing resume.

        Args:
            min_applications: Minimum applications to qualify

        Returns:
            ResumeStats for best resume or None
        """
        stats = self.get_resume_stats()

        # Filter to resumes with enough applications
        qualified = [s for s in stats if s.total_applications >= min_applications]

        if not qualified:
            # Fall back to any resume with applications
            return stats[0] if stats else None

        return qualified[0]  # Already sorted by response rate

    def compare_resumes(
        self,
        resume_id_1: str,
        resume_id_2: str,
    ) -> dict:
        """
        Compare two resume versions.

        Args:
            resume_id_1: First resume ID
            resume_id_2: Second resume ID

        Returns:
            Comparison dictionary
        """
        stats = self.get_resume_stats()

        stat1 = next((s for s in stats if s.resume.id == resume_id_1), None)
        stat2 = next((s for s in stats if s.resume.id == resume_id_2), None)

        if not stat1 or not stat2:
            return {"error": "One or both resumes not found"}

        return {
            "resume1": {
                "name": stat1.resume.name,
                "applications": stat1.total_applications,
                "response_rate": stat1.response_rate,
                "interview_rate": stat1.interview_rate,
            },
            "resume2": {
                "name": stat2.resume.name,
                "applications": stat2.total_applications,
                "response_rate": stat2.response_rate,
                "interview_rate": stat2.interview_rate,
            },
            "response_rate_diff": stat1.response_rate - stat2.response_rate,
            "interview_rate_diff": stat1.interview_rate - stat2.interview_rate,
            "winner": stat1.resume.name
            if stat1.response_rate > stat2.response_rate
            else stat2.resume.name,
        }

    def get_resume_usage_over_time(
        self,
        resume_id: str,
        weeks: int = 8,
    ) -> list[dict]:
        """
        Get weekly usage for a resume.

        Args:
            resume_id: Resume ID
            weeks: Number of weeks to analyze

        Returns:
            List of weekly data points
        """
        from datetime import timedelta

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=weeks)

        # Get applications by day
        stmt = select(
            func.date(Application.applied_date),
            func.count(Application.id),
        ).where(
            Application.resume_id == resume_id,
            Application.applied_date >= start_date,
        ).group_by(
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

    def get_no_resume_stats(self) -> dict:
        """
        Get stats for applications without a resume specified.

        Returns:
            Dictionary with stats
        """
        # Count applications with no resume
        stmt = select(func.count(Application.id)).where(
            Application.resume_id.is_(None)
        )
        result = self.session.execute(stmt)
        total = result.scalar() or 0

        if total == 0:
            return {
                "total": 0,
                "response_rate": 0,
                "message": "All applications have resumes assigned!",
            }

        # Count responses
        response_statuses = [
            "phone_screen",
            "interviewing",
            "offer",
            "accepted",
            "rejected",
        ]

        stmt = select(func.count(Application.id)).where(
            Application.resume_id.is_(None),
            Application.status.in_(response_statuses),
        )
        result = self.session.execute(stmt)
        responses = result.scalar() or 0

        return {
            "total": total,
            "responses": responses,
            "response_rate": (responses / total * 100) if total > 0 else 0,
            "message": f"{total} applications without resume tracking",
        }
