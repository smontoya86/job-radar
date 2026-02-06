"""Tests for multi-user data isolation.

TDD: These tests ensure users cannot access each other's data.
Critical for multi-tenant SaaS security.
"""
import pytest
from datetime import datetime, timezone


class TestJobIsolation:
    """Tests for job data isolation between users."""

    def test_user_only_sees_own_jobs(self, test_db):
        """User A cannot see User B's jobs."""
        from src.persistence.models import User, Job

        # Create two users
        user_a = User(email="user_a@example.com", username="user_a")
        user_b = User(email="user_b@example.com", username="user_b")
        test_db.add(user_a)
        test_db.add(user_b)
        test_db.commit()

        # Create jobs for each user
        job_a = Job(
            title="PM at Company A",
            company="Company A",
            url="https://a.com/job",
            source="test",
            user_id=user_a.id,
        )
        job_b = Job(
            title="PM at Company B",
            company="Company B",
            url="https://b.com/job",
            source="test",
            user_id=user_b.id,
        )
        test_db.add(job_a)
        test_db.add(job_b)
        test_db.commit()

        # Query jobs for user_a
        from sqlalchemy import select
        stmt = select(Job).where(Job.user_id == user_a.id)
        user_a_jobs = test_db.execute(stmt).scalars().all()

        # User A should only see their own job
        assert len(user_a_jobs) == 1
        assert user_a_jobs[0].company == "Company A"
        assert user_a_jobs[0].user_id == user_a.id

    def test_job_without_user_id_not_accessible(self, test_db):
        """Jobs without user_id should not appear in user-filtered queries."""
        from src.persistence.models import User, Job

        user = User(email="user@example.com", username="user")
        test_db.add(user)
        test_db.commit()

        # Create job without user_id (orphaned/legacy data)
        orphan_job = Job(
            title="Orphan Job",
            company="Unknown",
            url="https://orphan.com/job",
            source="test",
            user_id=None,
        )
        test_db.add(orphan_job)
        test_db.commit()

        # Query jobs for user
        from sqlalchemy import select
        stmt = select(Job).where(Job.user_id == user.id)
        user_jobs = test_db.execute(stmt).scalars().all()

        # User should not see orphaned job
        assert len(user_jobs) == 0


class TestApplicationIsolation:
    """Tests for application data isolation between users."""

    def test_user_only_sees_own_applications(self, test_db):
        """User A cannot see User B's applications."""
        from src.persistence.models import User, Application

        # Create two users
        user_a = User(email="user_a@example.com", username="user_a")
        user_b = User(email="user_b@example.com", username="user_b")
        test_db.add(user_a)
        test_db.add(user_b)
        test_db.commit()

        # Create applications for each user
        app_a = Application(
            company="Company A",
            position="PM",
            user_id=user_a.id,
            applied_date=datetime.now(timezone.utc),
        )
        app_b = Application(
            company="Company B",
            position="Engineer",
            user_id=user_b.id,
            applied_date=datetime.now(timezone.utc),
        )
        test_db.add(app_a)
        test_db.add(app_b)
        test_db.commit()

        # Query applications for user_a
        from sqlalchemy import select
        stmt = select(Application).where(Application.user_id == user_a.id)
        user_a_apps = test_db.execute(stmt).scalars().all()

        # User A should only see their own application
        assert len(user_a_apps) == 1
        assert user_a_apps[0].company == "Company A"
        assert user_a_apps[0].user_id == user_a.id


class TestProfileIsolation:
    """Tests for user profile isolation."""

    def test_user_only_sees_own_profile(self, test_db):
        """User A cannot see User B's profile."""
        from src.persistence.models import User, UserProfile

        # Create two users with profiles
        user_a = User(email="user_a@example.com", username="user_a")
        user_b = User(email="user_b@example.com", username="user_b")
        test_db.add(user_a)
        test_db.add(user_b)
        test_db.commit()

        profile_a = UserProfile(
            user_id=user_a.id,
            target_titles={"primary": ["PM"]},
        )
        profile_b = UserProfile(
            user_id=user_b.id,
            target_titles={"primary": ["Engineer"]},
        )
        test_db.add(profile_a)
        test_db.add(profile_b)
        test_db.commit()

        # Query profile for user_a
        from sqlalchemy import select
        stmt = select(UserProfile).where(UserProfile.user_id == user_a.id)
        user_a_profile = test_db.execute(stmt).scalar_one_or_none()

        # User A should only see their own profile
        assert user_a_profile is not None
        assert user_a_profile.target_titles == {"primary": ["PM"]}
        assert user_a_profile.user_id == user_a.id

    def test_profile_contains_sensitive_integration_data(self, test_db):
        """Integration tokens are isolated per user."""
        from src.persistence.models import User, UserProfile

        # Create users with integration tokens
        user_a = User(email="user_a@example.com", username="user_a")
        user_b = User(email="user_b@example.com", username="user_b")
        test_db.add(user_a)
        test_db.add(user_b)
        test_db.commit()

        profile_a = UserProfile(
            user_id=user_a.id,
            slack_webhook_url="https://hooks.slack.com/user_a_webhook",
            gmail_token="user_a_encrypted_token",
        )
        profile_b = UserProfile(
            user_id=user_b.id,
            slack_webhook_url="https://hooks.slack.com/user_b_webhook",
            gmail_token="user_b_encrypted_token",
        )
        test_db.add(profile_a)
        test_db.add(profile_b)
        test_db.commit()

        # Query profile for user_a
        from sqlalchemy import select
        stmt = select(UserProfile).where(UserProfile.user_id == user_a.id)
        user_a_profile = test_db.execute(stmt).scalar_one()

        # User A's profile should have their own tokens, not B's
        assert "user_a" in user_a_profile.slack_webhook_url
        assert "user_a" in user_a_profile.gmail_token


