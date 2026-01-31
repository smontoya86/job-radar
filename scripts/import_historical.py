#!/usr/bin/env python3
"""Import historical job-related emails from Gmail since layoff date."""
import sys
from datetime import datetime

from scripts.bootstrap import settings, get_session, init_db


def main():
    """Run historical email import."""
    print("Historical Email Import")
    print("=" * 50)
    print()

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
            print("Gmail not authenticated. Run setup_gmail.py first.")
            return 1

    except ImportError as e:
        print(f"Gmail libraries not installed: {e}")
        return 1

    # Set date range (from layoff date)
    start_date = datetime(2026, 1, 20)  # Layoff date from profile
    end_date = datetime.now()

    # Gmail label where job emails are stored
    JOB_EMAIL_LABEL = "Job Posting"

    print(f"Importing emails from {start_date.date()} to {end_date.date()}")
    print(f"Looking in Gmail label: '{JOB_EMAIL_LABEL}'")
    print()

    # Initialize clients
    client = GmailClient(auth)
    parser = EmailParser()

    # Search for job emails in the specific label
    print(f"Searching for emails in '{JOB_EMAIL_LABEL}' folder...")
    message_ids = client.search_job_emails(
        after_date=start_date,
        before_date=end_date,
        max_results=1000,
        label=JOB_EMAIL_LABEL,
    )

    print(f"Found {len(message_ids)} potential emails")
    print()

    if not message_ids:
        print("No emails found. Check your Gmail search filters.")
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
                print(f"  Processed {i + 1}/{len(message_ids)} emails...")

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
                                app_service.update_status(app.id, "interview")

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

    print()
    print("=" * 50)
    print("Import Complete!")
    print(f"  Emails imported: {imported_count}")
    print(f"  Applications created: {application_count}")
    print(f"  Already imported (skipped): {skipped_count}")
    print()
    print("Run the dashboard to view your imported applications.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
