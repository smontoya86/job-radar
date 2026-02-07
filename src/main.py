"""Main entry point for Job Radar scheduler."""
import asyncio
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from config.settings import settings
from src.collectors import (
    AdzunaCollector,
    AshbyCollector,
    GreenhouseCollector,
    HimalayasCollector,
    HNCollector,
    JSearchCollector,
    LeverCollector,
    RemoteOKCollector,
    RemotiveCollector,
    SearchDiscoveryCollector,
    SerpApiCollector,
    SmartRecruitersCollector,
    TheMuseCollector,
    WorkdayCollector,
)
from src.dedup.deduplicator import Deduplicator
from src.logging_config import setup_logging
from src.matching.keyword_matcher import KeywordMatcher
from src.matching.scorer import JobScorer
from src.notifications.slack_notifier import SlackNotifier
from src.persistence.database import get_session, init_db
from src.persistence.models import Job
from src.persistence.cleanup import cleanup_stale_data
from src.onboarding.config_checker import is_configured, get_missing_config

logger = logging.getLogger(__name__)

# Maximum description length to store (for storage optimization)
MAX_DESCRIPTION_LENGTH = 2000


async def run_job_scan(on_progress=None):
    """Run a complete job scan cycle.

    Args:
        on_progress: Optional callback(step: str, detail: str, pct: float)
                     for reporting progress to a UI. pct is 0.0-1.0.
    """
    def _progress(step, detail="", pct=0.0):
        if on_progress:
            on_progress(step, detail, pct)

    logger.info("=" * 60)
    logger.info("Starting job scan at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    _progress("Initializing", "Cleaning up stale data...", 0.0)

    # Run cleanup to maintain storage limits
    cleanup_stale_data()

    # Load profile and create matcher
    profile_path = str(settings.profile_path)
    matcher = KeywordMatcher(profile_path)
    scorer = JobScorer(matcher, min_score=settings.profile_path.parent.parent.joinpath("config/profile.yaml") and 30 or 30)

    # Get search queries from profile
    search_queries = matcher.get_search_queries()
    logger.info("Search queries: %s...", search_queries[:5])

    # Initialize collectors — all compliant, API-based sources
    collectors = [
        RemoteOKCollector(),
        GreenhouseCollector(),
        LeverCollector(),
        AshbyCollector(),
        HNCollector(),
    ]

    # Add optional API-key collectors (skip if placeholder credentials)
    adzuna_placeholders = {"your_id", "your_key", "", None}
    if (settings.adzuna_app_id not in adzuna_placeholders and
        settings.adzuna_app_key not in adzuna_placeholders):
        collectors.append(
            AdzunaCollector(
                app_id=settings.adzuna_app_id,
                app_key=settings.adzuna_app_key,
            )
        )
    else:
        logger.info("Adzuna credentials not configured, skipping collector")

    serpapi_placeholders = {"your_key", "", None}
    if settings.serpapi_key not in serpapi_placeholders:
        collectors.append(SerpApiCollector(api_key=settings.serpapi_key))
        collectors.append(SearchDiscoveryCollector(api_key=settings.serpapi_key))
    else:
        logger.info("SerpApi key not configured, skipping SerpApi + Search Discovery")

    jsearch_placeholders = {"your_key", "", None}
    if settings.jsearch_api_key not in jsearch_placeholders:
        collectors.append(JSearchCollector(api_key=settings.jsearch_api_key))
    else:
        logger.info("JSearch API key not configured, skipping collector")

    # ATS board collectors (no API key needed)
    collectors.append(WorkdayCollector())
    collectors.append(SmartRecruitersCollector())
    collectors.append(RemotiveCollector())
    collectors.append(HimalayasCollector())
    collectors.append(TheMuseCollector())

    # Collect jobs from all sources with rate limiting
    all_jobs = []
    total_collectors = len(collectors)
    for i, collector in enumerate(collectors):
        # Progress: collectors take ~80% of the total time (0.05 to 0.85)
        pct = 0.05 + (i / total_collectors) * 0.80
        _progress("Collecting", f"Scanning {collector.name}... ({i + 1}/{total_collectors})", pct)

        try:
            logger.info("Collecting from %s...", collector.name)
            jobs = await collector.collect(search_queries)
            logger.info("  Found %d jobs from %s", len(jobs), collector.name)
            all_jobs.extend(jobs)

            # Rate limiting: wait between collectors to avoid detection
            # Skip delay after the last collector
            if i < len(collectors) - 1:
                delay = random.uniform(5.0, 15.0)
                logger.info("  Rate limit: waiting %.1fs before next collector...", delay)
                await asyncio.sleep(delay)

        except Exception as e:
            logger.error("Error collecting from %s: %s", collector.name, e, exc_info=True)

    logger.info("Total jobs collected: %d", len(all_jobs))

    if not all_jobs:
        _progress("Complete", "No jobs found.", 1.0)
        logger.info("No jobs found. Check your search queries and collectors.")
        return

    # Score and filter jobs
    _progress("Scoring", f"Scoring {len(all_jobs)} jobs...", 0.87)
    logger.info("Scoring jobs...")
    scored_jobs = scorer.score_jobs(all_jobs)
    logger.info("Jobs passing minimum score: %d", len(scored_jobs))

    # Deduplicate
    _progress("Deduplicating", f"Checking {len(scored_jobs)} scored jobs for duplicates...", 0.92)
    logger.info("Deduplicating...")
    with get_session() as session:
        deduplicator = Deduplicator(session)
        unique_jobs = deduplicator.deduplicate(scored_jobs, check_db=True)
        logger.info("New unique jobs: %d", len(unique_jobs))

        if not unique_jobs:
            _progress("Complete", "No new jobs to process (all duplicates).", 1.0)
            logger.info("No new jobs to process.")
            return

        # Save to database
        _progress("Saving", f"Saving {len(unique_jobs)} new jobs to database...", 0.95)
        logger.info("Saving to database...")
        new_job_count = 0
        for scored in unique_jobs:
            job_data = scored.job

            # Truncate description to save storage space
            description = job_data.description
            if description and len(description) > MAX_DESCRIPTION_LENGTH:
                description = description[:MAX_DESCRIPTION_LENGTH - 3] + "..."

            job = Job(
                title=job_data.title,
                company=job_data.company,
                location=job_data.location,
                description=description,
                salary_min=job_data.salary_min,
                salary_max=job_data.salary_max,
                url=job_data.url,
                apply_url=job_data.apply_url,
                source=job_data.source,
                remote=job_data.remote,
                match_score=scored.score,
                matched_keywords=scored.matched_keywords,
                fingerprint=scored.fingerprint,
                posted_date=job_data.posted_date,
                status="new",
            )
            session.add(job)
            new_job_count += 1

        session.commit()
        logger.info("Saved %d new jobs", new_job_count)

    # Send notifications
    if settings.slack_webhook_url:
        logger.info("Sending Slack notifications...")
        notifier = SlackNotifier(
            webhook_url=settings.slack_webhook_url,
            min_score=50,  # Lowered from 60 to get more notifications
        )
        notified_count = await notifier.notify_batch(unique_jobs)
        logger.info("Sent %d notifications", notified_count)

        # Update notified timestamp
        with get_session() as session:
            for scored in unique_jobs[:notified_count]:
                # Find job by fingerprint and update
                stmt = select(Job).where(Job.fingerprint == scored.fingerprint)
                result = session.execute(stmt)
                job = result.scalar_one_or_none()
                if job:
                    job.notified_at = datetime.now(timezone.utc)
            session.commit()

    # Re-link unlinked applications to newly collected jobs
    from src.tracking.application_service import ApplicationService
    with get_session() as session:
        service = ApplicationService(session)
        relinked = service.relink_unlinked_applications()
        if relinked:
            logger.info("Re-linked %d applications to jobs", relinked)

    _progress("Complete", f"Scan complete! Found {new_job_count} new jobs.", 1.0)
    logger.info("Job scan completed at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)


async def run_email_import(on_progress=None):
    """Import new job-related emails from Gmail.

    Args:
        on_progress: Optional callback(step: str, detail: str, pct: float)
                     for reporting progress to a UI. pct is 0.0-1.0.
    """
    def _progress(step, detail="", pct=0.0):
        if on_progress:
            on_progress(step, detail, pct)

    logger.info("Checking Gmail for job emails...")
    _progress("Connecting", "Connecting to Gmail...", 0.0)

    try:
        from src.gmail.auth import GmailAuth
        from src.gmail.client import GmailClient
        from src.gmail.parser import EmailParser, EmailType

        # Initialize Gmail
        auth = GmailAuth(
            credentials_file=settings.gmail_credentials_file,
            token_file=settings.gmail_token_file,
        )

        if not auth.is_authenticated():
            _progress("Complete", "Gmail not authenticated. Run setup_gmail.py first.", 1.0)
            logger.info("Gmail not authenticated. Run setup_gmail.py first.")
            return

        client = GmailClient(auth)
        parser = EmailParser()

        # Search for recent job emails in the "Job Posting" label
        _progress("Searching", "Searching for job emails...", 0.15)
        from datetime import timedelta
        after_date = datetime.now() - timedelta(days=14)  # Last 2 weeks

        message_ids = client.search_job_emails(
            after_date=after_date,
            max_results=50,
            label="Job Posting",  # Only check labeled emails
        )

        logger.info("Found %d potential job emails", len(message_ids))

        if not message_ids:
            _progress("Complete", "No new emails found.", 1.0)
            return

        # Process emails
        from src.tracking.application_service import ApplicationService
        from src.persistence.models import EmailImport

        _progress("Processing", f"Processing {len(message_ids)} emails...", 0.3)

        processed_count = 0
        with get_session() as session:
            app_service = ApplicationService(session)

            for idx, msg_id in enumerate(message_ids):
                pct = 0.3 + (idx / len(message_ids)) * 0.65
                _progress("Processing", f"Email {idx + 1}/{len(message_ids)}...", pct)

                # Check if already imported
                stmt = select(EmailImport).where(EmailImport.gmail_message_id == msg_id)
                result = session.execute(stmt)
                if result.scalar_one_or_none():
                    continue  # Already imported

                # Fetch and parse email
                email = client.get_message(msg_id)
                if not email:
                    continue

                if not parser.is_job_related(email):
                    continue

                parsed = parser.parse(email)

                # Save email import
                email_import = EmailImport(
                    gmail_message_id=msg_id,
                    subject=email.subject,
                    from_address=email.from_address,
                    received_at=email.date,
                    email_type=parsed.email_type.value,
                    parsed_data={
                        "company": parsed.company,
                        "position": parsed.position,
                        "confidence": parsed.confidence,
                    },
                )
                session.add(email_import)
                processed_count += 1

                # Create or update application
                if parsed.email_type != EmailType.UNKNOWN and parsed.company:
                    app = app_service.create_from_email(parsed)
                    if app:
                        email_import.application_id = app.id
                        email_import.processed = True
                        logger.info("  Processed: %s from %s", parsed.email_type.value, parsed.company)

            session.commit()

        _progress("Complete", f"Imported {processed_count} new emails.", 1.0)
        logger.info("Email import completed")

    except ImportError as e:
        _progress("Error", f"Gmail not available: {e}", 1.0)
        logger.error("Gmail integration not available: %s", e)
    except Exception as e:
        _progress("Error", f"Sync failed: {e}", 1.0)
        logger.error("Email import error: %s", e, exc_info=True)


async def async_main():
    """Async main entry point."""
    setup_logging(log_file="logs/jobradar.log")
    logger.info("Job Radar Starting...")
    logger.info("Database: %s", settings.database_url)
    logger.info("Profile: %s", settings.profile_path)

    # Check if configured
    if not is_configured(project_root):
        logger.error("=" * 60)
        logger.error("ERROR: Job Radar is not configured!")
        logger.error("=" * 60)
        missing = get_missing_config(project_root)
        for item in missing:
            logger.error("  - %s", item)
        logger.error("To configure Job Radar:")
        logger.error("  1. Run the dashboard: streamlit run dashboard/app.py")
        logger.error("  2. Complete the Setup Wizard")
        logger.error("Or manually create config/profile.yaml and .env files.")
        logger.error("See config/profile.yaml.example and .env.example for templates.")
        logger.error("=" * 60)
        return

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Create scheduler
    scheduler = AsyncIOScheduler()

    # Add job scan job
    scheduler.add_job(
        run_job_scan,
        IntervalTrigger(minutes=settings.job_check_interval_minutes),
        id="job_scan",
        name="Job Scan",
        max_instances=1,
    )

    # Add email import job
    scheduler.add_job(
        run_email_import,
        IntervalTrigger(minutes=settings.email_check_interval_minutes),
        id="email_import",
        name="Email Import",
        max_instances=1,
    )

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started:")
    logger.info("  - Job scan every %d minutes", settings.job_check_interval_minutes)
    logger.info("  - Email import every %d minutes", settings.email_check_interval_minutes)
    logger.info("Running initial job scan...")

    try:
        # Run initial scan
        await run_job_scan()
        await run_email_import()

        logger.info("Job Radar running. Press Ctrl+C to stop.")

        # Keep running forever
        while True:
            await asyncio.sleep(60)

    except asyncio.CancelledError:
        logger.info("Shutting down...")
    finally:
        scheduler.shutdown()


def main():
    """Main entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
