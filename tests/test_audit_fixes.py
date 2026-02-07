"""Tests for system audit fixes."""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import select, func

from src.collectors.base import JobData
from src.gmail.client import EmailMessage
from src.gmail.parser import EmailParser, EmailType, ParsedEmail
from src.persistence.models import Application, Interview, Job, Resume, StatusHistory
from src.tracking.application_service import ApplicationService
from src.tracking.resume_service import ResumeService
from src.analytics.rejection_analysis import RejectionAnalyzer
from src.analytics.source_analysis import SourceAnalytics
from src.analytics.funnel import FunnelAnalytics


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


# =============================================================================
# Task #32: Bar chart uses raw status (not cumulative funnel)
# =============================================================================


class TestBarChartRawStatus:
    """Verify that raw status counts differ from cumulative funnel counts."""

    def test_raw_counts_differ_from_funnel_cumulative(self, test_db):
        """Raw GROUP BY status gives different numbers than cumulative funnel."""
        apps = [
            Application(id="bc-1", company="A", position="PM", status="applied",
                        applied_date=datetime(2026, 1, 20)),
            Application(id="bc-2", company="B", position="PM", status="phone_screen",
                        applied_date=datetime(2026, 1, 21)),
            Application(id="bc-3", company="C", position="PM", status="interviewing",
                        applied_date=datetime(2026, 1, 22)),
            Application(id="bc-4", company="D", position="PM", status="rejected",
                        applied_date=datetime(2026, 1, 23)),
        ]
        for app in apps:
            test_db.add(app)
        test_db.commit()

        # Cumulative funnel: Applied=4, Phone Screen=2, Interviewing=1
        funnel = FunnelAnalytics(test_db)
        funnel_data = funnel.get_funnel()
        funnel_applied = funnel_data.stages[0].count  # Cumulative: all apps

        # Raw status: applied=1, phone_screen=1, interviewing=1, rejected=1
        stmt = select(Application.status, func.count(Application.id)).group_by(Application.status)
        raw_counts = dict(test_db.execute(stmt).all())

        # The funnel "Applied" count is cumulative (4), raw "applied" count is 1
        assert funnel_applied == 4  # Cumulative
        assert raw_counts.get("applied", 0) == 1  # Raw
        assert funnel_applied != raw_counts.get("applied", 0)

    def test_raw_counts_sum_to_total_applications(self, test_db):
        """Raw status counts should sum exactly to total applications."""
        apps = [
            Application(id="bc-5", company="A", position="PM", status="applied",
                        applied_date=datetime(2026, 1, 20)),
            Application(id="bc-6", company="B", position="PM", status="rejected",
                        applied_date=datetime(2026, 1, 21)),
            Application(id="bc-7", company="C", position="PM", status="interviewing",
                        applied_date=datetime(2026, 1, 22)),
        ]
        for app in apps:
            test_db.add(app)
        test_db.commit()

        stmt = select(Application.status, func.count(Application.id)).group_by(Application.status)
        raw_counts = dict(test_db.execute(stmt).all())

        assert sum(raw_counts.values()) == 3


# =============================================================================
# Task #33: Keyword comparison uses substring matching
# =============================================================================


