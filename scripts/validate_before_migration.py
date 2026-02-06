#!/usr/bin/env python
"""
Validate database integrity before running migrations.

This script should be run before any migration to ensure:
1. No orphaned records exist
2. No duplicate fingerprints
3. All foreign key relationships are valid
4. Data is in expected format

Usage:
    python scripts/validate_before_migration.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select

from src.persistence.database import get_session
from src.persistence.models import (
    Application,
    EmailImport,
    Interview,
    Job,
    Resume,
    StatusHistory,
)


def validate_data_integrity() -> list[str]:
    """
    Run all validation checks on the database.

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors = []

    with get_session() as session:
        # Check 1: Orphaned interviews (application_id doesn't exist)
        orphaned_interviews = _check_orphaned_interviews(session)
        if orphaned_interviews > 0:
            errors.append(f"Found {orphaned_interviews} orphaned interview records")

        # Check 2: Orphaned status history (application_id doesn't exist)
        orphaned_history = _check_orphaned_status_history(session)
        if orphaned_history > 0:
            errors.append(f"Found {orphaned_history} orphaned status history records")

        # Check 3: Duplicate job fingerprints
        duplicate_fingerprints = _check_duplicate_fingerprints(session)
        if duplicate_fingerprints:
            errors.append(
                f"Found {len(duplicate_fingerprints)} duplicate job fingerprints: "
                f"{', '.join(duplicate_fingerprints[:5])}{'...' if len(duplicate_fingerprints) > 5 else ''}"
            )

        # Check 4: Invalid application statuses
        invalid_statuses = _check_invalid_statuses(session)
        if invalid_statuses:
            errors.append(
                f"Found {len(invalid_statuses)} applications with invalid status: "
                f"{', '.join(invalid_statuses[:5])}"
            )

        # Check 5: Applications with invalid resume_id
        invalid_resume_refs = _check_invalid_resume_references(session)
        if invalid_resume_refs > 0:
            errors.append(f"Found {invalid_resume_refs} applications with invalid resume_id")

        # Check 6: Email imports with invalid application_id
        invalid_email_refs = _check_invalid_email_references(session)
        if invalid_email_refs > 0:
            errors.append(f"Found {invalid_email_refs} email imports with invalid application_id")

    return errors


def _check_orphaned_interviews(session) -> int:
    """Check for interviews without valid application."""
    # Get all application IDs
    app_ids_stmt = select(Application.id)
    app_ids = {row[0] for row in session.execute(app_ids_stmt).fetchall()}

    # Get all interview application_ids
    interview_stmt = select(Interview.application_id).distinct()
    interview_app_ids = {row[0] for row in session.execute(interview_stmt).fetchall()}

    # Find orphans
    orphaned = interview_app_ids - app_ids
    return len(orphaned)


def _check_orphaned_status_history(session) -> int:
    """Check for status history without valid application."""
    app_ids_stmt = select(Application.id)
    app_ids = {row[0] for row in session.execute(app_ids_stmt).fetchall()}

    history_stmt = select(StatusHistory.application_id).distinct()
    history_app_ids = {row[0] for row in session.execute(history_stmt).fetchall()}

    orphaned = history_app_ids - app_ids
    return len(orphaned)


def _check_duplicate_fingerprints(session) -> list[str]:
    """Check for duplicate job fingerprints."""
    stmt = (
        select(Job.fingerprint)
        .group_by(Job.fingerprint)
        .having(func.count(Job.id) > 1)
    )
    result = session.execute(stmt).fetchall()
    return [row[0] for row in result if row[0]]


def _check_invalid_statuses(session) -> list[str]:
    """Check for applications with invalid status values."""
    valid_statuses = {
        "applied",
        "phone_screen",
        "interviewing",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "ghosted",
    }

    stmt = select(Application.status).distinct()
    all_statuses = {row[0] for row in session.execute(stmt).fetchall()}

    invalid = all_statuses - valid_statuses
    return list(invalid)


def _check_invalid_resume_references(session) -> int:
    """Check for applications with invalid resume_id."""
    # Get all resume IDs
    resume_ids_stmt = select(Resume.id)
    resume_ids = {row[0] for row in session.execute(resume_ids_stmt).fetchall()}
    resume_ids.add(None)  # None is valid (no resume)

    # Get all application resume_ids
    app_stmt = select(Application.resume_id).where(Application.resume_id.isnot(None))
    app_resume_ids = {row[0] for row in session.execute(app_stmt).fetchall()}

    # Find invalid
    invalid = app_resume_ids - resume_ids
    return len(invalid)


def _check_invalid_email_references(session) -> int:
    """Check for email imports with invalid application_id."""
    # Get all application IDs
    app_ids_stmt = select(Application.id)
    app_ids = {row[0] for row in session.execute(app_ids_stmt).fetchall()}
    app_ids.add(None)  # None is valid (not linked)

    # Get all email import application_ids
    email_stmt = select(EmailImport.application_id).where(EmailImport.application_id.isnot(None))
    email_app_ids = {row[0] for row in session.execute(email_stmt).fetchall()}

    # Find invalid
    invalid = email_app_ids - app_ids
    return len(invalid)


def get_table_counts() -> dict[str, int]:
    """Get row counts for all tables."""
    counts = {}

    with get_session() as session:
        counts["jobs"] = session.query(func.count(Job.id)).scalar() or 0
        counts["applications"] = session.query(func.count(Application.id)).scalar() or 0
        counts["resumes"] = session.query(func.count(Resume.id)).scalar() or 0
        counts["interviews"] = session.query(func.count(Interview.id)).scalar() or 0
        counts["email_imports"] = session.query(func.count(EmailImport.id)).scalar() or 0
        counts["status_history"] = session.query(func.count(StatusHistory.id)).scalar() or 0

    return counts


def main():
    """Run validation and print results."""
    print("=" * 60)
    print("Database Integrity Validation")
    print("=" * 60)

    # Print table counts
    print("\nTable counts:")
    counts = get_table_counts()
    for table, count in counts.items():
        print(f"  {table}: {count}")

    # Run validation
    print("\nRunning validation checks...")
    errors = validate_data_integrity()

    if errors:
        print("\n❌ VALIDATION FAILED")
        print("-" * 40)
        for error in errors:
            print(f"  - {error}")
        print("\nPlease fix these issues before running migrations.")
        sys.exit(1)
    else:
        print("\n✅ All validation checks passed!")
        print("Database is ready for migration.")
        sys.exit(0)


if __name__ == "__main__":
    main()
