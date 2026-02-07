"""Ashby job board collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json

logger = logging.getLogger(__name__)


class AshbyCollector(BaseCollector):
    """Collector for Ashby job boards."""

    name = "ashby"

    # Companies using Ashby as their ATS
    DEFAULT_COMPANIES = [
        "ramp",
        "linear",
        "vercel",
        "notion",
        "anthropic",
        "figma",
        "plaid",
        "brex",
        "loom",
        "retool",
        "postman",
        "deel",
        "lattice",
        "gusto",
        "rippling",
        "vanta",
        "drata",
        "mercury",
        "navan",
        "anduril",
    ]

    def __init__(
        self,
        companies: Optional[list[str]] = None,
        timeout: int = 30,
        max_concurrent: int = 5,
        delay_between_requests: tuple[float, float] = (0.5, 1.5),
    ):
        """
        Initialize Ashby collector.

        Args:
            companies: List of company board slugs (e.g., "ramp", "linear")
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests (rate limiting)
            delay_between_requests: Min/max seconds delay between requests
        """
        self.companies = companies or self.DEFAULT_COMPANIES
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.delay_range = delay_between_requests

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Ashby boards."""
        all_jobs: list[JobData] = []
        query_terms = [q.lower() for q in search_queries]

        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_with_rate_limit(company: str) -> list[JobData]:
            async with semaphore:
                # Add random delay before each request
                delay = random.uniform(*self.delay_range)
                await asyncio.sleep(delay)
                return await self._fetch_company_jobs(session, company)

        async with aiohttp.ClientSession() as session:
            tasks = [fetch_with_rate_limit(company) for company in self.companies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for company_jobs in results:
                if isinstance(company_jobs, Exception):
                    continue
                for job in company_jobs:
                    if self._matches_queries(job, query_terms):
                        all_jobs.append(job)

        return all_jobs

    async def _fetch_company_jobs(
        self,
        session: aiohttp.ClientSession,
        company: str,
    ) -> list[JobData]:
        """Fetch jobs from a specific company's Ashby board."""
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"

        try:
            data = await http_get_json(
                session,
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
            if data is None:
                return []

            jobs = []

            for job_data in data.get("jobs", []):
                job = self._parse_job(job_data, company)
                if job:
                    jobs.append(job)

            # Fetch descriptions for PM-related jobs (to avoid too many API calls)
            pm_jobs = [j for j in jobs if self._is_pm_related(j.title)]
            if pm_jobs:
                await self._fetch_descriptions(session, company, pm_jobs)

            return jobs

        except Exception as e:
            logger.error("Ashby error for %s: %s", company, e)
            return []

    def _is_pm_related(self, title: str) -> bool:
        """Check if job title is PM-related (to limit description fetches)."""
        title_lower = title.lower()
        pm_terms = ["product manager", "product lead", "product director", "pm", "product"]
        return any(term in title_lower for term in pm_terms)

    async def _fetch_descriptions(
        self,
        session: aiohttp.ClientSession,
        company: str,
        jobs: list[JobData],
    ) -> None:
        """Fetch full descriptions for jobs (modifies jobs in place)."""
        from bs4 import BeautifulSoup

        for job in jobs:
            try:
                job_id = job.extra_data.get("job_id")
                if not job_id:
                    continue

                url = (
                    f"https://api.ashbyhq.com/posting-api/job-board/{company}"
                    f"/job/{job_id}"
                )

                # Rate limit description fetches
                delay = random.uniform(*self.delay_range)
                await asyncio.sleep(delay)

                data = await http_get_json(
                    session, url, timeout=aiohttp.ClientTimeout(total=10)
                )
                if data is None:
                    continue

                # Prefer plain text, fall back to HTML parsing
                description = data.get("descriptionPlain")
                if not description:
                    html_content = data.get("descriptionHtml", "")
                    if html_content:
                        soup = BeautifulSoup(html_content, "html.parser")
                        description = soup.get_text(separator=" ", strip=True)

                if description:
                    job.description = description

            except Exception:
                # Silently continue on error - description fetching is best-effort
                pass

    def _matches_queries(self, job: JobData, query_terms: list[str]) -> bool:
        """Check if job title matches any search query term (case-insensitive)."""
        title_lower = job.title.lower()
        return any(term in title_lower for term in query_terms)

    def _parse_job(self, data: dict, company_slug: str) -> Optional[JobData]:
        """Parse Ashby job data to JobData."""
        try:
            title = data.get("title", "")
            job_id = data.get("id", "")

            # Get location
            location = data.get("location")

            # Determine if remote
            is_remote = False
            if location:
                is_remote = any(
                    term in location.lower()
                    for term in ["remote", "anywhere", "worldwide"]
                )

            # Parse date
            posted_date = None
            published = data.get("publishedDate")
            if published:
                try:
                    posted_date = datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Get company name (capitalize slug)
            company_name = company_slug.replace("-", " ").title()

            # Build the public job URL
            job_url = f"https://jobs.ashbyhq.com/{company_slug}/{job_id}"

            # Get department
            department = data.get("departmentName")

            return JobData(
                title=title,
                company=company_name,
                url=job_url,
                source="ashby",
                location=location,
                description=None,  # Fetched separately via _fetch_descriptions
                salary_min=None,
                salary_max=None,
                apply_url=job_url,
                remote=is_remote,
                posted_date=posted_date,
                extra_data={
                    "job_id": str(job_id),
                    "department": department,
                },
            )
        except Exception as e:
            logger.error("Error parsing Ashby job: %s", e)
            return None
