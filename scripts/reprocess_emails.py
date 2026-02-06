#!/usr/bin/env python3
"""Reprocess all imported emails with the improved parser.

This script:
1. Re-parses all EmailImport records with the updated parser
2. Links emails to existing applications based on company name
3. Updates application statuses based on email type (rejection, interview, etc.)
4. Creates applications for confirmations with no matching application

Usage:
    python scripts/reprocess_emails.py [--dry-run]
"""
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, func

from config.settings import settings
from src.persistence.database import get_session, init_db
from src.persistence.models import Application, EmailImport
from src.gmail.parser import EmailParser, EmailType
from src.tracking.application_service import ApplicationService


@dataclass
class FakeEmail:
    """Minimal email object for re-parsing."""
    from_address: str
    from_name: str
    subject: str
    body_text: str = ""
    body_html: str = ""
    snippet: str = ""
    date: Optional[datetime] = None


def normalize_company(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    # Lowercase and remove common suffixes
    name = name.lower().strip()
    for suffix in [" inc", " llc", " corp", " ltd", " co"]:
        name = name.replace(suffix, "")
    return name


# Bogus company names to ignore (parser artifacts)
INVALID_COMPANY_NAMES = {
    "us", "hi", "our", "hq", "candidates", "talent", "gem", "ir",
    "thank you for your", "we received your", "thank you for your interest in joining the",
    "our talent acquisition", "we will be in touch if we", "thank you for your interest in joining the brisk teaching",
    "appreview", "applytojob", "clearcompany", "hirebridgemail", "jobalerts", "jobgether", "strategiced",
    "agiloft hi sam", "joining reddit",  # Parser artifacts with extra text
}


def is_valid_company_name(name: str) -> bool:
    """Check if a company name looks valid."""
    if not name:
        return False

    normalized = name.lower().strip()

    # Skip known invalid names
    if normalized in INVALID_COMPANY_NAMES:
        return False

    # Skip if too short
    if len(normalized) < 3:
        return False

    # Skip if starts with common greeting/filler words
    if normalized.startswith(("thank ", "we ", "our ", "hi ", "hello ", "dear ")):
        return False

    # Skip if it looks like a sentence fragment
    if " if " in normalized or " will " in normalized or " be " in normalized:
        return False

    return True


def find_application_for_company(session, company: str) -> Optional[Application]:
    """Find an application matching the company name."""
    if not company:
        return None

    normalized = normalize_company(company)

    # Get all applications
    apps = session.execute(select(Application)).scalars().all()

    for app in apps:
        app_normalized = normalize_company(app.company)

        # Exact match
        if app_normalized == normalized:
            return app

        # Partial match (one contains the other)
        if normalized in app_normalized or app_normalized in normalized:
            return app

        # Handle "Meetcleo" vs "Cleo" type mismatches
        if normalized.replace("meet", "") == app_normalized or app_normalized.replace("meet", "") == normalized:
            return app

    return None


def reprocess_emails(dry_run: bool = False):
    """Reprocess all emails with the improved parser."""
    print("=" * 60)
    print("Reprocessing emails with improved parser")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print()

    init_db()
    parser = EmailParser()

    stats = {
        "total_emails": 0,
        "reparsed": 0,
        "linked": 0,
        "status_updated": 0,
        "apps_created": 0,
        "unchanged": 0,
    }

    with get_session() as session:
        # Get all email imports
        emails = session.execute(select(EmailImport)).scalars().all()
        stats["total_emails"] = len(emails)

        print(f"Found {len(emails)} email imports to process")
        print()

        for email_import in emails:
            # Create fake email object for parsing
            fake_email = FakeEmail(
                from_address=email_import.from_address or "",
                from_name="",
                subject=email_import.subject or "",
                date=email_import.received_at,
            )

            # Re-parse company
            old_company = email_import.parsed_data.get("company") if email_import.parsed_data else None
            new_company = parser._extract_company(fake_email)

            # Re-detect email type with new patterns
            text = f"{fake_email.subject}\n{fake_email.body_text}".lower()
            new_type, confidence = parser._detect_type(text)
            old_type = email_import.email_type

            # Update email type if it changed from unknown to something specific
            if old_type == "unknown" and new_type != EmailType.UNKNOWN:
                print(f"[TYPE] {email_import.subject[:50]}...")
                print(f"  Old type: {old_type} -> New type: {new_type.value}")
                if not dry_run:
                    email_import.email_type = new_type.value
                    email_import.parsed_data = {
                        **(email_import.parsed_data or {}),
                        "confidence": confidence,
                    }
                stats["reparsed"] += 1

            # Only update company if we got a different/better result
            if new_company and new_company != old_company and is_valid_company_name(new_company):
                stats["reparsed"] += 1
                print(f"[REPARSE] {email_import.subject[:50]}...")
                print(f"  Old company: {old_company} -> New company: {new_company}")

                if not dry_run:
                    email_import.parsed_data = {
                        **(email_import.parsed_data or {}),
                        "company": new_company,
                    }

            # Try to link to application
            company = new_company or old_company
            if company and not email_import.application_id:
                app = find_application_for_company(session, company)
                if app:
                    stats["linked"] += 1
                    print(f"[LINK] {email_import.email_type}: '{company}' -> Application '{app.company}'")

                    if not dry_run:
                        email_import.application_id = app.id
                        email_import.processed = True

                    # Update application status based on email type
                    app_service = ApplicationService(session)
                    if email_import.email_type == "rejection" and app.status not in ["rejected", "withdrawn"]:
                        print(f"  [STATUS] {app.company}: {app.status} -> rejected")
                        stats["status_updated"] += 1
                        if not dry_run:
                            app_service.update_status(
                                app.id, "rejected",
                                notes="Rejection email (reprocessed)",
                            )

                    elif email_import.email_type == "interview_invite" and app.status in ["applied"]:
                        print(f"  [STATUS] {app.company}: {app.status} -> interviewing")
                        stats["status_updated"] += 1
                        if not dry_run:
                            app_service.update_status(
                                app.id, "interviewing",
                                notes="Interview invite email (reprocessed)",
                            )

            # Check for confirmations without applications (create new app)
            if email_import.email_type == "confirmation" and company and not email_import.application_id:
                # Only create if it's a valid company name
                if is_valid_company_name(company):
                    app = find_application_for_company(session, company)
                    if not app:
                        print(f"[CREATE] New application for '{company}' from confirmation email")
                        stats["apps_created"] += 1

                        if not dry_run:
                            new_app = Application(
                                company=company,
                                position="Unknown Position",
                                applied_date=email_import.received_at or datetime.now(timezone.utc),
                                source="email_import",
                                status="applied",
                            )
                            session.add(new_app)
                            session.flush()  # Get the ID
                            email_import.application_id = new_app.id
                            email_import.processed = True

        if not dry_run:
            session.commit()

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Total emails: {stats['total_emails']}")
    print(f"  Re-parsed with new company: {stats['reparsed']}")
    print(f"  Linked to applications: {stats['linked']}")
    print(f"  Statuses updated: {stats['status_updated']}")
    print(f"  New applications created: {stats['apps_created']}")
    print("=" * 60)

    if dry_run:
        print("\nThis was a dry run. No changes were made.")
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    reprocess_emails(dry_run=dry_run)
