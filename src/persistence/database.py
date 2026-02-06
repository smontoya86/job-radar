"""Database connection and session management."""
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

# Create engine
engine = create_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL logging
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# Create session factory
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


def init_db() -> None:
    """Initialize the database, creating all tables."""
    Base.metadata.create_all(bind=engine)
    _migrate_add_user_id_columns()


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
