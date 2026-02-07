#!/usr/bin/env python3
"""Migrate application statuses to simplified system.

Old statuses: applied, screening, phone_screen, interview, onsite, offer, accepted, rejected, withdrawn, ghosted

New statuses: applied, phone_screen, interviewing, offer, accepted, rejected, withdrawn, ghosted

Migration mappings:
- screening -> phone_screen
- interview -> interviewing
- onsite -> interviewing

Also updates all existing records to ensure consistency.
"""
import logging
import sys
from sqlalchemy import select, update

from scripts.bootstrap import get_session, init_db
from src.logging_config import setup_logging
from src.persistence.models import Application, StatusHistory

logger = logging.getLogger(__name__)

# Status migration mapping
STATUS_MIGRATION = {
    "screening": "phone_screen",
    "interview": "interviewing",
    "onsite": "interviewing",
}


def migrate_statuses():
    """Migrate old statuses to new simplified statuses."""
    init_db()

    with get_session() as session:
        # Get counts before migration
        logger.info("Status counts before migration:")
        stmt = select(Application.status, Application.id)
        result = session.execute(stmt)
        apps = result.all()

        status_counts = {}
        for status, _ in apps:
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in sorted(status_counts.items()):
            migration_note = f" -> {STATUS_MIGRATION[status]}" if status in STATUS_MIGRATION else ""
            logger.info("  %s: %s%s", status, count, migration_note)

        # Migrate each old status
        migrated = 0
        for old_status, new_status in STATUS_MIGRATION.items():
            # Update applications
            stmt = update(Application).where(
                Application.status == old_status
            ).values(status=new_status)
            result = session.execute(stmt)
            count = result.rowcount
            if count > 0:
                logger.info("Migrated %s applications from '%s' to '%s'", count, old_status, new_status)
                migrated += count

            # Update status history (old_status column)
            stmt = update(StatusHistory).where(
                StatusHistory.old_status == old_status
            ).values(old_status=new_status)
            session.execute(stmt)

            # Update status history (new_status column)
            stmt = update(StatusHistory).where(
                StatusHistory.new_status == old_status
            ).values(new_status=new_status)
            session.execute(stmt)

        session.commit()

        # Get counts after migration
        logger.info("Status counts after migration:")
        stmt = select(Application.status, Application.id)
        result = session.execute(stmt)
        apps = result.all()

        status_counts = {}
        for status, _ in apps:
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in sorted(status_counts.items()):
            logger.info("  %s: %s", status, count)

        logger.info("Total applications migrated: %s", migrated)
        logger.info("Migration complete!")


if __name__ == "__main__":
    setup_logging()
    migrate_statuses()
