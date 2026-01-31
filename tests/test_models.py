"""Tests for database models."""
import pytest
from datetime import datetime

from src.persistence.models import Application, Job, Resume, Interview, EmailImport


class TestJobModel:
    """Tests for Job model."""

    def test_create_job(self, test_db, sample_job):
        """Test creating a job."""
        test_db.add(sample_job)
        test_db.commit()

        retrieved = test_db.get(Job, sample_job.id)
        assert retrieved is not None
        assert retrieved.title == "Senior AI Product Manager"
        assert retrieved.company == "Anthropic"
        assert retrieved.remote is True

    def test_job_defaults(self, test_db):
        """Test job default values."""
        job = Job(
            title="PM",
            company="Test Co",
            url="https://test.com",
            source="test",
        )
        test_db.add(job)
        test_db.commit()

        assert job.status == "new"
        assert job.remote is False
        assert job.discovered_at is not None

    def test_job_repr(self, sample_job):
        """Test job string representation."""
        assert "Anthropic" in repr(sample_job)
        assert "Senior AI Product Manager" in repr(sample_job)


class TestApplicationModel:
    """Tests for Application model."""

    def test_create_application(self, test_db, sample_application):
        """Test creating an application."""
        retrieved = test_db.get(Application, sample_application.id)
        assert retrieved is not None
        assert retrieved.company == "OpenAI"
        assert retrieved.status == "applied"

    def test_application_defaults(self, test_db):
        """Test application default values."""
        app = Application(
            company="Test",
            position="PM",
            applied_date=datetime.now(),
        )
        test_db.add(app)
        test_db.commit()

        assert app.status == "applied"
        assert app.interview_rounds == 0
        assert app.cover_letter_used is False

    def test_application_with_resume(self, test_db, sample_resume):
        """Test application with resume relationship."""
        app = Application(
            company="Test",
            position="PM",
            applied_date=datetime.now(),
            resume_id=sample_resume.id,
        )
        test_db.add(app)
        test_db.commit()

        retrieved = test_db.get(Application, app.id)
        assert retrieved.resume_id == sample_resume.id


class TestResumeModel:
    """Tests for Resume model."""

    def test_create_resume(self, test_db, sample_resume):
        """Test creating a resume."""
        retrieved = test_db.get(Resume, sample_resume.id)
        assert retrieved is not None
        assert retrieved.name == "AI PM v3"
        assert retrieved.version == 3

    def test_resume_target_roles_json(self, test_db, sample_resume):
        """Test that target_roles is stored as JSON."""
        retrieved = test_db.get(Resume, sample_resume.id)
        assert isinstance(retrieved.target_roles, list)
        assert "AI Product Manager" in retrieved.target_roles


class TestInterviewModel:
    """Tests for Interview model."""

    def test_create_interview(self, test_db, sample_application):
        """Test creating an interview."""
        interview = Interview(
            application_id=sample_application.id,
            round=1,
            type="phone",
            scheduled_at=datetime(2026, 1, 28, 14, 0),
            duration_minutes=45,
            outcome="pending",
        )
        test_db.add(interview)
        test_db.commit()

        retrieved = test_db.get(Interview, interview.id)
        assert retrieved is not None
        assert retrieved.round == 1
        assert retrieved.type == "phone"


class TestEmailImportModel:
    """Tests for EmailImport model."""

    def test_create_email_import(self, test_db):
        """Test creating an email import."""
        email = EmailImport(
            gmail_message_id="msg123",
            subject="Thank you for applying",
            from_address="jobs@company.com",
            received_at=datetime.now(),
            email_type="confirmation",
            parsed_data={"company": "Test Co"},
        )
        test_db.add(email)
        test_db.commit()

        retrieved = test_db.get(EmailImport, email.id)
        assert retrieved is not None
        assert retrieved.email_type == "confirmation"
        assert retrieved.parsed_data["company"] == "Test Co"

    def test_unique_gmail_message_id(self, test_db):
        """Test that gmail_message_id must be unique."""
        email1 = EmailImport(
            gmail_message_id="same_id",
            email_type="confirmation",
        )
        test_db.add(email1)
        test_db.commit()

        email2 = EmailImport(
            gmail_message_id="same_id",
            email_type="rejection",
        )
        test_db.add(email2)

        with pytest.raises(Exception):  # IntegrityError
            test_db.commit()
