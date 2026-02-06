"""Tests for system audit fixes."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from sqlalchemy import select, func

from src.collectors.base import JobData
from src.gmail.client import EmailMessage
from src.gmail.parser import EmailParser, EmailType, ParsedEmail
from src.persistence.models import Application, Interview, StatusHistory
from src.tracking.application_service import ApplicationService


class TestFindApplicationByCompanyDuplicates:
    """Fix 1.1: _find_application_by_company should not crash on duplicates."""

    def test_find_company_with_duplicates_returns_first(self, test_db):
        """scalar_one_or_none crashes when multiple rows match; scalars().first() should not."""
        app1 = Application(
            id="dup-1", company="Experian", position="PM",
            applied_date=datetime(2026, 1, 20), status="applied",
        )
        app2 = Application(
            id="dup-2", company="Experian", position="Sr PM",
            applied_date=datetime(2026, 1, 21), status="rejected",
        )
        test_db.add_all([app1, app2])
        test_db.commit()

        service = ApplicationService(test_db)
        result = service._find_application_by_company("Experian")

        # Should return one result without crashing
        assert result is not None
        assert result.company == "Experian"

    def test_find_company_partial_match_returns_result(self, test_db):
        """Partial match should still work for legitimate cases."""
        app = Application(
            id="partial-1", company="Fireblocks", position="PM",
            applied_date=datetime(2026, 1, 20), status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        # Exact match for "Fireblocks" should work
        result = service._find_application_by_company("Fireblocks")
        assert result is not None
        assert result.company == "Fireblocks"


class TestStatusValidation:
    """Fix 2.1: update_status should validate status names."""

    def test_update_status_rejects_invalid_status(self, test_db, sample_application):
        """Passing an invalid status like 'interview' should raise ValueError."""
        service = ApplicationService(test_db)
        with pytest.raises(ValueError, match="Invalid status"):
            service.update_status(sample_application.id, "interview")

    def test_update_status_rejects_screening(self, test_db, sample_application):
        """Old status 'screening' should be rejected."""
        service = ApplicationService(test_db)
        with pytest.raises(ValueError, match="Invalid status"):
            service.update_status(sample_application.id, "screening")

    def test_update_status_accepts_valid_status(self, test_db, sample_application):
        """Valid statuses like 'interviewing' should work."""
        service = ApplicationService(test_db)
        result = service.update_status(sample_application.id, "interviewing")
        assert result is not None
        assert result.status == "interviewing"

    def test_update_status_skips_same_status(self, test_db, sample_application):
        """No new StatusHistory when old_status == new_status."""
        service = ApplicationService(test_db)
        # First set to rejected
        service.update_status(sample_application.id, "rejected")

        # Count history entries
        count_before = test_db.execute(
            select(func.count(StatusHistory.id)).where(
                StatusHistory.application_id == sample_application.id
            )
        ).scalar()

        # Try to set rejected again
        result = service.update_status(sample_application.id, "rejected")

        count_after = test_db.execute(
            select(func.count(StatusHistory.id)).where(
                StatusHistory.application_id == sample_application.id
            )
        ).scalar()

        # Should not create a new history entry
        assert count_after == count_before
        assert result is not None


class TestAddInterviewGuard:
    """Fix 2.2: add_interview should not add to terminal applications."""

    def test_add_interview_rejected_app_returns_none(self, test_db, sample_application):
        """Can't add interview to a rejected application."""
        service = ApplicationService(test_db)
        service.update_status(sample_application.id, "rejected")

        result = service.add_interview(
            sample_application.id,
            interview_type="Phone Screen",
        )
        assert result is None

    def test_add_interview_active_app_works(self, test_db, sample_application):
        """Adding interview to active app should work."""
        service = ApplicationService(test_db)
        result = service.add_interview(
            sample_application.id,
            interview_type="Phone Screen",
        )
        assert result is not None
        assert result.type == "Phone Screen"


class TestNanFiltering:
    """Fix 1.2: 'nan' strings should be sanitized in JobData."""

    def test_nan_description_filtered_to_none(self):
        """'nan' string description becomes None in JobData."""
        job = JobData(
            title="PM", company="Test Co",
            url="https://test.com", source="test",
            description="nan",
        )
        assert job.description is None

    def test_nan_company_filtered_to_empty(self):
        """'nan' string company becomes empty string in JobData."""
        job = JobData(
            title="PM", company="nan",
            url="https://test.com", source="test",
        )
        assert job.company == ""

    def test_nan_title_filtered_to_empty(self):
        """'nan' string title becomes empty string in JobData."""
        job = JobData(
            title="nan", company="Test Co",
            url="https://test.com", source="test",
        )
        assert job.title == ""

    def test_valid_description_unchanged(self):
        """Normal descriptions should not be affected."""
        job = JobData(
            title="PM", company="Test Co",
            url="https://test.com", source="test",
            description="A great job at a great company",
        )
        assert job.description == "A great job at a great company"

    def test_nan_case_insensitive(self):
        """'NaN' and 'NAN' should also be filtered."""
        job1 = JobData(
            title="PM", company="Test Co",
            url="https://test.com", source="test",
            description="NaN",
        )
        job2 = JobData(
            title="PM", company="Test Co",
            url="https://test.com", source="test",
            description="NAN",
        )
        assert job1.description is None
        assert job2.description is None


