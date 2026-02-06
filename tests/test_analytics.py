"""Tests for analytics modules."""
import pytest
from datetime import datetime

from src.analytics.funnel import FunnelAnalytics, FunnelStage, FunnelData
from src.analytics.source_analysis import SourceAnalytics
from src.analytics.resume_analysis import ResumeAnalytics
from src.persistence.models import Application, Interview, EmailImport, Resume


class TestFunnelAnalytics:
    """Tests for FunnelAnalytics."""

    def test_funnel_stages_structure(self):
        """Test that FUNNEL_STAGES has correct structure (2 elements per tuple)."""
        for stage in FunnelAnalytics.FUNNEL_STAGES:
            assert len(stage) == 2, f"Stage {stage} should have exactly 2 elements"
            status, name = stage
            assert isinstance(status, str)
            assert isinstance(name, str)

    def test_get_funnel_empty(self, test_db):
        """Test funnel with no applications."""
        funnel = FunnelAnalytics(test_db)
        data = funnel.get_funnel()

        assert isinstance(data, FunnelData)
        assert data.total_applications == 0
        assert len(data.stages) == len(FunnelAnalytics.FUNNEL_STAGES)

    def test_get_funnel_with_applications(self, test_db, multiple_applications):
        """Test funnel with multiple applications."""
        funnel = FunnelAnalytics(test_db)
        data = funnel.get_funnel()

        assert data.total_applications == 6
        assert len(data.stages) > 0

        # Check that stages are FunnelStage objects
        for stage in data.stages:
            assert isinstance(stage, FunnelStage)
            assert isinstance(stage.name, str)
            assert isinstance(stage.count, int)
            assert isinstance(stage.percentage, float)

    def test_get_response_rate(self, test_db, multiple_applications):
        """Test response rate calculation."""
        funnel = FunnelAnalytics(test_db)
        rate = funnel.get_response_rate()

        # 4 out of 6 have responses (screening, interview, rejected, offer)
        assert rate > 0
        assert rate <= 100

    def test_get_active_pipeline_count(self, test_db, multiple_applications):
        """Test active pipeline count."""
        funnel = FunnelAnalytics(test_db)
        count = funnel.get_active_pipeline_count()

        # Should exclude rejected
        assert count < 6

    def test_get_conversion_rates(self, test_db, multiple_applications):
        """Test conversion rate calculation."""
        funnel = FunnelAnalytics(test_db)
        conversions = funnel.get_conversion_rates()

        assert isinstance(conversions, dict)
        for key, value in conversions.items():
            assert "->" in key
            assert isinstance(value, float)

    def test_get_weekly_applications(self, test_db, multiple_applications):
        """Test weekly application aggregation."""
        funnel = FunnelAnalytics(test_db)
        weekly = funnel.get_weekly_applications(weeks=4)

        assert isinstance(weekly, list)
        for week in weekly:
            assert "week_start" in week
            assert "count" in week


    def test_funnel_counts_rejected_after_interview(self, test_db):
        """Test that apps rejected after interviewing still appear in interview funnel stage."""
        apps = [
            Application(id="f-1", company="StillApplied", position="PM", applied_date=datetime(2026, 1, 20), status="applied"),
            Application(id="f-2", company="Interviewed", position="PM", applied_date=datetime(2026, 1, 21), status="rejected", rejected_at="interviewing"),
            Application(id="f-3", company="PhoneScreened", position="PM", applied_date=datetime(2026, 1, 22), status="rejected", rejected_at="phone_screen"),
            Application(id="f-4", company="ActiveInterview", position="PM", applied_date=datetime(2026, 1, 23), status="interviewing"),
        ]
        for app in apps:
            test_db.add(app)
        test_db.commit()

        funnel = FunnelAnalytics(test_db)
        data = funnel.get_funnel()

        assert data.total_applications == 4

        stage_dict = {s.name: s.count for s in data.stages}
        # All 4 are "Applied" (cumulative)
        assert stage_dict["Applied"] == 4
        # f-2 (rejected_at=interviewing), f-3 (rejected_at=phone_screen), f-4 (interviewing) = 3 reached phone_screen+
        assert stage_dict["Phone Screen"] == 3
        # f-2 (rejected_at=interviewing) + f-4 (currently interviewing) = 2 reached interviewing
        assert stage_dict["Interviewing"] == 2

    def test_interview_rate_includes_rejected_after_interview(self, test_db):
        """Test that interview rate counts apps rejected after interviewing."""
        apps = [
            Application(id="r-1", company="A", position="PM", applied_date=datetime(2026, 1, 1), status="applied"),
            Application(id="r-2", company="B", position="PM", applied_date=datetime(2026, 1, 2), status="rejected", rejected_at="applied"),
            Application(id="r-3", company="C", position="PM", applied_date=datetime(2026, 1, 3), status="rejected", rejected_at="phone_screen"),
            Application(id="r-4", company="D", position="PM", applied_date=datetime(2026, 1, 4), status="rejected", rejected_at="interviewing"),
        ]
        for app in apps:
            test_db.add(app)
        test_db.commit()

        funnel = FunnelAnalytics(test_db)
        rate = funnel.get_interview_rate()

        # r-3 (phone_screen) + r-4 (interviewing) = 2 out of 4 = 50%
        assert rate == 50.0

    def test_funnel_uses_interview_records_as_signal(self, test_db):
        """Test that Interview records boost a rejected app's effective stage."""
        app = Application(id="ir-1", company="InterviewCo", position="PM", applied_date=datetime(2026, 1, 1), status="rejected", rejected_at="applied")
        test_db.add(app)
        test_db.flush()

        # Add an interview record
        interview = Interview(application_id="ir-1", type="Phone Screen", round=1, outcome="pending")
        test_db.add(interview)
        test_db.commit()

        funnel = FunnelAnalytics(test_db)
        data = funnel.get_funnel()

        stage_dict = {s.name: s.count for s in data.stages}
        # Despite rejected_at="applied", the Interview record should elevate to phone_screen
        assert stage_dict["Phone Screen"] == 1

    def test_funnel_uses_interview_emails_as_signal(self, test_db):
        """Test that linked interview_invite emails boost a rejected app's effective stage."""
        app = Application(id="ie-1", company="EmailCo", position="PM", applied_date=datetime(2026, 1, 1), status="rejected", rejected_at="applied")
        test_db.add(app)
        test_db.flush()

        # Add a linked interview_invite email
        email = EmailImport(
            application_id="ie-1",
            gmail_message_id="msg-123",
            email_type="interview_invite",
            subject="Interview with EmailCo",
            from_address="hr@emailco.com",
            received_at=datetime(2026, 1, 5),
            processed=True,
        )
        test_db.add(email)
        test_db.commit()

        funnel = FunnelAnalytics(test_db)
        data = funnel.get_funnel()

        stage_dict = {s.name: s.count for s in data.stages}
        assert stage_dict["Phone Screen"] == 1


