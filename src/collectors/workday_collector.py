"""Workday career site collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseCollector, JobData
from .utils import http_post_json

logger = logging.getLogger(__name__)


class WorkdayCollector(BaseCollector):
    """Collector for Workday career sites."""

    name = "workday"

    # Large enterprises using Workday's standardized career site API
    DEFAULT_COMPANIES = [
        {"name": "Amazon", "slug": "amazon"},
        {"name": "Salesforce", "slug": "salesforce"},
        {"name": "Microsoft", "slug": "microsoft"},
        {"name": "Visa", "slug": "visa"},
        {"name": "Adobe", "slug": "adobe"},
        {"name": "PayPal", "slug": "paypal"},
        {"name": "VMware", "slug": "vmware"},
        {"name": "Deloitte", "slug": "deloitte"},
        {"name": "PwC", "slug": "pwc"},
        {"name": "Accenture", "slug": "accenture"},
    ]

    def __init__(
        self,
        companies: Optional[list[dict]] = None,
        timeout: int = 30,
        max_concurrent: int = 3,
        delay_between_requests: tuple[float, float] = (1.0, 2.5),
    ):
        """
        Initialize Workday collector.

        Args:
            companies: List of dicts with "name" and "slug" keys
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests (rate limiting)
            delay_between_requests: Min/max seconds delay between requests
        """
        self.companies = companies or self.DEFAULT_COMPANIES
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.delay_range = delay_between_requests

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Workday career sites."""
        all_jobs: list[JobData] = []

        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_with_rate_limit(
            company: dict, query: str
        ) -> list[JobData]:
            async with semaphore:
                delay = random.uniform(*self.delay_range)
                await asyncio.sleep(delay)
                return await self._fetch_company_jobs(
                    session, company, query
                )

        async with aiohttp.ClientSession() as session:
            tasks = [
                fetch_with_rate_limit(company, query)
                for company in self.companies
                for query in search_queries
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            seen_urls: set[str] = set()
            for company_jobs in results:
                if isinstance(company_jobs, Exception):
                    continue
                for job in company_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

        return all_jobs

    async def _fetch_company_jobs(
        self,
        session: aiohttp.ClientSession,
        company: dict,
        query: str,
    ) -> list[JobData]:
        """Fetch jobs from a specific company's Workday career site."""
        slug = company["slug"]
        company_name = company["name"]
        url = (
            f"https://{slug}.wd5.myworkdayjobs.com"
            f"/wday/cxs/{slug}/External/jobs"
        )
        payload = {
            "limit": 20,
            "offset": 0,
            "searchText": query,
        }

        try:
            data = await http_post_json(
                session,
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            if data is None:
                return []

            jobs = []

            for posting in data.get("jobPostings", []):
                job = self._parse_job(posting, slug, company_name)
                if job:
                    jobs.append(job)

            return jobs

        except Exception as e:
            logger.error("Workday error for %s: %s", company_name, e)
            return []

    def _parse_job(
        self, data: dict, slug: str, company_name: str
    ) -> Optional[JobData]:
        """Parse Workday job posting to JobData."""
        try:
            title = data.get("title", "")
            if not title:
                return None

            # Build the job URL from the external path
            external_path = data.get("externalPath", "")
            job_url = (
                f"https://{slug}.wd5.myworkdayjobs.com"
                f"/External{external_path}"
            )

            # Location from locationsText
            location = data.get("locationsText", "")

            # Determine if remote
            is_remote = False
            if location:
                is_remote = any(
                    term in location.lower()
                    for term in ["remote", "anywhere", "worldwide"]
                )

            # Parse bullet fields for salary or other metadata
            bullet_fields = data.get("bulletFields", [])
            description_parts = []
            posted_date = None

            for bullet in bullet_fields:
                if isinstance(bullet, str):
                    description_parts.append(bullet)
                    # Try to parse date from bullet fields
                    if not posted_date:
                        try:
                            posted_date = datetime.fromisoformat(
                                bullet.replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

            # Build a short description from bullet fields
            description = " | ".join(description_parts) if description_parts else None

            return JobData(
                title=title,
                company=company_name,
                url=job_url,
                source="workday",
                location=location or None,
                description=description,
                salary_min=None,
                salary_max=None,
                apply_url=job_url,
                remote=is_remote,
                posted_date=posted_date,
                extra_data={
                    "external_path": external_path,
                    "bullet_fields": bullet_fields,
                },
            )
        except Exception as e:
            logger.error("Error parsing Workday job for %s: %s", company_name, e)
            return None
