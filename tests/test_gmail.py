"""Tests for Gmail integration."""
import pytest
from datetime import datetime

from src.gmail.parser import EmailParser, EmailType, ParsedEmail
from src.gmail.client import EmailMessage


@pytest.fixture
def parser():
    """Create an email parser instance."""
    return EmailParser()


@pytest.fixture
def confirmation_email():
    """Create a sample confirmation email."""
    return EmailMessage(
        id="msg1",
        thread_id="thread1",
        subject="Thank you for applying to Anthropic",
        from_address="jobs@anthropic.com",
        from_name="Anthropic Recruiting",
        to_address="test@gmail.com",
        date=datetime.now(),
        body_text="Thank you for applying to the Product Manager position at Anthropic. We have received your application and will review it shortly.",
        snippet="Thank you for applying",
    )


@pytest.fixture
def rejection_email():
    """Create a sample rejection email."""
    return EmailMessage(
        id="msg2",
        thread_id="thread2",
        subject="Update on your application",
        from_address="recruiting@openai.com",
        from_name="OpenAI",
        to_address="test@gmail.com",
        date=datetime.now(),
        body_text="After careful consideration, we have decided to move forward with other candidates whose experience more closely matches our current needs.",
        snippet="After careful consideration",
    )


@pytest.fixture
def interview_email():
    """Create a sample interview invitation email."""
    return EmailMessage(
        id="msg3",
        thread_id="thread3",
        subject="Next steps - Interview with Stripe",
        from_address="talent@stripe.com",
        from_name="Stripe Talent",
        to_address="test@gmail.com",
        date=datetime.now(),
        body_text="We would like to schedule an interview with you. Please use the following Calendly link to book a time: https://calendly.com/stripe-recruiting/interview",
        snippet="We would like to schedule",
    )


class TestEmailParser:
    """Tests for EmailParser."""

    def test_parse_confirmation_email(self, parser, confirmation_email):
        """Test parsing a confirmation email."""
        result = parser.parse(confirmation_email)

        assert result.email_type == EmailType.CONFIRMATION
        assert result.confidence > 0
        assert result.company is not None

    def test_parse_rejection_email(self, parser, rejection_email):
        """Test parsing a rejection email."""
        result = parser.parse(rejection_email)

        assert result.email_type == EmailType.REJECTION
        assert result.confidence > 0

    def test_parse_interview_email(self, parser, interview_email):
        """Test parsing an interview invitation email."""
        result = parser.parse(interview_email)

        assert result.email_type == EmailType.INTERVIEW_INVITE
        assert result.calendar_link is not None
        assert "calendly" in result.calendar_link.lower()

    def test_extract_company_from_domain(self, parser):
        """Test company extraction from email domain."""
        email = EmailMessage(
            id="test",
            thread_id="test",
            subject="Your application",
            from_address="jobs@anthropic.com",
            from_name="",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="Thank you for applying",
            snippet="",
        )

        result = parser.parse(email)
        assert result.company is not None
        assert "anthropic" in result.company.lower()

    def test_extract_company_from_name(self, parser):
        """Test company extraction from sender name."""
        email = EmailMessage(
            id="test",
            thread_id="test",
            subject="Your application",
            from_address="noreply@greenhouse.io",
            from_name="Stripe Recruiting",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="Thank you for applying to the Product Manager position at Stripe.",
            snippet="",
        )

        result = parser.parse(email)
        # Should extract from body or name, not greenhouse.io
        assert result.company is not None

    def test_is_job_related_true(self, parser, confirmation_email):
        """Test job-related detection for job email."""
        assert parser.is_job_related(confirmation_email) is True

    def test_is_job_related_false(self, parser):
        """Test job-related detection for non-job email."""
        email = EmailMessage(
            id="test",
            thread_id="test",
            subject="Your Amazon order has shipped",
            from_address="shipping@amazon.com",
            from_name="Amazon",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="Your package is on the way!",
            snippet="Your package is on the way",
        )

        assert parser.is_job_related(email) is False

    def test_detect_rejection_stage(self, parser):
        """Test detection of rejection stage."""
        text = "after reviewing your resume, we have decided not to proceed"
        stage = parser._detect_rejection_stage(text)
        assert stage == "resume"

        text = "following your phone interview, we will not be moving forward"
        stage = parser._detect_rejection_stage(text)
        assert stage == "phone_screen"

    def test_extract_calendar_link(self, parser, interview_email):
        """Test calendar link extraction."""
        link = parser._extract_calendar_link(interview_email)
        assert link is not None
        assert "calendly" in link

    def test_unknown_email_type(self, parser):
        """Test parsing an email with unknown type."""
        email = EmailMessage(
            id="test",
            thread_id="test",
            subject="Hello",
            from_address="someone@company.com",
            from_name="Someone",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="Just wanted to say hello!",
            snippet="Just wanted to say hello",
        )

        result = parser.parse(email)
        assert result.email_type == EmailType.UNKNOWN


