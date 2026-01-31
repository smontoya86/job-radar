"""Pytest fixtures for Job Radar tests."""
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.persistence.models import Application, Base, Job, Resume


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