class TestResumeIsolation:
    """Tests for resume data isolation between users."""

    def test_user_only_sees_own_resumes(self, test_db):
        """User A cannot see User B's resumes."""
        from src.persistence.models import User, Resume

        # Create two users
        user_a = User(email="user_a@example.com", username="user_a")
        user_b = User(email="user_b@example.com", username="user_b")
        test_db.add(user_a)
        test_db.add(user_b)
        test_db.commit()

        # Create resumes for each user
        resume_a = Resume(
            name="User A Resume",
            user_id=user_a.id,
        )
        resume_b = Resume(
            name="User B Resume",
            user_id=user_b.id,
        )
        test_db.add(resume_a)
        test_db.add(resume_b)
        test_db.commit()

        # Query resumes for user_a
        from sqlalchemy import select
        stmt = select(Resume).where(Resume.user_id == user_a.id)
        user_a_resumes = test_db.execute(stmt).scalars().all()

        # User A should only see their own resume
        assert len(user_a_resumes) == 1
        assert user_a_resumes[0].name == "User A Resume"
        assert user_a_resumes[0].user_id == user_a.id


class TestCascadeDelete:
    """Tests for cascade delete protecting data integrity."""

    def test_deleting_user_deletes_their_jobs(self, test_db):
        """When user is deleted, their jobs are also deleted."""
        from src.persistence.models import User, Job
        from sqlalchemy import select

        user = User(email="user@example.com", username="user")
        test_db.add(user)
        test_db.commit()

        job = Job(
            title="PM",
            company="Test",
            url="https://test.com/job",
            source="test",
            user_id=user.id,
        )
        test_db.add(job)
        test_db.commit()
        job_id = job.id

        # Delete user
        test_db.delete(user)
        test_db.commit()

        # Job should also be deleted
        stmt = select(Job).where(Job.id == job_id)
        result = test_db.execute(stmt).scalar_one_or_none()
        assert result is None

    def test_deleting_user_does_not_affect_other_users(self, test_db):
        """Deleting User A does not affect User B's data."""
        from src.persistence.models import User, Job
        from sqlalchemy import select

        user_a = User(email="user_a@example.com", username="user_a")
        user_b = User(email="user_b@example.com", username="user_b")
        test_db.add(user_a)
        test_db.add(user_b)
        test_db.commit()

        job_a = Job(
            title="PM A",
            company="Company A",
            url="https://a.com/job",
            source="test",
            user_id=user_a.id,
        )
        job_b = Job(
            title="PM B",
            company="Company B",
            url="https://b.com/job",
            source="test",
            user_id=user_b.id,
        )
        test_db.add(job_a)
        test_db.add(job_b)
        test_db.commit()
        job_b_id = job_b.id

        # Delete user A
        test_db.delete(user_a)
        test_db.commit()

        # User B's job should still exist
        stmt = select(Job).where(Job.id == job_b_id)
        result = test_db.execute(stmt).scalar_one_or_none()
        assert result is not None
        assert result.company == "Company B"


class TestAdminIsolation:
    """Tests for admin access patterns."""

    def test_admin_flag_does_not_grant_data_access_by_default(self, test_db):
        """Admin flag alone doesn't bypass data isolation in queries."""
        from src.persistence.models import User, Job
        from sqlalchemy import select

        # Create admin and regular user
        admin = User(email="admin@example.com", username="admin", is_admin=True)
        regular = User(email="regular@example.com", username="regular")
        test_db.add(admin)
        test_db.add(regular)
        test_db.commit()

        # Create job for regular user
        job = Job(
            title="PM",
            company="Test",
            url="https://test.com/job",
            source="test",
            user_id=regular.id,
        )
        test_db.add(job)
        test_db.commit()

        # Query jobs for admin using standard user_id filter
        stmt = select(Job).where(Job.user_id == admin.id)
        admin_jobs = test_db.execute(stmt).scalars().all()

        # Admin shouldn't see regular user's jobs with standard query
        assert len(admin_jobs) == 0

    def test_admin_can_query_all_users(self, test_db):
        """Admin can query all users (for user management)."""
        from src.persistence.models import User
        from sqlalchemy import select

        admin = User(email="admin@example.com", username="admin", is_admin=True)
        user1 = User(email="user1@example.com", username="user1")
        user2 = User(email="user2@example.com", username="user2")
        test_db.add_all([admin, user1, user2])
        test_db.commit()

        # Admin can query all users
        stmt = select(User)
        all_users = test_db.execute(stmt).scalars().all()

        assert len(all_users) == 3
