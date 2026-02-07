#!/usr/bin/env python3
"""Data repair script for system audit issues.

Fixes:
- Merge duplicate application pairs (Experian, LegitScript, Sketchy)
- Clean "nan" descriptions in Job and Application tables
- Clean "nan" company names in Job table
- Unlink wrongly-linked emails from Coursera
- Remove duplicate Coursera interview rounds

Usage:
    python scripts/fix_audit_issues.py --dry-run   # Preview changes
    python scripts/fix_audit_issues.py              # Apply changes
"""
import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.bootstrap import get_session, init_db

from sqlalchemy import select, update, delete, func, text
from src.logging_config import setup_logging
from src.persistence.models import (
    Application, EmailImport, Interview, Job, StatusHistory,
)

logger = logging.getLogger(__name__)


def fix_nan_descriptions(session, dry_run: bool) -> int:
    """Clean 'nan' string descriptions in Job and Application tables."""
    # Jobs
    stmt = select(func.count(Job.id)).where(
        func.lower(Job.description) == "nan"
    )
    job_count = session.execute(stmt).scalar() or 0
    logger.info("  Jobs with 'nan' description: %s", job_count)

    if not dry_run and job_count > 0:
        session.execute(
            update(Job).where(func.lower(Job.description) == "nan").values(description=None)
        )

    # Applications
    stmt = select(func.count(Application.id)).where(
        func.lower(Application.job_description) == "nan"
    )
    app_count = session.execute(stmt).scalar() or 0
    logger.info("  Applications with 'nan' job_description: %s", app_count)

    if not dry_run and app_count > 0:
        session.execute(
            update(Application)
            .where(func.lower(Application.job_description) == "nan")
            .values(job_description=None)
        )

    return job_count + app_count


def fix_nan_companies(session, dry_run: bool) -> int:
    """Clean 'nan' string company names in Job table."""
    stmt = select(func.count(Job.id)).where(func.lower(Job.company) == "nan")
    count = session.execute(stmt).scalar() or 0
    logger.info("  Jobs with 'nan' company: %s", count)

    if not dry_run and count > 0:
        # Delete these junk records since a job without a company is useless
        session.execute(
            delete(Job).where(func.lower(Job.company) == "nan")
        )

    return count


def merge_duplicate_applications(session, dry_run: bool) -> int:
    """Merge duplicate application pairs. Keep the rejected one, merge data from applied."""
    # Find companies with duplicate applications
    stmt = (
        select(Application.company, func.count(Application.id))
        .group_by(func.lower(Application.company))
        .having(func.count(Application.id) > 1)
    )
    result = session.execute(stmt)
    duplicates = list(result.all())

    if not duplicates:
        logger.info("  No duplicate applications found.")
        return 0

    merged = 0
    for company, count in duplicates:
        logger.info("  Duplicate: %s (%s records)", company, count)

        # Get all apps for this company
        stmt = (
            select(Application)
            .where(func.lower(Application.company) == company.lower())
            .order_by(Application.applied_date)
        )
        apps = list(session.execute(stmt).scalars().all())

        if len(apps) < 2:
            continue

        # Keep the one with the most data (prefer rejected since it has more history)
        keep = None
        remove = []
        for app in apps:
            if app.status == "rejected":
                keep = app
            else:
                remove.append(app)

        if not keep:
            keep = apps[0]
            remove = apps[1:]

        for dup in remove:
            logger.info("    Merging %s (%s) into %s (%s)", dup.id, dup.status, keep.id, keep.status)

            if not dry_run:
                # Re-link emails from duplicate to keeper
                session.execute(
                    update(EmailImport)
                    .where(EmailImport.application_id == dup.id)
                    .values(application_id=keep.id)
                )

                # Re-link interviews
                session.execute(
                    update(Interview)
                    .where(Interview.application_id == dup.id)
                    .values(application_id=keep.id)
                )

                # Re-link status history
                session.execute(
                    update(StatusHistory)
                    .where(StatusHistory.application_id == dup.id)
                    .values(application_id=keep.id)
                )

                # Copy missing fields from duplicate to keeper
                if not keep.job_id and dup.job_id:
                    keep.job_id = dup.job_id
                if not keep.job_description and dup.job_description:
                    keep.job_description = dup.job_description
                if not keep.resume_id and dup.resume_id:
                    keep.resume_id = dup.resume_id

                # Delete the duplicate
                session.delete(dup)

            merged += 1

    return merged