class TestSourceAnalytics:
    """Tests for SourceAnalytics."""

    def test_get_source_stats_empty(self, test_db):
        """Test source stats with no applications."""
        analytics = SourceAnalytics(test_db)
        stats = analytics.get_source_stats()

        assert isinstance(stats, list)
        assert len(stats) == 0

    def test_get_source_stats_with_data(self, test_db):
        """Test source stats with applications from different sources."""
        # Create applications from different sources
        apps = [
            Application(company="A", position="PM", applied_date=datetime.now(), source="linkedin", status="applied"),
            Application(company="B", position="PM", applied_date=datetime.now(), source="linkedin", status="interview"),
            Application(company="C", position="PM", applied_date=datetime.now(), source="referral", status="offer"),
        ]
        for app in apps:
            test_db.add(app)
        test_db.commit()

        analytics = SourceAnalytics(test_db)
        stats = analytics.get_source_stats()

        assert len(stats) == 2  # linkedin and referral

        # Check stats structure
        for stat in stats:
            assert hasattr(stat, "source")
            assert hasattr(stat, "total_applications")
            assert hasattr(stat, "response_rate")
            assert hasattr(stat, "interview_rate")

    def test_get_source_comparison(self, test_db):
        """Test source comparison data."""
        analytics = SourceAnalytics(test_db)
        comparison = analytics.get_source_comparison()

        assert isinstance(comparison, dict)
        assert "sources" in comparison


class TestResumeAnalytics:
    """Tests for ResumeAnalytics."""

    def test_get_resume_stats_empty(self, test_db):
        """Test resume stats with no data."""
        analytics = ResumeAnalytics(test_db)
        stats = analytics.get_resume_stats()

        assert isinstance(stats, list)

    def test_get_resume_stats_with_data(self, test_db, sample_resume):
        """Test resume stats with applications."""
        # Create applications using the resume
        apps = [
            Application(company="A", position="PM", applied_date=datetime.now(), resume_id=sample_resume.id, status="applied"),
            Application(company="B", position="PM", applied_date=datetime.now(), resume_id=sample_resume.id, status="interview"),
        ]
        for app in apps:
            test_db.add(app)
        test_db.commit()

        analytics = ResumeAnalytics(test_db)
        stats = analytics.get_resume_stats()

        assert len(stats) == 1
        assert stats[0].total_applications == 2
        assert stats[0].resume.id == sample_resume.id

    def test_get_no_resume_stats(self, test_db):
        """Test stats for applications without resume."""
        # Create application without resume
        app = Application(company="A", position="PM", applied_date=datetime.now(), status="applied")
        test_db.add(app)
        test_db.commit()

        analytics = ResumeAnalytics(test_db)
        stats = analytics.get_no_resume_stats()

        assert stats["total"] == 1
