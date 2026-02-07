"""Backfill job descriptions for applications with NULL job_description.

Finds all applications missing a job_description, tries to link them
to a Job by company name, and copies the description over.

Usage:
    python scripts/backfill_job_descriptions.py          # Execute backfill
    python scripts/backfill_job_descriptions.py --dry-run # Preview only
"""
import argparse
import logging
import sys
from pathlib import Path

# Bootstrap imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.bootstrap import get_session, init_db
from src.logging_config import setup_logging
from src.tracking.application_service import ApplicationService
from src.persistence.models import Application
from sqlalchemy import or_, select

logger = logging.getLogger(__name__)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Backfill job descriptions for applications.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database.",
    )
    args = parser.parse_args()

    init_db()

    with get_session() as session:
        # Find applications with NULL or empty job_description
        stmt = select(Application).where(
            or_(
                Application.job_description.is_(None),
                Application.job_description == "",
            )
        ).order_by(Application.company)
        apps = session.execute(stmt).scalars().all()

        logger.info("Found %s applications without job descriptions.", len(apps))

        if not apps:
            logger.info("Nothing to backfill.")
            return

        service = ApplicationService(session)
        linked = 0
        skipped = 0

        for app in apps:
            service._try_link_to_job(app)

            if app.job_description:
                linked += 1
                desc_preview = app.job_description[:80].replace("\n", " ")
                logger.info("  [LINK] %s - %s", app.company, app.position)
                logger.info("         -> Job ID: %s", app.job_id)
                logger.info("         -> Description: %s...", desc_preview)
            else:
                skipped += 1
                logger.info("  [SKIP] %s - %s (no matching job found)", app.company, app.position)

        logger.info("Summary: %s linked, %s skipped", linked, skipped)

        if args.dry_run:
            logger.info("--dry-run mode: rolling back changes.")
            session.rollback()
        else:
            session.commit()
            logger.info("Committed %s updates to database.", linked)


if __name__ == "__main__":
    main()
