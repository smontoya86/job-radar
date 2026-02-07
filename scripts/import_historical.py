#!/usr/bin/env python3
"""Import historical job-related emails from Gmail since layoff date."""
import logging
import sys
from datetime import datetime

from scripts.bootstrap import settings, get_session, init_db
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main():
    """Run historical email import."""
    setup_logging()

    logger.info("Historical Email Import")
    logger.info("=" * 50)
    logger.info("")

    # Initialize database
    init_db()

    # Check Gmail auth
    try:
        from src.gmail.auth import GmailAuth
        from src.gmail.client import GmailClient
        from src.gmail.parser import EmailParser, EmailType

        auth = GmailAuth(
            credentials_file=settings.gmail_credentials_file,
            token_file=settings.gmail_token_file,
        )

        if not auth.is_authenticated():
            logger.error("Gmail not authenticated. Run setup_gmail.py first.")
            return 1

    except ImportError as e:
        logger.error("Gmail libraries not installed: %s", e)
        return 1

    # Set date range (from layoff date)
    start_date = datetime(2026, 1, 20)  # Layoff date from profile
    end_date = datetime.now()

    # Gmail label where job emails are stored
    JOB_EMAIL_LABEL = "Job Posting"

    logger.info("Importing emails from %s to %s", start_date.date(), end_date.date())
    logger.info("Looking in Gmail label: '%s'", JOB_EMAIL_LABEL)
    logger.info("")

    # Initialize clients
    client = GmailClient(auth)
    parser = EmailParser()

    # Search for job emails in the specific label
    logger.info("Searching for emails in '%s' folder...", JOB_EMAIL_LABEL)
    message_ids = client.search_job_emails(
        after_date=start_date,
        before_date=end_date,
        max_results=1000,
        label=JOB_EMAIL_LABEL,
    )

    logger.info("Found %s potential emails", len(message_ids))
    logger.info("")

    if not message_ids:
        logger.warning("No emails found. Check your Gmail search filters.")
        return 0

    # Process emails
    from src.tracking.application_service import ApplicationService
    from src.persistence.models import EmailImport
    from sqlalchemy import select

    imported_count = 0
    application_count = 0
    skipped_count = 0

    with get_session() as session:
        app_service = ApplicationService(session)

        for i, msg_id in enumerate(message_ids):
            # Progress indicator
            if (i + 1) % 50 == 0:
                logger.info("  Processed %s/%s emails...", i + 1, len(message_ids))

            # Check if already imported
            stmt = select(EmailImport).where(EmailImport.gmail_message_id == msg_id)
            result = session.execute(stmt)
            if result.scalar_one_or_none():
                skipped_count += 1
                continue

            # Fetch email
            email = client.get_message(msg_id)
            if not email:
                continue

            # Parse email (skip is_job_related check since we're using a specific label)
            parsed = parser.parse(email)

            # Save email import record
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
                    "rejection_stage": parsed.rejection_stage,
                },
            )
            session.add(email_import)
            imported_count += 1

            # Create application if applicable
            if parsed.email_type in [EmailType.CONFIRMATION, EmailType.INTERVIEW_INVITE]:
                if parsed.company:
                    # Check if application exists
                    existing = app_service._find_application_by_company(parsed.company)

                    if not existing:
                        # Create new application
                        app = app_service.create_application(
                            company=parsed.company,
                            position=parsed.position or "Unknown Position",
                            applied_date=email.date,
                            source="email_import",
                        )

                        if app:
                            email_import.application_id = app.id
                            email_import.processed = True
                            application_count += 1

                            # If it's an interview invite, update status
                            if parsed.email_type == EmailType.INTERVIEW_INVITE:
                                app_service.update_status(app.id, "interviewing")

                    else:
                        # Link to existing and update
                        email_import.application_id = existing.id
                        email_import.processed = True
                        app_service._update_from_email(existing, parsed)

            elif parsed.email_type == EmailType.REJECTION and parsed.company:
                # Update existing application if found
                existing = app_service._find_application_by_company(parsed.company)
                if existing and existing.status not in ["rejected", "withdrawn"]:
                    app_service.update_status(
                        existing.id,
                        "rejected",
                        notes=f"Rejection email received on {email.date.date()}",
                    )
                    email_import.application_id = existing.id
                    email_import.processed = True

        session.commit()

    logger.info("")
    logger.info("=" * 50)
    logger.info("Import Complete!")
    logger.info("  Emails imported: %s", imported_count)
    logger.info("  Applications created: %s", application_count)
    logger.info("  Already imported (skipped): %s", skipped_count)
    logger.info("")
    logger.info("Run the dashboard to view your imported applications.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
