"""Tests for analytics modules."""
import pytest
from datetime import datetime

from src.analytics.funnel import FunnelAnalytics, FunnelStage, FunnelData
from src.analytics.source_analysis import SourceAnalytics
from src.analytics.resume_analysis import ResumeAnalytics
from src.persistence.models import Application, Resume


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
