"""Database cleanup utilities for storage optimization."""
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update

from src.persistence.database import get_session
from src.persistence.models import Job


def delete_old_jobs(days: int = 60) -> int:
    """Delete jobs older than specified days.

    Preserves jobs that have been applied to, saved, or have applications.

    Args:
        days: Number of days to keep jobs (default 60)

    Returns:
        Number of jobs deleted
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    with get_session() as session:
        # Find jobs to delete:
        # - Older than cutoff
        # - Not saved or applied
        # - No linked applications
        stmt = (
            delete(Job)
            .where(Job.discovered_at < cutoff_date)
            .where(Job.status.in_(["new", "dismissed"]))
        )

        # For jobs with applications, we need to check differently
        # First, get IDs of jobs that have applications
        jobs_with_apps = select(Job.id).join(Job.applications)

        # Delete old jobs that have no applications and aren't saved/applied
        result = session.execute(
            delete(Job)
            .where(Job.discovered_at < cutoff_date)
            .where(Job.status.in_(["new", "dismissed"]))
            .where(Job.id.notin_(jobs_with_apps))
        )

        deleted_count = result.rowcount
        session.commit()

        return deleted_count


def truncate_descriptions(max_chars: int = 2000) -> int:
    """Truncate job descriptions longer than max_chars.

    Adds ellipsis to indicate truncation.

    Args:
        max_chars: Maximum characters to keep (default 2000)

    Returns:
        Number of jobs truncated
    """
    with get_session() as session:
        # Find jobs with long descriptions
        from sqlalchemy import func

        stmt = select(Job).where(func.length(Job.description) > max_chars)
        result = session.execute(stmt)
        jobs = result.scalars().all()

        truncated_count = 0
        for job in jobs:
            if job.description and len(job.description) > max_chars:
                job.description = job.description[:max_chars - 3] + "..."
                truncated_count += 1

        session.commit()

        return truncated_count


def cleanup_stale_data() -> dict:
    """Run all cleanup operations.

    Call this before each scan to maintain storage limits.

    Returns:
        Dictionary with counts of each cleanup operation
    """
    print("Running database cleanup...")

    deleted = delete_old_jobs(days=60)
    if deleted > 0:
        print(f"  Deleted {deleted} jobs older than 60 days")

    truncated = truncate_descriptions(max_chars=2000)
    if truncated > 0:
        print(f"  Truncated {truncated} long descriptions")

    return {
        "deleted_jobs": deleted,
        "truncated_descriptions": truncated,
    }
