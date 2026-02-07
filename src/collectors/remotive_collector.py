"""Remotive.com remote jobs collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json, parse_date_iso, parse_salary

logger = logging.getLogger(__name__)


class RemotiveCollector(BaseCollector):
    """Collector for Remotive.com remote jobs API.

    API docs: https://remotive.com/api/remote-jobs
    No authentication required. Jobs are delayed by 24 hours.
    """

    name = "remotive"
    API_URL = "https://remotive.com/api/remote-jobs"

    # Remotive category slugs for targeted searches
    CATEGORIES = [
        "software-dev",
        "data",
        "product",
        "design",
        "devops",
        "qa",
    ]

    def __init__(
        self,
        timeout: int = 30,
        limit: int = 100,
        delay_between_requests: tuple[float, float] = (1.0, 3.0),
    ):
        """
        Initialize Remotive collector.

        Args:
            timeout: Request timeout in seconds
            limit: Maximum number of jobs to fetch per request
            delay_between_requests: Min/max seconds delay between requests
        """
        self.timeout = timeout
        self.limit = limit
        self.delay_range = delay_between_requests

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Remotive API.

        Makes one request per search query using the API's search param,
        then filters results against all query terms.
        """
        all_jobs: list[JobData] = []
        seen_ids: set[int] = set()
        query_terms = [q.lower() for q in search_queries]

        async with aiohttp.ClientSession() as session:
            for i, query in enumerate(search_queries):
                try:
                    jobs = await self._fetch_jobs(session, search=query)

                    for job in jobs:
                        # Deduplicate within this collection run
                        job_id = job.extra_data.get("remotive_id")
                        if job_id and job_id in seen_ids:
                            continue
                        if job_id:
                            seen_ids.add(job_id)

                        if self._matches_queries(job, query_terms):
                            all_jobs.append(job)

                except Exception as e:
                    logger.error("Remotive error for query '%s': %s", query, e)

                # Rate limiting between requests
                if i < len(search_queries) - 1:
                    delay = random.uniform(*self.delay_range)
                    await asyncio.sleep(delay)

        logger.info("Remotive collected %d jobs from %d queries", len(all_jobs), len(search_queries))
        return all_jobs

    async def _fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        search: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[JobData]:
        """Fetch jobs from the Remotive API.

        Args:
            session: aiohttp client session
            search: Search term to filter jobs
            category: Remotive category slug (e.g., "software-dev")

        Returns:
            List of parsed JobData objects
        """
        params: dict[str, str | int] = {"limit": self.limit}
        if search:
            params["search"] = search
        if category:
            params["category"] = category

        data = await http_get_json(
            session,
            self.API_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers={"User-Agent": "JobRadar/1.0"},
        )

        if data is None:
            return []

        # API returns {"0-legal-notice": "...", "job-count": N, "jobs": [...]}
        jobs_list = data.get("jobs", [])
        if not isinstance(jobs_list, list):
            logger.warning("Remotive API returned unexpected format: %s", type(jobs_list))
            return []

        parsed: list[JobData] = []
        for job_data in jobs_list:
            job = self._parse_job(job_data)
            if job:
                parsed.append(job)

        return parsed

    def _matches_queries(self, job: JobData, query_terms: list[str]) -> bool:
        """Check if job matches any of the search queries."""
        searchable = " ".join(
            [
                job.title,
                job.company,
                job.description or "",
                job.location or "",
                " ".join(job.extra_data.get("tags", [])),
            ]
        ).lower()

        return any(term in searchable for term in query_terms)

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse Remotive job data to JobData."""
        try:
            title = data.get("title", "")
            company = data.get("company_name", "")

            if not title or not company:
                return None

            # Parse salary from salary string (e.g., "$120,000 - $150,000")
            salary_min = None
            salary_max = None
            salary_str = data.get("salary", "")
            if salary_str:
                salary_min, salary_max = self._parse_salary_range(salary_str)

            # Parse posted date
            posted_date = parse_date_iso(data.get("publication_date"))

            # Build location — Remotive provides candidate_required_location
            location = data.get("candidate_required_location", "")
            if not location:
                location = "Remote"

            # Build job URL
            url = data.get("url", "")

            # Get description (HTML) — strip tags for clean text
            description = data.get("description", "")
            if description and "<" in description:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(description, "html.parser")
                    description = soup.get_text(separator=" ", strip=True)
                except Exception:
                    pass  # Keep raw HTML if parsing fails

            # Tags from category and job_type
            tags = []
            if data.get("category"):
                tags.append(data["category"])
            if data.get("job_type"):
                tags.append(data["job_type"])

            return JobData(
                title=title,
                company=company,
                url=url,
                source="remotive",
                location=location,
                description=description,
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=url,
                remote=True,  # Remotive is exclusively remote jobs
                posted_date=posted_date,
                extra_data={
                    "remotive_id": data.get("id"),
                    "tags": tags,
                    "job_type": data.get("job_type"),
                    "category": data.get("category"),
                    "company_logo": data.get("company_logo"),
                },
            )
        except Exception as e:
            logger.error("Error parsing Remotive job: %s", e)
            return None

    def _parse_salary_range(
        self, salary_str: str
    ) -> tuple[Optional[int], Optional[int]]:
        """Parse salary range string into min/max integers.

        Handles formats like:
        - "$120,000 - $150,000"
        - "120k-150k"
        - "$80,000"

        Returns:
            Tuple of (salary_min, salary_max), either can be None
        """
        if not salary_str or not salary_str.strip():
            return None, None

        # Split on common range separators
        parts = salary_str.replace("\u2013", "-").replace("\u2014", "-").split("-")

        salary_min = parse_salary(parts[0].strip()) if len(parts) >= 1 else None
        salary_max = parse_salary(parts[-1].strip()) if len(parts) >= 2 else None

        return salary_min, salary_max
