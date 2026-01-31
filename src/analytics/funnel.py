"""Application funnel analytics."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistence.models import Application


@dataclass
class FunnelStage:
    """A stage in the application funnel."""

    name: str
    count: int
    percentage: float
    conversion_rate: float  # % that made it to this stage from previous


@dataclass
class FunnelData:
    """Complete funnel data."""

    stages: list[FunnelStage]
    total_applications: int
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None


class FunnelAnalytics:
    """Analyze application funnel metrics."""

    # Funnel stages in order (simplified)
    # Statuses: applied -> phone_screen -> interviewing -> offer -> accepted
    # Terminal: rejected, withdrawn, ghosted
    FUNNEL_STAGES = [
        ("applied", "Applied"),
        ("phone_screen", "Phone Screen"),
        ("interviewing", "Interviewing"),
        ("offer", "Offer"),
        ("accepted", "Accepted"),
    ]

    def __init__(self, session: Session):
        """
        Initialize funnel analytics.

        Args:
            session: Database session
        """
        self.session = session

    def get_funnel(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> FunnelData:
        """
        Get funnel data for applications.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            FunnelData with stages
        """
        # Get counts by status
        stmt = select(Application.status, func.count(Application.id))

        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)
        if end_date:
            stmt = stmt.where(Application.applied_date <= end_date)

        stmt = stmt.group_by(Application.status)

        result = self.session.execute(stmt)
        status_counts = dict(result.all())

        # Build funnel stages
        stages: list[FunnelStage] = []
        total = sum(status_counts.values())

        # For funnel, we need cumulative counts
        # Each stage includes all applications that reached that stage or beyond
        cumulative_count = 0
        stage_data = []

        for status, name in self.FUNNEL_STAGES:
            count = status_counts.get(status, 0)
            stage_data.append((status, name, count))

        # Calculate cumulative (bottom-up)
        cumulative = {}
        running_total = 0
        for status, name, count in reversed(stage_data):
            running_total += count
            cumulative[status] = running_total

        # Build stages with metrics
        prev_count = total
        for status, name in self.FUNNEL_STAGES:
            count = cumulative.get(status, 0)
            percentage = (count / total * 100) if total > 0 else 0
            conversion = (count / prev_count * 100) if prev_count > 0 else 0

            stages.append(
                FunnelStage(
                    name=name,
                    count=count,
                    percentage=percentage,
                    conversion_rate=conversion,
                )
            )
            prev_count = count

        return FunnelData(
            stages=stages,
            total_applications=total,
            date_range_start=start_date,
            date_range_end=end_date,
        )

    def get_conversion_rates(self) -> dict[str, float]:
        """
        Get stage-to-stage conversion rates.

        Returns:
            Dictionary of stage transitions with rates
        """
        funnel = self.get_funnel()
        conversions = {}

        for i, stage in enumerate(funnel.stages[1:], 1):
            prev_stage = funnel.stages[i - 1]
            key = f"{prev_stage.name} -> {stage.name}"
            conversions[key] = stage.conversion_rate

        return conversions

    def get_weekly_applications(
        self,
        weeks: int = 8,
    ) -> list[dict]:
        """
        Get application counts by week.

        Args:
            weeks: Number of weeks to look back

        Returns:
            List of {week_start, count} dicts
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=weeks)

        stmt = select(
            func.date(Application.applied_date),
            func.count(Application.id),
        ).where(
            Application.applied_date >= start_date
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
                "week_end": week_end.date(),
                "count": week_count,
            })

            current_date = week_end + timedelta(days=1)

        return weekly_data

    def get_response_rate(
        self,
        start_date: Optional[datetime] = None,
    ) -> float:
        """
        Calculate overall response rate (any response including rejections).

        Response = any status beyond "applied" (excluding ghosted)

        Args:
            start_date: Start date for calculation

        Returns:
            Response rate as percentage
        """
        # Count total applications
        stmt = select(func.count(Application.id))
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)
        result = self.session.execute(stmt)
        total = result.scalar() or 0

        if total == 0:
            return 0.0

        # Count responses (anything beyond applied, excluding ghosted)
        response_statuses = [
            "phone_screen",
            "interviewing",
            "offer",
            "accepted",
            "rejected",
        ]

        stmt = select(func.count(Application.id)).where(
            Application.status.in_(response_statuses)
        )
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)

        result = self.session.execute(stmt)
        responses = result.scalar() or 0

        return (responses / total) * 100

    def get_interview_rate(
        self,
        start_date: Optional[datetime] = None,
    ) -> float:
        """
        Calculate application to interview rate.

        Interview = reached phone_screen, interviewing, offer, or accepted stage.

        Args:
            start_date: Start date for calculation

        Returns:
            Interview rate as percentage
        """
        # Count total applications
        stmt = select(func.count(Application.id))
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)
        result = self.session.execute(stmt)
        total = result.scalar() or 0

        if total == 0:
            return 0.0

        # Count interviews (reached interview stage or beyond)
        interview_statuses = [
            "phone_screen",
            "interviewing",
            "offer",
            "accepted",
        ]

        stmt = select(func.count(Application.id)).where(
            Application.status.in_(interview_statuses)
        )
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)

        result = self.session.execute(stmt)
        interviews = result.scalar() or 0

        return (interviews / total) * 100

    def get_rejection_rate(
        self,
        start_date: Optional[datetime] = None,
    ) -> float:
        """
        Calculate rejection rate.

        Rejection rate = rejected applications / total applications.

        Args:
            start_date: Start date for calculation

        Returns:
            Rejection rate as percentage
        """
        # Count total applications
        stmt = select(func.count(Application.id))
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)
        result = self.session.execute(stmt)
        total = result.scalar() or 0

        if total == 0:
            return 0.0

        # Count rejections
        stmt = select(func.count(Application.id)).where(
            Application.status == "rejected"
        )
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)

        result = self.session.execute(stmt)
        rejections = result.scalar() or 0

        return (rejections / total) * 100

    def get_average_time_to_rejection(self) -> Optional[float]:
        """
        Calculate average days from application to rejection.

        Returns:
            Average days or None if no data
        """
        stmt = select(Application).where(
            Application.status == "rejected",
            Application.last_status_change.isnot(None),
        )

        result = self.session.execute(stmt)
        rejected = result.scalars().all()

        if not rejected:
            return None

        total_days = 0
        count = 0

        for app in rejected:
            if app.applied_date and app.last_status_change:
                days = (app.last_status_change - app.applied_date).days
                total_days += days
                count += 1

        return total_days / count if count > 0 else None

    def get_active_pipeline_count(self) -> int:
        """
        Count applications still active in pipeline.

        Active = not rejected, withdrawn, ghosted, or accepted
        """
        terminal_statuses = ["rejected", "withdrawn", "ghosted", "accepted", "declined"]

        stmt = select(func.count(Application.id)).where(
            Application.status.notin_(terminal_statuses)
        )

        result = self.session.execute(stmt)
        return result.scalar() or 0
