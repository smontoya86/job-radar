"""Tests for authentication service.

TDD: These tests are written BEFORE the implementation.
Run tests to see them fail, then implement to make them pass.
"""
import pytest
from datetime import datetime, timezone


class TestAuthServiceRegistration:
    """Tests for user registration."""

    def test_register_user_success(self, test_db):
        """User can register with valid email, username, and password."""
        from src.auth.service import AuthService

        service = AuthService(test_db)
        user = service.register(
            email="new@example.com",
            username="newuser",
            password="SecurePass123!",
        )

        assert user.id is not None
        assert user.email == "new@example.com"
        assert user.username == "newuser"
        # Password should be hashed, not stored plain
        assert user.password_hash != "SecurePass123!"
        assert user.password_hash is not None

    def test_register_user_creates_profile(self, test_db):
        """Registration creates an empty user profile."""
        from src.auth.service import AuthService
        from src.persistence.models import UserProfile

        service = AuthService(test_db)
        user = service.register(
            email="new@example.com",
            username="newuser",
            password="SecurePass123!",
        )

        # Profile should exist
        from sqlalchemy import select
        stmt = select(UserProfile).where(UserProfile.user_id == user.id)
        profile = test_db.execute(stmt).scalar_one_or_none()

        assert profile is not None
        assert profile.user_id == user.id

    def test_register_user_duplicate_email_fails(self, test_db):
        """Registration fails for duplicate email."""
        from src.auth.service import AuthService
        from src.auth.exceptions import DuplicateEmailError

        service = AuthService(test_db)

        # First registration succeeds
        service.register(
            email="test@example.com",
            username="user1",
            password="SecurePass123!",
        )

        # Second registration with same email fails
        with pytest.raises(DuplicateEmailError):
            service.register(
                email="test@example.com",
                username="user2",
                password="SecurePass123!",
            )

    def test_register_user_duplicate_username_fails(self, test_db):
        """Registration fails for duplicate username."""
        from src.auth.service import AuthService
        from src.auth.exceptions import DuplicateUsernameError

        service = AuthService(test_db)

        service.register(
            email="user1@example.com",
            username="sameusername",
            password="SecurePass123!",
        )

        with pytest.raises(DuplicateUsernameError):
            service.register(
                email="user2@example.com",
                username="sameusername",
                password="SecurePass123!",
            )

    def test_register_user_weak_password_fails(self, test_db):
        """Registration fails for weak password."""
        from src.auth.service import AuthService
        from src.auth.exceptions import WeakPasswordError

        service = AuthService(test_db)

        # Too short
        with pytest.raises(WeakPasswordError):
            service.register(
                email="test@example.com",
                username="testuser",
                password="weak",
            )

    def test_register_user_password_requirements(self, test_db):
        """Password must meet minimum requirements."""
        from src.auth.service import AuthService
        from src.auth.exceptions import WeakPasswordError

        service = AuthService(test_db)

        # No uppercase
        with pytest.raises(WeakPasswordError):
            service.register(
                email="test@example.com",
                username="testuser",
                password="alllowercase123!",
            )

        # No number
        with pytest.raises(WeakPasswordError):
            service.register(
                email="test2@example.com",
                username="testuser2",
                password="NoNumbers!",
            )

    def test_register_user_invalid_email_fails(self, test_db):
        """Registration fails for invalid email format."""
        from src.auth.service import AuthService
        from src.auth.exceptions import InvalidEmailError

        service = AuthService(test_db)

        with pytest.raises(InvalidEmailError):
            service.register(
                email="not_an_email",
                username="testuser",
                password="SecurePass123!",
            )


