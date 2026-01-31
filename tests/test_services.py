"""Tests for application and resume services."""
import pytest
from datetime import datetime

from src.tracking.application_service import ApplicationService
from src.tracking.resume_service import ResumeService
from src.persistence.models import Application, Resume, StatusHistory


class TestApplicationService:
    """Tests for ApplicationService."""

    def test_create_application(self, test_db):
        """Test creating an application."""
        service = ApplicationService(test_db)

        app = service.create_application(
            company="Test Company",
            position="Product Manager",
            source="linkedin",
        )

        assert app is not None
        assert app.company == "Test Company"
        assert app.position == "Product Manager"
        assert app.status == "applied"

    def test_create_application_with_date(self, test_db):
        """Test creating an application with specific date."""
        service = ApplicationService(test_db)
        applied_date = datetime(2026, 1, 15)

        app = service.create_application(
            company="Test Co",
            position="PM",
            applied_date=applied_date,
        )

        assert app.applied_date == applied_date

    def test_get_application(self, test_db, sample_application):
        """Test getting an application by ID."""
        service = ApplicationService(test_db)
        retrieved = service.get_application(sample_application.id)

        assert retrieved is not None
        assert retrieved.id == sample_application.id

    def test_get_all_applications(self, test_db, multiple_applications):
        """Test getting all applications."""
        service = ApplicationService(test_db)
        apps = service.get_all_applications()

        assert len(apps) == 6

    def test_get_applications_by_status(self, test_db, multiple_applications):
        """Test filtering applications by status."""
        service = ApplicationService(test_db)
        apps = service.get_all_applications(status="applied")

        assert all(app.status == "applied" for app in apps)

    def test_update_status(self, test_db, sample_application):
        """Test updating application status."""
        service = ApplicationService(test_db)

        updated = service.update_status(
            sample_application.id,
            "interviewing",
            notes="Phone screen scheduled",
        )

        assert updated.status == "interviewing"
        assert updated.last_status_change is not None

    def test_update_status_creates_history(self, test_db, sample_application):
        """Test that status update creates history record."""
        service = ApplicationService(test_db)

        service.update_status(sample_application.id, "phone_screen")

        # Check history was created
        from sqlalchemy import select
        stmt = select(StatusHistory).where(
            StatusHistory.application_id == sample_application.id
        )
        result = test_db.execute(stmt)
        history = result.scalar_one_or_none()

        assert history is not None
        assert history.old_status == "applied"
        assert history.new_status == "phone_screen"

    def test_add_interview(self, test_db, sample_application):
        """Test adding an interview."""
        service = ApplicationService(test_db)

        interview = service.add_interview(
            application_id=sample_application.id,
            interview_type="phone",
            scheduled_at=datetime(2026, 1, 30, 14, 0),
            duration_minutes=45,
        )

        assert interview is not None
        assert interview.type == "phone"
        assert interview.round == 1

    def test_add_interview_auto_increments_round(self, test_db, sample_application):
        """Test that interview rounds auto-increment."""
        service = ApplicationService(test_db)

        interview1 = service.add_interview(
            application_id=sample_application.id,
            interview_type="phone",
        )
        assert interview1.round == 1

        interview2 = service.add_interview(
            application_id=sample_application.id,
            interview_type="video",
        )
        assert interview2.round == 2

    def test_get_pipeline_counts(self, test_db, multiple_applications):
        """Test getting pipeline counts by status."""
        service = ApplicationService(test_db)
        counts = service.get_pipeline_counts()

        assert isinstance(counts, dict)
        assert "applied" in counts
        assert counts["applied"] == 2

    def test_find_application_by_company(self, test_db, sample_application):
        """Test finding application by company name."""
        service = ApplicationService(test_db)

        # Exact match
        found = service._find_application_by_company("OpenAI")
        assert found is not None
        assert found.id == sample_application.id

        # Case insensitive
        found = service._find_application_by_company("openai")
        assert found is not None

    def test_find_application_by_company_partial(self, test_db, sample_application):
        """Test partial company name matching."""
        service = ApplicationService(test_db)

        # Partial match
        found = service._find_application_by_company("Open")
        assert found is not None


class TestResumeService:
    """Tests for ResumeService."""

    def test_create_resume(self, test_db):
        """Test creating a resume."""
        service = ResumeService(test_db)

        resume = service.create_resume(
            name="AI PM v1",
            target_roles=["AI Product Manager"],
            key_changes="Initial version",
        )

        assert resume is not None
        assert resume.name == "AI PM v1"
        assert resume.version == 1

    def test_create_resume_auto_version(self, test_db):
        """Test that resume version auto-increments."""
        service = ResumeService(test_db)

        resume1 = service.create_resume(name="AI PM v1")
        resume2 = service.create_resume(name="AI PM v2")

        assert resume2.version == resume1.version + 1

    def test_get_resume(self, test_db, sample_resume):
        """Test getting a resume by ID."""
        service = ResumeService(test_db)
        retrieved = service.get_resume(sample_resume.id)

        assert retrieved is not None
        assert retrieved.id == sample_resume.id

    def test_get_all_resumes(self, test_db, sample_resume):
        """Test getting all resumes."""
        service = ResumeService(test_db)
        resumes = service.get_all_resumes()

        assert len(resumes) >= 1

    def test_get_active_resumes_only(self, test_db):
        """Test filtering to active resumes only."""
        service = ResumeService(test_db)

        # Create active and inactive resumes
        service.create_resume(name="Active")
        inactive = service.create_resume(name="Inactive")
        service.deactivate_resume(inactive.id)

        active_only = service.get_all_resumes(active_only=True)
        all_resumes = service.get_all_resumes(active_only=False)

        assert len(active_only) < len(all_resumes)

    def test_update_resume(self, test_db, sample_resume):
        """Test updating a resume."""
        service = ResumeService(test_db)

        updated = service.update_resume(
            sample_resume.id,
            name="Updated Name",
            key_changes="New changes",
        )

        assert updated.name == "Updated Name"
        assert updated.key_changes == "New changes"

    def test_deactivate_resume(self, test_db, sample_resume):
        """Test deactivating a resume."""
        service = ResumeService(test_db)

        deactivated = service.deactivate_resume(sample_resume.id)
        assert deactivated.is_active is False

    def test_get_resume_stats(self, test_db, sample_resume):
        """Test getting resume statistics."""
        service = ResumeService(test_db)

        # Add some applications using this resume
        app1 = Application(
            company="A",
            position="PM",
            applied_date=datetime.now(),
            resume_id=sample_resume.id,
            status="applied",
        )
        app2 = Application(
            company="B",
            position="PM",
            applied_date=datetime.now(),
            resume_id=sample_resume.id,
            status="interviewing",
        )
        test_db.add_all([app1, app2])
        test_db.commit()

        stats = service.get_resume_stats(sample_resume.id)

        assert stats["total_applications"] == 2
        assert "response_rate" in stats
        assert "interview_rate" in stats
