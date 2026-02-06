"""Tests for SQL injection prevention.

TDD: These tests ensure SQLAlchemy parameterized queries prevent SQL injection.
"""
import pytest
from datetime import datetime, timezone


class TestSQLInjectionPrevention:
    """Tests that SQL injection attacks are prevented."""

    # Common SQL injection payloads
    SQL_INJECTION_PAYLOADS = [
        "'; DROP TABLE users; --",
        "1; DROP TABLE jobs; --",
        "' OR '1'='1",
        "' OR 1=1 --",
        "admin'--",
        "1' OR '1'='1' /*",
        "'; SELECT * FROM users; --",
        "' UNION SELECT * FROM users --",
        "'; INSERT INTO users (email) VALUES ('hacker@evil.com'); --",
        "'; UPDATE users SET is_admin=1 WHERE email='",
        "1; DELETE FROM applications; --",
    ]

    def test_user_registration_prevents_sql_injection(self, test_db):
        """SQL injection in registration fields is safely handled."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        for payload in self.SQL_INJECTION_PAYLOADS:
            try:
                # Try injection in email (should fail validation, not SQL)
                service.register(
                    email=payload,
                    username="testuser",
                    password="SecurePass123!",
                )
            except Exception as e:
                # Should be validation error, not SQL error
                assert "SQL" not in str(e).upper()
                assert "sqlite3" not in str(e).lower()

    def test_user_login_prevents_sql_injection(self, test_db):
        """SQL injection in login fields is safely handled."""
        from src.auth.service import AuthService
        from src.auth.exceptions import InvalidCredentialsError

        service = AuthService(test_db)

        # Create a valid user first
        service.register(
            email="valid@example.com",
            username="validuser",
            password="SecurePass123!",
        )

        for payload in self.SQL_INJECTION_PAYLOADS:
            try:
                # Try injection in email field
                service.authenticate(
                    email=payload,
                    password="SomePassword123!",
                )
            except InvalidCredentialsError:
                # Expected - credentials don't match
                pass
            except Exception as e:
                # Should not be a SQL error
                assert "SQL" not in str(e).upper()
                assert "sqlite3" not in str(e).lower()

    def test_job_query_prevents_sql_injection(self, test_db):
        """SQL injection in job queries is safely handled."""
        from src.persistence.models import User, Job
        from sqlalchemy import select

        user = User(email="user@example.com", username="user")
        test_db.add(user)
        test_db.commit()

        # Create a valid job
        job = Job(
            title="PM",
            company="Test Company",
            url="https://test.com/job",
            source="test",
            user_id=user.id,
        )
        test_db.add(job)
        test_db.commit()

        for payload in self.SQL_INJECTION_PAYLOADS:
            # Try to use injection payload as a filter value
            # SQLAlchemy should parameterize this safely
            stmt = select(Job).where(Job.company == payload)
            result = test_db.execute(stmt).scalars().all()

            # Should return empty list, not execute injection
            assert len(result) == 0

            # Database should still be intact
            all_jobs = test_db.execute(select(Job)).scalars().all()
            assert len(all_jobs) == 1

    def test_user_query_prevents_sql_injection(self, test_db):
        """SQL injection in user queries is safely handled."""
        from src.persistence.models import User
        from sqlalchemy import select

        # Create a valid user
        user = User(email="user@example.com", username="user")
        test_db.add(user)
        test_db.commit()

        for payload in self.SQL_INJECTION_PAYLOADS:
            # Try to use injection payload in email lookup
            stmt = select(User).where(User.email == payload)
            result = test_db.execute(stmt).scalar_one_or_none()

            # Should return None, not execute injection
            assert result is None

            # Database should still be intact
            all_users = test_db.execute(select(User)).scalars().all()
            assert len(all_users) == 1

    def test_application_query_prevents_sql_injection(self, test_db):
        """SQL injection in application queries is safely handled."""
        from src.persistence.models import User, Application
        from sqlalchemy import select

        user = User(email="user@example.com", username="user")
        test_db.add(user)
        test_db.commit()

        # Create a valid application
        app = Application(
            company="Test Company",
            position="PM",
            user_id=user.id,
            applied_date=datetime.now(timezone.utc),
        )
        test_db.add(app)
        test_db.commit()

        for payload in self.SQL_INJECTION_PAYLOADS:
            # Try injection in company filter
            stmt = select(Application).where(Application.company == payload)
            result = test_db.execute(stmt).scalars().all()

            # Should return empty, not execute injection
            assert len(result) == 0

            # Database should still be intact
            all_apps = test_db.execute(select(Application)).scalars().all()
            assert len(all_apps) == 1

    def test_like_query_prevents_sql_injection(self, test_db):
        """SQL injection in LIKE queries is safely handled."""
        from src.persistence.models import User, Job
        from sqlalchemy import select

        user = User(email="user@example.com", username="user")
        test_db.add(user)
        test_db.commit()

        job = Job(
            title="PM",
            company="Test Company",
            url="https://test.com/job",
            source="test",
            user_id=user.id,
        )
        test_db.add(job)
        test_db.commit()

        # LIKE queries with wildcards could be dangerous
        dangerous_like_payloads = [
            "%'; DROP TABLE jobs; --",
            "Test%' OR '1'='1",
            "_'; DELETE FROM users; --",
        ]

        for payload in dangerous_like_payloads:
            stmt = select(Job).where(Job.company.like(payload))
            result = test_db.execute(stmt).scalars().all()

            # Should return empty, not execute injection
            assert len(result) == 0

            # Database still intact
            all_jobs = test_db.execute(select(Job)).scalars().all()
            assert len(all_jobs) == 1


class TestLikeWildcardEscaping:
    """Tests that LIKE wildcard characters are properly escaped in ApplicationService."""

    def test_percent_wildcard_escaped_in_company_search(self, test_db):
        """Searching for '%' should not match all companies."""
        from src.persistence.models import Application
        from src.tracking.application_service import ApplicationService

        app = Application(
            company="Acme Corp",
            position="PM",
            applied_date=datetime.now(timezone.utc),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)

        # Searching with bare "%" should NOT match "Acme Corp"
        results = service.get_all_applications(company="%")
        assert len(results) == 0

    def test_underscore_wildcard_escaped_in_company_search(self, test_db):
        """Searching with '_' should not act as a single-char wildcard."""
        from src.persistence.models import Application
        from src.tracking.application_service import ApplicationService

        app = Application(
            company="AB Corp",
            position="PM",
            applied_date=datetime.now(timezone.utc),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)

        # "_B" should NOT match "AB" (underscore = literal, not single-char wildcard)
        results = service.get_all_applications(company="_B")
        assert len(results) == 0

    def test_find_application_by_company_escapes_wildcards(self, test_db):
        """_find_application_by_company escapes LIKE wildcards."""
        from src.persistence.models import Application
        from src.tracking.application_service import ApplicationService

        app = Application(
            company="Test Company",
            position="PM",
            applied_date=datetime.now(timezone.utc),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)

        # These should NOT match via wildcard exploitation
        assert service._find_application_by_company("%") is None
        assert service._find_application_by_company("_est") is None

    def test_escape_like_static_method(self, test_db):
        """_escape_like correctly escapes special characters."""
        from src.tracking.application_service import ApplicationService

        assert ApplicationService._escape_like("hello%world") == r"hello\%world"
        assert ApplicationService._escape_like("test_company") == r"test\_company"
        assert ApplicationService._escape_like("normal") == "normal"


class TestInputSanitization:
    """Tests for input sanitization in auth service."""

    def test_email_normalized_on_registration(self, test_db):
        """Email is normalized (lowercased, trimmed) on registration."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        user = service.register(
            email="  TEST@EXAMPLE.COM  ",
            username="testuser",
            password="SecurePass123!",
        )

        assert user.email == "test@example.com"

    def test_email_normalized_on_login(self, test_db):
        """Email is normalized on login attempt."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        service.register(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!",
        )

        # Login with different casing should work
        user = service.authenticate(
            email="TEST@EXAMPLE.COM",
            password="SecurePass123!",
        )

        assert user is not None
        assert user.email == "test@example.com"

    def test_username_trimmed_on_registration(self, test_db):
        """Username is trimmed on registration."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        user = service.register(
            email="test@example.com",
            username="  testuser  ",
            password="SecurePass123!",
        )

        assert user.username == "testuser"