class TestEmailTypePatterns:
    """Tests for email type detection patterns."""

    def test_confirmation_patterns(self, parser):
        """Test all confirmation patterns."""
        confirmation_texts = [
            "Thank you for applying to our company",
            "We have received your application",
            "Your application has been submitted",
            "Application received for Product Manager",
        ]

        for text in confirmation_texts:
            email_type, confidence = parser._detect_type(text.lower())
            assert email_type == EmailType.CONFIRMATION, f"Failed for: {text}"

    def test_rejection_patterns(self, parser):
        """Test all rejection patterns."""
        rejection_texts = [
            "After careful consideration, we decided to move forward with other candidates",
            "We will not be proceeding with your application",
            "The position has been filled",
            "We regret to inform you",
        ]

        for text in rejection_texts:
            email_type, confidence = parser._detect_type(text.lower())
            assert email_type == EmailType.REJECTION, f"Failed for: {text}"

    def test_referral_not_classified_as_rejection(self, parser):
        """Referral request replies should not be classified as rejection."""
        email = EmailMessage(
            id="test-referral",
            thread_id="test",
            subject="Re: [External] : Sam Montoya Referral Request",
            from_address="delia.cercel-mihaita@oracle.com",
            from_name="Delia Cercel",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="Unfortunately, we don't have any open positions that match your profile at this time.",
            snippet="Unfortunately",
        )

        result = parser.parse(email)
        assert result.email_type != EmailType.REJECTION

    def test_company_extraction_update_on_your_application(self, parser):
        """'An update on your Fontainebleau application' extracts 'Fontainebleau'."""
        email = EmailMessage(
            id="test-fontainebleau",
            thread_id="test",
            subject="An update on your Fontainebleau application",
            from_address="morris@fblasvegas.com",
            from_name="Morris",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="After careful review, we decided to move forward with other candidates.",
            snippet="After careful review",
        )

        result = parser.parse(email)
        assert result.company is not None
        assert "fontainebleau" in result.company.lower()

    def test_company_extraction_follow_up(self, parser):
        """'Aristocrat Follow Up' extracts 'Aristocrat'."""
        email = EmailMessage(
            id="test-aristocrat",
            thread_id="test",
            subject="Aristocrat Follow Up",
            from_address="Aristocrat@myworkday.com",
            from_name="Aristocrat",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="We regret to inform you that we will not be moving forward.",
            snippet="We regret to inform",
        )

        result = parser.parse(email)
        assert result.company is not None
        assert "aristocrat" in result.company.lower()

    def test_company_extraction_ats_sender_prefix(self, parser):
        """ATS sender like 'Aristocrat@myworkday.com' extracts 'Aristocrat'."""
        company = parser._extract_company(EmailMessage(
            id="test",
            thread_id="test",
            subject="Update on your application",
            from_address="Aristocrat@myworkday.com",
            from_name="",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="Unfortunately we are not proceeding.",
            snippet="",
        ))
        assert company is not None
        assert "aristocrat" in company.lower()

    def test_company_extraction_employment_update(self, parser):
        """'Employment Update - World Wide Technology Holding, LLC' extracts company."""
        email = EmailMessage(
            id="test-wwt",
            thread_id="test",
            subject="Employment Update - World Wide Technology Holding, LLC",
            from_address="do-not-reply@candidatecare.com",
            from_name="",
            to_address="test@gmail.com",
            date=datetime.now(),
            body_text="We regret to inform you that the position has been filled.",
            snippet="",
        )

        result = parser.parse(email)
        assert result.company is not None
        assert "world wide technology" in result.company.lower()

    def test_interview_patterns(self, parser):
        """Test all interview patterns."""
        interview_texts = [
            "We would like to schedule an interview",
            "Next steps in the hiring process",
            "Please book a time using calendly.com/company",
            "We'd love to meet with our team",
        ]

        for text in interview_texts:
            email_type, confidence = parser._detect_type(text.lower())
            assert email_type == EmailType.INTERVIEW_INVITE, f"Failed for: {text}"
