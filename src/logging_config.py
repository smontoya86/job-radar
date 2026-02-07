"""Logging configuration for Job Radar."""
import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """Configure application-wide logging.

    Call once at application startup (main.py, dashboard common.py, scripts).

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path for rotating file handler
    """
    root = logging.getLogger()

    # Avoid duplicate handlers on repeated calls (e.g. Streamlit reruns)
    if root.handlers:
        return

    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Rotating file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Quiet noisy libraries
    for name in ("urllib3", "aiohttp", "sqlalchemy", "streamlit", "apscheduler"):
        logging.getLogger(name).setLevel(logging.WARNING)
