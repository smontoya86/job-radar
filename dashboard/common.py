"""Common setup for dashboard pages.

This module handles path configuration and database initialization
that was previously duplicated across all dashboard pages.

Usage:
    from dashboard.common import get_session, sanitize_html
    # init_db() is called automatically on import
"""
import html
import sys
from pathlib import Path

# Add project root to path (for imports from src/)
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Now we can import from project modules
from config.settings import settings
from src.logging_config import setup_logging
from src.persistence.database import get_session, init_db

# Initialize logging and database once on module import
setup_logging(log_file="logs/jobradar.log")
init_db()


def sanitize_html(text: str) -> str:
    """Escape user-supplied text for safe use in st.markdown(unsafe_allow_html=True).

    Converts characters like <, >, &, " to their HTML entity equivalents
    so that user data (company names, positions, notes) cannot inject
    scripts or break HTML structure.
    """
    if not text:
        return ""
    return html.escape(str(text))


# Re-export for convenience
__all__ = ["get_session", "init_db", "sanitize_html", "settings"]
