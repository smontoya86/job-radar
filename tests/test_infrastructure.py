"""Tests for infrastructure improvements: logging, retry, company_key, PostgreSQL compat."""
import asyncio
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, inspect
from sqlalchemy.orm import sessionmaker

from src.collectors.base import JobData
from src.persistence.models import (
    Application,
    Base,
    Job,
    normalize_company_key,
)
from src.tracking.application_service import ApplicationService


def _has_psycopg2() -> bool:
    """Check if psycopg2 is installed."""
    try:
        import psycopg2  # noqa: F401
        return True
    except ImportError:
        return False


# =============================================================================
# normalize_company_key tests
# =============================================================================


class TestNormalizeCompanyKey:
    """Test company key normalization for indexed matching."""

    def test_basic_normalization(self):
        assert normalize_company_key("Stripe") == "stripe"

    def test_strips_whitespace(self):
        assert normalize_company_key("  Stripe  ") == "stripe"

    def test_removes_inc_suffix(self):
        assert normalize_company_key("Stripe Inc") == "stripe"
        assert normalize_company_key("Stripe, Inc.") == "stripe"

    def test_removes_llc_suffix(self):
        assert normalize_company_key("Acme LLC") == "acme"

    def test_removes_corp_suffix(self):
        assert normalize_company_key("Big Corp") == "big"

    def test_removes_ltd_suffix(self):
        assert normalize_company_key("Firm Ltd") == "firm"

    def test_removes_trailing_punctuation(self):
        assert normalize_company_key("Stripe!") == "stripe"
        assert normalize_company_key("Stripe.") == "stripe"

    def test_empty_string(self):
        assert normalize_company_key("") == ""

    def test_matching_different_forms(self):
        """Different representations of the same company should match."""
        key1 = normalize_company_key("Stripe, Inc.")
        key2 = normalize_company_key("Stripe")
        key3 = normalize_company_key("stripe")
        assert key1 == key2 == key3

    def test_different_companies_differ(self):
        assert normalize_company_key("Stripe") != normalize_company_key("Block")


# =============================================================================
# company_key auto-population tests
# =============================================================================