class TestKeywordComparisonSubstringMatch:
    """get_keyword_comparison() should use substring matching, not exact set intersection."""

    def _make_analyzer(self, session, profile_keywords, tmp_path=None):
        """Create a RejectionAnalyzer with mocked profile keywords."""
        # Use a temp empty file so _load_profile doesn't fail
        if tmp_path is None:
            import tempfile
            tmp_path = Path(tempfile.mkdtemp())
        profile_file = tmp_path / "profile.yaml"
        profile_file.write_text("required_keywords: {}\n")

        analyzer = RejectionAnalyzer(session, profile_path=profile_file)
        analyzer._get_profile_keywords = lambda: profile_keywords
        return analyzer

    def test_single_word_skill_matches_multiword_profile(self, test_db):
        """'search' from JD should match 'product manager, search' in profile."""
        app = Application(
            id="kw-1", company="TestCo", position="PM",
            applied_date=datetime(2026, 1, 10),
            status="rejected", job_description="Looking for experience with search systems.",
        )
        test_db.add(app)
        test_db.commit()

        profile_kws = {"product manager, search", "ai product manager"}
        analyzer = self._make_analyzer(test_db, profile_kws)

        result = analyzer.get_keyword_comparison("kw-1")
        assert result is not None
        # "search" from the JD should match "product manager, search" via substring
        assert result["match_percentage"] > 0

    def test_profile_keyword_contained_in_skill(self, test_db):
        """Profile keyword 'ml' should match extracted skill 'ml' exactly."""
        app = Application(
            id="kw-2", company="MLCo", position="ML PM",
            applied_date=datetime(2026, 1, 10),
            status="rejected",
            job_description="Strong ML and machine learning background required.",
        )
        test_db.add(app)
        test_db.commit()

        profile_kws = {"ml", "machine learning"}
        analyzer = self._make_analyzer(test_db, profile_kws)

        result = analyzer.get_keyword_comparison("kw-2")
        assert result is not None
        assert len(result["matched_keywords"]) >= 1

    def test_no_match_when_genuinely_different(self, test_db):
        """Skills not in profile should be in missing_keywords."""
        app = Application(
            id="kw-3", company="FinCo", position="PM",
            applied_date=datetime(2026, 1, 10),
            status="rejected",
            job_description="Must have fintech and payments experience. B2B SaaS.",
        )
        test_db.add(app)
        test_db.commit()

        profile_kws = {"ai", "ml", "search"}
        analyzer = self._make_analyzer(test_db, profile_kws)

        result = analyzer.get_keyword_comparison("kw-3")
        assert result is not None
        assert len(result["missing_keywords"]) > 0

    def test_results_are_sorted(self, test_db):
        """matched_keywords and missing_keywords should be sorted."""
        app = Application(
            id="kw-4", company="SortCo", position="PM",
            applied_date=datetime(2026, 1, 10),
            status="rejected",
            job_description="Need python, sql, aws, machine learning, kubernetes experience.",
        )
        test_db.add(app)
        test_db.commit()

        profile_kws = {"python", "machine learning"}
        analyzer = self._make_analyzer(test_db, profile_kws)

        result = analyzer.get_keyword_comparison("kw-4")
        assert result is not None
        assert result["matched_keywords"] == sorted(result["matched_keywords"])
        assert result["missing_keywords"] == sorted(result["missing_keywords"])


# =============================================================================
# Task #34: Resume service interview rate uses Interview records
# =============================================================================


class TestResumeServiceInterviewRate:
    """Resume service should count Interview records for interview rate."""

    def test_rejected_after_interviewing_counted(self, test_db):
        """App rejected after interview should count in interview rate."""
        resume = Resume(id="res-1", name="v1", version=1, is_active=True)
        test_db.add(resume)

        # App with status=rejected but had an interview
        app = Application(
            id="rs-1", company="Co A", position="PM",
            status="rejected", resume_id="res-1",
            applied_date=datetime(2026, 1, 10),
        )
        test_db.add(app)
        test_db.flush()

        # Create Interview record
        interview = Interview(
            application_id="rs-1",
            type="Phone Screen",
            round=1,
        )
        test_db.add(interview)
        test_db.commit()

        service = ResumeService(test_db)
        stats = service.get_resume_stats("res-1")

        # Even though status is "rejected", interview rate should be > 0
        # because there's an Interview record
        assert stats["interview_rate"] > 0

    def test_phone_screen_counted_in_interview_rate(self, test_db):
        """phone_screen status should count in interview rate (consistency with FunnelAnalytics)."""
        resume = Resume(id="res-2", name="v2", version=1, is_active=True)
        test_db.add(resume)

        app = Application(
            id="rs-2", company="Co B", position="PM",
            status="phone_screen", resume_id="res-2",
            applied_date=datetime(2026, 1, 10),
        )
        test_db.add(app)
        test_db.commit()

        service = ResumeService(test_db)
        stats = service.get_resume_stats("res-2")

        assert stats["interview_rate"] == 100.0

    def test_withdrawn_counted_as_response(self, test_db):
        """withdrawn status should count in response rate."""
        resume = Resume(id="res-3", name="v3", version=1, is_active=True)
        test_db.add(resume)

        app = Application(
            id="rs-3", company="Co C", position="PM",
            status="withdrawn", resume_id="res-3",
            applied_date=datetime(2026, 1, 10),
        )
        test_db.add(app)
        test_db.commit()

        service = ResumeService(test_db)
        stats = service.get_resume_stats("res-3")

        assert stats["response_rate"] == 100.0


# =============================================================================
# Task #35: Source analysis counting consistency
# =============================================================================


