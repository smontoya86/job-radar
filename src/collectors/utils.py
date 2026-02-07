"""Shared utilities for job collectors."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


async def http_get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    retries: int = 3,
    **kwargs,
) -> dict | list | None:
    """GET request returning parsed JSON with retry on transient failures.

    Retries on 429 (rate limit), 5xx (server error), timeouts, and
    connection errors with exponential backoff + jitter.

    Returns None on non-retryable errors (400, 403, 404, etc.).
    """
    last_error = None
    for attempt in range(retries):
        try:
            async with session.get(url, **kwargs) as resp:
                if resp.status == 429 or resp.status >= 500:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
                        resp.status, url, wait, attempt + 1, retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    logger.debug("HTTP %d from %s", resp.status, url)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = e
            if attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Request to %s failed: %s, retrying in %.1fs (attempt %d/%d)",
                    url, e, wait, attempt + 1, retries,
                )
                await asyncio.sleep(wait)

    if last_error:
        logger.error("All %d retries failed for %s: %s", retries, url, last_error)
    return None


async def http_post_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    retries: int = 3,
    **kwargs,
) -> dict | list | None:
    """POST request returning parsed JSON with retry on transient failures.

    Same retry logic as http_get_json but for POST requests.
    """
    last_error = None
    for attempt in range(retries):
        try:
            async with session.post(url, **kwargs) as resp:
                if resp.status == 429 or resp.status >= 500:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
                        resp.status, url, wait, attempt + 1, retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    logger.debug("HTTP %d from %s", resp.status, url)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = e
            if attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Request to %s failed: %s, retrying in %.1fs (attempt %d/%d)",
                    url, e, wait, attempt + 1, retries,
                )
                await asyncio.sleep(wait)

    if last_error:
        logger.error("All %d retries failed for %s: %s", retries, url, last_error)
    return None


async def http_get_text(
    session: aiohttp.ClientSession,
    url: str,
    *,
    retries: int = 3,
    **kwargs,
) -> str | None:
    """GET request returning text with retry on transient failures."""
    last_error = None
    for attempt in range(retries):
        try:
            async with session.get(url, **kwargs) as resp:
                if resp.status == 429 or resp.status >= 500:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
                        resp.status, url, wait, attempt + 1, retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    return None
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = e
            if attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Request to %s failed: %s, retrying in %.1fs (attempt %d/%d)",
                    url, e, wait, attempt + 1, retries,
                )
                await asyncio.sleep(wait)

    if last_error:
        logger.error("All %d retries failed for %s: %s", retries, url, last_error)
    return None


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