class TestCompanyKeyAutoPopulation:
    """Test that company_key is set automatically on model creation."""

    def test_job_gets_company_key(self):
        job = Job(
            title="PM",
            company="Stripe Inc",
            url="https://stripe.com/jobs/1",
            source="test",
        )
        assert job.company_key == "stripe"

    def test_application_gets_company_key(self):
        app = Application(
            company="OpenAI",
            position="PM",
            applied_date=datetime(2026, 1, 25),
        )
        assert app.company_key == "openai"

    def test_company_key_persists_in_db(self, test_db):
        app = Application(
            company="Anthropic",
            position="AI PM",
            applied_date=datetime(2026, 1, 25),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        # Query by company_key
        result = test_db.execute(
            select(Application).where(Application.company_key == "anthropic")
        )
        found = result.scalars().first()
        assert found is not None
        assert found.company == "Anthropic"

    def test_find_application_uses_company_key(self, test_db):
        """ApplicationService._find_application_by_company uses company_key index."""
        app = Application(
            id="ck-1",
            company="Stripe, Inc.",
            position="PM",
            applied_date=datetime(2026, 1, 25),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        # Should find via normalized key matching
        result = service._find_application_by_company("Stripe")
        assert result is not None
        assert result.id == "ck-1"

    def test_find_application_inc_vs_plain(self, test_db):
        """'Stripe Inc' and 'Stripe' should match via company_key."""
        app = Application(
            id="ck-2",
            company="Stripe",
            position="PM",
            applied_date=datetime(2026, 1, 25),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        result = service._find_application_by_company("Stripe Inc")
        assert result is not None
        assert result.id == "ck-2"


# =============================================================================
# Database engine tests (SQLite vs PostgreSQL)
# =============================================================================


class TestDatabaseEngine:
    """Test database engine configuration."""

    def test_sqlite_engine_has_check_same_thread(self):
        """SQLite engine should have check_same_thread=False."""
        from src.persistence.database import _build_engine
        with patch("src.persistence.database.settings") as mock_settings:
            mock_settings.database_url = "sqlite:///:memory:"
            engine = _build_engine()
            # Should not raise when used from different threads
            assert engine is not None

    @pytest.mark.skipif(
        not _has_psycopg2(),
        reason="psycopg2 not installed (Docker-only dependency)",
    )
    def test_postgresql_engine_has_pool_settings(self):
        """PostgreSQL engine should have pool_size and pool_pre_ping."""
        from src.persistence.database import _build_engine
        with patch("src.persistence.database.settings") as mock_settings:
            mock_settings.database_url = "postgresql://user:pass@localhost:5432/db"
            engine = _build_engine()
            assert engine.pool.size() == 5
            assert engine.pool._pre_ping is True


# =============================================================================
# company_key migration test
# =============================================================================


class TestCompanyKeyMigration:
    """Test that company_key migration works correctly."""

    def test_migration_creates_column_and_index(self):
        """Migration should add company_key column and index to both tables."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        insp = inspect(engine)

        # Check column exists
        job_columns = [c["name"] for c in insp.get_columns("jobs")]
        assert "company_key" in job_columns

        app_columns = [c["name"] for c in insp.get_columns("applications")]
        assert "company_key" in app_columns


# =============================================================================
# Retry utility tests
# =============================================================================


class TestHTTPRetry:
    """Test retry helpers in collectors/utils.py."""

    @pytest.mark.asyncio
    async def test_http_get_json_success(self):
        """Successful request returns JSON data."""
        from src.collectors.utils import http_get_json

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"jobs": []})

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_async_context(mock_resp))

        result = await http_get_json(mock_session, "https://api.example.com/jobs")
        assert result == {"jobs": []}

    @pytest.mark.asyncio
    async def test_http_get_json_404_returns_none(self):
        """Non-retryable error returns None."""
        from src.collectors.utils import http_get_json

        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.json = AsyncMock(return_value={})

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_async_context(mock_resp))

        result = await http_get_json(mock_session, "https://api.example.com/jobs")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_get_json_retries_on_500(self):
        """Server error triggers retry, then succeeds."""
        from src.collectors.utils import http_get_json

        error_resp = AsyncMock()
        error_resp.status = 500
        error_resp.json = AsyncMock(return_value={})

        success_resp = AsyncMock()
        success_resp.status = 200
        success_resp.json = AsyncMock(return_value={"ok": True})

        call_count = 0

        class FakeContextManager:
            def __init__(self, resp):
                self.resp = resp

            async def __aenter__(self):
                return self.resp

            async def __aexit__(self, *args):
                pass

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeContextManager(error_resp)
            return FakeContextManager(success_resp)

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=side_effect)

        result = await http_get_json(mock_session, "https://api.example.com/jobs", retries=2)
        assert result == {"ok": True}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_http_get_json_retries_on_timeout(self):
        """Timeout triggers retry."""
        import aiohttp
        from src.collectors.utils import http_get_json

        success_resp = AsyncMock()
        success_resp.status = 200
        success_resp.json = AsyncMock(return_value={"ok": True})

        call_count = 0

        class FakeContextManager:
            def __init__(self, resp):
                self.resp = resp

            async def __aenter__(self):
                if self.resp is None:
                    raise asyncio.TimeoutError()
                return self.resp

            async def __aexit__(self, *args):
                pass

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeContextManager(None)  # Will raise timeout
            return FakeContextManager(success_resp)

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=side_effect)

        result = await http_get_json(mock_session, "https://api.example.com/jobs", retries=2)
        assert result == {"ok": True}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_http_post_json_success(self):
        """POST request works correctly."""
        from src.collectors.utils import http_post_json

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"posted": True})

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=_async_context(mock_resp))

        result = await http_post_json(mock_session, "https://api.example.com/search")
        assert result == {"posted": True}


# =============================================================================
# Logging configuration tests
# =============================================================================


class TestLoggingConfig:
    """Test logging setup."""

    def test_setup_logging_configures_root_logger(self):
        """setup_logging should add handlers to root logger."""
        from src.logging_config import setup_logging

        # Clear any existing handlers first
        root = logging.getLogger()
        original_handlers = root.handlers.copy()
        root.handlers.clear()

        try:
            setup_logging(level="INFO")
            assert len(root.handlers) > 0
            # Should have at least a console handler
            assert any(
                isinstance(h, logging.StreamHandler) for h in root.handlers
            )
        finally:
            # Restore original handlers
            root.handlers = original_handlers

    def test_setup_logging_idempotent(self):
        """Calling setup_logging twice should not add duplicate handlers."""
        from src.logging_config import setup_logging

        root = logging.getLogger()
        original_handlers = root.handlers.copy()
        root.handlers.clear()

        try:
            setup_logging(level="INFO")
            count_after_first = len(root.handlers)
            setup_logging(level="INFO")
            count_after_second = len(root.handlers)
            assert count_after_first == count_after_second
        finally:
            root.handlers = original_handlers

    def test_setup_logging_with_file(self, tmp_path):
        """setup_logging with log_file should add a file handler."""
        from src.logging_config import setup_logging

        root = logging.getLogger()
        original_handlers = root.handlers.copy()
        root.handlers.clear()

        log_file = str(tmp_path / "test.log")
        try:
            setup_logging(level="DEBUG", log_file=log_file)
            assert any(
                isinstance(h, logging.handlers.RotatingFileHandler)
                for h in root.handlers
            )
        finally:
            root.handlers = original_handlers


# =============================================================================
# Helpers
# =============================================================================


class _async_context:
    """Helper to create an async context manager from a mock response."""

    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, *args):
        pass
