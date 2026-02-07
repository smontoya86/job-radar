"""Database connection and session management."""
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings
from src.persistence.models import Base

logger = logging.getLogger(__name__)


def _build_engine():
    """Create SQLAlchemy engine with appropriate settings for the database backend."""
    url = settings.database_url

    if url.startswith("sqlite"):
        return create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
        )

    # PostgreSQL (or other server-based databases)
    return create_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before use
    )


# Create engine and session factory
engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _migrate_add_user_id_columns() -> None:
    """Add user_id columns to tables that were created before multi-tenant support."""
    tables_needing_user_id = ["jobs", "applications", "email_imports", "resumes", "status_history"]
    inspector = inspect(engine)

    with engine.begin() as conn:
        for table in tables_needing_user_id:
            if table not in inspector.get_table_names():
                continue
            columns = [col["name"] for col in inspector.get_columns(table)]
            if "user_id" not in columns:
                conn.execute(text(
                    f'ALTER TABLE {table} ADD COLUMN user_id VARCHAR REFERENCES users(id)'
                ))
                logger.info("Added user_id column to %s", table)


def _migrate_add_company_key_columns() -> None:
    """Add company_key columns to jobs and applications tables."""
    tables = ["jobs", "applications"]
    inspector = inspect(engine)

    with engine.begin() as conn:
        for table in tables:
            if table not in inspector.get_table_names():
                continue
            columns = [col["name"] for col in inspector.get_columns(table)]
            if "company_key" not in columns:
                conn.execute(text(
                    f'ALTER TABLE {table} ADD COLUMN company_key VARCHAR'
                ))
                logger.info("Added company_key column to %s", table)

                # Backfill existing rows
                conn.execute(text(
                    f"UPDATE {table} SET company_key = LOWER(TRIM(company)) WHERE company_key IS NULL"
                ))
                logger.info("Backfilled company_key for %s", table)

        # Create indexes (syntax works for both SQLite and PostgreSQL)
        for table in tables:
            if table not in inspector.get_table_names():
                continue
            existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
            idx_name = f"ix_{table}_company_key"
            if idx_name not in existing_indexes:
                conn.execute(text(
                    f'CREATE INDEX {idx_name} ON {table} (company_key)'
                ))
                logger.info("Created index %s", idx_name)


def init_db() -> None:
    """Initialize the database, creating all tables."""
    Base.metadata.create_all(bind=engine)
    _migrate_add_user_id_columns()
    _migrate_add_company_key_columns()


def drop_db() -> None:
    """Drop all tables (use with caution)."""
    Base.metadata.drop_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_direct() -> Session:
    """Get a database session directly (caller responsible for cleanup)."""
    return SessionLocal()
