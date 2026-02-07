"""JSearch (RapidAPI) job collector."""
import asyncio
import logging
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json, parse_date_iso, parse_salary

logger = logging.getLogger(__name__)


class JSearchCollector(BaseCollector):
    """Collector for JSearch API via RapidAPI."""

    name = "jsearch"
    BASE_URL = "https://jsearch.p.rapidapi.com/search"

    def __init__(
        self,
        api_key: Optional[str] = None,
        results_wanted: int = 20,
    ):
        """
        Initialize JSearch collector.

        Args:
            api_key: RapidAPI key for JSearch
            results_wanted: Number of results per query
        """
        self.api_key = api_key
        self.results_wanted = results_wanted

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from JSearch API."""
        if not self.api_key:
            logger.info("JSearch API key not configured, skipping")
            return []

        all_jobs: list[JobData] = []

        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                try:
                    jobs = await self._search(session, query)
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.error("JSearch error for query '%s': %s", query, e)

        return all_jobs

    async def _search(
        self, session: aiohttp.ClientSession, query: str
    ) -> list[JobData]:
        """Search JSearch API for jobs."""
        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        params = {
            "query": query,
            "num_pages": "1",
        }

        data = await http_get_json(
            session, self.BASE_URL, headers=headers, params=params
        )
        if data is None:
            return []

        jobs = []

        for item in data.get("data", []):
            job = self._parse_job(item)
            if job:
                jobs.append(job)

        return jobs

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse JSearch job data to JobData."""
        try:
            # Build location from city and state
            city = data.get("job_city")
            state = data.get("job_state")
            location_parts = [p for p in (city, state) if p]
            location = ", ".join(location_parts) if location_parts else None

            # Parse salary
            salary_min = parse_salary(data.get("job_min_salary"))
            salary_max = parse_salary(data.get("job_max_salary"))

            # Parse posted date
            posted_date = parse_date_iso(data.get("job_posted_at_datetime_utc"))

            # Detect remote
            is_remote = bool(data.get("job_is_remote"))

            return JobData(
                title=data.get("job_title", ""),
                company=data.get("employer_name", ""),
                url=data.get("job_apply_link", ""),
                source="jsearch",
                location=location,
                description=data.get("job_description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=data.get("job_apply_link"),
                remote=is_remote,
                posted_date=posted_date,
            )
        except Exception as e:
            logger.error("Error parsing JSearch job: %s", e)
            return None
