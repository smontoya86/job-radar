"""Bootstrap module for scripts - handles path setup and common imports.

This module handles the path configuration that was previously duplicated
across all script files.

Usage:
    from scripts.bootstrap import settings, get_session, init_db
"""
import sys
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Now we can import from project modules
from config.settings import settings
from src.persistence.database import get_session, init_db

# Re-export for convenience
__all__ = ["settings", "get_session", "init_db"]
