"""Lever job board collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData
from .utils import http_get_json

logger = logging.getLogger(__name__)


class LeverCollector(BaseCollector):
    """Collector for Lever job boards."""

    name = "lever"

    # Popular tech companies using Lever
    DEFAULT_COMPANIES = [
        # AI Companies
        "character",  # Character.ai
        "inflection",
        "adept",
        "imbue",
        "aleph-alpha",
        "together",  # Together.ai
        "modal",
        "replicate",
        "anyscale",
        "fireworks-ai",
        "baseten",
        "banana-dev",
        "humanloop",
        "promptlayer",
        # Big Tech & Fintech
        "netflix",
        "spotify",
        "coinbase",
        "robinhood",
        "plaid",
        "chime",
        "affirm",
        "brex",
        "ramp",
        "anduril",
        "palantir",
        "ziprecruiter",
        "gusto",
        "rippling",
        "deel",
        "lattice",
        "miro",
        "gong",
        "highspot",
        "outreach",
        # Search/Discovery
        "algolia",
        "elastic",
        "clarifai",
        "textio",
        "lucidworks",
        "coveo",
        "bloomreach",
        "constructor-io",
        "searchspring",
        # Real Estate/Proptech
        "firstam",  # First American
        "blend",
        "better",
        "snapdocs",
        "qualia",
        # Travel/Hospitality
        "airbnb",
        "sonder",
        "getaround",
        "turo",
        # Ecommerce
        "bolt",
        "afterpay",
        "klarna",
        "attentive",
        "klaviyo",
        "yotpo",
        # Enterprise SaaS
        "amplitude",
        "mixpanel",
        "heap",
        "segment",
        "braze",
        "iterable",
        "customer-io",
        "intercom",
        "drift",
        "qualified",
        # Dev Tools
        "vercel",
        "netlify",
        "render",
        "railway",
        "supabase",
        "planetscale",
        "cockroach-labs",
        "timescale",
        # HR/Recruiting
        "greenhouse",
        "lever",
        "gem",
        "ashbyhq",
        "dover",
    ]

    def __init__(
        self,
        companies: Optional[list[str]] = None,
        timeout: int = 30,
        max_concurrent: int = 5,
        delay_between_requests: tuple[float, float] = (0.5, 1.5),
    ):
        """
        Initialize Lever collector.

        Args:
            companies: List of company slugs (e.g., "netflix", "spotify")
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests (rate limiting)
            delay_between_requests: Min/max seconds delay between requests
        """
        self.companies = companies or self.DEFAULT_COMPANIES
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.delay_range = delay_between_requests

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Lever boards."""
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
        """Fetch jobs from a specific company's Lever board."""
        url = f"https://api.lever.co/v0/postings/{company}"

        try:
            data = await http_get_json(
                session,
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
            if data is None:
                return []

            jobs = []

            for job_data in data:
                job = self._parse_job(job_data, company)
                if job:
                    jobs.append(job)

            return jobs

        except Exception as e:
            logger.error("Lever error for %s: %s", company, e)
            return []

    def _matches_queries(self, job: JobData, query_terms: list[str]) -> bool:
        """Check if job matches any search queries."""
        searchable = " ".join(
            [
                job.title,
                job.company,
                job.description or "",
                job.location or "",
            ]
        ).lower()

        return any(term in searchable for term in query_terms)

    def _parse_job(self, data: dict, company_slug: str) -> Optional[JobData]:
        """Parse Lever job data to JobData."""
        try:
            # Get location
            location = data.get("categories", {}).get("location")

            # Determine if remote
            is_remote = False
            commitment = data.get("categories", {}).get("commitment", "")
            if location:
                is_remote = any(
                    term in location.lower()
                    for term in ["remote", "anywhere", "worldwide"]
                )
            if "remote" in commitment.lower():
                is_remote = True

            # Parse date
            posted_date = None
            if data.get("createdAt"):
                try:
                    posted_date = datetime.fromtimestamp(data["createdAt"] / 1000)
                except (ValueError, TypeError):
                    pass

            # Get company name (capitalize slug)
            company_name = company_slug.replace("-", " ").title()

            # Get description - try plain text first, then strip HTML from regular description
            description = data.get("descriptionPlain", "")
            if not description:
                description = data.get("description", "")

            # Strip any remaining HTML tags
            if description and "<" in description:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text(separator=" ", strip=True)

            return JobData(
                title=data.get("text", ""),
                company=company_name,
                url=data.get("hostedUrl", ""),
                source="lever",
                location=location,
                description=description,
                salary_min=None,
                salary_max=None,
                apply_url=data.get("applyUrl", data.get("hostedUrl")),
                remote=is_remote,
                posted_date=posted_date,
                extra_data={
                    "team": data.get("categories", {}).get("team"),
                    "department": data.get("categories", {}).get("department"),
                    "commitment": commitment,
                },
            )
        except Exception as e:
            logger.error("Error parsing Lever job: %s", e)
            return None
