"""Tests for application and resume services."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.tracking.application_service import ApplicationService
from src.tracking.resume_service import ResumeService
from src.gmail.parser import EmailType, ParsedEmail
from src.persistence.models import Application, Job, Resume, StatusHistory


class TestApplicationService:
    """Tests for ApplicationService."""

    def test_create_application(self, test_db):
        """Test creating an application."""
        service = ApplicationService(test_db)

        app = service.create_application(
            company="Test Company",
            position="Product Manager",
            source="linkedin",
        )

        assert app is not None
        assert app.company == "Test Company"
        assert app.position == "Product Manager"
        assert app.status == "applied"

    def test_create_application_with_date(self, test_db):
        """Test creating an application with specific date."""
        service = ApplicationService(test_db)
        applied_date = datetime(2026, 1, 15)

        app = service.create_application(
            company="Test Co",
            position="PM",
            applied_date=applied_date,
        )

        assert app.applied_date == applied_date

    def test_get_application(self, test_db, sample_application):
        """Test getting an application by ID."""
        service = ApplicationService(test_db)
        retrieved = service.get_application(sample_application.id)

        assert retrieved is not None
        assert retrieved.id == sample_application.id

    def test_get_all_applications(self, test_db, multiple_applications):
        """Test getting all applications."""
        service = ApplicationService(test_db)
        apps = service.get_all_applications()

        assert len(apps) == 6

    def test_get_applications_by_status(self, test_db, multiple_applications):
        """Test filtering applications by status."""
        service = ApplicationService(test_db)
        apps = service.get_all_applications(status="applied")

        assert all(app.status == "applied" for app in apps)

    def test_update_status(self, test_db, sample_application):
        """Test updating application status."""
        service = ApplicationService(test_db)

        updated = service.update_status(
            sample_application.id,
            "interviewing",
            notes="Phone screen scheduled",
        )

        assert updated.status == "interviewing"
        assert updated.last_status_change is not None

    def test_update_status_creates_history(self, test_db, sample_application):
        """Test that status update creates history record."""
        service = ApplicationService(test_db)

        service.update_status(sample_application.id, "phone_screen")

        # Check history was created
        from sqlalchemy import select
        stmt = select(StatusHistory).where(
            StatusHistory.application_id == sample_application.id
        )
        result = test_db.execute(stmt)
        history = result.scalar_one_or_none()

        assert history is not None
        assert history.old_status == "applied"
        assert history.new_status == "phone_screen"

    def test_add_interview(self, test_db, sample_application):
        """Test adding an interview."""
        service = ApplicationService(test_db)

        interview = service.add_interview(
            application_id=sample_application.id,
            interview_type="phone",
            scheduled_at=datetime(2026, 1, 30, 14, 0),
            duration_minutes=45,
        )

        assert interview is not None
        assert interview.type == "phone"
        assert interview.round == 1

    def test_add_interview_auto_increments_round(self, test_db, sample_application):
        """Test that interview rounds auto-increment."""
        service = ApplicationService(test_db)

        interview1 = service.add_interview(
            application_id=sample_application.id,
            interview_type="phone",
        )
        assert interview1.round == 1

        interview2 = service.add_interview(
            application_id=sample_application.id,
            interview_type="video",
        )
        assert interview2.round == 2

    def test_get_pipeline_counts(self, test_db, multiple_applications):
        """Test getting pipeline counts by status."""
        service = ApplicationService(test_db)
        counts = service.get_pipeline_counts()

        assert isinstance(counts, dict)
        assert "applied" in counts
        assert counts["applied"] == 2

    def test_find_application_by_company(self, test_db, sample_application):
        """Test finding application by company name."""
        service = ApplicationService(test_db)

        # Exact match
        found = service._find_application_by_company("OpenAI")
        assert found is not None
        assert found.id == sample_application.id

        # Case insensitive
        found = service._find_application_by_company("openai")
        assert found is not None

    def test_find_application_by_company_partial(self, test_db, sample_application):
        """Test partial company name matching."""
        service = ApplicationService(test_db)

        # Partial match
        found = service._find_application_by_company("Open")
        assert found is not None


class TestTryLinkToJob:
    """Tests for _try_link_to_job — linking Applications to Jobs by company."""

    def test_try_link_to_job_by_company_name(self, test_db):
        """Links Application to Job by matching company name."""
        # Create a Job
        job = Job(
            id="job-link-1",
            title="AI PM",
            company="TestCorp",
            url="https://testcorp.com/jobs/1",
            source="greenhouse",
            description="AI product management role requiring ML experience.",
        )
        test_db.add(job)
        test_db.commit()

        # Create an Application for the same company (no job_id yet)
        app = Application(
            id="app-link-1",
            company="TestCorp",
            position="AI PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id == "job-link-1"

    def test_try_link_to_job_case_insensitive(self, test_db):
        """Case-insensitive company matching: 'testcorp' matches 'TestCorp'."""
        job = Job(
            id="job-case-1",
            title="PM",
            company="TestCorp",
            url="https://testcorp.com/jobs/1",
            source="greenhouse",
            description="A great PM role.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-case-1",
            company="testcorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id == "job-case-1"

    def test_try_link_to_job_copies_description(self, test_db):
        """Populates application.job_description from Job.description."""
        job = Job(
            id="job-desc-1",
            title="PM",
            company="DescCorp",
            url="https://desccorp.com/jobs/1",
            source="lever",
            description="Full description of the PM role with ML requirements.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-desc-1",
            company="DescCorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_description == "Full description of the PM role with ML requirements."

    def test_try_link_to_job_does_not_overwrite(self, test_db):
        """Preserves existing job_description even when a Job is linked."""
        job = Job(
            id="job-no-overwrite-1",
            title="PM",
            company="KeepCorp",
            url="https://keepcorp.com/jobs/1",
            source="greenhouse",
            description="Job description from radar.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-no-overwrite-1",
            company="KeepCorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
            job_description="Manually entered description.",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        # job_id should be linked, but description should NOT be overwritten
        assert app.job_id == "job-no-overwrite-1"
        assert app.job_description == "Manually entered description."

    def test_create_from_email_links_to_job(self, test_db):
        """New applications created from email get linked to existing jobs."""
        job = Job(
            id="job-email-1",
            title="Data PM",
            company="EmailCorp",
            url="https://emailcorp.com/jobs/1",
            source="greenhouse",
            description="Data PM role with analytics focus.",
        )
        test_db.add(job)
        test_db.commit()

        parsed_email = ParsedEmail(
            email_type=EmailType.CONFIRMATION,
            company="EmailCorp",
            position="Data PM",
            confidence=0.9,
        )

        service = ApplicationService(test_db)
        app = service.create_from_email(parsed_email)

        assert app is not None
        assert app.job_id == "job-email-1"
        assert app.job_description == "Data PM role with analytics focus."

    def test_update_status_rejected_populates_description(self, test_db):
        """When status changes to 'rejected', description is copied from linked Job."""
        job = Job(
            id="job-rej-1",
            title="PM",
            company="RejCorp",
            url="https://rejcorp.com/jobs/1",
            source="lever",
            description="PM role description for analysis.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-rej-1",
            company="RejCorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
            job_id="job-rej-1",
            # job_description intentionally NULL
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        updated = service.update_status(app.id, "rejected")

        assert updated.status == "rejected"
        assert updated.job_description == "PM role description for analysis."

    def test_try_link_to_job_picks_most_recent(self, test_db):
        """When multiple jobs match the company, picks the most recently discovered one."""
        job_old = Job(
            id="job-old-1",
            title="PM",
            company="MultiCorp",
            url="https://multicorp.com/jobs/old",
            source="lever",
            description="Old job description.",
            discovered_at=datetime(2026, 1, 1),
        )
        job_new = Job(
            id="job-new-1",
            title="Senior PM",
            company="MultiCorp",
            url="https://multicorp.com/jobs/new",
            source="greenhouse",
            description="New job description.",
            discovered_at=datetime(2026, 1, 25),
        )
        test_db.add_all([job_old, job_new])
        test_db.commit()

        app = Application(
            id="app-multi-1",
            company="MultiCorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id == "job-new-1"
        assert app.job_description == "New job description."


class TestCreateFromRejectionEmail:
    """Tests for creating applications from rejection emails (no prior confirmation)."""

    def test_create_from_rejection_email_creates_application(self, test_db):
        """Rejection email with no existing app should create one."""
        parsed_email = ParsedEmail(
            email_type=EmailType.REJECTION,
            company="Fontainebleau",
            position="Product Manager",
            confidence=0.8,
        )

        service = ApplicationService(test_db)
        app = service.create_from_email(parsed_email)

        assert app is not None
        assert app.company == "Fontainebleau"
        assert app.status == "rejected"

    def test_create_from_rejection_email_links_to_job(self, test_db):
        """New app from rejection email should link to matching Job."""
        job = Job(
            id="job-rej-link-1",
            title="PM",
            company="Federato",
            url="https://federato.com/jobs/1",
            source="greenhouse",
            description="PM role at Federato requiring AI experience.",
        )
        test_db.add(job)
        test_db.commit()

        parsed_email = ParsedEmail(
            email_type=EmailType.REJECTION,
            company="Federato",
            position="Unknown Position",
            confidence=0.8,
        )

        service = ApplicationService(test_db)
        app = service.create_from_email(parsed_email)

        assert app is not None
        assert app.job_id == "job-rej-link-1"
        assert app.job_description == "PM role at Federato requiring AI experience."

    def test_create_from_rejection_email_sets_rejected_at(self, test_db):
        """New app from rejection email should have rejected_at = 'applied'."""
        parsed_email = ParsedEmail(
            email_type=EmailType.REJECTION,
            company="Aristocrat",
            confidence=0.7,
        )

        service = ApplicationService(test_db)
        app = service.create_from_email(parsed_email)

        assert app is not None
        assert app.rejected_at == "applied"

    def test_rejection_email_with_existing_app_updates_status(self, test_db):
        """Rejection email for existing app should update to rejected (not create new)."""
        existing = Application(
            company="WWT",
            position="PM",
            applied_date=datetime(2026, 1, 15),
            status="applied",
        )
        test_db.add(existing)
        test_db.commit()

        parsed_email = ParsedEmail(
            email_type=EmailType.REJECTION,
            company="WWT",
            confidence=0.8,
        )

        service = ApplicationService(test_db)
        app = service.create_from_email(parsed_email)

        assert app is not None
        assert app.id == existing.id
        assert app.status == "rejected"

    def test_rejection_email_no_company_returns_none(self, test_db):
        """Rejection email with no company should return None."""
        parsed_email = ParsedEmail(
            email_type=EmailType.REJECTION,
            company=None,
            confidence=0.5,
        )

        service = ApplicationService(test_db)
        app = service.create_from_email(parsed_email)

        assert app is None


class TestFuzzyJobLinking:
    """Tests for fuzzy company name matching when linking applications to jobs."""

    def test_fuzzy_link_merged_word(self, test_db):
        """'Fetchrewards' (from email domain) matches 'Fetch Rewards' job."""
        job = Job(
            id="job-fuzzy-1",
            title="Product Manager",
            company="Fetch Rewards",
            url="https://fetchrewards.com/jobs/1",
            source="greenhouse",
            description="PM role at Fetch Rewards.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-fuzzy-1",
            company="Fetchrewards",
            position="Product Manager",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id == "job-fuzzy-1"
        assert app.job_description == "PM role at Fetch Rewards."

    def test_fuzzy_link_suffix_stripped(self, test_db):
        """'TestCorp Inc' matches 'TestCorp' via suffix stripping."""
        job = Job(
            id="job-suffix-1",
            title="PM",
            company="TestCorp",
            url="https://testcorp.com/jobs/1",
            source="lever",
            description="PM at TestCorp.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-suffix-1",
            company="TestCorp Inc",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id == "job-suffix-1"

    def test_fuzzy_link_does_not_false_positive(self, test_db):
        """'Block' should NOT match 'Fireblocks' — substring is not sufficient."""
        job = Job(
            id="job-no-false-1",
            title="PM",
            company="Fireblocks",
            url="https://fireblocks.com/jobs/1",
            source="lever",
            description="Fireblocks PM role.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-no-false-1",
            company="Block",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id is None

    def test_fuzzy_link_with_punctuation(self, test_db):
        """'Maven AGI' matches 'Maven A.G.I.' after punctuation stripping."""
        job = Job(
            id="job-punct-1",
            title="PM",
            company="Maven A.G.I.",
            url="https://maven.com/jobs/1",
            source="lever",
            description="PM at Maven AGI.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-punct-1",
            company="Maven AGI",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        service._try_link_to_job(app)

        assert app.job_id == "job-punct-1"


class TestRelinkUnlinkedApplications:
    """Tests for periodic re-linking of unlinked applications."""

    def test_relink_finds_new_match(self, test_db):
        """App created BEFORE job should get linked by re-link."""
        # Create app first (no job exists yet)
        app = Application(
            id="app-relink-1",
            company="NewCorp",
            position="PM",
            applied_date=datetime(2026, 1, 15),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        assert app.job_id is None

        # Job arrives later
        job = Job(
            id="job-relink-1",
            title="PM",
            company="NewCorp",
            url="https://newcorp.com/jobs/1",
            source="greenhouse",
            description="PM at NewCorp.",
        )
        test_db.add(job)
        test_db.commit()

        service = ApplicationService(test_db)
        linked_count = service.relink_unlinked_applications()

        assert linked_count == 1
        assert app.job_id == "job-relink-1"
        assert app.job_description == "PM at NewCorp."

    def test_relink_skips_already_linked(self, test_db):
        """Re-link doesn't touch applications that already have job_id."""
        job = Job(
            id="job-skip-1",
            title="PM",
            company="LinkedCorp",
            url="https://linkedcorp.com/jobs/1",
            source="lever",
            description="Already linked.",
        )
        test_db.add(job)
        test_db.commit()

        app = Application(
            id="app-skip-1",
            company="LinkedCorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
            job_id="job-skip-1",
            job_description="Original description.",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        linked_count = service.relink_unlinked_applications()

        assert linked_count == 0
        assert app.job_description == "Original description."

    def test_relink_returns_zero_when_nothing_to_link(self, test_db):
        """Re-link returns 0 when no unlinked apps have matching jobs."""
        app = Application(
            id="app-nomatch-1",
            company="ObscureCorp",
            position="PM",
            applied_date=datetime(2026, 1, 20),
            status="applied",
        )
        test_db.add(app)
        test_db.commit()

        service = ApplicationService(test_db)
        linked_count = service.relink_unlinked_applications()

        assert linked_count == 0
        assert app.job_id is None


class TestResumeService:
    """Tests for ResumeService."""

    def test_create_resume(self, test_db):
        """Test creating a resume."""
        service = ResumeService(test_db)

        resume = service.create_resume(
            name="AI PM v1",
            target_roles=["AI Product Manager"],
            key_changes="Initial version",
        )

        assert resume is not None
        assert resume.name == "AI PM v1"
        assert resume.version == 1

    def test_create_resume_auto_version(self, test_db):
        """Test that resume version auto-increments."""
        service = ResumeService(test_db)

        resume1 = service.create_resume(name="AI PM v1")
        resume2 = service.create_resume(name="AI PM v2")

        assert resume2.version == resume1.version + 1

    def test_get_resume(self, test_db, sample_resume):
        """Test getting a resume by ID."""
        service = ResumeService(test_db)
        retrieved = service.get_resume(sample_resume.id)

        assert retrieved is not None
        assert retrieved.id == sample_resume.id

    def test_get_all_resumes(self, test_db, sample_resume):
        """Test getting all resumes."""
        service = ResumeService(test_db)
        resumes = service.get_all_resumes()

        assert len(resumes) >= 1

    def test_get_active_resumes_only(self, test_db):
        """Test filtering to active resumes only."""
        service = ResumeService(test_db)

        # Create active and inactive resumes
        service.create_resume(name="Active")
        inactive = service.create_resume(name="Inactive")
        service.deactivate_resume(inactive.id)

        active_only = service.get_all_resumes(active_only=True)
        all_resumes = service.get_all_resumes(active_only=False)

        assert len(active_only) < len(all_resumes)

    def test_update_resume(self, test_db, sample_resume):
        """Test updating a resume."""
        service = ResumeService(test_db)

        updated = service.update_resume(
            sample_resume.id,
            name="Updated Name",
            key_changes="New changes",
        )

        assert updated.name == "Updated Name"
        assert updated.key_changes == "New changes"

    def test_deactivate_resume(self, test_db, sample_resume):
        """Test deactivating a resume."""
        service = ResumeService(test_db)

        deactivated = service.deactivate_resume(sample_resume.id)
        assert deactivated.is_active is False

    def test_get_resume_stats(self, test_db, sample_resume):
        """Test getting resume statistics."""
        service = ResumeService(test_db)

        # Add some applications using this resume
        app1 = Application(
            company="A",
            position="PM",
            applied_date=datetime.now(),
            resume_id=sample_resume.id,
            status="applied",
        )
        app2 = Application(
            company="B",
            position="PM",
            applied_date=datetime.now(),
            resume_id=sample_resume.id,
            status="interviewing",
        )
        test_db.add_all([app1, app2])
        test_db.commit()

        stats = service.get_resume_stats(sample_resume.id)

        assert stats["total_applications"] == 2
        assert "response_rate" in stats
        assert "interview_rate" in stats