class TestAuthServiceLogin:
    """Tests for user login."""

    def test_authenticate_success(self, test_db):
        """User can authenticate with correct credentials."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        # Register user first
        service.register(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!",
        )

        # Authenticate
        user = service.authenticate(
            email="test@example.com",
            password="SecurePass123!",
        )

        assert user is not None
        assert user.email == "test@example.com"

    def test_authenticate_wrong_password_fails(self, test_db):
        """Authentication fails with wrong password."""
        from src.auth.service import AuthService
        from src.auth.exceptions import InvalidCredentialsError

        service = AuthService(test_db)

        service.register(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!",
        )

        with pytest.raises(InvalidCredentialsError):
            service.authenticate(
                email="test@example.com",
                password="WrongPassword123!",
            )

    def test_authenticate_nonexistent_user_fails(self, test_db):
        """Authentication fails for non-existent user."""
        from src.auth.service import AuthService
        from src.auth.exceptions import InvalidCredentialsError

        service = AuthService(test_db)

        with pytest.raises(InvalidCredentialsError):
            service.authenticate(
                email="nonexistent@example.com",
                password="SomePassword123!",
            )

    def test_authenticate_updates_last_login(self, test_db):
        """Successful authentication updates last_login timestamp."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        user = service.register(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!",
        )

        initial_login = user.last_login
        initial_count = user.login_count

        # Authenticate
        user = service.authenticate(
            email="test@example.com",
            password="SecurePass123!",
        )

        assert user.last_login is not None
        assert user.login_count == initial_count + 1

    def test_authenticate_inactive_user_fails(self, test_db):
        """Authentication fails for deactivated user."""
        from src.auth.service import AuthService
        from src.auth.exceptions import AccountDisabledError

        service = AuthService(test_db)

        user = service.register(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!",
        )

        # Deactivate user
        user.is_active = False
        test_db.commit()

        with pytest.raises(AccountDisabledError):
            service.authenticate(
                email="test@example.com",
                password="SecurePass123!",
            )


class TestAuthServiceGoogleOAuth:
    """Tests for Google OAuth authentication."""

    def test_authenticate_google_new_user(self, test_db):
        """Google OAuth creates new user if not exists."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        user = service.authenticate_google(
            google_id="google_123",
            email="newuser@gmail.com",
            name="New User",
        )

        assert user is not None
        assert user.email == "newuser@gmail.com"
        assert user.google_id == "google_123"
        assert user.password_hash is None  # OAuth users don't have passwords

    def test_authenticate_google_existing_user(self, test_db):
        """Google OAuth links to existing user by email."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        # Create user with password first
        existing_user = service.register(
            email="user@gmail.com",
            username="existinguser",
            password="SecurePass123!",
        )

        # OAuth with same email
        user = service.authenticate_google(
            google_id="google_456",
            email="user@gmail.com",
            name="Existing User",
        )

        assert user.id == existing_user.id
        assert user.google_id == "google_456"

    def test_authenticate_google_returns_existing_by_google_id(self, test_db):
        """Google OAuth returns existing user by Google ID."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        # First OAuth login
        user1 = service.authenticate_google(
            google_id="google_789",
            email="user@gmail.com",
            name="User",
        )

        # Second OAuth login with same Google ID
        user2 = service.authenticate_google(
            google_id="google_789",
            email="user@gmail.com",
            name="User",
        )

        assert user1.id == user2.id


class TestAuthServicePasswordReset:
    """Tests for password reset functionality."""

    def test_create_password_reset_token(self, test_db):
        """Can create a password reset token."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        user = service.register(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!",
        )

        token = service.create_password_reset_token(email="test@example.com")

        assert token is not None
        assert len(token) > 20  # Token should be reasonably long

    def test_reset_password_with_valid_token(self, test_db):
        """Can reset password with valid token."""
        from src.auth.service import AuthService

        service = AuthService(test_db)

        service.register(
            email="test@example.com",
            username="testuser",
            password="OldPassword123!",
        )

        token = service.create_password_reset_token(email="test@example.com")
        service.reset_password(token=token, new_password="NewPassword456!")

        # Should be able to login with new password
        user = service.authenticate(
            email="test@example.com",
            password="NewPassword456!",
        )
        assert user is not None

    def test_reset_password_invalid_token_fails(self, test_db):
        """Password reset fails with invalid token."""
        from src.auth.service import AuthService
        from src.auth.exceptions import InvalidTokenError

        service = AuthService(test_db)

        with pytest.raises(InvalidTokenError):
            service.reset_password(
                token="invalid_token",
                new_password="NewPassword456!",
            )


class TestPasswordHashing:
    """Tests for password hashing utilities."""

    def test_hash_password(self):
        """Password is hashed correctly."""
        from src.auth.service import hash_password, verify_password

        password = "SecurePass123!"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 50  # bcrypt hashes are long
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_password_correct(self):
        """Correct password verifies successfully."""
        from src.auth.service import hash_password, verify_password

        password = "SecurePass123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Incorrect password fails verification."""
        from src.auth.service import hash_password, verify_password

        password = "SecurePass123!"
        hashed = hash_password(password)

        assert verify_password("WrongPassword!", hashed) is False
