"""Shared utilities for job collectors."""
from datetime import datetime
from typing import Optional


def parse_salary(value) -> Optional[int]:
    """
    Parse salary value to integer, handling various formats.

    Args:
        value: Salary value (can be int, float, string, or None)

    Returns:
        Integer salary value or None if parsing fails
    """
    if value is None:
        return None
    try:
        # Handle string formats like "$150,000" or "150k"
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").lower()
            if cleaned.endswith("k"):
                return int(float(cleaned[:-1]) * 1000)
            return int(float(cleaned))
        return int(float(value))
    except (ValueError, TypeError):
        return None


def parse_date_iso(date_string: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO format date string to datetime.

    Handles common variations like trailing 'Z' or timezone offsets.

    Args:
        date_string: ISO format date string

    Returns:
        datetime object or None if parsing fails
    """
    if not date_string:
        return None
    try:
        # Handle 'Z' suffix (UTC indicator)
        if isinstance(date_string, str):
            return datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        if isinstance(date_string, datetime):
            return date_string
    except (ValueError, TypeError):
        pass
    return None


def parse_date_epoch(timestamp) -> Optional[datetime]:
    """
    Parse Unix epoch timestamp to datetime.

    Handles both seconds and milliseconds timestamps.

    Args:
        timestamp: Unix timestamp (seconds or milliseconds)

    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp:
        return None
    try:
        ts = int(timestamp)
        # If timestamp is in milliseconds (13 digits), convert to seconds
        if ts > 10000000000:
            ts = ts // 1000
        return datetime.fromtimestamp(ts)
    except (ValueError, TypeError, OSError):
        return None


def detect_remote(
    location: Optional[str] = None,
    title: str = "",
    description: str = "",
    commitment: str = "",
) -> bool:
    """
    Detect if a job is remote based on various fields.

    Args:
        location: Job location string
        title: Job title
        description: Job description
        commitment: Employment commitment type (e.g., "Full-time Remote")

    Returns:
        True if job appears to be remote
    """
    remote_terms = ["remote", "anywhere", "worldwide", "work from home", "wfh"]

    # Combine all searchable text
    searchable = " ".join([
        location or "",
        title,
        description,
        commitment,
    ]).lower()

    return any(term in searchable for term in remote_terms)


def matches_queries(
    job_fields: list[str],
    query_terms: list[str],
) -> bool:
    """
    Check if job fields match any of the search query terms.

    Args:
        job_fields: List of job field values to search (title, company, description, etc.)
        query_terms: List of search terms (should be lowercase)

    Returns:
        True if any query term is found in any field
    """
    searchable = " ".join(str(field) for field in job_fields if field).lower()
    return any(term in searchable for term in query_terms)
