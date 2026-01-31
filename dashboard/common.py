"""Common setup for dashboard pages.

This module handles path configuration and database initialization
that was previously duplicated across all dashboard pages.

Usage:
    from dashboard.common import get_session
    # init_db() is called automatically on import
"""
import sys
from pathlib import Path

# Add project root to path (for imports from src/)
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Now we can import from project modules
from config.settings import settings
from src.persistence.database import get_session, init_db

# Initialize database once on module import
init_db()

# Re-export for convenience
__all__ = ["get_session", "init_db", "settings"]