def fix_wrongly_linked_emails(session, dry_run: bool) -> int:
    """Unlink emails that were wrongly linked to Coursera via partial 'our' match."""
    # Find Coursera application
    stmt = select(Application).where(
        func.lower(Application.company) == "coursera"
    )
    coursera_app = session.execute(stmt).scalars().first()
    if not coursera_app:
        logger.info("  No Coursera application found.")
        return 0

    # Find emails linked to Coursera that don't mention Coursera in subject
    stmt = select(EmailImport).where(
        EmailImport.application_id == coursera_app.id
    )
    emails = list(session.execute(stmt).scalars().all())

    unlinked = 0
    for email in emails:
        subject = (email.subject or "").lower()
        if "coursera" not in subject:
            logger.info("    Unlinking: '%s' (from %s)", email.subject, email.from_address)
            if not dry_run:
                email.application_id = None
                email.processed = False
            unlinked += 1

    return unlinked


def fix_duplicate_interviews(session, dry_run: bool) -> int:
    """Remove duplicate Coursera interview rounds (reply email duplicates)."""
    # Find Coursera application
    stmt = select(Application).where(
        func.lower(Application.company) == "coursera"
    )
    coursera_app = session.execute(stmt).scalars().first()
    if not coursera_app:
        logger.info("  No Coursera application found.")
        return 0

    # Get all interviews for Coursera
    stmt = (
        select(Interview)
        .where(Interview.application_id == coursera_app.id)
        .order_by(Interview.round)
    )
    interviews = list(session.execute(stmt).scalars().all())

    if len(interviews) <= 2:
        logger.info("  Coursera has %s interviews, no duplicates to remove.", len(interviews))
        return 0

    # Keep rounds 1 and 2, remove any beyond that
    removed = 0
    for interview in interviews:
        if interview.round > 2:
            logger.info("    Removing interview round %s: %s", interview.round, interview.notes or interview.type)
            if not dry_run:
                session.delete(interview)
            removed += 1

    # Fix interview_rounds count
    if not dry_run and removed > 0:
        coursera_app.interview_rounds = 2

    return removed


def main():
    """Run data repair."""
    parser = argparse.ArgumentParser(description="Fix audit issues in database")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    dry_run = args.dry_run
    mode = "DRY RUN" if dry_run else "APPLY"

    setup_logging()

    logger.info("Data Repair Script [%s]", mode)
    logger.info("=" * 50)

    init_db()

    with get_session() as session:
        total_fixes = 0

        logger.info("1. Cleaning 'nan' descriptions...")
        total_fixes += fix_nan_descriptions(session, dry_run)

        logger.info("2. Cleaning 'nan' company names...")
        total_fixes += fix_nan_companies(session, dry_run)

        logger.info("3. Merging duplicate applications...")
        total_fixes += merge_duplicate_applications(session, dry_run)

        logger.info("4. Unlinking wrongly-linked emails...")
        total_fixes += fix_wrongly_linked_emails(session, dry_run)

        logger.info("5. Removing duplicate interviews...")
        total_fixes += fix_duplicate_interviews(session, dry_run)

        if not dry_run:
            session.commit()
            logger.info("Committed %s fixes to database.", total_fixes)
        else:
            logger.info("[DRY RUN] Would apply %s fixes. Run without --dry-run to apply.", total_fixes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
