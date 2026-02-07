#!/usr/bin/env python3
"""Migrate data from SQLite to PostgreSQL.

Reads all records from the local SQLite database and inserts them
into the PostgreSQL database running in Docker.

Usage:
    python scripts/migrate_sqlite_to_postgres.py [--dry-run]
"""
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text, inspect, MetaData
from sqlalchemy.orm import sessionmaker

from src.logging_config import setup_logging
from src.persistence.models import Base

logger = logging.getLogger(__name__)

# Source: local SQLite
SQLITE_URL = "sqlite:///data/job_radar.db"

# Target: Docker PostgreSQL (use DATABASE_URL env var if set, else default)
import os
POSTGRES_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://jobradar:jobradar@localhost:5432/jobradar",
)

# Tables to migrate in order (respecting foreign key dependencies)
TABLE_ORDER = [
    "users",
    "user_profiles",
    "jobs",
    "applications",
    "resumes",
    "interviews",
    "email_imports",
    "status_history",
]


def migrate(dry_run: bool = False):
    """Migrate all data from SQLite to PostgreSQL."""
    logger.info("=" * 60)
    logger.info("Migrating data from SQLite to PostgreSQL")
    logger.info("=" * 60)
    logger.info("Source: %s", SQLITE_URL)
    logger.info("Target: %s", POSTGRES_URL.replace("jobradar:jobradar", "jobradar:***"))
    logger.info("Dry run: %s", dry_run)
    logger.info("")

    # Connect to both databases
    sqlite_engine = create_engine(SQLITE_URL)
    pg_engine = create_engine(POSTGRES_URL)

    # Ensure PostgreSQL tables exist
    Base.metadata.create_all(bind=pg_engine)
    logger.info("PostgreSQL tables created/verified")

    # Reflect SQLite metadata to get column info
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    pg_meta = MetaData()
    pg_meta.reflect(bind=pg_engine)

    total_migrated = 0

    for table_name in TABLE_ORDER:
        if table_name not in sqlite_meta.tables:
            logger.info("Skipping %s (not in SQLite)", table_name)
            continue

        sqlite_table = sqlite_meta.tables[table_name]

        with sqlite_engine.connect() as sqlite_conn:
            rows = sqlite_conn.execute(sqlite_table.select()).fetchall()
            column_names = [c.name for c in sqlite_table.columns]

        if not rows:
            logger.info("%-20s: 0 rows (empty)", table_name)
            continue

        # Get PostgreSQL table columns to filter out any SQLite-only columns
        if table_name in pg_meta.tables:
            pg_columns = {c.name for c in pg_meta.tables[table_name].columns}
        else:
            logger.warning("Table %s not found in PostgreSQL, skipping", table_name)
            continue

        # Filter columns to only those that exist in both databases
        common_columns = [c for c in column_names if c in pg_columns]

        if not dry_run:
            with pg_engine.connect() as pg_conn:
                # Check if table already has data
                existing = pg_conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar()

                if existing > 0:
                    logger.info("%-20s: %d rows already exist, skipping", table_name, existing)
                    continue

                # Identify JSON columns that need casting
                from sqlalchemy import JSON as SA_JSON
                pg_table = pg_meta.tables[table_name]
                json_columns = {
                    c.name for c in pg_table.columns
                    if isinstance(c.type, SA_JSON)
                }

                # Build insert statement (cast JSON columns)
                col_list = ", ".join(common_columns)
                param_list = ", ".join(
                    f"CAST(:{c} AS json)" if c in json_columns else f":{c}"
                    for c in common_columns
                )
                insert_sql = text(
                    f"INSERT INTO {table_name} ({col_list}) VALUES ({param_list})"
                )

                # Insert rows in batches
                batch_size = 100
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    row_dicts = []
                    for row in batch:
                        d = {c: getattr(row, c, None) for c in common_columns}
                        # Serialize JSON columns as strings for CAST
                        for jc in json_columns:
                            if jc in d and d[jc] is not None:
                                import json as json_mod
                                if isinstance(d[jc], (list, dict)):
                                    d[jc] = json_mod.dumps(d[jc])
                        row_dicts.append(d)
                    pg_conn.execute(insert_sql, row_dicts)

                pg_conn.commit()

        total_migrated += len(rows)
        logger.info("%-20s: %d rows migrated", table_name, len(rows))

    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration complete: %d total rows", total_migrated)
    logger.info("=" * 60)

    if dry_run:
        logger.info("This was a dry run. No data was written.")

    # Close engines
    sqlite_engine.dispose()
    pg_engine.dispose()


if __name__ == "__main__":
    setup_logging()
    dry_run = "--dry-run" in sys.argv
    migrate(dry_run=dry_run)
