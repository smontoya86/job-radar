"""Backfill job descriptions for applications with NULL job_description.

Finds all applications missing a job_description, tries to link them
to a Job by company name, and copies the description over.

Usage:
    python scripts/backfill_job_descriptions.py          # Execute backfill
    python scripts/backfill_job_descriptions.py --dry-run # Preview only
"""
import argparse
import sys
from pathlib import Path

# Bootstrap imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.bootstrap import get_session, init_db
from src.tracking.application_service import ApplicationService
from src.persistence.models import Application
from sqlalchemy import or_, select


def main():
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

        print(f"Found {len(apps)} applications without job descriptions.\n")

        if not apps:
            print("Nothing to backfill.")
            return

        service = ApplicationService(session)
        linked = 0
        skipped = 0

        for app in apps:
            service._try_link_to_job(app)

            if app.job_description:
                linked += 1
                desc_preview = app.job_description[:80].replace("\n", " ")
                print(f"  [LINK] {app.company} - {app.position}")
                print(f"         → Job ID: {app.job_id}")
                print(f"         → Description: {desc_preview}...")
            else:
                skipped += 1
                print(f"  [SKIP] {app.company} - {app.position} (no matching job found)")

        print(f"\nSummary: {linked} linked, {skipped} skipped")

        if args.dry_run:
            print("\n--dry-run mode: rolling back changes.")
            session.rollback()
        else:
            session.commit()
            print(f"\nCommitted {linked} updates to database.")


if __name__ == "__main__":
    main()
