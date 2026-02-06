"""Tests for compliant collectors (Phase 5).

Tests parsing logic with mock API responses for each new collector.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.base import JobData
from src.collectors.serpapi_collector import SerpApiCollector
from src.collectors.jsearch_collector import JSearchCollector
from src.collectors.ashby_collector import AshbyCollector
from src.collectors.workday_collector import WorkdayCollector
from src.collectors.smartrecruiters_collector import SmartRecruitersCollector
from src.collectors.search_discovery_collector import SearchDiscoveryCollector
from src.collectors.email_alert_collector import EmailAlertCollector


# ---- SerpApi Collector ----

class TestSerpApiCollector:
    """Tests for SerpApiCollector."""

    def test_skips_without_api_key(self):
        collector = SerpApiCollector(api_key=None)
        result = asyncio.run(collector.collect(["product manager"]))
        assert result == []

    def test_parse_job_basic(self):
        collector = SerpApiCollector(api_key="test")
        data = {
            "title": "Senior Product Manager",
            "company_name": "Anthropic",
            "location": "San Francisco, CA",
            "description": "We are looking for a product manager...",
            "detected_extensions": {},
            "share_link": "https://google.com/jobs/123",
        }
        job = collector._parse_job(data)
        assert job is not None
        assert job.title == "Senior Product Manager"
        assert job.company == "Anthropic"
        assert job.source == "serpapi"
        assert job.location == "San Francisco, CA"

    def test_parse_job_with_salary(self):
        collector = SerpApiCollector(api_key="test")
        data = {
            "title": "PM",
            "company_name": "Test",
            "location": "Remote",
            "description": "Test",
            "detected_extensions": {
                "salary": "$120K-$180K a year",
                "work_from_home": True,
            },
            "share_link": "https://example.com",
        }
        job = collector._parse_job(data)
        assert job is not None
        assert job.salary_min == 120000
        assert job.salary_max == 180000
        assert job.remote is True

    def test_parse_salary_hourly(self):
        collector = SerpApiCollector(api_key="test")
        min_sal, max_sal = collector._parse_salary("$50-$70 an hour")
        assert min_sal == 50 * 2080
        assert max_sal == 70 * 2080

    def test_parse_salary_single_value(self):
        collector = SerpApiCollector(api_key="test")
        min_sal, max_sal = collector._parse_salary("$150,000")
        assert min_sal == 150000
        assert max_sal == 150000

    def test_parse_job_with_apply_options(self):
        collector = SerpApiCollector(api_key="test")
        data = {
            "title": "PM",
            "company_name": "Test",
            "description": "Test",
            "detected_extensions": {},
            "apply_options": [{"link": "https://apply.example.com/job/123"}],
        }
        job = collector._parse_job(data)
        assert job is not None
        assert job.apply_url == "https://apply.example.com/job/123"

    def test_parse_job_returns_none_on_error(self):
        collector = SerpApiCollector(api_key="test")
        job = collector._parse_job(None)  # type: ignore
        assert job is None


# ---- JSearch Collector ----

class TestJSearchCollector:
    """Tests for JSearchCollector."""

    def test_skips_without_api_key(self):
        collector = JSearchCollector(api_key=None)
        result = asyncio.run(collector.collect(["product manager"]))
        assert result == []

    def test_parse_job_basic(self):
        collector = JSearchCollector(api_key="test")
        data = {
            "job_title": "Data Scientist",
            "employer_name": "Google",
            "job_city": "Mountain View",
            "job_state": "CA",
            "job_description": "Looking for a data scientist...",
            "job_apply_link": "https://careers.google.com/job/123",
            "job_is_remote": False,
            "job_posted_at_datetime_utc": "2026-01-15T12:00:00.000Z",
        }
        job = collector._parse_job(data)
        assert job is not None
        assert job.title == "Data Scientist"
        assert job.company == "Google"
        assert job.source == "jsearch"
        assert job.location == "Mountain View, CA"
        assert job.remote is False

    def test_parse_job_remote(self):
        collector = JSearchCollector(api_key="test")
        data = {
            "job_title": "Remote PM",
            "employer_name": "Startup",
            "job_description": "Remote role",
            "job_apply_link": "https://example.com",
            "job_is_remote": True,
        }
        job = collector._parse_job(data)
        assert job is not None
        assert job.remote is True

    def test_parse_job_with_salary(self):
        collector = JSearchCollector(api_key="test")
        data = {
            "job_title": "PM",
            "employer_name": "Test",
            "job_description": "Test",
            "job_apply_link": "https://example.com",
            "job_min_salary": 100000,
            "job_max_salary": 150000,
        }
        job = collector._parse_job(data)
        assert job is not None
        assert job.salary_min == 100000
        assert job.salary_max == 150000


# ---- Ashby Collector ----

class TestAshbyCollector:
    """Tests for AshbyCollector."""

    def test_default_companies(self):
        collector = AshbyCollector()
        assert len(collector.companies) == 20
        assert "ramp" in collector.companies
        assert "anthropic" in collector.companies

    def test_custom_companies(self):
        collector = AshbyCollector(companies=["mycompany"])
        assert collector.companies == ["mycompany"]

    def test_parse_job_basic(self):
        collector = AshbyCollector()
        data = {
            "id": "abc-123",
            "title": "Staff Product Manager",
            "location": "San Francisco, CA",
            "publishedDate": "2026-01-15T00:00:00Z",
            "departmentName": "Product",
        }
        job = collector._parse_job(data, "anthropic")
        assert job is not None
        assert job.title == "Staff Product Manager"
        assert job.company == "Anthropic"
        assert job.source == "ashby"
        assert job.url == "https://jobs.ashbyhq.com/anthropic/abc-123"

    def test_parse_job_remote(self):
        collector = AshbyCollector()
        data = {
            "id": "xyz",
            "title": "PM",
            "location": "Remote (US)",
        }
        job = collector._parse_job(data, "ramp")
        assert job is not None
        assert job.remote is True

    def test_matches_queries(self):
        collector = AshbyCollector()
        job = JobData(
            title="Product Manager, AI",
            company="Test",
            url="https://example.com",
            source="ashby",
        )
        assert collector._matches_queries(job, ["product manager"]) is True
        assert collector._matches_queries(job, ["engineer"]) is False


# ---- Workday Collector ----

class TestWorkdayCollector:
    """Tests for WorkdayCollector."""

    def test_default_companies(self):
        collector = WorkdayCollector()
        assert len(collector.companies) == 10
        assert any(c["name"] == "Amazon" for c in collector.companies)

    def test_parse_job_basic(self):
        collector = WorkdayCollector()
        data = {
            "title": "Product Manager",
            "locationsText": "Seattle, WA",
            "externalPath": "/job/PM-12345",
            "bulletFields": ["Full-time", "Posted 2 days ago"],
        }
        job = collector._parse_job(data, "amazon", "Amazon")
        assert job is not None
        assert job.title == "Product Manager"
        assert job.company == "Amazon"
        assert job.source == "workday"
        assert "/External/job/PM-12345" in job.url

    def test_parse_job_remote(self):
        collector = WorkdayCollector()
        data = {
            "title": "Remote PM",
            "locationsText": "Remote - US",
            "externalPath": "/job/1",
        }
        job = collector._parse_job(data, "test", "Test Corp")
        assert job is not None
        assert job.remote is True

    def test_parse_job_empty_title_returns_none(self):
        collector = WorkdayCollector()
        data = {"title": "", "externalPath": "/job/1"}
        job = collector._parse_job(data, "test", "Test")
        assert job is None


# ---- SmartRecruiters Collector ----

class TestSmartRecruitersCollector:
    """Tests for SmartRecruitersCollector."""

    def test_default_companies(self):
        collector = SmartRecruitersCollector()
        assert len(collector.companies) == 10
        assert "visa" in collector.companies

    def test_name(self):
        collector = SmartRecruitersCollector()
        assert collector.name == "smartrecruiters"


# ---- Search Discovery Collector ----

class TestSearchDiscoveryCollector:
    """Tests for SearchDiscoveryCollector."""

    def test_skips_without_api_key(self):
        collector = SearchDiscoveryCollector(api_key=None)
        result = asyncio.run(collector.collect(["product manager"]))
        assert result == []

    def test_extract_company_greenhouse(self):
        collector = SearchDiscoveryCollector(api_key="test")
        company = collector._extract_company(
            "https://boards.greenhouse.io/anthropic/jobs/123",
            "boards.greenhouse.io",
        )
        assert company == "Anthropic"

    def test_extract_company_lever(self):
        collector = SearchDiscoveryCollector(api_key="test")
        company = collector._extract_company(
            "https://jobs.lever.co/netflix/abc-123",
            "jobs.lever.co",
        )
        assert company == "Netflix"

    def test_extract_company_ashby(self):
        collector = SearchDiscoveryCollector(api_key="test")
        company = collector._extract_company(
            "https://jobs.ashbyhq.com/ramp/job-id",
            "jobs.ashbyhq.com",
        )
        assert company == "Ramp"

    def test_extract_company_unknown(self):
        collector = SearchDiscoveryCollector(api_key="test")
        company = collector._extract_company(
            "https://example.com/random",
            "boards.greenhouse.io",
        )
        assert company == "Unknown"

    def test_parse_result(self):
        collector = SearchDiscoveryCollector(api_key="test")
        result = {
            "link": "https://boards.greenhouse.io/anthropic/jobs/123",
            "title": "Product Manager",
            "snippet": "Join our team...",
        }
        job = collector._parse_result(result, "boards.greenhouse.io")
        assert job is not None
        assert job.source == "search_discovery"
        assert job.company == "Anthropic"

    def test_parse_result_no_link_returns_none(self):
        collector = SearchDiscoveryCollector(api_key="test")
        result = {"link": "", "title": "PM"}
        job = collector._parse_result(result, "boards.greenhouse.io")
        assert job is None


# ---- Email Alert Collector ----

class TestEmailAlertCollector:
    """Tests for EmailAlertCollector."""

    def test_detect_provider_linkedin(self):
        collector = EmailAlertCollector([])
        assert collector._detect_provider(
            "jobs-noreply@linkedin.com", "anything"
        ) == "linkedin"

    def test_detect_provider_google(self):
        collector = EmailAlertCollector([])
        assert collector._detect_provider(
            "noreply@google.com", "new jobs for product manager"
        ) == "google"

    def test_detect_provider_indeed(self):
        collector = EmailAlertCollector([])
        assert collector._detect_provider(
            "alert@indeed.com", "new jobs for you"
        ) == "indeed"

    def test_detect_provider_glassdoor(self):
        collector = EmailAlertCollector([])
        assert collector._detect_provider(
            "noreply@glassdoor.com", "new jobs at top companies"
        ) == "glassdoor"

    def test_detect_provider_unknown(self):
        collector = EmailAlertCollector([])
        assert collector._detect_provider(
            "random@example.com", "hello"
        ) is None

    def test_parse_linkedin_alert(self):
        collector = EmailAlertCollector([])
        html = """
        <div>
          <a href="https://www.linkedin.com/jobs/view/12345">
            Senior Product Manager
          </a>
          <span>Anthropic - San Francisco</span>
        </div>
        """
        jobs = collector._parse_linkedin_alert(html)
        assert len(jobs) == 1
        assert jobs[0].title == "Senior Product Manager"
        assert jobs[0].source == "email_alert:linkedin"
        assert "linkedin.com/jobs/view/12345" in jobs[0].url

    def test_parse_indeed_alert(self):
        collector = EmailAlertCollector([])
        html = """
        <div>
          <a href="https://www.indeed.com/viewjob?jk=abc123">
            Data Scientist
          </a>
        </div>
        """
        jobs = collector._parse_indeed_alert(html)
        assert len(jobs) == 1
        assert jobs[0].source == "email_alert:indeed"

    def test_parse_generic_alert_job_links(self):
        collector = EmailAlertCollector([])
        html = """
        <a href="https://boards.greenhouse.io/anthropic/jobs/123">ML Engineer</a>
        <a href="https://jobs.lever.co/openai/456">Research Scientist</a>
        <a href="https://example.com/not-a-job">Click here</a>
        """
        jobs = collector._parse_generic_alert(html)
        assert len(jobs) == 2

    def test_collect_deduplicates_by_url(self):
        """Same URL from two emails should produce one job."""
        html = '<a href="https://www.linkedin.com/jobs/view/99">PM</a>'
        emails = [
            {"html": html, "subject": "new job", "from_address": "jobs-noreply@linkedin.com"},
            {"html": html, "subject": "new job", "from_address": "jobs-noreply@linkedin.com"},
        ]
        collector = EmailAlertCollector(emails)
        jobs = asyncio.run(collector.collect([]))
        assert len(jobs) == 1

    def test_clean_url_strips_tracking(self):
        collector = EmailAlertCollector([])
        url = "https://www.indeed.com/viewjob?jk=abc&utm_source=email&utm_medium=alert"
        cleaned = collector._clean_url(url, "indeed.com/viewjob")
        assert "utm_source" not in cleaned
        assert "jk=abc" in cleaned


# ---- Cross-collector dedup test ----

class TestCrossCollectorDedup:
    """Test that dedup works across old and new sources."""

    def test_same_fingerprint_different_sources(self):
        """Jobs from different sources with same URL should dedup."""
        from src.dedup.deduplicator import Deduplicator
        from src.matching.keyword_matcher import MatchResult
        from src.matching.scorer import ScoredJob

        # Create scored results from two different sources
        job1 = JobData(
            title="PM at Anthropic",
            company="Anthropic",
            url="https://example.com/job/123",
            source="serpapi",
        )
        job2 = JobData(
            title="PM at Anthropic",
            company="Anthropic",
            url="https://example.com/job/123",
            source="jsearch",
        )

        match1 = MatchResult(
            matched=True,
            score=80.0,
            matched_primary=["AI", "ML"],
        )
        match2 = MatchResult(
            matched=True,
            score=75.0,
            matched_primary=["AI"],
        )

        scored1 = ScoredJob(job=job1, match_result=match1, fingerprint="abc123")
        scored2 = ScoredJob(job=job2, match_result=match2, fingerprint="abc123")

        # Dedup without DB check (in-memory only)
        deduplicator = Deduplicator(session=MagicMock(), lookback_days=30)
        unique = deduplicator.deduplicate([scored1, scored2], check_db=False)
        assert len(unique) == 1
