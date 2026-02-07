"""Adzuna job collector."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json

logger = logging.getLogger(__name__)


class AdzunaCollector(BaseCollector):
    """Collector for Adzuna Jobs API."""

    name = "adzuna"
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
        country: str = "us",
        results_per_page: int = 50,
    ):
        """
        Initialize Adzuna collector.

        Args:
            app_id: Adzuna API app ID
            app_key: Adzuna API key
            country: Country code (us, gb, ca, etc.)
            results_per_page: Number of results per query
        """
        self.app_id = app_id
        self.app_key = app_key
        self.country = country
        self.results_per_page = results_per_page

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Adzuna API."""
        if not self.app_id or not self.app_key:
            logger.info("Adzuna credentials not configured, skipping")
            return []

        all_jobs: list[JobData] = []

        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                try:
                    jobs = await self._search(session, query)
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.error("Adzuna error for query '%s': %s", query, e)

        return all_jobs

    async def _search(self, session: aiohttp.ClientSession, query: str) -> list[JobData]:
        """Search Adzuna for jobs."""
        url = f"{self.BASE_URL}/{self.country}/search/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": query,
            "what_or": "remote",
            "results_per_page": self.results_per_page,
            "content-type": "application/json",
        }

        data = await http_get_json(session, url, params=params)
        if data is None:
            return []

        jobs = []

        for result in data.get("results", []):
            job = self._parse_job(result)
            if job:
                jobs.append(job)

        return jobs

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse Adzuna job data to JobData."""
        try:
            # Parse salary
            salary_min = data.get("salary_min")
            salary_max = data.get("salary_max")
            if salary_min:
                salary_min = int(salary_min)
            if salary_max:
                salary_max = int(salary_max)

            # Parse date
            posted_date = None
            if data.get("created"):
                try:
                    posted_date = datetime.fromisoformat(
                        data["created"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Determine location
            location_data = data.get("location", {})
            location_parts = []
            for area in location_data.get("area", []):
                if area:
                    location_parts.append(area)
            location = ", ".join(location_parts) if location_parts else None

            # Check if remote
            title_lower = data.get("title", "").lower()
            desc_lower = data.get("description", "").lower()
            is_remote = any(
                term in title_lower or term in desc_lower
                for term in ["remote", "work from home", "wfh"]
            )

            return JobData(
                title=data.get("title", ""),
                company=data.get("company", {}).get("display_name", ""),
                url=data.get("redirect_url", ""),
                source="adzuna",
                location=location,
                description=data.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=data.get("redirect_url"),
                remote=is_remote,
                posted_date=posted_date,
                extra_data={"category": data.get("category", {}).get("label")},
            )
        except Exception as e:
            logger.error("Error parsing Adzuna job: %s", e)
            return None
