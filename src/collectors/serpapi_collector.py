"""SerpApi Google Jobs collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json

logger = logging.getLogger(__name__)


class SerpApiCollector(BaseCollector):
    """Collector for SerpApi Google Jobs engine."""

    name = "serpapi"
    BASE_URL = "https://serpapi.com/search"

    def __init__(
        self,
        api_key: Optional[str] = None,
        results_wanted: int = 30,
    ):
        """
        Initialize SerpApi collector.

        Args:
            api_key: SerpApi API key
            results_wanted: Number of results per query
        """
        self.api_key = api_key
        self.results_wanted = results_wanted

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from SerpApi Google Jobs engine."""
        if not self.api_key:
            logger.info("SerpApi API key not configured, skipping")
            return []

        all_jobs: list[JobData] = []

        async with aiohttp.ClientSession() as session:
            for i, query in enumerate(search_queries):
                try:
                    jobs = await self._search(session, query)
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.error("SerpApi error for query '%s': %s", query, e)

                # Rate limit: 1-2s between queries (free tier: 100 req/day)
                if i < len(search_queries) - 1:
                    await asyncio.sleep(random.uniform(1.0, 2.0))

        return all_jobs

    async def _search(self, session: aiohttp.ClientSession, query: str) -> list[JobData]:
        """Search SerpApi Google Jobs for jobs."""
        params = {
            "engine": "google_jobs",
            "q": query,
            "api_key": self.api_key,
            "num": self.results_wanted,
        }

        data = await http_get_json(session, self.BASE_URL, params=params)
        if data is None:
            return []

        jobs = []

        for result in data.get("jobs_results", []):
            job = self._parse_job(result)
            if job:
                jobs.append(job)

        return jobs

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse SerpApi Google Jobs result to JobData."""
        try:
            # Extract extensions for salary and remote info
            extensions = data.get("detected_extensions", {})

            # Parse salary from detected_extensions
            salary_min = None
            salary_max = None
            if extensions.get("salary"):
                salary_min, salary_max = self._parse_salary(extensions["salary"])

            # Determine remote status
            title_lower = data.get("title", "").lower()
            desc_lower = data.get("description", "").lower()
            location_lower = data.get("location", "").lower()
            is_remote = (
                extensions.get("work_from_home", False)
                or any(
                    term in title_lower or term in desc_lower or term in location_lower
                    for term in ["remote", "work from home", "wfh"]
                )
            )

            # Build job URL from share_link or related_links
            url = ""
            if data.get("share_link"):
                url = data["share_link"]
            elif data.get("related_links"):
                links = data["related_links"]
                if isinstance(links, list) and len(links) > 0:
                    url = links[0].get("link", "")

            # Build apply URL from apply_options if available
            apply_url = None
            apply_options = data.get("apply_options", [])
            if apply_options and isinstance(apply_options, list):
                apply_url = apply_options[0].get("link")

            return JobData(
                title=data.get("title", ""),
                company=data.get("company_name", ""),
                url=url,
                source="serpapi",
                location=data.get("location"),
                description=data.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=apply_url,
                remote=is_remote,
                posted_date=None,
                extra_data={
                    "job_id": data.get("job_id"),
                    "schedule_type": extensions.get("schedule_type"),
                    "qualifications": extensions.get("qualifications"),
                },
            )
        except Exception as e:
            logger.error("Error parsing SerpApi job: %s", e)
            return None

    def _parse_salary(self, salary_str: str) -> tuple[Optional[int], Optional[int]]:
        """
        Parse salary string from SerpApi detected_extensions.

        Examples: "$120K-$180K a year", "$50-$70 an hour", "$150,000"

        Returns:
            Tuple of (salary_min, salary_max) as annual integers, or (None, None).
        """
        try:
            import re

            # Determine if hourly
            is_hourly = "hour" in salary_str.lower()

            # Extract all dollar amounts
            amounts = re.findall(r"\$[\d,.]+K?", salary_str)
            if not amounts:
                return None, None

            parsed = []
            for amount in amounts:
                cleaned = amount.replace("$", "").replace(",", "")
                if cleaned.upper().endswith("K"):
                    value = float(cleaned[:-1]) * 1000
                else:
                    value = float(cleaned)

                # Convert hourly to annual (2080 work hours/year)
                if is_hourly:
                    value = value * 2080

                parsed.append(int(value))

            if len(parsed) >= 2:
                return parsed[0], parsed[1]
            elif len(parsed) == 1:
                return parsed[0], parsed[0]
            else:
                return None, None
        except (ValueError, IndexError):
            return None, None
