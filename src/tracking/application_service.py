"""Application tracking service."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dateutil import parser as dateutil_parser

from src.gmail.parser import EmailType, ParsedEmail
from src.persistence.models import Application, EmailImport, Interview, Job, StatusHistory


class ApplicationService:
    """Service for managing job applications."""

    # Valid status transitions (simplified)
    # applied -> phone_screen -> interviewing -> offer -> accepted
    STATUS_ORDER = [
        "applied",
        "phone_screen",
        "interviewing",
        "offer",
        "accepted",
    ]
    TERMINAL_STATUSES = ["rejected", "withdrawn", "ghosted"]

    def __init__(self, session: Session):
        """
        Initialize application service.

        Args:
            session: Database session
        """
        self.session = session

    def create_application(
        self,
        company: str,
        position: str,
        applied_date: Optional[datetime] = None,
        source: Optional[str] = None,
        resume_id: Optional[str] = None,
        job_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Application:
        """
        Create a new application.

        Args:
            company: Company name
            position: Job position/title
            applied_date: Date of application (defaults to now)
            source: Application source (linkedin, referral, etc.)
            resume_id: ID of resume used
            job_id: ID of job from radar (if applicable)
            notes: Additional notes

        Returns:
            Created Application
        """
        application = Application(
            company=company,
            position=position,
            applied_date=applied_date or datetime.now(timezone.utc),
            source=source,
            resume_id=resume_id,
            job_id=job_id,
            notes=notes,
            status="applied",
        )

        self.session.add(application)
        self.session.commit()
        self.session.refresh(application)

        return application

    def get_application(self, application_id: str) -> Optional[Application]:
        """Get an application by ID."""
        return self.session.get(Application, application_id)

    def get_all_applications(
        self,
        status: Optional[str] = None,
        company: Optional[str] = None,
        limit: int = 100,
    ) -> list[Application]:
        """
        Get applications with optional filters.

        Args:
            status: Filter by status
            company: Filter by company name (partial match)
            limit: Maximum results

        Returns:
            List of applications
        """
        stmt = select(Application).order_by(Application.applied_date.desc())

        if status:
            stmt = stmt.where(Application.status == status)
        if company:
            escaped = self._escape_like(company)
            stmt = stmt.where(Application.company.ilike(f"%{escaped}%", escape="\\"))

        stmt = stmt.limit(limit)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def update_status(
        self,
        application_id: str,
        new_status: str,
        notes: Optional[str] = None,
    ) -> Optional[Application]:
        """
        Update application status with history tracking.

        Args:
            application_id: Application ID
            new_status: New status
            notes: Notes about the status change

        Returns:
            Updated application or None if not found
        """
        # Validate status
        VALID_STATUSES = set(self.STATUS_ORDER + self.TERMINAL_STATUSES)
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}")

        application = self.get_application(application_id)
        if not application:
            return None

        old_status = application.status

        # Skip if already at the same status (prevents duplicate history entries)
        if old_status == new_status:
            return application

        # Record status history
        history = StatusHistory(
            application_id=application_id,
            old_status=old_status,
            new_status=new_status,
            notes=notes,
        )
        self.session.add(history)

        # Update application
        application.status = new_status
        application.last_status_change = datetime.now(timezone.utc)

        # Set rejection info if rejected
        if new_status == "rejected":
            application.rejected_at = old_status
            # Auto-populate job_description from linked Job for analysis
            if not application.job_description and application.job_id:
                job = self.session.get(Job, application.job_id)
                if job and job.description:
                    application.job_description = job.description

        self.session.commit()
        self.session.refresh(application)

        return application

    def add_interview(
        self,
        application_id: str,
        interview_type: str,
        scheduled_at: Optional[datetime] = None,
        round_num: Optional[int] = None,
        interviewers: Optional[list[str]] = None,
        duration_minutes: Optional[int] = None,
        topics: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ) -> Optional[Interview]:
        """
        Add an interview to an application.

        Args:
            application_id: Application ID
            interview_type: Type of interview (phone, video, onsite, take_home)
            scheduled_at: Interview date/time
            round_num: Interview round number
            interviewers: List of interviewer names
            duration_minutes: Expected duration
            topics: Topics to be covered
            notes: Additional notes

        Returns:
            Created Interview or None if application not found
        """
        application = self.get_application(application_id)
        if not application:
            return None

        # Don't add interviews to terminated applications
        if application.status in self.TERMINAL_STATUSES:
            return None

        # Auto-increment round if not specified
        if round_num is None:
            round_num = application.interview_rounds + 1

        interview = Interview(
            application_id=application_id,
            type=interview_type,
            scheduled_at=scheduled_at,
            round=round_num,
            interviewers=interviewers,
            duration_minutes=duration_minutes,
            topics=topics,
            notes=notes,
            outcome="pending",
        )

        self.session.add(interview)

        # Update application
        application.interview_rounds = round_num
        if scheduled_at:
            application.next_interview_date = scheduled_at

        # Update status and current_stage based on interview type
        if interview_type in ["Phone Screen", "Recruiter Screen"]:
            if application.status == "applied":
                self.update_status(application_id, "phone_screen")
            application.current_stage = interview_type
        else:
            if application.status in ["applied", "phone_screen"]:
                self.update_status(application_id, "interviewing")
            application.current_stage = interview_type

        self.session.commit()
        self.session.refresh(interview)

        return interview

    def update_interview_outcome(
        self,
        interview_id: str,
        outcome: str,
        feedback: Optional[str] = None,
    ) -> Optional[Interview]:
        """
        Update interview outcome.

        Args:
            interview_id: Interview ID
            outcome: Outcome (passed, failed, pending)
            feedback: Interview feedback

        Returns:
            Updated Interview or None
        """
        interview = self.session.get(Interview, interview_id)
        if not interview:
            return None

        interview.outcome = outcome
        interview.feedback = feedback

        self.session.commit()
        self.session.refresh(interview)

        return interview

    def create_from_email(self, parsed_email: ParsedEmail) -> Optional[Application]:
        """
        Create or update application from parsed email.

        Args:
            parsed_email: Parsed email data

        Returns:
            Created/updated Application or None
        """
        if not parsed_email.company:
            return None

        # Check if application already exists for this company
        existing = self._find_application_by_company(parsed_email.company)

        if existing:
            # Try to link to a Job before updating
            self._try_link_to_job(existing)
            # Update existing application based on email type
            return self._update_from_email(existing, parsed_email)
        elif parsed_email.email_type == EmailType.CONFIRMATION:
            # Create new application from confirmation email
            app = self.create_application(
                company=parsed_email.company,
                position=parsed_email.position or "Unknown Position",
                source="email_import",
            )
            # Try to link newly created app to a Job
            self._try_link_to_job(app)
            self.session.commit()
            return app
        elif parsed_email.email_type == EmailType.REJECTION:
            # Create application directly from rejection email
            # (no prior confirmation email was processed for this company)
            app = self.create_application(
                company=parsed_email.company,
                position=parsed_email.position or "Unknown Position",
                source="email_import",
            )
            self._try_link_to_job(app)
            self.update_status(
                app.id,
                "rejected",
                notes="Rejection email received (no prior application tracked)",
            )
            return app
        elif parsed_email.email_type == EmailType.INTERVIEW_INVITE:
            # Create application from interview invite (no prior email tracked)
            app = self.create_application(
                company=parsed_email.company,
                position=parsed_email.position or "Unknown Position",
                source="email_import",
            )
            self._try_link_to_job(app)
            self._update_from_email(app, parsed_email)
            return app
        elif parsed_email.email_type == EmailType.OFFER:
            # Create application from offer email (no prior email tracked)
            app = self.create_application(
                company=parsed_email.company,
                position=parsed_email.position or "Unknown Position",
                source="email_import",
            )
            self._try_link_to_job(app)
            self.update_status(
                app.id,
                "offer",
                notes="Offer email received (no prior application tracked)",
            )
            return app

        return None

    def _try_link_to_job(self, application: Application) -> None:
        """Try to link an application to a Job by company name.

        Sets application.job_id and copies Job.description to
        application.job_description (if not already set).
        Picks the most recently discovered Job when multiple match.
        """
        if application.job_id:
            # Already linked — still copy description if missing
            if not application.job_description:
                job = self.session.get(Job, application.job_id)
                if job and job.description:
                    application.job_description = job.description
            return

        # Find matching job by company name (case-insensitive, most recent first)
        stmt = (
            select(Job)
            .where(func.lower(Job.company) == application.company.lower())
            .order_by(Job.discovered_at.desc())
            .limit(1)
        )
        result = self.session.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            return

        application.job_id = job.id
        if not application.job_description and job.description:
            application.job_description = job.description

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escape special LIKE characters (%, _) in user input."""
        return value.replace("%", r"\%").replace("_", r"\_")

    def _find_application_by_company(
        self,
        company: str,
    ) -> Optional[Application]:
        """Find existing application by company name."""
        # Try exact match first
        stmt = select(Application).where(
            func.lower(Application.company) == company.lower()
        )
        result = self.session.execute(stmt)
        app = result.scalars().first()

        if app:
            return app

        # Try partial match - return first match if multiple
        escaped = self._escape_like(company)
        stmt = select(Application).where(
            Application.company.ilike(f"%{escaped}%", escape="\\")
        ).limit(1)
        result = self.session.execute(stmt)
        return result.scalars().first()

    def _update_from_email(
        self,
        application: Application,
        parsed_email: ParsedEmail,
    ) -> Application:
        """Update application based on email type."""
        if parsed_email.email_type == EmailType.REJECTION:
            self.update_status(
                application.id,
                "rejected",
                notes=f"Rejection email received",
            )
        elif parsed_email.email_type == EmailType.INTERVIEW_INVITE:
            # Determine interview type from email context
            subject = ""
            if parsed_email.raw_email:
                subject = (parsed_email.raw_email.subject or "").lower()
            position_lower = (parsed_email.position or "").lower()

            phone_keywords = ["phone screen", "recruiter", "phone call", "phone interview"]
            if any(kw in subject or kw in position_lower for kw in phone_keywords):
                interview_type = "Phone Screen"
            else:
                interview_type = "Other"

            # Parse interview date if available
            scheduled_at = None
            if parsed_email.interview_date:
                try:
                    scheduled_at = dateutil_parser.parse(parsed_email.interview_date)
                except ValueError:
                    pass

            # Create Interview record (also updates status and current_stage)
            email_subject = parsed_email.raw_email.subject if parsed_email.raw_email else "Interview invitation"
            self.add_interview(
                application.id,
                interview_type=interview_type,
                scheduled_at=scheduled_at,
                notes=f"Auto-created from email: {email_subject}",
            )
        elif parsed_email.email_type == EmailType.OFFER:
            self.update_status(
                application.id,
                "offer",
                notes=f"Offer received",
            )

        return application

    def link_email_import(
        self,
        application_id: str,
        email_import_id: str,
    ) -> None:
        """Link an email import to an application."""
        email_import = self.session.get(EmailImport, email_import_id)
        if email_import:
            email_import.application_id = application_id
            email_import.processed = True
            self.session.commit()

    def get_pipeline_counts(self) -> dict[str, int]:
        """Get counts by status for pipeline view."""
        stmt = select(Application.status, func.count(Application.id)).group_by(
            Application.status
        )
        result = self.session.execute(stmt)
        return dict(result.all())

    def get_application_by_job(self, job_id: str) -> Optional[Application]:
        """Get application for a specific job."""
        stmt = select(Application).where(Application.job_id == job_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def mark_job_applied(self, job_id: str) -> Optional[Job]:
        """Mark a job as applied."""
        job = self.session.get(Job, job_id)
        if job:
            job.status = "applied"
            self.session.commit()
        return job