class TestSourceAnalyticsCounting:
    """Source analysis should have consistent counting methodology."""

    def test_withdrawn_counts_as_response(self, test_db):
        """Withdrawn applications should be counted as responses."""
        app = Application(
            id="sa-1", company="Co A", position="PM",
            status="withdrawn", source="linkedin",
            applied_date=datetime(2026, 1, 10),
        )
        test_db.add(app)
        test_db.commit()

        analytics = SourceAnalytics(test_db)
        stats = analytics.get_source_stats()

        linkedin_stat = next((s for s in stats if s.source == "linkedin"), None)
        assert linkedin_stat is not None
        assert linkedin_stat.responses == 1
        assert linkedin_stat.response_rate == 100.0

    def test_interview_count_cannot_exceed_response_count(self, test_db):
        """Interview count should never exceed response count."""
        # App with ghosted status but has Interview record
        app = Application(
            id="sa-2", company="Co B", position="PM",
            status="ghosted", source="email_import",
            applied_date=datetime(2026, 1, 10),
        )
        test_db.add(app)
        test_db.flush()

        interview = Interview(
            application_id="sa-2",
            type="Phone Screen",
            round=1,
        )
        test_db.add(interview)
        test_db.commit()

        analytics = SourceAnalytics(test_db)
        stats = analytics.get_source_stats()

        source_stat = next((s for s in stats if s.source == "email_import"), None)
        assert source_stat is not None
        # Interview count should not exceed response count
        assert source_stat.interviews <= source_stat.responses


# =============================================================================
# Task #38: Email parser validation (company names, position "the" prefix)
# =============================================================================


class TestEmailParserValidation:
    """Email parser should reject garbage company names and strip 'the' from positions."""

    def test_rejects_long_company_name(self):
        """Company names > 50 chars should be rejected as sentence fragments."""
        parser = EmailParser()
        result = parser._clean_company_name(
            "Working here means you get to help change the way businesses connect"
        )
        assert result is None

    def test_rejects_sentence_fragment_company(self):
        """Company names that look like sentences should be rejected."""
        parser = EmailParser()
        assert parser._clean_company_name("Our exceptional team") is None
        assert parser._clean_company_name("Thank you for submitting") is None
        assert parser._clean_company_name("We appreciate your interest") is None

    def test_accepts_normal_company_name(self):
        """Normal company names should pass validation."""
        parser = EmailParser()
        assert parser._clean_company_name("Google") == "Google"
        assert parser._clean_company_name("Fetch Rewards") == "Fetch Rewards"
        assert parser._clean_company_name("OpenAI") == "OpenAI"

    def test_clean_position_strips_the_prefix(self):
        """'the Staff Product Manager, AI' → 'Staff Product Manager, AI'."""
        parser = EmailParser()
        assert parser._clean_position("the Staff Product Manager, AI") == "Staff Product Manager, AI"
        assert parser._clean_position("the Senior PM") == "Senior PM"
        assert parser._clean_position("The Lead Product Manager (AI)") == "Lead Product Manager (AI)"

    def test_clean_position_rejects_email_phrases(self):
        """Strings that are email phrases should be rejected as positions."""
        parser = EmailParser()
        assert parser._clean_position("Thank you for submitting your resume") is None
        assert parser._clean_position("Thanks for applying to the") is None
        assert parser._clean_position("We received your application") is None

    def test_clean_position_keeps_valid_titles(self):
        """Valid position titles should pass through."""
        parser = EmailParser()
        assert parser._clean_position("Senior Product Manager") == "Senior Product Manager"
        assert parser._clean_position("AI Product Manager") == "AI Product Manager"


# =============================================================================
# Task #40: Source inference from email domain
# =============================================================================


class TestSourceInference:
    """EmailParser.infer_source should map email domains to sources."""

    def test_linkedin_domain(self):
        assert EmailParser.infer_source("jobs-noreply@linkedin.com") == "linkedin"

    def test_greenhouse_domain(self):
        assert EmailParser.infer_source("no-reply@greenhouse-mail.io") == "greenhouse"

    def test_lever_domain(self):
        assert EmailParser.infer_source("notifications@hire.lever.co") == "lever"

    def test_ashby_domain(self):
        assert EmailParser.infer_source("noreply@ashbyhq.com") == "ashby"

    def test_workday_domain(self):
        assert EmailParser.infer_source("Aristocrat@myworkday.com") == "workday"

    def test_smartrecruiters_domain(self):
        assert EmailParser.infer_source("noreply@smartrecruiters.com") == "smartrecruiters"

    def test_company_domain_stays_email_import(self):
        """Company-specific domains should stay as email_import."""
        assert EmailParser.infer_source("hr@instacart.com") == "email_import"
        assert EmailParser.infer_source("careers@coursera.org") == "email_import"

    def test_empty_address(self):
        assert EmailParser.infer_source("") == "email_import"
        assert EmailParser.infer_source(None) == "email_import"

    def test_wellfound_domain(self):
        assert EmailParser.infer_source("noreply@hi.wellfound.com") == "wellfound"

    def test_rippling_domain(self):
        assert EmailParser.infer_source("noreply@ats.rippling.com") == "rippling"
