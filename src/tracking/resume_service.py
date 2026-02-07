"""Resume management service."""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistence.models import Application, Interview, Resume


class ResumeService:
    """Service for managing resume versions."""

    def __init__(self, session: Session):
        """
        Initialize resume service.

        Args:
            session: Database session
        """
        self.session = session

    def create_resume(
        self,
        name: str,
        file_path: Optional[str] = None,
        target_roles: Optional[list[str]] = None,
        key_changes: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Resume:
        """
        Create a new resume version.

        Args:
            name: Resume name/identifier (e.g., "AI PM v3")
            file_path: Path to resume file
            target_roles: List of target role types
            key_changes: Description of key changes from previous version
            version: Version number (auto-incremented if not specified)

        Returns:
            Created Resume
        """
        # Auto-increment version if not specified
        if version is None:
            # Find max version for similar names
            stmt = select(func.max(Resume.version)).where(
                Resume.name.ilike(f"%{name.split()[0]}%")
            )
            result = self.session.execute(stmt)
            max_version = result.scalar() or 0
            version = max_version + 1

        resume = Resume(
            name=name,
            file_path=file_path,
            version=version,
            target_roles=target_roles,
            key_changes=key_changes,
            is_active=True,
        )

        self.session.add(resume)
        self.session.commit()
        self.session.refresh(resume)

        return resume

    def get_resume(self, resume_id: str) -> Optional[Resume]:
        """Get a resume by ID."""
        return self.session.get(Resume, resume_id)

    def get_all_resumes(self, active_only: bool = False) -> list[Resume]:
        """
        Get all resumes.

        Args:
            active_only: Only return active resumes

        Returns:
            List of resumes
        """
        stmt = select(Resume).order_by(Resume.created_at.desc())

        if active_only:
            stmt = stmt.where(Resume.is_active == True)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def update_resume(
        self,
        resume_id: str,
        name: Optional[str] = None,
        file_path: Optional[str] = None,
        target_roles: Optional[list[str]] = None,
        key_changes: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Resume]:
        """
        Update a resume.

        Args:
            resume_id: Resume ID
            name: New name
            file_path: New file path
            target_roles: New target roles
            key_changes: New key changes description
            is_active: Active status

        Returns:
            Updated Resume or None
        """
        resume = self.get_resume(resume_id)
        if not resume:
            return None

        if name is not None:
            resume.name = name
        if file_path is not None:
            resume.file_path = file_path
        if target_roles is not None:
            resume.target_roles = target_roles
        if key_changes is not None:
            resume.key_changes = key_changes
        if is_active is not None:
            resume.is_active = is_active

        self.session.commit()
        self.session.refresh(resume)

        return resume

    def deactivate_resume(self, resume_id: str) -> Optional[Resume]:
        """Deactivate a resume."""
        return self.update_resume(resume_id, is_active=False)

    def get_resume_stats(self, resume_id: str) -> dict:
        """
        Get statistics for a resume.

        Args:
            resume_id: Resume ID

        Returns:
            Dictionary with stats
        """
        # Count applications using this resume
        stmt = select(func.count(Application.id)).where(
            Application.resume_id == resume_id
        )
        result = self.session.execute(stmt)
        total_applications = result.scalar() or 0

        # Count by status
        stmt = select(Application.status, func.count(Application.id)).where(
            Application.resume_id == resume_id
        ).group_by(Application.status)
        result = self.session.execute(stmt)
        status_counts = dict(result.all())

        # Calculate response rate (any response including rejections and withdrawn)
        responses = sum(
            status_counts.get(s, 0)
            for s in ["phone_screen", "interviewing", "offer", "accepted", "rejected", "withdrawn"]
        )
        response_rate = (responses / total_applications * 100) if total_applications > 0 else 0

        # Calculate interview rate (reached phone_screen or beyond)
        # Use both status-based and Interview-record-based counting so apps
        # rejected after interviewing are still counted
        status_interviews = sum(
            status_counts.get(s, 0)
            for s in ["phone_screen", "interviewing", "offer", "accepted"]
        )
        # Also count apps with Interview records (covers rejected-after-interview)
        record_stmt = (
            select(func.count(func.distinct(Application.id)))
            .join(Interview, Interview.application_id == Application.id)
            .where(Application.resume_id == resume_id)
        )
        record_interviews = self.session.execute(record_stmt).scalar() or 0
        interviews = max(status_interviews, record_interviews)
        interview_rate = (interviews / total_applications * 100) if total_applications > 0 else 0

        return {
            "total_applications": total_applications,
            "status_counts": status_counts,
            "response_rate": response_rate,
            "interview_rate": interview_rate,
        }

    def get_all_resume_stats(self) -> list[dict]:
        """Get stats for all resumes."""
        resumes = self.get_all_resumes()
        stats = []

        for resume in resumes:
            resume_stats = self.get_resume_stats(resume.id)
            resume_stats["resume"] = resume
            stats.append(resume_stats)

        return stats

    def get_best_performing_resume(self) -> Optional[dict]:
        """Get the best performing resume by response rate."""
        all_stats = self.get_all_resume_stats()

        if not all_stats:
            return None

        # Filter to resumes with at least 5 applications
        qualified = [s for s in all_stats if s["total_applications"] >= 5]

        if not qualified:
            return max(all_stats, key=lambda x: x["total_applications"])

        return max(qualified, key=lambda x: x["response_rate"])
