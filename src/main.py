"""Main entry point for Job Radar scheduler."""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from src.collectors import (
    AdzunaCollector,
    GreenhouseCollector,
    HNCollector,
    JobSpyCollector,
    LeverCollector,
    RemoteOKCollector,
    WellfoundCollector,
)
from src.dedup.deduplicator import Deduplicator
from src.matching.keyword_matcher import KeywordMatcher
from src.matching.scorer import JobScorer
from src.notifications.slack_notifier import SlackNotifier
from src.persistence.database import get_session, init_db
from src.persistence.models import Job
from src.persistence.cleanup import cleanup_stale_data

# Maximum description length to store (for storage optimization)
MAX_DESCRIPTION_LENGTH = 2000


async def run_job_scan():
    """Run a complete job scan cycle."""
    print(f"\n{'='*60}")
    print(f"Starting job scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Run cleanup to maintain storage limits
    cleanup_stale_data()

    # Load profile and create matcher
    profile_path = str(settings.profile_path)
    matcher = KeywordMatcher(profile_path)
    scorer = JobScorer(matcher, min_score=settings.profile_path.parent.parent.joinpath("config/profile.yaml") and 30 or 30)

    # Get search queries from profile
    search_queries = matcher.get_search_queries()
    print(f"Search queries: {search_queries[:5]}...")

    # Initialize collectors
    collectors = [
        JobSpyCollector(sites=["indeed", "linkedin", "glassdoor", "google"], results_wanted=30),
        RemoteOKCollector(),
        WellfoundCollector(),  # Startup jobs
        GreenhouseCollector(),
        LeverCollector(),
    ]

    # Add optional collectors
    if settings.adzuna_app_id and settings.adzuna_app_key:
        collectors.append(
            AdzunaCollector(
                app_id=settings.adzuna_app_id,
                app_key=settings.adzuna_app_key,
            )
        )

    # Add HN collector (runs monthly anyway)
    collectors.append(HNCollector())

    # Collect jobs from all sources
    all_jobs = []
    for collector in collectors:
        try:
            print(f"Collecting from {collector.name}...")
            jobs = await collector.collect(search_queries)
            print(f"  Found {len(jobs)} jobs from {collector.name}")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  Error collecting from {collector.name}: {e}")

    print(f"\nTotal jobs collected: {len(all_jobs)}")

    if not all_jobs:
        print("No jobs found. Check your search queries and collectors.")
        return

    # Score and filter jobs
    print("\nScoring jobs...")
    scored_jobs = scorer.score_jobs(all_jobs)
    print(f"Jobs passing minimum score: {len(scored_jobs)}")

    # Deduplicate
    print("\nDeduplicating...")
    with get_session() as session:
        deduplicator = Deduplicator(session)
        unique_jobs = deduplicator.deduplicate(scored_jobs, check_db=True)
        print(f"New unique jobs: {len(unique_jobs)}")

        if not unique_jobs:
            print("No new jobs to process.")
            return

        # Save to database
        print("\nSaving to database...")
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
        print(f"Saved {new_job_count} new jobs")

    # Send notifications
    if settings.slack_webhook_url:
        print("\nSending Slack notifications...")
        notifier = SlackNotifier(
            webhook_url=settings.slack_webhook_url,
            min_score=60,
        )
        notified_count = await notifier.notify_batch(unique_jobs)
        print(f"Sent {notified_count} notifications")

        # Update notified timestamp
        with get_session() as session:
            for scored in unique_jobs[:notified_count]:
                # Find job by fingerprint and update
                from sqlalchemy import select
                stmt = select(Job).where(Job.fingerprint == scored.fingerprint)
                result = session.execute(stmt)
                job = result.scalar_one_or_none()
                if job:
                    job.notified_at = datetime.utcnow()
            session.commit()

    print(f"\nJob scan completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


async def run_email_import():
    """Import new job-related emails from Gmail."""
    print(f"\nChecking Gmail for job emails...")

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
            print("Gmail not authenticated. Run setup_gmail.py first.")
            return

        client = GmailClient(auth)
        parser = EmailParser()

        # Search for recent job emails in the "Job Posting" label
        from datetime import timedelta
        after_date = datetime.now() - timedelta(days=1)  # Last 24 hours

        message_ids = client.search_job_emails(
            after_date=after_date,
            max_results=50,
            label="Job Posting",  # Only check labeled emails
        )

        print(f"Found {len(message_ids)} potential job emails")

        if not message_ids:
            return

        # Process emails
        from src.tracking.application_service import ApplicationService
        from src.persistence.models import EmailImport

        with get_session() as session:
            app_service = ApplicationService(session)

            for msg_id in message_ids:
                # Check if already imported
                from sqlalchemy import select
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

                # Create or update application
                if parsed.email_type != EmailType.UNKNOWN and parsed.company:
                    app = app_service.create_from_email(parsed)
                    if app:
                        email_import.application_id = app.id
                        email_import.processed = True
                        print(f"  Processed: {parsed.email_type.value} from {parsed.company}")

            session.commit()

        print("Email import completed")

    except ImportError as e:
        print(f"Gmail integration not available: {e}")
    except Exception as e:
        print(f"Email import error: {e}")


async def async_main():
    """Async main entry point."""
    print("Job Radar Starting...")
    print(f"Database: {settings.database_url}")
    print(f"Profile: {settings.profile_path}")

    # Initialize database
    init_db()
    print("Database initialized")

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
    print(f"\nScheduler started:")
    print(f"  - Job scan every {settings.job_check_interval_minutes} minutes")
    print(f"  - Email import every {settings.email_check_interval_minutes} minutes")
    print("\nRunning initial job scan...")

    try:
        # Run initial scan
        await run_job_scan()
        await run_email_import()

        print("\nJob Radar running. Press Ctrl+C to stop.")

        # Keep running forever
        while True:
            await asyncio.sleep(60)

    except asyncio.CancelledError:
        print("\nShutting down...")
    finally:
        scheduler.shutdown()


def main():
    """Main entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")


if __name__ == "__main__":
    main()
