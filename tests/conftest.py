"""Pytest fixtures for Job Radar tests."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.persistence.models import Application, Base, Job, Resume


# =============================================================================
# DATABASE FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    return Job(
        id="test-job-1",
        title="Senior AI Product Manager",
        company="Anthropic",
        location="Remote",
        description="We are looking for an AI PM with experience in LLMs and search.",
        salary_min=180000,
        salary_max=220000,
        url="https://anthropic.com/jobs/1",
        source="greenhouse",
        remote=True,
        match_score=85.0,
        matched_keywords=["AI", "LLM", "search"],
        fingerprint="anthropic:senior ai product manager",
        status="new",
    )


@pytest.fixture
def sample_application(test_db):
    """Create a sample application for testing."""
    app = Application(
        id="test-app-1",
        company="OpenAI",
        position="AI Product Manager",
        applied_date=datetime(2026, 1, 25),
        source="linkedin",
        status="applied",
    )
    test_db.add(app)
    test_db.commit()
    return app


@pytest.fixture
def sample_resume(test_db):
    """Create a sample resume for testing."""
    resume = Resume(
        id="test-resume-1",
        name="AI PM v3",
        version=3,
        target_roles=["AI Product Manager", "ML Product Manager"],
        key_changes="Added GenAI experience",
        is_active=True,
    )
    test_db.add(resume)
    test_db.commit()
    return resume


@pytest.fixture
def multiple_applications(test_db):
    """Create multiple applications for funnel testing."""
    # Using simplified statuses: applied, phone_screen, interviewing, offer, accepted, rejected, withdrawn, ghosted
    apps = [
        Application(id="app-1", company="Company A", position="PM", applied_date=datetime(2026, 1, 20), status="applied"),
        Application(id="app-2", company="Company B", position="PM", applied_date=datetime(2026, 1, 21), status="applied"),
        Application(id="app-3", company="Company C", position="PM", applied_date=datetime(2026, 1, 22), status="phone_screen"),
        Application(id="app-4", company="Company D", position="PM", applied_date=datetime(2026, 1, 23), status="interviewing"),
        Application(id="app-5", company="Company E", position="PM", applied_date=datetime(2026, 1, 24), status="rejected"),
        Application(id="app-6", company="Company F", position="PM", applied_date=datetime(2026, 1, 25), status="offer"),
    ]
    for app in apps:
        test_db.add(app)
    test_db.commit()
    return apps


# =============================================================================
# MULTI-USER FIXTURES (For SaaS platform tests)
# =============================================================================

# Note: User and UserProfile models will be added in Phase 1.
# These fixtures are placeholders that will be updated once models exist.

@pytest.fixture
def user_factory(test_db):
    """
    Factory fixture to create test users.

    Usage:
        user1 = user_factory("alice@test.com", "alice")
        user2 = user_factory("bob@test.com", "bob")
    """
    created_users = []

    def _create_user(email: str, username: str, password: str = "TestPass123!", is_admin: bool = False):
        # TODO: Replace with actual User model when created
        # For now, return a mock user dict
        user = {
            "id": str(uuid4()),
            "email": email,
            "username": username,
            "password_hash": f"hashed_{password}",  # Placeholder
            "is_admin": is_admin,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        }
        created_users.append(user)
        return user

    yield _create_user

    # Cleanup (when real model exists, delete from DB)
    created_users.clear()


@pytest.fixture
def test_user(user_factory):
    """Create a single test user."""
    return user_factory("test@example.com", "testuser")


@pytest.fixture
def admin_user(user_factory):
    """Create an admin user for admin tests."""
    return user_factory("admin@jobradar.io", "admin", is_admin=True)


@pytest.fixture
def two_users(user_factory):
    """Create two users for data isolation tests."""
    user_a = user_factory("alice@test.com", "alice")
    user_b = user_factory("bob@test.com", "bob")
    return user_a, user_b


# =============================================================================
# MOCK FIXTURES (For external services)
# =============================================================================

@pytest.fixture
def mock_gmail_client():
    """Mock Gmail API client for tests."""
    with patch("src.gmail.client.GmailClient") as mock:
        mock_instance = MagicMock()
        mock_instance.search_job_emails.return_value = []
        mock_instance.get_message.return_value = None
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_slack_notifier():
    """Mock Slack webhook for tests."""
    with patch("src.notifications.slack_notifier.SlackNotifier") as mock:
        mock_instance = MagicMock()
        mock_instance.notify.return_value = True
        mock_instance.notify_batch.return_value = 0
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_http_session():
    """Mock aiohttp session for collector tests."""
    with patch("aiohttp.ClientSession") as mock:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json.return_value = {}
        mock_response.text.return_value = ""
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock.return_value.__aenter__.return_value = mock_session
        yield mock_session


# =============================================================================
# SECURITY TEST FIXTURES
# =============================================================================

@pytest.fixture
def sql_injection_payloads():
    """Common SQL injection payloads for security testing."""
    return [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "1; SELECT * FROM users",
        "admin'--",
        "' UNION SELECT * FROM users --",
        "1' AND 1=1 --",
        "' OR 1=1 --",
    ]


@pytest.fixture
def xss_payloads():
    """Common XSS payloads for security testing."""
    return [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "<svg onload=alert('XSS')>",
        "'\"><script>alert('XSS')</script>",
    ]


# =============================================================================
# TEMPORARY DIRECTORY FIXTURES
# =============================================================================

@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory with config structure."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return tmp_path


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Create a temporary directory for backups."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir
