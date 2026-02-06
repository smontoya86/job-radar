"""Tests for User and UserProfile models.

TDD: These tests are written BEFORE the implementation.
Run tests to see them fail, then implement to make them pass.
"""
import pytest
from datetime import datetime, timezone

# Note: These imports will fail until models are created
# This is expected in TDD - tests come first


class TestUserModel:
    """Tests for the User model."""

    def test_create_user_with_email_and_password(self, test_db):
        """User can be created with email, username, and password hash."""
        from src.persistence.models import User

        user = User(
            email="test@example.com",
            username="testuser",
            password_hash="hashed_password_here",
        )
        test_db.add(user)
        test_db.commit()

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.password_hash == "hashed_password_here"

    def test_user_has_default_values(self, test_db):
        """User has sensible defaults for optional fields."""
        from src.persistence.models import User

        user = User(
            email="test@example.com",
            username="testuser",
        )
        test_db.add(user)
        test_db.commit()

        assert user.is_active is True
        assert user.is_admin is False
        assert user.is_superuser is False
        assert user.tier == "free"
        assert user.login_count == 0
        assert user.google_id is None
        assert user.created_at is not None

    def test_user_email_must_be_unique(self, test_db):
        """Two users cannot have the same email."""
        from sqlalchemy.exc import IntegrityError
        from src.persistence.models import User

        user1 = User(email="same@example.com", username="user1")
        test_db.add(user1)
        test_db.commit()

        user2 = User(email="same@example.com", username="user2")
        test_db.add(user2)

        with pytest.raises(IntegrityError):
            test_db.commit()

    def test_user_username_must_be_unique(self, test_db):
        """Two users cannot have the same username."""
        from sqlalchemy.exc import IntegrityError
        from src.persistence.models import User

        user1 = User(email="user1@example.com", username="sameusername")
        test_db.add(user1)
        test_db.commit()

        user2 = User(email="user2@example.com", username="sameusername")
        test_db.add(user2)

        with pytest.raises(IntegrityError):
            test_db.commit()

    def test_user_google_id_can_be_null(self, test_db):
        """Google ID is optional (for email/password users)."""
        from src.persistence.models import User

        user = User(
            email="test@example.com",
            username="testuser",
            password_hash="hashed",
            google_id=None,
        )
        test_db.add(user)
        test_db.commit()

        assert user.google_id is None

    def test_user_google_id_must_be_unique_when_set(self, test_db):
        """If Google ID is set, it must be unique."""
        from sqlalchemy.exc import IntegrityError
        from src.persistence.models import User

        user1 = User(
            email="user1@example.com",
            username="user1",
            google_id="google_123",
        )
        test_db.add(user1)
        test_db.commit()

        user2 = User(
            email="user2@example.com",
            username="user2",
            google_id="google_123",
        )
        test_db.add(user2)

        with pytest.raises(IntegrityError):
            test_db.commit()

    def test_user_can_be_admin(self, test_db):
        """User can be marked as admin."""
        from src.persistence.models import User

        user = User(
            email="admin@example.com",
            username="admin",
            is_admin=True,
        )
        test_db.add(user)
        test_db.commit()

        assert user.is_admin is True

    def test_user_tracks_last_login(self, test_db):
        """User can track last login time."""
        from src.persistence.models import User

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        login_time = datetime.now(timezone.utc)
        user.last_login = login_time
        user.login_count += 1
        test_db.commit()

        # SQLite stores datetime without timezone, so compare without tzinfo
        assert user.last_login.replace(tzinfo=None) == login_time.replace(tzinfo=None)
        assert user.login_count == 1


class TestUserProfileModel:
    """Tests for the UserProfile model."""

    def test_create_user_profile(self, test_db):
        """UserProfile can be created and linked to User."""
        from src.persistence.models import User, UserProfile

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        profile = UserProfile(
            user_id=user.id,
            target_titles={"primary": ["PM"], "secondary": []},
            required_keywords={"primary": ["AI"], "secondary": []},
        )
        test_db.add(profile)
        test_db.commit()

        assert profile.id is not None
        assert profile.user_id == user.id

    def test_user_profile_stores_json_data(self, test_db):
        """UserProfile stores JSON data correctly."""
        from src.persistence.models import User, UserProfile

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        profile_data = {
            "target_titles": {"primary": ["AI PM", "Senior PM"], "secondary": ["ML PM"]},
            "required_keywords": {"primary": ["AI", "ML"], "secondary": ["GenAI"]},
            "negative_keywords": ["junior", "intern"],
            "compensation": {"min_salary": 150000, "max_salary": 250000},
            "location": {"preferred": ["Remote"], "remote_only": True},
            "target_companies": {"tier1": ["OpenAI"], "tier2": ["Stripe"]},
        }

        profile = UserProfile(
            user_id=user.id,
            target_titles=profile_data["target_titles"],
            required_keywords=profile_data["required_keywords"],
            negative_keywords=profile_data["negative_keywords"],
            compensation=profile_data["compensation"],
            location=profile_data["location"],
            target_companies=profile_data["target_companies"],
        )
        test_db.add(profile)
        test_db.commit()

        # Reload from DB
        test_db.refresh(profile)

        assert profile.target_titles == profile_data["target_titles"]
        assert profile.compensation["min_salary"] == 150000
        assert profile.location["remote_only"] is True

    def test_user_has_one_profile(self, test_db):
        """User can have only one profile (one-to-one)."""
        from sqlalchemy.exc import IntegrityError
        from src.persistence.models import User, UserProfile

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        profile1 = UserProfile(user_id=user.id)
        test_db.add(profile1)
        test_db.commit()

        profile2 = UserProfile(user_id=user.id)
        test_db.add(profile2)

        with pytest.raises(IntegrityError):
            test_db.commit()

    def test_user_profile_notification_preferences(self, test_db):
        """UserProfile stores notification preferences."""
        from src.persistence.models import User, UserProfile

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        profile = UserProfile(
            user_id=user.id,
            in_app_notifications=True,
            email_digest_enabled=True,
            email_digest_frequency="daily",
            slack_notifications=False,
            min_score_for_notification=60,
        )
        test_db.add(profile)
        test_db.commit()

        assert profile.in_app_notifications is True
        assert profile.email_digest_frequency == "daily"
        assert profile.min_score_for_notification == 60

    def test_user_profile_integration_tokens(self, test_db):
        """UserProfile stores encrypted integration tokens."""
        from src.persistence.models import User, UserProfile

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        profile = UserProfile(
            user_id=user.id,
            slack_webhook_url="https://hooks.slack.com/services/xxx",
            gmail_token="encrypted_token_data_here",
        )
        test_db.add(profile)
        test_db.commit()

        assert profile.slack_webhook_url is not None
        assert profile.gmail_token is not None


class TestUserRelationships:
    """Tests for User relationships with other models."""

    def test_user_has_jobs_relationship(self, test_db):
        """User can have many jobs."""
        from src.persistence.models import User, Job

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        job = Job(
            title="PM",
            company="Test",
            url="https://test.com",
            source="test",
            user_id=user.id,
        )
        test_db.add(job)
        test_db.commit()

        # Reload user to get relationship
        test_db.refresh(user)

        assert len(user.jobs) == 1
        assert user.jobs[0].title == "PM"

    def test_user_has_applications_relationship(self, test_db):
        """User can have many applications."""
        from src.persistence.models import User, Application

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        app = Application(
            company="Test Corp",
            position="PM",
            user_id=user.id,
            applied_date=datetime.now(timezone.utc),
        )
        test_db.add(app)
        test_db.commit()

        test_db.refresh(user)

        assert len(user.applications) == 1
        assert user.applications[0].company == "Test Corp"

    def test_deleting_user_cascades_to_profile(self, test_db):
        """Deleting user also deletes their profile."""
        from src.persistence.models import User, UserProfile

        user = User(email="test@example.com", username="testuser")
        test_db.add(user)
        test_db.commit()

        profile = UserProfile(user_id=user.id)
        test_db.add(profile)
        test_db.commit()

        profile_id = profile.id

        # Delete user
        test_db.delete(user)
        test_db.commit()

        # Profile should also be deleted
        from sqlalchemy import select
        stmt = select(UserProfile).where(UserProfile.id == profile_id)
        result = test_db.execute(stmt).scalar_one_or_none()
        assert result is None
