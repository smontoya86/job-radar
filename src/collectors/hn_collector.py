"""Hacker News Who's Hiring collector."""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json

logger = logging.getLogger(__name__)


class HNCollector(BaseCollector):
    """Collector for Hacker News 'Who is Hiring?' threads."""

    name = "hn_whoishiring"
    HN_API_BASE = "https://hacker-news.firebaseio.com/v0"

    # Who is hiring user ID
    WHOISHIRING_USER = "whoishiring"

    def __init__(self, timeout: int = 60, max_comments: int = 500):
        """
        Initialize HN collector.

        Args:
            timeout: Request timeout in seconds
            max_comments: Maximum comments to process per thread
        """
        self.timeout = timeout
        self.max_comments = max_comments

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from HN Who's Hiring thread."""
        query_terms = [q.lower() for q in search_queries]

        try:
            # Get the latest Who's Hiring thread
            thread_id = await self._find_latest_thread()
            if not thread_id:
                logger.info("No HN Who's Hiring thread found")
                return []

            # Fetch and parse comments
            jobs = await self._parse_thread(thread_id, query_terms)
            return jobs

        except Exception as e:
            logger.error("HN collector error: %s", e)
            return []

    async def _find_latest_thread(self) -> Optional[int]:
        """Find the latest Who's Hiring thread ID."""
        async with aiohttp.ClientSession() as session:
            # Get user submissions
            url = f"{self.HN_API_BASE}/user/{self.WHOISHIRING_USER}.json"

            data = await http_get_json(
                session,
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
            if data is None:
                return None

            submitted = data.get("submitted", [])

            if not submitted:
                return None

            # Check recent submissions for "Who is hiring"
            for item_id in submitted[:10]:  # Check last 10 posts
                item_url = f"{self.HN_API_BASE}/item/{item_id}.json"
                item_data = await http_get_json(session, item_url)
                if item_data is None:
                    continue
                title = item_data.get("title", "").lower()
                if "who is hiring" in title:
                    return item_id

            return None

    async def _parse_thread(
        self,
        thread_id: int,
        query_terms: list[str],
    ) -> list[JobData]:
        """Parse a Who's Hiring thread for job postings."""
        jobs: list[JobData] = []

        async with aiohttp.ClientSession() as session:
            # Get thread details
            url = f"{self.HN_API_BASE}/item/{thread_id}.json"

            thread_data = await http_get_json(
                session,
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
            if thread_data is None:
                return []

            comment_ids = thread_data.get("kids", [])

            # Limit number of comments to process
            comment_ids = comment_ids[: self.max_comments]

            # Fetch comments concurrently in batches
            batch_size = 50
            for i in range(0, len(comment_ids), batch_size):
                batch = comment_ids[i : i + batch_size]
                tasks = [
                    self._fetch_comment(session, cid)
                    for cid in batch
                ]
                comments = await asyncio.gather(*tasks, return_exceptions=True)

                for comment in comments:
                    if isinstance(comment, Exception) or not comment:
                        continue

                    # Check if matches query
                    job = self._parse_comment(comment, query_terms, thread_id)
                    if job:
                        jobs.append(job)

        return jobs

    async def _fetch_comment(
        self,
        session: aiohttp.ClientSession,
        comment_id: int,
    ) -> Optional[dict]:
        """Fetch a single comment."""
        url = f"{self.HN_API_BASE}/item/{comment_id}.json"
        return await http_get_json(
            session, url, timeout=aiohttp.ClientTimeout(total=10)
        )

    def _parse_comment(
        self,
        comment: dict,
        query_terms: list[str],
        thread_id: int,
    ) -> Optional[JobData]:
        """Parse a HN comment into a job posting."""
        if comment.get("deleted") or comment.get("dead"):
            return None

        text = comment.get("text", "")
        if not text:
            return None

        text_lower = text.lower()

        # Check if matches search queries OR contains PM-related keywords
        # Be more inclusive - let the scorer filter out irrelevant jobs
        pm_keywords = [
            "product manager", "product lead", "product director", "pm ",
            " pm,", "ai ", "ml ", "machine learning", "search", "personalization",
            "recommendation", "llm", "genai", "generative ai"
        ]
        query_match = any(term in text_lower for term in query_terms)
        pm_match = any(kw in text_lower for kw in pm_keywords)

        if not query_match and not pm_match:
            return None

        # Parse the comment
        # HN posts typically start with: Company | Location | Role | Details
        # Extract company name (usually first line/first part)
        lines = text.split("<p>")
        first_line = re.sub(r"<[^>]+>", "", lines[0]).strip() if lines else ""

        # Try to extract company from first line
        parts = re.split(r"\s*[|]\s*", first_line)
        company = parts[0].strip() if parts else "Unknown Company"

        # Try to find job title
        title = "Software Engineer"  # Default
        title_patterns = [
            r"(senior|lead|staff|principal)?\s*(product manager|pm|engineer|developer)",
            r"hiring\s+(?:a\s+)?([\w\s]+)",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, text_lower)
            if match:
                title = match.group(0).strip().title()
                break

        # Check for remote
        is_remote = any(
            term in text_lower
            for term in ["remote", "remote ok", "remote friendly", "anywhere"]
        )

        # Try to extract location
        location = None
        location_match = re.search(
            r"(?:location|based in|office in)[:\s]+([^|<\n]+)",
            text_lower,
        )
        if location_match:
            location = location_match.group(1).strip().title()
        elif is_remote:
            location = "Remote"

        # Parse date from comment timestamp
        posted_date = None
        if comment.get("time"):
            try:
                posted_date = datetime.fromtimestamp(comment["time"])
            except (ValueError, TypeError):
                pass

        # Clean description
        description = re.sub(r"<[^>]+>", "\n", text).strip()

        return JobData(
            title=title[:200],  # Truncate if too long
            company=company[:100],
            url=f"https://news.ycombinator.com/item?id={comment.get('id')}",
            source="hn_whoishiring",
            location=location,
            description=description[:5000],  # Truncate very long descriptions
            salary_min=None,
            salary_max=None,
            apply_url=f"https://news.ycombinator.com/item?id={comment.get('id')}",
            remote=is_remote,
            posted_date=posted_date,
            extra_data={"thread_id": thread_id, "comment_id": comment.get("id")},
        )
