"""Application funnel analytics."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistence.models import Application, Interview, EmailImport


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

    # Map stage names to numeric order for comparison
    STAGE_ORDER = {
        "applied": 0,
        "phone_screen": 1,
        "interviewing": 2,
        "offer": 3,
        "accepted": 4,
    }

    def __init__(self, session: Session):
        """
        Initialize funnel analytics.

        Args:
            session: Database session
        """
        self.session = session

    def _get_highest_stage(self, app: Application) -> str:
        """
        Determine the highest stage an application reached.

        For non-terminal apps, returns current status.
        For rejected/withdrawn/ghosted apps, uses rejected_at, interview
        records, and linked interview emails as signals.
        """
        terminal_statuses = {"rejected", "withdrawn", "ghosted"}

        if app.status not in terminal_statuses:
            return app.status

        # Start with current_stage or rejected_at as hints
        best = "applied"

        # Check rejected_at field (set by update_status when rejecting)
        if app.rejected_at:
            ra = app.rejected_at.lower()
            if ra in self.STAGE_ORDER:
                best = ra
            elif ra in ("interview", "final_round", "onsite"):
                best = "interviewing"

        # Check if the app has Interview records
        interview_count = (
            self.session.execute(
                select(func.count(Interview.id)).where(
                    Interview.application_id == app.id
                )
            ).scalar() or 0
        )
        if interview_count > 0:
            if self.STAGE_ORDER.get(best, 0) < self.STAGE_ORDER["phone_screen"]:
                best = "phone_screen"

        # Check linked interview_invite emails
        interview_email_count = (
            self.session.execute(
                select(func.count(EmailImport.id)).where(
                    EmailImport.application_id == app.id,
                    EmailImport.email_type == "interview_invite",
                )
            ).scalar() or 0
        )
        if interview_email_count > 0:
            if self.STAGE_ORDER.get(best, 0) < self.STAGE_ORDER["phone_screen"]:
                best = "phone_screen"

        # Check current_stage for more specific info
        if app.current_stage:
            cs = app.current_stage.lower()
            if cs in ("phone screen", "recruiter screen", "phone_screen"):
                if self.STAGE_ORDER.get(best, 0) < self.STAGE_ORDER["phone_screen"]:
                    best = "phone_screen"
            elif cs not in ("", "applied"):
                if self.STAGE_ORDER.get(best, 0) < self.STAGE_ORDER["interviewing"]:
                    best = "interviewing"

        return best

    def _get_effective_stage_counts(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, int]:
        """
        Count applications by their highest stage reached.

        Unlike grouping by current status, this ensures apps rejected after
        interviewing still count in the interview stage.
        """
        stmt = select(Application)
        if start_date:
            stmt = stmt.where(Application.applied_date >= start_date)
        if end_date:
            stmt = stmt.where(Application.applied_date <= end_date)

        apps = self.session.execute(stmt).scalars().all()

        counts: dict[str, int] = {}
        for app in apps:
            stage = self._get_highest_stage(app)
            counts[stage] = counts.get(stage, 0) + 1

        return counts

    def get_funnel(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> FunnelData:
        """
        Get funnel data for applications.

        Uses highest stage reached (not current status) so that apps
        rejected after interviewing still appear in the interview count.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            FunnelData with stages
        """
        stage_counts = self._get_effective_stage_counts(start_date, end_date)
        total = sum(stage_counts.values())

        # Build stage data
        stage_data = []
        for status, name in self.FUNNEL_STAGES:
            count = stage_counts.get(status, 0)
            stage_data.append((status, name, count))

        # Calculate cumulative (bottom-up)
        cumulative = {}
        running_total = 0
        for status, name, count in reversed(stage_data):
            running_total += count
            cumulative[status] = running_total

        # Build stages with metrics
        stages: list[FunnelStage] = []
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
        end_date = datetime.now(timezone.utc)
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

        Uses highest stage reached so that apps rejected after interviewing
        are still counted.

        Args:
            start_date: Start date for calculation

        Returns:
            Interview rate as percentage
        """
        stage_counts = self._get_effective_stage_counts(start_date)
        total = sum(stage_counts.values())

        if total == 0:
            return 0.0

        # Count apps that reached phone_screen or beyond
        interview_stages = {"phone_screen", "interviewing", "offer", "accepted"}
        interviews = sum(
            stage_counts.get(s, 0) for s in interview_stages
        )

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
