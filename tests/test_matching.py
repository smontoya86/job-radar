"""Tests for matching and scoring modules."""
import pytest
import tempfile
import yaml
from pathlib import Path

from src.collectors.base import JobData
from src.matching.keyword_matcher import KeywordMatcher, MatchResult
from src.matching.scorer import JobScorer, ScoredJob


@pytest.fixture
def test_profile():
    """Create a test profile YAML file."""
    profile = {
        "target_titles": {
            "primary": ["AI Product Manager", "Senior AI Product Manager"],
            "secondary": ["Product Manager, AI"],
        },
        "required_keywords": {
            "primary": ["AI", "ML", "machine learning", "search"],
            "secondary": ["product manager", "LLM"],
        },
        "negative_keywords": ["junior", "intern"],
        "compensation": {
            "min_salary": 150000,
            "max_salary": 250000,
            "flexible": True,
        },
        "location": {
            "remote_only": False,
        },
        "target_companies": {
            "tier1": ["OpenAI", "Anthropic"],
            "tier2": ["Stripe"],
            "tier3": ["Spotify"],
        },
        "scoring": {
            "title_match": 0.35,
            "keyword_match": 0.30,
            "company_tier": 0.15,
            "salary_match": 0.10,
            "remote_match": 0.10,
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(profile, f)
        yield f.name

    # Cleanup
    Path(f.name).unlink()


@pytest.fixture
def sample_job_data():
    """Create sample JobData for testing."""
    return JobData(
        title="Senior AI Product Manager",
        company="Anthropic",
        url="https://anthropic.com/jobs/1",
        source="greenhouse",
        location="Remote",
        description="Looking for an AI PM with ML and search experience.",
        salary_min=180000,
        salary_max=220000,
        remote=True,
    )


class TestKeywordMatcher:
    """Tests for KeywordMatcher."""

    def test_load_profile(self, test_profile):
        """Test loading profile from YAML."""
        matcher = KeywordMatcher(test_profile)
        assert len(matcher.primary_keywords) == 4
        assert len(matcher.negative_keywords) == 2

    def test_match_positive(self, test_profile, sample_job_data):
        """Test matching a good job."""
        matcher = KeywordMatcher(test_profile)
        result = matcher.match(sample_job_data)

        assert result.matched is True
        assert result.score > 0
        assert "AI" in result.matched_primary
        assert result.matched_company_tier == 1  # Anthropic is tier 1

    def test_match_negative_keyword(self, test_profile):
        """Test that negative keywords cause rejection."""
        matcher = KeywordMatcher(test_profile)

        job = JobData(
            title="Junior AI Product Manager",
            company="Unknown Co",
            url="https://test.com",
            source="test",
            description="Entry level AI PM position",
        )

        result = matcher.match(job)
        assert result.matched is False
        assert "junior" in result.negative_matches

    def test_match_no_keywords(self, test_profile):
        """Test job with no matching keywords."""
        matcher = KeywordMatcher(test_profile)

        job = JobData(
            title="Marketing Manager",
            company="Random Co",
            url="https://test.com",
            source="test",
            description="Marketing position",
        )

        result = matcher.match(job)
        assert result.matched is False
        assert len(result.matched_primary) == 0

    def test_title_match(self, test_profile, sample_job_data):
        """Test title matching."""
        matcher = KeywordMatcher(test_profile)
        result = matcher.match(sample_job_data)

        assert result.matched_title is True

    def test_company_tier_detection(self, test_profile):
        """Test company tier detection."""
        matcher = KeywordMatcher(test_profile)

        # Tier 1
        job1 = JobData(title="PM", company="OpenAI", url="http://test.com", source="test", description="AI role")
        result1 = matcher.match(job1)
        assert result1.matched_company_tier == 1

        # Tier 2
        job2 = JobData(title="PM", company="Stripe", url="http://test.com", source="test", description="AI role")
        result2 = matcher.match(job2)
        assert result2.matched_company_tier == 2

        # Unknown company
        job3 = JobData(title="PM", company="Unknown", url="http://test.com", source="test", description="AI role")
        result3 = matcher.match(job3)
        assert result3.matched_company_tier is None

    def test_get_search_queries(self, test_profile):
        """Test search query generation."""
        matcher = KeywordMatcher(test_profile)
        queries = matcher.get_search_queries()

        assert len(queries) > 0
        assert "AI Product Manager" in queries


class TestJobScorer:
    """Tests for JobScorer."""

    def test_score_jobs(self, test_profile, sample_job_data):
        """Test scoring a list of jobs."""
        matcher = KeywordMatcher(test_profile)
        scorer = JobScorer(matcher, min_score=0)

        jobs = [sample_job_data]
        scored = scorer.score_jobs(jobs)

        assert len(scored) == 1
        assert isinstance(scored[0], ScoredJob)
        assert scored[0].score > 0

    def test_filter_by_min_score(self, test_profile, sample_job_data):
        """Test filtering by minimum score."""
        matcher = KeywordMatcher(test_profile)
        scorer = JobScorer(matcher, min_score=90)  # High threshold

        jobs = [sample_job_data]
        scored = scorer.score_jobs(jobs)

        # May or may not pass depending on score
        assert all(s.score >= 90 for s in scored)

    def test_fingerprint_generation(self, test_profile, sample_job_data):
        """Test fingerprint generation."""
        matcher = KeywordMatcher(test_profile)
        scorer = JobScorer(matcher)

        fingerprint = scorer._generate_fingerprint(sample_job_data)
        assert "anthropic" in fingerprint.lower()
        assert "senior ai product manager" in fingerprint.lower()

    def test_get_top_jobs(self, test_profile):
        """Test getting top N jobs."""
        matcher = KeywordMatcher(test_profile)
        scorer = JobScorer(matcher, min_score=0)

        jobs = [
            JobData(title="AI PM", company="A", url="http://a.com", source="test", description="AI ML search"),
            JobData(title="AI PM", company="B", url="http://b.com", source="test", description="AI"),
            JobData(title="AI PM", company="C", url="http://c.com", source="test", description="AI ML"),
        ]

        scored = scorer.score_jobs(jobs)
        top = scorer.get_top_jobs(scored, n=2)

        assert len(top) <= 2

    def test_sorted_by_score(self, test_profile):
        """Test that results are sorted by score descending."""
        matcher = KeywordMatcher(test_profile)
        scorer = JobScorer(matcher, min_score=0)

        jobs = [
            JobData(title="PM", company="Unknown", url="http://a.com", source="test", description="AI"),
            JobData(title="AI PM", company="Anthropic", url="http://b.com", source="test", description="AI ML search LLM"),
        ]

        scored = scorer.score_jobs(jobs)

        if len(scored) > 1:
            assert scored[0].score >= scored[1].score


class TestDescriptionCentricScoring:
    """Tests for the description-centric scoring algorithm."""

    def test_description_heavy_beats_title_only(self, test_profile):
        """
        A generic title with AI-heavy description should score well.
        This is the key behavior change - description matters more than title.
        """
        matcher = KeywordMatcher(test_profile)
        scorer = JobScorer(matcher, min_score=0)

        # Job A: Great title, weak description
        job_title_only = JobData(
            title="AI Product Manager",
            company="Unknown Co",
            url="http://a.com",
            source="test",
            description="Looking for a product manager to join our team. Great benefits.",
        )

        # Job B: Generic title, AI-heavy description
        job_desc_heavy = JobData(
            title="Staff Product Manager",
            company="Unknown Co",
            url="http://b.com",
            source="test",
            description="""
            We're looking for a PM to lead our AI and ML initiatives.
            You'll work on search, personalization, and recommendations.
            Experience with LLM, machine learning, and AI required.
            This role focuses on AI-powered features and ML infrastructure.
            """,
        )

        result_title = matcher.match(job_title_only)
        result_desc = matcher.match(job_desc_heavy)

        # Both should match
        assert result_title.matched is True
        assert result_desc.matched is True

        # Description-heavy job should have higher keyword count
        assert result_desc.description_keyword_count > result_title.description_keyword_count

        # Description-heavy job should score competitively (within 20 points or higher)
        # The key is that a generic title doesn't tank the score anymore
        assert result_desc.score >= result_title.score - 20

    def test_keyword_variety_bonus(self, test_profile):
        """Jobs mentioning multiple different keywords should score higher."""
        matcher = KeywordMatcher(test_profile)

        # Job with variety: AI, ML, search
        job_variety = JobData(
            title="Product Manager",
            company="Test Co",
            url="http://a.com",
            source="test",
            description="Work on AI, ML, and search features.",
        )

        # Job with repetition: AI, AI, AI
        job_repetition = JobData(
            title="Product Manager",
            company="Test Co",
            url="http://b.com",
            source="test",
            description="Work on AI. More AI. Even more AI.",
        )

        result_variety = matcher.match(job_variety)
        result_repetition = matcher.match(job_repetition)

        # Variety should have more unique keywords
        assert result_variety.description_keyword_variety >= result_repetition.description_keyword_variety

    def test_partial_title_credit(self, test_profile):
        """Related titles should get partial credit even without exact match."""
        matcher = KeywordMatcher(test_profile)

        # Exact match title
        job_exact = JobData(
            title="AI Product Manager",
            company="Test Co",
            url="http://a.com",
            source="test",
            description="AI role",
        )

        # Related title (has "Product Manager" and seniority)
        job_partial = JobData(
            title="Senior Product Manager",
            company="Test Co",
            url="http://b.com",
            source="test",
            description="AI role",
        )

        result_exact = matcher.match(job_exact)
        result_partial = matcher.match(job_partial)

        # Exact should have full title match
        assert result_exact.matched_title is True

        # Partial should have some title relevance score
        assert result_partial.title_partial_match > 0

    def test_description_keywords_tracked(self, test_profile):
        """Verify description keyword count and variety are tracked."""
        matcher = KeywordMatcher(test_profile)

        job = JobData(
            title="Product Manager",
            company="Test Co",
            url="http://a.com",
            source="test",
            description="AI and ML role. More AI mentioned. Search experience needed.",
        )

        result = matcher.match(job)

        # Should track keyword mentions
        assert result.description_keyword_count >= 3  # AI, ML, AI, search
        assert result.description_keyword_variety >= 3  # AI, ML, search
