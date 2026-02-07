#!/usr/bin/env python
"""
Clean up orphaned records in the database.

This script removes records that reference non-existent parent records.
Always run validate_before_migration.py first to see what will be cleaned.

Usage:
    python scripts/cleanup_orphaned_records.py
"""
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.logging_config import setup_logging
from src.persistence.database import get_session
from src.persistence.models import (
    Application,
    EmailImport,
    Interview,
    StatusHistory,
)

logger = logging.getLogger(__name__)


def cleanup_orphaned_status_history() -> int:
    """Remove status history records with invalid application_id."""
    with get_session() as session:
        # Get all valid application IDs
        app_ids_stmt = select(Application.id)
        app_ids = {row[0] for row in session.execute(app_ids_stmt).fetchall()}

        # Find and delete orphans
        history_stmt = select(StatusHistory).where(
            StatusHistory.application_id.notin_(app_ids)
        )
        orphans = session.execute(history_stmt).scalars().all()

        count = len(orphans)
        for orphan in orphans:
            session.delete(orphan)

        session.commit()
        return count


def cleanup_orphaned_interviews() -> int:
    """Remove interview records with invalid application_id."""
    with get_session() as session:
        # Get all valid application IDs
        app_ids_stmt = select(Application.id)
        app_ids = {row[0] for row in session.execute(app_ids_stmt).fetchall()}

        # Find and delete orphans
        interview_stmt = select(Interview).where(
            Interview.application_id.notin_(app_ids)
        )
        orphans = session.execute(interview_stmt).scalars().all()

        count = len(orphans)
        for orphan in orphans:
            session.delete(orphan)

        session.commit()
        return count


def cleanup_orphaned_email_imports() -> int:
    """Remove email import records with invalid application_id."""
    with get_session() as session:
        # Get all valid application IDs
        app_ids_stmt = select(Application.id)
        app_ids = {row[0] for row in session.execute(app_ids_stmt).fetchall()}

        # Find email imports with non-null invalid application_id
        email_stmt = select(EmailImport).where(
            EmailImport.application_id.isnot(None),
            EmailImport.application_id.notin_(app_ids)
        )
        orphans = session.execute(email_stmt).scalars().all()

        count = len(orphans)
        for orphan in orphans:
            # Don't delete, just unlink
            orphan.application_id = None

        session.commit()
        return count


def main():
    """Run cleanup and log results."""
    setup_logging()

    logger.info("=" * 60)
    logger.info("Orphaned Records Cleanup")
    logger.info("=" * 60)

    # Cleanup status history
    logger.info("Cleaning up orphaned status history records...")
    history_count = cleanup_orphaned_status_history()
    logger.info("  Removed %s orphaned status history records", history_count)

    # Cleanup interviews
    logger.info("Cleaning up orphaned interview records...")
    interview_count = cleanup_orphaned_interviews()
    logger.info("  Removed %s orphaned interview records", interview_count)

    # Cleanup email imports
    logger.info("Cleaning up orphaned email import references...")
    email_count = cleanup_orphaned_email_imports()
    logger.info("  Unlinked %s email import records", email_count)

    total = history_count + interview_count + email_count
    logger.info("Cleanup complete. Total records cleaned: %s", total)


if __name__ == "__main__":
    main()
