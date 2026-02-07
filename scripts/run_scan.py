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
import logging
import sys

from scripts.bootstrap import settings, init_db
from src.logging_config import setup_logging
from src.persistence.cleanup import cleanup_stale_data
from src.main import run_job_scan

logger = logging.getLogger(__name__)


async def main():
    """Run a single job scan with cleanup."""
    setup_logging()

    logger.info("Job Radar - One-time Scan")
    logger.info("=" * 40)
    logger.info("Database: %s...", settings.database_url[:50])
    logger.info("Profile: %s", settings.profile_path)
    logger.info("")

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Run cleanup before scan
    cleanup_results = cleanup_stale_data()
    logger.info("")

    # Run the job scan
    await run_job_scan()

    logger.info("Scan complete. Exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(1)
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)
