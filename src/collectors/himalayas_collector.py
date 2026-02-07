"""Himalayas.app remote job collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json, parse_date_epoch

logger = logging.getLogger(__name__)


class HimalayasCollector(BaseCollector):
    """Collector for Himalayas.app remote jobs API."""

    name = "himalayas"
    API_URL = "https://himalayas.app/jobs/api"
    # Fetch a reasonable batch; the API returns 118k+ jobs total
    DEFAULT_LIMIT = 100

    def __init__(self, timeout: int = 30, limit: int = DEFAULT_LIMIT):
        """
        Initialize Himalayas collector.

        Args:
            timeout: Request timeout in seconds
            limit: Number of jobs to fetch per request
        """
        self.timeout = timeout
        self.limit = limit

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Himalayas.app API."""
        all_jobs: list[JobData] = []
        query_terms = [q.lower() for q in search_queries]

        try:
            async with aiohttp.ClientSession() as session:
                # Fetch recent jobs in pages to improve query coverage
                offset = 0
                max_pages = 5

                for page in range(max_pages):
                    url = f"{self.API_URL}?limit={self.limit}&offset={offset}"

                    data = await http_get_json(
                        session,
                        url,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                        headers={"User-Agent": "JobRadar/1.0"},
                    )
                    if data is None:
                        break

                    jobs = data.get("jobs", [])
                    if not jobs:
                        break

                    for job_data in jobs:
                        if self._matches_queries(job_data, query_terms):
                            job = self._parse_job(job_data)
                            if job:
                                all_jobs.append(job)

                    # If we got fewer jobs than requested, no more pages
                    if len(jobs) < self.limit:
                        break

                    offset += self.limit

                    # Rate limiting between pages
                    if page < max_pages - 1:
                        delay = random.uniform(1.0, 3.0)
                        await asyncio.sleep(delay)

        except Exception as e:
            logger.error("Himalayas error: %s", e)

        logger.info("Himalayas: found %d matching jobs", len(all_jobs))
        return all_jobs

    def _matches_queries(self, job_data: dict, query_terms: list[str]) -> bool:
        """Check if job matches any of the search queries."""
        searchable = " ".join(
            [
                str(job_data.get("title", "")),
                str(job_data.get("companyName", "")),
                str(job_data.get("excerpt", "")),
                str(job_data.get("description", "")),
                " ".join(str(c) for c in job_data.get("categories", [])),
                " ".join(str(c) for c in job_data.get("parentCategories", [])),
            ]
        ).lower()

        return any(term in searchable for term in query_terms)

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse Himalayas job data to JobData."""
        try:
            # Parse salary
            salary_min = None
            salary_max = None
            if data.get("minSalary") is not None:
                try:
                    salary_min = int(data["minSalary"])
                except (ValueError, TypeError):
                    pass
            if data.get("maxSalary") is not None:
                try:
                    salary_max = int(data["maxSalary"])
                except (ValueError, TypeError):
                    pass

            # Parse date (Unix epoch)
            posted_date = parse_date_epoch(data.get("pubDate"))

            # Build location from location restrictions
            location_restrictions = data.get("locationRestrictions", [])
            if location_restrictions:
                location = "Remote - " + ", ".join(location_restrictions)
            else:
                location = "Remote - Worldwide"

            # Job URL — use applicationLink or guid
            url = (
                data.get("applicationLink")
                or data.get("guid")
                or ""
            )

            # Build extra_data
            extra_data = {}
            if data.get("categories"):
                extra_data["categories"] = data["categories"]
            if data.get("parentCategories"):
                extra_data["parentCategories"] = data["parentCategories"]
            if data.get("seniority"):
                extra_data["seniority"] = data["seniority"]
            if data.get("employmentType"):
                extra_data["employmentType"] = data["employmentType"]
            if data.get("currency"):
                extra_data["currency"] = data["currency"]

            return JobData(
                title=data.get("title", ""),
                company=data.get("companyName", ""),
                url=url,
                source="himalayas",
                location=location,
                description=data.get("description") or data.get("excerpt", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=data.get("applicationLink"),
                remote=True,  # Himalayas is all remote jobs
                posted_date=posted_date,
                extra_data=extra_data,
            )
        except Exception as e:
            logger.error("Error parsing Himalayas job: %s", e)
            return None
