"""Tests for job collectors."""
import pytest
from datetime import datetime

from src.collectors.base import BaseCollector, JobData
from src.collectors.remoteok_collector import RemoteOKCollector
from src.collectors.greenhouse_collector import GreenhouseCollector
from src.collectors.lever_collector import LeverCollector


class TestJobData:
    """Tests for JobData dataclass."""

    def test_create_job_data(self):
        """Test creating JobData."""
        job = JobData(
            title="Product Manager",
            company="Test Co",
            url="https://test.com/jobs/1",
            source="test",
        )

        assert job.title == "Product Manager"
        assert job.company == "Test Co"
        assert job.remote is False  # Default

    def test_job_data_remote_detection_from_location(self):
        """Test automatic remote detection from location."""
        job = JobData(
            title="PM",
            company="Test",
            url="https://test.com",
            source="test",
            location="Remote - US",
        )

        assert job.remote is True

    def test_job_data_with_salary(self):
        """Test JobData with salary info."""
        job = JobData(
            title="PM",
            company="Test",
            url="https://test.com",
            source="test",
            salary_min=150000,
            salary_max=200000,
        )

        assert job.salary_min == 150000
        assert job.salary_max == 200000

    def test_job_data_extra_data(self):
        """Test JobData extra_data field."""
        job = JobData(
            title="PM",
            company="Test",
            url="https://test.com",
            source="test",
            extra_data={"tags": ["ai", "ml"]},
        )

        assert "tags" in job.extra_data
        assert "ai" in job.extra_data["tags"]


class TestRemoteOKCollector:
    """Tests for RemoteOKCollector."""

    def test_collector_name(self):
        """Test collector name."""
        collector = RemoteOKCollector()
        assert collector.name == "remoteok"

    def test_matches_queries(self):
        """Test query matching logic."""
        collector = RemoteOKCollector()

        job_data = {
            "position": "AI Product Manager",
            "company": "Test Co",
            "description": "Machine learning focused role",
            "tags": ["ai", "product"],
        }

        query_terms = ["ai", "product manager"]

        assert collector._matches_queries(job_data, query_terms) is True

    def test_matches_queries_no_match(self):
        """Test query matching with no match."""
        collector = RemoteOKCollector()

        job_data = {
            "position": "Marketing Manager",
            "company": "Test Co",
            "description": "Marketing role",
            "tags": ["marketing"],
        }

        query_terms = ["ai", "machine learning"]

        assert collector._matches_queries(job_data, query_terms) is False


class TestGreenhouseCollector:
    """Tests for GreenhouseCollector."""

    def test_collector_name(self):
        """Test collector name."""
        collector = GreenhouseCollector()
        assert collector.name == "greenhouse"

    def test_default_companies(self):
        """Test default companies list."""
        collector = GreenhouseCollector()
        assert len(collector.companies) > 0
        assert "stripe" in collector.companies

    def test_custom_companies(self):
        """Test custom companies list."""
        collector = GreenhouseCollector(companies=["custom1", "custom2"])
        assert collector.companies == ["custom1", "custom2"]

    def test_matches_queries(self):
        """Test query matching."""
        collector = GreenhouseCollector()

        job = JobData(
            title="AI Product Manager",
            company="Stripe",
            url="https://boards.greenhouse.io/stripe/jobs/123",
            source="greenhouse",
            description="AI and ML experience required",
        )

        query_terms = ["ai", "product"]

        assert collector._matches_queries(job, query_terms) is True


class TestLeverCollector:
    """Tests for LeverCollector."""

    def test_collector_name(self):
        """Test collector name."""
        collector = LeverCollector()
        assert collector.name == "lever"

    def test_default_companies(self):
        """Test default companies list."""
        collector = LeverCollector()
        assert len(collector.companies) > 0
        assert "netflix" in collector.companies

    def test_custom_companies(self):
        """Test custom companies list."""
        collector = LeverCollector(companies=["company1"])
        assert len(collector.companies) == 1
