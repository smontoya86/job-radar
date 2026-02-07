"""Fix rejection analysis data issues.

1. Fix bad `rejected_at` values ("rejected" -> "applied", None -> "applied")
2. Run backfill to link applications to Jobs and copy descriptions
3. Create applications for unlinked rejection emails

Usage:
    python scripts/fix_rejection_data.py          # Execute fixes
    python scripts/fix_rejection_data.py --dry-run # Preview only
"""
import argparse
import logging
import re
import sys
from pathlib import Path

# Bootstrap imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.bootstrap import get_session, init_db
from src.logging_config import setup_logging
from src.tracking.application_service import ApplicationService
from src.persistence.models import Application, EmailImport
from src.gmail.parser import EmailParser, EmailType, ParsedEmail
from src.gmail.client import EmailMessage
from sqlalchemy import or_, select

logger = logging.getLogger(__name__)


def fix_rejected_at(session, dry_run: bool) -> int:
    """Fix bad rejected_at values."""
    logger.info("=== Fix 1: Repair rejected_at values ===")
    stmt = select(Application).where(Application.status == "rejected")
    apps = session.execute(stmt).scalars().all()

    fixed = 0
    for app in apps:
        if app.rejected_at in ("rejected", None, ""):
            old_val = repr(app.rejected_at)
            app.rejected_at = "applied"
            fixed += 1
            logger.info("  [FIX] %s: rejected_at %s -> 'applied'", app.company, old_val)

    logger.info("  Fixed %s of %s rejected applications", fixed, len(apps))
    return fixed


def backfill_descriptions(session, dry_run: bool) -> int:
    """Link applications to Jobs and copy descriptions."""
    logger.info("=== Fix 2: Backfill job descriptions ===")
    stmt = select(Application).where(
        or_(
            Application.job_description.is_(None),
            Application.job_description == "",
        )
    ).order_by(Application.company)
    apps = session.execute(stmt).scalars().all()

    logger.info("  Found %s applications without job descriptions", len(apps))

    service = ApplicationService(session)
    linked = 0

    for app in apps:
        service._try_link_to_job(app)
        if app.job_description:
            linked += 1
            desc_preview = app.job_description[:60].replace("\n", " ")
            logger.info("  [LINK] %s - %s -> %s...", app.company, app.position, desc_preview)
        else:
            logger.info("  [SKIP] %s - %s (no matching job)", app.company, app.position)

    logger.info("  Linked %s of %s applications", linked, len(apps))
    return linked


def create_apps_from_unlinked_emails(session, dry_run: bool) -> int:
    """Create applications for unlinked rejection emails."""
    logger.info("=== Fix 3: Process unlinked rejection emails ===")
    stmt = select(EmailImport).where(
        EmailImport.email_type == "rejection",
        EmailImport.application_id.is_(None),
    )
    unlinked = session.execute(stmt).scalars().all()
    logger.info("  Found %s unlinked rejection emails", len(unlinked))

    parser = EmailParser()
    service = ApplicationService(session)
    created = 0
    skipped = 0

    for email_import in unlinked:
        subject = email_import.subject or ""

        # Check exclusion patterns (referral requests, etc.) — these are false positives
        is_excluded = any(
            re.search(pat, subject, re.IGNORECASE)
            for pat in parser.EXCLUSION_PATTERNS
        )
        if is_excluded:
            logger.info("  [EXCLUDE] '%s' - matches exclusion pattern", subject)
            email_import.email_type = "unknown"
            skipped += 1
            continue

        # Build minimal EmailMessage for company extraction only
        # (trust original rejection classification — body was available then)
        email_msg = EmailMessage(
            id=email_import.gmail_message_id or "",
            thread_id="",
            subject=subject,
            from_address=email_import.from_address or "",
            from_name="",
            to_address="",
            date=email_import.received_at,
            body_text="",
            snippet="",
        )

        # Extract company using improved parser
        company = parser._extract_company(email_msg)

        if not company:
            logger.info("  [SKIP] '%s' - no company extracted", subject)
            skipped += 1
            continue

        # Check if an application already exists for this company
        existing = service._find_application_by_company(company)
        if existing:
            email_import.application_id = existing.id
            email_import.processed = True
            if existing.status != "rejected":
                service.update_status(existing.id, "rejected", notes="Rejection email (reprocessed)")
            logger.info("  [LINK] '%s' -> existing app for %s", subject, existing.company)
            skipped += 1
            continue

        # Create new application from rejection email
        parsed_email = ParsedEmail(
            email_type=EmailType.REJECTION,
            company=company,
            confidence=0.8,
        )
        app = service.create_from_email(parsed_email)
        if app:
            email_import.application_id = app.id
            email_import.processed = True
            created += 1
            logger.info("  [CREATE] %s - %s (status: %s)", app.company, app.position, app.status)
        else:
            skipped += 1
            logger.info("  [SKIP] '%s' - create_from_email returned None", subject)

    logger.info("  Created %s, skipped %s", created, skipped)
    return created


def main():
    setup_logging()

    arg_parser = argparse.ArgumentParser(description="Fix rejection analysis data issues.")
    arg_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database.",
    )
    args = arg_parser.parse_args()

    init_db()

    with get_session() as session:
        total_fixes = 0

        total_fixes += fix_rejected_at(session, args.dry_run)
        total_fixes += backfill_descriptions(session, args.dry_run)
        total_fixes += create_apps_from_unlinked_emails(session, args.dry_run)

        # Summary
        logger.info("=" * 50)
        if args.dry_run:
            logger.info("DRY RUN: Would apply %s fixes. Rolling back.", total_fixes)
            session.rollback()
        else:
            session.commit()
            logger.info("Applied %s fixes to database.", total_fixes)

        # Final stats
        from sqlalchemy import func
        rejected_count = session.query(func.count(Application.id)).filter(
            Application.status == "rejected"
        ).scalar()
        with_desc = session.query(func.count(Application.id)).filter(
            Application.status == "rejected",
            Application.job_description.isnot(None),
            Application.job_description != "",
        ).scalar()
        logger.info("Rejected applications: %s", rejected_count)
        logger.info("With descriptions: %s", with_desc)
        coverage = with_desc / rejected_count * 100 if rejected_count else 0
        logger.info("Analysis coverage: %s%%", f"{coverage:.0f}")


if __name__ == "__main__":
    main()
