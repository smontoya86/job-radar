#!/usr/bin/env python
"""
Clean up orphaned records in the database.

This script removes records that reference non-existent parent records.
Always run validate_before_migration.py first to see what will be cleaned.

Usage:
    python scripts/cleanup_orphaned_records.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.persistence.database import get_session
from src.persistence.models import (
    Application,
    EmailImport,
    Interview,
    StatusHistory,
)


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
    """Run cleanup and print results."""
    print("=" * 60)
    print("Orphaned Records Cleanup")
    print("=" * 60)

    # Cleanup status history
    print("\nCleaning up orphaned status history records...")
    history_count = cleanup_orphaned_status_history()
    print(f"  Removed {history_count} orphaned status history records")

    # Cleanup interviews
    print("\nCleaning up orphaned interview records...")
    interview_count = cleanup_orphaned_interviews()
    print(f"  Removed {interview_count} orphaned interview records")

    # Cleanup email imports
    print("\nCleaning up orphaned email import references...")
    email_count = cleanup_orphaned_email_imports()
    print(f"  Unlinked {email_count} email import records")

    total = history_count + interview_count + email_count
    print(f"\n✅ Cleanup complete. Total records cleaned: {total}")


if __name__ == "__main__":
    main()
