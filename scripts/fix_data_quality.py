#!/usr/bin/env python3
"""Fix data quality issues identified by system audit.

Fixes:
1. Delete 2 applications with garbage company names (sentence fragments)
2. Strip "the" prefix from 3 positions
3. Backfill source from email sender domain (108 apps with "email_import")

Usage:
    python scripts/fix_data_quality.py --dry-run   # Preview changes
    python scripts/fix_data_quality.py              # Apply changes
"""
import logging
import sys

from scripts.bootstrap import get_session, init_db
from src.logging_config import setup_logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def fix_garbage_companies(session, dry_run: bool) -> int:
    """Delete applications with garbage company names (sentence fragments)."""
    garbage = session.execute(text(
        "SELECT id, company, position FROM applications "
        "WHERE LENGTH(company) > 50 "
        "OR LOWER(company) LIKE '%our exceptional%' "
        "OR LOWER(company) LIKE '%working here means%' "
        "OR LOWER(company) LIKE '%thank you for submitting%'"
    )).fetchall()

    if not garbage:
        logger.info("  No garbage company names found")
        return 0

    for row in garbage:
        logger.info("  %s: company='%s' position='%s'",
                     "WOULD DELETE" if dry_run else "DELETING", row[1][:50], row[2][:40])
        if not dry_run:
            # Delete related records first
            session.execute(text("DELETE FROM status_history WHERE application_id = :id"), {"id": row[0]})
            session.execute(text("DELETE FROM interviews WHERE application_id = :id"), {"id": row[0]})
            session.execute(text("UPDATE email_imports SET application_id = NULL WHERE application_id = :id"), {"id": row[0]})
            session.execute(text("DELETE FROM applications WHERE id = :id"), {"id": row[0]})

    return len(garbage)


def fix_the_prefix_positions(session, dry_run: bool) -> int:
    """Strip 'the' prefix from positions like 'the Staff Product Manager, AI'."""
    rows = session.execute(text(
        "SELECT id, company, position FROM applications WHERE LOWER(position) LIKE 'the %'"
    )).fetchall()

    if not rows:
        logger.info("  No positions with 'the' prefix found")
        return 0

    for row in rows:
        import re
        new_position = re.sub(r"^the\s+", "", row[2], flags=re.IGNORECASE)
        logger.info("  %s: %s '%s' -> '%s'",
                     "WOULD FIX" if dry_run else "FIXING", row[1], row[2], new_position)
        if not dry_run:
            session.execute(text(
                "UPDATE applications SET position = :pos WHERE id = :id"
            ), {"pos": new_position, "id": row[0]})

    return len(rows)


def backfill_source_from_email(session, dry_run: bool) -> int:
    """Backfill application source from email sender domain."""
    from src.gmail.parser import EmailParser

    # Find applications with source='email_import' that have linked emails
    rows = session.execute(text("""
        SELECT DISTINCT a.id, a.company, a.source, e.from_address
        FROM applications a
        JOIN email_imports e ON e.application_id = a.id
        WHERE a.source = 'email_import'
        AND e.from_address IS NOT NULL
        ORDER BY a.company
    """)).fetchall()

    if not rows:
        logger.info("  No applications to backfill source for")
        return 0

    updated = 0
    for row in rows:
        app_id, company, old_source, from_address = row
        new_source = EmailParser.infer_source(from_address)

        if new_source != "email_import":
            logger.info("  %s: %s '%s' -> '%s' (from %s)",
                         "WOULD UPDATE" if dry_run else "UPDATING",
                         company, old_source, new_source, from_address)
            if not dry_run:
                session.execute(text(
                    "UPDATE applications SET source = :src WHERE id = :id"
                ), {"src": new_source, "id": app_id})
            updated += 1

    return updated


def main():
    setup_logging()
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("DRY RUN MODE — no changes will be made")
    logger.info("")

    init_db()

    with get_session() as session:
        logger.info("1. Fixing garbage company names...")
        deleted = fix_garbage_companies(session, dry_run)
        logger.info("   %s %d garbage records", "Would delete" if dry_run else "Deleted", deleted)
        logger.info("")

        logger.info("2. Fixing 'the' prefix positions...")
        fixed_pos = fix_the_prefix_positions(session, dry_run)
        logger.info("   %s %d positions", "Would fix" if dry_run else "Fixed", fixed_pos)
        logger.info("")

        logger.info("3. Backfilling source from email domains...")
        backfilled = backfill_source_from_email(session, dry_run)
        logger.info("   %s %d sources", "Would update" if dry_run else "Updated", backfilled)
        logger.info("")

        if not dry_run:
            session.commit()
            logger.info("All changes committed.")
        else:
            logger.info("Dry run complete. Run without --dry-run to apply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