class TestIdempotency:
    """Fix 1.4: Rejection on already-rejected app should not create duplicate history."""

    def test_rejection_email_on_already_rejected_no_duplicate_history(self, test_db):
        """Processing a rejection email on an already-rejected app should be a no-op."""
        app = Application(
            id="idemp-1", company="TestCorp", position="PM",
            applied_date=datetime(2026, 1, 20), status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)

        # First rejection
        service.update_status(app.id, "rejected", notes="First rejection")

        count_after_first = test_db.execute(
            select(func.count(StatusHistory.id)).where(
                StatusHistory.application_id == app.id
            )
        ).scalar()

        # Second rejection (e.g., from email processing)
        service.update_status(app.id, "rejected", notes="Duplicate rejection email")

        count_after_second = test_db.execute(
            select(func.count(StatusHistory.id)).where(
                StatusHistory.application_id == app.id
            )
        ).scalar()

        assert count_after_second == count_after_first


def _make_email(subject: str, from_address: str = "noreply@company.com",
                from_name: str = "", body_text: str = "") -> EmailMessage:
    """Helper to create an EmailMessage for parser tests."""
    return EmailMessage(
        id="test-id",
        thread_id="test-thread",
        subject=subject,
        from_address=from_address,
        from_name=from_name,
        to_address="user@gmail.com",
        date=datetime(2026, 1, 25),
        body_text=body_text,
    )


class TestLinkedInConfirmationPattern:
    """Task 6: LinkedIn 'application was sent' should be CONFIRMATION."""

    def test_application_was_sent_to_is_confirmation(self):
        """'your application was sent to X' emails should be classified as confirmation."""
        parser = EmailParser()
        email = _make_email(
            subject="Sam, your application was sent to Cint",
            from_address="jobs-noreply@linkedin.com",
        )
        result = parser.parse(email)
        assert result.email_type == EmailType.CONFIRMATION

    def test_application_was_sent_to_extracts_company(self):
        """Company should be extracted from 'your application was sent to X' subjects."""
        parser = EmailParser()
        email = _make_email(
            subject="Sam, your application was sent to Cint",
            from_address="jobs-noreply@linkedin.com",
        )
        result = parser.parse(email)
        assert result.company == "Cint"


class TestCreateFromEmailTypes:
    """Task 7: create_from_email should handle INTERVIEW_INVITE and OFFER."""

    def test_create_from_interview_invite(self, test_db):
        """INTERVIEW_INVITE email should create an application and interview."""
        service = ApplicationService(test_db)
        parsed = ParsedEmail(
            email_type=EmailType.INTERVIEW_INVITE,
            company="NewCo",
            position="Product Manager",
            confidence=0.8,
            raw_email=_make_email(
                subject="Interview invitation from NewCo",
                from_address="hr@newco.com",
            ),
        )
        result = service.create_from_email(parsed)
        assert result is not None
        assert result.company == "NewCo"
        # Should have created an interview record too
        interviews = test_db.execute(
            select(Interview).where(Interview.application_id == result.id)
        ).scalars().all()
        assert len(interviews) >= 1

    def test_create_from_offer(self, test_db):
        """OFFER email should create an application with 'offer' status."""
        service = ApplicationService(test_db)
        parsed = ParsedEmail(
            email_type=EmailType.OFFER,
            company="OfferCorp",
            position="Senior PM",
            confidence=0.9,
        )
        result = service.create_from_email(parsed)
        assert result is not None
        assert result.company == "OfferCorp"
        assert result.status == "offer"


class TestCompanyExtractionPunctuation:
    """Task 8: Trailing punctuation should not break company extraction."""

    def test_trailing_exclamation_stripped(self):
        """'Thank you for applying to Cint!' should extract 'Cint'."""
        parser = EmailParser()
        email = _make_email(
            subject="Thank you for applying to Cint!",
            from_address="noreply@cint.com",
        )
        result = parser.parse(email)
        assert result.company is not None
        assert "!" not in result.company

    def test_trailing_period_stripped(self):
        """'Thank you for your interest in Acme.' should extract 'Acme'."""
        parser = EmailParser()
        email = _make_email(
            subject="Thank you for your interest in Acme.",
            from_address="noreply@acme.com",
        )
        result = parser.parse(email)
        assert result.company is not None
        assert "." not in result.company

    def test_clean_company_name_strips_punctuation(self):
        """_clean_company_name should strip trailing punctuation."""
        parser = EmailParser()
        assert parser._clean_company_name("Cint!") == "Cint"
        assert parser._clean_company_name("Acme.") == "Acme"
        assert parser._clean_company_name("Test Co,") == "Test Co"


class TestSelfSentFiltering:
    """Task 9: Self-sent emails should be classified as UNKNOWN."""

    def test_self_sent_email_is_unknown(self):
        """Emails from the user's own address should be UNKNOWN."""
        parser = EmailParser(user_email="sam@gmail.com")
        email = _make_email(
            subject="Fwd: Interview with Company",
            from_address="sam@gmail.com",
            body_text="Forwarding this for my records",
        )
        result = parser.parse(email)
        assert result.email_type == EmailType.UNKNOWN

    def test_non_self_email_still_classified(self):
        """Emails from other addresses should still be classified normally."""
        parser = EmailParser(user_email="sam@gmail.com")
        email = _make_email(
            subject="Thank you for applying to TestCo",
            from_address="noreply@testco.com",
            body_text="We received your application.",
        )
        result = parser.parse(email)
        assert result.email_type != EmailType.UNKNOWN

    def test_no_user_email_skips_check(self):
        """Without user_email set, self-sent filtering is skipped."""
        parser = EmailParser()  # No user_email
        email = _make_email(
            subject="Thank you for applying to TestCo",
            from_address="sam@gmail.com",
            body_text="We received your application.",
        )
        result = parser.parse(email)
        # Should still classify normally since no user_email filter
        assert result.email_type != EmailType.UNKNOWN
