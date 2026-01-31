#!/usr/bin/env python3
"""One-time job scan for GitHub Actions.

This script runs a single job scan cycle and exits.
Designed for ephemeral CI/CD environments like GitHub Actions.

Usage:
    python scripts/run_scan.py

Environment variables:
    DATABASE_URL: PostgreSQL connection string (required)
    SLACK_WEBHOOK_URL: Slack webhook for notifications (optional)
"""
import asyncio
import sys

from scripts.bootstrap import settings, init_db
from src.persistence.cleanup import cleanup_stale_data
from src.main import run_job_scan


async def main():
    """Run a single job scan with cleanup."""
    print("Job Radar - One-time Scan")
    print("=" * 40)
    print(f"Database: {settings.database_url[:50]}...")
    print(f"Profile: {settings.profile_path}")
    print()

    # Initialize database
    init_db()
    print("Database initialized")

    # Run cleanup before scan
    cleanup_results = cleanup_stale_data()
    print()

    # Run the job scan
    await run_job_scan()

    print("\nScan complete. Exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
